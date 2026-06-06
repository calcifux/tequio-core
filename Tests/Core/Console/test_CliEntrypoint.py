"""Guardrail e2e del entry point `tequio` (separado del launcher ./jornal de test_JornalLauncher).

Arranca el CLI del paquete tal como lo haría el script instalado `tequio` (declarado en pyproject
como `tequio = tequio.Core.Console.Cli:run`), pero por subproceso vía `python -m
tequio.Core.Console.Cli` — más portable que apuntar al script del venv: `Cli.py` tiene su
`if __name__ == "__main__": run()`, así que `-m` arranca exactamente el mismo `run()`.

Cubre que el script instalado arranca, descubre los comandos y lista la tabla 'Labores del tequio'
con exit 0. Reemplaza, para el lado worker, al e2e jornal+scaffold de milpa.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Raíz del repo: paridad con test_JornalLauncher (cwd estable, encuentra logs/ si aplica).
_ROOT = Path(__file__).resolve().parents[3]


def test_tequio_entrypoint_lists_commands() -> None:
    """`tequio list` (vía `python -m tequio.Core.Console.Cli list`) sale con código 0 y muestra
    la tabla de labores."""
    result = subprocess.run(
        [sys.executable, "-m", "tequio.Core.Console.Cli", "list"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": "sqlite://"},  # arranca sin .env (CI)
        timeout=60,
    )

    assert result.returncode == 0, (
        f"`tequio list` falló (código {result.returncode}).\n"
        f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}"
    )
    assert "Labores del tequio" in result.stdout  # el título de la tabla del `list`
