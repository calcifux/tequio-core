"""Task de Celery `mail.send` (= `Mailable implements ShouldQueue` del legacy).

Encolar un correo no debe bloquear el flujo que lo dispara (un command, un job,
un controller). Esta task reinstancia el `Mailable` en el worker desde primitivas
serializables — equivalente al `SerializesModels` trait de Laravel: el worker
recibe (class_path, kwargs) y se encarga de reconstruir el objeto y llamar
`build()`.

Por qué no serializamos el Mailable directamente: pickle de instancias arbitrarias
es frágil e inseguro (especialmente con dependencias que NO deben viajar, como
sesiones de BD). El contrato es estricto: el `__init__` del Mailable solo recibe
primitivas (str, int, dataclasses, ids), y los llamadores pasan EXACTAMENTE esos
mismos kwargs en `enqueue_mail(...)`.
"""

from __future__ import annotations

import importlib
import inspect
import smtplib
from typing import Any

from celery import Task
from loguru import logger

from tequio.Core.CeleryApp import broker_guard, celery_app, retry_policy
from tequio.Core.Mail.Mailable import Mailable
from tequio.Core.Mail.Mailer import mailer as default_mailer
from tequio.Core.Translate import current_locale, set_request_locale

# Excepciones TRANSITORIAS que justifican reintentar: caídas/timeouts del SMTP y fallos
# de red. ConnectionError/TimeoutError cubren el "conexión rechazada/colgada" ANTES de
# que smtplib lo envuelva; smtplib.SMTPException cubre los cuelgues post-handshake
# (SMTPServerDisconnected, SMTPConnectError...). Deliberadamente NO incluimos OSError a
# secas para no reintentar un FileNotFoundError de un adjunto (bug de datos, no transitorio).
_RETRYABLE_MAIL_ERRORS = (smtplib.SMTPException, ConnectionError, TimeoutError)


# retry_policy(): defaults de reintento desde .env (TASK_*), overridables A MANO si algún
# día este correo necesita una política distinta (p. ej. max_retries=5 sin tocar el entorno).
@celery_app.task(bind=True, name="mail.send", **retry_policy(retry_for=_RETRYABLE_MAIL_ERRORS))
def send_mail_task(
    self: Task,
    mailable_class_path: str,
    mailable_kwargs: dict[str, Any],
    to: list[str],
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    locale: str | None = None,
) -> None:
    """Reinstancia el Mailable en el worker y lo manda, con reintentos ante fallos
    transitorios de SMTP/red (backoff exponencial; ver `_RETRYABLE_MAIL_ERRORS` y
    `MAIL_MAX_RETRIES`/`MAIL_RETRY_BACKOFF*` en Settings).

    Args:
        self: la Task de Celery (bind=True) — da acceso a `self.request.retries` para
              loguear el intento actual y a la maquinaria de reintentos de `autoretry_for`.
        mailable_class_path: ruta dotted al Mailable concreto
                             (ej. "tequio.Modules.Demo.Mail.DailyDigestMailable.DailyDigestMailable").
        mailable_kwargs: kwargs primitivos para el constructor del Mailable.
        to/cc/bcc: destinatarios.
        locale: locale CAPTURADO al encolar. Lo RESTAURAMOS en el contextvar antes de
                build() para que el correo se traduzca en el idioma del request que lo
                disparo (= como Laravel restaura el locale en el worker). El worker no
                tiene el contexto HTTP, por eso viaja explicito aqui (no en init_kwargs).
    """
    if locale:
        set_request_locale(locale)
    # request.retries = 0 en el primer intento; +1 por cada reintento. Lo logueamos como
    # "intento N/total" para que un fallo transitorio sea visible y auditable en los logs.
    # getattr defensivo: en una llamada DIRECTA (fuera del worker) el Context puede no
    # traer `retries` poblado; en el worker/eager sí lo está.
    attempt = (getattr(self.request, "retries", 0) or 0) + 1
    total_attempts = (self.max_retries or 0) + 1
    logger.info(
        "mail.send | intento {a}/{tot} | clase:{c} | to:{t} | cc:{cc} | bcc:{bcc} | locale:{loc}",
        a=attempt,
        tot=total_attempts,
        c=mailable_class_path,
        t=to,
        cc=cc or [],
        bcc=bcc or [],
        loc=locale,
    )
    mailable_class = _resolve_mailable_class(mailable_class_path)
    mailable = mailable_class(**mailable_kwargs)
    content = mailable.build()
    default_mailer.send(content, to=to, cc=cc, bcc=bcc)


def enqueue_mail(
    mailable: Mailable,
    *,
    to: list[str],
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    queue: str | None = None,
    init_kwargs: dict[str, Any] | None = None,
) -> None:
    """Helper: encola un Mailable para envío asíncrono vía Celery.

    El llamador es responsable de pasar `init_kwargs` que coincida con los args
    que reciba el `__init__` del Mailable cuando se reinstancie en el worker
    (mismo trato que `dispatch(new Mailable(...))` en Laravel: los args
    serializables son responsabilidad del llamador). Si `init_kwargs` no se da y el
    `__init__` exige argumentos, reventamos AQUÍ con instrucción clara: en el worker el
    "missing argument" sería invisible para el remitente (para él, encolar fue exitoso).

    `queue`: cola de Celery a la que se enruta (= `->onQueue('emails')`). None = cola
    por defecto; el worker la consume con `queue work --queue=<cola>`.
    """
    # Faro (bug real cazado 2026-06-06): el digest del demo encolaba sin init_kwargs y el
    # worker tronaba con TypeError al reinstanciar — fallo asíncrono que el remitente nunca
    # ve. Validamos la firma EN EL PROCESO QUE ENCOLA, donde el error sí es accionable.
    if not init_kwargs:
        empty = inspect.Parameter.empty
        variadic = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        required = [
            parameter.name
            for parameter in inspect.signature(type(mailable).__init__).parameters.values()
            if parameter.name != "self" and parameter.default is empty and parameter.kind not in variadic
        ]
        if required:
            raise ValueError(
                f"{type(mailable).__name__}.__init__ requiere {required} pero Mail.queue no recibió "
                "init_kwargs: el worker reinstancia el Mailable desde primitivas y fallaría allá "
                "(invisible para quien encola). Pasa init_kwargs= con EXACTAMENTE esos argumentos."
            )
    mailable_class_path = f"{type(mailable).__module__}.{type(mailable).__qualname__}"
    # Capturamos el locale AMBIENTE aqui (request/CLI) y lo mandamos al worker, que lo
    # restaura antes de build() (= Laravel captura el locale al encolar el Mailable).
    locale = current_locale()
    # broker_guard: si redis no está, error claro en vez del stacktrace de kombu.
    with broker_guard():
        send_mail_task.apply_async(
            kwargs={
                "mailable_class_path": mailable_class_path,
                "mailable_kwargs": init_kwargs or {},
                "to": to,
                "cc": cc,
                "bcc": bcc,
                "locale": locale,
            },
            queue=queue,
        )


# ------------------------------------------------------------------- internos


def _resolve_mailable_class(class_path: str) -> type[Mailable]:
    """Importa la clase desde su ruta dotted y valida que sea un Mailable."""
    module_path, _, class_name = class_path.rpartition(".")
    if not module_path or not class_name:
        raise ValueError(f"Ruta de Mailable inválida: {class_path!r}")
    module = importlib.import_module(module_path)
    mailable_class = getattr(module, class_name, None)
    if mailable_class is None:
        raise ValueError(f"No se encontró la clase {class_name!r} en {module_path!r}")
    if not (isinstance(mailable_class, type) and issubclass(mailable_class, Mailable)):
        raise TypeError(f"{class_path!r} no es subclase de Mailable")
    return mailable_class
