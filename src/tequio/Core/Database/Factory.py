"""Factory base estilo Laravel: construye/persiste modelos con atributos por default.

La subclase fija `model` y define `definition()` (los atributos por default — típicamente con
Faker; ver `tequio.Core.Database.Faker`). `make()` construye SIN persistir; `create()`/`count()`
PERSISTEN en la sesión AMBIENTE (la del seeder `@transactional` o la del test). Mismo idiom
genérico que `Repository[Model, Id]`, y se apoya en las mismas primitivas (`current_session`).

NO obliga a usar factories: un seeder puede llenar a mano (`current_session().add(...)`), usar
factories, o mezclar. Las factories sirven igual para los TESTS, no solo para seeders.

    class UserFactory(Factory[User]):
        model = User
        def definition(self) -> dict[str, Any]:
            return {"name": faker.name(), "email": faker.unique.email(), "roles": ""}

    UserFactory().create(email="admin@demo.test", roles="admin")   # 1, persistido
    UserFactory().count(100)                                       # 100, persistidos
    note = NoteFactory().make(title="Borrador")                    # construido, sin persistir
"""

from __future__ import annotations

from typing import Any

from tequio.Core.Database.Transactional import current_session


class Factory[ModelT]:
    """Base de factory tipada por modelo. La subclase fija `model` y override `definition()`."""

    model: type[ModelT]

    def definition(self) -> dict[str, Any]:
        """Atributos por DEFAULT del modelo (típicamente con Faker). DEBE definirlo la subclase."""
        raise NotImplementedError("Define definition() con los atributos por default del modelo.")

    def make(self, **overrides: Any) -> ModelT:
        """Construye UNA instancia (sin persistir): `definition()` + `overrides`."""
        return self.model(**{**self.definition(), **overrides})

    def make_many(self, count: int, **overrides: Any) -> list[ModelT]:
        """Construye `count` instancias (sin persistir). Cada una re-evalúa `definition()`."""
        return [self.make(**overrides) for _ in range(count)]

    def create(self, **overrides: Any) -> ModelT:
        """Construye y PERSISTE una instancia en la sesión ambiente (flush para asignar PK)."""
        entity = self.make(**overrides)
        session = current_session()
        session.add(entity)
        session.flush()
        return entity

    def count(self, count: int, **overrides: Any) -> list[ModelT]:
        """Construye y PERSISTE `count` instancias."""
        entities = self.make_many(count, **overrides)
        session = current_session()
        session.add_all(entities)
        session.flush()
        return entities
