"""
    IO PDX Mesh Python module.
    Collection of shared library functions and constants.

    author : ross-g
"""

import re
import logging
import functools


PDX_SHADER = "shader"
PDX_ANIMATION = "animation"
PDX_IGNOREJOINT = "pdxIgnoreJoint"
PDX_MESHINDEX = "meshindex"
PDX_MAXSKININFS = 4
PDX_MAXUVSETS = 4

PDX_DECIMALPTS = 5
PDX_ROUND_ROT = 4
PDX_ROUND_TRANS = 3
PDX_ROUND_SCALE = 2

LOD_PATTERN = r".*_?LOD_?(?P<level>\d)"  # allow LODX or LOD_X, with or without any kind of prefix


def get_lod_level(*names):
    for name in names:
        lod_match = re.match(LOD_PATTERN, name, re.IGNORECASE)
        if lod_match:
            return int(lod_match.group("level"))


def allow_debug_logging(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        debug_enabled = kwargs.get("debug_mode", False)

        # enabled debug logging level
        if debug_enabled:
            root_level = logging.root.level
            io_pdx_level = logging.getLogger("io_pdx").level
            logging.root.setLevel(logging.DEBUG)
            logging.getLogger("io_pdx").setLevel(logging.DEBUG)

        value = func(*args, **kwargs)

        # restore logging level
        if debug_enabled:
            logging.root.setLevel(root_level)
            logging.getLogger("io_pdx").setLevel(io_pdx_level)

        return value

    return wrapper
