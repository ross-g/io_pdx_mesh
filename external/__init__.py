import os
import sys
import site
import urllib
import inspect
import logging
import subprocess
import os.path as path


external_path = path.abspath(path.dirname(inspect.getfile(inspect.currentframe())))
site.addsitedir(external_path)

EXTERNAL_LOG = logging.getLogger("io_pdx.external")

import six  # noqa
import click  # noqa
import appdirs  # noqa
import scandir  # noqa

try:
    # pathlib is included with Py3
    import pathlib
except ImportError:
    import pathlib2 as pathlib  # noqa

try:
    # numpy is included with Blender, or might have been installed to user site-packages (eg for Maya 2022+)
    import numpy  # noqa

    EXTERNAL_LOG.info("Found numpy at: {}".format(path.dirname(numpy.__file__)))

except ImportError:
    # check if numpy has been installed to external/numpy_maya
    numpy_maya = path.join(external_path, "numpy_maya")
    site.addsitedir(numpy_maya)
    try:
        import numpy  # noqa

    except ImportError:
        # we need to install numpy and possibly pip
        EXTERNAL_LOG.info("Installing numpy package")
        mayapy = path.join(path.dirname(sys.executable), "mayapy.exe")

        # since Maya 2022 (Py3) numpy can just be installed via pip, and pip is included
        if six.PY3 and path.isfile(mayapy):
            try:
                subprocess.check_call(
                    [mayapy, "-m", "pip", "install", "numpy"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                import numpy  # noqa

                EXTERNAL_LOG.info("Installed Numpy at: {}".format(path.dirname(numpy.__file__)))

            except (subprocess.CalledProcessError, ImportError):
                numpy = None
                EXTERNAL_LOG.warning("Failed to install Numpy (from pip)")

        # otherwise try installing pip (after downloading get-pip.py) and loading numpy from a bespoke wheel
        elif path.isfile(mayapy):
            def download_get_pip():  # Py2 only
                file = urllib.URLopener()
                pip_url = "https://bootstrap.pypa.io/pip/{}.{}/get-pip.py".format(*sys.version_info[:2])
                fpath, _ = file.retrieve(pip_url, path.join(os.environ["LOCALAPPDATA"], "get-pip.py"))
                return fpath

            try:
                # first get pip working
                get_pip = download_get_pip()
                subprocess.check_call(
                    [mayapy, get_pip],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                import pip

                EXTERNAL_LOG.info("Installed pip at: {}".format(path.dirname(pip.__file__)))

            except (subprocess.CalledProcessError, ImportError):
                numpy = None
                EXTERNAL_LOG.warning("Failed to install pip (from get-pip.py)")

            try:
                # # then install the bundled numpy wheel
                # numpy_wheel = path.join(numpy_maya, "numpy-1.9.2-cp27-none-win_amd64.whl")
                # subprocess.check_call(
                #     [mayapy, "-m", "pip", "install", "--upgrade", numpy_wheel, "--target", numpy_maya],
                #     creationflags=subprocess.CREATE_NEW_CONSOLE,
                # )
                # then install the numpy wheel from 3rd party package index
                subprocess.check_call(
                    [mayapy, "-m", "pip", "install", "--upgrade",
                    "--index-url", "https://pypi.anaconda.org/carlkl/simple", "numpy", "--target", numpy_maya],
                )
                import numpy  # noqa

                EXTERNAL_LOG.info("Installed Numpy at: {}".format(path.dirname(numpy.__file__)))

            except (subprocess.CalledProcessError, ImportError):
                numpy = None
                EXTERNAL_LOG.warning("Failed to install Numpy (from wheel)")

        else:
            EXTERNAL_LOG.error("Unable to instll pip/numpy using mayapy.exe")


__all__ = [
    "six",
    "click",
    "appdirs",
    "scandir",
    "pathlib",
    "numpy",
]
