"""
    Paradox asset files, Blender import/export.

    author : ross-g
"""

import inspect
import importlib

import bpy
from bpy.types import PropertyGroup
from bpy.props import PointerProperty, CollectionProperty, StringProperty, BoolProperty, EnumProperty, IntProperty

from .. import IO_PDX_LOG

from . import blender_import_export, blender_ui

importlib.reload(blender_import_export)
importlib.reload(blender_ui)


""" ====================================================================================================================
    Tool properties, stored at scene level.
========================================================================================================================
"""


# fmt:off
class PDXBlender_settings(PropertyGroup):
    setup_engine: EnumProperty(
        name="Engine",
        description="Engine",
        items=blender_ui.get_engine_list,
    )
    setup_fps: IntProperty(
        name="Animation fps",
        description="Animation fps",
        min=1,
        default=15,
        update=blender_ui.set_animation_fps,
    )


class PDXMaterial_settings(PropertyGroup):
    mat_name: StringProperty(
        name="Material name",
        description="Material name",
        default="",
    )
    mat_type: StringProperty(
        name="Shader type",
        description="Shader type",
        default="",
    )


class PDXObject_Pointer(PropertyGroup):
    ref: PointerProperty(
        name='pdx pointer',
        type=bpy.types.Object,
    )


class PDXObject_Group(PropertyGroup):
    coll: CollectionProperty(
        type=PDXObject_Pointer,
    )
    idx: IntProperty()     # index for the collection


class PDXExport_settings(PropertyGroup):
    custom_range: BoolProperty(
        name='Custom range',
        description='Custom range',
        default=False,
    )
# fmt:on


""" ====================================================================================================================
    Registered classes for the import/export tool.
========================================================================================================================
"""


classes = [PDXBlender_settings, PDXMaterial_settings, PDXObject_Pointer, PDXObject_Group, PDXExport_settings]

# Append classes dynamically from submodules
for name, obj in inspect.getmembers(blender_ui, inspect.isclass):
    if obj.__module__.startswith(__name__) and hasattr(obj, "bl_rna"):
        classes.append(obj)

# Sort based on possible class attribute panel_order so we can set UI rollout order in the tool panel
classes.sort(key=lambda cls: cls.panel_order if hasattr(cls, "panel_order") else 0)


""" ====================================================================================================================
    Main entry point.
========================================================================================================================
"""


def register():
    IO_PDX_LOG.info("Loading Blender UI.")
    import importlib

    importlib.reload(blender_import_export)
    importlib.reload(blender_ui)

    for cls in classes:
        bpy.utils.register_class(cls)

    # initialise tool properties to scene
    bpy.types.Scene.io_pdx_settings = PointerProperty(type=PDXBlender_settings)
    bpy.types.Scene.io_pdx_material = PointerProperty(type=PDXMaterial_settings)
    bpy.types.Scene.io_pdx_group = PointerProperty(type=PDXObject_Group)
    bpy.types.Scene.io_pdx_export = PointerProperty(type=PDXExport_settings)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    # remove tool properties from scene
    del bpy.types.Scene.io_pdx_settings
    del bpy.types.Scene.io_pdx_material
    del bpy.types.Scene.io_pdx_group
    del bpy.types.Scene.io_pdx_export
