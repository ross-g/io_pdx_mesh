"""
    Paradox asset files, Blender import/export interface.

    author : ross-g
"""

import os
import inspect
import json
import importlib
import bpy
from bpy.types import Operator, Panel, UIList
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper

from ..pdx_data import PDXData
from ..updater import CURRENT_VERSION, LATEST_VERSION, LATEST_URL, AT_LATEST

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

    settings = load_settings()  # settings from json
    engine_list = ((engine, engine, engine) for engine in sorted(settings.keys()))

    return engine_list


def get_material_list(self, context):
    sel_engine = context.scene.io_pdx_settings.setup_engine

    settings = load_settings()  # settings from json
    material_list = [(material, material, material) for material in settings[sel_engine]['material']]
    material_list.insert(0, ('__NONE__', '', ''))

    return material_list


def get_scene_material_list(self, context):
    material_list = [(mat.name, mat.name, mat.name) for mat in bpy.data.materials if mat.get(PDX_SHADER, None)]

    return material_list


def set_animation_fps(self, context):
    context.scene.render.fps = context.scene.io_pdx_settings.setup_fps


""" ====================================================================================================================
    Operator classes called by the tool UI.
========================================================================================================================
"""


class popup_message(Operator):
    bl_idname = 'io_pdx_mesh.popup_message'
    bl_label = '[io_pdx_mesh]'
    bl_options = {'REGISTER'}

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


class material_popup(object):
    bl_options = {'REGISTER'}

    mat_name = StringProperty(
        name='Name',
        default=''
    )
    mat_type = EnumProperty(
        name='Shader preset',
        items=get_material_list
    )
    use_custom = BoolProperty(
        name='custom Shader:',
        default=False,
    )
    custom_type = StringProperty(
        name='Shader',
        default=''
    )


class material_create_popup(material_popup, Operator):
    bl_idname = 'io_pdx_mesh.material_create_popup'
    bl_label = 'Create a PDX material'

    def check(self, context):
        return True

    def execute(self, context):
        mat_name = self.mat_name
        mat_type = self.mat_type
        if self.use_custom or mat_type == '__NONE__':
            mat_type = self.custom_type
        # create a mock PDXData object for convenience here to pass to the create_shader function
        mat_pdx = type(
            'Material',
            (PDXData, object),
            {'shader': [mat_type]}
        )

        create_material(mat_pdx, None, mat_name=mat_name)
        return {'FINISHED'}

    def invoke(self, context, event):
        self.mat_name = ''
        self.mat_type = '__NONE__'
        self.use_custom = False
        self.custom_type = ''
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        box = self.layout.box()
        box.prop(self, 'mat_name')
        box.prop(self, 'mat_type')
        row = box.split(0.33)
        row.prop(self, 'use_custom')
        if self.use_custom:
            row.prop(self, 'custom_type', text='')
        self.layout.separator()


class material_edit_popup(material_popup, Operator):
    bl_idname = 'io_pdx_mesh.material_edit_popup'
    bl_label = 'Edit a PDX material'

    def mat_select(self, context):
        mat = bpy.data.materials[self.scene_mats]

        curr_mat = context.scene.io_pdx_material
        curr_mat.mat_name = mat.name
        curr_mat.mat_type = mat[PDX_SHADER]

    scene_mats = EnumProperty(
        name='Selected material',
        items=get_scene_material_list,
        update=mat_select
    )

    def check(self, context):
        return True

    def execute(self, context):
        mat = bpy.data.materials[self.scene_mats]
        curr_mat = context.scene.io_pdx_material
        mat.name = curr_mat.mat_name
        mat[PDX_SHADER] = curr_mat.mat_type
        return {'FINISHED'}

    def invoke(self, context, event):
        pdx_scene_materials = get_scene_material_list(self, context)
        if pdx_scene_materials:
            if self.scene_mats in bpy.data.materials:
                self.mat_select(context)
                mat = bpy.data.materials[self.scene_mats]
                self.mat_name = mat.name
                self.custom_type = mat[PDX_SHADER]
                return context.window_manager.invoke_props_dialog(self, width=350)
            else:
                return {'CANCELLED'}
        else:
            bpy.ops.io_pdx_mesh.popup_message('INVOKE_DEFAULT', msg_text='NO PDX MATERIALS FOUND IN THE SCENE!')
            return {'CANCELLED'}

    def draw(self, context):
        curr_mat = context.scene.io_pdx_material

        self.layout.prop(self, 'scene_mats')
        self.layout.separator()

        box = self.layout.box()
        box.prop(curr_mat, 'mat_name')
        box.prop(curr_mat, 'mat_type')
        self.layout.separator()


class mesh_index_list(UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'name', text='', emboss=False)


class mesh_index_actions(Operator):
    bl_idname = "io_pdx_mesh.mesh_index_actions"
    bl_label = "Mesh index list actions"
    bl_options = {'REGISTER'}

    action = EnumProperty(
        items=(('UP', "Up", ""), ('DOWN', "Down", ""))
    )

    @classmethod
    def poll(cls, context):
        return context.scene.io_pdx_group

    def move_index(self):
        list_index = bpy.context.scene.io_pdx_group.idx
        list_length = len(bpy.context.scene.io_pdx_group.coll) - 1

        new_index = list_index + (-1 if self.action == 'UP' else 1)
        bpy.context.scene.io_pdx_group.idx = max(0, min(new_index, list_length))

    def execute(self, context):
        collection = context.scene.io_pdx_group.coll
        index = context.scene.io_pdx_group.idx
        neighbor = index + (-1 if self.action == 'UP' else 1)
        collection.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}


class mesh_index_popup(Operator):
    bl_idname = 'io_pdx_mesh.mesh_index_popup'
    bl_label = 'Set mesh index on PDX meshes'
    bl_options = {'REGISTER'}

    def check(self, context):
        return True

    def execute(self, context):
        for i, item in enumerate(context.scene.io_pdx_group.coll):
            item.ref.data['meshindex'] = i
        return{'FINISHED'}

    def invoke(self, context, event):
        obj_group = context.scene.io_pdx_group

        obj_group.coll.clear()
        pdx_scenemeshes = list_scene_pdx_meshes()
        pdx_scenemeshes.sort(key=lambda obj: get_mesh_index(obj.data))

        for obj in pdx_scenemeshes:
            item = obj_group.coll.add()
            item.name = obj.name
            item.ref = obj
        return context.window_manager.invoke_props_dialog(self, width=200)

    def draw(self, context):
        obj_group = context.scene.io_pdx_group
        row = self.layout.row()
        row.template_list('mesh_index_list', '', obj_group, 'coll', obj_group, 'idx', rows=8)

        col = row.column(align=True)
        col.operator("io_pdx_mesh.mesh_index_actions", icon='TRIA_UP', text="").action = 'UP'
        col.operator("io_pdx_mesh.mesh_index_actions", icon='TRIA_DOWN', text="").action = 'DOWN'
        self.layout.separator()


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
    chk_bonespace = BoolProperty(
        name='Convert bone orientation - WARNING',
        description='Convert bone orientation - WARNING: this re-orients bones authored in Maya, but will BREAK ALL '
                    'EXISTING ANIMATIONS. Only use this option if you are going to re-animate the model.',
        default=False,
    )

    def draw(self, context):
        box = self.layout.box()
        box.label('Settings:', icon='IMPORT')
        box.prop(self, 'chk_mesh')
        box.prop(self, 'chk_skel')
        box.prop(self, 'chk_locs')
        # box.prop(self, 'chk_bonespace')  # TODO: works but overcomplicates things, disabled for now

    def execute(self, context):
        try:
            import_meshfile(
                self.filepath,
                imp_mesh=self.chk_mesh,
                imp_skel=self.chk_skel,
                imp_locs=self.chk_locs,
                bonespace=self.chk_bonespace
            )
            self.report({'INFO'}, '[io_pdx_mesh] Finsihed importing {}'.format(self.filepath))
        except Exception as err:
            msg = '[io_pdx_mesh] FAILED to import {}'.format(self.filepath)
            self.report({'WARNING'}, msg)
            self.report({'ERROR'}, err)
            print(msg)
            print(err)
            raise

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
    chk_merge = BoolProperty(
        name='Merge vertices',
        description='Merge vertices',
        default=True,
    )

    def draw(self, context):
        box = self.layout.box()
        box.label('Settings:', icon='EXPORT')
        box.prop(self, 'chk_mesh')
        box.prop(self, 'chk_skel')
        box.prop(self, 'chk_locs')
        box.prop(self, 'chk_merge')

    def execute(self, context):
        try:
            export_meshfile(
                self.filepath,
                exp_mesh=self.chk_mesh,
                exp_skel=self.chk_skel,
                exp_locs=self.chk_locs,
                merge_verts=self.chk_merge
            )
            self.report({'INFO'}, '[io_pdx_mesh] Finsihed exporting {}'.format(self.filepath))
        except Exception as err:
            msg = '[io_pdx_mesh] FAILED to export {}'.format(self.filepath)
            self.report({'WARNING'}, msg)
            self.report({'ERROR'}, err)
            print(msg)
            print(err)
            raise

        return {'FINISHED'}


class import_anim(Operator, ImportHelper):
    bl_idname = 'io_pdx_mesh.import_anim'
    bl_label = 'Import PDX animation'
    bl_options = {'REGISTER', 'UNDO'}

    # ImportHelper mixin class uses these
    filename_ext = '.anim'
    filter_glob = StringProperty(
        default='*.anim',
        options={'HIDDEN'},
        maxlen=255,
    )

    # list of operator properties
    int_start = IntProperty(
        name='Start frame',
        description='Start frame',
        default=1,
    )

    def draw(self, context):
        box = self.layout.box()
        box.label('Settings:', icon='IMPORT')
        box.prop(self, 'int_start')

    def execute(self, context):
        try:
            import_animfile(
                self.filepath,
                timestart=self.int_start
            )
            self.report({'INFO'}, '[io_pdx_mesh] Finsihed importing {}'.format(self.filepath))
        except Exception as err:
            msg = '[io_pdx_mesh] FAILED to import {}'.format(self.filepath)
            self.report({'WARNING'}, msg)
            self.report({'ERROR'}, err)
            print(msg)
            print(err)
            raise

        return {'FINISHED'}


class export_anim(Operator, ExportHelper):
    bl_idname = 'io_pdx_mesh.export_anim'
    bl_label = 'Export PDX animation'
    bl_options = {'REGISTER', 'UNDO'}

    # ExportHelper mixin class uses these
    filename_ext = '.anim'
    filter_glob = StringProperty(
        default='*.anim',
        options={'HIDDEN'},
        maxlen=255,
    )

    # list of operator properties
    int_start = IntProperty(
        name='Start frame',
        description='Start frame',
        default=1,
    )
    int_end = IntProperty(
        name='End frame',
        description='End frame',
        default=100,
    )

    def draw(self, context):
        settings = context.scene.io_pdx_export

        box = self.layout.box()
        box.label('Settings:', icon='EXPORT')
        box.prop(settings, 'custom_range')
        col = box.column()
        col.enabled = settings.custom_range
        col.prop(self, 'int_start')
        col.prop(self, 'int_end')

    def execute(self, context):
        settings = context.scene.io_pdx_export

        try:
            if settings.custom_range:
                export_animfile(
                    self.filepath,
                    timestart=self.int_start,
                    timeend=self.int_end
                )
            else:
                export_animfile(
                    self.filepath,
                    timestart=context.scene.frame_start,
                    timeend=context.scene.frame_end
                )
            self.report({'INFO'}, '[io_pdx_mesh] Finsihed exporting {}'.format(self.filepath))
        except Exception as err:
            msg = '[io_pdx_mesh] FAILED to export {}'.format(self.filepath)
            self.report({'WARNING'}, msg)
            self.report({'ERROR'}, err)
            print(msg)
            print(err)
            raise

        return {'FINISHED'}


class show_axis(Operator):
    bl_idname = 'io_pdx_mesh.show_axis'
    bl_label = 'Show local axis'
    bl_options = {'REGISTER'}

    show = BoolProperty(
        default=True
    )
    data_type = EnumProperty(
        name='Data type',
        items=(
            ('EMPTY', 'Empty', 'Empty', 1),
            ('ARMATURE', 'Armature', 'Armature', 2)
        )
    )

    def execute(self, context):
        set_local_axis_display(self.show, self.data_type)
        return {'FINISHED'}


class ignore_bone(Operator):
    bl_idname = 'io_pdx_mesh.ignore_bone'
    bl_label = 'Ignore selected bones'
    bl_options = {'REGISTER'}

    state = BoolProperty(
        default=False
    )

    def execute(self, context):
        set_ignore_joints(self.state)
        return {'FINISHED'}


""" ====================================================================================================================
    UI classes for the import/export tool.
========================================================================================================================
"""


class PDXUI(object):
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'


class PDXblenderUI_file(PDXUI, Panel):
    bl_idname = 'panel.io_pdx_mesh.file'
    bl_label = 'File'
    panel_order = 1

    def draw(self, context):
        self.layout.label('Import:', icon='IMPORT')
        row = self.layout.row(align=True)
        row.operator('io_pdx_mesh.import_mesh', icon='MESH_CUBE', text='Load mesh ...')
        row.operator('io_pdx_mesh.import_anim', icon='RENDER_ANIMATION', text='Load anim ...')

        self.layout.label('Export:', icon='EXPORT')
        row = self.layout.row(align=True)
        row.operator('io_pdx_mesh.export_mesh', icon='MESH_CUBE', text='Save mesh ...')
        row.operator('io_pdx_mesh.export_anim', icon='RENDER_ANIMATION', text='Save anim ...')


class PDXblenderUI_tools(PDXUI, Panel):
    bl_idname = 'panel.io_pdx_mesh.tools'
    bl_label = 'Tools'
    panel_order = 2

    def draw(self, context):
        col = self.layout.column(align=True)

        col.label('PDX materials:')
        row = col.row(align=True)
        row.operator('io_pdx_mesh.material_create_popup', icon='MATERIAL', text='Create')
        row.operator('io_pdx_mesh.material_edit_popup', icon='TEXTURE_SHADED', text='Edit')
        col.separator()

        col.label('PDX bones:')
        row = col.row(align=True)
        op_ignore_bone = row.operator('io_pdx_mesh.ignore_bone', icon='OUTLINER_DATA_POSE', text='Ignore bones')
        op_ignore_bone.state = True
        op_unignore_bone = row.operator('io_pdx_mesh.ignore_bone', icon='POSE_HLT', text='Un-ignore bones')
        op_unignore_bone.state = False
        col.separator()

        # col.label('PDX animations:')
        # row = col.row(align=True)
        # row.operator('io_pdx_mesh.popup_message', icon='IPO_BEZIER', text='Create')
        # row.operator('io_pdx_mesh.popup_message', icon='NORMALIZE_FCURVES', text='Edit')
        # col.separator()

        col.label('PDX meshes:')
        row = col.row(align=True)
        row.operator('io_pdx_mesh.mesh_index_popup', icon='SORTALPHA', text='Set mesh order')


class PDXblenderUI_display(PDXUI, Panel):
    bl_idname = 'panel.io_pdx_mesh.display'
    bl_label = 'Display'
    bl_options = {'DEFAULT_CLOSED'}
    panel_order = 3

    def draw(self, context):
        col = self.layout.column(align=True)

        col.label('Display local axes:')
        row = col.row(align=True)
        op_show_bone_axis = row.operator('io_pdx_mesh.show_axis', icon='OUTLINER_OB_ARMATURE', text='Show all')
        op_show_bone_axis.show = True
        op_show_bone_axis.data_type = 'ARMATURE'
        op_hide_bone_axis = row.operator('io_pdx_mesh.show_axis', icon='OUTLINER_DATA_ARMATURE', text='Hide all')
        op_hide_bone_axis.show = False
        op_hide_bone_axis.data_type = 'ARMATURE'
        row = col.row(align=True)
        op_show_loc_axis = row.operator('io_pdx_mesh.show_axis', icon='MANIPUL', text='Show all')
        op_show_loc_axis.show = True
        op_show_loc_axis.data_type = 'EMPTY'
        op_hide_loc_axis = row.operator('io_pdx_mesh.show_axis', icon='OUTLINER_DATA_EMPTY', text='Hide all')
        op_hide_loc_axis.show = False
        op_hide_loc_axis.data_type = 'EMPTY'


class PDXblenderUI_setup(PDXUI, Panel):
    bl_idname = 'panel.io_pdx_mesh.setup'
    bl_label = 'Setup'
    bl_options = {'DEFAULT_CLOSED'}
    panel_order = 4

    def draw(self, context):
        settings = context.scene.io_pdx_settings

        self.layout.prop(settings, 'setup_engine')
        row = self.layout.row(align=True)
        row.label('Animation:')
        row.prop(settings, 'setup_fps', text='FPS')


class PDXblenderUI_help(PDXUI, Panel):
    bl_idname = 'panel.io_pdx_mesh.help'
    bl_label = 'Help'
    bl_options = {'DEFAULT_CLOSED'}
    panel_order = 5

    def draw(self, context):
        col = self.layout.column(align=True)

        col.label('version: {}'.format(CURRENT_VERSION))
        if not AT_LATEST:   # update info appears if we aren't at the latest tag version
            btn_txt = 'GET UPDATE {}'.format(LATEST_VERSION)
            col.operator(
                'wm.url_open', icon='FILE_REFRESH', text=btn_txt
            ).url = LATEST_URL
        col.separator()

        col.operator(
            'wm.url_open', icon='QUESTION', text='Tool Wiki'
        ).url = 'https://github.com/ross-g/io_pdx_mesh/wiki'
        col.operator(
            'wm.url_open', icon='QUESTION', text='Paradox forums'
        ).url = 'https://forum.paradoxplaza.com/forum/index.php?forums/clausewitz-maya-exporter-modding-tool.935/'
        col.operator(
            'wm.url_open', icon='QUESTION', text='Source code'
        ).url = 'https://github.com/ross-g/io_pdx_mesh'
