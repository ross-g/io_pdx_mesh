"""
    IO PDX Mesh Python module.
    Supports Maya 2012 and up.

    author : ross-g
"""

try:
    # if running from Maya, launch the Maya UI
    import maya.cmds
    print("[io_pdx_mesh] __init__")
    import pdx_maya.maya_ui
    reload(pdx_maya.maya_ui)
    pdx_maya.maya_ui.main()
except:
    raise
