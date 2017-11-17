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
import bmesh
import math
from bpy_extras.io_utils import axis_conversion as axis_conversion
from mathutils import Vector, Matrix, Quaternion

from .. import pdx_data


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

PDX_SHADER = 'shader'
PDX_ANIMATION = 'animation'
PDX_IGNOREJOINT = 'pdxIgnoreJoint'


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

    if type(data) == Vector or len(data) == 3:
        vec = Vector(data)
        return (vec * space_matrix)

    if type(data) == Matrix:
        return (space_matrix * data * space_matrix.inverted())


""" ====================================================================================================================
    Functions.
========================================================================================================================
"""


def create_datatexture(tex_filepath):
    """
        Creates & connects up a new file node and place2dTexture node, uses the supplied filepath.
    """
    texture_name = os.path.splitext(os.path.split(tex_filepath)[1])[0]

    newImage = bpy.data.images.load(tex_filepath)
    newBlendDataTexture = bpy.data.textures.new(texture_name, type='IMAGE')
    newBlendDataTexture.image = newImage

    return newBlendDataTexture


def create_material(PDX_material, mesh, texture_dir):
    mat_name = 'PDXphong_' + mesh.name
    new_material = bpy.data.materials.new(mat_name)
    new_material.diffuse_intensity = 1
    new_material.specular_shader = 'PHONG'

    new_material[PDX_SHADER] =  PDX_material.shader[0]

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


def create_locator(PDX_locator):
    # create locator and link to the scene
    new_loc = bpy.data.objects.new(PDX_locator.name, None)
    new_loc.empty_draw_type = 'PLAIN_AXES'
    new_loc.show_axis = True

    bpy.context.scene.objects.link(new_loc)

    # parent locator
    parent = getattr(PDX_locator, 'pa', None)
    # if parent is not None:
    #     parent_bone = pmc.ls(parent[0], type='joint')
    #     if parent_bone:
    #         pmc.parent(new_loc, parent_bone[0])

    # set attributes
    new_loc.rotation_mode = 'XYZ'
    # rotation
    quat = Quaternion([PDX_locator.q[3], PDX_locator.q[0], PDX_locator.q[1], PDX_locator.q[2]])
    new_loc.rotation_euler = quat.to_euler()
    # translation
    new_loc.location = (PDX_locator.p[0], PDX_locator.p[1], PDX_locator.p[2])

    bpy.context.scene.update()

    # convert to Blender space
    xForm = swap_coord_space(new_loc.matrix_world)
    new_loc.matrix_world = xForm


def create_skeleton(PDX_bone_list):
    # keep track of bones as we create them
    bone_list = [None for _ in range(0, len(PDX_bone_list))]

    # bpy.ops.object.select_all(action='DESELECT')
    # temporary name used during creation
    tmp_rig_name = 'io_pdx_rig'

    # create the armature datablock
    armt = bpy.data.armatures.new('armature')

    # create the object and link to the scene
    new_rig = bpy.data.objects.new(tmp_rig_name, armt)
    bpy.context.scene.objects.link(new_rig)
    bpy.context.scene.objects.active = new_rig
    new_rig.select = True

    bpy.ops.object.mode_set(mode='EDIT')
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
        # if pmc.ls(unique_name, type='joint'):
        #     bone_list[index] = pmc.PyNode(unique_name)
        #     continue    # bone already exists, likely the skeleton is already built, so collect and return joints

        # create joint
        new_bone = armt.edit_bones.new(name=unique_name)
        new_bone.select = True
        bone_list[index] = new_bone

        # set transform
        mat = Matrix((
            (transform[0], transform[3], transform[6], transform[9]),
            (transform[1], transform[4], transform[7], transform[10]),
            (transform[2], transform[5], transform[8], transform[11]),
            (0.0, 0.0, 0.0, 1.0)
        ))
        new_bone.head = swap_coord_space(mat.inverted_safe().to_translation())      # convert coords to Blender space
        new_bone.tail = new_bone.head + Vector((0,-1,0))

        # connect to parent
        if parent is not None:
            parent_bone = bone_list[parent[0]]
            new_bone.parent = parent_bone
            new_bone.use_connect = True

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.scene.update()
    new_rig.show_x_ray = True

    return bone_list


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
        # v = [verts[i], verts[i+1], verts[i+2]]
        v = swap_coord_space([verts[i], verts[i+1], verts[i+2]])      # convert coords to Blender space
        vertexArray.append(v)

    # faces
    faceArray = []
    for i in range(0, len(tris), 3):
        # f = [tris[i], tris[i+1], tris[i+2]]
        f = [tris[i+2], tris[i+1], tris[i]]         # convert handedness to Blender space
        faceArray.append(f)

    # create the mesh datablock
    new_mesh = bpy.data.meshes.new(tmp_mesh_name)

    # add mesh data
    new_mesh.from_pydata(vertexArray, [], faceArray)
    new_mesh.update()

    # create the object and link to the scene
    if name is None:
        name = tmp_mesh_name
    new_obj = bpy.data.objects.new(name, new_mesh)
    bpy.context.scene.objects.link(new_obj)
    new_mesh.name = name

    # apply the vertex normal data
    if norms:
        normals = []
        for i in range(0, len(norms), 3):
            # n = [norms[i], norms[i+1], norms[i+2]]
            n = swap_coord_space([norms[i], norms[i+1], norms[i+2]])      # convert vector to Blender space
            normals.append(n)

        new_mesh.polygons.foreach_set('use_smooth', [True] * len(new_mesh.polygons))
        new_mesh.normals_split_custom_set_from_vertices(normals)
        new_mesh.use_auto_smooth = True
        new_mesh.show_edge_sharp = True
        new_mesh.free_normals_split()
    
    # apply the UV data channels
    for idx in uv_Ch:
        uv_data = uv_Ch[idx]
        uvSetName = 'map' + str(idx+1)
        
        uvArray = []
        for i in range(0, len(uv_data), 2):
            uv = [uv_data[i], 1 - uv_data[i+1]]     # flip the UV coords in V!
            uvArray.append(uv)

        new_mesh.uv_textures.new(uvSetName)
        bm = get_BMesh(new_mesh)
        bm.faces.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv[uvSetName]
        bm.faces.layers.tex.verify()

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

    return new_mesh


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

        # create the skeleton first, so we can skin the mesh to it
        joints = None
        skeleton = node.find('skeleton')
        if imp_skel and skeleton:
            print("[io_pdx_mesh] creating skeleton -")
            pdx_bone_list = list()
            for b in skeleton:
                pdx_bone = pdx_data.PDXData(b)
                pdx_bone_list.append(pdx_bone)

            joints = create_skeleton(pdx_bone_list)

        # then create all the meshes
        meshes = node.findall('mesh')
        if imp_mesh:
            for m in meshes:
                print("[io_pdx_mesh] creating mesh -")
                pdx_mesh = pdx_data.PDXData(m)
                pdx_material = getattr(pdx_mesh, 'material', None)
                pdx_skin = getattr(pdx_mesh, 'skin', None)

                # create the geometry
                mesh = create_mesh(pdx_mesh, name=node.tag)

                # create the material
                if pdx_material:
                    print("[io_pdx_mesh] creating material -")
                    create_material(pdx_material, mesh, os.path.split(meshpath)[0])

                # # create the skin cluster
                # if joints and pdx_skin:
                #     print("[io_pdx_mesh] creating skinning data -")
                #     create_skin(pdx_skin, mesh, joints)

    # go through locators
    if imp_locs:
        print("[io_pdx_mesh] creating locators -")
        for loc in locators:
            pdx_locator = pdx_data.PDXData(loc)
            create_locator(pdx_locator)

    print("[io_pdx_mesh] finished!")


def export_meshfile(meshpath):
    pass


def import_animfile(animpath, timestart=1.0):
    pass
