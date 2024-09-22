import sys

from . import (
    appdirs,  # noqa
    click,  # noqa
    six,  # noqa  # TODO: drop along with Py2 support
)

try:
    # Py 3.4
    import pathlib
except ImportError:
    from . import scandir  # noqa  # TODO: drop along with Py2 support

    sys.modules["scandir"] = scandir
    from . import pathlib2 as pathlib  # noqa  # TODO: drop along with Py2 support


try:
    # Py 3.11
    import tomllib  # noqa
except ImportError:
    from . import toml_tools as tomllib  # noqa

__all__ = [
    "appdirs",
    "click",
    "pathlib",
    "scandir",
    "six",
    "tomllib",
]
