"""
Paradox asset files, Blender import/export.

author : ross-g
"""

import importlib
import inspect

import bpy  # type: ignore
from bpy.props import (  # type: ignore
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup  # type: ignore

from .. import ENGINE_SETTINGS, IO_PDX_LOG, IO_PDX_SETTINGS
from . import blender_import_export, blender_ui

importlib.reload(blender_import_export)
importlib.reload(blender_ui)


""" ====================================================================================================================
    Tool properties, stored at scene level.
========================================================================================================================
"""


# fmt:off
class PDXBlender_settings(PropertyGroup):
    engine_items = [(engine, ) * 3 for engine in ENGINE_SETTINGS]
    engine_default = IO_PDX_SETTINGS.last_set_engine or list(ENGINE_SETTINGS)[0]

    setup_engine: EnumProperty(
        name="Engine",
        description="Engine",
        items=engine_items,
        default=engine_default,
        update=blender_ui.set_engine,
    )


class PDXMaterial_settings(PropertyGroup):
    mat_name: StringProperty(
        name="Material name",
        description="Material name",
        default="",
    )
    mat_type: StringProperty(
        name="Material type",
        description="Material type",
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
for _name, obj in inspect.getmembers(blender_ui, inspect.isclass):
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
