"""
    IO PDX Mesh Python module.
    Supports Maya 2012 and up, supports Blender 2.78 and up.

    author : ross-g
"""

import os
import sys
import inspect
import logging
import traceback

bl_info = {
    'name': 'IO PDX mesh',
    'author': 'ross-g',
    'description': 'Import/Export Paradox asset files for the Clausewitz game engine.',
    'blender': (2, 78, 0),
    'maya': (2012),
    'category': 'Import-Export',
    'location': '3D View > Toolbox',
    'support': 'COMMUNITY',
    'version': '0.6',
    'warning': 'this add-on is beta',
    'wiki_url': 'https://github.com/ross-g/io_pdx_mesh',
}

# setup module logging
IO_PDX_LOG = logging.getLogger('io_pdx_mesh')
IO_PDX_LOG.propagate = False
if not IO_PDX_LOG.handlers:
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(logging.Formatter('[%(name)s] %(levelname)s:  %(message)s'))
    IO_PDX_LOG.addHandler(console)

app = os.path.split(sys.executable)[1]
root_path = os.path.dirname(inspect.getfile(inspect.currentframe()))
IO_PDX_LOG.info("Running from {0}".format(app))
IO_PDX_LOG.info(root_path)

# check if running in Blender
if 'blender' in app.lower():
    import bpy

    try:
        # register the Blender addon
        from .pdx_blender import register, unregister
    except Exception as e:
        traceback.print_exc()
        raise e

# otherwise running in Maya
if 'maya' in app.lower():
    import maya.cmds

    try:
        # launch the Maya UI
        from .pdx_maya import maya_ui

        reload(maya_ui)
        maya_ui.main()
    except Exception as e:
        traceback.print_exc()
        raise e
