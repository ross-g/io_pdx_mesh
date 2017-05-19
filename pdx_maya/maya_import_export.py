"""
    Paradox asset files, Maya import/export.
    
    author : ross-g
"""

import os
try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

import maya.cmds as cmds
import pymel.core as pmc
import pymel.core.datatypes as pmdt
import maya.OpenMaya as OpenMaya    # Maya Python API 1.0

from io_pdx_mesh import pdx_data


""" ================================================================================================
    Variables.
====================================================================================================
"""

PDX_SHADER = 'shader'
PDX_IGNOREJOINT = 'pdxIgnoreJoint'


""" ================================================================================================
    Functions.
====================================================================================================
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


def list_scene_materials():
    return [mat for mat in pmc.ls(materials=True)]


def create_shader(shader_name, PDX_material, texture_dir):
    new_shader = pmc.shadingNode('phong', asShader=True, name=shader_name)
    new_shadinggroup = pmc.sets(renderable=True, noSurfaceShader=True, empty=True, name='{}_SG'.format(shader_name))
    pmc.connectAttr(new_shader.outColor, new_shadinggroup.surfaceShader)

    # TODO: should this be an enum attribute type?
    # would need to parse the possible engine/material combinations from clausewitz.json
    pmc.addAttr(longName=PDX_SHADER, dataType='string')
    new_shader.shader.set(PDX_material.shader)

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


def set_local_axis_display(state, object_list=None):
    if object_list is None:
        object_list = [pmc.listRelatives(loc, parent=True)[0] for loc in pmc.ls(type='locator')]

    for obj in object_list:
        obj.displayLocalAxis.set(state)


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
    obj = OpenMaya.MObject()
    selList = OpenMaya.MSelectionList()
    selList.add(new_loc.name())
    selList.getDependNode(0, obj)

    m_FnXform = OpenMaya.MFnTransform(obj)
    # translation
    vector = OpenMaya.MVector(PDX_locator.p[0], PDX_locator.p[1], PDX_locator.p[2])
    space = OpenMaya.MSpace.kTransform
    m_FnXform.setTranslation(vector, space)
    # rotation
    m_FnXform.setRotationQuaternion(PDX_locator.q[0], PDX_locator.q[1], PDX_locator.q[2], PDX_locator.q[3])


def set_ignore_joints(state):
    joint_list = pmc.selected(type='joint')

    for joint in joint_list:
        try:
            joint.pdxIgnoreJoint.set(state)
        except:
            pmc.addAttr(joint, longName=PDX_IGNOREJOINT, attributeType='bool')
            joint.pdxIgnoreJoint.set(state)


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
        new_bone.radius.set(0.5)
        
        # set transform
        mat = pmdt.Matrix(
            transform[0], transform[1], transform[2], 0.0,
            transform[3], transform[4], transform[5], 0.0,
            transform[6], transform[7], transform[8], 0.0,
            transform[9], transform[10], transform[11], 1.0
        )
        pmc.xform(matrix=mat.inverse())   # set transform to inverse of matrix in world-space
        pmc.select(clear=True)
        
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
    verts = PDX_mesh.p      # flat list of co-ordinates, verts[:2] = vtx[0]

    # normals
    norms = None
    if hasattr(PDX_mesh, 'n'):
        norms = PDX_mesh.n      # flat list of co-ordinates, norms[:2] = nrm[0]

    # triangles
    tris = PDX_mesh.tri     # flat list of connections, tris[:3] = face[0]

    # UVs (channels 0 to 3)
    uv_Ch = dict()
    for i, uv in enumerate(['u0', 'u1', 'u2', 'u3']):
        if hasattr(PDX_mesh, uv):
            uv_Ch[i] = getattr(PDX_mesh, uv)

    # create the data structures for mesh and transform
    m_FnMesh = OpenMaya.MFnMesh()
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
    m_FnMesh.create(numVertices, numPolygons, vertexArray, polygonCounts, polygonConnects, uArray, vArray, new_object)
    m_FnMesh.setName(tmp_mesh_name)
    m_DagMod.doIt()     # sets up the transform parent to the mesh shape

    # PyNode for the mesh
    new_mesh = pmc.PyNode(tmp_mesh_name)
    new_transform = pmc.listRelatives(new_mesh, parent=True)

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
        m_FnMesh.setVertexNormals(normalsIn, vertexList)

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
        m_FnMesh.assignUVs(uvCounts, uvIds, 'map1')
        # note bulk assignment via .assignUVs only works to the default UV set!
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

            m_FnMesh.createUVSetWithName(uvSetName)
            m_FnMesh.setUVs(uArray, vArray, uvSetName)

    # assign the default material
    pmc.select(new_mesh)
    shd_group = pmc.PyNode('initialShadingGroup')
    pmc.hyperShade(assign=shd_group)

    return new_mesh


""" ====================================================================================================================
    Main function.
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

    pmc.select()
    print "[io_pdx_mesh] finished!"

def export_meshfile(meshpath):
    # create an XML structure to store the object hierarchy
    root_xml = Xml.Element('File')
    root_xml.set('pdxasset', [1, 0])

    # create root elements for objects and locators
    object_xml = Xml.SubElement(root_xml, 'object')
    locator_xml = Xml.SubElement(root_xml, 'locator')

    # populate object data
    pdx_scenemats = [mat for mat in list_scene_materials() if hasattr(mat, PDX_SHADER)]
    maya_shadingengines = [pmc.listConnections(mat, type='shadingEngine') for mat in pdx_scenemats]
    maya_meshfaces = [sg[0].members(flatten=True) for sg in maya_shadingengines]

    # populate locator data
    maya_locators = [loc.getTransform() for loc in pmc.ls(type=pmc.nt.Locator)]
    for loc in maya_locators:
        locnode_xml = Xml.SubElement(locator_xml, loc.name())
        locnode_xml.set('p', [p for p in loc.getTranslation()])
        locnode_xml.set('q', [q for q in loc.getRotation(quaternion=True)])
        if loc.getParent():
            locnode_xml.set('pa', [loc.getParent().name()])

    # write the binary file from our XML structure
    #pdx_data.write_meshfile(meshpath, root_xml)
    return root_xml
