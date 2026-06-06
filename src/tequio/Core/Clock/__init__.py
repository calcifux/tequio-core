"""Abstracción de reloj inyectable (= `java.time.Clock` de Spring / `Carbon::setTestNow` de Laravel).

Re-exporta el protocolo y las implementaciones para que
`from tequio.Core.Clock import Clock, SystemClock, FixedClock` siga funcionando.
"""

from __future__ import annotations

from tequio.Core.Clock.Clock import Clock, FixedClock, SystemClock

__all__ = ["Clock", "FixedClock", "SystemClock"]
