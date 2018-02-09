"""
    Paradox asset files, Blender import/export.

    author : ross-g
"""

if 'bpy' in locals():
    import importlib
    if 'blender_import_export' in locals():
        importlib.reload(blender_import_export)
    if 'blender_ui' in locals():
        importlib.reload(blender_ui)

import os
import bpy
from bpy.types import PropertyGroup
from bpy.props import PointerProperty, StringProperty, BoolProperty, EnumProperty, IntProperty

from . import blender_import_export, blender_ui


""" ====================================================================================================================
    Tool properties, stored at scene level.
========================================================================================================================
"""


class PDXBlender_settings(PropertyGroup):
    setup_engine = EnumProperty(
        name='Engine',
        description='Engine',
        items=blender_ui.get_engine_list
    )
    setup_fps = IntProperty(
        name='Animation fps',
        description='Animation fps',
        min=1,
        default=15,
        update=blender_ui.set_animation_fps
    )
    chk_merge_vtx = BoolProperty(
        name='Merge vertices',
        description='Merge vertices',
        default=True,
    )
    chk_merge_obj = BoolProperty(
        name='Merge objects',
        description='Merge objects',
        default=True,
    )
    # chk_create = BoolProperty(
    #     name='Create .gfx and .asset',
    #     description='Create .gfx and .asset',
    #     default=False,
    # )
    # chk_preview = BoolProperty(
    #     name='Preview on export',
    #     description='Preview on export',
    #     default=False,
    # )


""" ====================================================================================================================
    Registered classes for the import/export tool.
========================================================================================================================
"""


classes = [
    PDXBlender_settings,
    blender_ui.popup_message,
    blender_ui.import_mesh,
    blender_ui.export_mesh,
    blender_ui.show_axis,
    blender_ui.edit_settings,
    blender_ui.PDXblender_file_ui,
    blender_ui.PDXblender_tools_ui,
    blender_ui.PDXblender_setup_ui,
    blender_ui.PDXblender_help_ui
]


""" ====================================================================================================================
    Main entry point.
========================================================================================================================
"""


def register():
    print("[io_pdx_mesh] Loading Blender UI.")
    import importlib
    importlib.reload(blender_import_export)
    importlib.reload(blender_ui)

    for cls in classes:
        bpy.utils.register_class(cls)

    # initialise tool properties to scene
    bpy.types.Scene.io_pdx_settings = PointerProperty(type=PDXBlender_settings)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    # remove tool properties from scene
    del bpy.types.Scene.io_pdx_settings
