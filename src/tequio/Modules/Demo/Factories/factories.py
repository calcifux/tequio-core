"""Factory de Note con datos de Faker. El locale es configurable
(`FAKER_LOCALE` en .env; default es_MX) — ver `tequio.Core.Database.Faker`.

La nota es pelada (sin dueño): `definition()` solo da `title`/`body` con Faker.
"""

from __future__ import annotations

from typing import Any

from tequio.Core.Database import Factory
from tequio.Core.Database.Faker import faker
from tequio.Models.Note import Note


class NoteFactory(Factory[Note]):
    model = Note

    def definition(self) -> dict[str, Any]:
        return {
            "title": faker.sentence(nb_words=4).rstrip("."),
            "body": faker.paragraph(nb_sentences=2),
        }
