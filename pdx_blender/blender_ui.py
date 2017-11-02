"""
    Paradox asset files, Blender import/export interface.

    author : ross-g
"""

import importlib
import bpy
from bpy.types import Operator, Panel
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper

try:
    from . import blender_import_export
    importlib.reload(blender_import_export)
    from .blender_import_export import *
except Exception as err:
    print(err)
    raise


""" ====================================================================================================================
    Operator classes called by the tool UI.
========================================================================================================================
"""


class importmesh(Operator, ImportHelper):
    bl_idname = 'io_pdx_mesh.importmesh'
    bl_label = 'Import PDX mesh'
    bl_options = {'REGISTER', 'UNDO'}

    # ImportHelper mixin class uses these
    filename_ext = '.mesh'
    filter_glob = StringProperty(
            default='*.mesh',
            options={'HIDDEN'},
            maxlen=255,
            )

    # list of operator properties    
    chk_mesh = BoolProperty(
            name='Import mesh',
            description='Import mesh',
            default=True,
            )
    chk_skel = BoolProperty(
            name='Import skeleton',
            description='Import skeleton',
            default=True,
            )
    chk_locs = BoolProperty(
            name='Import locators',
            description='Import locators',
            default=True,
            )
 
    def execute(self, context):
        import_meshfile(self.filepath, imp_mesh=self.chk_mesh, imp_skel=self.chk_skel, imp_locs=self.chk_locs)

        return {'FINISHED'}


""" ====================================================================================================================
    UI classes for the import/export tool.
========================================================================================================================
"""


class PDXblender_import_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.import'
    bl_label = 'Import'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    # @classmethod
    # def poll(cls, context):
    #     obj = context.active_object
    #     return (obj and obj.type == 'MESH')

    def draw(self, context):
        self.layout.operator('io_pdx_mesh.importmesh', icon='MESH_CUBE', text='Import mesh ...')
        self.layout.operator('io_pdx_mesh.importmesh', icon='RENDER_ANIMATION', text='Import anim ...')


class PDXblender_export_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.export'
    bl_label = 'Export'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    # @classmethod
    # def poll(cls, context):
    #     obj = context.active_object
    #     return (obj and obj.type == 'MESH')

    def draw(self, context):
        self.layout.operator('io_pdx_mesh.importmesh', icon='MESH_CUBE', text='Export mesh ...')
        self.layout.operator('io_pdx_mesh.importmesh', icon='RENDER_ANIMATION', text='Export anim ...')


class PDXblender_setup_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.setup'
    bl_label = 'Setup and Tools'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    # @classmethod
    # def poll(cls, context):
    #     obj = context.active_object
    #     return (obj and obj.type == 'MESH')

    def draw(self, context):
        pass
