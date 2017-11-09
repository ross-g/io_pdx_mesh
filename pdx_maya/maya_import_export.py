"""
    Paradox asset files, Maya import/export.

    As Mayas 3D space is (Y-up, right-handed) and the Clausewitz engine seems to be (Y-up, left-handed) we have to
    mirror all positions, normals etc along the Z axis and flip texture coordinates in V.
    
    author : ross-g
"""

import os
from collections import OrderedDict
try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

import maya.cmds as cmds
import pymel.core as pmc
import pymel.core.datatypes as pmdt
import maya.OpenMaya as OpenMaya    # Maya Python API 1.0
import maya.OpenMayaAnim as OpenMayaAnim    # Maya Python API 1.0

from io_pdx_mesh import pdx_data


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

PDX_SHADER = 'shader'
PDX_ANIMATION = 'animation'
PDX_IGNOREJOINT = 'pdxIgnoreJoint'

PDX_DECIMALPTS = 2


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


def list_scene_materials():
    return [mat for mat in pmc.ls(materials=True)]


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
        except:
            print "[io_pdx_mesh] node '{}' has no displayLocalAxis property".format(node)


def set_ignore_joints(state):
    joint_list = pmc.selected(type='joint')

    for joint in joint_list:
        try:
            getattr(joint, PDX_IGNOREJOINT).set(state)
        except:
            pmc.addAttr(joint, longName=PDX_IGNOREJOINT, attributeType='bool')
            getattr(joint, PDX_IGNOREJOINT).set(state)


def check_mesh_material(maya_mesh):
    result = False

    shadingengines = list(set(pmc.listConnections(maya_mesh, type='shadingEngine')))
    for sg in shadingengines:
        material = pmc.listConnections(sg.surfaceShader)[0]
        result = result or hasattr(material, PDX_SHADER)    # needs at least one of it's materials to be a PDX material

    return result


def get_mesh_skin(maya_mesh):
    skinclusters = list(set(pmc.listConnections(maya_mesh, type='skinCluster')))

    return skinclusters


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


def get_mesh_info(maya_mesh, merge_vertices=False):
    """
        Returns a dictionary of mesh information neccessary to export.
        By default this does NOT merge vertices across triangles, so each tri-vert is exported separately!
    """
    # ensure we're using MeshFace type
    if type(maya_mesh) == pmc.general.MeshFace:
        meshfaces = maya_mesh
        mesh = meshfaces.node()
    elif type(maya_mesh) == pmc.nt.Mesh:
        meshfaces = maya_mesh.faces
        mesh = maya_mesh
    else:
        raise NotImplementedError("Unsupported mesh type encountered. {}".format(type(maya_mesh)))

    # build a dictionary of mesh information for the exporter
    mesh_dict = dict(
        p=[],
        n=[],
        ta=[],
        u0=[],      # TODO: multiple UV set support
        tri=[]
    )
    # track processed verts, key: mesh_dict array index, value: mesh vert id
    vert_dict = {}

    # cache some mesh info
    vertices = mesh.getPoints(space='world')        # list of vertices positions
    normals = mesh.getNormals(space='world')        # list of vectors for each vertex per face
    normalIds = mesh.getNormalIds()
    triangles = mesh.getTriangles()
    uv_SetNames = mesh.getUVSetNames()
    _u, _v = mesh.getUVs(uvSet=uv_SetNames[0])
    uv_Coords = zip(_u, _v)
    trangents = mesh.getTangents(space='world', uvSet=uv_SetNames[0])

    for face in meshfaces:
        # vertices making this face
        face_vert_ids = face.getVertices()

        # number of triangles making this face
        num_triangles = triangles[0][face.index()]

        # store data for each tri of each face
        for i in xrange(0, num_triangles):
            # vertices making this triangle
            tri_vert_ids = mesh.getPolygonTriangleVertices(face.index(), i)

            # loop over tri verts
            for vert_id in tri_vert_ids:
                # local vertex index
                _local_id = face_vert_ids.index(vert_id)

                # normal
                vert_norm_ids = set(mesh.vtx[vert_id].getNormalIndices())
                vert_norm_id = face.normalIndex(_local_id)
                _normal = pmc.util.round(normals[vert_norm_id], PDX_DECIMALPTS)
                # FIXME: normal vector here must be mirrored in Z to go back to game space
                mesh_dict['n'].extend([_normal[0], _normal[1], -_normal[2]])

                # uv
                vert_uv_ids = set(mesh.vtx[vert_id].getUVIndices())
                vert_uv_id = face.getUVIndex(_local_id, uv_SetNames[0])
                _uvcoords = pmc.util.round(uv_Coords[vert_uv_id], PDX_DECIMALPTS)
                # FIXME: UV v-coord here must be flipped in V
                mesh_dict['u0'].extend([_uvcoords[0], 1 - _uvcoords[1]])

                # tangent
                vert_tangent_id = mesh.getTangentId(face.index(), vert_id)
                _tangent = pmc.util.round(trangents[vert_tangent_id], PDX_DECIMALPTS)
                # FIXME: tangent basis here must be mirrored in Z
                mesh_dict['ta'].extend([_tangent[0], _tangent[1], -_tangent[2], 1.0])

                # position
                _position = pmc.util.round(vertices[vert_id], PDX_DECIMALPTS)   # round position info
                # FIXME: vertex position here must be mirrored in Z
                mesh_dict['p'].extend([_position[0], _position[1], -_position[2]])

                # flag this vert as processed
                vert_dict[str(len(mesh_dict['p']) / 3 - 1)] = vert_id

            # faces
            face_verts = [tri_vert_ids[0], tri_vert_ids[2], tri_vert_ids[1]]    # re-order face for left handedness here
            mesh_dict['tri'].extend([vert_dict[v] for v in face_verts])

            print face.index(), i
            print vert_dict
            print face_verts
            print mesh_dict['tri']

    return mesh_dict


def mirror_in_z(node):
    """
        Mirrors a point across the XY plane at Z = 0.
    """
    # get the current transform as quaternion rotation and translation
    m_XformMat = OpenMaya.MTransformationMatrix(node.matrix.get())
    quat = m_XformMat.rotation()
    tran = m_XformMat.translation(OpenMaya.MSpace.kTransform)

    q = [quat[0], quat[1], -quat[2], -quat[3]]      # negate Z axis and angle components of quaternion
    t = [tran.x, tran.y, -tran.z]                   # negate Z axis component of translation

    # set new transformation
    obj = get_MObject(node.name())
    mFn_Xform = OpenMaya.MFnTransform(obj)

    mFn_Xform.setRotationQuaternion(*q)
    vector = OpenMaya.MVector(*t)
    mFn_Xform.setTranslation(vector, OpenMaya.MSpace.kTransform)


""" ====================================================================================================================
    Functions.
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


def create_shader(shader_name, PDX_material, texture_dir):
    new_shader = pmc.shadingNode('phong', asShader=True, name=shader_name)
    new_shadinggroup = pmc.sets(renderable=True, noSurfaceShader=True, empty=True, name='{}_SG'.format(shader_name))
    pmc.connectAttr(new_shader.outColor, new_shadinggroup.surfaceShader)

    # TODO: should this be an enum attribute type?
    # would need to parse the possible engine/material combinations from clausewitz.json
    pmc.addAttr(longName=PDX_SHADER, dataType='string')
    getattr(new_shader, PDX_SHADER).set(PDX_material.shader)

    if getattr(PDX_material, 'diff', None):
        texture_path = os.path.join(texture_dir, PDX_material.diff[0])
        new_file, _ = create_filetexture(texture_path)
        pmc.connectAttr(new_file.outColor, new_shader.color)

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
    shader, s_group = create_shader(shader_name, PDX_material, texture_path)

    pmc.select(mesh)
    mesh.backfaceCulling.set(1)
    pmc.hyperShade(assign=s_group)


def create_locator(PDX_locator):
    # create locator
    new_loc = pmc.spaceLocator()
    pmc.select(new_loc)
    pmc.rename(new_loc, PDX_locator.name)

    # parent locator
    parent = getattr(PDX_locator, 'pa', None)
    if parent is not None:
        parent_bone = pmc.ls(parent[0], type='joint')
        if parent_bone:
            pmc.parent(new_loc, parent_bone[0])

    # set attributes
    obj = get_MObject(new_loc.name())
    mFn_Xform = OpenMaya.MFnTransform(obj)

    # rotation
    mFn_Xform.setRotationQuaternion(PDX_locator.q[0], PDX_locator.q[1], PDX_locator.q[2], PDX_locator.q[3])
    # translation
    vector = OpenMaya.MVector(PDX_locator.p[0], PDX_locator.p[1], PDX_locator.p[2])
    space = OpenMaya.MSpace.kTransform
    mFn_Xform.setTranslation(vector, space)

    # mirror in Z
    mirror_in_z(new_loc)


def create_skeleton(PDX_bone_list):
    # keep track of bones as we create them
    bone_list = [None for _ in range(0, len(PDX_bone_list))]

    pmc.select(clear=True)
    for bone in PDX_bone_list:
        index = bone.ix[0]
        transform = bone.tx
        parent = getattr(bone, 'pa', None)

        # determine bone name
        name = bone.name.split(':')[-1]
        namespace = bone.name.split(':')[:-1]  # TODO: setup namespaces properly

        # ensure bone name is unique
        # Maya allows non-unique transform names (on leaf nodes) and handles them internally with | separators
        unique_name = name.replace('|', '_')
        if pmc.ls(unique_name, type='joint'):
            bone_list[index] = pmc.PyNode(unique_name)
            continue    # bone already exists, likely the skeleton is already built, so collect and return joints

        # create joint
        new_bone = pmc.joint()
        pmc.select(new_bone)
        pmc.rename(new_bone, unique_name)
        pmc.parent(new_bone, world=True)
        bone_list[index] = new_bone
        new_bone.radius.set(0.25)

        # set transform
        mat = pmdt.Matrix(
            transform[0], transform[1], transform[2], 0.0,
            transform[3], transform[4], transform[5], 0.0,
            transform[6], transform[7], transform[8], 0.0,
            transform[9], transform[10], transform[11], 1.0
        )
        pmc.xform(matrix=mat.inverse())     # set transform to inverse of matrix in world-space
        pmc.select(clear=True)

        # mirror in Z
        mirror_in_z(new_bone)

        # connect to parent
        if parent is not None:
            parent_bone = bone_list[parent[0]]
            pmc.connectJoint(new_bone, parent_bone, parentMode=True)

    return bone_list


def create_skin(PDX_skin, mesh, skeleton, max_infs=None):
    if max_infs is None:
        max_infs = 4

    # create dictionary of skinning info per vertex
    skin_dict = dict()

    num_infs = PDX_skin.bones[0]
    for vtx in xrange(0, len(PDX_skin.ix)/max_infs):
        skin_dict[vtx] = dict(joints=[], weights=[])

    # gather joint index and weighting that each vertex is skinned to
    for vtx, j in enumerate(xrange(0, len(PDX_skin.ix), max_infs)):
        skin_dict[vtx]['joints'] = PDX_skin.ix[j:j+num_infs]
        skin_dict[vtx]['weights'] = PDX_skin.w[j:j+num_infs]

    # select mesh and joints
    pmc.select(skeleton, mesh)

    # create skin cluster and then prune all default skin weights
    skin_cluster = pmc.skinCluster(bindMethod=0, skinMethod=0, normalizeWeights=0,
                                   maximumInfluences=max_infs, obeyMaxInfluences=True)
    pmc.skinPercent(skin_cluster, mesh, normalize=False, pruneWeights=100)

    # # set skin weights from our dict
    # FIXME: this worked for the AI portrait with single inf skins etc, but breaks skinning on the ship (oars etc)
    # for vtx in xrange(len(skin_dict.keys())):
    #     joints = skin_dict[vtx]['joints']
    #     weights = skin_dict[vtx]['weights']
    #
    #     for jnt, wt in zip(joints, weights):
    #         # we shouldn't get unused influences, but just in case ignore joint index -1
    #         if jnt != -1:
    #             pmc.setAttr('{}.weightList[{}].weights[{}]'.format(skin_cluster, vtx, jnt), wt)

    # then set skin weights
    for v in xrange(len(skin_dict.keys())):
        joints = [skeleton[j] for j in skin_dict[v]['joints']]
        weights = skin_dict[v]['weights']
        # normalise joint weights
        try:
            norm_weights = [float(w)/sum(weights) for w in weights]
        except:
            norm_weights = weights
        # strip zero weight entries
        joint_weights = [(j, w) for j, w in zip(joints, norm_weights) if w != 0.0]

        pmc.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh.name(), v),
                        transformValue=joint_weights, normalize=True)

    # turn on skin weights normalization again
    pmc.setAttr('{}.normalizeWeights'.format(skin_cluster), True)


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

    # create the data structures for mesh and transform
    mFn_Mesh = OpenMaya.MFnMesh()
    m_DagMod = OpenMaya.MDagModifier()
    new_object = m_DagMod.createNode('transform')

    # build the following arguments for the MFnMesh.create() function
    # numVertices, numPolygons, vertexArray, polygonCounts, polygonConnects, uArray, vArray, new_object

    # vertices
    numVertices = 0
    vertexArray = OpenMaya.MFloatPointArray()   # array of points
    for i in xrange(0, len(verts), 3):
        v = OpenMaya.MFloatPoint(verts[i], verts[i+1], verts[i+2])
        vertexArray.append(v)
        numVertices += 1

    # faces
    numPolygons = len(tris) / 3
    polygonCounts = OpenMaya.MIntArray()    # count of vertices per poly
    for i in range(0, numPolygons):
        polygonCounts.append(3)
    # OpenMaya.MScriptUtil.createIntArrayFromList([3]*numPolygons, polygonCounts)

    # vert connections
    polygonConnects = OpenMaya.MIntArray()
    for item in tris:
        polygonConnects.append(item)
    # OpenMaya.MScriptUtil.createIntArrayFromList(tris, polygonConnects)

    # default UVs
    uArray = OpenMaya.MFloatArray()
    vArray = OpenMaya.MFloatArray()
    if uv_Ch.get(0):
        uv_data = uv_Ch[0]
        for i in xrange(0, len(uv_data), 2):
            uArray.append(uv_data[i])
            vArray.append(1 - uv_data[i+1])        # flip the UV coords in V!

    """ ================================================================================================================
        create the new mesh """
    mFn_Mesh.create(numVertices, numPolygons, vertexArray, polygonCounts, polygonConnects, uArray, vArray, new_object)
    mFn_Mesh.setName(tmp_mesh_name)
    m_DagMod.doIt()     # sets up the transform parent to the mesh shape

    # PyNode for the mesh
    new_mesh = pmc.PyNode(tmp_mesh_name)
    new_transform = pmc.listRelatives(new_mesh, type='transform', parent=True)[0]

    # name and namespace
    if name is not None:
        mesh_name = name.split(':')[-1]
        namespace = name.split(':')[:-1]      # TODO: setup namespaces properly

        pmc.rename(new_mesh, mesh_name)

    # apply the vertex normal data
    if norms:
        normalsIn = OpenMaya.MVectorArray()     # array of vectors
        for i in xrange(0, len(norms), 3):
            n = OpenMaya.MVector(norms[i], norms[i+1], norms[i+2])
            normalsIn.append(n)
        vertexList = OpenMaya.MIntArray()       # matches normal to vert by index
        for i in range(0, numVertices):
            vertexList.append(i)
        mFn_Mesh.setVertexNormals(normalsIn, vertexList)

    # apply the default UV data
    if uv_Ch.get(0):
        uvCounts = OpenMaya.MIntArray()
        for i in range(0, numPolygons):
            uvCounts.append(3)
        # OpenMaya.MScriptUtil.createIntArrayFromList(verts_per_poly, uvCounts)
        uvIds = OpenMaya.MIntArray()
        for item in tris:
            uvIds.append(item)
        # OpenMaya.MScriptUtil.createIntArrayFromList(raw_tris, uvIds)
        # note bulk assignment via .assignUVs only works to the default UV set!
        mFn_Mesh.assignUVs(uvCounts, uvIds, 'map1')

    # set other UV channels
    for idx in uv_Ch:
        # ignore Ch 0 as we have already set this
        if idx != 0:
            uv_data = uv_Ch[idx]
            uvSetName = 'map' + str(idx+1)

            uArray = OpenMaya.MFloatArray()
            vArray = OpenMaya.MFloatArray()
            for i in xrange(0, len(uv_data), 2):
                uArray.append(uv_data[i])
                vArray.append(1 - uv_data[i+1])        # flip the UV coords in V!

            mFn_Mesh.createUVSetWithName(uvSetName)
            mFn_Mesh.setUVs(uArray, vArray, uvSetName)

    # mirror in Z
    # we need to mirror the mesh components here, not just the transform
    z_mirror = pmdt.Matrix(
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, -1, 0,
        0, 0, 0, 1
    )
    pmc.select(new_transform)
    new_transform.setMatrix(z_mirror)
    # freeze transform
    pmc.makeIdentity(apply=True, jo=False, n=0, pn=True, r=False, s=True, t=False)

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
    mFn_AnimCurve.setName('{}_{}'.format(OpenMaya.MFnDependencyNode(joint).name(), attr))

    # check for and remove any existing connections
    if in_plug.isConnected():
        mplugs = OpenMaya.MPlugArray()
        in_plug.connectedTo(mplugs, True, False)
        for i in range(0, mplugs.length()):
            m_DGMod = OpenMaya.MDGModifier()
            m_DGMod.deleteNode(mplugs[i].node())
    # connect the new animation curve to the attribute on the joint
    connect_nodeplugs(anim_curve, 'output', joint, attr)

    return anim_curve, mFn_AnimCurve


def create_anim_keys(joint, key_dict, timestart):
    jnt_obj = get_MObject(joint.name())

    # calculate start and end frames
    timestart = int(timestart)
    timeend = timestart + len(max(key_dict.values(), key=len))

    # create a time array
    time_array = OpenMaya.MTimeArray()
    for t in xrange(timestart, timeend):
        time_array.append(OpenMaya.MTime(t, OpenMaya.MTime.uiUnit()))

    # define anim curve tangent
    k_Tangent = OpenMayaAnim.MFnAnimCurve.kTangentLinear

    if 's' in key_dict:     # scale data
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
            # mirror in Z
            x_scale_data.append(scale_data[0])
            y_scale_data.append(scale_data[0])
            z_scale_data.append(scale_data[0])

        # add keys to the new curves
        for attrib, data_array in zip(animated_attrs, [x_scale_data, y_scale_data, z_scale_data]):
            mFn_AnimCurve = animated_attrs[attrib]
            mFn_AnimCurve.addKeys(time_array, data_array, k_Tangent, k_Tangent)

    if 'q' in key_dict:     # quaternion data
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
            # mirror in Z
            q = [quat_data[0], quat_data[1], -quat_data[2], -quat_data[3]]
            # convert from quaternion to euler, this gives values in radians (which Maya uses internally)
            euler_data = OpenMaya.MQuaternion(*q).asEulerRotation()
            x_rot_data.append(euler_data.x)
            y_rot_data.append(euler_data.y)
            z_rot_data.append(euler_data.z)

        # add keys to the new curves
        for attrib, data_array in zip(animated_attrs, [x_rot_data, y_rot_data, z_rot_data]):
            mFn_AnimCurve = animated_attrs[attrib]
            mFn_AnimCurve.addKeys(time_array, data_array, k_Tangent, k_Tangent)

    if 't' in key_dict:     # translation data
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
            # mirror in Z
            t = [trans_data[0], trans_data[1], -trans_data[2]]
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


def import_meshfile(meshpath, imp_mesh=True, imp_skel=True, imp_locs=True):
    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(meshpath)

    # find shapes and locators
    shapes = asset_elem.find('object')
    locators = asset_elem.find('locator')

    # go through shapes
    for node in shapes:
        print "[io_pdx_mesh] creating node - {}".format(node.tag)

        # create the skeleton first, so we can skin the mesh to it
        joints = None
        skeleton = node.find('skeleton')
        if imp_skel and skeleton:
            print "[io_pdx_mesh] creating skeleton -"
            pdx_bone_list = list()
            for b in skeleton:
                pdx_bone = pdx_data.PDXData(b)
                pdx_bone_list.append(pdx_bone)

            joints = create_skeleton(pdx_bone_list)

        # then create all the meshes
        meshes = node.findall('mesh')
        if imp_mesh:
            pdx_mesh_list = list()
            for m in meshes:
                print "[io_pdx_mesh] creating mesh -"
                pdx_mesh = pdx_data.PDXData(m)
                pdx_material = getattr(pdx_mesh, 'material', None)
                pdx_skin = getattr(pdx_mesh, 'skin', None)

                # create the geometry
                mesh = create_mesh(pdx_mesh, name=node.tag)
                pdx_mesh_list.append(mesh)

                # create the material
                if pdx_material:
                    print "[io_pdx_mesh] creating material -"
                    create_material(pdx_material, mesh, os.path.split(meshpath)[0])

                # create the skin cluster
                if joints and pdx_skin:
                    print "[io_pdx_mesh] creating skinning data -"
                    create_skin(pdx_skin, mesh, joints)

    # go through locators
    if imp_locs:
        print "[io_pdx_mesh] creating locators -"
        for loc in locators:
            pdx_locator = pdx_data.PDXData(loc)
            create_locator(pdx_locator)

    pmc.select(None)
    print "[io_pdx_mesh] finished!"


def export_meshfile(meshpath):
    # create an XML structure to store the object hierarchy
    root_xml = Xml.Element('File')
    root_xml.set('pdxasset', [1, 0])

    # create root elements for objects and locators
    object_xml = Xml.SubElement(root_xml, 'object')
    locator_xml = Xml.SubElement(root_xml, 'locator')

    # populate object data
    maya_meshes = [mesh for mesh in pmc.ls(shapes=True) if type(mesh) == pmc.nt.Mesh and check_mesh_material(mesh)]
    for shape in maya_meshes:
        shapenode_xml = Xml.SubElement(object_xml, shape.name())
        
        # one shape can have multiple materials on a per meshface basis
        shading_groups = list(set(shape.connections(type='shadingEngine')))

        for group in shading_groups:     # this type of object set associates shaders with geometry
            # create parent element for this mesh
            meshnode_xml = Xml.SubElement(shapenode_xml, 'mesh')

            # check which faces are using this material
            mesh = group.members(flatten=True)[0]
            mesh_info_dict = get_mesh_info(mesh)

            # populate mesh attributes
            for key in ['p', 'n', 'ta', 'u0', 'tri']:
                if key in mesh_info_dict and len(mesh_info_dict[key]) != 0:
                    meshnode_xml.set(key, mesh_info_dict[key])

            # create parent element for bounding box data
            aabbnode_xml = Xml.SubElement(meshnode_xml, 'aabb')
            aabbnode_xml.set('min', [])
            aabbnode_xml.set('max', [])

            # create parent element for material data
            materialnode_xml = Xml.SubElement(meshnode_xml, 'material')
            maya_mat = group.surfaceShader.connections()[0]
            # populate material attributes
            materialnode_xml.set('shader', [getattr(maya_mat, PDX_SHADER).get()])
            mat_texture_dict = get_material_textures(maya_mat)
            for slot, texture in mat_texture_dict.iteritems():
                materialnode_xml.set(slot, [os.path.split(texture)[1]])

            # create parent element for skin data if the mesh is skinned
            if get_mesh_skin(shape):
                skinnode_xml = Xml.SubElement(meshnode_xml, 'skin')

    # populate locator data
    maya_locators = [pmc.listRelatives(loc, type='transform', parent=True)[0] for loc in pmc.ls(type=pmc.nt.Locator)]
    for loc in maya_locators:
        locnode_xml = Xml.SubElement(locator_xml, loc.name())
        # FIXME: the transform here must be mirrored in Z to go back to game space
        locnode_xml.set('p', [p for p in loc.getTranslation()])
        locnode_xml.set('q', [q for q in loc.getRotation(quaternion=True)])
        if loc.getParent():
            locnode_xml.set('pa', [loc.getParent().name()])

    # write the binary file from our XML structure
    pdx_data.write_meshfile(meshpath, root_xml)


def import_animfile(animpath, timestart=1.0):
    # read the file into an XML structure
    asset_elem = pdx_data.read_meshfile(animpath)

    # find animation info and samples
    info = asset_elem.find('info')
    samples = asset_elem.find('samples')
    framecount = info.attrib['sa'][0]

    # set scene animation and playback settings
    fps = info.attrib['fps'][0]
    try:
        pmc.currentUnit(time=('{}fps'.format(fps)))
    except RuntimeError:
        fps = int(fps)
        if fps == 15:
            pmc.currentUnit(time='game')
        elif fps == 30:
            pmc.currentUnit(time='ntsc')
        else:
            raise NotImplementedError("Unsupported animation speed. {}".format(fps))
    print "[io_pdx_mesh] setting playback speed - {}".format(fps)
    pmc.playbackOptions(e=True, playbackSpeed=1.0)
    pmc.playbackOptions(e=True, animationStartTime=0.0)
    pmc.playbackOptions(e=True, minTime=timestart)
    pmc.playbackOptions(e=True, maxTime=(timestart+framecount))
    print "[io_pdx_mesh] setting playback range - ({},{})".format(timestart,(timestart+framecount))
    pmc.currentTime(0, edit=True)

    # find bones being animated in the scene
    bone_errors = []
    print "[io_pdx_mesh] finding bones -"
    for bone in info:
        bone_joint = None
        try:
            bone_joint = pmc.PyNode(bone.tag)
        except pmc.MayaObjectError:
            bone_errors.append(bone.tag)
            print "[io_pdx_mesh] failed to find bone {}".format(bone.tag)

        # set initial transform and remove any joint orientation (this is baked into rotation values in the .anim file)
        if bone_joint:
            bone_joint.setScale(
                [bone.attrib['s'][0], bone.attrib['s'][0], bone.attrib['s'][0]]
            )
            bone_joint.setRotation(
                # mirror in Z
                [bone.attrib['q'][0], bone.attrib['q'][1], -bone.attrib['q'][2], -bone.attrib['q'][3]]
            )
            bone_joint.setTranslation(
                # mirror in Z
                [bone.attrib['t'][0], bone.attrib['t'][1], -bone.attrib['t'][2]]
            )
            bone_joint.jointOrient.set(0.0, 0.0, 0.0)

    # break on bone errors
    if bone_errors:
        raise RuntimeError("Missing bones required for animation:\n{}".format(bone_errors))

    # check which transform types are animated on each bone
    all_bone_keyframes = OrderedDict()
    for bone in info:
        bone_name = bone.tag
        key_data = dict()
        all_bone_keyframes[bone_name] = key_data

        for sample_type in bone.attrib['sa'][0]:
            key_data[sample_type] = []

    # then traverse the samples data to store keys per bone
    s_index, q_index, t_index = 0, 0, 0
    for f in range(0, framecount):
        for i, bone_name in enumerate(all_bone_keyframes):
            bone_key_data = all_bone_keyframes[bone_name]

            if 's' in bone_key_data:
                bone_key_data['s'].append(samples.attrib['s'][s_index:s_index+1])
                s_index += 1
            if 'q' in bone_key_data:
                bone_key_data['q'].append(samples.attrib['q'][q_index:q_index+4])
                q_index += 4
            if 't' in bone_key_data:
                bone_key_data['t'].append(samples.attrib['t'][t_index:t_index+3])
                t_index += 3

    for bone_name in all_bone_keyframes:
        keys = all_bone_keyframes[bone_name]
        # check bone has keyframe values
        if keys.values():
            create_anim_keys(pmc.PyNode(bone_name), keys, timestart)

    pmc.select(None)
    print "[io_pdx_mesh] finished!"
