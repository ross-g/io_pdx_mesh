import sys

from . import (
    appdirs,  # type: ignore
    click,  # type: ignore
    six,  # type: ignore  # TODO: drop along with Py2 support
)

try:
    # Py 3.4
    import pathlib
except ImportError:
    from . import scandir  # type: ignore  # TODO: drop along with Py2 support

    sys.modules["scandir"] = scandir
    from . import pathlib2 as pathlib  # type: ignore  # TODO: drop along with Py2 support


try:
    # Py 3.11
    import tomllib  # type: ignore
except ImportError:
    from . import toml_tools as tomllib  # type: ignore

__all__ = [
    "appdirs",
    "click",
    "pathlib",
    "scandir",
    "six",
    "tomllib",
]
