# Imports perezosos (`tequio.lazy`) y análisis (`jornal scan`)

## El principio (el camino tequio)

tequio **importa todos los módulos de tu app al arrancar** para registrarlos solos: tasks,
observers, rutas, modelos, crons. Eso es lo que hace que "las carpetas sean propuesta" y que
agregar un `@cron_task` o un `@Get` sea *solo crear el archivo*. Pero tiene una consecuencia:
un `import openpyxl` (o `pandas`, `torch`, `httpx`) **al top-level de un módulo** se carga en
**todos** los procesos que hacen ese discovery — aunque ese proceso nunca use la lib.

En Python cada intérprete es caro (~110 MB de base). Si el worker que **nunca** genera Excel
carga `openpyxl` igual, o el `schedule run` efímero carga libs que solo usa el web, estás
pagando RAM (y arranque) donde no hace falta. El camino tequio: **el discovery registra todo,
pero tú difieres lo pesado que cada proceso no siempre usa.**

## `tequio.lazy` — difiere la lib hasta el primer uso

```python
from tequio.lazy import openpyxl          # NO carga openpyxl aún — solo lo nombra

def generar(...):
    wb = openpyxl.Workbook()             # se carga AQUÍ, la 1ª vez que se usa
    celda.font = openpyxl.styles.Font(bold=True)
```

El módulo queda como `_LazyModule` (vía `importlib.util.LazyLoader`, stdlib) hasta que accedes
a un atributo. Es **opt-in**: el dev que escribe `import openpyxl` normal sigue igual (eager) —
no rompe nada, solo no ahorra. Y **genérico**: cualquier lib (`from tequio.lazy import pandas`,
`numpy`, lo que instales).

### Dos formas — elige según el uso

**Forma A — runtime puro (la limpia para pandas/numpy/requests):**
```python
from tequio.lazy import pandas
df = pandas.DataFrame(datos)             # el cuerpo usa pandas.X
```

**Forma B — la lib tiene TIPO en anotaciones + corres mypy strict** (p. ej. `httpx.Response`):
aquí la Forma A truena en mypy (ve `ModuleType`, no `httpx.Client`). Usa `TYPE_CHECKING` para
el tipo + import function-local para el runtime:
```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:                        # solo para anotaciones; no carga en runtime
    import httpx

class Cliente:
    def __init__(self):
        import httpx                      # function-local: carga solo al instanciar
        self._c = httpx.Client(...)
    def _check(self, r: httpx.Response): ...   # la anotación es string (future), usa el TYPE_CHECKING
```

### Los límites honestos

- Lazy es del **módulo**, no de `from openpyxl import Workbook` (esa forma accede al atributo y
  carga). Por eso difieres el módulo y cualificas el cuerpo (`openpyxl.Workbook()`).
- No accedas a la lib **en el cuerpo del módulo** (top-level) — solo dentro de funciones —, o
  el discovery la carga igual.
- Las **excepciones en `except`** necesitan la clase real → impórtala function-local.
- No baja el **piso obligatorio** (SQLAlchemy/pydantic/celery van en casi todo). Lazy trimea lo
  **opcional/pesado** del proceso que no lo usa, y acelera el **cold-start** (clave para
  `schedule run` efímero y scale-to-zero). No es magia: es disciplina.

## `jornal scan` — el copiloto que te enseña dónde

```bash
jornal scan              # corre todas las capacidades sobre tu app
jornal scan --only http  # solo una
```

Construye un **modelo de tu app** (grafo de imports al top-level + estado eager/lazy, usando el
discovery que ya existe) y corre **capacidades** por concern:

| Capacidad | Qué te dice |
|---|---|
| `lazy` | libs pesadas (openpyxl, pandas, numpy, torch...) importadas **eager** → sugiere `tequio.lazy`. Acredita ✓ las que ya difieres. |
| `http` | clientes http crudos (requests, httpx...) → centraliza timeouts/trazas y difiere |
| `db` | engine/session de SQLAlchemy a mano → usa la sesión ambiente (`@transactional`) |
| `mongo` | drivers de Mongo crudos → aísla la conexión (lazy + config por `.env`) |

No ejecuta acciones: **reporta** y te apunta al hint exacto. La magia 100% automática no es
posible (un `from X import Y` carga sí o sí), así que el scan es **diagnóstico**: te enseña
dónde aplicar el camino, no lo aplica a tus espaldas.

## Capacidades propias — encodea las convenciones de tu equipo

Como tasks y observers, una capacidad propia **se suelta y el discovery la encuentra** — sin
registro central:

```python
from tequio.scan import capability, Capability, Finding

@capability
class _Auditoria(Capability):
    name = "auditoria"
    def analyze(self, model):
        return [
            Finding("auditoria", "warn", m.dotted, "módulo sensible sin revisión de permisos")
            for m in model.modules if "Admin" in m.dotted
        ]
```

`jornal scan --only auditoria` la corre. Cada capacidad que agregues hace **toda la flota** más
segura: dejas de regañar en code review y dejas que el scan enseñe el camino solo. Eso es estilo
tequio — la convención vive como conocimiento ejecutable, auto-descubrible, que escala a N apps.
