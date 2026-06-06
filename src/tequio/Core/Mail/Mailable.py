"""ABC `Mailable` (= `Illuminate\\Mail\\Mailable` del legacy) + dataclass de payload.

Patrón porteado 1:1:

    class ReminderPreviousMail(Mailable):  // = "extends Mailable"
        def __init__(self, data, channel, show_guarantor): ...

        def build(self) -> MailContent:    // = build() del legacy
            return MailContent(
                subject=self._data.subject,                  // ->subject(...)
                template="Emails/Trans/Reminder/Debtor/...",        // ->view(...)
                context={"data": self._data, "show_guarantor": ...},  // ->with([...])
                from_email=self._data.sender_email,          // ->from(...)
                from_name=self._data.sender_name,
            )

El `Mailer` toma este `MailContent` y se encarga de renderizar el template y
construir el MIME — el `Mailable` NO toca SMTP ni Jinja directamente
(responsabilidades separadas, como en todo el monolito modular).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DataAttachment:
    """Adjunto desde BYTES en memoria (= `attachData()` de Laravel). No toca disco.

    Útil cuando el PDF/XML se genera al vuelo (p. ej. un reporte): lo construyes en
    `build()` y lo mandas como bytes — sin archivos temporales que limpiar. En el
    camino encolado, como `build()` corre en el worker, los bytes NO viajan por la
    cola (se generan worker-side), así que tampoco engordan el mensaje del broker.
    """

    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


@dataclass
class MailContent:
    """Payload puro de un correo, listo para que el `Mailer` lo renderice y mande.

    Atributos (mapeo al legacy):
      • subject:        `->subject(...)` — string ya traducido por el llamador.
      • template:       `->view(...)` — ruta relativa al loader de Jinja
                        (ej. `"Emails/Trans/Reminder/Debtor/reminder_previous.html.j2"`).
      • context:        `->with([...])` — variables disponibles en el template.
      • from_email/name: `->from(addr, name)` — si None, el Mailer cae al default
                        configurado en settings (`mail_from_email`/`mail_from_name`).
      • inline_assets:  cid → ruta a archivo (= `$message->embed(public_path(...))`).
                        Se agregan como `add_related` con Content-ID; el template los
                        referencia con `<img src="cid:<key>">`.
      • attachments:    archivos adjuntos POR RUTA (= `->attach($path)`).
      • data_attachments: adjuntos POR BYTES (= `->attachData(...)`); preferidos
                        cuando armas el archivo en memoria (no creas temporales).
      • cleanup_paths:  rutas a BORRAR tras enviar (en un `finally` del Mailer). Es
                        OPT-IN: el Mailer NUNCA borra un `attachments` por su cuenta;
                        si quieres que un temporal-en-disco se limpie, decláralo aquí.
                        (= el `File::delete($pdfPath)` del `finally` en un Mailable
                        Laravel que sobreescribe `send()`.) Lo que no declares, se queda.
    """

    subject: str
    template: str
    context: dict[str, object] = field(default_factory=dict)
    from_email: str | None = None
    from_name: str | None = None
    inline_assets: dict[str, Path] = field(default_factory=dict)
    attachments: list[Path] = field(default_factory=list)
    data_attachments: list[DataAttachment] = field(default_factory=list)
    cleanup_paths: list[Path] = field(default_factory=list)


class Mailable(ABC):
    """Base abstracta para todos los correos de la aplicación.

    Subclases implementan `build()` retornando un `MailContent`. La regla
    importante (= legacy `ShouldQueue`): el constructor solo recibe DATOS
    serializables (primitivos, dataclasses, ids) — nunca conexiones, sesiones
    de BD, ni clientes HTTP — para que el `Mailable` se pueda re-instanciar
    desde una task de Celery sin reconstruir contexto fuera de su alcance.
    """

    @abstractmethod
    def build(self) -> MailContent:
        """Arma el `MailContent` con el subject, template, contexto y from."""
