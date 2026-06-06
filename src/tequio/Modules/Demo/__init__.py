"""Módulo Demo (worker-side): app de ejemplo corrible de NOTAS sobre SQLite.

Luce el stack worker-side de tequio sin capa web: jobs de background (`@job`),
crons agendados (`@cron_task`), eventos/observers (1:N), comandos del Mediator (1:1),
el Pipeline de limpieza y los seeders/factories con Faker. La nota es pelada
(`id`/`title`/`body`/`archived`): ya no hay dueño ni Auth/Gate (tequio es worker-side).

Encarpetado LIBRE: este Demo usa la convención que generan los `make:*` —un archivo por
clase, agrupado en subcarpetas por rol (`Jobs/`, `Crons/`, `Observers/`, `Handlers/`,
`Mail/`, `Pipes/`, `Services/`, `Repositories/`, `Seeders/`, `Factories/`), con
`Events.py`/`Commands.py` sueltos por chicos. Es UNA forma de organizarse, no LA forma:
el discovery importa TODO el árbol del módulo (recursivo), así que organiza tu app como
quieras —ya como haga el programador su aplicación, nos vale—. La única convención de
lectura es `Console/Commands/` para el automontaje de los commands de CLI (ver más abajo).

Quickstart: `tequio migrate run` → `tequio db:seed` → arrancar el worker/scheduler
(`tequio queue work` / `tequio schedule run`). El launcher raíz `./jornal` envuelve
el mismo entry point `tequio`.
"""
