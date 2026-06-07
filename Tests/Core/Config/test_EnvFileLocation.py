"""Test del env_file DESANCLADO del CWD: tequio lee el .env desde TEQUIO_ENV_FILE.

`model_config` resuelve `os.environ.get("TEQUIO_ENV_FILE", ".env")` al DEFINIRSE la clase
(una vez por import), así que para ejercer la variable de verdad recargamos Settings en un
SUBPROCESO limpio con TEQUIO_ENV_FILE apuntando a un .env temporal fuera del CWD. Prueba el
caso real: un beat en docker con el repo montado de solo-lectura apunta su env a /tmp sin
symlinkear .env al CWD.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tequio.Core.Config.Settings import Settings

_SRC = str(Path(__file__).resolve().parents[3] / "src")


def test_model_config_deriva_env_file_de_milpa_env_file() -> None:
    """El env_file del model_config SE DERIVA de TEQUIO_ENV_FILE (no clavado a ".env")."""
    expected = os.environ.get("TEQUIO_ENV_FILE", ".env")
    assert Settings.model_config["env_file"] == expected


def test_milpa_env_file_redirige_la_lectura_en_subproceso(tmp_path: Path) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text('APP_NAME="Desde TEQUIO_ENV_FILE"\n', encoding="utf-8")

    code = "from tequio.Core.Config import settings;print(settings.app_name)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),  # CWD SIN .env: si estuviera clavado al CWD, no leería nada
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": _SRC,
            "TEQUIO_ENV_FILE": str(env_file),  # apunta a un archivo FUERA del patrón ./.env
            "LOG_DIR": str(tmp_path / "logs"),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Desde TEQUIO_ENV_FILE" in result.stdout
