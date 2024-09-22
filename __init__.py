"""
IO PDX Mesh Python module.
Supports Maya 2018 and up, supports Blender 2.83 and up.

author : ross-g
"""

from __future__ import unicode_literals

import inspect
import json
import logging
import os.path as path
import sys
import traceback
import zipfile
from collections import OrderedDict
from imp import reload

# vendored package imports
from .external import tomllib
from .external.appdirs import user_data_dir  # user settings directory
from .settings import PDXsettings

bl_info = {  # legacy support: Blender < 4.2
    "author": "ross-g",
    "name": "IO PDX Mesh",
    "description": "Import/Export Paradox asset files for the Clausewitz game engine.",
    "location": "3D Viewport: View > Sidebar (N to toggle)",
    "category": "Import-Export",
    "support": "COMMUNITY",
    "blender": (3, 6, 4),
}
root_path = path.abspath(path.dirname(inspect.getfile(inspect.currentframe())))
with open(path.join(root_path, "blender_manifest.toml"), "rb") as fh:
    IO_PDX_INFO = tomllib.load(fh)


""" ====================================================================================================================
    Setup.
========================================================================================================================
"""


# setup module logging
log_name = "io_pdx"
log_format = "[%(name)s] %(levelname)s:  %(message)s"
log_lvl = logging.INFO

# setup module preferences
config_path = path.join(user_data_dir(IO_PDX_INFO["id"], False), "settings.json")
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
    raise RuntimeError(msg)  # noqa: B904


""" ====================================================================================================================
    Startup.
========================================================================================================================
"""

IO_PDX_LOG, running_from, version = None, None, None
environment = sys.executable.lower()

# check if running from Blender
try:
    import bpy  # type: ignore

    running_from, version = bpy.app.binary_path.lower(), bpy.app.version
except ImportError:
    pass
else:
    logging.basicConfig(level=log_lvl, format=log_format)
    IO_PDX_LOG = logging.getLogger(log_name)

    min_version = tuple(IO_PDX_INFO["blender_support_min"])
    if version < min_version:
        IO_PDX_LOG.warning("UNSUPPORTED VERSION! Update to Blender {0}".format(min_version))
        IO_PDX_INFO["unsupported_version"] = True

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

    min_version = tuple(IO_PDX_INFO["maya_support_min"])[0]
    if version < min_version:
        IO_PDX_LOG.warning("UNSUPPORTED VERSION! Update to Maya {0}".format(min_version))
        IO_PDX_INFO["unsupported_version"] = True

    try:
        # launch the Maya UI
        from .pdx_maya import maya_ui

        reload(maya_ui)
        maya_ui.main()
    except Exception as e:
        traceback.print_exc()
        raise e

if running_from is not None:
    IO_PDX_LOG.info("Running {0} from {1} ({2})".format(__package__, running_from, version))
    IO_PDX_LOG.info(root_path)
# otherwise, we don't support running with UI setup
else:
    logging.basicConfig(level=logging.DEBUG, format=log_format)
    IO_PDX_LOG = logging.getLogger(log_name)
    IO_PDX_LOG.warning('Running without UI from environment "{0}"'.format(sys.executable))
