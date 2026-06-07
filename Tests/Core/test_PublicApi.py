"""Unit tests de la fachada pública (sin BD). Espeja src/tequio/__init__.py.

Dos contratos:
  1. `import tequio` a secas es LIBRE de efectos colaterales (no instancia Celery ni
     toca el Core) — se verifica en un subproceso limpio, porque el proceso de pytest
     ya trae medio framework importado por los demás tests.
  2. Cada símbolo de `__all__` resuelve vía `__getattr__` (PEP 562) al MISMO objeto
     que exporta su módulo canónico, y la fachada se mantiene en sync con `_EXPORTS`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

import tequio

# Sonda que corre en un intérprete limpio: importa la fachada y falla RUIDOSO si eso
# arrastró Celery o cualquier submódulo de tequio (la pereza es el contrato).
_PROBE = """
import sys

import tequio

cargados = [
    m for m in sys.modules
    if m == "celery" or m.startswith("celery.") or m.startswith("tequio.")
    if m != "tequio"
]
assert not cargados, f"import tequio arrastro side effects: {cargados}"
"""


def test_import_tequio_no_tiene_efectos_colaterales() -> None:
    src = str(Path(__file__).resolve().parents[2] / "src")
    resultado = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env={**os.environ, "PYTHONPATH": src},
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_all_esta_ordenado_y_en_sync_con_exports() -> None:
    assert list(tequio.__all__) == sorted(tequio._EXPORTS), "__all__ debe listar exactamente _EXPORTS, ordenado"


def test_cada_simbolo_resuelve_al_objeto_de_su_modulo_canonico() -> None:
    for nombre in tequio.__all__:
        canonico = getattr(import_module(tequio._EXPORTS[nombre]), nombre)
        assert getattr(tequio, nombre) is canonico, f"tequio.{nombre} no es el objeto canónico"


def test_acceso_cachea_en_el_modulo() -> None:
    vars(tequio).pop("job", None)  # fuerza el camino de __getattr__
    _ = tequio.job
    assert "job" in vars(tequio)  # el segundo acceso ya no pasa por __getattr__


def test_atributo_inexistente_levanta_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no_existe"):
        _ = tequio.no_existe  # mypy no se queja: con __getattr__ el atributo tipa como Any


def test_dir_lista_la_fachada_completa() -> None:
    assert set(tequio.__all__) <= set(dir(tequio))
