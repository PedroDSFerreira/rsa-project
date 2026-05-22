import importlib
import pkgutil
from pathlib import Path

from algorithms.base import Algorithm, _registry, register

# Auto-import every module in this package so their @register decorators run.
_package_path = str(Path(__file__).parent)
for _mod_info in pkgutil.iter_modules([_package_path]):
    if _mod_info.name not in ("base",):
        importlib.import_module(f"algorithms.{_mod_info.name}")


def available_algorithms() -> list[str]:
    return list(_registry.keys())


def make_algorithm(name: str) -> Algorithm:
    try:
        return _registry[name]()
    except KeyError:
        raise ValueError(
            f"Unknown algorithm {name!r}. Available: {available_algorithms()}"
        )
