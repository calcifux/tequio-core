"""Tests de los helpers de cadencia estilo Laravel (app/Core/Cron/Schedule.py).

Solo verifican que cada helper produzca la expresión cron correcta y que validen
sus argumentos. Sin BD ni Redis.
"""

from __future__ import annotations

import pytest
from celery.schedules import crontab

from tequio.Core.Cron import (
    cron,
    daily,
    daily_at,
    every_fifteen_minutes,
    every_five_minutes,
    every_minute,
    every_minutes,
    every_ten_minutes,
    every_thirty_minutes,
    hourly,
    hourly_at,
    monthly,
    to_crontab,
    weekly,
)


def test_named_helpers_return_expected_cron_expressions() -> None:
    assert every_minute() == "* * * * *"
    assert every_five_minutes() == "*/5 * * * *"
    assert every_ten_minutes() == "*/10 * * * *"
    assert every_fifteen_minutes() == "*/15 * * * *"
    assert every_thirty_minutes() == "*/30 * * * *"
    assert hourly() == "0 * * * *"
    assert daily() == "0 0 * * *"
    assert weekly() == "0 0 * * 0"
    assert monthly() == "0 0 1 * *"


def test_every_minutes_builds_step_expression() -> None:
    assert every_minutes(1) == "*/1 * * * *"
    assert every_minutes(2) == "*/2 * * * *"


def test_every_minutes_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        every_minutes(0)
    with pytest.raises(ValueError):
        every_minutes(60)


def test_hourly_at_and_daily_at() -> None:
    assert hourly_at(15) == "15 * * * *"
    assert daily_at("02:30") == "30 2 * * *"
    assert daily_at("13:00") == "0 13 * * *"


def test_daily_at_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        daily_at("2:30pm")
    with pytest.raises(ValueError):
        daily_at("25:00")


def test_cron_escape_hatch_passes_through() -> None:
    assert cron("15 9 * * 1-5") == "15 9 * * 1-5"


# --------------------------------------------------------- conversor a crontab de celery beat
def test_to_crontab_maps_five_fields_positionally() -> None:
    # El mapeo posicional "minuto hora día-mes mes día-semana" -> crontab; dos crontab
    # construidos idénticos comparan == (lo verifica celery), así que assertamos igualdad exacta.
    assert to_crontab("30 8 * * 1-5") == crontab(
        minute="30", hour="8", day_of_month="*", month_of_year="*", day_of_week="1-5"
    )


def test_to_crontab_from_daily_at_helper() -> None:
    # El helper de cadencia encadena con el conversor: daily_at('08:00') -> minuto 0, hora 8.
    result = to_crontab(daily_at("08:00"))
    assert result.minute == {0}
    assert result.hour == {8}


def test_to_crontab_collapses_multiple_spaces() -> None:
    # split() (sin argumento) colapsa espacios múltiples y tabs: no da falsos >5 campos.
    assert to_crontab("*/5  *  *  *  *") == crontab(
        minute="*/5", hour="*", day_of_month="*", month_of_year="*", day_of_week="*"
    )


def test_to_crontab_rejects_non_five_field_expression() -> None:
    # Faro: no agendar mal en silencio. Ni 4 ni 6 campos: el beat exige exactamente 5.
    with pytest.raises(ValueError, match="5 campos"):
        to_crontab("* * * *")
    with pytest.raises(ValueError, match="5 campos"):
        to_crontab("* * * * * *")
