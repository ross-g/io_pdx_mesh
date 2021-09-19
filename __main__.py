import sys
import site
import json
import warnings
from os import path

from . import PY2
from .pdx_data import PDXData, PDXDataJSON, read_meshfile

# vendored package imports
from . import root_path

site.addsitedir(path.join(root_path, "external"))
import click  # noqa


""" ====================================================================================================================
    Main.
========================================================================================================================
"""


@click.group()
def cli():
    pass


@cli.command()
@click.option("-i", "--inpath", required=True, type=click.Path())
@click.option("-o", "--outpath", required=False, type=click.Path(), default=None)
@click.option("-f", "--format", "out_format", type=click.Choice(["txt", "json", "xml"]), default="")
def convert_to(inpath, outpath, out_format):
    from pathlib import Path  # noqa

    files = []
    out_folder = None

    inpath = Path(inpath)
    # run on single file
    if inpath.is_file():
        try:
            out_filepath = Path(outpath)  # assumes outpath is a file (not folder)
        except TypeError:
            out_filepath = inpath.parent / inpath.name
        out_folder = out_filepath.parent
        files.append([inpath, out_filepath.with_suffix(f".{out_format}")])

    # run on whole directory, recursively
    elif inpath.is_dir():
        try:
            out_folder = Path(outpath)
        except TypeError:
            out_folder = inpath

        for ext in ["*.mesh", "*.anim"]:
            for fullpath in inpath.rglob(ext):
                files.append([fullpath, (out_folder / fullpath.relative_to(inpath)).with_suffix(f".{out_format}")])

    for i, (in_file, out_file) in enumerate(files):
        pdx_data = PDXData(read_meshfile(str(in_file)))
        if out_format:
            print(f"{i + 1}/{len(files)} : {in_file.relative_to(inpath.parent)} --> {out_file.relative_to(out_folder)}")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(str(out_file), "wt") as fp:
                if out_format == "txt":
                    fp.write(str(pdx_data) + "\n")
                if out_format == "json":
                    json.dump(pdx_data, fp, indent=2, cls=PDXDataJSON)
        else:
            print("-" * 120)
            print(f"{i + 1}/{len(files)} : {in_file.relative_to(inpath.parent)}",  end="\n")
            print(str(pdx_data))


if __name__ == "__main__":
    """When called from the command line we can just print the structure and contents of the .mesh or .anim file to
    stdout or write directly to a text file. """
    if PY2:
        warnings.warn(
            "Commandline mode is only supported under Python 3 (running from {0})".format(
                ".".join(str(c) for c in sys.version_info)
            )
        )
    else:
        cli()
