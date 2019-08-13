"""
    IO PDX Mesh Python module.
    Supports Maya 2012 and up, supports Blender 2.78 and up.

    author : ross-g
"""

import sys
import site
import inspect
import logging
import traceback
import os.path as path

from .settings import PDXsettings


bl_info = {
    'author': 'ross-g',
    'name': 'IO PDX Mesh',
    'description': 'Import/Export Paradox asset files for the Clausewitz game engine.',
    'location': '3D View > Toolbox',
    'category': 'Import-Export',
    'support': 'COMMUNITY',
    'blender': (2, 78, 0),
    'maya': (2012),
    'version': (0, 6),
    'warning': 'this add-on is beta',
    'wiki_url': 'https://github.com/ross-g/io_pdx_mesh',
    'repo_name': 'io_pdx_mesh',
}


""" ====================================================================================================================
    Setup.
========================================================================================================================
"""

app = path.split(sys.executable)[1]
root_path = path.abspath(path.dirname(inspect.getfile(inspect.currentframe())))

# setup module logging
logging.basicConfig(level=logging.DEBUG, format='[%(name)s] %(levelname)s:  %(message)s')
IO_PDX_LOG = logging.getLogger('io_pdx_mesh')
IO_PDX_LOG.info("Running from {0}".format(app))
IO_PDX_LOG.info(root_path)

# setup module preferences
site.addsitedir(path.join(root_path, 'external'))
from appdirs import user_data_dir  # noqa

config_path = path.join(user_data_dir(bl_info['name'], False), 'settings.json')
IO_PDX_SETTINGS = PDXsettings(config_path)


""" ====================================================================================================================
    Startup.
========================================================================================================================
"""

# check if running in Blender
if 'blender' in app.lower():
    import bpy  # noqa

    try:
        # register the Blender addon
        from .pdx_blender import register, unregister  # noqa
    except Exception as e:
        traceback.print_exc()
        raise e

# otherwise running in Maya
if 'maya' in app.lower():
    import maya.cmds  # noqa

    try:
        # launch the Maya UI
        from .pdx_maya import maya_ui

        reload(maya_ui)
        maya_ui.main()
    except Exception as e:
        traceback.print_exc()
        raise e
