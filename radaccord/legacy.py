"""Load unchanged scientific sources under private package names.

The source checkout keeps these files in software/. Wheels place the exact
same bytes in radaccord/_frozen/. A module-local import hook resolves the one
historical absolute import without changing sys.path or public module aliases.
"""
from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
import sys


_directory = Path(__file__).resolve().parent / "_frozen"
if not _directory.is_dir():
    _directory = Path(__file__).resolve().parents[1] / "software"


def _load(name, dependencies=None):
    qualified = "radaccord._frozen_" + name
    if qualified in sys.modules:
        return sys.modules[qualified]
    spec = importlib.util.spec_from_file_location(qualified, _directory / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    if dependencies:
        def local_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and name in dependencies:
                return dependencies[name]
            return builtins.__import__(name, globals, locals, fromlist, level)
        module.__dict__["__builtins__"] = {**vars(builtins), "__import__": local_import}
    sys.modules[qualified] = module  # Dataclass type resolution requires this entry.
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(qualified, None)
        raise
    return module


physical_contracts = _load("physical_contracts")
sampling_contracts = _load("sampling_contracts", {"physical_contracts": physical_contracts})
Frame = physical_contracts.Frame
sampling_witness = sampling_contracts.sampling_witness


if __name__ == "__main__":
    # The historical CLI changes its own import path. Isolate this behaviour
    # in the command subprocess; neither alias exists in callers of the API.
    import runpy
    sys.modules["physical_contracts"] = physical_contracts
    sys.modules["sampling_contracts"] = sampling_contracts
    runpy.run_module("radaccord_sampling", run_name="__main__")

