"""Helpers de cadencia estilo Laravel (`->everyMinute()`, `->daily()`, ...).

Cada helper devuelve una EXPRESIÓN CRON (string de 5 campos: "minuto hora día mes
día-semana") que se pasa a `@cron_task(schedule=...)`. `schedule run` la evalúa con
croniter cada minuto. Son el equivalente en snake_case de los métodos del scheduler
de Laravel, para que portar un `->everyFiveMinutes()` sea 1:1.

`to_crontab(...)` traduce ese mismo string de 5 campos a la primitiva de agenda de
celery beat (`celery.schedules.crontab`): es el puente que deja que el beat AGENDE
los `@cron_task` descubiertos (ver Registry.collect_beat_schedule).

Ejemplos:
    @cron_task(name="x", schedule=every_five_minutes())   # ->everyFiveMinutes()
    @cron_task(name="y", schedule=daily_at("02:30"))      # ->dailyAt('02:30')
    @cron_task(name="z", schedule=cron("15 9 * * 1-5"))   # ->cron('15 9 * * 1-5')
"""

from __future__ import annotations

from celery.schedules import crontab


def to_crontab(expression: str) -> crontab:
    """Traduce una expresión cron de 5 campos al `crontab` de celery beat.

    Estilo milpa: el MISMO string que producen los helpers de cadencia
    (`every_minute()`, `daily_at(...)`, `cron(...)`) se reusa para agendar el cron
    en el beat. Esto cierra el círculo: `schedule run` evalúa el string con croniter
    y el beat lo agenda con esta primitiva, ambos desde una sola fuente de cadencia.

    Los 5 campos posicionales son "minuto hora día-mes mes día-semana" (el cron
    estándar). `split()` (sin argumento) colapsa espacios múltiples y tabs.

    FARO (no agendar mal en silencio): si la expresión NO tiene exactamente 5
    campos —p. ej. una de 6 campos (con segundos) que croniter sí toleraría en
    `schedule run`— se lanza ValueError. El beat exige 5 campos; usa `schedule run`
    o corrige la expresión. NO se validan los rangos de cada campo aquí: eso lo
    hacen croniter/crontab al EJECUTAR.
    """
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(
            f"expresión cron inválida '{expression}': se esperan 5 campos "
            f"'minuto hora día-mes mes día-semana', se recibieron {len(fields)}."
        )
    return crontab(
        minute=fields[0],
        hour=fields[1],
        day_of_month=fields[2],
        month_of_year=fields[3],
        day_of_week=fields[4],
    )


def cron(expression: str) -> str:
    """Escape hatch: una expresión cron cruda. = `->cron('* * * * *')` de Laravel."""
    return expression


def every_minute() -> str:
    """Cada minuto. = `->everyMinute()`."""
    return "* * * * *"


def every_minutes(n: int) -> str:
    """Cada n minutos (1-59). Generaliza `->everyTwoMinutes()`, etc."""
    if not 1 <= n <= 59:
        raise ValueError(f"every_minutes(n): n debe estar entre 1 y 59, no {n}.")
    return f"*/{n} * * * *"


def every_five_minutes() -> str:
    """= `->everyFiveMinutes()`."""
    return "*/5 * * * *"


def every_ten_minutes() -> str:
    """= `->everyTenMinutes()`."""
    return "*/10 * * * *"


def every_fifteen_minutes() -> str:
    """= `->everyFifteenMinutes()`."""
    return "*/15 * * * *"


def every_thirty_minutes() -> str:
    """= `->everyThirtyMinutes()`."""
    return "*/30 * * * *"


def hourly() -> str:
    """Al minuto 0 de cada hora. = `->hourly()`."""
    return "0 * * * *"


def hourly_at(minute: int) -> str:
    """A un minuto fijo de cada hora (0-59). = `->hourlyAt(17)`."""
    if not 0 <= minute <= 59:
        raise ValueError(f"hourly_at(minute): minute debe estar entre 0 y 59, no {minute}.")
    return f"{minute} * * * *"


def daily() -> str:
    """Todos los días a medianoche. = `->daily()`."""
    return "0 0 * * *"


def daily_at(time: str) -> str:
    """Todos los días a una hora "HH:MM" (24h). = `->dailyAt('13:00')`."""
    hour, minute = _parse_hour_minute(time)
    return f"{minute} {hour} * * *"


def weekly() -> str:
    """Cada domingo a medianoche. = `->weekly()`."""
    return "0 0 * * 0"


def monthly() -> str:
    """El día 1 de cada mes a medianoche. = `->monthly()`."""
    return "0 0 1 * *"


def _parse_hour_minute(time: str) -> tuple[int, int]:
    """Valida y parte un "HH:MM" en (hora, minuto). Falla claro si el formato es inválido."""
    parts = time.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"hora inválida '{time}': se espera formato 'HH:MM' (24h), p. ej. '02:30'.")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"hora inválida '{time}': hora 0-23 y minuto 0-59.")
    return hour, minute
