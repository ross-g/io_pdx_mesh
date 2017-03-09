"""
    Paradox asset files, Blender import/export.

    author : ross-g
"""

bl_info = {
    "name": "IO PDX mesh",
    "author": "ross-g",
    "version": (0, 1),
    "blender": (2, 6, 2),
    "location": "3D View > Toolbox",
    "description": "Import/Export Paradox asset files for the Clausewitz game engine.",
    "warning": "this add-on is beta",
    "wiki_url": "https://github.com/ross-g/io_pdx_mesh",
    "support": "COMMUNITY",
    "category": "Import-Export"
}

if "bpy" in locals():
    import importlib
    importlib.reload(blender_ui)
else:
    import bpy
    from bpy.props import (
            StringProperty,
            BoolProperty,
            IntProperty,
            FloatProperty,
            FloatVectorProperty,
            EnumProperty,
            PointerProperty,
            )
    from bpy.types import (
            Operator,
            AddonPreferences,
            PropertyGroup,
            )
    from . import blender_ui


""" ================================================================================================
    UI class for the import/export tool.
====================================================================================================
"""


class PDXblender_ui(Operator):
    bl_idname = "object.open_pdx_blender_tools"
    bl_label = "Open "


""" ================================================================================================
    Main entry point.
====================================================================================================
"""


def register():
    pass


def unregister():
    pass


if __name__ == "__main__":
    register()
