"""Mailer SMTP (= `Illuminate\\Mail\\Mailer` del legacy).

Responsabilidades:
  1. Renderizar el template Jinja2 del `MailContent` (delegando en TemplateEngine).
  2. Construir el mensaje MIME multipart (texto plano + HTML alternativo + inline
     assets con CID + adjuntos), usando `email.message.EmailMessage` de stdlib.
  3. Enviar por SMTP respetando `mail_encryption` (sin cifrado / STARTTLS / SMTPS).

Por qué stdlib (sin librerías de terceros): el caso de uso es directo y stdlib
ya cubre MIME multipart + STARTTLS + autenticación. Una dependencia extra (yagmail,
fastapi-mail, etc.) no agrega valor para este alcance.
"""

from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html.parser import HTMLParser
from pathlib import Path

from loguru import logger

from tequio.Core.Config import settings
from tequio.Core.Mail.Mailable import DataAttachment, MailContent
from tequio.Core.Translate import current_locale
from tequio.Core.View.TemplateEngine import TemplateEngine
from tequio.Core.View.TemplateEngine import template_engine as default_engine


class _HtmlToPlainText(HTMLParser):
    """Conversor pobre HTML → texto plano para el `set_content()` de respaldo.

    No pretende ser perfecto: los lectores de correo modernos muestran el HTML;
    el texto plano es solo el fallback para clientes que NO soportan HTML
    (raros hoy, pero el RFC los exige como `multipart/alternative`).
    """

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Saltos de línea en tags de bloque para que el plano sea legible.
        if tag in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def to_text(self) -> str:
        return "".join(self._chunks).strip()


def _html_to_text(html: str) -> str:
    parser = _HtmlToPlainText()
    parser.feed(html)
    return parser.to_text()


class Mailer:
    """Servicio de envío de correos. Inyectable (engine + settings)."""

    def __init__(self, engine: TemplateEngine | None = None):
        self._engine = engine or default_engine

    def send(
        self,
        content: MailContent,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> None:
        """Renderiza `content`, arma el MIME y lo entrega según `MAIL_DRIVER`.

        Con driver "smtp" lanza `smtplib.SMTPException` si el envío falla; el llamador
        decide la política (reintento, status terminal, etc.). Con "log"/"null" nunca
        toca la red (útil en dev sin SMTP, o en tests).
        """
        # try/except/finally = patrón del `send()` de un Mailable Laravel
        # (AnnexBMail): observabilidad del fallo + cleanup de temporales en el
        # finally. El finally corre SIEMPRE (envíe, falle, o sea null/log).
        try:
            # Inyectamos el locale AMBIENTE (lo fijo la frontera: dependency HTTP, CLI,
            # o el worker al restaurarlo) para que el template y t() no lo reciban a
            # mano. Si el Mailable puso un `locale` explicito en su context, ese gana.
            render_context = {"locale": current_locale(), **content.context}
            html_body = self._engine.render(content.template, render_context)
            message = self._build_message(content, html_body, to=to, cc=cc or [], bcc=bcc or [])
            recipients = to + (cc or []) + (bcc or [])

            # Loguear el subject + destinatarios ayuda a auditar sin imprimir el HTML.
            logger.info(
                "Mailer.send | subject:{s} | to:{t} | cc:{c} | bcc:{b} | template:{tpl} | driver:{d}",
                s=content.subject,
                t=to,
                c=cc or [],
                b=bcc or [],
                tpl=content.template,
                d=settings.mail_driver,
            )

            driver = settings.mail_driver.lower()
            if driver in ("null", "array"):
                return  # no-op: se descarta a propósito.
            if driver == "log":
                # = el driver `log` de Laravel: deja el correo COMPLETO en el log, sin enviar.
                logger.info("Mailer[log] | correo NO enviado (driver=log):\n{msg}", msg=message.as_string())
                return
            # driver "smtp" (default) y cualquier otro -> envío real por SMTP.
            self._dispatch(message, recipients=recipients)
        except Exception:
            # loguru captura el traceback solo (no necesitamos getTraceAsString()).
            logger.exception("Mailer.send | fallo enviando | subject:{s}", s=content.subject)
            raise  # re-lanzamos: el llamador decide la política (reintento, status).
        finally:
            self._cleanup_temp_files(content.cleanup_paths)

    @staticmethod
    def _cleanup_temp_files(cleanup_paths: list[Path]) -> None:
        """Borra los temporales que el Mailable DECLARÓ explícitamente en `cleanup_paths`.

        OPT-IN a propósito: NUNCA borramos un `attachments` por nuestra cuenta. Si un
        dev adjunta por ruta y NO declara la ruta aquí, el archivo se queda — es su
        decisión (= el `File::delete` que tú pones en el `finally` de tu Mailable, o no).
        """
        for path in cleanup_paths:
            try:
                if path.is_file():
                    path.unlink()
                    logger.info("Mailer | temporal borrado: {p}", p=path)
            except OSError as error:
                # Un fallo al borrar no debe tumbar el flujo (el correo ya se mandó).
                logger.warning("Mailer | no se pudo borrar temporal {p}: {e}", p=path, e=error)

    # ----------------------------------------------------------- internos

    def _build_message(
        self,
        content: MailContent,
        html_body: str,
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
    ) -> EmailMessage:
        """Arma el `EmailMessage` multipart con plano + HTML + inlines + adjuntos."""
        message = EmailMessage()
        message["Subject"] = content.subject

        # From: prioriza lo declarado por el Mailable; default desde settings.
        from_email = content.from_email or settings.mail_from_email
        from_name = content.from_name or settings.mail_from_name
        message["From"] = formataddr((from_name, from_email))

        # Destinatarios visibles. BCC NO se pone en headers (ese es justo el
        # punto: lo enviamos vía SMTP RCPT TO pero no aparece en el mensaje).
        message["To"] = ", ".join(to)
        if cc:
            message["Cc"] = ", ".join(cc)

        # Cuerpos: plano primero (set_content), luego HTML como "alternative".
        # Los clientes modernos muestran el HTML; los que no soportan, el plano.
        message.set_content(_html_to_text(html_body))
        message.add_alternative(html_body, subtype="html")

        # Inline assets (CID): equivalentes a `$message->embed(public_path(...))`
        # del legacy. El template hace `<img src="cid:logo">`; aquí ligamos
        # "logo" -> archivo binario con un Content-ID estable.
        if content.inline_assets:
            self._attach_inline_assets(message, content.inline_assets)

        # Adjuntos POR RUTA (PDF/XML/etc. que ya viven en disco).
        for attachment_path in content.attachments:
            self._attach_file(message, attachment_path)

        # Adjuntos POR BYTES (= attachData): generados en memoria, sin tocar disco.
        for data_attachment in content.data_attachments:
            self._attach_data(message, data_attachment)

        return message

    @staticmethod
    def _attach_inline_assets(message: EmailMessage, inline_assets: dict[str, Path]) -> None:
        """Agrega cada asset como `multipart/related` con Content-ID = cid:<key>."""
        # Los inlines se agregan al payload HTML (que es el "alternative" agregado
        # justo antes). Lo localizamos por subtipo "html".
        html_part = None
        for part in message.iter_parts():
            if part.get_content_subtype() == "html":
                html_part = part
                break
        if html_part is None:
            # Edge case: no hay HTML. Saltamos los inlines.
            return

        for cid_key, asset_path in inline_assets.items():
            mime_type, _ = mimetypes.guess_type(str(asset_path))
            maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
            with asset_path.open("rb") as asset_file:
                content_bytes = asset_file.read()
            content_id = make_msgid()  # CID único; el template usa la KEY (dominio = hostname)
            html_part.add_related(
                content_bytes,
                maintype=maintype,
                subtype=subtype,
                cid=f"<{cid_key}>",
                filename=asset_path.name,
                # `disposition="inline"` explícito: sin esto, stdlib marca
                # `attachment` cuando se pasa `filename`, y la imagen se vería
                # DUPLICADA (inline por CID + adjunto descargable) en clientes
                # como Outlook. inline = solo embebida, no en la lista de adjuntos.
                disposition="inline",
            )
            # Nota: el `cid` del header lleva ángulos; en `src="cid:..."` del HTML
            # el navegador/cliente NO los espera. Por eso usamos cid_key plano en
            # el template y aquí envolvemos en <...> al setear el header.
            _ = content_id  # silenciamos el warning de no-uso (lo mantenemos por si lo necesitamos)

    @staticmethod
    def _attach_file(message: EmailMessage, attachment_path: Path) -> None:
        """Agrega un archivo (POR RUTA) como adjunto normal (`Content-Disposition: attachment`)."""
        mime_type, _ = mimetypes.guess_type(str(attachment_path))
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        with attachment_path.open("rb") as attachment_file:
            content_bytes = attachment_file.read()
        message.add_attachment(
            content_bytes,
            maintype=maintype,
            subtype=subtype,
            filename=attachment_path.name,
        )

    @staticmethod
    def _attach_data(message: EmailMessage, data_attachment: DataAttachment) -> None:
        """Agrega un adjunto desde BYTES en memoria (= attachData), sin leer disco."""
        maintype, _, subtype = (data_attachment.mime_type or "application/octet-stream").partition("/")
        message.add_attachment(
            data_attachment.content,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=data_attachment.filename,
        )

    @staticmethod
    def _check_refused(refused: dict[str, tuple[int, bytes]], recipients: list[str]) -> None:
        """`smtp.send_message` SOLO lanza si TODOS los destinatarios son rechazados; ante un
        rechazo PARCIAL en RCPT TO (unos aceptados, otros no) NO lanza — devuelve un dict de los
        rechazados. Tenet "nunca falla en silencio": si hay rechazos, los logueamos y relanzamos
        (el caller decide la política), en vez de perder el fallo remoto parcial sin rastro."""
        if refused:
            logger.error("Mailer | rechazo PARCIAL de destinatarios | refused:{r} | total:{t}", r=refused, t=recipients)
            raise smtplib.SMTPRecipientsRefused(refused)

    @staticmethod
    def _dispatch(message: EmailMessage, *, recipients: list[str]) -> None:
        """Abre la conexión SMTP, autentica si toca, y envía el mensaje."""
        host = settings.mail_host
        port = settings.mail_port
        encryption = settings.mail_encryption.lower()
        username = settings.mail_username
        password = settings.mail_password

        # SMTPS (SSL directo en el handshake) usa una clase distinta; STARTTLS y
        # "sin cifrado" usan SMTP normal y, en su caso, upgrading post-EHLO.
        if encryption == "ssl":
            with smtplib.SMTP_SSL(host=host, port=port, timeout=30) as smtp:
                if username:
                    smtp.login(username, password)
                Mailer._check_refused(smtp.send_message(message, to_addrs=recipients), recipients)
        else:
            with smtplib.SMTP(host=host, port=port, timeout=30) as smtp:
                smtp.ehlo()
                if encryption == "tls":
                    smtp.starttls()
                    smtp.ehlo()
                if username:
                    smtp.login(username, password)
                Mailer._check_refused(smtp.send_message(message, to_addrs=recipients), recipients)


# Instancia compartida del proceso (el TemplateEngine ya viene por default).
mailer = Mailer()
