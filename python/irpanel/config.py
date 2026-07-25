"""Load the shared config.yml and resolve its paths.

The same config.yml drives the R and Python implementations. Relative paths in
it are relative to the repo root (the directory holding config.yml); this
module resolves them to absolute Paths. Python outputs go to a py/ subdirectory
of the output path so the two implementations never overwrite each other.
"""

from pathlib import Path

import yaml


def find_repo_root(start=None):
    """Walk up from start (default: this file) to the directory with config.yml.

    :param start: path to start from; defaults to this module's location.
    :return: Path of the repo root.
    """
    p = Path(start) if start else Path(__file__).resolve()
    for parent in (p, *p.parents):
        if (parent / "config.yml").is_file() and (parent / "R").is_dir():
            return parent
    raise FileNotFoundError("config.yml not found above " + str(p))


def load_config(root=None):
    """Read config.yml and resolve paths.

    :param root: repo root; found automatically when omitted.
    :return: dict as in config.yml, with paths.* as absolute Path objects and
        an added paths.output_py (data/output/py) for Python-side outputs.
    """
    root = Path(root) if root else find_repo_root()
    with open(root / "config.yml") as f:
        config = yaml.safe_load(f)
    paths = config["paths"]
    for key, val in paths.items():
        p = Path(val)
        paths[key] = p if p.is_absolute() else (root / p).resolve()
    paths["output_py"] = paths["output"] / "py"
    return config
