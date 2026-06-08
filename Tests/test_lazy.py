"""Tests de tequio.lazy: import perezoso (difiere hasta el primer uso)."""

from __future__ import annotations

import sys

import pytest

from tequio import lazy as lazy_mod


def test_load_defers_until_first_attribute_access() -> None:
    """`load` devuelve un módulo _LazyModule (no ejecutado); el primer acceso lo carga."""
    sys.modules.pop("colorsys", None)  # asegurar que NO esté cargado
    mod = lazy_mod.load("colorsys")
    assert type(mod).__name__ == "_LazyModule"  # diferido, no ejecutado
    _ = mod.rgb_to_hls  # primer acceso -> dispara la carga real
    assert type(sys.modules["colorsys"]).__name__ == "module"  # ya ejecutado


def test_from_tequio_lazy_import_works() -> None:
    """`from tequio.lazy import X` (PEP 562) devuelve el módulo X perezoso y usable."""
    from tequio.lazy import json  # pasa por __getattr__

    assert json.dumps({"a": 1}) == '{"a": 1}'


def test_load_is_idempotent() -> None:
    """Si ya está cargado, lo devuelve tal cual (no re-envuelve)."""
    import math

    assert lazy_mod.load("math") is math


def test_unknown_module_raises() -> None:
    with pytest.raises(ModuleNotFoundError):
        lazy_mod.load("modulo_que_no_existe_xyz_123")


def test_dunder_attrs_are_not_treated_as_modules() -> None:
    """`__path__` y demás dunders NO se intentan cargar como libs (raise AttributeError)."""
    with pytest.raises(AttributeError):
        lazy_mod.__getattr__("__path__")
