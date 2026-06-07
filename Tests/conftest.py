"""Configuración global de pytest.

Redirige los logs de la suite a `logs/tests/` para que los tests NO escriban en el
`logs/app.log` real. Los tests ejercen el Mailer (incluido el driver `log`, que vuelca
el MIME completo), los crons y el despacho de jobs/events —todo eso loguea—, así que sin
esto contaminarían el log de la app.

También fija un `DATABASE_URL` sqlite en memoria para la suite: tequio prueba SIN base de
datos real (fakes + monkeypatch), pero importar cualquier módulo que toque `Core/Database`
construye el engine, y SQLAlchemy `make_url()` revienta si el `.env` local trae el
DATABASE_URL del template con placeholders (`mysql+pymysql://<user>:<password>@<host>:
<port>/...`). Lo fijamos en `os.environ` (que en pydantic-settings PRECEDE al `.env`) para
que la suite sea hermética sin depender de la config local del dev. Usamos `setdefault`:
si el dev ya exportó un DATABASE_URL real, se respeta.

Debe correr ANTES de que se instancie `settings` o se llame a `setup_logging()`: por eso
solo toca `os.environ` aquí arriba (pytest importa este conftest antes que los módulos de
test, que son los que importan el paquete). `logs/` ya está en `.gitignore`, así que
`logs/tests/` también queda ignorado.
"""

from __future__ import annotations

import os

os.environ.setdefault("LOG_DIR", "logs/tests")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

# Layout del código del USUARIO. Los defaults del framework ahora apuntan a `app.*` (lo que
# tiene quien instala tequio, generado por `tequio new`), NO a `tequio.*`: así una instalación
# SIN .env no auto-descubre el Demo EMPAQUETADO. Pero el código de ESTE repo vive en src/tequio
# (no en app/), así que aquí re-apuntamos los tres paquetes a `tequio.*` para que la suite y el
# CI descubran los módulos del framework (el Demo, sus crons/jobs/mailers) como siempre — la
# suite y el CI NO cambian de comportamiento. Mismo patrón que el LOG_DIR/DATABASE_URL de arriba.
os.environ.setdefault("MODULES_PACKAGE", "tequio.Modules")
os.environ.setdefault("MODELS_PACKAGE", "tequio.Models")
os.environ.setdefault("APP_COMMANDS_PACKAGE", "tequio.Console.Commands")

# Entorno de la suite = "local" (el del dev del framework, ver .env.example). El Demo gana ahora
# environments=("local","development") como cinturón para que ni apuntando MODULES_PACKAGE al Demo
# se agende en prod (default app_env "qa" queda fuera). Los tests del Demo (test_DemoFlows) corren
# el cuerpo del cron `demo.daily_digest` directamente y esperan que ejecute: bajo "local" el gate de
# entorno lo permite, así la suite NO cambia de comportamiento. setdefault: si el dev exportó otro
# APP_ENV, se respeta.
os.environ.setdefault("APP_ENV", "local")
