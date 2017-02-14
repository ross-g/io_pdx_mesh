"""
    Paradox asset files, Maya import/export.
    
    author : ross-g
"""

import os, sys
import maya.cmds as cmds
import pymel.core as pmc
import pymel.core.datatypes as pmdt
import maya.OpenMaya as OpenMaya    # Maya Python API 1.0
import maya.api.OpenMaya as OpenMaya2    # Maya Python API 2.0

sys.path.append(r"C:\Users\Ross\Documents\GitHub\io_pdx_mesh")
try:
    import pdx_data
    reload(pdx_data)
except:
    import pdx_data


""" ================================================================================================
    Functions.
====================================================================================================
"""

def create_FileTexture(tex_filepath):
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


def create_Shader(shader_name, PDX_material, texture_dir):
    """
        
    """
    new_shader = pmc.shadingNode('phong', asShader=True, name=shader_name)
    new_shadinggroup= pmc.sets(renderable=True, noSurfaceShader=True, empty=True, name='{}_SG'.format(shader_name))
    pmc.connectAttr(new_shader.outColor, new_shadinggroup.surfaceShader)

    # TODO: should be an enum datatype, need to parse the possible engine/material combinations from clausewitz.txt
    pmc.addAttr(longName='shader', dataType='string')
    new_shader.shader.set(PDX_material.shader)

    texture_dict = PDX_material.get_textures()

    if texture_dict.get('diff'):
        texture_path = os.path.join(texture_dir, PDX_material.diff[0])
        new_file, _ = create_FileTexture(texture_path)
        pmc.connectAttr(new_file.outColor, new_shader.color)

    if texture_dict.get('n'):
        texture_path = os.path.join(texture_dir, PDX_material.n[0])
        new_file, _ = create_FileTexture(texture_path)
        bump2d = pmc.shadingNode('bump2d', asUtility=True)
        bump2d.bumpDepth.set(0.1)
        new_file.alphaIsLuminance.set(True)
        pmc.connectAttr(new_file.outAlpha, bump2d.bumpValue)
        pmc.connectAttr(bump2d.outNormal, new_shader.normalCamera)

    if texture_dict.get('spec'):
        texture_path = os.path.join(texture_dir, PDX_material.spec[0])
        new_file, _ = create_FileTexture(texture_path)
        pmc.connectAttr(new_file.outColor, new_shader.specularColor)

    return new_shader, new_shadinggroup


def create_Locator(PDX_locator):
    # create locator
    new_loc = pmc.spaceLocator()
    pmc.select(new_loc)
    pmc.rename(new_loc, PDX_locator.name)

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


def create_Skeleton(PDX_bone_list):
    # keep track of bones as we create them
    bone_list = [None for _ in range(0, len(PDX_bone_list))]

    pmc.select(clear=True)
    for bone in PDX_bone_list:
        index = bone.ix[0]
        transform = bone.tx
        parent = getattr(bone, 'pa', None)

        # create joint
        new_bone = pmc.joint()
        pmc.select(new_bone)
        valid_name = bone.name.split(':')[-1]
        pmc.rename(new_bone, valid_name)     # TODO: setup namespaces properly?
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
        pmc.xform(matrix = mat.inverse())   # set transform to inverse of matrix in world-space
        pmc.select(clear=True)
        
        # connect to parent
        if parent is not None:
            parent_bone = bone_list[parent[0]]
            pmc.connectJoint(new_bone, parent_bone, parentMode=True)

    return bone_list


def create_Skin(mesh, PDX_skin, skeleton):
    # create dictionary of skinning info per vertex
    skin_dict = dict()

    num_infs = PDX_skin.bones[0]
    for vtx in xrange(0, len(PDX_skin.ix)/num_infs):
        skin_dict[vtx] = dict(joints=[], weights=[])

    # gather joint index that each vert is skinned to
    for vtx, j in enumerate(xrange(0, len(PDX_skin.ix), num_infs)):
        skin_dict[vtx]['joints'] = PDX_skin.ix[j:j+num_infs]
    # gather skin weight for each joint in the vertex skin
    for vtx, w in enumerate(xrange(0, len(PDX_skin.ix), num_infs)):
        skin_dict[vtx]['weights'] = PDX_skin.w[w:w+num_infs]
    
    # select mesh and joints
    pmc.select(mesh, skeleton)

    # create skin cluster
    skin_cluster = pmc.skinCluster(bindMethod=0, skinMethod=0, normalizeWeights=1, forceNormalizeWeights=True, 
                                   maximumInfluences=num_infs, obeyMaxInfluences=True, 
                                   name='sc_{}'.format(mesh.name()))

    # set skin weights
    for v in xrange(len(skin_dict.keys())):
        joints = [skeleton[j] for j in skin_dict[v]['joints']]
        weights = skin_dict[v]['weights']
        # normalise joint weights
        norm_weights = [float(w)/sum(weights) for w in weights]
        # strip zero weight entries
        joint_weights = [(j, w) for j, w in zip(joints, norm_weights) if w != 0.0]

        pmc.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh.name(), v),
                        transformValue=joint_weights, normalize=True)


def create_Mesh(PDX_mesh, path):
    # name and namespace
    mesh_name = PDX_mesh.name.split(':')[-1]        # TODO: check for identical mesh names, this just means material will be different
    namespaces = PDX_mesh.name.split(':')[:-1]      # TODO: setup namespaces properly

    # vertices
    verts = PDX_mesh.p      # flat list of co-ordinates, verts[:2] = vtx[0]

    # normals
    norms = None
    if hasattr(PDX_mesh, 'n'):
        norms = PDX_mesh.n      # flat list of co-ordinates, norms[:2] = nrm[0]

    # triangles
    tris = PDX_mesh.tri     # flat list of connections, tris[:3] = face[0]

    # UVs
    uv_0 = None
    uv_1 = None
    if hasattr(PDX_mesh, 'u0'):
        uv_0 = PDX_mesh.u0
    if hasattr(PDX_mesh, 'u1'):
        uv_1 = PDX_mesh.u1

    # material
    mat = PDX_mesh.material

    # skeleton
    skeleton = None
    if hasattr(PDX_mesh, 'skeleton') and PDX_mesh.skeleton:
        skeleton = PDX_mesh.skeleton
    # skin
    skin = None
    if hasattr(PDX_mesh, 'skin'):
        skin = PDX_mesh.skin


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

    # UVs
    uArray = OpenMaya.MFloatArray()
    vArray = OpenMaya.MFloatArray()
    if uv_0:
        for i in xrange(0, len(uv_0), 2):
            uArray.append(uv_0[i])
            vArray.append(1 - uv_0[i+1])        # flip the UV coords in V!


    # create the new mesh
    m_FnMesh.create(numVertices, numPolygons, vertexArray, polygonCounts, polygonConnects, uArray, vArray, new_object)
    m_FnMesh.setName(mesh_name)
    m_DagMod.doIt()     # sets up the transform parent to the mesh shape
    # PyNode for the mesh
    new_mesh = pmc.PyNode(mesh_name)

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

    # apply the UV data
    if uv_0:
        uvCounts = OpenMaya.MIntArray()
        for i in range(0, numPolygons):
            uvCounts.append(3)
        # OpenMaya.MScriptUtil.createIntArrayFromList(verts_per_poly, uvCounts)
        uvIds = OpenMaya.MIntArray()
        for item in tris:
            uvIds.append(item)
        # OpenMaya.MScriptUtil.createIntArrayFromList(raw_tris, uvIds)
        m_FnMesh.assignUVs(uvCounts, uvIds, 'map1')     # note bulk assignment via .assignUVs only works to the default UV set!


    # setup the material
    shader_name = 'Phong_'+mesh_name
    texture_dir = path
    shader, s_group = create_Shader(shader_name, mat, texture_dir)

    pmc.select(new_mesh)
    new_mesh.backfaceCulling.set(1)
    pmc.hyperShade(assign=s_group)


    # setup skeleton and skinning
    bone_list = []
    if skeleton:
        bone_list = create_Skeleton(skeleton)
    if skin and bone_list:
        create_Skin(new_mesh, skin, bone_list)


""" ================================================================================================
    Main.
====================================================================================================
"""

# read the data
# filepath = r"C:\Users\Ross\Documents\GitHub\io_pdx_mesh\test files\fallen_empire_large_warship.mesh"
# filepath = r"C:\Users\Ross\Documents\GitHub\io_pdx_mesh\test files\JAP_01.mesh"
#
# asset = pdx_data.read_meshfile(filepath, to_stdout=True)
#
# for mesh in asset.meshes:
#     create_Skeleton(mesh.skeleton)
#
# for mesh in asset.meshes:
#     create_Mesh(mesh)
#
# for loc in asset.locators:
#     create_Locator(loc)
