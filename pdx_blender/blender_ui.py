"""
    Paradox asset files, Blender import/export interface.

    author : ross-g
"""

import bpy
from .blender_import_export import *


""" ====================================================================================================================
    Operator classes called by the tool UI.
========================================================================================================================
"""


class importmesh(bpy.types.Operator):
    bl_idname = 'mesh.import_pdx_mesh'
    bl_label = 'Import PDX mesh'
    bl_options = {'REGISTER', 'UNDO'}
 
    def execute(self, context):
        # bpy.ops.mesh.primitive_cube_add()
        import os
        a_file = os.path.join('J:\\', 'Github', 'io_pdx_mesh', 'test files', 'fallen_empire_large_warship.mesh')
        import_meshfile(a_file, imp_mesh=True, imp_skel=True, imp_locs=True)

        return {'FINISHED'}


""" ====================================================================================================================
    UI classes for the import/export tool.
========================================================================================================================
"""


class PDXblender_import_ui(bpy.types.Panel):
    bl_idname = 'panel.io_pdx_mesh_import'
    bl_label = 'Import'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    # @classmethod
    # def poll(cls, context):
    #     obj = context.active_object
    #     return (obj and obj.type == 'MESH')

    def draw(self, context):
        self.layout.operator('mesh.import_pdx_mesh', icon='MESH_CUBE', text='Import mesh ...')
        self.layout.operator('mesh.import_pdx_mesh', icon='RENDER_ANIMATION', text='Import anim ...')


class PDXblender_export_ui(bpy.types.Panel):
    bl_idname = 'panel.io_pdx_mesh_export'
    bl_label = 'Export'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    # @classmethod
    # def poll(cls, context):
    #     obj = context.active_object
    #     return (obj and obj.type == 'MESH')

    def draw(self, context):
        self.layout.operator('mesh.import_pdx_mesh', icon='MESH_CUBE', text='Export mesh ...')
