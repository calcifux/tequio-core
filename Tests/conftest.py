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
