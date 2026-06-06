# Errores de dominio (nunca falla en silencio)

tequio hereda de milpa un **tenet** que atraviesa todo el núcleo: **nunca falla en
silencio**. Un error que se traga —un `except: pass`, un parámetro ignorado, un
`return None` ambiguo— es deuda que se cobra a las 3am, cuando algo "no jala" y no hay
rastro de por qué. La regla es simple: **log-or-throw**. Todo error o se lanza (y un
borde lo convierte en una salida limpia) o se loguea (con una pista accionable). Nada se
traga.

En tequio (worker-side) eso se concreta en dos bordes:

- **CLI** — el borde de error de `tequio`/`jornal` distingue error esperado (mensaje
  limpio) de bug inesperado (conciso + traceback al log).
- **Lógica** — un bug (handler sin registrar) **truena rápido** (fail-fast); un fallo
  best-effort en remoto (un observer que falla, un cron degradado) **deja rastro
  observable**, nunca silencio.

## El tenet en tres modos

| Modo | Cuándo | Qué hace |
|------|--------|----------|
| **fail-fast** | Es un BUG de programación/config (comando del Mediator sin handler). | Truena ya, con un error claro que apunta al fix. |
| **log-or-throw** | Error de negocio esperado ("no existe", "ya existe"). | Lo lanzas como `DomainError`; el borde lo rinde limpio. |
| **best-effort OBSERVABLE** | Operación que puede degradarse sin romper el flujo (un observer secundario que falla). | Sigue, pero **loguea** lo que decidió y por qué. Nunca en silencio. |

La diferencia entre tequio y un `try/except` casero: aquí **no decides en cada `catch`**
si loguear o no. El borde (el del CLI) ya lo hace, de una forma, para todo. Tú solo
lanzas el error correcto desde donde ocurre.

## La jerarquía `DomainError`

Los errores de negocio viven en `tequio/Core/Errors`, **neutrales al transporte** a
propósito: la capa de persistencia (un `Repository.find_or_fail`) puede lanzarlos sin
importar ningún framework web (respeta el layering "persistencia ↛ web"). No saben que
existe el RFC ni el status HTTP como tal — solo llevan los datos que un borde mapea.

`DomainError` es la base. Cada subclase fija sus defaults (`status_code`, `error_code`,
`title`):

| Excepción | `status_code` | `error_code` | Significado |
|-----------|--------------|--------------|-------------|
| `ResourceNotFoundError` | 404 | `resource_not_found` | El recurso pedido no existe. Lo usa, p. ej., `Repository.find_or_fail()`. |
| `ConflictError` | 409 | `conflict` | Choque con el estado: duplicado, transición inválida. |
| `InvalidFilterError` | 422 | `invalid_filter` | El cliente pidió un filtro/orden fuera de la whitelist. |
| `HandlerNotFoundError` | 500 | `handler_not_found` | (BUG) Comando del Mediator sin `@handles`. |

La última es `500` a propósito: **no es error de cliente, es un bug tuyo** (olvidaste
`@handles(MiComando)` o el módulo no se descubrió) — por eso fail-fast en vez de un `4xx`
que confundiría.

> El `status_code` se conserva en cada error aunque tequio no tenga capa HTTP: es el dato
> neutral que el borde de transporte (en milpa, el handler RFC 9457) mapea. En tequio el
> CLI usa sobre todo `message` y `error_code`; ver abajo.

### Firma de `DomainError`

```python
class DomainError(Exception):
    status_code: int = 400
    error_code: str = "domain_error"
    title: str = "Domain error"

    def __init__(
        self,
        message: str,
        *,
        details: Any = None,
        error_code: str | None = None,
        status_code: int | None = None,
        title: str | None = None,
    ) -> None: ...
```

- `message`: la explicación de **esta** ocurrencia (lo que el CLI imprime).
- `details`: datos opcionales (qué id, qué campo). En `HandlerNotFoundError`, p. ej., el
  `command_type`.
- `error_code` / `status_code` / `title`: override **por instancia** sin tener que
  subclasear para cada caso puntual:

```python
raise DomainError("Saldo insuficiente", error_code="insufficient_funds",
                  status_code=409, title="Conflict")
```

### Forma tradicional vs. estilo milpa

**Forma tradicional** — el service decide a mano qué pasa cuando algo no existe (devuelve
`None` y quien llama adivina, o lanza un error acoplado al transporte):

```python
# Acoplado / ambiguo: el service traduce a mano, o regresa None y el caller adivina.
def find_note(note_id: int) -> Note | None:
    note = session.get(Note, note_id)
    if note is None:
        return None          # ¿404? ¿error? el caller no sabe
    return note
```

**Estilo milpa** — el dominio lanza lo que SABE explicar ("no existe"); el borde decide
cómo rendirlo. Ejemplo del demo (`Modules/Demo/Services/NoteService.py` usa este
patrón a través del repositorio):

```python
from tequio.Core.Errors import ResourceNotFoundError

def _find(note_id: int) -> Note:
    note = current_session().get(Note, note_id)
    if note is None:
        raise ResourceNotFoundError(f"Nota {note_id} no existe", details={"id": note_id})
    return note
```

Y un conflicto de duplicado:

```python
from tequio.Core.Errors import ConflictError

if self._email_taken(email):
    raise ConflictError("El email ya está registrado.", details={"email": email})
```

El comando/job **no atrapa** estos errores: los deja subir al borde del CLI. Un service
de dominio sin un solo `import` de framework web.

## El borde del CLI (`tequio` / `jornal`)

El CLI tiene su propio borde de error. Vive en `run()` de
`tequio/Core/Console/Cli.py`, que envuelve toda la app de Typer:

```python
def run() -> None:
    setup_logging()  # sinks configurados (stderr concisa + archivo)
    try:
        app()
    except DomainError as error:
        raise SystemExit(_render_cli_error(error)) from None
    except Exception as error:  # borde final del CLI: nada escapa sin loguearse
        raise SystemExit(_render_cli_error(error)) from None
```

`pretty_exceptions_enable=False` en la app de Typer es deliberado: **nosotros**
controlamos el render, para no escupir el traceback crudo de Rich (con locals) ante un
error esperado. El render distingue los dos casos:

```python
def _render_cli_error(error: BaseException) -> int:
    console = Console()
    if isinstance(error, DomainError):
        console.print(f"[red]✗[/red] {error.message} [dim]({error.error_code})[/dim]")
        return 1
    logger.opt(exception=True).error("CLI | error inesperado ({t})", t=type(error).__name__)
    console.print(f"[red]✗[/red] Error interno ({type(error).__name__}). El detalle quedó en el log.")
    return 1
```

| Tipo de error | En consola | En el log | Exit code |
|---------------|-----------|-----------|-----------|
| **`DomainError`** (esperado) | Mensaje LIMPIO + su `error_code`, sin traceback. | (nada extra) | `1` |
| **Inesperado** (bug) | Conciso: `Error interno (X). El detalle quedó en el log.` | Traceback **completo** vía loguru. | `1` |

Ejemplo en consola de un error de dominio:

```
✗ Nota 7 no existe (resource_not_found)
```

Y de un bug inesperado (el detalle no se pierde, va al log):

```
✗ Error interno (KeyError). El detalle quedó en el log.
```

- **No se traga**: `logger.opt(exception=True).error(...)` deja el traceback **completo**
  en el log (observable a las 3am).
- **No fuga**: a la consola le llega un mensaje genérico, **sin** el mensaje real de la
  excepción ni el stack.

### `diagnose`: valores en el traceback solo en dev

El traceback que loguea el CLI tiene un matiz de seguridad, controlado en
`setup_logging()` (`tequio/Core/Logging`):

- En `APP_ENV=local`: el traceback en consola muestra los **valores** de las variables
  (depuras rápido).
- En qa/production: el traceback sigue, pero **sin** los valores (no fuga tokens ni
  passwords a la consola).

El sink de archivo nunca persiste valores sensibles a disco, en ningún ambiente.

## El borde HTTP (RFC 9457) vive en milpa

milpa rinde **todo** error HTTP como `application/problem+json`
([RFC 9457 *Problem Details*](https://www.rfc-editor.org/rfc/rfc9457)), mapeando
`error_code → code`, `title → title`, `message → detail`, `details → errors`,
`status_code → status`. Por eso `DomainError` carga esos campos aunque tequio no los use
para HTTP: **el mismo error de dominio sirve a los dos bordes**, lo cual es justo el
punto de tenerlos neutrales al transporte.

> tequio es worker-side: **no** monta ese handler ni la respuesta `problem+json`. Si tu
> servicio sirve API o páginas, quieres [milpa](https://github.com/calcifux/milpa), que
> añade el borde HTTP sobre esta misma jerarquía.

## Receta

1. **En el dominio** (service/repository): lanza el `DomainError` que mejor describa el
   caso. No devuelvas `None` ambiguo.
2. **En el comando/job**: no atrapes los `DomainError`; déjalos subir al borde del CLI.
3. **Bugs**: deja que truenen. El borde los loguea con traceback completo y sale con un
   mensaje limpio. No los escondas con un `except: pass`.
4. **Best-effort**: si algo puede degradarse sin romper (un observer secundario), está
   bien — pero **loguea** qué decidiste y por qué. Best-effort sí; silencioso no.

## Siguiente paso

[Consola (`tequio` / `jornal`)](07-consola-jornal.md) — dónde el CLI rinde estos errores.
