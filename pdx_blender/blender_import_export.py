"""
    Paradox asset files, Blender import/export.

    As Blenders 3D space is (Z-up, right-handed) and the Clausewitz engine seems to be (Y-up, left-handed) we have to
    mirror all positions, normals etc along the Z axis, rotate about X and flip texture coordinates in V.
    
    author : ross-g
"""

import os
import time
from collections import OrderedDict
try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

import bpy
import bmesh
import math
from mathutils import Vector, Matrix, Quaternion

from .. import pdx_data


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

PDX_SHADER = 'shader'
PDX_ANIMATION = 'animation'
PDX_IGNOREJOINT = 'pdxIgnoreJoint'
PDX_MAXSKININFS = 4

PDX_DECIMALPTS = 5


""" ====================================================================================================================
    Helper functions.
========================================================================================================================
"""


def get_BMesh(mesh_data):
    """
        Returns a BMesh from existing mesh data
    """
    bm = bmesh.new()
    bm.from_mesh(mesh_data)

    return bm


def get_rig_from_bone_name(bone_name):
    scene_rigs = (obj for obj in bpy.data.objects if type(obj.data) == bpy.types.Armature)

    for rig in scene_rigs:
        armt = rig.data
        if bone_name in [b.name for b in armt.bones]:
            return rig


def clean_imported_name(name):
    # strip any namespace names, taking the final name only
    clean_name = name.split(':')[-1]

    # replace hierarchy separator character used by Maya in the case of non-unique leaf node names
    clean_name = clean_name.replace('|', '_')

    return clean_name


def set_local_axis_display(state, data_type):
    object_list = [obj for obj in bpy.data.objects if type(obj.data) == data_type]

    for node in object_list:
        try:
            node.show_axis = state
        except:
            print("[io_pdx_mesh] node '{}' could not have it's axis shown.".format(node.name))


def swap_coord_space(data):
    """
        Transforms from PDX space (-Z forward, Y up) to Blender space (Y forward, Z up)
    """
    space_matrix = Matrix((
        (1, 0, 0, 0),
        (0, 0, 1, 0),
        (0, 1, 0, 0),
        (0, 0, 0, 1)
    ))

    # vector
    if type(data) == Vector or len(data) == 3:
        vec = Vector(data)
        return vec * space_matrix
    # matrix
    elif type(data) == Matrix:
        return space_matrix * data * space_matrix.inverted()
    # quaternion
    elif type(data) == Quaternion:
        mat = data.to_matrix()
        return (space_matrix * mat.to_4x4() * space_matrix.inverted()).to_quaternion()
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


def create_datatexture(tex_filepath):
    texture_name = os.path.split(tex_filepath)[1]

    if texture_name in bpy.data.images:
        new_image = bpy.data.images[texture_name]
    else:
        new_image = bpy.data.images.load(tex_filepath)

    if texture_name in bpy.data.textures:
        new_texture = bpy.data.textures[texture_name]
    else:
        new_texture = bpy.data.textures.new(texture_name, type='IMAGE')
        new_texture.image = new_image

    new_image.use_fake_user = True
    new_texture.use_fake_user = True

    return new_texture


def create_material(PDX_material, mesh, texture_dir):
    mat_name = 'PDXphong_' + mesh.name
    new_material = bpy.data.materials.new(mat_name)
    new_material.diffuse_intensity = 1
    new_material.specular_shader = 'PHONG'

    new_material[PDX_SHADER] = PDX_material.shader[0]

    if getattr(PDX_material, 'diff', None):
        texture_path = os.path.join(texture_dir, PDX_material.diff[0])
        if os.path.exists(texture_path):
            new_file = create_datatexture(texture_path)
            diff_tex = new_material.texture_slots.add()
            diff_tex.texture = new_file
            diff_tex.texture_coords = 'UV'
            diff_tex.use_map_color_diffuse = True

    if getattr(PDX_material, 'n', None):
        texture_path = os.path.join(texture_dir, PDX_material.n[0])
        if os.path.exists(texture_path):
            new_file = create_datatexture(texture_path)
            norm_tex = new_material.texture_slots.add()
            norm_tex.texture = new_file
            norm_tex.texture_coords = 'UV'
            norm_tex.use_map_color_diffuse = False
            norm_tex.use_map_normal = True
            norm_tex.normal_map_space = 'TANGENT'

    if getattr(PDX_material, 'spec', None):
        texture_path = os.path.join(texture_dir, PDX_material.spec[0])
        if os.path.exists(texture_path):
            new_file = create_datatexture(texture_path)
            spec_tex = new_material.texture_slots.add()
            spec_tex.texture = new_file
            spec_tex.texture_coords = 'UV'
            spec_tex.use_map_color_diffuse = False
            spec_tex.use_map_color_spec = True

    mesh.materials.append(new_material)


def create_locator(PDX_locator, PDX_bone_dict):
    # create locator and link to the scene
    new_loc = bpy.data.objects.new(PDX_locator.name, None)
    new_loc.empty_draw_type = 'PLAIN_AXES'
    new_loc.empty_draw_size = 0.25
    new_loc.show_axis = False

    bpy.context.scene.objects.link(new_loc)

    # parent locator through a constraint
    parent = getattr(PDX_locator, 'pa', None)
    parent_Xform = Matrix()

    if parent is not None:
        rig = get_rig_from_bone_name(parent[0])
        if rig:
            parent_constraint = new_loc.constraints.new('CHILD_OF')
            parent_constraint.name = 'imported_constraint'
            parent_constraint.target = rig
            parent_constraint.subtarget = parent[0]

            bone_space = rig.matrix_world * rig.data.bones[parent[0]].matrix.to_4x4()
            parent_constraint.inverse_matrix = bone_space.inverted()
        else:
            # parent bone doesn't exist in scene, build its transform
            transform = PDX_bone_dict[parent[0]]
            # note we transpose the matrix on creation
            parent_Xform = Matrix((
                (transform[0], transform[3], transform[6], transform[9]),
                (transform[1], transform[4], transform[7], transform[10]),
                (transform[2], transform[5], transform[8], transform[11]),
                (0.0, 0.0, 0.0, 1.0)
            ))

    # set attributes
    new_loc.rotation_mode = 'XYZ'
    # rotation
    quat = Quaternion([PDX_locator.q[3], PDX_locator.q[0], PDX_locator.q[1], PDX_locator.q[2]])
    new_loc.rotation_euler = quat.to_euler()
    # translation
    new_loc.location = (PDX_locator.p[0], PDX_locator.p[1], PDX_locator.p[2])

    bpy.context.scene.update()

    # apply parent transform (must be multipled in transposed form, then re-transpoed before being applied)
    new_loc.matrix_world = (new_loc.matrix_world.transposed() * parent_Xform.inverted_safe().transposed()).transposed()

    # convert to Blender space
    new_loc.matrix_world = swap_coord_space(new_loc.matrix_world)


def create_skeleton(PDX_bone_list):
    # keep track of bones as we create them
    bone_list = [None for _ in range(0, len(PDX_bone_list))]

    # check this skeleton is not already built in the scene
    matching_rigs = [get_rig_from_bone_name(clean_imported_name(bone.name)) for bone in PDX_bone_list]
    matching_rigs = list(set(rig for rig in matching_rigs if rig))
    if len(matching_rigs) == 1:
        return matching_rigs[0]

    # temporary name used during creation
    tmp_rig_name = 'io_pdx_rig'

    # create the armature datablock
    armt = bpy.data.armatures.new('armature')
    armt.name = 'imported_armature'
    armt.draw_type = 'STICK'

    # create the object and link to the scene
    new_rig = bpy.data.objects.new(tmp_rig_name, armt)
    bpy.context.scene.objects.link(new_rig)
    bpy.context.scene.objects.active = new_rig
    new_rig.show_x_ray = True
    new_rig.select = True

    bpy.ops.object.mode_set(mode='EDIT')
    for bone in PDX_bone_list:
        index = bone.ix[0]
        transform = bone.tx
        parent = getattr(bone, 'pa', None)

        # determine unique bone name
        # Maya allows non-unique transform names (on leaf nodes) and handles it internally by using | separators
        unique_name = clean_imported_name(bone.name)

        # create joint
        new_bone = armt.edit_bones.new(name=unique_name)
        new_bone.select = True
        bone_list[index] = new_bone

        # connect to parent
        if parent is not None:
            parent_bone = bone_list[parent[0]]
            new_bone.parent = parent_bone
            new_bone.use_connect = False

        # set head transform
        mat = Matrix((
            (transform[0], transform[3], transform[6], transform[9]),
            (transform[1], transform[4], transform[7], transform[10]),
            (transform[2], transform[5], transform[8], transform[11]),
            (0.0, 0.0, 0.0, 1.0)
        ))
        # set matrix directly as this includes bone roll
        new_bone.matrix = swap_coord_space(mat.inverted_safe())                        # convert coords to Blender space

        # set tail transform (based on possible children)
        bone_children = [b for b in PDX_bone_list if getattr(b, 'pa', [None]) == bone.ix]
        if bone_children:
            # use the first childs position as the tail
            child_transform = bone_children[0].tx
            c_mat = Matrix((
                (child_transform[0], child_transform[3], child_transform[6], child_transform[9]),
                (child_transform[1], child_transform[4], child_transform[7], child_transform[10]),
                (child_transform[2], child_transform[5], child_transform[8], child_transform[11]),
                (0.0, 0.0, 0.0, 1.0)
            ))
            new_bone.tail = swap_coord_space(c_mat.inverted_safe().to_translation())   # convert coords to Blender space

        else:
            # leaf node bone, use an arbitrary extension of the parent bone vector (as zero length bones are culled)
            new_bone.tail = new_bone.head + (new_bone.parent.vector / new_bone.parent.length) * 0.1

    # set or correct some bone settings based on hierarchy
    for bone in bone_list:
        bone_parent = bone.parent
        if bone_parent:
            # Blender culls zero length bones, nudge the tail to ensure we don't create any
            if bone_parent.head == bone_parent.tail:
                bone_parent.tail += Vector((0, 0, 0.01))
                continue

            # set "use_connect" for bones whos parent has exactly 1 child bone (provided we didn't nudge their tail)
            if len(bone_parent.children) == 1:
                bone.use_connect = True

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.scene.update()

    return new_rig


def create_skin(PDX_skin, obj, rig, max_infs=None):
    if max_infs is None:
        max_infs = PDX_MAXSKININFS

    # create dictionary of skinning info per bone
    skin_dict = dict()

    num_infs = PDX_skin.bones[0]
    armt_bones = rig.data.bones

    for vtx in range(0, int(len(PDX_skin.ix)/max_infs)):
        skin_dict[vtx] = dict(joints=[], weights=[])

    # gather joint index and weighting that each vertex is skinned to
    for vtx, j in enumerate(range(0, len(PDX_skin.ix), max_infs)):
        skin_dict[vtx]['joints'] = PDX_skin.ix[j:j+num_infs]
        skin_dict[vtx]['weights'] = PDX_skin.w[j:j+num_infs]

    # create skin weight vertex groups
    for bone in armt_bones:
        obj.vertex_groups.new(bone.name)

    # set all skin weights
    for v in range(len(skin_dict.keys())):
        # FIXME: this will break if we have failed to create any bones (due to zero length etc)
        joints = [armt_bones[j].name for j in skin_dict[v]['joints']]
        weights = skin_dict[v]['weights']
        # normalise joint weights
        try:
            norm_weights = [float(w)/sum(weights) for w in weights]
        except:
            norm_weights = weights
        # strip zero weight entries
        joint_weights = [(j, w) for j, w in zip(joints, norm_weights) if w != 0.0]

        for joint, weight in joint_weights:
            obj.vertex_groups[joint].add([v], weight, 'REPLACE')

    # create an armature modifier for the mesh object
    skin_mod = obj.modifiers.new(rig.name + '_skin', 'ARMATURE')
    skin_mod.object = rig
    skin_mod.use_bone_envelopes = False
    skin_mod.use_vertex_groups = True


def create_mesh(PDX_mesh, name=None):
    # temporary name used during creation
    tmp_mesh_name = 'io_pdx_mesh'

    # vertices
    verts = PDX_mesh.p      # flat list of 3d co-ordinates, verts[:2] = vtx[0]

    # normals
    norms = None
    if hasattr(PDX_mesh, 'n'):
        norms = PDX_mesh.n      # flat list of vectors, norms[:2] = nrm[0]

    # triangles
    tris = PDX_mesh.tri     # flat list of vertex connections, tris[:3] = face[0]

    # UVs (channels 0 to 3)
    uv_Ch = dict()
    for i, uv in enumerate(['u0', 'u1', 'u2', 'u3']):
        if hasattr(PDX_mesh, uv):
            uv_Ch[i] = getattr(PDX_mesh, uv)    # flat list of 2d co-ordinates, u0[:1] = vtx[0]uv0

    # vertices
    vertexArray = []   # array of points
    for i in range(0, len(verts), 3):
        v = swap_coord_space([verts[i], verts[i+1], verts[i+2]])                       # convert coords to Blender space
        vertexArray.append(v)

    # faces
    faceArray = []
    for i in range(0, len(tris), 3):
        f = [tris[i+2], tris[i+1], tris[i]]                                        # convert handedness to Blender space
        faceArray.append(f)

    # create the mesh datablock
    new_mesh = bpy.data.meshes.new(tmp_mesh_name)

    # add mesh data
    new_mesh.from_pydata(vertexArray, [], faceArray)
    new_mesh.update()

    # create the object and link to the scene
    if name is None:
        name = tmp_mesh_name
    new_obj = bpy.data.objects.new(clean_imported_name(name), new_mesh)
    bpy.context.scene.objects.link(new_obj)
    new_mesh.name = name

    # apply the vertex normal data
    if norms:
        normals = []
        for i in range(0, len(norms), 3):
            n = swap_coord_space([norms[i], norms[i+1], norms[i+2]])                   # convert vector to Blender space
            normals.append(n)

        new_mesh.polygons.foreach_set('use_smooth', [True] * len(new_mesh.polygons))
        new_mesh.normals_split_custom_set_from_vertices(normals)
        new_mesh.use_auto_smooth = True
        new_mesh.free_normals_split()

    # apply the UV data channels
    for idx in uv_Ch:
        uvSetName = 'map' + str(idx+1)
        new_mesh.uv_textures.new(uvSetName)

        uvArray = []
        uv_data = uv_Ch[idx]
        for i in range(0, len(uv_data), 2):
            uv = [uv_data[i], 1 - uv_data[i+1]]     # flip the UV coords in V!
            uvArray.append(uv)

        bm = get_BMesh(new_mesh)
        uv_layer = bm.loops.layers.uv[uvSetName]

        for face in bm.faces:
            for loop in face.loops:
                i = loop.vert.index
                loop[uv_layer].uv = uvArray[i]

        bm.to_mesh(new_mesh)    # write the bmesh back to the mesh
        bm.free()

    # select the object
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.scene.objects.active = new_obj
    new_obj.select = True

    return new_mesh, new_obj


""" ====================================================================================================================
    Main IO functions.
========================================================================================================================
"""


def import_meshfile(meshpath, imp_mesh=True, imp_skel=True, imp_locs=True):
    start = time.time()
    print("[io_pdx_mesh] Importing {}".format(meshpath))

    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(meshpath)

    # find shapes and locators
    shapes = asset_elem.find('object')
    locators = asset_elem.find('locator')

    # store all bone transforms, irrespective of skin association
    scene_bone_dict = dict()

    # go through shapes
    for node in shapes:
        print("[io_pdx_mesh] creating node - {}".format(node.tag))

        # create the skeleton first, so we can skin the mesh to it
        rig = None
        skeleton = node.find('skeleton')
        if skeleton:
            pdx_bone_list = list()
            for b in skeleton:
                pdx_bone = pdx_data.PDXData(b)
                pdx_bone_list.append(pdx_bone)
                scene_bone_dict[pdx_bone.name] = pdx_bone.tx

            if imp_skel:
                print("[io_pdx_mesh] creating skeleton -")
                rig = create_skeleton(pdx_bone_list)

        # then create all the meshes
        meshes = node.findall('mesh')
        if imp_mesh and meshes:
            for m in meshes:
                print("[io_pdx_mesh] creating mesh -")
                pdx_mesh = pdx_data.PDXData(m)
                pdx_material = getattr(pdx_mesh, 'material', None)
                pdx_skin = getattr(pdx_mesh, 'skin', None)

                # create the geometry
                mesh, obj = create_mesh(pdx_mesh, name=node.tag)

                # create the material
                if pdx_material:
                    print("[io_pdx_mesh] creating material -")
                    create_material(pdx_material, mesh, os.path.split(meshpath)[0])

                # create the vertex group skin
                if rig and pdx_skin:
                    print("[io_pdx_mesh] creating skinning data -")
                    create_skin(pdx_skin, obj, rig)

    # go through locators
    if imp_locs and locators:
        print("[io_pdx_mesh] creating locators -")
        for loc in locators:
            pdx_locator = pdx_data.PDXData(loc)
            create_locator(pdx_locator, scene_bone_dict)

    print("[io_pdx_mesh] import finished! ({} sec)".format(time.time()-start))


def export_meshfile(meshpath, exp_mesh=True, exp_skel=True, exp_locs=True):
    start = time.time()
    print("[io_pdx_mesh] Exporting {}".format(meshpath))

    # create an XML structure to store the object hierarchy
    root_xml = Xml.Element('File')
    root_xml.set('pdxasset', [1, 0])

    # create root element for objects
    object_xml = Xml.SubElement(root_xml, 'object')

    # populate object data
    blender_meshes = [obj for obj in bpy.data.objects if type(obj.data) == bpy.types.Mesh]
    for shape in blender_meshes:
        print("[io_pdx_mesh] writing node - {}".format(shape.name))
        shapenode_xml = Xml.SubElement(object_xml, shape.name)

    # create root element for locators
    locator_xml = Xml.SubElement(root_xml, 'locator')
    blender_empties = [obj for obj in bpy.data.objects if obj.data is None]
    if exp_locs and blender_empties:
        for loc in blender_empties:
            # create sub-elements for each locator, populate locator attributes
            print("[io_pdx_mesh] writing locators -")
            locnode_xml = Xml.SubElement(locator_xml, loc.name)
            # TODO: if we export locators without exporting bones, then we should write translation differently if a locator is parented to a bone for example
            position = list(swap_coord_space(loc.location))
            rotation = list(swap_coord_space(loc.rotation_euler.to_quaternion()))
            locnode_xml.set('p', position)
            locnode_xml.set('q', [rotation[1], rotation[2], rotation[3], rotation[0]])
            # if loc.getParent():   # we create parent constraints rather than parent empties directly
            #     locnode_xml.set('pa', [loc.getParent().name()])

    # write the binary file from our XML structure
    pdx_data.write_meshfile(meshpath, root_xml)

    bpy.ops.object.select_all(action='DESELECT')
    print("[io_pdx_mesh] export finished! ({} sec)".format(time.time() - start))


def import_animfile(animpath, timestart=1.0):
    pass
