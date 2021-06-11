"""
    Paradox asset files, Blender import/export.

    As Blenders 3D space is (Z-up, right-handed) and the Clausewitz engine seems to be (Y-up, left-handed) we have to
    mirror all positions, normals etc about the XY plane AND rotate 90 about X and flip texture coordinates in V.
    Note - Blender treats matrices as column-major.
         - Blender 2.8 mathutils uses Pythons PEP 465 binary operator for multiplying matrices/vectors. @

    author : ross-g
"""

import os
import time
from operator import itemgetter
from collections import OrderedDict, namedtuple, defaultdict

try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

import bpy
import bmesh
import math
from mathutils import Vector, Matrix, Quaternion

from .. import pdx_data
from .. import IO_PDX_LOG


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

PDX_SHADER = "shader"
PDX_ANIMATION = "animation"
PDX_IGNOREJOINT = "pdxIgnoreJoint"
PDX_MESHINDEX = "meshindex"
PDX_MAXSKININFS = 4
PDX_MAXUVSETS = 4

PDX_DECIMALPTS = 5
PDX_ROUND_ROT = 4
PDX_ROUND_TRANS = 3
PDX_ROUND_SCALE = 2

# fmt: off
SPACE_MATRIX = Matrix((
    (1, 0, 0, 0),
    (0, 0, 1, 0),
    (0, 1, 0, 0),
    (0, 0, 0, 1)
))
BONESPACE_MATRIX = Matrix((
    (0, 1, 0, 0),
    (-1, 0, 0, 0),
    (0, 0, 1, 0),
    (0, 0, 0, 1)
))
# fmt: on


""" ====================================================================================================================
    Helper functions.
========================================================================================================================
"""


def util_round(data, ndigits=0):
    return tuple(round(x, ndigits) for x in data)


def clean_imported_name(name):
    # strip any namespace names, taking the final name only
    clean_name = name.split(":")[-1]

    # replace hierarchy separator character used by Maya in the case of non-unique leaf node names
    clean_name = clean_name.replace("|", "_")

    return clean_name


def get_bmesh(mesh_data, *args):
    """Returns a BMesh from existing mesh data.
    face_normals=True, use_shape_key=False, shape_key_index=0"""
    bm = bmesh.new()
    bm.from_mesh(mesh_data, *args)

    return bm


def get_rig_from_bone_name(bone_name):
    scene_rigs = [obj for obj in bpy.data.objects if type(obj.data) == bpy.types.Armature]

    for rig in scene_rigs:
        armt = rig.data
        if bone_name in [b.name for b in armt.bones]:
            return rig


def get_rig_from_mesh(blender_obj):
    skin_modifier = [mod for mod in blender_obj.modifiers if type(mod) == bpy.types.ArmatureModifier]

    if skin_modifier:
        # we only allow a mesh to be connected to one armature modifier
        skin = skin_modifier[0]
        # get the armature referenced by the modifier
        rig = skin.object
    else:
        rig = None

    return rig


def list_scene_pdx_meshes():
    # restrict to current scene, so use bpy.context.scene.objects not bpy.data.objects
    return [obj for obj in bpy.context.scene.objects if type(obj.data) == bpy.types.Mesh and check_mesh_material(obj)]


def set_local_axis_display(state, data_type):
    type_dict = {"EMPTY": type(None), "ARMATURE": bpy.types.Armature}
    object_list = [obj for obj in bpy.data.objects if type(obj.data) == type_dict[data_type]]

    for node in object_list:
        try:
            node.show_axis = state
            if node.data:
                node.data.show_axes = state
        except Exception as err:
            IO_PDX_LOG.warning("could not display local axis for node - {0}".format(node.name))
            IO_PDX_LOG.error(err)


def set_ignore_joints(state):
    sel_pose_bones = bpy.context.selected_pose_bones or []
    sel_edit_bones = bpy.context.selected_editable_bones or []

    bone_list = [posebone.bone for posebone in sel_pose_bones] + sel_edit_bones

    for bone in bone_list:
        bone[PDX_IGNOREJOINT] = state


def set_mesh_index(blender_mesh, i):
    if PDX_MESHINDEX not in blender_mesh.keys():
        blender_mesh["_RNA_UI"] = {}
        blender_mesh["_RNA_UI"][PDX_MESHINDEX] = {"min": 0, "max": 255, "soft_min": 0, "soft_max": 255, "step": 1}

    blender_mesh[PDX_MESHINDEX] = i


def get_mesh_index(blender_mesh):
    return blender_mesh.get(PDX_MESHINDEX, 255)


def check_mesh_material(blender_obj):
    """ Object needs at least one of it's materials to be a PDX material if we're going to export it. """
    result = False

    materials = [slot.material for slot in blender_obj.material_slots]
    for material in materials:
        if material:
            result = result or (PDX_SHADER in material.keys())

    return result


def get_material_shader(blender_material):
    return blender_material.get(PDX_SHADER, None)


def get_material_textures(blender_material):
    texture_dict = dict()

    node_tree = blender_material.node_tree
    nodes = node_tree.nodes

    # find the first valid Matrial Output node linked to a Surface shader
    try:
        material_output = next(
            n for n in nodes if type(n) == bpy.types.ShaderNodeOutputMaterial and n.inputs["Surface"].is_linked
        )
    except StopIteration:
        raise RuntimeError("No connected 'Material Output' found for material: {0}".format(blender_material.name))

    surface_input = material_output.inputs["Surface"].links[0]
    shader_root = surface_input.from_node
    if not type(surface_input.from_socket) == bpy.types.NodeSocketShader:
        raise RuntimeError(
            "No BSDF shader connected to 'Material Output > Surface' for material: {0}".format(blender_material.name)
        )

    # follow linked Shader node inputs up the node tree until we find a connected Image Texture node
    for bsdf_input, pdxmaterial_slot in zip(["Base Color", "Roughness", "Normal"], ["diff", "spec", "n"]):
        if shader_root.inputs[bsdf_input].is_linked:
            try:
                input_node = shader_root.inputs[bsdf_input].links[0].from_node
                while type(input_node) != bpy.types.ShaderNodeTexImage:
                    # just check the first connected input for simplicity and continue upstream
                    first_link = next(i for i in input_node.inputs if i.is_linked)
                    input_node = first_link.links[0].from_node

                tex_filepath = input_node.image.filepath_from_user()
                texture_dict[pdxmaterial_slot] = tex_filepath

            except StopIteration:
                IO_PDX_LOG.warning(
                    "no connected '{0}' image texture found for - {1}".format(bsdf_input, blender_material.name)
                )

    return texture_dict


def get_mesh_info(blender_obj, mat_index, split_all_vertices=False, round_data=False):
    """Returns a dictionary of mesh information neccessary for the exporter.
    By default this merges vertices across triangles where normal and UV data is shared, otherwise each tri-vert is
    exported separately!"""
    # get mesh and Bmesh data structures for this object
    mesh = blender_obj.data.copy()  # blender_obj.to_mesh(bpy.context.scene, True, 'PREVIEW')
    mesh.name = blender_obj.data.name + "_export"
    mesh.transform(blender_obj.matrix_world)
    mesh.calc_loop_triangles()
    mesh.calc_normals_split()

    # we will need to test vertices for equality based on their attributes
    # critically: whether per-face vertices (sharing an object-relative vert id) share normals and uvs
    UniqueVertex = namedtuple("UniqueVertex", ["id", "p", "n", "uv"])

    # cache some mesh data
    uv_setnames = [uv_set.name for uv_set in mesh.uv_layers if len(uv_set.data)][:PDX_MAXUVSETS]
    if uv_setnames:
        mesh.calc_tangents(uvmap=uv_setnames[0])

    # build a blank dictionary of mesh information for the exporter
    mesh_dict = {x: [] for x in ["p", "n", "ta", "u0", "u1", "u2", "u3", "tri", "min", "max"]}

    # collect all unique verts in the order that we process them
    export_verts = []
    unique_verts = set()

    # for tri in bm.faces:  # all Bmesh faces were triangulated previously
    # store data for each loop triangle
    for tri in mesh.loop_triangles:
        if tri.material_index != mat_index:
            continue  # skip this triangle if it has the wrong material index

        # implementation note: the official PDX exporter seems to process verts, in vertex order, for each triangle
        # we must sort the list of loops in vert order, as by default Blender can return a different order
        # required to support exporting new Blendshape targets where the base mesh came from the PDX exporter
        _sorted = sorted(enumerate([mesh.loops[i] for i in tri.loops]), key=lambda x: x[1].vertex_index)
        sorted_indices = [i[0] for i in _sorted]  # track sorting change
        sorted_loops = [i[1] for i in _sorted]

        dict_vert_idx = []

        for loop in sorted_loops:
            vert_id = loop.vertex_index

            # position
            _position = mesh.vertices[vert_id].co
            _position = tuple(swap_coord_space(_position))
            if round_data:
                _position = util_round(_position, PDX_DECIMALPTS)

            # normal
            _normal = loop.normal
            _normal = tuple(swap_coord_space(_normal))
            if round_data:
                _normal = util_round(_normal, PDX_DECIMALPTS)

            # uv
            _uv_coords = ()
            for i, uv_set in enumerate(uv_setnames):
                uv_layer = mesh.uv_layers[uv_set]
                uv = uv_layer.data[loop.index].uv
                uv = tuple(swap_coord_space(tuple(uv)))
                if round_data:
                    uv = util_round(uv, PDX_DECIMALPTS)
                _uv_coords += (uv,)

            # tangent (omitted if there were no UVs)
            if uv_setnames:
                _bitangent_sign = loop.bitangent_sign
                _tangent = loop.tangent
                _tangent = tuple(swap_coord_space(_tangent))
                if round_data:
                    _tangent = util_round(_tangent, PDX_DECIMALPTS)

            # check if this tri-vert is new and unique, or can if we can just use an existing vertex
            new_vert = UniqueVertex(vert_id, _position, _normal, _uv_coords)

            # test if we have already stored this vertex in the unique set
            i = None
            if not split_all_vertices:
                if new_vert in unique_verts:
                    # no new data to be added to the mesh dict, the tri will reference an existing vert
                    i = export_verts.index(new_vert)

            if i is None:
                # collect the new vertex
                unique_verts.add(new_vert)
                export_verts.append(new_vert)

                # add this vert data to the mesh dict
                mesh_dict["p"].extend(_position)
                mesh_dict["n"].extend(_normal)
                for i, uv_set in enumerate(uv_setnames):
                    mesh_dict["u" + str(i)].extend(_uv_coords[i])
                if uv_setnames:
                    mesh_dict["ta"].extend(_tangent)
                    mesh_dict["ta"].append(_bitangent_sign)  # UV winding order
                # the tri will reference the last added vertex
                i = len(export_verts) - 1

            # store the tri-vert reference
            dict_vert_idx.append(i)

        # tri-faces (converting handedness to Game space)
        mesh_dict["tri"].extend(
            # to build the tri-face correctly, we need to use the original unsorted vertex order to reference verts
            [dict_vert_idx[sorted_indices[0]], dict_vert_idx[sorted_indices[2]], dict_vert_idx[sorted_indices[1]]]
        )

    # calculate min and max bounds of mesh
    x_vtx_pos = set([mesh_dict["p"][j] for j in range(0, len(mesh_dict["p"]), 3)])
    y_vtx_pos = set([mesh_dict["p"][j + 1] for j in range(0, len(mesh_dict["p"]), 3)])
    z_vtx_pos = set([mesh_dict["p"][j + 2] for j in range(0, len(mesh_dict["p"]), 3)])
    mesh_dict["min"] = [min(x_vtx_pos), min(y_vtx_pos), min(z_vtx_pos)]
    mesh_dict["max"] = [max(x_vtx_pos), max(y_vtx_pos), max(z_vtx_pos)]

    # create an ordered list of vertex ids that we have gathered into the mesh dict
    vert_id_list = [vert.id for vert in export_verts]

    # cleanup
    bpy.data.meshes.remove(mesh)  # delete duplicate mesh datablock

    return mesh_dict, vert_id_list


def get_mesh_skin_info(blender_obj, vertex_ids=None):
    """
    bpy.ops.object.vertex_group_limit_total(group_select_mode='', limit=4)
    """
    skin_mod = [mod for mod in blender_obj.modifiers if type(mod) == bpy.types.ArmatureModifier]
    if not skin_mod:
        return None

    # a mesh can only be connected to one armature modifier
    skin = skin_mod[0]
    # get the armature referenced by the modifier
    rig = skin.object
    if rig is None:
        return None

    # build a dictionary of skin information for the exporter
    skin_dict = {x: [] for x in ["bones", "ix", "w"]}

    # set number of joint influences per vert
    skin_dict["bones"].append(PDX_MAXSKININFS)

    # find bone/vertex-group influences
    bone_names = [bone.name for bone in get_skeleton_hierarchy(rig)]
    group_names = [group.name for group in blender_obj.vertex_groups]

    # parse all verts in order if we didn't supply a subset of vert ids
    mesh = blender_obj.data
    if vertex_ids is None:
        vertex_ids = range(len(mesh.vertices))

    # iterate over influences to find weights, per vertex
    vert_weights = {v: {} for v in vertex_ids}
    for vert_id, vtx in enumerate(mesh.vertices):
        for vtx_group in vtx.groups:
            group_index = vtx_group.group
            # get bone index by group name lookup, as it's not guaranteed that group indices and bone indices line up
            try:
                bone_index = bone_names.index(group_names[group_index])
            except ValueError:
                raise RuntimeError(
                    "Mesh {0} has vertices skinned to a group ({1}) targeting a missing or excluded armature bone!"
                    "Check all bones using the '{2}' property.".format(
                        mesh.name, group_names[group_index], PDX_IGNOREJOINT
                    )
                )
            if group_index < len(blender_obj.vertex_groups):
                # check we actually want this vertex (in case of material split meshes)
                if vert_id in vertex_ids:
                    # store any non-zero weights, by influence, per vertex
                    weight = vtx_group.weight
                    if weight != 0.0:
                        vert_weights[vert_id][bone_index] = vtx_group.weight

    # collect data from the weights dict into the skin dict
    for vtx in vertex_ids:
        # if we have excess influences, prune them and renormalise weights
        if len(vert_weights[vtx]) > PDX_MAXSKININFS:
            IO_PDX_LOG.warning(
                "Mesh '{0}' has vertices skinned to more than {1} vertex groups.".format(mesh.name, PDX_MAXSKININFS)
            )
            # sort by influence and remove the smallest
            inf_weights = sorted(vert_weights[vtx].items(), key=itemgetter(1), reverse=True)
            inf_weights = dict(inf_weights[:PDX_MAXSKININFS])
            total = sum(inf_weights.values())

            vert_weights[vtx] = {inf: weight / total for inf, weight in inf_weights.items()}

        # store influence and weight data
        for influence, weight in vert_weights[vtx].items():
            skin_dict["ix"].append(influence)
            skin_dict["w"].append(weight)

        if len(vert_weights[vtx]) <= PDX_MAXSKININFS:
            # pad out with null data to fill the maximum influence count
            padding = PDX_MAXSKININFS - len(vert_weights[vtx])
            skin_dict["ix"].extend([-1] * padding)
            skin_dict["w"].extend([0.0] * padding)

    return skin_dict


def get_mesh_skeleton_info(blender_obj):
    rig = get_rig_from_mesh(blender_obj)
    if rig is None:
        return []

    # find all bones in hierarchy to be exported
    rig_bones = get_skeleton_hierarchy(rig)

    return get_bones_info(rig_bones)


def get_bones_info(blender_bones):
    # build a list of bone information dictionaries for the exporter
    bone_list = [{"name": x.name} for x in blender_bones]

    for i, bone in enumerate(blender_bones):
        # bone index
        bone_list[i]["ix"] = [i]

        # bone parent index
        if bone.parent:
            bone_list[i]["pa"] = [blender_bones.index(bone.parent)]

        # bone inverse world-space transform
        armature = bone.id_data
        rig = [obj for obj in bpy.data.objects if type(obj.data) == bpy.types.Armature and obj.data == armature][0]
        mat = swap_coord_space(rig.matrix_world @ bone.matrix_local).inverted_safe()
        mat.transpose()
        mat = [i for vector in mat for i in vector]  # flatten matrix to list
        bone_list[i]["tx"] = []
        bone_list[i]["tx"].extend(mat[0:3])
        bone_list[i]["tx"].extend(mat[4:7])
        bone_list[i]["tx"].extend(mat[8:11])
        bone_list[i]["tx"].extend(mat[12:15])

    return bone_list


def get_locators_info(blender_empties):
    # build a list of locator information dictionaries for the exporter
    locator_list = [{"name": x.name} for x in blender_empties]

    for i, obj in enumerate(blender_empties):
        # unparented, use worldspace position/rotation
        _transform = obj.matrix_world

        # parented to bone, use local position/rotation
        if obj.parent and obj.parent_type == "BONE":
            locator_list[i]["pa"] = [obj.parent_bone]
            rig = obj.parent
            bone_matrix = rig.matrix_world @ rig.data.bones[obj.parent_bone].matrix_local
            # TODO: test if this should be .matrix_world or .matrix_local
            _transform = bone_matrix.inverted_safe() @ obj.matrix_world

        _position, _rotation, _scale = swap_coord_space(_transform).decompose()

        locator_list[i]["p"] = list(_position)
        # convert quaternions from wxyz to xyzw
        locator_list[i]["q"] = list([_rotation[1], _rotation[2], _rotation[3], _rotation[0]])

        is_scaled = util_round(list(_scale), PDX_ROUND_SCALE) != (1.0, 1.0, 1.0)
        # TODO: check engine config here to see if full 'tx' attribute is supported
        if is_scaled:
            transform = swap_coord_space(_transform)
            locator_list[i]["tx"] = [
                transform[0][0],
                transform[1][0],
                transform[2][0],
                transform[3][0],
                transform[0][1],
                transform[1][1],
                transform[2][1],
                transform[3][1],
                transform[0][2],
                transform[1][2],
                transform[2][2],
                transform[3][2],
                transform[0][3],
                transform[1][3],
                transform[2][3],
                transform[3][3],
            ]

    return locator_list


def get_skeleton_hierarchy(rig):
    root_bone = rig.data.bones[0]

    def get_recursive_children(bone, hierarchy):
        hierarchy.append(bone)
        children = [jnt for jnt in bone.children if not jnt.get(PDX_IGNOREJOINT)]

        for bone in children:
            get_recursive_children(bone, hierarchy)

        return hierarchy

    valid_bones = []
    get_recursive_children(root_bone, valid_bones)

    return valid_bones


def get_scene_animdata(rig, export_bones, startframe, endframe, round_data=True):
    # store transform for each bone over the frame range
    frames_data = defaultdict(list)

    for f in range(startframe, endframe + 1):
        bpy.context.scene.frame_set(f)
        for bone in export_bones:
            pose_bone = rig.pose.bones[bone.name]

            # build a matrix describing the transform from parent bone
            parent_matrix = Matrix()
            if pose_bone.parent:
                # parent_matrix = pose_bone.parent.matrix.copy()
                parent_matrix = rig.convert_space(
                    pose_bone=pose_bone.parent, matrix=pose_bone.parent.matrix, from_space="POSE", to_space="WORLD"
                )

            # offset_matrix = parent_matrix.inverted_safe() @ pose_bone.matrix
            pose_matrix = rig.convert_space(
                pose_bone=pose_bone, matrix=pose_bone.matrix, from_space="POSE", to_space="WORLD"
            )
            offset_matrix = parent_matrix.inverted_safe() @ pose_matrix
            _translation, _rotation, _scale = swap_coord_space(offset_matrix).decompose()

            frames_data[bone.name].append((_translation, _rotation, _scale))

    # create an ordered dictionary of all animated bones to store sample data
    all_bone_keyframes = OrderedDict()
    for bone in export_bones:
        all_bone_keyframes[bone.name] = dict()

    # determine if any transform attributes were animated over this frame range for each bone
    for bone in export_bones:
        # convert data from list of tuples [(t,q,s)] to three nested lists [t][q][s]
        t_list, q_list, s_list = zip(*frames_data[bone.name])

        if round_data:
            t_list = [util_round(t, PDX_ROUND_TRANS) for t in t_list]
            q_list = [util_round(q, PDX_ROUND_ROT) for q in q_list]
            s_list = [util_round(s, PDX_ROUND_SCALE) for s in s_list]
        else:
            t_list = [t.freeze() for t in t_list]  # call freeze so Blender data can be hashed into a set
            q_list = [q.freeze() for q in q_list]
            s_list = [s.freeze() for s in s_list]

        # convert quaternions from wxyz to xyzw
        q_list = [(q[1], q[2], q[3], q[0]) for q in q_list]

        # store any animated transform samples per attribute
        for attr, attr_list in zip(["t", "q", "s"], [t_list, q_list, s_list]):
            if len(set(attr_list)) != 1:
                all_bone_keyframes[bone.name][attr] = attr_list

    return all_bone_keyframes


def swap_coord_space(data):
    """ Transforms from PDX space (-Z forward, Y up) to Blender space (-Y forward, Z up). """
    global SPACE_MATRIX

    # matrix
    if type(data) == Matrix:
        return SPACE_MATRIX @ data.to_4x4() @ SPACE_MATRIX.inverted_safe()
    # quaternion
    elif type(data) == Quaternion:
        mat = data.to_matrix()
        return (SPACE_MATRIX @ mat.to_4x4() @ SPACE_MATRIX.inverted_safe()).to_quaternion()
    # vector
    elif type(data) == Vector or len(data) == 3:
        vec = Vector(data)
        return vec @ SPACE_MATRIX
    # uv coordinate
    elif len(data) == 2:
        return data[0], 1 - data[1]
    # unknown
    else:
        raise NotImplementedError("Unknown data type encountered.")


""" ====================================================================================================================
    Functions.
========================================================================================================================
"""


def create_node_texture(node_tree, tex_filepath, as_data=False):
    teximage_node = node_tree.nodes.new("ShaderNodeTexImage")

    if tex_filepath is not None:
        texture_name = os.path.basename(tex_filepath)

        try:
            # path exists on disc, just load the image if we haven't already done so
            new_image = bpy.data.images.load(tex_filepath, check_existing=True)
        except RuntimeError:
            # check for existing named placeholder image
            if texture_name in bpy.data.images:
                new_image = bpy.data.images[texture_name]
            else:
                # create a named placeholder image for a missing texture file
                new_image = bpy.data.images.new(texture_name, 32, 32)
                new_image.source = "FILE"
            # highlight node to show error
            teximage_node.color = (1, 0, 0)
            teximage_node.use_custom_color = True

        if not os.path.isfile(tex_filepath):
            IO_PDX_LOG.warning("unable to find texture filepath - {0}".format(tex_filepath))

        new_image.use_fake_user = True
        new_image.alpha_mode = "CHANNEL_PACKED"
        new_image.colorspace_settings.is_data = as_data

        teximage_node.name = texture_name
        teximage_node.image = new_image

    return teximage_node


def create_shader(PDX_material, shader_name, texture_dir, template_only=False):
    new_shader = bpy.data.materials.new(shader_name)
    new_shader[PDX_SHADER] = PDX_material.shader[0]
    new_shader.use_fake_user = True
    new_shader.use_nodes = True

    new_shader.use_backface_culling = True
    new_shader.shadow_method = "CLIP"
    new_shader.blend_method = "CLIP"

    def set_node_pos(node, x, y):
        node.location = Vector((x * 300.0, y * -300.0))

    node_tree = new_shader.node_tree
    nodes = node_tree.nodes
    links = node_tree.links

    shader_root = nodes.get("Principled BSDF")
    if shader_root is None:
        # if we can't find the root node we expect, clear the graph and create from scratch
        nodes.clear()
        output = nodes.new(type="ShaderNodeOutputMaterial")
        shader_root = nodes.new(type="ShaderNodeBsdfPrincipled")

        links.new(shader_root.outputs["BSDF"], output.inputs["Surface"])
        set_node_pos(output, 1, 0)

    # link up diffuse texture to base-color slot
    if getattr(PDX_material, "diff", None) or template_only:
        texture_path = None if template_only else os.path.join(texture_dir, PDX_material.diff[0])

        albedo_texture = create_node_texture(node_tree, texture_path)
        set_node_pos(albedo_texture, -5, 0)

        links.new(albedo_texture.outputs["Color"], shader_root.inputs["Base Color"])
        # links.new(albedo_texture.outputs['Alpha'], shader_root.inputs['Alpha'])  # diffuse.A sometimes used for alpha

    # link up specular texture to roughness, metallic and specular slots
    if getattr(PDX_material, "spec", None) or template_only:
        texture_path = None if template_only else os.path.join(texture_dir, PDX_material.spec[0])

        material_texture = create_node_texture(node_tree, texture_path, as_data=True)
        set_node_pos(material_texture, -5, 1)

        separate_rgb = node_tree.nodes.new(type="ShaderNodeSeparateRGB")
        set_node_pos(separate_rgb, -4, 1)

        links.new(material_texture.outputs["Color"], separate_rgb.inputs["Image"])
        # links.new(separate_rgb.outputs['R'], shader_root.inputs['Specular'])  # material.R used for custom mask?
        links.new(separate_rgb.outputs["G"], shader_root.inputs["Specular"])
        links.new(separate_rgb.outputs["B"], shader_root.inputs["Metallic"])
        links.new(material_texture.outputs["Alpha"], shader_root.inputs["Roughness"])

    # link up normal texture to normal slot
    if getattr(PDX_material, "n", None) or template_only:
        texture_path = None if template_only else os.path.join(texture_dir, PDX_material.n[0])

        normal_texture = create_node_texture(node_tree, texture_path, as_data=True)
        set_node_pos(normal_texture, -5, 2)

        separate_rgb = node_tree.nodes.new(type="ShaderNodeSeparateRGB")
        set_node_pos(separate_rgb, -4, 2)
        combine_rgb = node_tree.nodes.new(type="ShaderNodeCombineRGB")
        combine_rgb.inputs["B"].default_value = 1.0
        set_node_pos(combine_rgb, -3, 2)

        normal_map = node_tree.nodes.new("ShaderNodeNormalMap")
        set_node_pos(normal_map, -2, 2)

        links.new(normal_texture.outputs["Color"], separate_rgb.inputs["Image"])
        links.new(separate_rgb.outputs["G"], combine_rgb.inputs["R"])
        # links.new(separate_rgb.outputs['B'], combine_rgb.inputs['R'])  # normal.B used for emissive?
        links.new(normal_texture.outputs["Alpha"], combine_rgb.inputs["G"])
        links.new(combine_rgb.outputs["Image"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], shader_root.inputs["Normal"])

    return new_shader


def create_material(PDX_material, mesh, texture_path):
    shader_name = "PDXmat_" + mesh.name
    shader = create_shader(PDX_material, shader_name, texture_path)

    mesh.materials.append(shader)


def create_locator(PDX_locator, PDX_bone_dict):
    # create locator and link to the scene
    new_loc = bpy.data.objects.new(PDX_locator.name, None)
    new_loc.empty_display_type = "PLAIN_AXES"
    new_loc.empty_display_size = 0.4
    new_loc.show_axis = False

    bpy.context.scene.collection.objects.link(new_loc)

    # check for a parent relationship
    parent = getattr(PDX_locator, "pa", None)
    parent_Xform = None

    if parent is not None:
        # parent the locator to a bone in the armature
        rig = get_rig_from_bone_name(parent[0])
        if rig:
            new_loc.parent = rig
            new_loc.parent_bone = parent[0]
            new_loc.parent_type = "BONE"
            new_loc.matrix_world = Matrix()  # reset transform after parenting

        # determine the locators transform
        if parent[0] in PDX_bone_dict:
            transform = PDX_bone_dict[parent[0]]
            # note we transpose the matrix on creation
            parent_Xform = Matrix(
                (
                    (transform[0], transform[3], transform[6], transform[9]),
                    (transform[1], transform[4], transform[7], transform[10]),
                    (transform[2], transform[5], transform[8], transform[11]),
                    (0.0, 0.0, 0.0, 1.0),
                )
            )
            # rescale or recompose matrix so we always treat bones at 1.0 scale on import
            loc, rot, scale = parent_Xform.decompose()
            try:
                parent_Xform = Matrix.Scale(1.0 / scale[0], 4) @ parent_Xform
            except ZeroDivisionError:  # guard against zero scale bones...
                parent_Xform = Matrix.Translation(loc) @ rot.to_matrix().to_4x4() @ Matrix.Scale(1.0, 4)
        else:
            IO_PDX_LOG.warning(
                "unable to create locator '{0}' (missing parent '{1}' in file data)".format(PDX_locator.name, parent[0])
            )
            bpy.data.objects.remove(new_loc)
            return

    # if full transformation is available, set transformation directly
    if hasattr(PDX_locator, "tx"):
        # fmt: off
        loc_matrix = Matrix((
            (PDX_locator.tx[0], PDX_locator.tx[4], PDX_locator.tx[8], PDX_locator.tx[12]),
            (PDX_locator.tx[1], PDX_locator.tx[5], PDX_locator.tx[9], PDX_locator.tx[13]),
            (PDX_locator.tx[2], PDX_locator.tx[6], PDX_locator.tx[10], PDX_locator.tx[14]),
            (PDX_locator.tx[3], PDX_locator.tx[7], PDX_locator.tx[11], PDX_locator.tx[15]),
        ))
        # fmt: on
    # otherwise just rotate and translate components
    else:
        # compose transform parts
        _scale = Matrix.Scale(1, 4)
        _rotation = (
            Quaternion((PDX_locator.q[3], PDX_locator.q[0], PDX_locator.q[1], PDX_locator.q[2])).to_matrix().to_4x4()
        )
        _translation = Matrix.Translation(PDX_locator.p)

        loc_matrix = _translation @ _rotation @ _scale

    # apply parent transform
    if parent_Xform is not None:
        # TODO: why is the transposed multiplication needed?
        # must be multiplied in transposed form, then re-transposed before being applied
        loc_matrix = (loc_matrix.transposed() @ parent_Xform.inverted_safe().transposed()).transposed()

    new_loc.matrix_world = swap_coord_space(loc_matrix)
    new_loc.rotation_mode = "XYZ"

    bpy.context.view_layer.update()

    return new_loc


def create_skeleton(PDX_bone_list, convert_bonespace=False):
    # keep track of bones as we create them (may not be created in indexed order)
    bone_list = [None for _ in range(0, len(PDX_bone_list))]

    # check this skeleton is not already built in the scene
    matching_rigs = [get_rig_from_bone_name(clean_imported_name(bone.name)) for bone in PDX_bone_list]
    matching_rigs = list(set(rig for rig in matching_rigs if rig))
    if len(matching_rigs) == 1:
        IO_PDX_LOG.debug("matching armature already found in scene")
        return matching_rigs[0]

    # temporary name used during creation
    tmp_rig_name = "io_pdx_rig"

    # create the armature datablock
    armt = bpy.data.armatures.new("armature")
    armt.name = "imported_armature"
    armt.display_type = "STICK"

    # create the object and link to the scene
    new_rig = bpy.data.objects.new(tmp_rig_name, armt)
    bpy.context.scene.collection.objects.link(new_rig)
    bpy.context.view_layer.objects.active = new_rig
    new_rig.show_in_front = True
    new_rig.select_set(state=True)

    bpy.ops.object.mode_set(mode="EDIT")
    for bone in PDX_bone_list:
        index = bone.ix[0]
        transform = bone.tx
        parent = getattr(bone, "pa", None)

        # determine unique bone name
        # Maya allows non-unique transform names (on leaf nodes) and handles it internally by using | separators
        unique_name = clean_imported_name(bone.name)

        # create joint
        new_bone = armt.edit_bones.new(name=unique_name)
        new_bone.select = True
        new_bone.inherit_scale = "NONE"
        bone_list[index] = new_bone

        # connect to parent
        if parent is not None:
            parent_bone = bone_list[parent[0]]
            new_bone.parent = parent_bone
            new_bone.use_connect = False

        # determine bone head transform
        # fmt: off
        mat = Matrix((
            (transform[0], transform[3], transform[6], transform[9]),
            (transform[1], transform[4], transform[7], transform[10]),
            (transform[2], transform[5], transform[8], transform[11]),
            (0.0, 0.0, 0.0, 1.0),
        ))
        # fmt: on
        # rescale or recompose matrix so we always import bones at 1.0 scale
        loc, rot, scale = mat.decompose()
        try:
            safemat = Matrix.Scale(1.0 / scale[0], 4) @ mat
        except ZeroDivisionError:  # guard against zero scale bones...
            IO_PDX_LOG.warning("bad transform found on bone '{0}' (defaulting to bone scale 1.0)".format(unique_name))
            safemat = Matrix.Translation(loc) @ rot.to_matrix().to_4x4() @ Matrix.Scale(1.0, 4)

        # determine avg distance to any children
        bone_children = [b for b in PDX_bone_list if getattr(b, "pa", [None]) == bone.ix]
        bone_dists = []
        for child in bone_children:
            child_transform = child.tx
            # fmt: off
            c_mat = Matrix((
                (child_transform[0], child_transform[3], child_transform[6], child_transform[9]),
                (child_transform[1], child_transform[4], child_transform[7], child_transform[10]),
                (child_transform[2], child_transform[5], child_transform[8], child_transform[11]),
                (0.0, 0.0, 0.0, 1.0),
            ))
            # fmt: on
            c_dist = c_mat.to_translation() - safemat.to_translation()
            bone_dists.append(math.sqrt(c_dist.x ** 2 + c_dist.y ** 2 + c_dist.z ** 2))

        avg_dist = 5.0
        if bone_children:
            avg_dist = sum(bone_dists) / len(bone_dists)
        avg_dist = min(max(1.0, avg_dist), 10.0) * 0.05

        # set bone tail offset first
        new_bone.tail = Vector((0.0, 0.0, avg_dist))
        # set matrix directly as this includes bone roll/rotation
        new_bone.matrix = swap_coord_space(safemat.inverted_safe())
        if convert_bonespace:
            new_bone.matrix = swap_coord_space(safemat.inverted_safe()) @ BONESPACE_MATRIX

        IO_PDX_LOG.debug("new bone created - {}".format(new_bone.name))

    # set or correct some bone settings based on hierarchy
    for bone in bone_list:
        # Blender culls zero length bones, nudge the tail to ensure we don't create any
        if bone.length == 0:
            # FIXME : is this safe? this would affect bone rotation?
            bone.tail += Vector((0, 0, 0.1))

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()

    return new_rig


def create_skin(PDX_skin, PDX_bones, obj, rig, max_infs=None):
    if max_infs is None:
        max_infs = PDX_MAXSKININFS

    # create dictionary of skinning info per bone
    skin_dict = dict()

    num_infs = PDX_skin.bones[0]
    armt_bones = rig.data.bones

    for vtx in range(0, int(len(PDX_skin.ix) / max_infs)):
        skin_dict[vtx] = dict(joints=[], weights=[])

    # gather joint index and weighting that each vertex is skinned to
    for vtx, j in enumerate(range(0, len(PDX_skin.ix), max_infs)):
        skin_dict[vtx]["joints"] = PDX_skin.ix[j : j + num_infs]
        skin_dict[vtx]["weights"] = PDX_skin.w[j : j + num_infs]

    # create skin weight vertex groups
    for bone in armt_bones:
        obj.vertex_groups.new(name=bone.name)

    # set all skin weights
    for v in range(len(skin_dict.keys())):
        joints = [PDX_bones[j].name for j in skin_dict[v]["joints"]]
        weights = skin_dict[v]["weights"]
        # normalise joint weights
        try:
            norm_weights = [float(w) / sum(weights) for w in weights]
        except Exception as err:
            norm_weights = weights
            IO_PDX_LOG.error(err)
        # strip zero weight entries
        joint_weights = [(j, w) for j, w in zip(joints, norm_weights) if w != 0.0]

        for joint, weight in joint_weights:
            obj.vertex_groups[clean_imported_name(joint)].add([v], weight, "REPLACE")

    # create an armature modifier for the mesh object
    skin_mod = obj.modifiers.new(rig.name + "_skin", "ARMATURE")
    skin_mod.object = rig
    skin_mod.use_bone_envelopes = False
    skin_mod.use_vertex_groups = True


def create_mesh(PDX_mesh, name=None):
    # temporary name used during creation
    tmp_mesh_name = "io_pdx_mesh"

    # vertices
    verts = PDX_mesh.p  # flat list of 3d co-ordinates, verts[:2] = vtx[0]

    # normals
    norms = None
    if hasattr(PDX_mesh, "n"):
        norms = PDX_mesh.n  # flat list of vectors, norms[:2] = nrm[0]

    # triangles
    tris = PDX_mesh.tri  # flat list of vertex connections, tris[:3] = face[0]

    # UVs (channels 0 to 3)
    uv_Ch = dict()
    for i, uv in enumerate(["u0", "u1", "u2", "u3"]):
        if hasattr(PDX_mesh, uv):
            uv_Ch[i] = getattr(PDX_mesh, uv)  # flat list of 2d co-ordinates, u0[:1] = vtx[0]uv0

    # vertices
    vertexArray = []  # array of points
    for i in range(0, len(verts), 3):
        v = swap_coord_space([verts[i], verts[i + 1], verts[i + 2]])
        vertexArray.append(v)

    # faces
    faceArray = []
    for i in range(0, len(tris), 3):
        f = [tris[i + 2], tris[i + 1], tris[i]]  # convert handedness to Blender space
        faceArray.append(f)

    # create the mesh datablock
    new_mesh = bpy.data.meshes.new(tmp_mesh_name)

    # add mesh data
    new_mesh.from_pydata(vertexArray, [], faceArray)
    new_mesh.update()

    # create the object and link to the scene
    if name is None:
        mesh_name = tmp_mesh_name
    else:
        mesh_name = clean_imported_name(name)

    new_obj = bpy.data.objects.new(mesh_name, new_mesh)
    bpy.context.scene.collection.objects.link(new_obj)
    new_mesh.name = mesh_name
    new_obj.name = mesh_name.replace("Shape", "")

    # apply the vertex normal data
    if norms:
        normals = []
        for i in range(0, len(norms), 3):
            n = swap_coord_space([norms[i], norms[i + 1], norms[i + 2]])
            normals.append(n)

        new_mesh.polygons.foreach_set("use_smooth", [True] * len(new_mesh.polygons))
        new_mesh.normals_split_custom_set_from_vertices(normals)
        new_mesh.use_auto_smooth = True
        new_mesh.free_normals_split()

    # apply the UV data channels
    for idx in uv_Ch:
        uvSetName = "map" + str(idx + 1)
        new_mesh.uv_layers.new(name=uvSetName)

        uvArray = []
        uv_data = uv_Ch[idx]
        for i in range(0, len(uv_data), 2):
            uv = [uv_data[i], 1 - uv_data[i + 1]]  # flip the UV coords in V!
            uvArray.append(uv)

        bm = get_bmesh(new_mesh)
        uv_layer = bm.loops.layers.uv[uvSetName]

        for face in bm.faces:
            for loop in face.loops:
                i = loop.vert.index
                loop[uv_layer].uv = uvArray[i]

        bm.to_mesh(new_mesh)  # write the bmesh back to the mesh
        bm.free()

    # select the object
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = new_obj
    new_obj.select_set(state=True)

    return new_mesh, new_obj


def create_fcurve(armature, bone_name, data_type, index):
    # create anim data block on the armature
    if armature.animation_data is None:
        armature.animation_data_create()
    anim_data = armature.animation_data

    # create action data
    if anim_data.action is None:
        anim_data.action = bpy.data.actions.new(armature.name + "_action")
    action = anim_data.action

    # determine data path
    data_path = 'pose.bones["{0}"].{1}'.format(bone_name, data_type)

    # check if the fcurve for this data path and index already exists
    for curve in anim_data.action.fcurves:
        if curve.data_path != data_path:
            continue
        if index < 0 or curve.array_index == index:
            return curve

    # otherwise create a new fcurve inside the correct group
    if bone_name not in action.groups:  # create group if it doesn't exist
        action.groups.new(bone_name)
    f_curve = anim_data.action.fcurves.new(data_path, index, bone_name)

    return f_curve


def create_anim_keys(armature, bone_name, key_dict, timestart, pose):
    # TODO: this is very slow, create f-curves directly instead of keyframing
    pose_bone = armature.pose.bones[bone_name]

    # validate keyframe counts per attribute
    duration = list(set(len(keyframes) for keyframes in key_dict.values()))
    if len(duration) != 1:
        raise RuntimeError("Inconsistent keyframe animation lengths across attributes. {0}".format(bone_name))
    duration = duration[0]

    # calculate start and end frames
    timestart = int(timestart)
    timeend = timestart + duration

    # build a matrix describing the transform from parent bone in the initial pose
    pose_bone_initial = pose[bone_name]
    parent_initial = Matrix()
    if pose_bone.parent:
        parent_initial = pose[pose_bone.parent.name]

    parent_to_pose = parent_initial.inverted_safe() @ pose_bone_initial
    # decompose (so we can over write with animated components)
    _scale = Matrix.Scale(parent_to_pose.to_scale()[0], 4)
    _rotation = parent_to_pose.to_quaternion().to_matrix().to_4x4()
    _translation = Matrix.Translation(parent_to_pose.to_translation())

    # set transform per frame and insert keys on data channels
    for k, frame in enumerate(range(timestart, timeend)):
        bpy.context.scene.frame_set(frame)

        # determine if we have a parent matrix
        parent_world = Matrix()
        if pose_bone.parent:
            parent_world = pose_bone.parent.matrix

        # over-ride initial pose offset based on keyed attributes
        if "s" in key_dict:
            _scale = Matrix.Scale(key_dict["s"][k][0], 4)
            _scale = swap_coord_space(_scale)

        if "q" in key_dict:
            _rotation = (
                Quaternion((key_dict["q"][k][3], key_dict["q"][k][0], key_dict["q"][k][1], key_dict["q"][k][2]))
                .to_matrix()
                .to_4x4()
            )
            _rotation = swap_coord_space(_rotation)

        if "t" in key_dict:
            _translation = Matrix.Translation(key_dict["t"][k])
            _translation = swap_coord_space(_translation)

        # recompose
        offset_matrix = _translation @ _rotation @ _scale

        # apply offset matrix
        pose_bone.matrix = parent_world @ offset_matrix

        # set keyframes on the new transform
        if "s" in key_dict:
            pose_bone.keyframe_insert(data_path="scale", index=-1)
        if "q" in key_dict:
            pose_bone.keyframe_insert(data_path="rotation_quaternion", index=-1)
        if "t" in key_dict:
            pose_bone.keyframe_insert(data_path="location", index=-1)


""" ====================================================================================================================
    Main IO functions.
========================================================================================================================
"""


def import_meshfile(meshpath, imp_mesh=True, imp_skel=True, imp_locs=True, join_materials=True, bonespace=False):
    start = time.time()
    IO_PDX_LOG.info("importing - {0}".format(meshpath))

    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(meshpath)

    # find shapes and locators
    shapes = asset_elem.find("object")
    locators = asset_elem.find("locator")

    # store all bone transforms, irrespective of skin association
    scene_bone_dict = dict()

    # go through shapes
    for i, node in enumerate(shapes):
        IO_PDX_LOG.info("creating node {0}/{1} - {2}".format(i + 1, len(shapes), node.tag))

        # create the skeleton first, so we can skin the mesh to it
        rig = None
        skeleton = node.find("skeleton")
        if skeleton:
            pdx_bone_list = list()
            for b in skeleton:
                pdx_bone = pdx_data.PDXData(b)
                pdx_bone_list.append(pdx_bone)
                scene_bone_dict[pdx_bone.name] = pdx_bone.tx

            if imp_skel:
                IO_PDX_LOG.info("creating skeleton -")
                rig = create_skeleton(pdx_bone_list, convert_bonespace=bonespace)

        # then create all the meshes
        meshes = node.findall("mesh")
        if imp_mesh and meshes:
            created = []
            for mat_idx, m in enumerate(meshes):
                IO_PDX_LOG.info("creating mesh -")
                pdx_mesh = pdx_data.PDXData(m)
                pdx_material = getattr(pdx_mesh, "material", None)
                pdx_skin = getattr(pdx_mesh, "skin", None)

                # create the geometry
                if join_materials:
                    meshmaterial_name = node.tag if mat_idx == 0 else "{0}-{1:0>3}".format(node.tag, mat_idx)
                else:
                    meshmaterial_name = "{0}-{1:0>3}".format(node.tag, mat_idx)
                mesh, obj = create_mesh(pdx_mesh, name=meshmaterial_name)
                created.append(obj)

                # set mesh index from source file
                set_mesh_index(mesh, i)

                # create the material
                if pdx_material:
                    IO_PDX_LOG.info("creating material - {0}".format(pdx_material.name))
                    create_material(pdx_material, mesh, os.path.split(meshpath)[0])

                # create the vertex group skin
                if rig and pdx_skin:
                    IO_PDX_LOG.info("creating skinning data -")
                    create_skin(pdx_skin, pdx_bone_list, obj, rig)

            if join_materials and len(created) > 1:
                ctx = bpy.context.copy()
                ctx["active_object"] = created[0]
                ctx["selected_editable_objects"] = created
                bpy.ops.object.join(ctx)
                ctx.clear()

    # go through locators
    if imp_locs and locators:
        for i, loc in enumerate(locators):
            IO_PDX_LOG.info("creating locator {0}/{1} - {2}".format(i + 1, len(locators), loc.tag))
            pdx_locator = pdx_data.PDXData(loc)
            obj = create_locator(pdx_locator, scene_bone_dict)

    bpy.ops.object.select_all(action="DESELECT")
    IO_PDX_LOG.info("import finished! ({0:.4f} sec)".format(time.time() - start))


def export_meshfile(meshpath, exp_mesh=True, exp_skel=True, exp_locs=True, split_verts=False, exp_selected=False):
    start = time.time()
    IO_PDX_LOG.info("exporting - {0}".format(meshpath))

    # create an XML structure to store the object hierarchy
    root_xml = Xml.Element("File")
    root_xml.set("pdxasset", [1, 0])

    # create root element for objects
    object_xml = Xml.SubElement(root_xml, "object")

    # populate object data
    if exp_mesh:
        # get all meshes using at least one PDX material in the scene
        blender_meshes = list_scene_pdx_meshes()
        # optionally intersect with selection
        if exp_selected:
            blender_meshes = [obj for obj in blender_meshes if obj.select_get()]

        if len(blender_meshes) == 0:
            raise RuntimeError("Mesh export is selected, but found no meshes with PDX materials applied.")

        # sort meshes for export by index
        blender_meshes.sort(key=lambda obj: get_mesh_index(obj.data))

        for obj in blender_meshes:
            # create parent element for node data, if exporting meshes
            obj_name = obj.data.name
            IO_PDX_LOG.info("writing node - {0}".format(obj_name))
            objnode_xml = Xml.SubElement(object_xml, obj_name)

            # one object can have multiple materials on a per face basis
            materials = list(obj.data.materials)

            for mat_idx, blender_mat in enumerate(materials):
                # skip material slots that are empty or not PDX materials
                if blender_mat is None or PDX_SHADER not in blender_mat.keys():
                    continue

                # create parent element for this mesh (mesh here being faces sharing a material, within one object)
                IO_PDX_LOG.info("writing mesh - {0}".format(mat_idx))
                meshnode_xml = Xml.SubElement(objnode_xml, "mesh")

                # get all necessary info about this set of faces and determine which unique verts they include
                mesh_info_dict, vert_ids = get_mesh_info(obj, mat_idx, split_verts)

                # populate mesh attributes
                for key in ["p", "n", "ta", "u0", "u1", "u2", "u3", "tri"]:
                    if key in mesh_info_dict and mesh_info_dict[key]:
                        meshnode_xml.set(key, mesh_info_dict[key])

                # create parent element for bounding box data
                aabbnode_xml = Xml.SubElement(meshnode_xml, "aabb")
                for key in ["min", "max"]:
                    if key in mesh_info_dict and mesh_info_dict[key]:
                        aabbnode_xml.set(key, mesh_info_dict[key])

                # create parent element for material data
                IO_PDX_LOG.info("writing material -")
                materialnode_xml = Xml.SubElement(meshnode_xml, "material")
                # populate material attributes
                materialnode_xml.set("shader", [get_material_shader(blender_mat)])
                mat_texture_dict = get_material_textures(blender_mat)
                for slot, texture in mat_texture_dict.items():
                    materialnode_xml.set(slot, [os.path.split(texture)[1]])

                # create parent element for skin data, if the mesh is skinned
                skin_info_dict = get_mesh_skin_info(obj, vert_ids)
                if exp_skel and skin_info_dict:
                    IO_PDX_LOG.info("writing skinning data -")
                    skinnode_xml = Xml.SubElement(meshnode_xml, "skin")
                    for key in ["bones", "ix", "w"]:
                        if key in skin_info_dict and skin_info_dict[key]:
                            skinnode_xml.set(key, skin_info_dict[key])

            bone_info_list = get_mesh_skeleton_info(obj)
            # create parent element for skeleton data, if the mesh is skinned
            if exp_skel and bone_info_list:
                IO_PDX_LOG.info("writing skeleton -")
                skeletonnode_xml = Xml.SubElement(objnode_xml, "skeleton")

                # create sub-elements for each bone, populate bone attributes
                for bone_info_dict in bone_info_list:
                    bonenode_xml = Xml.SubElement(skeletonnode_xml, bone_info_dict["name"])
                    for key in ["ix", "pa", "tx"]:
                        if key in bone_info_dict and bone_info_dict[key]:
                            bonenode_xml.set(key, bone_info_dict[key])

    if exp_skel and not exp_mesh:
        # create dummy element for node data, if exporting bones but not exporting meshes
        obj_name = "skel_frame"
        IO_PDX_LOG.info("writing node - {0}".format(obj_name))
        objnode_xml = Xml.SubElement(object_xml, obj_name)

        blender_rigs = [obj for obj in bpy.data.objects if type(obj.data) == bpy.types.Armature]
        # optionally intersect with selection
        if exp_selected:
            blender_rigs = [obj for obj in blender_rigs if obj.select_get()]

        if len(blender_rigs) > 1:
            raise RuntimeError("Unable to resolve a single armature for export. {0}".format(blender_rigs))

        rig_bones = get_skeleton_hierarchy(blender_rigs[0])

        if len(rig_bones) == 0:
            raise RuntimeError("Skeleton only export is selected, but found no bones.")

        bone_info_list = get_bones_info(rig_bones)
        # create parent element for skeleton data
        if exp_skel and bone_info_list:
            IO_PDX_LOG.info("writing skeleton -")
            skeletonnode_xml = Xml.SubElement(objnode_xml, "skeleton")

            # create sub-elements for each bone, populate bone attributes
            for bone_info_dict in bone_info_list:
                bonenode_xml = Xml.SubElement(skeletonnode_xml, bone_info_dict["name"])
                for key in ["ix", "pa", "tx"]:
                    if key in bone_info_dict and bone_info_dict[key]:
                        bonenode_xml.set(key, bone_info_dict[key])

    # create root element for locators
    locator_xml = Xml.SubElement(root_xml, "locator")

    # populate locator data
    if exp_locs:
        blender_empties = [obj for obj in bpy.context.scene.objects if obj.data is None]
        # optionally intersect with selection
        if exp_selected:
            blender_empties = [obj for obj in blender_empties if obj.select_get()]

        loc_info_list = get_locators_info(blender_empties)
        IO_PDX_LOG.info("writing locators -")

        # create sub-elements for each locator, populate locator attributes
        for loc_info_dict in loc_info_list:
            locnode_xml = Xml.SubElement(locator_xml, loc_info_dict["name"])
            for key in ["p", "q", "pa", "tx"]:
                if key in loc_info_dict and loc_info_dict[key]:
                    locnode_xml.set(key, loc_info_dict[key])

    # write the binary file from our XML structure
    pdx_data.write_meshfile(meshpath, root_xml)

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    IO_PDX_LOG.info("export finished! ({0:.4f} sec)".format(time.time() - start))


def import_animfile(animpath, frame_start=1):
    start = time.time()
    IO_PDX_LOG.info("importing - {0}".format(animpath))

    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(animpath)

    # find animation info and samples
    info = asset_elem.find("info")
    samples = asset_elem.find("samples")
    framecount = info.attrib["sa"][0]

    # set scene animation and playback settings
    fps = int(info.attrib["fps"][0])
    IO_PDX_LOG.info("setting playback speed - {0}".format(fps))
    try:
        bpy.context.scene.render.fps = fps
    except Exception as err:
        IO_PDX_LOG.error(err)
        raise RuntimeError("Unsupported animation speed. {0}".format(fps))
    bpy.context.scene.render.fps_base = 1.0

    IO_PDX_LOG.info("setting playback range - ({0},{1})".format(frame_start, (frame_start + framecount - 1)))
    bpy.context.scene.frame_start = frame_start
    bpy.context.scene.frame_end = frame_start + framecount - 1
    bpy.context.scene.frame_set(frame_start)

    # find armature and bones being animated in the scene
    IO_PDX_LOG.info("finding armature and bones -")
    matching_rigs = [get_rig_from_bone_name(clean_imported_name(bone.tag)) for bone in info]
    matching_rigs = list(set(rig for rig in matching_rigs if rig))
    if len(matching_rigs) != 1:
        raise RuntimeError("Missing unique armature required for animation: {0}".format(matching_rigs))
    rig = matching_rigs[0]

    # clear any current pose before attempting to load the animation
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.pose.transforms_clear()
    bpy.ops.object.mode_set(mode="OBJECT")

    # check armature has all required bones
    bone_errors = []
    initial_pose = dict()
    for bone in info:
        pose_bone, edit_bone = None, None
        bone_name = clean_imported_name(bone.tag)
        try:
            pose_bone = rig.pose.bones[bone_name]
            edit_bone = pose_bone.bone  # rig.data.bones[bone_name]
        except KeyError:
            bone_errors.append(bone_name)
            IO_PDX_LOG.warning("failed to find bone - {0}".format(bone_name))

        # and set initial transform
        if pose_bone and edit_bone:
            pose_bone.rotation_mode = "QUATERNION"

            # compose transform parts
            _scale = Matrix.Scale(bone.attrib["s"][0], 4)
            _rotation = (
                Quaternion((bone.attrib["q"][3], bone.attrib["q"][0], bone.attrib["q"][1], bone.attrib["q"][2]))
                .to_matrix()
                .to_4x4()
            )
            _translation = Matrix.Translation(bone.attrib["t"])

            # this matrix describes the transform from parent bone in the initial starting pose
            offset_matrix = swap_coord_space(_translation @ _rotation @ _scale)
            # determine if we have a parent matrix
            parent_matrix = Matrix()
            if edit_bone.parent:
                parent_matrix = edit_bone.parent.matrix_local

            # apply transform and set initial pose keyframe (not all bones in this initial pose will be animated)
            pose_bone.matrix = (offset_matrix.transposed() @ parent_matrix.transposed()).transposed()
            pose_bone.keyframe_insert(data_path="scale", index=-1, group=bone_name)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", index=-1, group=bone_name)
            pose_bone.keyframe_insert(data_path="location", index=-1, group=bone_name)

            # record the initial pose as the basis for subsequent keyframes
            initial_pose[bone_name] = pose_bone.matrix

    # break on bone errors
    if bone_errors:
        raise RuntimeError("Missing bones required for animation: {0}".format(bone_errors))

    # check which transform types are animated on each bone
    all_bone_keyframes = OrderedDict()
    for bone in info:
        bone_name = clean_imported_name(bone.tag)
        key_data = dict()
        all_bone_keyframes[bone_name] = key_data

        for sample_type in bone.attrib["sa"][0]:
            key_data[sample_type] = []

    # then traverse the samples data to store keys per bone
    s_index, q_index, t_index = 0, 0, 0
    for _ in range(0, framecount):
        for bone_name in all_bone_keyframes:
            bone_key_data = all_bone_keyframes[bone_name]

            if "s" in bone_key_data:
                bone_key_data["s"].append(samples.attrib["s"][s_index : s_index + 1])
                s_index += 1
            if "q" in bone_key_data:
                bone_key_data["q"].append(samples.attrib["q"][q_index : q_index + 4])
                q_index += 4
            if "t" in bone_key_data:
                bone_key_data["t"].append(samples.attrib["t"][t_index : t_index + 3])
                t_index += 3

    for bone_name in all_bone_keyframes:
        bone_keys = all_bone_keyframes[bone_name]
        # check bone has keyframe values
        if bone_keys.values():
            IO_PDX_LOG.info("setting {0} keyframes on bone - {1}".format(list(bone_keys.keys()), bone_name))
            create_anim_keys(rig, bone_name, bone_keys, frame_start, initial_pose)

    bpy.context.scene.frame_set(frame_start)
    bpy.context.view_layer.update()

    bpy.ops.object.select_all(action="DESELECT")
    IO_PDX_LOG.info("import finished! ({0:.4f} sec)".format(time.time() - start))


def export_animfile(animpath, frame_start=1, frame_end=10):
    start = time.time()
    IO_PDX_LOG.info("exporting - {0}".format(animpath))

    curr_frame = bpy.context.scene.frame_start
    if frame_start != int(frame_start) or frame_end != int(frame_end):
        raise RuntimeError(
            "Invalid animation range selected ({0},{1}). Only whole frames are supported.".format(
                frame_start, frame_end
            )
        )
    frame_start = int(frame_start)
    frame_end = int(frame_end)

    # create an XML structure to store the object hierarchy
    root_xml = Xml.Element("File")
    root_xml.set("pdxasset", [1, 0])

    # create root element for animation info
    info_xml = Xml.SubElement(root_xml, "info")

    # fill in animation info and initial pose
    IO_PDX_LOG.info("writing animation info -")
    fps = bpy.context.scene.render.fps
    info_xml.set("fps", [float(fps)])

    frame_samples = (frame_end + 1) - frame_start
    info_xml.set("sa", [frame_samples])

    # find the scene armature with animation property (assume this is unique)
    rig = None

    # scene_rigs = [
    #     obj for obj in bpy.context.scene.objects if type(obj.data) == bpy.types.Armature
    # ]  # and hasattr(bone, PDX_ANIMATION) ?
    # TODO : finsh this, just use active object for now
    rig = bpy.context.active_object
    if rig is None:
        raise RuntimeError("Please select a specific armature before exporting.")

    # populate bone data, assume that the rig to be exported is selected
    export_bones = get_skeleton_hierarchy(rig)
    info_xml.set("j", [len(export_bones)])

    # parse the scene animation data
    all_bone_keyframes = get_scene_animdata(rig, export_bones, frame_start, frame_end)

    # for each bone, write sample types and describe the initial offset from parent
    IO_PDX_LOG.info("writing initial bone transforms -")
    bpy.context.scene.frame_set(frame_start)
    for bone in export_bones:
        pose_bone = rig.pose.bones[bone.name]
        bone_xml = Xml.SubElement(info_xml, pose_bone.name)

        # check sample types
        sample_types = ""
        for attr in ["t", "q", "s"]:
            if attr in all_bone_keyframes[pose_bone.name]:
                sample_types += attr
        bone_xml.set("sa", [sample_types])

        # determine if we have a parent matrix
        parent_matrix = Matrix()
        if pose_bone.parent:
            parent_matrix = pose_bone.parent.matrix.copy()

        # calculate the inital pose offset for this bone
        offset_matrix = parent_matrix.inverted_safe() @ pose_bone.matrix
        _translation, _rotation, _scale = swap_coord_space(offset_matrix).decompose()

        # convert quaternions from wxyz to xyzw
        _rotation = [list(_rotation)[1], list(_rotation)[2], list(_rotation)[3], list(_rotation)[0]]
        # animation supports uniform scale only
        _scale = [_scale[0]]

        # round to required precisions and set attribute
        bone_xml.set("t", util_round(_translation, PDX_ROUND_TRANS))
        bone_xml.set("q", util_round(_rotation, PDX_ROUND_ROT))
        bone_xml.set("s", util_round(_scale, PDX_ROUND_SCALE))

    # create root element for animation keyframe data
    samples_xml = Xml.SubElement(root_xml, "samples")
    IO_PDX_LOG.info("writing keyframes -")
    for bone_name in all_bone_keyframes:
        bone_keys = all_bone_keyframes[bone_name]
        if bone_keys:
            IO_PDX_LOG.info("writing {0} keyframes for bone - {1}".format(list(bone_keys.keys()), bone_name))

    # pack all scene animation data into flat keyframe lists
    t_packed, q_packed, s_packed = [], [], []
    for i in range(frame_samples):
        for bone in all_bone_keyframes:
            if "t" in all_bone_keyframes[bone]:
                t_packed.extend(all_bone_keyframes[bone]["t"].pop(0))
            if "q" in all_bone_keyframes[bone]:
                q_packed.extend(all_bone_keyframes[bone]["q"].pop(0))
            if "s" in all_bone_keyframes[bone]:
                s_packed.append(all_bone_keyframes[bone]["s"].pop(0)[0])  # support uniform scale only

    if t_packed:
        samples_xml.set("t", t_packed)
    if q_packed:
        samples_xml.set("q", q_packed)
    if s_packed:
        samples_xml.set("s", s_packed)

    # write the binary file from our XML structure
    pdx_data.write_animfile(animpath, root_xml)

    bpy.context.scene.frame_set(curr_frame)

    bpy.ops.object.select_all(action="DESELECT")
    IO_PDX_LOG.info("export finished! ({0:.4f} sec)".format(time.time() - start))
