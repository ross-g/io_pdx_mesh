"""
    IO PDX Mesh Python module.
    Collection of shared library functions and constants.

    author : ross-g
"""

import re


PDX_SHADER = "shader"
PDX_ANIMATION = "animation"
PDX_IGNOREJOINT = "pdxIgnoreJoint"
PDX_MESHINDEX = "meshindex"
PDX_MAXSKININFS = 4
PDX_MAXUVSETS = 4

LOD_PATTERN = r".*_?LOD_?(?P<level>\d)"  # allow LODX or LOD_X, with or without any kind of prefix


def get_lod_level(*names):
    for name in names:
        lod_match = re.match(LOD_PATTERN, name, re.IGNORECASE)
        if lod_match:
            return int(lod_match.groupdict()["level"])
