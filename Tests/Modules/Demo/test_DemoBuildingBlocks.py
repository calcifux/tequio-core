"""Tests del módulo Demo SIN BD ni red: prueban las piezas estilo milpa de forma EJECUTABLE
(serializer Pydantic del NoteService, Pipeline de limpieza, registro de @job/@cron_task y del
handler del Mediator). "Código sin demostración ejecutable son promesas": esto las cumple.

Layout estilo make:* del demo (un archivo por clase, agrupado por rol en carpetas:
Jobs/ExportNotesJob.py, Crons/DailyDigestCron.py, Handlers/ArchiveNoteHandler.py,
Pipes/CleanContent.py, Services/NoteService.py...), con Commands.py/Events.py sueltos por chicos.
El encarpetado es LIBRE: el discovery importa todo el árbol del módulo, no carpetas de
convención fijas.

El correo VUELVE a tequio (los crons mandan correo, que para eso nació): el demo trae un
`DailyDigestMailable` (Mail/DailyDigestMailable.py) que el cron `demo.daily_digest` envía. Aquí probamos
ese Mailable como building-block (subject + template + firma del layout firmado) y su render real
contra el TemplateEngine; el ENVÍO con driver `log` se ejercita en test_DemoFlows.py. El observer
`LogNoteCreated` sigue logueando (el otro transporte): ese flujo evento → Observer → log también
vive en test_DemoFlows.py. Aquí: registro, transformación pura y el Mailable del digest.
"""

from __future__ import annotations

import importlib

from tequio.Core.Mediator import registered_handlers, reset_handlers
from tequio.Core.Pipeline import Pipeline
from tequio.Core.View.TemplateEngine import template_engine
from tequio.Modules.Demo.Commands import ArchiveNote
from tequio.Modules.Demo.Jobs.ExportNotesJob import export_user_notes
from tequio.Modules.Demo.Mail.DailyDigestMailable import DailyDigestMailable
from tequio.Modules.Demo.Pipes.CleanContent import CollapseWhitespace, NoteDraft, TrimContent

# En milpa NoteOut vivía en Modules/Demo/Serializers.py junto a UserOut/user_dict (Auth). En tequio
# UserOut se descarta (sin User/Auth) y NoteOut/note_dict se inlinaron en el NoteService (Services/NoteService.py).
from tequio.Modules.Demo.Services.NoteService import NoteOut


# --------------------------------------------------------- serializer (computed_field)
def test_note_serializer_truncates_excerpt() -> None:
    # Nota SIN dueño: el demo soltó owner_id (era la cicatriz de Auth); NoteOut ya no lo lleva.
    short = NoteOut(id=1, title="t", body="corto").model_dump()
    assert short["excerpt"] == "corto"
    long = NoteOut(id=1, title="t", body="x" * 200).model_dump()
    assert long["excerpt"].endswith("…") and len(long["excerpt"]) <= 81


# --------------------------------------------------------- pipeline (limpieza de contenido)
def test_clean_content_pipeline_trims_and_collapses() -> None:
    draft: NoteDraft = (
        Pipeline()
        .send(NoteDraft(title="  Hola    mundo  ", body="  cuerpo  "))
        .through([TrimContent(), CollapseWhitespace()])
        .then_return()
    )
    assert draft.title == "Hola mundo"
    assert draft.body == "cuerpo"


# --------------------------------------------------------- command del Mediator (sin actor)
def test_archive_note_command_has_no_actor() -> None:
    # ArchiveNote soltó actor_id junto con el dueño: solo viaja el note_id.
    command = ArchiveNote(note_id=7)
    assert command.note_id == 7
    assert not hasattr(command, "actor_id")


# --------------------------------------------------------- mailable del digest (firma + render)
def test_daily_digest_mailable_builds_signed_content() -> None:
    # El correo del digest: subject con el conteo + template firmado + la FIRMA común del demo
    # (sender_*) que consume el layout firmado. Sin dueño/usuario (worker-side): solo `total`.
    content = DailyDigestMailable(total=7).build()

    assert "7" in content.subject  # el conteo viaja en el subject monolingüe (ES)
    assert content.template == "demo/emails/digest.html.j2"
    assert content.context["sender_name"] == "Equipo tequio"  # firma común de DemoMailable
    assert content.context["total"] == 7
    # El logo de marca se embebe por CID (no URL): el layout firmado hace <img src="cid:logo">.
    assert content.context["logo_cid"] == "logo"
    assert "logo" in content.inline_assets


def test_digest_template_renders_extending_signed_layout() -> None:
    # Render real del template del digest (extiende Emails/Trans/mastersigned): si el extends, el
    # bloque content o un t() del layout estuvieran rotos, esto explota. No manda nada (solo renderiza).
    content = DailyDigestMailable(total=3).build()
    html = template_engine.render(content.template, {"locale": "es", **content.context})

    assert "<html" in html.lower()  # el layout firmado renderizó
    assert "cid:logo" in html  # el logo de marca se embebió por CID
    assert "3" in html  # el conteo del resumen aparece en el cuerpo


# --------------------------------------------------------- job / cron (registro)
def test_export_notes_is_a_dispatchable_job() -> None:
    assert export_user_notes.name == "demo.export_notes"
    assert hasattr(export_user_notes, "dispatch")  # es un Job (no una task pelada)


def test_daily_digest_is_a_cron_task() -> None:
    from tequio.Modules.Demo.Crons.DailyDigestCron import daily_digest

    assert daily_digest.name == "demo.daily_digest"


def test_daily_digest_is_in_the_beat_schedule() -> None:
    # Contrato end-to-end del demo: el digest LLEGA al beat sin Kernel.py (lo agenda
    # el @cron_task descubierto). El registro de crons es un global que otros tests
    # resetean; recargamos el módulo del cron para re-ejecutar `@cron_task` y poblar
    # el registro sin depender del orden de la suite (mismo patrón que el handler).
    from tequio.Core.Cron import daily_at, to_crontab
    from tequio.Core.Registry import collect_beat_schedule

    cron_mod = importlib.import_module("tequio.Modules.Demo.Crons.DailyDigestCron")
    importlib.reload(cron_mod)

    schedule = collect_beat_schedule()
    assert "demo.daily_digest" in schedule
    entry = schedule["demo.daily_digest"]
    assert isinstance(entry, dict)
    # daily_at('08:00') -> crontab minuto 0, hora 8.
    assert entry["schedule"] == to_crontab(daily_at("08:00"))


# --------------------------------------------------------- mediator (registro del handler)
def test_archive_note_handler_is_registered() -> None:
    # El registro de handlers es un global compartido que otros tests resetean; reseteamos +
    # recargamos el módulo para re-ejecutar `@handles(ArchiveNote)` y probar el wiring sin
    # depender del orden de ejecución de la suite.
    reset_handlers()
    handler_mod = importlib.import_module("tequio.Modules.Demo.Handlers.ArchiveNoteHandler")
    importlib.reload(handler_mod)
    assert registered_handlers().get(ArchiveNote) is handler_mod.ArchiveNoteHandler
