"""
    IO PDX Mesh Python module.
    Supports Maya 2018 and up, supports Blender 2.83 and up.

    author : ross-g
"""

from __future__ import unicode_literals

import sys
import site
import json
import inspect
import logging
import zipfile
import traceback
import os.path as path
from imp import reload
from collections import OrderedDict

from .settings import PDXsettings

# vendored package imports
root_path = path.abspath(path.dirname(inspect.getfile(inspect.currentframe())))
site.addsitedir(path.join(root_path, "external"))
from appdirs import user_data_dir  # noqa

# Py2, Py3 compatibility
PY2 = sys.version_info[0] < 3


bl_info = {
    "author": "ross-g",
    "name": "IO PDX Mesh",
    "description": "Import/Export Paradox asset files for the Clausewitz game engine.",
    "location": "3D View > Toolbox",
    "category": "Import-Export",
    "support": "COMMUNITY",
    "blender": (2, 83, 0),
    "maya": (2018),
    "version": (0, 8),
    "warning": "this add-on is beta",
    "project_name": "io_pdx_mesh",
    "project_url": "https://github.com/ross-g/io_pdx_mesh",
    "doc_url": "https://github.com/ross-g/io_pdx_mesh/wiki",
    "tracker_url": "https://github.com/ross-g/io_pdx_mesh/issues",
    "forum_url": "https://forum.paradoxplaza.com/forum/index.php?forums/clausewitz-maya-exporter-modding-tool.935/",
}


""" ====================================================================================================================
    Setup.
========================================================================================================================
"""


# setup module logging
log_name = bl_info["project_name"]
log_format = "[%(name)s] %(levelname)s:  %(message)s"
log_lvl = logging.INFO

# setup module preferences
config_path = path.join(user_data_dir(bl_info["project_name"], False), "settings.json")
IO_PDX_SETTINGS = PDXsettings(config_path)

# setup engine/export settings
export_settings = path.join(root_path, "clausewitz.json")
ENGINE_SETTINGS = {}
try:
    if ".zip" in export_settings:
        zipped = export_settings.split(".zip")[0] + ".zip"
        with zipfile.ZipFile(zipped, "r") as z:
            f = z.open("io_pdx_mesh/clausewitz.json")
            ENGINE_SETTINGS = json.loads(f.read(), object_pairs_hook=OrderedDict)
    else:
        with open(export_settings, "rt") as f:
            ENGINE_SETTINGS = json.load(f, object_pairs_hook=OrderedDict)
except Exception as err:
    print(err)
    msg = (
        "CRITICAL ERROR! Your 'clausewitz.json' settings file has errors and is unreadable."
        "Some functions of the tool will not work without these settings."
    )
    raise RuntimeError(msg)


""" ====================================================================================================================
    Startup.
========================================================================================================================
"""

IO_PDX_LOG, running_from, version = None, None, None
environment = sys.executable.lower()

# check if running from Blender
try:
    import bpy  # noqa
    running_from, version = bpy.app.binary_path.lower(), bpy.app.version
except ImportError:
    pass
else:
    logging.basicConfig(level=log_lvl, format=log_format)
    IO_PDX_LOG = logging.getLogger(log_name)

    if version < bl_info["blender"]:
        IO_PDX_LOG.warning("UNSUPPORTED VERSION! Update to Blender {0}".format(bl_info["blender"]))
        bl_info["unsupported_version"] = True

    try:
        # register the Blender addon
        from .pdx_blender import register, unregister  # noqa
    except Exception as e:
        traceback.print_exc()
        raise e

# or running from Maya
try:
    import maya.cmds  # noqa
    running_from, version = sys.executable.lower(), int(maya.cmds.about(version=True))
except ImportError:
    pass
else:
    IO_PDX_LOG = logging.getLogger(log_name)
    IO_PDX_LOG.setLevel(log_lvl)
    IO_PDX_LOG.propagate = False
    IO_PDX_LOG.handlers = []
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(log_format))
    IO_PDX_LOG.addHandler(console)

    if version < bl_info["maya"]:
        IO_PDX_LOG.warning("UNSUPPORTED VERSION! Update to Maya {0}".format(bl_info["maya"]))
        bl_info["unsupported_version"] = True

    try:
        # launch the Maya UI
        from .pdx_maya import maya_ui
        reload(maya_ui)
        maya_ui.main()
    except Exception as e:
        traceback.print_exc()
        raise e

if running_from is not None:
    IO_PDX_LOG.info("Running from {0} ({1})".format(running_from, version))
    IO_PDX_LOG.info(root_path)
# otherwise, we don't support running with UI setup
else:
    logging.basicConfig(level=logging.DEBUG, format=log_format)
    IO_PDX_LOG = logging.getLogger(log_name)
    IO_PDX_LOG.warning('Running without UI from environment "{0}"'.format(sys.executable))
