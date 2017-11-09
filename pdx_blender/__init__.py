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

import bpy
from . import blender_import_export, blender_ui


""" ====================================================================================================================
    Registered classes for the import/export tool.
========================================================================================================================
"""


classes = [
    blender_ui.import_mesh,
    blender_ui.edit_settings,
    blender_ui.PDXblender_import_ui,
    blender_ui.PDXblender_export_ui,
    blender_ui.PDXblender_setup_ui
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


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
