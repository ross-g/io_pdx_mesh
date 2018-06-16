"""
    IO PDX Mesh Python module.
    Supports Maya 2012 and up.

    author : ross-g
"""

import os
import sys


app = os.path.split(sys.executable)[1]
print('[io_pdx_mesh] __init__ (running from {})'.format(app))


# running in Maya
if 'maya' in app.lower():
    import maya.cmds

    try:
        # launch the Maya UI
        import pdx_maya.maya_ui
        reload(pdx_maya.maya_ui)
        pdx_maya.maya_ui.main()
    except Exception as e:
        print sys.exc_info()
        raise e
