"""Reloj de la app, INYECTABLE (estilo `java.time.Clock` de Spring), para los
cálculos de fechas de NEGOCIO en la zona configurada (TIMEZONE del .env).

Es un `Protocol`: se inyecta A MANO donde se necesita instanciándolo en el call-site
(hoy el único consumidor es `ScheduleRunCommand`, que hace `SystemClock().now()`).
`SystemClock` da la hora real (naive local); `FixedClock` la CONGELA en tests
(equivalente a `Carbon::setTestNow()`), p. ej. con `monkeypatch.setattr(SystemClock,
"now", ...)` o inyectando un `FixedClock(datetime(...))` en el código que lo reciba.

Para los timestamps de BD NO se usa esto: los pone la BD con func.now() y la
conexión ya corre en la zona de la app (ver Database/Session.py y Timestamp.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from tequio.Core.Config.Settings import settings


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Hora real en la zona de la app, NAIVE local (como guarda Eloquent/Carbon)."""

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)


class FixedClock:
    """Reloj congelado para tests (= Carbon::setTestNow). Siempre devuelve `moment`."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment
