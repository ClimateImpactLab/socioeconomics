"""Load a track config and resolve its paths.

The same config files drive the R and Python implementations, one per track
under configs/ (climate-compensation is the book reproduction and the
default; new-socioeconomics is the updated panel). IRPANEL_CONFIG selects
the config path; relative paths in it are relative to the repo root, and
this module resolves them to absolute Paths. Python outputs go to a py/
subdirectory of the output path so the two implementations never overwrite
each other.
"""

import os
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path("configs") / "climate-compensation.yml"


def find_repo_root(start=None):
    """Walk up from start (default: this file) to the repo root.

    :param start: path to start from; defaults to this module's location.
    :return: Path of the repo root (the directory with configs/ and R/).
    """
    p = Path(start) if start else Path(__file__).resolve()
    for parent in (p, *p.parents):
        if (parent / "configs").is_dir() and (parent / "R").is_dir():
            return parent
    raise FileNotFoundError("repo root (configs/ + R/) not found above "
                            + str(p))


def load_config(root=None):
    """Read the track config and resolve paths.

    The config file is taken from the IRPANEL_CONFIG environment variable,
    defaulting to configs/climate-compensation.yml; a relative value is
    resolved against the repo root.

    :param root: repo root; found automatically when omitted.
    :return: dict as in the config file, with paths.* as absolute Path
        objects and added paths.output_py (output/py) and paths.cache_py
        (cache/py) for Python-side outputs, so the R cache and outputs
        stay intact.
    """
    root = Path(root) if root else find_repo_root()
    cfg_path = Path(os.environ.get("IRPANEL_CONFIG", DEFAULT_CONFIG))
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    with open(cfg_path) as f:
        config = yaml.safe_load(f)
    paths = config["paths"]
    for key, val in paths.items():
        p = Path(val)
        paths[key] = p if p.is_absolute() else (root / p).resolve()
    paths["output_py"] = paths["output"] / "py"
    paths["cache_py"] = paths["cache"] / "py"
    return config
