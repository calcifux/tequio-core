"""Seeder del demo: siembra notas demo (idempotente), usando NoteFactory + datos a mano.

Muestra que un seeder puede usar FACTORIES (datos con Faker) y/o ir A MANO — tequio no obliga.
Aquí: el volumen de notas se crea con `count(...)` (Faker), y una nota concreta va a mano.
Las notas son peladas (sin dueño): tequio es worker-side, sin tabla users/Auth.

Lo corre `tequio db:seed` / `./jornal db:seed`.
"""

from __future__ import annotations

from sqlalchemy import select

from tequio.Core.Database import current_session
from tequio.Core.Database.Seeder import Seeder
from tequio.Models.Note import Note
from tequio.Modules.Demo.Factories.factories import NoteFactory


class DemoSeeder(Seeder):
    def run(self) -> None:
        if current_session().execute(select(Note).limit(1)).first() is not None:
            return  # ya sembrado: no duplicar

        NoteFactory().count(23)  # 23 notas con Faker (para el scroll)
        NoteFactory().create(title="Idea de Beto", body="Probar tequio este finde")
