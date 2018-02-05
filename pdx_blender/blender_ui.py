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
from bpy_extras.io_utils import ImportHelper

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

    def excute(self, context):
        print("[io_pdx_mesh] Importing {}".format(self.filepath))
        import_meshfile(self.filepath, imp_mesh=self.chk_mesh, imp_skel=self.chk_skel, imp_locs=self.chk_locs)

        return {'FINISHED'}


class popup_message(Operator):
    bl_idname = 'io_pdx_mesh.popup_message'
    bl_label = ''

    msg_text = StringProperty(
        default='PLACEHOLDER',
    )
    msg_icon = StringProperty(
        default='QUESTION',  # 'ERROR', 'CANCEL'
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
        op_import_mesh = row.operator('io_pdx_mesh.import_mesh', icon='MESH_CUBE', text='Load mesh ...')
        op_import_anim = row.operator('io_pdx_mesh.popup_message', icon='RENDER_ANIMATION', text='Load anim ...')
        op_import_anim.msg_text = 'Animation import not implemented yet!'
        op_import_anim.msg_icon = 'ERROR'

        self.layout.label('Export:', icon='EXPORT')
        row = self.layout.row()
        op_export_mesh = row.operator('io_pdx_mesh.popup_message', icon='MESH_CUBE', text='Save mesh ...')
        op_export_mesh.msg_text = 'Mesh export not implemented yet!'
        op_export_mesh.msg_icon = 'ERROR'
        op_export_anim = row.operator('io_pdx_mesh.popup_message', icon='RENDER_ANIMATION', text='Save anim ...')
        op_export_anim.msg_text = 'Animation export not implemented yet!'
        op_export_anim.msg_icon = 'ERROR'


class PDXblender_setup_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.setup'
    bl_label = 'Setup and Tools'
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

        box = self.layout.box()
        box.label('Tools:')
        box.operator('io_pdx_mesh.edit_settings', icon='FILE_TEXT', text='Edit Clausewitz settings')


class PDXblender_help_ui(Panel):
    bl_idname = 'panel.io_pdx_mesh.help'
    bl_label = 'Help'
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    def draw(self, context):
        self.layout.operator('wm.url_open', icon='QUESTION', text='Paradox forums').url = 'https://forum.paradoxplaza.com/forum/index.php?forums/clausewitz-maya-exporter-modding-tool.935/'
        self.layout.operator('wm.url_open', icon='QUESTION', text='Source code').url = 'https://github.com/ross-g/io_pdx_mesh'
