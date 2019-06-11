"""
    Paradox asset files, Maya import/export.

    As Mayas 3D space is (Y-up, right-handed) and the Clausewitz engine seems to be (Y-up, left-handed) we have to
    mirror all positions, normals etc about the XY plane and flip texture coordinates in V.

    author : ross-g
"""

import os
import time
from collections import OrderedDict, namedtuple, defaultdict

try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

import pymel.core as pmc
import pymel.core.datatypes as pmdt
import maya.OpenMaya as OpenMaya  # Maya Python API 1.0
import maya.OpenMayaAnim as OpenMayaAnim  # Maya Python API 1.0
from maya.api.OpenMaya import MVector, MMatrix, MTransformationMatrix, MQuaternion  # Maya Python API 2.0

from .. import pdx_data
from .. import IO_PDX_LOG


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

PDX_SHADER = 'shader'
PDX_ANIMATION = 'animation'
PDX_IGNOREJOINT = 'pdxIgnoreJoint'
PDX_MESHINDEX = 'meshindex'
PDX_MAXSKININFS = 4

PDX_DECIMALPTS = 5
PDX_ROUND_ROT = 4
PDX_ROUND_TRANS = 3
PDX_ROUND_SCALE = 2

# fmt: off
SPACE_MATRIX = MMatrix((
    (1, 0, 0, 0),
    (0, 1, 0, 0),
    (0, 0, -1, 0),
    (0, 0, 0, 1)
))
# fmt: on

# simple datatype for animation clips
AnimClip = namedtuple('AnimClip', ['name', 'start', 'end'])


""" ====================================================================================================================
    API functions.
========================================================================================================================
"""


def get_MObject(object_name):
    m_Obj = OpenMaya.MObject()

    m_SelList = OpenMaya.MSelectionList()
    m_SelList.add(object_name)
    m_SelList.getDependNode(0, m_Obj)

    return m_Obj


def get_MDagPath(object_name):
    m_DagPath = OpenMaya.MDagPath()

    m_SelList = OpenMaya.MSelectionList()
    m_SelList.add(object_name)
    m_SelList.getDagPath(0, m_DagPath)

    return m_DagPath


def get_plug(mobject, plug_name):
    mFn_DepNode = OpenMaya.MFnDependencyNode(mobject)
    mplug = mFn_DepNode.findPlug(plug_name)

    return mplug


def connect_nodeplugs(source_mobject, source_mplug, dest_mobject, dest_mplug):
    source_mplug = get_plug(source_mobject, source_mplug)
    dest_mplug = get_plug(dest_mobject, dest_mplug)

    m_DGMod = OpenMaya.MDGModifier()
    m_DGMod.connect(source_mplug, dest_mplug)
    m_DGMod.doIt()


""" ====================================================================================================================
    Helper functions.
========================================================================================================================
"""


def util_round(data, ndigits=0):
    """
        Element-wise rounding to a given precision in decimal digits. (reimplementing pmc.util.round for speed)
    """
    return tuple(round(x, ndigits) for x in data)


def clean_imported_name(name):
    # strip any namespace names, taking the final name only
    clean_name = name.split(':')[-1]

    # replace hierarchy separator character used by Maya in the case of non-unique leaf node names
    clean_name = clean_name.replace('|', '_')

    return clean_name


def list_scene_materials():
    return [mat for mat in pmc.ls(materials=True)]


def list_scene_rootbones():
    return list(set([bone.root() for bone in pmc.ls(type='joint')]))


def list_scene_pdx_meshes():
    return [mesh for mesh in pmc.ls(shapes=True) if type(mesh) == pmc.nt.Mesh and check_mesh_material(mesh)]


def set_local_axis_display(state, object_type=None, object_list=None):
    if object_list is None:
        if object_type is None:
            object_list = pmc.selected()
        else:
            object_list = pmc.ls(type=object_type)

    for node in object_list:
        if not hasattr(node, 'displayLocalAxis'):
            node = pmc.listRelatives(node, parent=True)[0]
        try:
            node.displayLocalAxis.set(state)
        except Exception:
            IO_PDX_LOG.info("node '{0}' has no displayLocalAxis property".format(node))


def set_ignore_joints(state):
    joint_list = pmc.selected(type='joint')

    for joint in joint_list:
        try:
            getattr(joint, PDX_IGNOREJOINT).set(state)
        except Exception:
            pmc.addAttr(joint, longName=PDX_IGNOREJOINT, attributeType='bool')
            getattr(joint, PDX_IGNOREJOINT).set(state)


def get_animation_clips(bone_list):
    anim_clips = []
    root_bone = get_skeleton_hierarchy(bone_list)[0]

    # parse the string attribute and produce a list of AnimClip tuples
    attr_string = None
    if hasattr(root_bone, PDX_ANIMATION):
        attr_string = getattr(root_bone, PDX_ANIMATION).get()

    if attr_string and attr_string != '':
        for clip_string in attr_string.split('@'):
            anim_clip = AnimClip(
                clip_string.split('~')[0], int(clip_string.split('~')[1]), int(clip_string.split('~')[2])
            )
            anim_clips.append(anim_clip)

        # sort clips by start frame
        anim_clips.sort(key=lambda clip: clip.start)

    return anim_clips


def set_animation_clips(bone_list, clips_list):
    root_bone = get_skeleton_hierarchy(bone_list)[0]

    # sort clips by start frame
    clips_list.sort(key=lambda clip: clip.start)

    # write the attribute string back to the root bone
    attr_string = '@'.join(['~'.join([str(getattr(clip, f)) for f in clip._fields]) for clip in clips_list])
    getattr(root_bone, PDX_ANIMATION).set(attr_string)


def edit_animation_clip(bone_list, anim_name, start, end):
    root_bone = get_skeleton_hierarchy(bone_list)[0]

    if not hasattr(root_bone, PDX_ANIMATION):
        # add the animation attribute, PDX tool uses ENUM attr and keyframes but we use a string and separators
        pmc.addAttr(root_bone, longName=PDX_ANIMATION, dataType='string')

    # get all existing animation clips
    anim_clips = get_animation_clips([root_bone])
    anim_clips_names = [clip.name for clip in anim_clips]

    new_clip = AnimClip(anim_name, start, end)

    # check if we're editing or adding a clip (names are unique)
    if new_clip.name in anim_clips_names:
        i = anim_clips_names.index(new_clip.name)
        anim_clips[i] = new_clip
    else:
        anim_clips.append(new_clip)

    set_animation_clips(bone_list, anim_clips)


def remove_animation_clip(bone_list, anim_name):
    # get all existing animation clips
    anim_clips = get_animation_clips(bone_list)
    anim_clips_names = [clip.name for clip in anim_clips]

    # find and remove the existing clip
    i = anim_clips_names.index(anim_name)
    anim_clips.pop(i)

    set_animation_clips(bone_list, anim_clips)


def set_mesh_index(maya_mesh, i):
    if not hasattr(maya_mesh, PDX_MESHINDEX):
        pmc.addAttr(maya_mesh, longName=PDX_MESHINDEX, attributeType='byte')

    getattr(maya_mesh, PDX_MESHINDEX).set(i)


def get_mesh_index(maya_mesh):
    if hasattr(maya_mesh, PDX_MESHINDEX):
        return getattr(maya_mesh, PDX_MESHINDEX).get()
    else:
        return 255


def check_mesh_material(maya_mesh):
    result = False

    shadingengines = list(set(pmc.listConnections(maya_mesh, type='shadingEngine')))
    for sg in shadingengines:
        material = pmc.listConnections(sg.surfaceShader)[0]
        result = result or hasattr(material, PDX_SHADER)  # needs at least one of it's materials to be a PDX material

    return result


def get_material_shader(maya_material):
    shader_attr = getattr(maya_material, PDX_SHADER)
    shader_val = shader_attr.get()

    # PDX source assets use an enum attr
    if shader_attr.type() == 'enum':
        _enum_dict = shader_attr.getEnums()
        return _enum_dict[shader_val]

    # imported assets will get a string attr
    elif shader_attr.type() == 'string':
        return shader_val


def get_material_textures(maya_material):
    texture_dict = dict()

    if maya_material.color.connections():
        texture_dict['diff'] = maya_material.color.connections()[0].fileTextureName.get()

    if maya_material.normalCamera.connections():
        bump2d = maya_material.normalCamera.connections()[0]
        texture_dict['n'] = bump2d.bumpValue.connections()[0].fileTextureName.get()

    if maya_material.specularColor.connections():
        texture_dict['spec'] = maya_material.specularColor.connections()[0].fileTextureName.get()

    return texture_dict


def get_mesh_info(maya_mesh, skip_merge_vertices=False, round_data=False):
    """
        Returns a dictionary of mesh information neccessary to the exporter.
        By default this merges vertices across triangles where normal and UV data is shared, otherwise each tri-vert is
        exported separately!
    """
    # get references to MeshFace and Mesh types
    if type(maya_mesh) == pmc.general.MeshFace:
        meshfaces = maya_mesh
        mesh = meshfaces.node()
    elif type(maya_mesh) == pmc.nt.Mesh:
        meshfaces = maya_mesh.faces
        mesh = maya_mesh
    else:
        raise RuntimeError("Unsupported mesh type encountered. {0}".format(type(maya_mesh)))

    # we will need to test vertices for equality based on their attributes
    # critically: whether per-face vertices (sharing an object-relative vert id) share normals and uvs
    UniqueVertex = namedtuple('UniqueVertex', ['id', 'p', 'n', 'uv'])

    # API mesh function set
    mesh_obj = get_MObject(mesh.name())
    mFn_Mesh = OpenMaya.MFnMesh(mesh_obj)

    # cache some mesh data
    vertices = mesh.getPoints(space='world')  # list of vertices positions
    normals = mesh.getNormals(space='world')  # list of vectors for each vertex per face
    triangles = mesh.getTriangles()
    uv_setnames = [uv_set for uv_set in mesh.getUVSetNames() if mFn_Mesh.numUVs(uv_set) > 0]
    uv_coords = {}
    for i, uv_set in enumerate(uv_setnames):
        _u, _v = mesh.getUVs(uvSet=uv_set)
        uv_coords[i] = zip(_u, _v)
    if uv_setnames:
        tangents = mesh.getTangents(space='world', uvSet=uv_setnames[0])

    # build a blank dictionary of mesh information for the exporter
    mesh_dict = {x: [] for x in ['p', 'n', 'ta', 'u0', 'u1', 'u2', 'u3', 'tri', 'min', 'max']}

    # collect all unique verts in the order that we process them
    unique_verts = []

    for face in meshfaces:
        face_vert_ids = face.getVertices()  # vertices making this face
        num_triangles = triangles[0][face.index()]  # number of triangles making this face

        # store data for each tri of each face
        for tri in xrange(0, num_triangles):
            tri_vert_ids = mesh.getPolygonTriangleVertices(face.index(), tri)  # vertices making this triangle

            dict_vert_idx = []

            # loop over tri verts
            for vert_id in tri_vert_ids:
                _local_id = face_vert_ids.index(vert_id)  # face relative vertex index

                # position
                _position = vertices[vert_id]
                _position = swap_coord_space(_position)  # convert to Game space
                if round_data:
                    _position = util_round(list(_position), PDX_DECIMALPTS)

                # normal
                vert_norm_id = face.normalIndex(_local_id)
                _normal = list(normals[vert_norm_id])
                _normal = swap_coord_space(_normal)  # convert to Game space
                if round_data:
                    _normal = util_round(list(_normal), PDX_DECIMALPTS)

                # uv
                _uv_coords = {}
                for i, uv_set in enumerate(uv_setnames):
                    try:
                        vert_uv_id = face.getUVIndex(_local_id, uv_set)
                        uv = uv_coords[i][vert_uv_id]
                        uv = swap_coord_space(uv)  # convert to Game space
                        if round_data:
                            uv = util_round(list(uv), PDX_DECIMALPTS)
                    # case where verts are unmapped, eg when two meshes are merged with different UV set counts
                    except RuntimeError:
                        uv = (0.0, 0.0)
                    _uv_coords[i] = uv

                # tangent (omitted if there were no UVs)
                if uv_setnames and tangents:
                    vert_tangent_id = mesh.getTangentId(face.index(), vert_id)
                    _tangent = list(tangents[vert_tangent_id])
                    _tangent = swap_coord_space(_tangent)  # convert to Game space
                    if round_data:
                        _tangent = util_round(list(_tangent), PDX_DECIMALPTS)

                # check if this tri vert is new and unique, or can just reference an existing vertex
                new_vert = UniqueVertex(vert_id, _position, _normal, _uv_coords)
                # test if we have already stored this vertex
                try:
                    # no data needs to be added to the dict, the tri can just reference an existing vertex
                    i = unique_verts.index(new_vert)
                except ValueError:
                    i = None
                if i is None or skip_merge_vertices:
                    # new unique vertex, collect it and add the vert data to the dict
                    unique_verts.append(new_vert)
                    mesh_dict['p'].extend(_position)
                    mesh_dict['n'].extend(_normal)
                    for i, uv_set in enumerate(uv_setnames):
                        mesh_dict['u' + str(i)].extend(_uv_coords[i])
                    if uv_setnames:
                        mesh_dict['ta'].extend(_tangent)
                        mesh_dict['ta'].append(1.0)
                    i = len(unique_verts) - 1  # the tri will reference the last added vertex

                # store the tri vert reference
                dict_vert_idx.append(i)

            # tri-faces
            mesh_dict['tri'].extend(
                [dict_vert_idx[0], dict_vert_idx[2], dict_vert_idx[1]]  # convert handedness to Game space
            )

    # calculate min and max bounds of mesh
    x_VtxPos = set([mesh_dict['p'][i] for i in xrange(0, len(mesh_dict['p']), 3)])
    y_VtxPos = set([mesh_dict['p'][i + 1] for i in xrange(0, len(mesh_dict['p']), 3)])
    z_VtxPos = set([mesh_dict['p'][i + 2] for i in xrange(0, len(mesh_dict['p']), 3)])
    mesh_dict['min'] = [min(x_VtxPos), min(y_VtxPos), min(z_VtxPos)]
    mesh_dict['max'] = [max(x_VtxPos), max(y_VtxPos), max(z_VtxPos)]

    # create an ordered list of vertex ids that we have gathered into the mesh dict
    vert_id_list = [vert.id for vert in unique_verts]

    return mesh_dict, vert_id_list


def get_mesh_skin_info(maya_mesh, vertex_ids=None):
    skinclusters = list(set(pmc.listConnections(maya_mesh, type='skinCluster')))
    if not skinclusters:
        return None

    # a mesh can only be connected to one skin cluster
    skin = skinclusters[0]

    # build a dictionary of skin information for the exporter
    skin_dict = {x: [] for x in ['bones', 'ix', 'w']}

    # set number of joint influences per vert
    skin_dict['bones'].append(skin.getMaximumInfluences())

    # find all bones in hierarchy
    skin_bones = skin.influenceObjects()
    all_bones = get_skeleton_hierarchy(skin_bones)

    # parse all verts in order if we didn't supply a subset of vert ids
    if vertex_ids is None:
        vertex_ids = range(len(maya_mesh.verts))

    # iterate over influences to find weights, per vertex
    vert_weights = {v: {} for v in vertex_ids}
    for bone in skin_bones:
        try:
            bone_index = all_bones.index(bone)
        except ValueError:
            raise RuntimeError(
                "A skinned bone ({0}) is being excluded from export, check all bones using the '{1}' property.".format(
                    bone, PDX_IGNOREJOINT
                )
            )

        # do not use skin.indexForInfluenceObject (bones can be plugged into the cluster but are not influence objects)
        inf_index = skin_bones.index(bone)

        for vert_id, weight in enumerate(skin.getWeights(maya_mesh, influenceIndex=inf_index)):
            # check we actually want this vertex (in case of material split meshes)
            if vert_id in vertex_ids:
                # store any non-zero weights, by influence, per vertex
                if weight != 0.0:
                    vert_weights[vert_id][bone_index] = weight

    # collect data from the weights dict into the skin dict
    for vtx in vertex_ids:
        for influence, weight in vert_weights[vtx].iteritems():
            skin_dict['ix'].append(influence)
            skin_dict['w'].append(weight)
        if len(vert_weights[vtx]) < PDX_MAXSKININFS:
            # pad out with null data to fill container
            padding = PDX_MAXSKININFS - len(vert_weights[vtx])
            skin_dict['ix'].extend([-1] * padding)
            skin_dict['w'].extend([0.0] * padding)

    return skin_dict


def get_mesh_skeleton_info(maya_mesh):
    skinclusters = list(set(pmc.listConnections(maya_mesh, type='skinCluster')))
    if not skinclusters:
        return []

    # a mesh can only be connected to one skin cluster
    skin = skinclusters[0]

    # find all bones in hierarchy to be exported
    all_bones = get_skeleton_hierarchy(skin.influenceObjects())

    # build a list of bone information dictionaries for the exporter
    bone_list = [{'name': x.name()} for x in all_bones]
    for i, bone in enumerate(all_bones):
        # bone index
        bone_list[i]['ix'] = [i]

        # bone parent index
        if bone.getParent():
            bone_list[i]['pa'] = [all_bones.index(bone.getParent())]

        # bone inverse world-space transform
        mat = list(swap_coord_space(bone.getMatrix(worldSpace=True)).inverse())
        bone_list[i]['tx'] = []
        bone_list[i]['tx'].extend(mat[0:3])
        bone_list[i]['tx'].extend(mat[4:7])
        bone_list[i]['tx'].extend(mat[8:11])
        bone_list[i]['tx'].extend(mat[12:15])

    return bone_list


def get_skeleton_hierarchy(bone_list):
    root_bone = set()

    for bone in bone_list:
        root_bone.add(bone.root())

    if len(root_bone) != 1:
        raise RuntimeError("Unable to resolve a single root bone for the skeleton. {0}".format(list(root_bone)))

    root_bone = list(root_bone)[0]

    def get_recursive_children(bone, hierarchy):
        hierarchy.append(bone)
        children = [
            jnt
            for jnt in pmc.listRelatives(bone, children=True, type='joint')
            if not (hasattr(jnt, PDX_IGNOREJOINT) and getattr(jnt, PDX_IGNOREJOINT).get())
        ]

        for bone in children:
            get_recursive_children(bone, hierarchy)

        return hierarchy

    valid_bones = []
    get_recursive_children(root_bone, valid_bones)

    return valid_bones


def get_animation_fps():
    time_unit = pmc.currentUnit(query=True, time=True)

    if time_unit == 'game':
        return 15
    elif time_unit == 'ntsc':
        return 30
    else:
        raise RuntimeError("Unsupported animation speed. {0}".format(time_unit))


def get_scene_animdata(export_bones, startframe, endframe, round_data=True):
    # store transform for each bone over the frame range
    frames_data = defaultdict(list)

    for f in range(startframe, endframe + 1):
        pmc.currentTime(f, edit=True)
        for bone in export_bones:
            # convert to Game space
            _translation = swap_coord_space(bone.getTranslation())
            # bone rotation must be pre-multiplied by joint orientation
            _rotation = swap_coord_space(bone.getRotation(quaternion=True) * bone.getOrientation())
            _scale = bone.getScale()

            frames_data[bone.name()].append((_translation, _rotation, _scale))

    # create an ordered dictionary of all animated bones to store sample data
    all_bone_keyframes = OrderedDict()
    for bone in export_bones:
        all_bone_keyframes[bone.name()] = dict()

    # determine if any transform attributes were animated over this frame range for each bone
    for bone in export_bones:
        # convert data from list of tuples [(t,q,s)] to three nested lists [t][q][s]
        t_list, q_list, s_list = zip(*frames_data[bone.name()])

        if round_data:
            t_list = [util_round(list(t), PDX_ROUND_TRANS) for t in t_list]
            q_list = [util_round(list(q), PDX_ROUND_ROT) for q in q_list]
            s_list = [util_round(list(s), PDX_ROUND_SCALE) for s in s_list]

        # store any animated transform samples per attribute
        for attr, attr_list in zip(['t', 'q', 's'], [t_list, q_list, s_list]):
            if len(set(attr_list)) != 1:
                all_bone_keyframes[bone.name()][attr] = attr_list

    return all_bone_keyframes


def swap_coord_space(data):
    """
        Transforms from PDX space (-Z forward, Y up) to Maya space (Z forward, Y up)
    """
    global SPACE_MATRIX

    # matrix
    if type(data) == MMatrix or type(data) == pmdt.Matrix:
        mat = MMatrix(data)
        return SPACE_MATRIX * mat * SPACE_MATRIX.inverse()
    # quaternion
    elif type(data) == MQuaternion or type(data) == pmdt.Quaternion:
        mat = MMatrix(data.asMatrix())
        return MTransformationMatrix(SPACE_MATRIX * mat * SPACE_MATRIX.inverse()).rotation(asQuaternion=True)
    # vector
    elif type(data) == MVector or type(data) == pmdt.Vector or len(data) == 3:
        vec = MVector(data)
        return vec * SPACE_MATRIX
    # uv coordinate
    elif len(data) == 2:
        return data[0], 1 - data[1]
    # unknown
    else:
        raise NotImplementedError("Unknown data type encountered.")


""" ====================================================================================================================
    Creation functions.
========================================================================================================================
"""


def create_filetexture(tex_filepath):
    """
        Creates & connects up a new file node and place2dTexture node, uses the supplied filepath.
    """
    newFile = pmc.shadingNode('file', asTexture=True)
    new2dTex = pmc.shadingNode('place2dTexture', asUtility=True)

    pmc.connectAttr(new2dTex.coverage, newFile.coverage)
    pmc.connectAttr(new2dTex.translateFrame, newFile.translateFrame)
    pmc.connectAttr(new2dTex.rotateFrame, newFile.rotateFrame)
    pmc.connectAttr(new2dTex.mirrorU, newFile.mirrorU)
    pmc.connectAttr(new2dTex.mirrorV, newFile.mirrorV)
    pmc.connectAttr(new2dTex.stagger, newFile.stagger)
    pmc.connectAttr(new2dTex.wrapU, newFile.wrapU)
    pmc.connectAttr(new2dTex.wrapV, newFile.wrapV)
    pmc.connectAttr(new2dTex.repeatUV, newFile.repeatUV)
    pmc.connectAttr(new2dTex.offset, newFile.offset)
    pmc.connectAttr(new2dTex.rotateUV, newFile.rotateUV)
    pmc.connectAttr(new2dTex.noiseUV, newFile.noiseUV)
    pmc.connectAttr(new2dTex.vertexUvOne, newFile.vertexUvOne)
    pmc.connectAttr(new2dTex.vertexUvTwo, newFile.vertexUvTwo)
    pmc.connectAttr(new2dTex.vertexUvThree, newFile.vertexUvThree)
    pmc.connectAttr(new2dTex.vertexCameraOne, newFile.vertexCameraOne)
    pmc.connectAttr(new2dTex.outUV, newFile.uv)
    pmc.connectAttr(new2dTex.outUvFilterSize, newFile.uvFilterSize)
    newFile.fileTextureName.set(tex_filepath)

    return newFile, new2dTex


def create_shader(PDX_material, shader_name, texture_dir):
    new_shader = pmc.shadingNode('phong', asShader=True, name=shader_name)
    new_shadinggroup = pmc.sets(renderable=True, noSurfaceShader=True, empty=True, name='{0}_SG'.format(shader_name))
    pmc.connectAttr(new_shader.outColor, new_shadinggroup.surfaceShader)

    # add the game shader attribute, PDX tool uses ENUM attr to store but writes as a string
    pmc.addAttr(new_shader, longName=PDX_SHADER, dataType='string')
    getattr(new_shader, PDX_SHADER).set(PDX_material.shader[0])

    if getattr(PDX_material, 'diff', None):
        texture_path = os.path.join(texture_dir, PDX_material.diff[0])
        new_file, _ = create_filetexture(texture_path)
        pmc.connectAttr(new_file.outColor, new_shader.color)
        if new_file.fileHasAlpha.get():
            pmc.connectAttr(new_file.outTransparency, new_shader.transparency)

    if getattr(PDX_material, 'n', None):
        texture_path = os.path.join(texture_dir, PDX_material.n[0])
        new_file, _ = create_filetexture(texture_path)
        bump2d = pmc.shadingNode('bump2d', asUtility=True)
        bump2d.bumpDepth.set(0.1)
        new_file.alphaIsLuminance.set(True)
        pmc.connectAttr(new_file.outAlpha, bump2d.bumpValue)
        pmc.connectAttr(bump2d.outNormal, new_shader.normalCamera)

    if getattr(PDX_material, 'spec', None):
        texture_path = os.path.join(texture_dir, PDX_material.spec[0])
        new_file, _ = create_filetexture(texture_path)
        pmc.connectAttr(new_file.outColor, new_shader.specularColor)

    return new_shader, new_shadinggroup


def create_material(PDX_material, mesh, texture_path):
    shader_name = 'PDXphong_' + mesh.name()
    shader, s_group = create_shader(PDX_material, shader_name, texture_path)

    pmc.select(mesh)
    mesh.backfaceCulling.set(1)
    pmc.hyperShade(assign=s_group)


def create_locator(PDX_locator, PDX_bone_dict):
    """
        Creates a Maya Locator object.

    :param pdx_data.PDXData PDX_locator:
    :param dict PDX_bone_dict:
    """
    # create locator
    new_loc = pmc.spaceLocator()
    pmc.select(new_loc)
    pmc.rename(new_loc, PDX_locator.name)

    # parent locator to scene bone, or apply parents transform
    parent = getattr(PDX_locator, 'pa', None)
    parent_Xform = pmdt.Matrix()

    if parent is not None:
        parent_bone = pmc.ls(parent[0], type='joint')
        if parent_bone:
            pmc.parent(new_loc, parent_bone[0])
        else:
            # parent bone doesn't exist in scene, build its transform
            if parent[0] in PDX_bone_dict:
                transform = PDX_bone_dict[parent[0]]
                # fmt: off
                parent_Xform = pmdt.Matrix(
                    transform[0], transform[1], transform[2], 0.0,
                    transform[3], transform[4], transform[5], 0.0,
                    transform[6], transform[7], transform[8], 0.0,
                    transform[9], transform[10], transform[11], 1.0
                )
                # fmt: on
            else:
                IO_PDX_LOG.info(
                    "ERROR! unable to create locator '{0}' (missing parent '{1}' in file data)".format(
                        PDX_locator.name, parent[0]
                    )
                )
                pmc.delete(new_loc)
                return

    # set attributes
    loc_obj = get_MObject(new_loc.name())
    mFn_Xform = OpenMaya.MFnTransform(loc_obj)

    # rotation
    mFn_Xform.setRotationQuaternion(PDX_locator.q[0], PDX_locator.q[1], PDX_locator.q[2], PDX_locator.q[3])
    # translation
    vector = OpenMaya.MVector(PDX_locator.p[0], PDX_locator.p[1], PDX_locator.p[2])
    space = OpenMaya.MSpace.kTransform
    mFn_Xform.setTranslation(vector, space)

    # apply parent transform
    new_loc.setMatrix(new_loc.getMatrix() * parent_Xform.inverse())

    # convert to Maya space
    new_loc.setMatrix(swap_coord_space(new_loc.getMatrix()))


def create_skeleton(PDX_bone_list):
    # keep track of bones as we create them
    bone_list = [None for _ in range(0, len(PDX_bone_list))]

    pmc.select(clear=True)
    for bone in PDX_bone_list:
        index = bone.ix[0]
        transform = bone.tx
        parent = getattr(bone, 'pa', None)

        # determine unique bone name
        # Maya allows non-unique transform names (on leaf nodes) and handles it internally by using | separators
        unique_name = clean_imported_name(bone.name)

        # check if bone already exists, possible the skeleton is already built so collect and return joints
        existing_bone = pmc.ls(unique_name, type='joint')
        if len(existing_bone) == 1:
            bone_list[index] = pmc.PyNode(existing_bone[0])
            continue

        # create joint
        new_bone = pmc.joint()
        pmc.select(new_bone)
        pmc.rename(new_bone, unique_name)
        pmc.parent(new_bone, world=True)
        bone_list[index] = new_bone

        # set transform
        # fmt: off
        mat = pmdt.Matrix(
            transform[0], transform[1], transform[2], 0.0,
            transform[3], transform[4], transform[5], 0.0,
            transform[6], transform[7], transform[8], 0.0,
            transform[9], transform[10], transform[11], 1.0
        )
        # fmt: on
        # convert to Maya space
        new_bone.setMatrix(swap_coord_space(mat.inverse()), worldSpace=True)  # set to matrix inverse in world-space
        pmc.select(clear=True)

        # connect to parent
        if parent is not None:
            parent_bone = bone_list[parent[0]]
            pmc.connectJoint(new_bone, parent_bone, parentMode=True)

    for joint in bone_list:
        joint.radius.set(0.3)
        joint.segmentScaleCompensate.set(False)

    return bone_list


def create_skin(PDX_skin, mesh, skeleton, max_infs=None):
    if max_infs is None:
        max_infs = PDX_MAXSKININFS

    # create dictionary of skinning info per vertex
    skin_dict = dict()

    num_infs = PDX_skin.bones[0]
    for vtx in xrange(0, len(PDX_skin.ix) / max_infs):
        skin_dict[vtx] = dict(joints=[], weights=[])

    # gather joint index and weighting that each vertex is skinned to
    for vtx, j in enumerate(xrange(0, len(PDX_skin.ix), max_infs)):
        skin_dict[vtx]['joints'] = PDX_skin.ix[j : j + num_infs]
        skin_dict[vtx]['weights'] = PDX_skin.w[j : j + num_infs]

    # select mesh and joints
    pmc.select(skeleton, mesh)

    # create skin cluster and then prune all default skin weights
    skin_cluster = pmc.skinCluster(
        bindMethod=0, skinMethod=0, normalizeWeights=0, maximumInfluences=num_infs, obeyMaxInfluences=True
    )
    pmc.skinPercent(skin_cluster, mesh, normalize=False, pruneWeights=100)

    # API skin cluster function set
    skin_obj = get_MObject(skin_cluster.name())
    mFn_SkinCluster = OpenMayaAnim.MFnSkinCluster(skin_obj)

    mesh_dag = get_MDagPath(mesh.name())

    indices = OpenMaya.MIntArray()
    for vtx in xrange(len(skin_dict.keys())):
        indices.append(vtx)
    mFn_SingleIdxCo = OpenMaya.MFnSingleIndexedComponent()
    vertex_IdxCo = mFn_SingleIdxCo.create(OpenMaya.MFn.kMeshVertComponent)
    mFn_SingleIdxCo.addElements(indices)  # must only add indices after running create()

    infs = OpenMaya.MIntArray()
    for j in xrange(len(skeleton)):
        infs.append(j)

    weights = OpenMaya.MDoubleArray()
    for vtx in xrange(len(skin_dict.keys())):
        jts = skin_dict[vtx]['joints']
        wts = skin_dict[vtx]['weights']
        for j in xrange(len(skeleton)):
            if j in jts:
                weights.append(wts[jts.index(j)])
            else:
                weights.append(0.0)

    # set skin weights
    mFn_SkinCluster.setWeights(mesh_dag, vertex_IdxCo, infs, weights)

    # turn on skin weights normalization again
    pmc.setAttr('{0}.normalizeWeights'.format(skin_cluster), True)


def create_mesh(PDX_mesh, name=None):
    """
        Creates a Maya mesh objet
    :rtype: pmc.nt.Mesh
    """
    # temporary name used during creation
    tmp_mesh_name = 'io_pdx_mesh'

    # vertices
    verts = PDX_mesh.p  # flat list of 3d co-ordinates, verts[:2] = vtx[0]

    # normals
    norms = None
    if hasattr(PDX_mesh, 'n'):
        norms = PDX_mesh.n  # flat list of vectors, norms[:2] = nrm[0]

    # triangles
    tris = PDX_mesh.tri  # flat list of vertex connections, tris[:3] = face[0]

    # UVs (channels 0 to 3)
    uv_Ch = dict()
    for i, uv in enumerate(['u0', 'u1', 'u2', 'u3']):
        if hasattr(PDX_mesh, uv):
            uv_Ch[i] = getattr(PDX_mesh, uv)  # flat list of 2d co-ordinates, u0[:1] = vtx[0]uv0

    # build the following arguments for the MFnMesh.create() function
    # numVertices, numPolygons, vertexArray, polygonCounts, polygonConnects, uArray, vArray, new_transform

    # vertices
    numVertices = 0
    vertexArray = OpenMaya.MFloatPointArray()  # array of points
    for i in xrange(0, len(verts), 3):
        _verts = swap_coord_space([verts[i], verts[i + 1], verts[i + 2]])  # convert coords to Maya space
        v = OpenMaya.MFloatPoint(_verts[0], _verts[1], _verts[2])
        vertexArray.append(v)
        numVertices += 1

    # faces
    numPolygons = len(tris) / 3
    polygonCounts = OpenMaya.MIntArray()  # count of vertices per poly
    for i in range(0, numPolygons):
        polygonCounts.append(3)

    # vert connections
    polygonConnects = OpenMaya.MIntArray()
    for i in range(0, len(tris), 3):
        polygonConnects.append(tris[i + 2])  # convert handedness to Maya space
        polygonConnects.append(tris[i + 1])
        polygonConnects.append(tris[i])

    # default UVs
    uArray = OpenMaya.MFloatArray()
    vArray = OpenMaya.MFloatArray()
    if uv_Ch.get(0):
        uv_data = uv_Ch[0]
        for i in xrange(0, len(uv_data), 2):
            uArray.append(uv_data[i])
            vArray.append(1 - uv_data[i + 1])  # flip the UV coords in V!

    """ ================================================================================================================
        Create the new mesh """

    # create the data structures for mesh and transform
    mFn_Mesh = OpenMaya.MFnMesh()
    m_DagMod = OpenMaya.MDagModifier()
    new_transform = m_DagMod.createNode('transform')

    mFn_Mesh.create(
        numVertices, numPolygons, vertexArray, polygonCounts, polygonConnects, uArray, vArray, new_transform
    )

    # set up the transform parent to the new mesh (linking it to the scene)
    m_DagMod.doIt()

    # PyNode for the mesh
    mFn_Mesh.setName(tmp_mesh_name)
    new_mesh = pmc.PyNode(tmp_mesh_name)

    # name and namespace
    if name is not None:
        mesh_name = clean_imported_name(name)
        # set shape name
        pmc.rename(new_mesh, mesh_name)
        # set transform name
        mFn_Transform = OpenMaya.MFnTransform(new_transform)
        mFn_Transform.setName(mesh_name.replace('Shape', ''))

    # apply the vertex normal data
    if norms:
        normalsIn = OpenMaya.MVectorArray()  # array of vectors
        for i in xrange(0, len(norms), 3):
            _norms = swap_coord_space([norms[i], norms[i + 1], norms[i + 2]])  # convert vector to Maya space
            n = OpenMaya.MVector(_norms[0], _norms[1], _norms[2])
            normalsIn.append(n)
        vertexList = OpenMaya.MIntArray()  # matches normal to vert by index
        for i in range(0, numVertices):
            vertexList.append(i)
        mFn_Mesh.setVertexNormals(normalsIn, vertexList)

    # apply the UV data channels
    uvCounts = OpenMaya.MIntArray()
    for i in range(0, numPolygons):
        uvCounts.append(3)
    uvIds = OpenMaya.MIntArray()
    for i in range(0, len(tris), 3):
        uvIds.append(tris[i + 2])  # convert handedness to Maya space
        uvIds.append(tris[i + 1])
        uvIds.append(tris[i])

    # note we don't call setUVs before assignUVs for the default UV set, this was done during creation!
    if uv_Ch.get(0):
        mFn_Mesh.assignUVs(uvCounts, uvIds, 'map1')

    # set other UV channels
    for idx in uv_Ch:
        # ignore Ch 0 as we have already set this
        if idx != 0:
            uv_data = uv_Ch[idx]
            uvSetName = 'map' + str(idx + 1)

            uArray = OpenMaya.MFloatArray()
            vArray = OpenMaya.MFloatArray()
            for i in xrange(0, len(uv_data), 2):
                uArray.append(uv_data[i])
                vArray.append(1 - uv_data[i + 1])  # flip the UV coords in V!

            mFn_Mesh.createUVSetWithName(uvSetName)
            mFn_Mesh.setUVs(uArray, vArray, uvSetName)
            mFn_Mesh.assignUVs(uvCounts, uvIds, uvSetName)

    mFn_Mesh.updateSurface()

    # assign the default material
    pmc.select(new_mesh)
    shd_group = pmc.PyNode('initialShadingGroup')
    pmc.hyperShade(assign=shd_group)

    return new_mesh


def create_animcurve(joint, attr):
    mFn_AnimCurve = OpenMayaAnim.MFnAnimCurve()

    # use the attribute on the joint to determine which type of anim curve to create
    in_plug = get_plug(joint, attr)
    plug_type = mFn_AnimCurve.timedAnimCurveTypeForPlug(in_plug)

    # create the curve and get its output attribute
    anim_curve = mFn_AnimCurve.create(plug_type)
    mFn_AnimCurve.setName('{0}_{1}'.format(OpenMaya.MFnDependencyNode(joint).name(), attr))

    # check for and remove any existing animation curve
    if in_plug.isConnected():
        mplugs = OpenMaya.MPlugArray()
        in_plug.connectedTo(mplugs, True, False)
        for i in range(0, mplugs.length()):
            m_DGMod = OpenMaya.MDGModifier()
            m_DGMod.deleteNode(mplugs[i].node())
    # check for and return any existing animation curve
    # if in_plug.isConnected():
    #     mplugs = OpenMaya.MPlugArray()
    #     in_plug.connectedTo(mplugs, True, False)
    #     for i in range(0, mplugs.length()):
    #         mObj = mplugs[i].node()
    #         if mObj.hasFn(OpenMaya.MFn.kAnimCurve):
    #             return None, OpenMayaAnim.MFnAnimCurve(mObj)

    # connect the new animation curve to the attribute on the joint
    connect_nodeplugs(anim_curve, 'output', joint, attr)

    return anim_curve, mFn_AnimCurve


def create_anim_keys(joint_name, key_dict, timestart):
    jnt_obj = get_MObject(joint_name)

    # calculate start and end frames
    timestart = int(timestart)
    timeend = timestart + len(max(key_dict.values(), key=len))

    # create a time array
    time_array = OpenMaya.MTimeArray()
    for t in xrange(timestart, timeend):
        time_array.append(OpenMaya.MTime(t, OpenMaya.MTime.uiUnit()))

    # define anim curve tangent
    k_Tangent = OpenMayaAnim.MFnAnimCurve.kTangentLinear

    if 's' in key_dict:  # scale data
        animated_attrs = dict(scaleX=None, scaleY=None, scaleZ=None)

        for attrib in animated_attrs:
            # create the curve and API function set
            anim_curve, mFn_AnimCurve = create_animcurve(jnt_obj, attrib)
            animated_attrs[attrib] = mFn_AnimCurve

        # create data arrays per animating attribute
        x_scale_data = OpenMaya.MDoubleArray()
        y_scale_data = OpenMaya.MDoubleArray()
        z_scale_data = OpenMaya.MDoubleArray()

        for scale_data in key_dict['s']:
            # convert to Game space
            x_scale_data.append(scale_data[0])
            y_scale_data.append(scale_data[0])
            z_scale_data.append(scale_data[0])

        # add keys to the new curves
        for attrib, data_array in zip(animated_attrs, [x_scale_data, y_scale_data, z_scale_data]):
            mFn_AnimCurve = animated_attrs[attrib]
            mFn_AnimCurve.addKeys(time_array, data_array, k_Tangent, k_Tangent)

    if 'q' in key_dict:  # quaternion data
        animated_attrs = dict(rotateX=None, rotateY=None, rotateZ=None)

        for attrib in animated_attrs:
            # create the curve and API function set
            anim_curve, mFn_AnimCurve = create_animcurve(jnt_obj, attrib)
            animated_attrs[attrib] = mFn_AnimCurve

        # create data arrays per animating attribute
        x_rot_data = OpenMaya.MDoubleArray()
        y_rot_data = OpenMaya.MDoubleArray()
        z_rot_data = OpenMaya.MDoubleArray()

        for quat_data in key_dict['q']:
            # convert to Game space
            q = swap_coord_space(MQuaternion(*quat_data))
            # convert from quaternion to euler, this gives values in radians (which Maya uses internally)
            euler_data = q.asEulerRotation()
            x_rot_data.append(euler_data.x)
            y_rot_data.append(euler_data.y)
            z_rot_data.append(euler_data.z)

        # add keys to the new curves
        for attrib, data_array in zip(animated_attrs, [x_rot_data, y_rot_data, z_rot_data]):
            mFn_AnimCurve = animated_attrs[attrib]
            mFn_AnimCurve.addKeys(time_array, data_array, k_Tangent, k_Tangent)

    if 't' in key_dict:  # translation data
        animated_attrs = dict(translateX=None, translateY=None, translateZ=None)

        for attrib in animated_attrs:
            # create the curve and API function set
            anim_curve, mFn_AnimCurve = create_animcurve(jnt_obj, attrib)
            animated_attrs[attrib] = mFn_AnimCurve

        # create data arrays per animating attribute
        x_trans_data = OpenMaya.MDoubleArray()
        y_trans_data = OpenMaya.MDoubleArray()
        z_trans_data = OpenMaya.MDoubleArray()

        for trans_data in key_dict['t']:
            # convert to Game space
            t = swap_coord_space(MVector(*trans_data))
            x_trans_data.append(t[0])
            y_trans_data.append(t[1])
            z_trans_data.append(t[2])

        # add keys to the new curves
        for attrib, data_array in zip(animated_attrs, [x_trans_data, y_trans_data, z_trans_data]):
            mFn_AnimCurve = animated_attrs[attrib]
            mFn_AnimCurve.addKeys(time_array, data_array, k_Tangent, k_Tangent)


""" ====================================================================================================================
    Main IO functions.
========================================================================================================================
"""


def import_meshfile(meshpath, imp_mesh=True, imp_skel=True, imp_locs=True, progress_fn=None):
    start = time.time()
    IO_PDX_LOG.info("importing {0}".format(meshpath))

    progress = None
    if progress_fn:
        progress = progress_fn('Importing', 10)

    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(meshpath)

    # find shapes and locators
    shapes = asset_elem.find('object')
    locators = asset_elem.find('locator')

    # store all bone transforms, irrespective of skin association
    complete_bone_dict = dict()

    # go through shapes
    for i, node in enumerate(shapes):
        IO_PDX_LOG.info("creating node - {0}".format(node.tag))
        if progress_fn:
            progress.update(1, 'creating node')

        # create the skeleton first, so we can skin the mesh to it
        joints = None
        skeleton = node.find('skeleton')
        if skeleton:
            pdx_bone_list = list()
            for b in skeleton:
                pdx_bone = pdx_data.PDXData(b)
                pdx_bone_list.append(pdx_bone)
                complete_bone_dict[pdx_bone.name] = pdx_bone.tx

            if imp_skel:
                IO_PDX_LOG.info("creating skeleton -")
                if progress_fn:
                    progress.update(1, 'creating skeleton')
                joints = create_skeleton(pdx_bone_list)

        # then create all the meshes
        meshes = node.findall('mesh')
        if imp_mesh and meshes:
            for m in meshes:
                IO_PDX_LOG.info("creating mesh -")
                if progress_fn:
                    progress.update(1, 'creating mesh')
                pdx_mesh = pdx_data.PDXData(m)
                pdx_material = getattr(pdx_mesh, 'material', None)
                pdx_skin = getattr(pdx_mesh, 'skin', None)

                # create the geometry
                mesh = create_mesh(pdx_mesh, name=node.tag)

                # set mesh index from source file
                set_mesh_index(mesh, i)

                # create the material
                if pdx_material:
                    IO_PDX_LOG.info("creating material -")
                    if progress_fn:
                        progress.update(1, 'creating material')
                    create_material(pdx_material, mesh, os.path.split(meshpath)[0])

                # create the skin cluster
                if joints and pdx_skin:
                    IO_PDX_LOG.info("creating skinning data -")
                    if progress_fn:
                        progress.update(1, 'creating skinning data')
                    create_skin(pdx_skin, mesh, joints)

    # go through locators
    if imp_locs and locators:
        IO_PDX_LOG.info("creating locators -")
        if progress_fn:
            progress.update(1, 'creating locators')
        for loc in locators:
            pdx_locator = pdx_data.PDXData(loc)
            create_locator(pdx_locator, complete_bone_dict)

    pmc.select(None)
    IO_PDX_LOG.info("import finished! ({0:.4f} sec)".format(time.time() - start))
    if progress_fn:
        progress.finished()


def export_meshfile(meshpath, exp_mesh=True, exp_skel=True, exp_locs=True, merge_verts=True, progress_fn=None):
    start = time.time()
    IO_PDX_LOG.info("exporting {0}".format(meshpath))

    progress = None
    if progress_fn:
        progress = progress_fn('Exporting', 10)

    # create an XML structure to store the object hierarchy
    root_xml = Xml.Element('File')
    root_xml.set('pdxasset', [1, 0])

    # create root element for objects
    object_xml = Xml.SubElement(root_xml, 'object')

    # populate object data
    maya_meshes = list_scene_pdx_meshes()
    # sort meshes for export by index
    maya_meshes.sort(key=lambda mesh: get_mesh_index(mesh))

    for shape in maya_meshes:
        IO_PDX_LOG.info("writing node - {0}".format(shape.name()))
        if progress_fn:
            progress.update(1, 'writing node')
        shapenode_xml = Xml.SubElement(object_xml, shape.name())

        # one shape can have multiple materials on a per meshface basis
        shading_groups = list(set(shape.connections(type='shadingEngine')))

        if exp_mesh and shading_groups:
            # this type of ObjectSet associates shaders with geometry
            for group in shading_groups:
                # validate that this shading group corresponds to a PDX material, skip otherwise
                maya_mat = group.surfaceShader.connections()[0]
                if not hasattr(maya_mat, PDX_SHADER):
                    continue

                # create parent element for this mesh (mesh here being geometry sharing a material, within one shape)
                IO_PDX_LOG.info("writing mesh -")
                if progress_fn:
                    progress.update(1, 'writing mesh')
                meshnode_xml = Xml.SubElement(shapenode_xml, 'mesh')

                # check which faces are using this shading group
                # (groups are shared across shapes, so only select group members that are components of this shape)
                mesh = [m for m in group.members(flatten=True) if m.node() == shape][0]

                # get all necessary info about this set of faces and determine which unique verts they include
                mesh_info_dict, vert_ids = get_mesh_info(mesh, not merge_verts, True)

                # populate mesh attributes
                for key in ['p', 'n', 'ta', 'u0', 'u1', 'u2', 'u3', 'tri']:
                    if key in mesh_info_dict and mesh_info_dict[key]:
                        meshnode_xml.set(key, mesh_info_dict[key])

                # create parent element for bounding box data
                aabbnode_xml = Xml.SubElement(meshnode_xml, 'aabb')
                for key in ['min', 'max']:
                    if key in mesh_info_dict and mesh_info_dict[key]:
                        aabbnode_xml.set(key, mesh_info_dict[key])

                # create parent element for material data
                IO_PDX_LOG.info("writing material -")
                if progress_fn:
                    progress.update(1, 'writing material')
                materialnode_xml = Xml.SubElement(meshnode_xml, 'material')
                # populate material attributes
                materialnode_xml.set('shader', [get_material_shader(maya_mat)])
                mat_texture_dict = get_material_textures(maya_mat)
                for slot, texture in mat_texture_dict.iteritems():
                    materialnode_xml.set(slot, [os.path.split(texture)[1]])

                # create parent element for skin data, if the mesh is skinned
                skin_info_dict = get_mesh_skin_info(shape, vert_ids)
                if exp_skel and skin_info_dict:
                    IO_PDX_LOG.info("writing skinning data -")
                    if progress_fn:
                        progress.update(1, 'writing skinning data')
                    skinnode_xml = Xml.SubElement(meshnode_xml, 'skin')
                    for key in ['bones', 'ix', 'w']:
                        if key in skin_info_dict and skin_info_dict[key]:
                            skinnode_xml.set(key, skin_info_dict[key])

        # create parent element for skeleton data, if the mesh is skinned
        bone_info_list = get_mesh_skeleton_info(shape)
        if exp_skel and bone_info_list:
            IO_PDX_LOG.info("writing skeleton -")
            if progress_fn:
                progress.update(1, 'writing skeleton')
            skeletonnode_xml = Xml.SubElement(shapenode_xml, 'skeleton')

            # create sub-elements for each bone, populate bone attributes
            for bone_info_dict in bone_info_list:
                bonenode_xml = Xml.SubElement(skeletonnode_xml, bone_info_dict['name'])
                for key in ['ix', 'pa', 'tx']:
                    if key in bone_info_dict and bone_info_dict[key]:
                        bonenode_xml.set(key, bone_info_dict[key])

    # create root element for locators
    locator_xml = Xml.SubElement(root_xml, 'locator')
    maya_locators = [pmc.listRelatives(loc, type='transform', parent=True)[0] for loc in pmc.ls(type=pmc.nt.Locator)]

    if exp_locs and maya_locators:
        IO_PDX_LOG.info("writing locators -")
        if progress_fn:
            progress.update(1, 'writing locators')
        for loc in maya_locators:
            # create sub-elements for each locator, populate locator attributes
            locnode_xml = Xml.SubElement(locator_xml, loc.name())

            _position= loc.getTranslation(worldSpace=True)
            _rotation = loc.getRotation(worldSpace=True, quaternion=True)
            if exp_skel and loc.getParent() and type(loc.getParent()) == pmc.nt.Joint:
                _position= loc.getTranslation()
                _rotation = loc.getRotation(quaternion=True)

                locnode_xml.set('pa', [loc.getParent().name()])

            position = list(swap_coord_space(_position))
            rotation = list(swap_coord_space(_rotation))

            locnode_xml.set('p', position)
            locnode_xml.set('q', rotation)

    # write the binary file from our XML structure
    pdx_data.write_meshfile(meshpath, root_xml)

    pmc.select(None)
    IO_PDX_LOG.info("export finished! ({0:.4f} sec)".format(time.time() - start))
    if progress_fn:
        progress.finished()


def import_animfile(animpath, timestart=1, progress_fn=None):
    start = time.time()
    IO_PDX_LOG.info("importing {0}".format(animpath))

    progress = None
    if progress_fn:
        progress = progress_fn('Importing', 10)

    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(animpath)

    # find animation info and samples
    info = asset_elem.find('info')
    samples = asset_elem.find('samples')
    framecount = info.attrib['sa'][0]

    # set scene animation and playback settings
    fps = int(info.attrib['fps'][0])
    try:
        pmc.currentUnit(time=('{0}fps'.format(fps)))
    except RuntimeError:
        if fps == 15:
            pmc.currentUnit(time='game')
        elif fps == 30:
            pmc.currentUnit(time='ntsc')
        elif fps == 60:
            pmc.currentUnit(time='ntscf')
        else:
            raise RuntimeError("Unsupported animation speed. ({0} fps)".format(fps))

    IO_PDX_LOG.info("setting playback speed - {0}".format(fps))
    if progress_fn:
        progress.update(1, 'setting playback speed')
    pmc.playbackOptions(edit=True, playbackSpeed=1.0)
    pmc.playbackOptions(edit=True, animationStartTime=0.0)

    IO_PDX_LOG.info("setting playback range - ({0},{1})".format(timestart, (timestart + framecount - 1)))
    if progress_fn:
        progress.update(1, 'setting playback range')
    pmc.playbackOptions(edit=True, minTime=timestart)
    pmc.playbackOptions(edit=True, maxTime=(timestart + framecount - 1))

    pmc.currentTime(timestart, edit=True)

    # find bones being animated in the scene
    IO_PDX_LOG.info("finding bones -")
    if progress_fn:
        progress.update(1, 'finding bones')
    bone_errors = []
    bone_list = []
    for bone in info:
        bone_joint = None
        bone_name = clean_imported_name(bone.tag)
        try:
            matching_bones = pmc.ls(bone_name, type=pmc.nt.Joint, long=True)  # type: pmc.nodetypes.joint
            bone_joint = matching_bones[0]
        except IndexError:
            bone_errors.append(bone_name)
            IO_PDX_LOG.info("failed to find bone '{0}'".format(bone_name))
            if progress_fn:
                progress.update(1, 'failed to find bone!')

        # set initial transform and remove any joint orientation (this is baked into rotation values in the .anim file)
        if bone_joint:
            # compose transform parts
            _scale = [bone.attrib['s'][0], bone.attrib['s'][0], bone.attrib['s'][0]]
            _rotation = MQuaternion(*bone.attrib['q'])
            _translation = MVector(*bone.attrib['t'])

            # convert to Game space
            bone_joint.setScale(_scale)
            bone_joint.setRotation(swap_coord_space(_rotation))
            bone_joint.setTranslation(swap_coord_space(_translation))

            # zero out joint orientation
            bone_joint.jointOrient.set(0.0, 0.0, 0.0)

            bone_list.append(bone_joint)

    # break on bone errors
    if bone_errors:
        raise RuntimeError("Missing bones required for animation:\n{0}".format(bone_errors))

    # check which transform types are animated on each bone
    all_bone_keyframes = OrderedDict()
    for bone in info:
        bone_name = clean_imported_name(bone.tag)
        key_data = dict()
        all_bone_keyframes[bone_name] = key_data

        for sample_type in bone.attrib['sa'][0]:
            key_data[sample_type] = []

    # then traverse the samples data to store keys per bone
    s_index, q_index, t_index = 0, 0, 0
    for _ in range(0, framecount):
        for bone_name in all_bone_keyframes:
            bone_key_data = all_bone_keyframes[bone_name]

            if 's' in bone_key_data:
                bone_key_data['s'].append(samples.attrib['s'][s_index : s_index + 1])
                s_index += 1
            if 'q' in bone_key_data:
                bone_key_data['q'].append(samples.attrib['q'][q_index : q_index + 4])
                q_index += 4
            if 't' in bone_key_data:
                bone_key_data['t'].append(samples.attrib['t'][t_index : t_index + 3])
                t_index += 3

    for bone_name in all_bone_keyframes:
        bone_keys = all_bone_keyframes[bone_name]
        # check bone has keyframe values
        if bone_keys.values():
            IO_PDX_LOG.info("setting {0} keyframes on bone '{1}'".format(list(bone_keys.keys()), bone_name))
            if progress_fn:
                progress.update(1, 'setting keyframes on bone')
            bone_long_name = pmc.ls(bone_name, type=pmc.nt.Joint, long=True)[0].name()
            create_anim_keys(bone_long_name, bone_keys, timestart)

    animation_name = os.path.split(os.path.splitext(animpath)[0])[1]
    edit_animation_clip(bone_list, animation_name, timestart, (timestart + framecount - 1))

    pmc.select(None)
    IO_PDX_LOG.info("import finished! ({0:.4f} sec)".format(time.time() - start))
    if progress_fn:
        progress.finished()


def export_animfile(animpath, timestart=1, timeend=10, progress_fn=None):
    start = time.time()
    IO_PDX_LOG.info("Exporting {0}".format(animpath))

    progress = None
    if progress_fn:
        progress = progress_fn('Exporting', 10)

    curr_frame = pmc.currentTime(query=True)
    if timestart != int(timestart) or timeend != int(timeend):
        raise RuntimeError(
            "Invalid animation range selected ({0},{1}). Only whole frames are supported.".format(timestart, timeend)
        )
    timestart = int(timestart)
    timeend = int(timeend)

    # create an XML structure to store the object hierarchy
    root_xml = Xml.Element('File')
    root_xml.set('pdxasset', [1, 0])

    # create root element for animation info
    info_xml = Xml.SubElement(root_xml, 'info')

    # fill in animation info and initial pose
    IO_PDX_LOG.info("writing animation info -")
    fps = get_animation_fps()  # pmc.mel.currentTimeUnitToFPS()
    info_xml.set('fps', [float(fps)])

    frame_samples = (timeend + 1) - timestart
    info_xml.set('sa', [frame_samples])

    # find the scene root bone with animation property (assume this is unique)
    root_bone = None

    pdx_scene_rootbones = [bone for bone in list_scene_rootbones() if hasattr(bone, PDX_ANIMATION)]
    if len(pdx_scene_rootbones) == 1:
        root_bone = pdx_scene_rootbones[0]
    else:
        # try to use selection root bone
        selected_bones = pmc.selected(type='joint')
        if selected_bones:
            root_bone = selected_bones[0].root()

    if root_bone is None:
        raise RuntimeError(
            "Found {0} root bones with PDX animation. Please select a specific root bone before exporting.".format(
                len(pdx_scene_rootbones)
            )
        )

    # populate bone data, assume that the skeleton to be exported starts at the scene root bone
    export_bones = get_skeleton_hierarchy([root_bone])
    info_xml.set('j', [len(export_bones)])

    # parse the scene animation data
    all_bone_keyframes = get_scene_animdata(export_bones, timestart, timeend)

    # for each bone, write sample types and describe the initial offset from parent
    IO_PDX_LOG.info("writing initial bone transforms -")
    if progress_fn:
        progress.update(1, 'writing initial bone transforms')
    pmc.currentTime(timestart, edit=True)
    for bone in export_bones:
        bone_xml = Xml.SubElement(info_xml, bone.name())

        # check sample types
        sample_types = ''
        for attr in ['t', 'q', 's']:
            if attr in all_bone_keyframes[bone.name()]:
                sample_types += attr
        bone_xml.set('sa', [sample_types])

        # convert to Game space
        _translation = swap_coord_space(bone.getTranslation())
        # bone rotation must be pre-multiplied by joint orientation
        _rotation = swap_coord_space(bone.getRotation(quaternion=True) * bone.getOrientation())
        _scale = [bone.getScale()[0]]  # animation supports uniform scale only

        bone_xml.set('t', util_round(list(_translation), PDX_ROUND_TRANS))
        bone_xml.set('q', util_round(list(_rotation), PDX_ROUND_ROT))
        bone_xml.set('s', util_round(list(_scale), PDX_ROUND_SCALE))

    # create root element for animation keyframe data
    samples_xml = Xml.SubElement(root_xml, 'samples')
    IO_PDX_LOG.info("writing keyframes -")
    if progress_fn:
        progress.update(1, 'writing keyframes')
    for bone_name in all_bone_keyframes:
        bone_keys = all_bone_keyframes[bone_name]
        if bone_keys:
            IO_PDX_LOG.info("writing {0} keyframes for bone '{1}'".format(list(bone_keys.keys()), bone_name))

    # pack all scene animation data into flat keyframe lists
    t_packed, q_packed, s_packed = [], [], []
    for i in range(frame_samples):
        for bone in all_bone_keyframes:
            if 't' in all_bone_keyframes[bone]:
                t_packed.extend(all_bone_keyframes[bone]['t'].pop(0))  # TODO: pop first item is slow?
            if 'q' in all_bone_keyframes[bone]:
                q_packed.extend(all_bone_keyframes[bone]['q'].pop(0))
            if 's' in all_bone_keyframes[bone]:
                s_packed.append(all_bone_keyframes[bone]['s'].pop(0)[0])  # support uniform scale only

    if t_packed:
        samples_xml.set('t', t_packed)
    if q_packed:
        samples_xml.set('q', q_packed)
    if s_packed:
        samples_xml.set('s', s_packed)

    # write the binary file from our XML structure
    pdx_data.write_animfile(animpath, root_xml)

    pmc.currentTime(curr_frame, edit=True)

    IO_PDX_LOG.info("export finished! ({0:.4f} sec)".format(time.time() - start))
    if progress_fn:
        progress.finished()
