"""Guardrail: el launcher `jornal` de la raíz DEBE arrancar (importar tequio y correr).

Por qué existe: `jornal` es un script suelto (sin extensión .py) que NINGÚN otro test ejecuta.
Un import roto ahí pasa los gates en silencio — exactamente el tipo de bug que un launcher suelto
esconde (p. ej. importar un símbolo que ya no existe). Este test lo corre como SUBPROCESO, igual
que un usuario haría `python jornal list`, así que cubre tanto la línea de import (`from
tequio.Core.Console.Cli import run`) como la invocación `run()` del `__main__`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Tests/Core/Console/test_JornalLauncher.py -> parents[3] = raíz del repo (donde vive ./jornal).
_JORNAL = Path(__file__).resolve().parents[3] / "jornal"


def test_jornal_launcher_runs() -> None:
    """`python jornal list` debe salir con código 0 y listar comandos."""
    assert _JORNAL.is_file(), f"no se encontró el launcher jornal en {_JORNAL}"

    result = subprocess.run(
        [sys.executable, str(_JORNAL), "list"],
        cwd=_JORNAL.parent,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": "sqlite://"},  # arranca sin .env (CI)
        timeout=60,
    )

    assert result.returncode == 0, (
        f"`jornal list` falló (código {result.returncode}).\n"
        f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}"
    )
    # La tabla de comandos siempre incluye el comando raíz `list`.
    assert "list" in result.stdout
