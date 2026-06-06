"""Facade `Mail` estilo Laravel: `Mail.send(...)` (síncrono) y `Mail.queue(...)`
(asíncrono vía Celery). Equivalen 1:1 a `Mail::send` / `Mail::queue` del legacy.

- `Mail.send` → manda el correo EN EL ACTO por SMTP. NO usa redis ni worker.
  Úsalo cuando no quieras encolar, o cuando el entorno/proyecto no tenga redis
  (p. ej. probar en local sin levantar nada).
- `Mail.queue` → ENCOLA el envío en Celery (no bloquea el flujo que lo dispara).
  Requiere redis + un worker (`queue work`). Importa la maquinaria de Celery de
  forma PEREZOSA, así un proyecto que solo use `Mail.send` nunca jala redis/celery.
"""

from __future__ import annotations

from typing import Any

from tequio.Core.Mail.Mailable import Mailable
from tequio.Core.Mail.Mailer import mailer


class Mail:
    """Punto de entrada único para mandar correos (= la facade `Mail` de Laravel)."""

    @staticmethod
    def send(
        mailable: Mailable,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> None:
        """SÍNCRONO (= `Mail::send`). Arma el correo y lo manda ya por SMTP. Sin redis."""
        content = mailable.build()
        mailer.send(content, to=to, cc=cc, bcc=bcc)

    @staticmethod
    def queue(
        mailable: Mailable,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        queue: str | None = None,
        init_kwargs: dict[str, Any] | None = None,
    ) -> None:
        """ASÍNCRONO (= `Mail::queue`). Encola en Celery; requiere redis + worker.

        `queue` None (default) = la COLA POR DEFECTO (la consume `queue work` sin
        `--queue`). Para tu convención Laravel pásalo explícito, p. ej. `queue="emails"`
        (lo consume `queue work --queue=emails`). `init_kwargs` deben coincidir con el
        `__init__` del Mailable (se reinstancia en el worker). Import perezoso de Celery:
        si nunca llamas `queue`, no se jala redis/celery. Si redis no está disponible,
        lanza `QueueUnavailableError` con un mensaje claro.
        """
        from tequio.Core.Mail.Tasks import enqueue_mail

        enqueue_mail(mailable, to=to, cc=cc, bcc=bcc, queue=queue, init_kwargs=init_kwargs)
