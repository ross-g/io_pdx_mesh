import inspect
import os.path as path
import site

external_path = path.abspath(path.dirname(inspect.getfile(inspect.currentframe())))
site.addsitedir(external_path)

import six  # noqa
import click  # noqa
import appdirs  # noqa
import scandir  # noqa

try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib  # noqa

__all__ = [
    "six",
    "click",
    "appdirs",
    "scandir",
    "pathlib",
]
