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
import inspect
import json
import bpy
from bpy.types import PropertyGroup
from bpy.props import PointerProperty, StringProperty, BoolProperty, EnumProperty, IntProperty

from . import blender_import_export, blender_ui


""" ====================================================================================================================
    Variables and Helper functions.
========================================================================================================================
"""


_script_dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
settings_file = os.path.join(os.path.split(_script_dir)[0], 'clausewitz.json')


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


class PDXBlender_settings(PropertyGroup):
    settings = load_settings()     # settings from json

    setup_engine = EnumProperty(
            name='Engine',
            description='Engine',
            items=((engine, engine, '') for engine in sorted(settings.keys())),
            default=sorted(settings.keys())[-1]
        )
    setup_fps = IntProperty(
            name='Animation fps',
            description='Animation fps',
            min=0,
            default=15
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
    chk_create = BoolProperty(
            name='Create .gfx and .asset',
            description='Create .gfx and .asset',
            default=False,
        )
    chk_preview = BoolProperty(
            name='Preview on export',
            description='Preview on export',
            default=False,
        )



""" ====================================================================================================================
    Registered classes for the import/export tool.
========================================================================================================================
"""


classes = [
    PDXBlender_settings,
    blender_ui.import_mesh,
    blender_ui.edit_settings,
    blender_ui.PDXblender_file_ui,
    blender_ui.PDXblender_setup_ui,
    blender_ui.PDXblender_help_ui
]


""" ====================================================================================================================
    Main entry point.
========================================================================================================================
"""


def register():
    # try:
    #     unregister()
    # except:
    #     pass

    print("[io_pdx_mesh] Loading Blender UI.")
    import importlib
    importlib.reload(blender_import_export)
    importlib.reload(blender_ui)

    for cls in classes:
        bpy.utils.register_class(cls)

    # initialise tool properties
    bpy.types.Scene.io_pdx_mesh_settings = PointerProperty(type=PDXBlender_settings)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
