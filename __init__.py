"""
    IO PDX Mesh Python module.
    Supports Maya 2012 and up, supports Blender 2.78 and up.

    author : ross-g
"""

import os
import sys

bl_info = {
    'name': 'IO PDX mesh',
    'author': 'ross-g',
    'blender': (2, 78, 0),
    'location': '3D View > Toolbox',
    'description': 'Import/Export Paradox asset files for the Clausewitz game engine.',
    'warning': 'this add-on is beta',
    'wiki_url': 'https://github.com/ross-g/io_pdx_mesh',
    'support': 'COMMUNITY',
    'category': 'Import-Export'
}

print('[io_pdx_mesh] __init__ (running from {})'.format(os.path.split(sys.executable)[1]))


# check if running in Blender
try:
    import bpy
    
    # register the Blender addon
    from .pdx_blender import register, unregister

# otherwise running in Maya
except ImportError:
    import maya.cmds

    # launch the Maya UI
    import pdx_maya.maya_ui
    reload(pdx_maya.maya_ui)
    pdx_maya.maya_ui.main()
