# Imports perezosos (`tequio.lazy`) y análisis (`jornal scan`)

El auto-discovery de tequio importa **todos** los módulos de tu app al arrancar (para registrar
tasks, observers, rutas, modelos, crons). Eso es lo que hace que "las carpetas sean propuesta" y
todo se registre solo — pero también significa que un `import openpyxl` (o `pandas`, `torch`...)
al tope de un módulo se carga en **todos** los procesos, incluso en los que nunca lo usan: el
worker que no genera Excel carga openpyxl igual, el cron efímero también. En Python cada intérprete
es caro (~110 MB de base), y esas libs pesadas se suman donde no hacen falta.

## `tequio.lazy` — difiere la lib hasta el primer uso

```python
from tequio.lazy import openpyxl          # NO carga openpyxl aún (solo lo nombra)

def generar(...):
    wb = openpyxl.Workbook()             # se carga AQUÍ, la 1ª vez que se usa
    celda.font = openpyxl.styles.Font(bold=True)
```

- Es **opt-in y documentado**: el dev que escribe `import openpyxl` normal sigue igual (eager) — no rompe nada, solo no ahorra.
- Genérico para **cualquier** lib: `from tequio.lazy import pandas`, `numpy`, etc.
- Respaldado por `importlib.util.LazyLoader` (stdlib). El módulo queda como `_LazyModule` hasta que accedes a un atributo.

**Para submódulos** (la API de openpyxl vive en `.styles`/`.utils`): una vez cargado el paquete,
sus submódulos son accesibles (`openpyxl.styles.Font`). Para tipos en anotaciones, usa
`if TYPE_CHECKING:` — no disparan la carga.

**Límite honesto:** lazy es del **módulo**, no de `from openpyxl import Workbook` (esa forma accede
al atributo y carga). Y no accedas a la lib en el cuerpo del módulo (a nivel top-level) — solo
dentro de funciones —, o el discovery la carga igual.

## `jornal scan` — qué libs pesadas se cargan donde no van

```bash
jornal scan              # corre todas las capacidades sobre tu app
jornal scan --only http  # solo la capacidad de http
```

El comando construye un **modelo de la app** (vía el discovery que ya existe: el grafo de imports
al top-level + el estado eager/lazy de cada lib) y corre las **capacidades** — checks por concern:

| Capacidad | Qué detecta |
|---|---|
| `lazy` | libs pesadas (openpyxl, pandas, numpy, torch...) importadas **eager** — candidatas a `tequio.lazy`. Acredita ✓ las que ya están diferidas. |
| `http` | clientes http crudos (requests, httpx...) — a centralizar timeouts/trazas y diferir |
| `db` | engine/session de SQLAlchemy armados a mano — usa la sesión ambiente (`@transactional`) |
| `mongo` | drivers de Mongo crudos — aísla la conexión (lazy + config por `.env`) |

## Capacidades propias (auto-descubribles)

Como tasks y observers, una capacidad propia **se suelta y el discovery la encuentra** — sin
registro central:

```python
from tequio.scan import capability, Capability, Finding

@capability
class _Auditoria(Capability):
    name = "auditoria"
    def analyze(self, model):
        return [
            Finding("auditoria", "info", m.dotted, "módulo sensible: revisar permisos")
            for m in model.modules if "Admin" in m.dotted
        ]
```

`jornal scan --only auditoria` la corre. Cada capacidad que agregues hace **toda la flota** más
segura: encodeas las convenciones de tu equipo como conocimiento ejecutable.
