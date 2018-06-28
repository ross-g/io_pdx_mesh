"""
    IO PDX Mesh Python module.
    Supports Maya 2012 and up, supports Blender 2.78 and up.

    author : ross-g
"""

import os
import sys
import inspect

bl_info = {
    'name': 'IO PDX mesh',
    'author': 'ross-g',
    'blender': (2, 78, 0),
    'location': '3D View > Toolbox',
    'description': 'Import/Export Paradox asset files for the Clausewitz game engine.',
    'warning': 'this add-on is beta',
    'wiki_url': 'https://github.com/ross-g/io_pdx_mesh',
    'support': 'COMMUNITY',
    'category': 'Import-Export',
}

app = os.path.split(sys.executable)[1]
root_path = os.path.dirname(inspect.getfile(inspect.currentframe()))
print('[io_pdx_mesh] Running from {}'.format(app))
print('[io_pdx_mesh] {}'.format(root_path))

# check if running in Blender
if 'blender' in app.lower():
    import bpy

    try:
        # register the Blender addon
        from .pdx_blender import register, unregister
    except Exception as e:
        print(sys.exc_info())
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
        print(sys.exc_info())
        raise e
