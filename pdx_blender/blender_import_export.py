"""
    Paradox asset files, Blender import/export.
    
    author : ross-g
"""

import os
import sys
import inspect
from collections import OrderedDict
try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

import bpy
import math

import site
site.addsitedir(os.path.join('J:\\', 'Github', 'io_pdx_mesh'))
import pdx_data


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

PDX_SHADER = 'shader'
PDX_ANIMATION = 'animation'
PDX_IGNOREJOINT = 'pdxIgnoreJoint'


""" ====================================================================================================================
    Functions.
========================================================================================================================
"""


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
        v = [verts[i], verts[i+1], verts[i+2]]
        vertexArray.append(v)

    # faces
    faceArray = []
    for i in range(0, len(tris), 3):
        f = [tris[i], tris[i+1], tris[i+2]]
        faceArray.append(f)

    # create the mesh datablock
    new_mesh = bpy.data.meshes.new(tmp_mesh_name)

    # add mesh data
    new_mesh.from_pydata(vertexArray, [], faceArray)

    # create the object and link it to the scene
    if name is None:
        name = tmp_mesh_name
    new_obj = bpy.data.objects.new(name, new_mesh)
    bpy.context.scene.objects.link(new_obj)

    # apply the vertex normal data
    
    # apply the default UV data
    
    # set other UV channels
    
    # mirror in X and rotate by 90 about X

    # select the object
    bpy.context.scene.objects.active = new_obj
    new_obj.select = True


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
        print("[io_pdx_mesh] creating node - {}".format(node.tag))

        # # create the skeleton first, so we can skin the mesh to it
        # joints = None
        # skeleton = node.find('skeleton')
        # if imp_skel and skeleton:
        #     print("[io_pdx_mesh] creating skeleton -")
        #     pdx_bone_list = list()
        #     for b in skeleton:
        #         pdx_bone = pdx_data.PDXData(b)
        #         pdx_bone_list.append(pdx_bone)

        #     joints = create_skeleton(pdx_bone_list)

        # then create all the meshes
        meshes = node.findall('mesh')
        if imp_mesh:
            pdx_mesh_list = list()
            for m in meshes:
                print("[io_pdx_mesh] creating mesh -")
                pdx_mesh = pdx_data.PDXData(m)
                pdx_material = getattr(pdx_mesh, 'material', None)
                pdx_skin = getattr(pdx_mesh, 'skin', None)

                # create the geometry
                mesh = create_mesh(pdx_mesh, name=node.tag)
                pdx_mesh_list.append(mesh)

                # # create the material
                # if pdx_material:
                #     print("[io_pdx_mesh] creating material -")
                #     create_material(pdx_material, mesh, os.path.split(meshpath)[0])

                # # create the skin cluster
                # if joints and pdx_skin:
                #     print("[io_pdx_mesh] creating skinning data -")
                #     create_skin(pdx_skin, mesh, joints)

    # go through locators
    # if imp_locs:
    #     print("[io_pdx_mesh] creating locators -")
    #     for loc in locators:
    #         pdx_locator = pdx_data.PDXData(loc)
    #         create_locator(pdx_locator)

    print("[io_pdx_mesh] finished!")


def export_meshfile(meshpath):
    pass


def import_animfile(animpath, timestart=1.0):
    pass

a_file = os.path.join('J:\\', 'Github', 'io_pdx_mesh', 'test files', 'archipelago_frigate.mesh')
import_meshfile(a_file, imp_mesh=True, imp_skel=True, imp_locs=True)
