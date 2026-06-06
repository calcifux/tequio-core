"""Commands `make ...`: scaffolding de archivos (= los `make:*` de artisan).

Generan un stub idiomático y se auto-montan por convención (no hay que registrarlos a mano).
Idempotente: NUNCA sobrescriben un archivo existente.
"""

from __future__ import annotations

from pathlib import Path

import typer

from tequio.Core.Config import settings
from tequio.Core.Console import console_command


def _app_dir() -> Path:
    """Raíz del código del USUARIO donde escribe `make:*` (cwd/app por default,
    configurable con APP_DIR). Se resuelve en CADA llamada → relativa al cwd donde el dev
    corre `tequio`, NO a la ubicación del paquete instalado (que es el bug que evita)."""
    return Path(settings.app_dir).resolve()


def _write(path: Path, content: str) -> None:
    """Escribe `content` en `path` si NO existe; si existe, aborta (no sobrescribe)."""
    if path.exists():
        typer.echo(f"✗ ya existe (no se sobrescribe): {path}")
        raise typer.Exit(code=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    typer.echo(f"✓ creado: {path}")


def _ensure_pkg(directory: Path) -> None:
    """Crea el __init__.py de la carpeta de convención si falta (idempotente, NO aborta).
    Así Observers/, Handlers/, Pipes/, ... son paquetes y el discovery los importa."""
    init = directory / "__init__.py"
    if init.exists():
        return
    directory.mkdir(parents=True, exist_ok=True)
    init.write_text(f'"""{directory.name} del módulo."""\n', encoding="utf-8")
    typer.echo(f"✓ creado: {init}")


def model_stub(name: str) -> str:
    """Stub de un modelo SQLAlchemy (con timestamps)."""
    table = f"{name.lower()}s"
    return (
        f'"""Modelo {name}."""\n\n'
        "from __future__ import annotations\n\n"
        "from sqlalchemy.orm import Mapped, mapped_column\n\n"
        "from tequio.Core.Database import Base, TimestampMixin\n\n\n"
        f"class {name}(TimestampMixin, Base):\n"
        f'    __tablename__ = "{table}"\n\n'
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        "    # TODO: agrega tus columnas, p. ej.:\n"
        '    # name: Mapped[str] = mapped_column(default="")\n'
    )


def observer_stub(name: str) -> str:
    """Stub de un Observer (+ su evento) — patrón opt-in Events (estilo Laravel Listener)."""
    return (
        f'"""Observer {name}: reacciona a un evento de aplicación (se auto-descubre)."""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n\n"
        "from tequio.Core.Events import Observer\n\n\n"
        "@dataclass(frozen=True)\n"
        f"class {name}Event:\n"
        '    """El hecho ocurrido. Campos = primitivos planos (viajan al worker si hay broker)."""\n\n'
        "    # TODO: agrega los datos del evento, p. ej.:\n"
        "    # entity_id: int\n\n\n"
        f"class {name}Observer(Observer):\n"
        f"    observes = {name}Event\n\n"
        f"    def handle(self, event: {name}Event) -> None:\n"
        "        # TODO: reacciona aquí. Corre sobre el broker si hay; si no, síncrono.\n"
        "        ...\n"
    )


def handler_stub(name: str) -> str:
    """Stub de un command handler — patrón opt-in Mediator (un caso de uso = un archivo)."""
    return (
        f'"""Handler {name}: un caso de uso (comando + handler), se resuelve con Mediator.send."""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n\n"
        "from tequio.Core.Mediator import handles\n\n\n"
        "@dataclass(frozen=True)\n"
        f"class {name}:\n"
        '    """El comando = la intención. Campos = primitivos."""\n\n'
        "    # TODO: agrega los parámetros del comando, p. ej.:\n"
        "    # entity_id: int\n\n\n"
        f"@handles({name})\n"
        f"class {name}Handler:\n"
        f"    def handle(self, command: {name}) -> object:\n"
        "        # TODO: ejecuta el caso de uso y devuelve el resultado.\n"
        "        ...\n"
    )


def repository_stub(model: str) -> str:
    """Stub de un Repository[Model, Id] (CRUD tipado)."""
    return (
        f'"""Repositorio de {model}: CRUD tipado heredado de Repository[Model, Id]."""\n\n'
        "from __future__ import annotations\n\n"
        "from tequio.Core.Database import Repository\n\n"
        f"from app.Models.{model} import {model}\n\n\n"
        f"class {model}Repository(Repository[{model}, int]):\n"
        f"    model = {model}\n"
    )


def pipe_stub(name: str) -> str:
    """Stub de un Pipe (etapa de un Pipeline)."""
    return (
        f'"""Pipe {name}: una etapa de un Pipeline. Transforma `passable` y sigue, o corta."""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Callable\n"
        "from typing import Any\n\n\n"
        f"class {name}:\n"
        "    def handle(self, passable: Any, next: Callable[[Any], Any]) -> Any:  # noqa: A002\n"
        "        # TODO: transforma `passable`; llama next(passable) para seguir, o NO lo llames para cortar.\n"
        "        return next(passable)\n"
    )


def mailable_stub(module: str, name: str) -> str:
    """Stub de un Mailable (build() -> MailContent), estilo milpa, que ASUME la cola "emails".

    Adaptado de milpa: sin Auth/dueño (tequio es worker-side). El docstring del stub narra el
    despacho idiomático ENCOLADO con la convención de cola de correos ("emails", = `->onQueue('emails')`
    de Laravel) y apunta su plantilla a la convención `Resources/Views/emails/` del módulo (con la
    nota del catálogo Lang para el subject, igual que milpa).
    """
    ns = module.lower()
    return (
        f'"""Mailable {name}: arma un correo (build() -> MailContent).\n\n'
        "Despáchalo ENCOLADO (idiomático worker-side) a la cola de correos `emails`\n"
        "(= `->onQueue('emails')` de Laravel); el worker la consume con `queue work --queue emails`\n"
        "(o `--queue emails,celery` para drenar también la cola por defecto):\n\n"
        "    from tequio.Core.Mail import Mail\n\n"
        f'    Mail.queue({name}Mailable(name), to=[...], queue="emails", init_kwargs={{"name": name}})\n\n'
        "`init_kwargs` debe COINCIDIR con el __init__ (el Mailable se reinstancia en el worker, solo\n"
        "primitivas serializables — sin sesiones de BD). Si no hay broker, manda en el acto con\n"
        "`Mail.send(...)` (síncrono, sin redis).\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from tequio.Core.Mail import Mailable, MailContent\n\n\n"
        f"class {name}Mailable(Mailable):\n"
        "    def __init__(self, name: str) -> None:\n"
        "        self._name = name\n\n"
        "    def build(self) -> MailContent:\n"
        "        # TODO: subject / template (vista Jinja) / context de tu correo.\n"
        f'        # La plantilla vive en Resources/Views/emails/ del módulo (namespace "{ns}/emails/...").\n'
        '        # Para un subject multilingüe usa el catálogo Lang: t("' + ns + '/<archivo>.<clave>").\n'
        "        return MailContent(\n"
        '            subject=f"Hola {self._name}",\n'
        f'            template="{ns}/emails/mi_correo.html.j2",\n'
        '            context={"name": self._name},\n'
        "        )\n"
    )


def job_stub(module: str, name: str) -> str:
    """Stub de un Job de background on-demand (`@job` + `.dispatch()`, estilo milpa)."""
    func = name.lower()
    return (
        f'"""Job {name}: corre en el worker (background). Dispáralo con {func}.dispatch(...)."""\n\n'
        "from __future__ import annotations\n\n"
        "from tequio.Core.Jobs import job\n\n\n"
        f'@job(name="{module.lower()}.{func}")\n'
        f"def {func}() -> None:\n"
        "    # TODO: el trabajo en background (lo corre `queue work`). Despáchalo desde tu código:\n"
        f"    #     {func}.dispatch()        # encola (broker_guard: 503 limpio si el broker cae)\n"
        "    ...\n"
    )


def service_stub(name: str) -> str:
    """Stub de un Service: un caso de uso en UNA transacción (@transactional), que serializa a
    dict ANTES del commit (estilo NoteService) para no chocar con DetachedInstanceError."""
    return (
        f'"""Servicio {name}: un caso de uso en UNA transacción. Serializa a dict ANTES del\n'
        'commit (para no chocar con expire_on_commit / DetachedInstanceError)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "from tequio.Core.Database import current_session, transactional\n\n\n"
        f"class {name}Service:\n"
        "    @transactional\n"
        "    def handle(self) -> dict[str, Any]:\n"
        "        # TODO: carga/muta el recurso vía current_session(); usa .flush() para asignar PK.\n"
        "        _ = current_session\n"
        "        # Serializa ANTES del commit (devuelve un dict JSON-able):\n"
        "        return {}\n"
    )


def seeder_stub(name: str) -> str:
    """Stub de un Seeder (subclase de Seeder con run()). Se auto-descubre por import_all_seeders."""
    return (
        f'"""Seeder {name}: puebla la BD con datos iniciales/demo (se auto-descubre). '
        'La IDEMPOTENCIA es tu responsabilidad: revisa si el dato ya existe antes de crearlo."""\n\n'
        "from __future__ import annotations\n\n"
        "from tequio.Core.Database import current_session\n"
        "from tequio.Core.Database.Seeder import Seeder\n\n\n"
        f"class {name}Seeder(Seeder):\n"
        "    def run(self) -> None:\n"
        "        # TODO: siembra tus datos aquí (corre dentro de su propia transacción).\n"
        "        # Idempotencia: revisa si ya existe antes de crear.\n"
        "        _ = current_session\n"
        "        ...\n"
    )


def factory_stub(model: str) -> str:
    """Stub de una Factory[Model] (datos por default con Faker)."""
    return (
        f'"""Factory de {model}: construye/persiste {model} con datos por default (Faker)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "from tequio.Core.Database import Factory\n\n"
        f"from app.Models.{model} import {model}\n\n\n"
        f"class {model}Factory(Factory[{model}]):\n"
        f"    model = {model}\n\n"
        "    def definition(self) -> dict[str, Any]:\n"
        "        # TODO: atributos por default. Para Faker instala `uv add faker` y, p. ej.:\n"
        "        #   from tequio.Core.Database.Faker import faker\n"
        '        #   return {"name": faker.name(), "email": faker.unique.email()}\n'
        "        return {}\n"
    )


def serializer_stub(name: str) -> str:
    """Stub de un Serializer: una función modelo → dict JSON-able (estilo *_dict del demo)."""
    obj = name.lower()
    return (
        f'"""Serializer de {name}: modelo → dict JSON-able. Llámalo MIENTRAS la sesión sigue\n'
        'abierta (en writes @transactional, antes del commit)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        f"from app.Models.{name} import {name}\n\n\n"
        f"def {obj}_dict({obj}: {name}) -> dict[str, Any]:\n"
        "    # TODO: agrega los campos a exponer, p. ej.:\n"
        f'    # return {{"id": {obj}.id, "name": {obj}.name}}\n'
        f'    return {{"id": {obj}.id}}\n'
    )


@console_command(name="observer", group="make", help="Crea un Observer (+ su evento) en un módulo. (≈ make:observer)")
def make_observer(module: str, name: str) -> None:
    target = _app_dir() / "Modules" / module / "Observers" / f"{name}Observer.py"
    _ensure_pkg(target.parent)
    _write(target, observer_stub(name))


@console_command(name="handler", group="make", help="Crea un command handler (Mediator) en un módulo. (≈ make:handler)")
def make_handler(module: str, name: str) -> None:
    target = _app_dir() / "Modules" / module / "Handlers" / f"{name}Handler.py"
    _ensure_pkg(target.parent)
    _write(target, handler_stub(name))


@console_command(name="repository", group="make", help="Crea un Repository[Model,Id] en un módulo. (≈ make:repository)")
def make_repository(module: str, model: str) -> None:
    target = _app_dir() / "Modules" / module / "Repositories" / f"{model}Repository.py"
    _ensure_pkg(target.parent)
    _write(target, repository_stub(model))


@console_command(name="pipe", group="make", help="Crea un Pipe (etapa de Pipeline) en un módulo. (≈ make:pipe)")
def make_pipe(module: str, name: str) -> None:
    target = _app_dir() / "Modules" / module / "Pipes" / f"{name}.py"
    _ensure_pkg(target.parent)
    _write(target, pipe_stub(name))


@console_command(name="mailable", group="make", help="Crea un Mailable (cola 'emails') en un módulo. (≈ make:mail)")
def make_mailable(module: str, name: str) -> None:
    target = _app_dir() / "Modules" / module / "Mail" / f"{name}Mailable.py"
    _ensure_pkg(target.parent)
    _write(target, mailable_stub(module, name))


@console_command(name="job", group="make", help="Crea un Job de Celery en un módulo. (≈ php artisan make:job)")
def make_job(module: str, name: str) -> None:
    target = _app_dir() / "Modules" / module / "Jobs" / f"{name}.py"
    _ensure_pkg(target.parent)
    _write(target, job_stub(module, name))


@console_command(
    name="service", group="make", help="Crea un Service (caso de uso, @transactional) en un módulo. (≈ make:service)"
)
def make_service(module: str, name: str) -> None:
    target = _app_dir() / "Modules" / module / "Services" / f"{name}Service.py"
    _ensure_pkg(target.parent)
    _write(target, service_stub(name))


@console_command(name="seeder", group="make", help="Crea un Seeder en un módulo. (≈ php artisan make:seeder)")
def make_seeder(module: str, name: str) -> None:
    target = _app_dir() / "Modules" / module / "Seeders" / f"{name}Seeder.py"
    _ensure_pkg(target.parent)
    _write(target, seeder_stub(name))


@console_command(
    name="factory", group="make", help="Crea una Factory[Model] (Faker) en un módulo. (≈ php artisan make:factory)"
)
def make_factory(module: str, model: str) -> None:
    target = _app_dir() / "Modules" / module / "Factories" / f"{model}Factory.py"
    _ensure_pkg(target.parent)
    _write(target, factory_stub(model))


@console_command(
    name="serializer", group="make", help="Crea un Serializer (modelo → dict) en un módulo. (≈ make:resource)"
)
def make_serializer(module: str, name: str) -> None:
    target = _app_dir() / "Modules" / module / "Serializers" / f"{name}Serializer.py"
    _ensure_pkg(target.parent)
    _write(target, serializer_stub(name))


@console_command(name="model", group="make", help="Crea un modelo SQLAlchemy en app/Models. (≈ php artisan make:model)")
def make_model(name: str) -> None:
    _write(_app_dir() / "Models" / f"{name}.py", model_stub(name))
