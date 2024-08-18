"""
Paradox asset files, Maya import/export.

As Mayas 3D space is (Y-up, right-handed) and the Clausewitz engine seems to be (Y-up, left-handed) we have to
mirror all positions, normals etc about the XY plane and flip texture coordinates in V.
Note - Maya treats matrices as row-major.

author : ross-g
"""

from __future__ import print_function, unicode_literals

import os
import sys
import time
from collections import OrderedDict, defaultdict, namedtuple
from operator import itemgetter

try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

# Maya Python API 2.0
import maya.api.OpenMaya as OpenMayaAPI
import maya.cmds as cmds

# Maya Python API 1.0
import maya.OpenMaya as OpenMaya
import maya.OpenMayaAnim as OpenMayaAnim
import pymel.core as pmc
import pymel.core.datatypes as pmdt
from maya.api.OpenMaya import MMatrix, MQuaternion, MTransformationMatrix, MVector

from .. import IO_PDX_LOG, pdx_data
from ..external import pathlib

# Py2, Py3 compatibility (Maya 2022+ adopts Py3)
from ..external.six.moves import range
from ..library import (
    PDX_ANIMATION,
    PDX_DECIMALPTS,
    PDX_IGNOREJOINT,
    PDX_MAXSKININFS,
    PDX_MAXUVSETS,
    PDX_MESHINDEX,
    PDX_ROUND_ROT,
    PDX_ROUND_SCALE,
    PDX_ROUND_TRANS,
    PDX_SHADER,
    allow_debug_logging,
    get_lod_level,
)

""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

maya_up = cmds.upAxis(query=True, axis=True)
# fmt: off
SPACE_MATRIX = MMatrix((
    (1, 0, 0, 0),
    (0, 1, 0, 0),
    (0, 0, -1, 0),
    (0, 0, 0, 1)
))
if maya_up == "z":
    SPACE_MATRIX = MMatrix((
        (1, 0, 0, 0),
        (0, 0, 1, 0),
        (0, 1, 0, 0),
        (0, 0, 0, 1)
    ))
SPACE_MATRIX_INV = SPACE_MATRIX.inverse()
# fmt: on


""" ====================================================================================================================
    API functions.
========================================================================================================================
"""


def get_mobject(name):
    sel_list = OpenMayaAPI.MSelectionList()
    sel_list.add(name)
    m_obj = sel_list.getDependNode(0)

    return m_obj


def get_dagpath(name):
    sel_list = OpenMayaAPI.MSelectionList()
    sel_list.add(name)
    m_dagpath = sel_list.getDagPath(0)

    return m_dagpath


def get_dagnode(name):
    m_obj = get_mobject(name)
    fn_dag = OpenMayaAPI.MFnDagNode(m_obj)

    return fn_dag


def get_dagroot(name):
    dag = get_dagnode(name)
    while dag.parentCount() != 0 and dag.parent(0).apiType() != OpenMayaAPI.MFn.kWorld:
        dag = OpenMayaAPI.MFnDagNode(dag.parent(0))

    return pmc.PyNode(dag.name())


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
    """Element-wise rounding to a given precision in decimal digits. (reimplementing pmc.util.round for speed)."""
    return tuple(round(x, ndigits) for x in data)


def clean_imported_name(name):
    # strip any namespace names, taking the final name only
    clean_name = name.split(":")[-1]

    # replace hierarchy separator character used by Maya in the case of non-unique leaf node names
    clean_name = clean_name.replace("|", "_")

    return clean_name


def list_scene_pdx_materials():
    return [mat for mat in pmc.ls(materials=True) if hasattr(mat, PDX_SHADER)]


def list_scene_rootbones():
    return list(set([get_dagroot(bone.name()) for bone in pmc.ls(type="joint")]))


def list_scene_pdx_meshes():
    return [mesh for mesh in pmc.ls(type="mesh", noIntermediate=True) if check_mesh_material(mesh)]


def set_local_axis_display(state, object_type=None, object_list=None):
    if object_list is None:
        if object_type is None:
            object_list = pmc.selected()
        else:
            object_list = pmc.ls(type=object_type)

    for node in object_list:
        if not hasattr(node, "displayLocalAxis"):
            node = pmc.listRelatives(node, parent=True)[0]
        try:
            node.displayLocalAxis.set(state)
        except Exception as err:
            IO_PDX_LOG.warning("could not display local axis for node - {0}".format(node))
            IO_PDX_LOG.error(err)


def set_ignore_joints(state):
    joint_list = pmc.selected(type="joint")

    for joint in joint_list:
        try:
            getattr(joint, PDX_IGNOREJOINT).set(state)
        except Exception:
            pmc.addAttr(joint, longName=PDX_IGNOREJOINT, attributeType="bool")
            getattr(joint, PDX_IGNOREJOINT).set(state)


def get_animation_fps():
    # mel.eval("float $fps = `currentTimeUnitToFPS`")
    return pmc.mel.currentTimeUnitToFPS()


def set_animation_fps(fps):
    try:
        cmds.currentUnit(time=("{0}fps".format(fps)))
    except RuntimeError:
        if fps == 15:
            cmds.currentUnit(time="game")
        elif fps == 30:
            cmds.currentUnit(time="ntsc")
        elif fps == 60:
            cmds.currentUnit(time="ntscf")
        else:
            raise RuntimeError("Unsupported animation speed. ({0} fps)".format(fps))


def set_mesh_index(maya_mesh, i):
    if not hasattr(maya_mesh, PDX_MESHINDEX):
        pmc.addAttr(maya_mesh, longName=PDX_MESHINDEX, attributeType="byte")

    getattr(maya_mesh, PDX_MESHINDEX).set(i)


def get_mesh_index(maya_mesh):
    if hasattr(maya_mesh, PDX_MESHINDEX):
        return getattr(maya_mesh, PDX_MESHINDEX).get()
    else:
        return 255


def check_mesh_material(maya_mesh):
    result = False

    shadingengines = list(set(pmc.listConnections(maya_mesh, type="shadingEngine")))
    for sg in shadingengines:
        material = pmc.listConnections(sg.surfaceShader)[0]
        result = result or hasattr(material, PDX_SHADER)  # needs at least one of it's materials to be a PDX material

    return result


def get_material_shader(maya_material):
    shader_attr = getattr(maya_material, PDX_SHADER)
    shader_val = shader_attr.get()

    # PDX source assets use an enum attr
    if shader_attr.type() == "enum":
        _enum_dict = shader_attr.getEnums()
        return _enum_dict[shader_val]

    # imported assets will get a string attr
    elif shader_attr.type() == "string":
        return shader_val


def get_material_textures(maya_material):
    texture_dict = {}

    basecolor = maya_material.color.connections()
    if basecolor:
        filepath = basecolor[0].fileTextureName.get()
        if filepath:
            texture_dict["diff"] = filepath

    roughness = maya_material.specularColor.connections()
    if roughness:
        filepath = roughness[0].fileTextureName.get()
        if filepath:
            texture_dict["spec"] = filepath

    normal = maya_material.normalCamera.connections()
    if normal:
        bump2d = normal[0]
        filepath = bump2d.bumpValue.connections()[0].fileTextureName.get()
        if filepath:
            texture_dict["n"] = filepath

    return texture_dict


def get_mesh_info(maya_mesh, split_criteria=None, split_all=False, sort_vertices=True):
    """Returns a dictionary of mesh information neccessary to the exporter.

    This performs a tri-split on all points to create unique vertices where points have split UV or Normal data.
    `split_all` will enable tri-split on all points even where points share data.

    Points are processed in order of vertex id for each triangle to maintain compatibility with the official exporter.
    `sort_vertices` will allow for descending/DCC-native/ascending vertex order.
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

    # API mesh function set
    mesh_obj = get_mobject(mesh.name())
    mFn_Mesh = OpenMayaAPI.MFnMesh(mesh_obj)

    # cache some mesh data
    vertices = mesh.getPoints(space="world")  # list of vertices positions
    normals = mesh.getNormals(space="world")  # list of vectors for each vertex per face
    triangles = mesh.getTriangles()
    uv_setnames = [uv_set for uv_set in mesh.getUVSetNames() if mFn_Mesh.numUVs(uv_set) > 0][:PDX_MAXUVSETS]
    uv_data = {}
    tangents = None
    for i, uv_set in enumerate(uv_setnames):
        _u, _v = mesh.getUVs(uvSet=uv_set)
        uv_data[i] = list(zip(_u, _v))
    if uv_setnames:
        tangents = mesh.getTangents(space="world", uvSet=uv_setnames[0])

    # build a blank dictionary of mesh information for the exporter
    mesh_dict = {x: [] for x in ["p", "n", "ta", "u0", "u1", "u2", "u3", "tri", "min", "max"]}

    # we will need to test vertices for equality based on their attributes and some split criteria
    # critically: whether per-face vertices (sharing an object-relative vert id) share normals and uvs
    split_criteria = split_criteria or ["id", "p", "n", "uv"]
    UniqueVertex = namedtuple("UniqueVertex", split_criteria)

    # collect all unique verts in the order that we process them
    export_verts = []
    unique_verts = set()

    for face in meshfaces:
        face_id = face.index()
        face_vert_ids = face.getVertices()  # vertices making this face
        num_triangles = triangles[0][face_id]  # number of triangles making this face

        # store data for each tri of each face
        for tri in range(0, num_triangles):
            tri_vert_ids = mesh.getPolygonTriangleVertices(face_id, tri)  # vertices making this triangle

            # process verts for each triangle, sort the list of tri-verts in vertex order or use default Maya ordering
            if sort_vertices is not None:
                _sorted = sorted(enumerate(tri_vert_ids), key=lambda x: x[1], reverse=not sort_vertices)
                indices = [i[0] for i in _sorted]  # track sorting change
                tri_vert_ids = [i[1] for i in _sorted]
            else:
                indices = [0, 1, 2]

            dict_vert_idx = []
            # iterate over tri verts
            for vert_id in tri_vert_ids:
                _local_id = face_vert_ids.index(vert_id)  # face relative vertex index

                # position
                _position = vertices[vert_id]
                _position = tuple(swap_coord_space(_position))

                # normal
                vert_norm_id = face.normalIndex(_local_id)
                _normal = list(normals[vert_norm_id])
                _normal = tuple(swap_coord_space(_normal))

                # uv
                _uv_coords = ()
                for i, uv_set in enumerate(uv_setnames):
                    try:
                        vert_uv_id = face.getUVIndex(_local_id, uv_set)
                        uv = uv_data[i][vert_uv_id]
                        uv = swap_coord_space(uv)
                    # case where verts are unmapped, eg when two meshes are merged with different UV set counts
                    except RuntimeError:
                        uv = (0.0, 0.0)
                    _uv_coords += (uv,)

                # tangent (omitted if there were no UVs)
                if uv_setnames and tangents:
                    vert_tangent_id = mesh.getTangentId(face_id, vert_id)
                    _binormal_sign = 1.0 if mFn_Mesh.isRightHandedTangent(vert_tangent_id, uv_setnames[0]) else -1.0
                    _tangent = list(tangents[vert_tangent_id])
                    _tangent = swap_coord_space(_tangent)

                # check if this tri-verts vertex data is new and unique, or can if we can just use an existing vertex
                vdata = {"id": vert_id, "p": _position, "n": _normal, "uv": _uv_coords}
                new_vert = UniqueVertex(*[vdata.get(x) for x in split_criteria])

                # test if we have already stored this vertex in the unique set
                i = None
                if not split_all:
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
                        mesh_dict["ta"].append(_binormal_sign)  # UV winding order
                    # the tri will reference the last added vertex
                    i = len(export_verts) - 1

                # store the tri-vert reference
                dict_vert_idx.append(i)

            # tri-faces (converting handedness to Game space)
            mesh_dict["tri"].extend(
                # to build the tri-face correctly, we need to use the original unsorted vertex order to reference verts
                [dict_vert_idx[indices[0]], dict_vert_idx[indices[2]], dict_vert_idx[indices[1]]]
            )

    if not export_verts:
        # no mesh data collected?
        return {}, []

    # calculate mesh bounds
    x_vtx_pos = set(mesh_dict["p"][::3])
    y_vtx_pos = set(mesh_dict["p"][1::3])
    z_vtx_pos = set(mesh_dict["p"][2::3])
    # min and max axis aligned bounding box
    mesh_dict["min"] = [min(x_vtx_pos), min(y_vtx_pos), min(z_vtx_pos)]
    mesh_dict["max"] = [max(x_vtx_pos), max(y_vtx_pos), max(z_vtx_pos)]
    # centre and radius of bounding sphere
    centre = MVector(*[(mesh_dict["max"][axis] + mesh_dict["min"][axis]) * 0.5 for axis in range(3)])
    radius = max(((MVector(*vertex.p) - centre).length() for vertex in unique_verts))
    mesh_dict["boundingsphere"] = [centre.x, centre.y, centre.z, radius]

    # create an ordered list of vertex ids that we have gathered into the mesh dict
    vert_id_list = [vert.id for vert in export_verts]

    return mesh_dict, vert_id_list


def get_mesh_skin_info(maya_mesh, vertex_ids=None):
    # pmc.skinPercent(skin, maya_mesh, normalize=True, pruneWeights=0.1)
    skinclusters = list(set(pmc.listConnections(maya_mesh, type="skinCluster")))
    if not skinclusters:
        return None

    # a mesh can only be connected to one skin cluster
    skin = skinclusters[0]

    # build a dictionary of skin information for the exporter
    skin_dict = {x: [] for x in ["bones", "ix", "w"]}

    # set number of joint influences per vert
    skin_maxinfs = skin.getMaximumInfluences()
    if skin_maxinfs > PDX_MAXSKININFS:
        raise RuntimeError(
            "Mesh '{0}' has skinning with max influences set to more than {1}! This is not supported.".format(
                maya_mesh.getTransform().name(), PDX_MAXSKININFS
            )
        )
    skin_dict["bones"].append(skin_maxinfs)

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
                "A skinned bone ({0}) is being excluded from export! Check all bones using the '{1}' property.".format(
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
        # if we have excess influences, prune them and renormalise weights
        if len(vert_weights[vtx]) > PDX_MAXSKININFS:
            IO_PDX_LOG.warning(
                "mesh '{0}' has vertices skinned to more than {1} joints.".format(
                    maya_mesh.getTransform().name(), PDX_MAXSKININFS
                )
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
            # pad out with null data to fill containers, so each is the same size
            padding = PDX_MAXSKININFS - len(vert_weights[vtx])
            skin_dict["ix"].extend([-1] * padding)
            skin_dict["w"].extend([0.0] * padding)

    return skin_dict


def get_mesh_skeleton_info(maya_mesh):
    skinclusters = list(set(pmc.listConnections(maya_mesh, type="skinCluster")))
    if not skinclusters:
        return []

    # a mesh can only be connected to one skin cluster
    skin = skinclusters[0]

    # find all bones in hierarchy to be exported
    rig_bones = get_skeleton_hierarchy(skin.influenceObjects())

    return get_bones_info(rig_bones)


def get_bones_info(maya_bones):
    # build a list of bone information dictionaries for the exporter
    bone_list = [{"name": x.name()} for x in maya_bones]

    for i, bone in enumerate(maya_bones):
        # bone index
        bone_list[i]["ix"] = [i]

        # bone parent index
        if bone.getParent():
            bone_list[i]["pa"] = [maya_bones.index(bone.getParent())]

        # bone inverse world-space transform
        mat = list(swap_coord_space(bone.getMatrix(worldSpace=True)).inverse())
        bone_list[i]["tx"] = []
        bone_list[i]["tx"].extend(mat[0:3])
        bone_list[i]["tx"].extend(mat[4:7])
        bone_list[i]["tx"].extend(mat[8:11])
        bone_list[i]["tx"].extend(mat[12:15])

    return bone_list


def get_locators_info(maya_locators):
    # build a list of locator information dictionaries for the exporter
    locator_list = [{"name": x.name()} for x in maya_locators]

    for i, loc in enumerate(maya_locators):
        # unparented, use worldspace position/rotation
        _position = loc.getTranslation(worldSpace=True)
        _rotation = loc.getRotation(worldSpace=True, quaternion=True)

        # parented to bone, use local position/rotation
        loc_parent = loc.getParent()
        if loc_parent is not None and type(loc_parent) == pmc.nt.Joint:
            locator_list[i]["pa"] = [loc_parent.name()]
            _position = loc.getTranslation()
            _rotation = loc.getRotation(quaternion=True)

        locator_list[i]["p"] = list(swap_coord_space(_position))
        locator_list[i]["q"] = list(swap_coord_space(_rotation))

        _scale = loc.getScale()
        is_scaled = util_round(list(_scale), PDX_ROUND_SCALE) != (1.0, 1.0, 1.0)
        # TODO: check engine config here to see if full 'tx' attribute is supported
        if is_scaled:
            _transform = loc.getMatrix()
            locator_list[i]["tx"] = list(swap_coord_space(_transform))

    return locator_list


def get_skeleton_hierarchy(bone_list):
    root_bone = set()
    for bone in bone_list:
        root_bone.add(get_dagroot(bone.name()))

    if len(root_bone) != 1:
        raise RuntimeError("Unable to resolve a single root bone for the skeleton. {0}".format(list(root_bone)))

    root_bone = list(root_bone)[0]

    def get_recursive_children(bone, hierarchy):
        hierarchy.append(bone)
        children = [
            jnt
            for jnt in pmc.listRelatives(bone, children=True, type="joint")
            if not (hasattr(jnt, PDX_IGNOREJOINT) and getattr(jnt, PDX_IGNOREJOINT).get())
        ]

        for bone in children:
            get_recursive_children(bone, hierarchy)

        return hierarchy

    valid_bones = []
    get_recursive_children(root_bone, valid_bones)

    return valid_bones


def get_scene_animdata(export_bones, startframe, endframe):
    # store transform for each bone over the frame range
    frames_data = defaultdict(list)

    try:
        cmds.refresh(suspend=True)
        for f in range(startframe, endframe + 1):
            pmc.currentTime(f, edit=True)
            for bone in export_bones:
                # TODO: this is slow, don't use PyMel here or check f-curves directly
                _translation = swap_coord_space(bone.getTranslation())
                # bone rotation must be pre-multiplied by joint orientation
                _rotation = swap_coord_space(bone.getRotation(quaternion=True) * bone.getOrientation())
                _scale = bone.getScale()

                frames_data[bone.name()].append((_translation, _rotation, _scale))
    except Exception as err:
        IO_PDX_LOG.error(err)
        raise
    finally:
        cmds.refresh(suspend=False)
        cmds.refresh(force=True)

    # convert from defaultdict after building up the data
    frames_data = dict(frames_data)

    # create an ordered dictionary of all animated bones to store sample data
    all_bone_keyframes = OrderedDict()
    for bone in export_bones:
        all_bone_keyframes[bone.name()] = dict()

    # determine if any transform attributes were animated over this frame range for each bone
    # FIXME: this should look at f-curves and keys, not just a set() of transform data
    for bone in export_bones:
        # convert data from list of tuples [(t,q,s)] to three nested lists [t][q][s]
        t_list, q_list, s_list = zip(*frames_data[bone.name()])
        t_list = [tuple(t) for t in t_list]
        q_list = [tuple(q) for q in q_list]
        s_list = [tuple(s) for s in s_list]

        # store any animated transform samples per attribute
        for attr, attr_list in zip(["t", "q", "s"], [t_list, q_list, s_list]):
            if len(set(attr_list)) != 1:
                all_bone_keyframes[bone.name()][attr] = attr_list

    return all_bone_keyframes


def swap_coord_space(data, space_mat=SPACE_MATRIX, space_mat_inv=SPACE_MATRIX_INV):
    """Transforms from PDX space (-Z forward, Y up) to Maya space (Z forward, Y up)."""
    # matrix
    if type(data) == MMatrix or type(data) == pmdt.Matrix:
        mat = MMatrix(data)
        return space_mat * mat * space_mat_inv
    # quaternion
    elif type(data) == MQuaternion or type(data) == pmdt.Quaternion:
        mat = MMatrix(data.asMatrix())
        return MTransformationMatrix(space_mat * mat * space_mat_inv).rotation(asQuaternion=True)
    # vector
    elif type(data) == MVector or type(data) == pmdt.Vector or len(data) == 3:
        vec = MVector(data)
        return vec * space_mat
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
    """Creates and connects up a new file node and place2dTexture node, uses the supplied filepath."""
    newFile = pmc.shadingNode("file", asTexture=True)
    new2dTex = pmc.shadingNode("place2dTexture", asUtility=True)

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

    if not os.path.isfile(tex_filepath):
        IO_PDX_LOG.warning("unable to find texture filepath - {0}".format(tex_filepath))

    return newFile, new2dTex


def create_shader(PDX_material, shader_name, texture_dir):
    new_shader = pmc.shadingNode("phong", asShader=True, name=shader_name, skipSelect=True)
    new_shadinggroup = pmc.sets(renderable=True, noSurfaceShader=True, empty=True, name="{0}_SG".format(shader_name))
    pmc.connectAttr(new_shader.outColor, new_shadinggroup.surfaceShader)

    # add the game shader attribute, PDX tool uses ENUM attr to store but writes as a string
    pmc.addAttr(new_shader, longName=PDX_SHADER, dataType="string")
    getattr(new_shader, PDX_SHADER).set(PDX_material.shader[0])

    if getattr(PDX_material, "diff", None):
        texture_path = os.path.join(texture_dir, PDX_material.diff[0])
        new_file, _ = create_filetexture(texture_path)
        pmc.connectAttr(new_file.outColor, new_shader.color)
        if new_file.fileHasAlpha.get():
            pmc.connectAttr(new_file.outTransparency, new_shader.transparency)

    if getattr(PDX_material, "n", None):
        texture_path = os.path.join(texture_dir, PDX_material.n[0])
        new_file, _ = create_filetexture(texture_path)
        bump2d = pmc.shadingNode("bump2d", asUtility=True)
        bump2d.bumpDepth.set(0.1)
        new_file.alphaIsLuminance.set(True)
        pmc.connectAttr(new_file.outAlpha, bump2d.bumpValue)
        pmc.connectAttr(bump2d.outNormal, new_shader.normalCamera)

    if getattr(PDX_material, "spec", None):
        texture_path = os.path.join(texture_dir, PDX_material.spec[0])
        new_file, _ = create_filetexture(texture_path)
        pmc.connectAttr(new_file.outColor, new_shader.specularColor)

    return new_shader, new_shadinggroup


def create_material(PDX_material, mesh, texture_folder):
    shader_name = "PDXmat_" + mesh.name()
    shader, group = create_shader(PDX_material, shader_name, texture_folder)

    pmc.select(mesh)
    mesh.backfaceCulling.set(1)
    pmc.hyperShade(assign=group)


def create_locator(PDX_locator, PDX_bone_dict):
    """Creates a Maya Locator object."""
    # create locator
    new_loc = pmc.spaceLocator()
    pmc.select(new_loc)
    pmc.rename(new_loc, PDX_locator.name)

    # check for parent, then parent locator to scene bone, or apply parents transform
    parent = getattr(PDX_locator, "pa", None)
    parent_Xform = None

    if parent is not None:
        parent_bone = pmc.ls(parent[0], type="joint")
        if parent_bone:
            # parent the locator to a bone in the scene
            pmc.parent(new_loc, parent_bone[0])
        else:  # parent bone doesn't exist in current scene
            # determine the locators transform
            if parent[0] in PDX_bone_dict:
                transform = PDX_bone_dict[parent[0]]
                # fmt: off
                parent_Xform = pmdt.Matrix(
                    transform[0], transform[1], transform[2], 0.0,
                    transform[3], transform[4], transform[5], 0.0,
                    transform[6], transform[7], transform[8], 0.0,
                    transform[9], transform[10], transform[11], 1.0,
                )
                # fmt: on
            else:
                IO_PDX_LOG.warning(
                    "unable to create locator '{0}' (missing parent '{1}' in file data)".format(
                        PDX_locator.name, parent[0]
                    )
                )
                pmc.delete(new_loc)
                return

    # get transform function set
    loc_MObj = get_mobject(new_loc.name())
    mFn_Xform = OpenMayaAPI.MFnTransform(loc_MObj)

    # if full transformation is available, set transformation directly
    if hasattr(PDX_locator, "tx"):
        # fmt: off
        loc_Xform = MTransformationMatrix(
            MMatrix((
                (PDX_locator.tx[0], PDX_locator.tx[1], PDX_locator.tx[2], PDX_locator.tx[3]),
                (PDX_locator.tx[4], PDX_locator.tx[5], PDX_locator.tx[6], PDX_locator.tx[7]),
                (PDX_locator.tx[8], PDX_locator.tx[9], PDX_locator.tx[10], PDX_locator.tx[11]),
                (PDX_locator.tx[12], PDX_locator.tx[13], PDX_locator.tx[14], PDX_locator.tx[15]),
            ))
        )
        # fmt: on
        mFn_Xform.setTransformation(loc_Xform)
    # otherwise just rotate and translate components
    else:
        # rotation
        quat = MQuaternion(*PDX_locator.q)
        mFn_Xform.setRotation(quat, OpenMayaAPI.MSpace.kTransform)
        # translation
        vector = MVector(PDX_locator.p[0], PDX_locator.p[1], PDX_locator.p[2])
        mFn_Xform.setTranslation(vector, OpenMayaAPI.MSpace.kTransform)

    # apply parent transform
    if parent_Xform is not None:
        new_loc.setMatrix(new_loc.getMatrix() * parent_Xform.inverse())

    new_loc.setMatrix(swap_coord_space(new_loc.getMatrix()))

    return new_loc


def create_skeleton(PDX_bone_list):
    # keep track of bones as we create them
    bone_list = [None for _ in range(0, len(PDX_bone_list))]

    pmc.select(clear=True)
    for bone in PDX_bone_list:
        index = bone.ix[0]
        transform = bone.tx
        parent = getattr(bone, "pa", None)

        # determine unique bone name
        # Maya allows non-unique transform names (on leaf nodes) and handles it internally by using | separators
        unique_name = clean_imported_name(bone.name)

        # check if bone already exists, possible the skeleton is already built so collect and return joints
        existing_bone = pmc.ls(unique_name, type="joint")
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
            transform[9], transform[10], transform[11], 1.0,
        )
        # fmt: on
        new_bone.setMatrix(swap_coord_space(mat.inverse()), worldSpace=True)  # set to matrix inverse in world-space
        pmc.select(clear=True)

        # connect to parent
        if parent is not None:
            parent_bone = bone_list[parent[0]]
            pmc.connectJoint(new_bone, parent_bone, parentMode=True)

        IO_PDX_LOG.debug("new joint created - {0}".format(new_bone.name()))

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
    for vtx in range(0, int(len(PDX_skin.ix) / max_infs)):
        skin_dict[vtx] = dict(joints=[], weights=[])

    # gather joint index and weighting that each vertex is skinned to
    for vtx, j in enumerate(range(0, len(PDX_skin.ix), max_infs)):
        skin_dict[vtx]["joints"] = PDX_skin.ix[j : j + num_infs]
        skin_dict[vtx]["weights"] = PDX_skin.w[j : j + num_infs]

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
    for vtx in range(len(skin_dict.keys())):
        indices.append(vtx)
    mFn_SingleIdxCo = OpenMaya.MFnSingleIndexedComponent()
    vertex_IdxCo = mFn_SingleIdxCo.create(OpenMaya.MFn.kMeshVertComponent)
    mFn_SingleIdxCo.addElements(indices)  # must only add indices after running create()

    infs = OpenMaya.MIntArray()
    for j in range(len(skeleton)):
        infs.append(j)

    weights = OpenMaya.MDoubleArray()
    for vtx in range(len(skin_dict.keys())):
        jts = skin_dict[vtx]["joints"]
        wts = skin_dict[vtx]["weights"]
        for j in range(len(skeleton)):
            if j in jts:
                weights.append(wts[jts.index(j)])
            else:
                weights.append(0.0)

    # set skin weights
    mFn_SkinCluster.setWeights(mesh_dag, vertex_IdxCo, infs, weights)

    # turn on skin weights normalization again
    pmc.setAttr("{0}.normalizeWeights".format(skin_cluster), True)


def create_mesh(PDX_mesh, name=None):
    """Creates a Maya mesh object."""
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

    # build the following arguments for the MFnMesh.create() function
    # numVertices, numPolygons, vertexArray, polygonCounts, polygonConnects, uArray, vArray, new_transform

    # vertices
    numVertices = 0
    vertexArray = OpenMaya.MFloatPointArray()  # array of points
    for i in range(0, len(verts), 3):
        _verts = swap_coord_space([verts[i], verts[i + 1], verts[i + 2]])
        v = OpenMaya.MFloatPoint(_verts[0], _verts[1], _verts[2])
        vertexArray.append(v)
        numVertices += 1

    # faces
    numPolygons = int(len(tris) / 3)
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
        for i in range(0, len(uv_data), 2):
            uArray.append(uv_data[i])
            vArray.append(1 - uv_data[i + 1])  # flip the UV coords in V!

    """ ================================================================================================================
        Create the new mesh """

    # create the data structures for mesh and transform
    mFn_Mesh = OpenMaya.MFnMesh()
    m_DagMod = OpenMaya.MDagModifier()
    new_transform = m_DagMod.createNode("transform")

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
        mFn_Transform.setName(mesh_name.replace("Shape", ""))

    # apply the vertex normal data
    if norms:
        normalsIn = OpenMaya.MVectorArray()  # array of vectors
        for i in range(0, len(norms), 3):
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
        mFn_Mesh.assignUVs(uvCounts, uvIds, "map1")

    # set other UV channels
    for idx in uv_Ch:
        # ignore Ch 0 as we have already set this
        if idx != 0:
            uv_data = uv_Ch[idx]
            uvSetName = "map" + str(idx + 1)

            uArray = OpenMaya.MFloatArray()
            vArray = OpenMaya.MFloatArray()
            for i in range(0, len(uv_data), 2):
                uArray.append(uv_data[i])
                vArray.append(1 - uv_data[i + 1])  # flip the UV coords in V!

            mFn_Mesh.createUVSetWithName(uvSetName)
            mFn_Mesh.setUVs(uArray, vArray, uvSetName)
            mFn_Mesh.assignUVs(uvCounts, uvIds, uvSetName)

    mFn_Mesh.updateSurface()

    # assign the default material
    pmc.select(new_mesh)
    shd_group = pmc.PyNode("initialShadingGroup")
    pmc.hyperShade(assign=shd_group)
    new_obj = pmc.PyNode(new_transform)

    return new_mesh, new_obj


def create_animcurve(joint, attr):
    mFn_AnimCurve = OpenMayaAnim.MFnAnimCurve()

    # use the attribute on the joint to determine which type of anim curve to create
    in_plug = get_plug(joint, attr)
    plug_type = mFn_AnimCurve.timedAnimCurveTypeForPlug(in_plug)

    # create the curve and get its output attribute
    anim_curve = mFn_AnimCurve.create(plug_type)
    mFn_AnimCurve.setName("{0}_{1}".format(OpenMaya.MFnDependencyNode(joint).name(), attr))

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
    connect_nodeplugs(anim_curve, "output", joint, attr)

    return anim_curve, mFn_AnimCurve


def create_anim_keys(joint_name, key_dict, timestart):
    jnt_obj = get_MObject(joint_name)

    # calculate start and end frames
    timestart = int(timestart)
    timeend = timestart + len(max(key_dict.values(), key=len))

    # create a time array
    time_array = OpenMaya.MTimeArray()
    for t in range(timestart, timeend):
        time_array.append(OpenMaya.MTime(t, OpenMaya.MTime.uiUnit()))

    # define anim curve tangent
    k_Tangent = OpenMayaAnim.MFnAnimCurve.kTangentLinear

    if "s" in key_dict:  # scale data
        animated_attrs = dict(scaleX=None, scaleY=None, scaleZ=None)

        for attrib in animated_attrs:
            # create the curve and API function set
            anim_curve, mFn_AnimCurve = create_animcurve(jnt_obj, attrib)
            animated_attrs[attrib] = mFn_AnimCurve

        # create data arrays per animating attribute
        x_scale_data = OpenMaya.MDoubleArray()
        y_scale_data = OpenMaya.MDoubleArray()
        z_scale_data = OpenMaya.MDoubleArray()

        for scale_data in key_dict["s"]:
            # TODO: if maya_up == "z"
            s = MVector(*scale_data)
            x_scale_data.append(s[0])
            y_scale_data.append(s[1])
            z_scale_data.append(s[2])

        # add keys to the new curves
        for attrib, data_array in zip(animated_attrs, [x_scale_data, y_scale_data, z_scale_data]):
            mFn_AnimCurve = animated_attrs[attrib]
            mFn_AnimCurve.addKeys(time_array, data_array, k_Tangent, k_Tangent)

    if "q" in key_dict:  # quaternion data
        animated_attrs = dict(rotateX=None, rotateY=None, rotateZ=None)

        for attrib in animated_attrs:
            # create the curve and API function set
            anim_curve, mFn_AnimCurve = create_animcurve(jnt_obj, attrib)
            animated_attrs[attrib] = mFn_AnimCurve

        # create data arrays per animating attribute
        x_rot_data = OpenMaya.MDoubleArray()
        y_rot_data = OpenMaya.MDoubleArray()
        z_rot_data = OpenMaya.MDoubleArray()

        for quat_data in key_dict["q"]:
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

    if "t" in key_dict:  # translation data
        animated_attrs = dict(translateX=None, translateY=None, translateZ=None)

        for attrib in animated_attrs:
            # create the curve and API function set
            anim_curve, mFn_AnimCurve = create_animcurve(jnt_obj, attrib)
            animated_attrs[attrib] = mFn_AnimCurve

        # create data arrays per animating attribute
        x_trans_data = OpenMaya.MDoubleArray()
        y_trans_data = OpenMaya.MDoubleArray()
        z_trans_data = OpenMaya.MDoubleArray()

        for trans_data in key_dict["t"]:
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


@allow_debug_logging
def import_meshfile(meshpath, imp_mesh=True, imp_skel=True, imp_locs=True, join_materials=True, **kwargs):
    progress = kwargs.get("progress_fn", lambda *args, **kwargs: None)

    start = time.time()
    IO_PDX_LOG.info("importing - {0}".format(meshpath))
    progress("show", 10, "Importing")

    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(meshpath)

    # find shapes and locators
    shapes = asset_elem.find("object")
    locators = asset_elem.find("locator")

    # store all bone transforms, irrespective of skin association
    complete_bone_dict = dict()

    # go through shapes
    for i, node in enumerate(shapes):
        IO_PDX_LOG.info("creating node {0}/{1} - {2}".format(i + 1, len(shapes), node.tag))
        progress("update", 1, "creating node")

        # create the skeleton first, so we can skin the mesh to it
        joints = None
        skeleton = node.find("skeleton")
        if skeleton:
            pdx_bone_list = list()
            for b in skeleton:
                pdx_bone = pdx_data.PDXData(b)
                pdx_bone_list.append(pdx_bone)
                complete_bone_dict[pdx_bone.name] = pdx_bone.tx

            if imp_skel:
                IO_PDX_LOG.info("creating skeleton - {0} bones".format(len(pdx_bone_list)))
                progress("update", 1, "creating skeleton")
                joints = create_skeleton(pdx_bone_list)

        # then create all the meshes
        meshes = node.findall("mesh")
        if imp_mesh and meshes:
            created = []
            for mat_idx, m in enumerate(meshes):
                IO_PDX_LOG.info("creating mesh - {0}".format(mat_idx))
                progress("update", 1, "creating mesh")
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
                    IO_PDX_LOG.info("creating material - {0}".format(pdx_material.shader[0]))
                    progress("update", 1, "creating material")
                    create_material(pdx_material, mesh, os.path.split(meshpath)[0])

                # create the skin cluster
                if joints and pdx_skin:
                    IO_PDX_LOG.info("creating skinning data -")
                    progress("update", 1, "creating skinning data")
                    create_skin(pdx_skin, mesh, joints)

            if join_materials and len(created) > 1:
                name = created[0].name()
                try:
                    joined_mesh = pmc.polyUniteSkinned(*created, constructionHistory=False, mergeUVSets=1)[0]
                except RuntimeError:  # Maya raises this when using polyUniteSkinned on a group of unskinned meshes
                    joined_mesh = pmc.polyUnite(*created, constructionHistory=False, mergeUVSets=1)[0]
                pmc.rename(joined_mesh, name)

    # go through locators
    if imp_locs and locators:
        progress("update", 1, "creating locators")
        for i, loc in enumerate(locators):
            IO_PDX_LOG.info("creating locator {0}/{1} - {2}".format(i + 1, len(locators), loc.tag))
            pdx_locator = pdx_data.PDXData(loc)
            obj = create_locator(pdx_locator, complete_bone_dict)

    pmc.select(None)
    IO_PDX_LOG.info("import finished! ({0:.4f} sec)".format(time.time() - start))
    progress("finished")


@allow_debug_logging
def export_meshfile(meshpath, exp_mesh=True, exp_skel=True, exp_locs=True, exp_selected=False, **kwargs):
    # kwargs wrangling
    progress = kwargs.get("progress_fn", lambda *args, **kwargs: None)
    # export mesh(es) as blendshapes
    as_blendshape = kwargs.get("as_blendshape", False)
    split_by = ["id", "p", "uv"] if as_blendshape else None
    # full vertex split option
    split_verts = kwargs.get("split_verts", False)
    # vertex sorting options
    sort_verts = {"+": True, "~": None, "-": False}.get(kwargs.get("sort_verts", "+"))
    # with plain text file option
    plain_txt = kwargs.get("plain_txt", False)

    start = time.time()
    IO_PDX_LOG.info("exporting - {0}".format(meshpath))
    progress("show", 10, "Exporting")

    current_selection = pmc.selected()

    # create an XML structure to store the object hierarchy
    root_xml = Xml.Element("File")
    root_xml.set("pdxasset", [1, 0])

    # create root element for objects and populate object data
    object_xml = Xml.SubElement(root_xml, "object")

    if exp_mesh:
        # get all meshes using at least one PDX material in the scene
        maya_meshes = list_scene_pdx_meshes()
        # optionally intersect with selection
        if exp_selected:
            maya_meshes = [
                shape
                for shape in maya_meshes
                if pmc.listRelatives(shape, parent=True, type="transform")[0] in current_selection
            ]

        if len(maya_meshes) == 0:
            raise RuntimeError("Mesh export is selected, but found no meshes with PDX materials applied.")

        # sort meshes for export by index
        maya_meshes.sort(key=lambda mesh: get_mesh_index(mesh))

        for i, shape in enumerate(maya_meshes):
            # create parent element for node data, if exporting meshes
            obj_name = shape.name()

            IO_PDX_LOG.info("writing node {0}/{1} - {2}".format(i + 1, len(maya_meshes), obj_name))
            progress("update", 1, "writing node")
            objnode_xml = Xml.SubElement(object_xml, obj_name)

            # populate LOD attribute on object element
            lod_match = get_lod_level(obj_name)
            if lod_match is not None:
                IO_PDX_LOG.info("writing lod index - {0}".format(lod_match))
                objnode_xml.set("lod", [lod_match])

            # one shape can have multiple materials on a per meshface basis
            shading_groups = list(set(shape.connections(type="shadingEngine")))

            for mat_idx, group in enumerate(shading_groups):
                # this type of ObjectSet associates shaders with geometry
                shaders = group.surfaceShader.connections()
                # skip shading groups that are unconnected or not PDX materials
                if len(shaders) != 1 or not hasattr(shaders[0], PDX_SHADER):
                    continue
                maya_mat = shaders[0]

                # create parent element for this mesh (mesh here being geometry sharing a material, within one shape)
                IO_PDX_LOG.info("writing mesh - {0}".format(mat_idx))
                progress("update", 1, "writing mesh")
                meshnode_xml = Xml.SubElement(objnode_xml, "mesh")

                # check which faces are using this shading group
                # (groups are shared across shapes, so only select group members that are components of this shape)
                mesh = [meshface for meshface in group.members(flatten=True) if meshface.node() == shape][0]

                # get all necessary info about this set of faces and determine which unique verts they include
                mesh_info_dict, vert_ids = get_mesh_info(
                    mesh, split_criteria=split_by, split_all=split_verts, sort_vertices=sort_verts
                )
                # skip shading groups that are used on no faces
                if not (mesh_info_dict and vert_ids):
                    continue

                # populate mesh attributes
                for key in ["p", "n", "ta", "u0", "u1", "u2", "u3", "tri", "boundingsphere"]:
                    if key in mesh_info_dict and mesh_info_dict[key]:
                        meshnode_xml.set(key, mesh_info_dict[key])

                # create parent element for bounding box data
                aabbnode_xml = Xml.SubElement(meshnode_xml, "aabb")
                for key in ["min", "max"]:
                    if key in mesh_info_dict and mesh_info_dict[key]:
                        aabbnode_xml.set(key, mesh_info_dict[key])

                # create parent element for material data
                IO_PDX_LOG.info("writing material -")
                progress("update", 1, "writing material")
                materialnode_xml = Xml.SubElement(meshnode_xml, "material")
                # populate material attributes
                materialnode_xml.set("shader", [get_material_shader(maya_mat)])
                mat_texture_dict = get_material_textures(maya_mat)
                for slot, texture in mat_texture_dict.items():
                    materialnode_xml.set(slot, [os.path.split(texture)[1]])

                # create parent element for skin data, if the mesh is skinned
                skin_info_dict = get_mesh_skin_info(shape, vert_ids)
                if exp_skel and skin_info_dict:
                    IO_PDX_LOG.info("writing skinning data -")
                    progress("update", 1, "writing skinning data")
                    skinnode_xml = Xml.SubElement(meshnode_xml, "skin")
                    for key in ["bones", "ix", "w"]:
                        if key in skin_info_dict and skin_info_dict[key]:
                            skinnode_xml.set(key, skin_info_dict[key])

            bone_info_list = get_mesh_skeleton_info(shape)
            # create parent element for skeleton data, if the mesh is skinned
            if exp_skel and bone_info_list:
                IO_PDX_LOG.info("writing skeleton -")
                progress("update", 1, "writing skeleton")
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
        progress("update", 1, "writing node")
        objnode_xml = Xml.SubElement(object_xml, obj_name)

        maya_bones = [bone for bone in pmc.ls(type="joint")]
        # optionally intersect with selection
        if exp_selected:
            rig_bones = [bone for bone in maya_bones if bone in current_selection]

        rig_bones = get_skeleton_hierarchy(maya_bones)

        if len(rig_bones) == 0:
            raise RuntimeError("Skeleton only export is selected, but found no bones.")

        bone_info_list = get_bones_info(rig_bones)
        # create parent element for skeleton data
        if exp_skel and bone_info_list:
            IO_PDX_LOG.info("writing skeleton -")
            progress("update", 1, "writing skeleton")
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
        maya_locators = [t for t in pmc.ls(type="transform") if pmc.listRelatives(t, shapes=True, type="locator")]
        # optionally intersect with selection
        if exp_selected:
            maya_locators = [obj for obj in maya_locators if obj in current_selection]

        loc_info_list = get_locators_info(maya_locators)
        IO_PDX_LOG.info("writing locators -")
        progress("update", 1, "writing locators")

        # create sub-elements for each locator, populate locator attributes
        for loc_info_dict in loc_info_list:
            locnode_xml = Xml.SubElement(locator_xml, loc_info_dict["name"])
            for key in ["p", "q", "pa", "tx"]:
                if key in loc_info_dict and loc_info_dict[key]:
                    locnode_xml.set(key, loc_info_dict[key])

    # write the binary file from our XML structure
    IO_PDX_LOG.info("writing .mesh file -")
    pdx_data.write_meshfile(meshpath, root_xml)
    if plain_txt:
        IO_PDX_LOG.info("writing .txt file -")
        with open(str(pathlib.Path(meshpath).with_suffix(".txt")), "wt") as fp:
            fp.write(str(pdx_data.PDXData(root_xml)) + "\n")

    pmc.select(None)
    IO_PDX_LOG.info("export finished! ({0:.4f} sec)".format(time.time() - start))
    progress("finished")


@allow_debug_logging
def import_animfile(animpath, frame_start=1, **kwargs):
    progress = kwargs.get("progress_fn", lambda *args, **kwargs: None)

    start = time.time()
    IO_PDX_LOG.info("importing - {0}".format(animpath))
    progress("show", 10, "Importing")

    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(animpath)

    # find animation info and samples
    info = asset_elem.find("info")
    samples = asset_elem.find("samples")
    framecount = info.attrib["sa"][0]

    # set scene animation and playback settings
    fps = int(info.attrib["fps"][0])
    IO_PDX_LOG.info("setting playback speed - {0}".format(fps))
    set_animation_fps(fps)

    progress("update", 1, "setting playback speed")
    pmc.playbackOptions(edit=True, playbackSpeed=1.0)
    pmc.playbackOptions(edit=True, animationStartTime=0.0)

    IO_PDX_LOG.info("setting playback range - ({0},{1})".format(frame_start, (frame_start + framecount - 1)))
    progress("update", 1, "setting playback range")
    pmc.playbackOptions(edit=True, minTime=frame_start)
    pmc.playbackOptions(edit=True, maxTime=(frame_start + framecount - 1))
    pmc.currentTime(frame_start, edit=True)

    # check scene has all required bones, check scale uniformity
    IO_PDX_LOG.info("finding bones -")
    progress("update", 1, "finding bones")
    scale_length = set()
    bone_errors = []
    for bone in info:
        scale_length.add(len(bone.attrib["s"]))
        bone_name = clean_imported_name(bone.tag)
        try:
            matching_bones = pmc.ls(bone_name, type=pmc.nt.Joint, long=True)  # type: pmc.nodetypes.joint
            bone_joint = matching_bones[0]
        except IndexError:
            bone_errors.append(bone_name)
            IO_PDX_LOG.warning("failed to find bone - {0}".format(bone_name))
            progress("update", 1, "failed to find bone!")

    # break on missing bones
    if bone_errors:
        raise RuntimeError("Missing bones required for animation: {0}".format(bone_errors))

    # break on variable size scale vectors
    if len(scale_length) != 1:
        raise NotImplementedError("Mixed length scale vectors ({0}) are not supported".format(scale_length))
    # support both uniform ([x]) and non-uniform ([x,y,z]) scale data
    scale_length = scale_length.pop()
    scale_padding = 4 - scale_length
    IO_PDX_LOG.info("animation supports {0}uniform scale -".format("non-" if scale_length > 1 else ""))

    # clear any current pose before attempting to load the animation
    # TODO: clear existing anim curves from bones and restore bind pose

    # set the initial pose (includes un-keyframed bones)
    initial_pose = dict()
    IO_PDX_LOG.info("setting initial pose on bones - {0}".format(len(info)))
    for bone in info:
        bone_name = clean_imported_name(bone.tag)
        matching_bones = pmc.ls(bone_name, type=pmc.nt.Joint, long=True)  # type: pmc.nodetypes.joint
        bone_joint = matching_bones[0]

        # set initial transform and remove any joint orientation (this is baked into rotation values in the .anim file)
        if bone_joint:
            # compose transform parts
            _scale = MVector(*bone.attrib["s"] * scale_padding)
            _rotation = MQuaternion(*bone.attrib["q"])
            _translation = MVector(*bone.attrib["t"])

            bone_joint.setScale(_scale)
            bone_joint.setRotation(_rotation)
            bone_joint.setTranslation(_translation)

            # zero out joint orientation
            bone_joint.jointOrient.set(0.0, 0.0, 0.0)
            # apply transform
            # TODO: set initial pose keyframe (not all bones in this initial pose will be animated)
            bone_joint.setMatrix(swap_coord_space(bone_joint.getMatrix()))

            # record the initial pose
            initial_pose[bone_name] = bone_joint.getMatrix()

    # check which transform types are animated on each bone
    all_bone_keyframes = OrderedDict()
    for bone in info:
        bone_name = clean_imported_name(bone.tag)
        all_bone_keyframes[bone_name] = OrderedDict((sample_type, []) for sample_type in bone.attrib["sa"][0])

    # then traverse the samples data to store keys per bone
    s_idx, q_idx, t_idx = 0, 0, 0  # track offsets into samples data arrays
    s_len, q_len, t_len = scale_length, 4, 3  # track stride across samples data arrays
    for _ in range(0, framecount):
        for bone_name in all_bone_keyframes:
            bone_key_data = all_bone_keyframes[bone_name]
            if "s" in bone_key_data:
                frame_bone_scale = samples.attrib["s"][s_idx : s_idx + s_len] * scale_padding
                bone_key_data["s"].append(frame_bone_scale)
                s_idx += s_len
            if "q" in bone_key_data:
                frame_bone_quat = samples.attrib["q"][q_idx : q_idx + q_len]
                bone_key_data["q"].append(frame_bone_quat)
                q_idx += q_len
            if "t" in bone_key_data:
                frame_bone_trans = samples.attrib["t"][t_idx : t_idx + t_len]
                bone_key_data["t"].append(frame_bone_trans)
                t_idx += t_len

    for bone_name in all_bone_keyframes:
        bone_keys = all_bone_keyframes[bone_name]
        # check bone has keyframe values
        if bone_keys.values():
            IO_PDX_LOG.info("setting {0} keyframes on bone - {1}".format(list(bone_keys.keys()), bone_name))
            non_uni_keys = [i for i, data in enumerate(bone_keys.get("s", [])) if not len(set(data)) == 1]
            if any(non_uni_keys):
                IO_PDX_LOG.debug("Bone: {0} has non-uniform scale keyframes at: {1}".format(bone_name, non_uni_keys))
            progress("update", 1, "setting keyframes on bone")
            bone_long_name = pmc.ls(bone_name, type=pmc.nt.Joint, long=True)[0].name()
            create_anim_keys(bone_long_name, bone_keys, frame_start)

    pmc.select(None)
    IO_PDX_LOG.info("import finished! ({0:.4f} sec)".format(time.time() - start))
    progress("finished")


@allow_debug_logging
def export_animfile(animpath, frame_start=1, frame_end=10, **kwargs):
    # kwargs wrangling
    progress = kwargs.get("progress_fn", lambda *args, **kwargs: None)
    # allow non-uniform scale
    uniform_scale = kwargs.get("uniform_scale", True)
    # with plain text file option
    plain_txt = kwargs.get("plain_txt", False)

    start = time.time()
    IO_PDX_LOG.info("exporting - {0}".format(animpath))
    progress("show", 10, "Exporting")

    curr_frame = pmc.currentTime(query=True)
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
    IO_PDX_LOG.info("gathering animation info -")
    fps = get_animation_fps()  # pmc.mel.currentTimeUnitToFPS()
    info_xml.set("fps", [float(fps)])

    frame_samples = (frame_end + 1) - frame_start
    info_xml.set("sa", [frame_samples])

    # find the scene root bone with animation property (assume this is unique)
    root_bone = None

    # pdx_scene_rootbones = [bone for bone in list_scene_rootbones() if hasattr(bone, PDX_ANIMATION)]
    # TODO : finsh this, just use selected bone for now
    root_bone = pmc.selected(type="joint")
    if not root_bone:
        raise RuntimeError("Please select a specific root bone before exporting.")

    # populate bone data, assume that the skeleton to be exported starts at the scene root bone
    export_bones = get_skeleton_hierarchy(root_bone)
    info_xml.set("j", [len(export_bones)])

    # parse the scene animation data
    all_bone_keyframes = get_scene_animdata(export_bones, frame_start, frame_end)

    # for each bone, write sample types and describe the initial offset from parent
    IO_PDX_LOG.info("gathering initial bone transforms -")
    progress("update", 1, "gathering initial bone transforms")
    pmc.currentTime(frame_start, edit=True)
    for bone in export_bones:
        bone_name = bone.name()
        bone_xml = Xml.SubElement(info_xml, bone_name)

        # check sample types
        sample_types = ""
        for attr in ["t", "q", "s"]:
            if attr in all_bone_keyframes[bone_name]:
                sample_types += attr
        bone_xml.set("sa", [sample_types])

        _translation = swap_coord_space(bone.getTranslation())
        # bone rotation must be pre-multiplied by joint orientation
        _rotation = swap_coord_space(bone.getRotation(quaternion=True) * bone.getOrientation())
        _scale = list(bone.getScale())
        # animation may support either uniform / non-uniform scale
        if uniform_scale:
            _scale = [_scale[0]]

        # set initial attributes
        bone_xml.set("t", list(_translation))
        bone_xml.set("q", list(_rotation))
        bone_xml.set("s", list(_scale))

    # create root element for animation keyframe data
    samples_xml = Xml.SubElement(root_xml, "samples")
    IO_PDX_LOG.info("gathering keyframes -")
    progress("update", 1, "gathering keyframes")
    for bone_name in all_bone_keyframes:
        bone_keys = all_bone_keyframes[bone_name]
        if bone_keys:
            IO_PDX_LOG.info("gathering {0} keyframes for bone - {1}".format(list(bone_keys.keys()), bone_name))

    # pack all scene animation data into flat keyframe lists
    t_packed, q_packed, s_packed = [], [], []
    for i in range(frame_samples):
        for bone in all_bone_keyframes:
            bone_key_data = all_bone_keyframes[bone]
            if "t" in bone_key_data:
                t_packed.extend(bone_key_data["t"].pop(0))
            if "q" in bone_key_data:
                q_packed.extend(bone_key_data["q"].pop(0))
            if "s" in bone_key_data:
                # animation may support either uniform / non-uniform scale
                if uniform_scale:
                    s_packed.append(bone_key_data["s"].pop(0)[0])
                else:
                    s_packed.extend(bone_key_data["s"].pop(0))

    if t_packed:
        samples_xml.set("t", t_packed)
    if q_packed:
        samples_xml.set("q", q_packed)
    if s_packed:
        samples_xml.set("s", s_packed)

    # write the binary file from our XML structure
    IO_PDX_LOG.info("writing .anim file")
    pdx_data.write_animfile(animpath, root_xml)
    if plain_txt:
        IO_PDX_LOG.info("writing .txt file -")
        with open(str(pathlib.Path(animpath).with_suffix(".txt")), "wt") as fp:
            fp.write(str(pdx_data.PDXData(root_xml)) + "\n")

    pmc.currentTime(curr_frame, edit=True)

    pmc.select(None)
    IO_PDX_LOG.info("export finished! ({0:.4f} sec)".format(time.time() - start))
    progress("finished")
