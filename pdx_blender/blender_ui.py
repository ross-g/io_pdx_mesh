"""
    Paradox asset files, Blender import/export interface.

    author : ross-g
"""

import os
import inspect
import json
import importlib
import bpy
from bpy.types import Operator, Panel
from bpy.props import StringProperty, IntProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper

try:
    from . import blender_import_export
    importlib.reload(blender_import_export)
    from .blender_import_export import *

except Exception as err:
    print(err)
    raise


""" ====================================================================================================================
    Variables and Helper functions.
========================================================================================================================
"""


_script_dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
settings_file = os.path.join(os.path.split(_script_dir)[0], 'clausewitz.json')

engine_list = ()


def load_settings():
    global settings_file
    with open(settings_file, 'rt') as f:
        try:
            settings = json.load(f)
            return settings
        except Exception as err:
            print("[io_pdx_mesh] Critical error.")
            print(err)
            return {}


def get_engine_list(self, context):
    global engine_list

    settings = load_settings()     # settings from json
    engine_list = ((engine, engine, '') for engine in sorted(settings.keys()))

    return engine_list


def set_animation_fps(self, context):
    context.scene.render.fps = context.scene.io_pdx_settings.setup_fps


class popup_message(Operator):
    bl_idname = 'io_pdx_mesh.popup_message'
    bl_label = '[io_pdx_mesh]'

    msg_text = StringProperty(
        default='NOT YET IMPLEMENTED!',
    )
    msg_icon = StringProperty(
        default='ERROR',  # 'QUESTION', 'CANCEL'
    )
    msg_width = IntProperty(
        default=300,
    )

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=self.msg_width)

    def draw(self, context):
        self.layout.label(self.msg_text, icon=self.msg_icon)
        self.layout.label('')


""" ====================================================================================================================
    Operator classes called by the tool UI.
========================================================================================================================
"""


class import_mesh(Operator, ImportHelper):
    bl_idname = 'io_pdx_mesh.import_mesh'
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


class export_mesh(Operator, ExportHelper):
    bl_idname = 'io_pdx_mesh.export_mesh'
    bl_label = 'Export PDX mesh'
    bl_options = {'REGISTER', 'UNDO'}

    # ExportHelper mixin class uses these
    filename_ext = '.mesh'
    filter_glob = StringProperty(
        default='*.mesh',
        options={'HIDDEN'},
        maxlen=255,
    )

    # list of operator properties
    chk_mesh = BoolProperty(
        name='Export mesh',
        description='Export mesh',
        default=True,
    )
    chk_skel = BoolProperty(
        name='Export skeleton',
        description='Export skeleton',
        default=True,
    )
    chk_locs = BoolProperty(
        name='Export locators',
        description='Export locators',
        default=True,
    )

    def execute(self, context):
        export_meshfile(self.filepath, exp_mesh=self.chk_mesh, exp_skel=self.chk_skel, exp_locs=self.chk_locs)
        return {'FINISHED'}


class show_axis(Operator):
    bl_idname = 'io_pdx_mesh.show_axis'
    bl_label = 'Show local axis'
    bl_options = {'REGISTER'}

    show = BoolProperty(
        default=True
    )
    obj_type = type(None)   # TODO: can this be a property so we can over-ride it per usage rather than set at class level?
 
    def execute(self, context):
        set_local_axis_display(self.show, self.obj_type)
        return {'FINISHED'}


class edit_settings(Operator):
    bl_idname = 'io_pdx_mesh.edit_settings'
    bl_label = 'Edit Clausewitz settings'
    bl_options = {'REGISTER'}

    def execute(self, context):
        os.startfile(settings_file)
        return {'FINISHED'}


""" ====================================================================================================================
    UI classes for the import/export tool.
========================================================================================================================
"""


class PDXblender_file_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.file'
    bl_label = 'File'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    # @classmethod
    # def poll(cls, context):
    #     obj = context.active_object
    #     return (obj and obj.type == 'MESH')

    def draw(self, context):
        self.layout.label('Import:', icon='IMPORT')
        row = self.layout.row()
        row.operator('io_pdx_mesh.import_mesh', icon='MESH_CUBE', text='Load mesh ...')
        row.operator('io_pdx_mesh.popup_message', icon='RENDER_ANIMATION', text='Load anim ...')

        self.layout.label('Export:', icon='EXPORT')
        row = self.layout.row()
        row.operator('io_pdx_mesh.export_mesh', icon='MESH_CUBE', text='Save mesh ...')
        row.operator('io_pdx_mesh.popup_message', icon='RENDER_ANIMATION', text='Save anim ...')


class PDXblender_tools_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.tools'
    bl_label = 'Tools'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    def draw(self, context):
        settings = context.scene.io_pdx_settings

        col = self.layout.column(align=True)
        col.label('Locator axes:')
        row = col.row(align=True)
        op_show_axis = row.operator('io_pdx_mesh.show_axis', icon='MANIPUL', text='Show all')
        op_show_axis.show = True
        op_hide_axis = row.operator('io_pdx_mesh.show_axis', icon='OUTLINER_DATA_EMPTY', text='Hide all')
        op_hide_axis.show = False
        col.separator()
        col.label('Materials:')
        row = col.row(align=True)
        row.operator('io_pdx_mesh.popup_message', icon='MATERIAL', text='Create ...')
        row.operator('io_pdx_mesh.popup_message', icon='MATERIAL', text='Edit')


class PDXblender_setup_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.setup'
    bl_label = 'Setup'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    def draw(self, context):
        settings = context.scene.io_pdx_settings

        box = self.layout.box()
        box.label('Scene setup:')
        box.prop(settings, 'setup_engine')
        row = box.row()
        row.label('Animation')
        row.prop(settings, 'setup_fps', text='fps')

        box = self.layout.box()
        box.label('Export settings:')
        box.prop(settings, 'chk_merge_vtx')
        box.prop(settings, 'chk_merge_obj')
        # box.prop(settings, 'chk_create')
        # box.prop(settings, 'chk_preview')


class PDXblender_help_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.help'
    bl_label = 'Help'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    def draw(self, context):
        self.layout.operator('io_pdx_mesh.edit_settings', icon='FILE_TEXT', text='Edit Clausewitz settings')
        self.layout.operator('wm.url_open', icon='QUESTION', text='Paradox forums').url = 'https://forum.paradoxplaza.com/forum/index.php?forums/clausewitz-maya-exporter-modding-tool.935/'
        self.layout.operator('wm.url_open', icon='QUESTION', text='Source code').url = 'https://github.com/ross-g/io_pdx_mesh'
