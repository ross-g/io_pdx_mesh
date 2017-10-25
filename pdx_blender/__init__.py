"""
    Paradox asset files, Blender import/export.

    author : ross-g
"""

if "bpy" in locals():
    import importlib
    importlib.reload(blender_import_export)
    importlib.reload(blender_ui)
else:
    import bpy
    from . import blender_import_export, blender_ui


""" ====================================================================================================================
    Registered classes for the import/export tool.
========================================================================================================================
"""


classes = [
    blender_ui.PDXblender_import_ui,
    blender_ui.PDXblender_export_ui,
    blender_ui.importmesh
]


""" ====================================================================================================================
    Main entry point.
========================================================================================================================
"""


def register():
    import importlib
    importlib.reload(blender_import_export)
    importlib.reload(blender_ui)

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
