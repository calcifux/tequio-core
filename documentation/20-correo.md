# Correo

El correo en tequio sigue el patrón **Mailable** de Laravel: una clase encapsula "qué
correo es" (asunto, template, contexto, adjuntos) y la facade `Mail` lo envía, síncrono
o encolado.

```python
# Ejemplo ILUSTRATIVO: el import y la API son reales; `WelcomeMailable` es de ejemplo
# (el Mailable real del demo es `DailyDigestMailable`).
from tequio.Core.Mail import Mail
Mail.send(WelcomeMailable(name="Calcifux"), to=["calcifux@example.com"])
```

!!! info "Correo worker-side"
    tequio extrajo el correo de milpa porque **vuelve al worker**: muchos crons y jobs
    terminan mandando un correo (un resumen diario, una alerta, una notificación). Lo que
    NO viene es la capa **web** que lo disparaba (controladores HTTP, endpoints): aquí el
    correo nace de un cron, un job, un command de consola o un observer.

## Anatomía: `Mailable` + `MailContent`

Un Mailable hereda de la ABC `Mailable` (`tequio/Core/Mail/Mailable.py`) e implementa
`build()`, que devuelve un `MailContent` (el `WelcomeMailable` de abajo es **ilustrativo**;
el Mailable real del demo es `DailyDigestMailable`):

```python
from tequio.Core.Mail.Mailable import Mailable, MailContent
from tequio.Core.Translate import t, current_locale

class WelcomeMailable(Mailable):
    def __init__(self, name: str):
        # SOLO primitivos serializables (ver "Encolar" más abajo).
        self._name = name

    def build(self) -> MailContent:
        return MailContent(
            subject=t("emails.welcome.subject", {"name": self._name}),
            template="mymodule/mail/welcome.html.j2",
            context={"name": self._name, "locale": current_locale()},
        )
```

`build()` arma el **payload puro** — no toca SMTP ni Jinja directamente.

### Campos de `MailContent`

| Campo | Tipo | Para qué | Laravel |
|-------|------|----------|---------|
| `subject` | `str` | Asunto (ya traducido por ti). | `->subject()` |
| `template` | `str` | Ruta del template Jinja (compartido o `modulo/...`). | `->view()` |
| `context` | `dict` | Variables del template. | `->with()` |
| `from_email` / `from_name` | `str \| None` | Remitente; si `None`, usa el default de settings. | `->from()` |
| `inline_assets` | `dict[str, Path]` | CID → ruta (imagen embebida). En HTML: `<img src="cid:logo">`. | `$message->embed()` |
| `attachments` | `list[Path]` | Adjuntos por ruta (archivos en disco). | `->attach()` |
| `data_attachments` | `list[DataAttachment]` | Adjuntos por **bytes** en memoria. | `->attachData()` |
| `cleanup_paths` | `list[Path]` | Rutas a borrar tras enviar (opt-in). | `File::delete()` en `finally` |

## Enviar: la facade `Mail`

### Síncrono — `Mail.send`

```python
Mail.send(mailable, *, to, cc=None, bcc=None)
```

Construye y manda **en el acto** por SMTP. No usa redis ni worker; bloquea hasta que
SMTP responde. Ideal para local sin broker, tests, o cuando necesitas confirmar el envío.

### Encolado — `Mail.queue`

```python
Mail.queue(mailable, *, to, cc=None, bcc=None, queue=None, init_kwargs=None)
```

Encola el envío en Celery (no bloquea). Parámetros:

- `queue`: cola de Celery (ej. `"emails"`); `None` = cola por defecto.
- `init_kwargs`: los argumentos primitivos para **reinstanciar** el Mailable en el
  worker. Deben coincidir con el `__init__`.

```python
mailable = WelcomeMailable(name="Calcifux")
Mail.queue(mailable, to=["calcifux@example.com"], queue="emails",
           init_kwargs={"name": "Calcifux"})
```

Por convención, los correos van a la cola **`emails`** (ver [La cola de correos](#la-cola-de-correos)),
que un worker consume con `queue work --queue emails`.

Si el broker está caído, `Mail.queue` lanza `QueueUnavailableError` (un mensaje claro,
no un 500 técnico). En un worker o un cron lo capturas y decides: reintentar, caer al
envío síncrono, o solo loguear que la cola no está disponible:

```python
from tequio.Core.CeleryApp import QueueUnavailableError

try:
    Mail.queue(mailable, to=to, init_kwargs={...})
except QueueUnavailableError as e:
    logger.warning("cola de correo no disponible: {e}", e=e)
    # ...reintentar más tarde, o caer a Mail.send(...) si el envío no puede esperar.
```

## La cola de correos

Por convención, **los correos van a la cola `emails`** (= `->onQueue('emails')` de Laravel):
al encolar pasas `queue="emails"`, y el worker la consume con

```bash
tequio queue work --queue emails
```

Una cola dedicada deja los correos en su propio carril: un pico de envíos no atasca tus
jobs, y puedes escalar los workers de correo por separado. El generador `make mailable` ya
escribe este patrón en el stub (ver [Consola](07-consola-jornal.md)), y el cron `daily_digest`
del demo encola así.

La cola `emails` **no es mágica**: es solo un nombre. Lo que la hace existir es que un worker
la consuma. Si arrancas `queue work` **sin** `--queue`, ese worker procesa la cola **por
defecto** (`celery`), no `emails`. Para consumir ambas en un mismo worker, lístalas:

```bash
tequio queue work --queue emails,celery   # correos + la cola por defecto
```

> Si encolas a `emails` pero ningún worker la consume, los correos se quedan esperando en el
> broker (no se pierden, pero tampoco salen). En dev sin broker no necesitas nada de esto: usa
> `Mail.send` (síncrono) o el driver `log`, abajo.

## El contrato del constructor: solo primitivos

Al encolar, el Mailable se **reinstancia en el worker** desde su dotted path +
`init_kwargs`, y **`build()` corre allí** (worker-side). Por eso el constructor solo
debe recibir primitivos serializables (str, int, listas de str, ids). Nada de sesiones
de BD ni clientes HTTP: no se serializan. Si necesitas más datos, pasa un id y recupéralo
en `build()`.

Ventaja: si `build()` genera bytes (un PDF), esos bytes **no viajan por la cola** — se
generan en el worker.

## Adjuntos

### Por bytes (recomendado)

Sin tocar disco, sin cleanup:

```python
from tequio.Core.Mail.Mailable import DataAttachment

content.data_attachments.append(
    DataAttachment("reporte.pdf", pdf_bytes, "application/pdf")
)
```

### Por archivo + cleanup opt-in

Si el PDF ya vive en disco como temporal, adjúntalo por ruta y **declara** su limpieza:

```python
content.attachments.append(temp_path)
content.cleanup_paths.append(temp_path)   # el Mailer lo borra tras enviar (finally)
```

El framework **nunca** borra un `attachments` por su cuenta: solo lo que declares en
`cleanup_paths`. Un asset persistente (un PDF fijo) va en `attachments` y NO en
`cleanup_paths`.

### Logo inline por CID

```python
content.inline_assets["logo"] = Path("app/Resources/Images/Emails/logo.png")
content.context["logo_cid"] = "logo"
```

En el template: `<img src="cid:logo">`. (El header SMTP usa `<logo>`; en el HTML va sin
ángulos.)

## Plantillas (jinja)

El HTML de cada correo lo renderiza el **`TemplateEngine`** (`tequio.Core.View`) — el "Blade"
de tequio: un solo `Environment` de Jinja2 por proceso, **autoescape ON** (default seguro) y
**`StrictUndefined`**: una variable faltante en la plantilla **revienta** en lugar de
renderizar vacío en silencio (un correo a deudores debe fallar visiblemente en QA, no llegar
con campos en blanco).

### Dónde viven y cómo se resuelven

El loader busca en este **orden de prioridad**:

| # | Dónde | Cómo se referencia |
|---|-------|--------------------|
| 1 | `Modules/<X>/Resources/Views/` (por módulo, viaja con él) | namespaced con el módulo en minúsculas: `"demo/emails/digest.html.j2"` (= `demo::emails.digest` de Laravel) |
| 2 | `USER_VIEWS_DIR` del `.env` (carpeta de TU proyecto) | ruta relativa: puede **pisar** los layouts del framework |
| 3 | La raíz compartida del paquete (`tequio/Resources/Views/`) | ruta relativa: `"Emails/Trans/mastersigned.html.j2"` |

En la raíz compartida ya vienen los **layouts de correo** listos para extender:
`Emails/Trans/master.html.j2` (pelón) y `Emails/Trans/mastersigned.html.j2` (con header de
logo + footer firmado), más sus parciales (`Footer/`, `Styles/`).

### Crear tu plantilla

La del digest del demo es el ejemplo mínimo completo
(`Modules/Demo/Resources/Views/emails/digest.html.j2`):

```html+jinja
{% extends "Emails/Trans/mastersigned.html.j2" %}
{% block content %}
    <h2 style="margin:0 0 12px;">Resumen diario</h2>
    <p>Hoy hay <strong>{{ total }}</strong> notas en total.</p>
{% endblock %}
```

El `context` que pasas en `MailContent` llega como variables (`{{ total }}`). Dos **globals**
ya están registrados en todos los templates sin importar nada: **`t()`** (i18n, ver
[Monolingüe vs. i18n](#monolingue-vs-i18n)) y **`app_name`** (la marca del proyecto, desde
`APP_NAME`). Para cadenas con HTML legítimo usa `| safe` (≈ `{!! !!}`).

Si vienes de Laravel, el mapeo es 1:1:

| Blade (legacy) | Jinja (tequio) |
|---|---|
| `@extends('emails.trans.master')` | `{% extends "Emails/Trans/master.html.j2" %}` |
| `@yield('content')` / `@section` | `{% block content %}{% endblock %}` |
| `@include('emails.trans.footer.x')` | `{% include "Emails/Trans/Footer/x.html.j2" %}` |
| `{!! __('ns.key', $vars) !!}` | `{{ t('ns.key', vars) \| safe }}` |
| `{{ $data->x ?? '----' }}` | `{{ data.x or '----' }}` |

> El logo del layout firmado se embebe **por CID** (ver [Logo inline por
> CID](#logo-inline-por-cid)): el `mastersigned` pinta `<img src="cid:{{ logo_cid }}">` solo
> si el Mailable adjuntó el logo.

!!! tip "El motor y `t()` no son exclusivos del correo"
    El `TemplateEngine` (`tequio.Core.View`) es **genérico**: `render()` sirve para cualquier
    salida con plantilla (un reporte, un fichero generado), no solo el HTML del Mailable. Y
    `t()` (`tequio.Core.Translate`) es una función standalone: puedes traducir **fuera** de un
    Mailable —en un job, un cron o un command— sin pasar por el correo.

## Drivers (`MAIL_DRIVER`)

| Driver | Comportamiento |
|--------|----------------|
| `smtp` (**default**) | Envío real por SMTP, según `MAIL_*` y `MAIL_ENCRYPTION` (`""`/`tls`/`ssl`). El default apunta a **Mailpit** (`MAIL_HOST=localhost`, `MAIL_PORT=1025`). |
| `log` | Loguea el correo completo (el MIME), **no** lo envía. **Recomendado** en dev sin SMTP. |
| `null` / `array` | No-op: lo descarta. |

El default es `MAIL_DRIVER=smtp`, apuntando a **Mailpit** (`MAIL_HOST=localhost`,
`MAIL_PORT=1025`): con `docker compose up -d` los correos llegan a Mailpit y los ves en
`http://localhost:8025`. Sin Mailpit (ni otro SMTP) ese envío falla, así que para dev sin
SMTP **pon `MAIL_DRIVER=log`**: el correo se **vuelca al log** sin abrir ninguna conexión
SMTP — arrancas un cron que manda correo y ves el MIME completo en `logs/` sin levantar un
servidor.

## Probar correos directo en el repo

¿Quieres ver el correo del demo **sin** levantar SMTP, redis ni Mailpit? El truco es
combinar tres cosas: **SQLite** (`DATABASE_URL`, la BD de juguete), el driver **`log`**
(`MAIL_DRIVER=log`, el MIME al log en vez de SMTP) y un **broker a un puerto muerto**
(`BROKER_URL`) para que `Mail.queue` falle limpio y el cron caiga al envío síncrono:

```bash
DATABASE_URL="sqlite:///probar_correo.db" \
MAIL_DRIVER=log \
BROKER_URL="redis://127.0.0.1:1/0" \
uv run python - <<'PY'
# Crea la tabla `notes` en la SQLite (vacía: el digest cuenta 0 y manda igual).
from tequio.Core.Database import Base, engine
import tequio.Models.Note  # registra Note en la metadata

Base.metadata.create_all(engine)

# Dispara el cron a mano: Mail.queue("emails") falla (broker muerto) -> cae a Mail.send,
# y con MAIL_DRIVER=log el MIME COMPLETO se vuelca al log (subject, To, HTML, logo por CID).
from tequio.Modules.Demo.Crons.DailyDigestCron import daily_digest

daily_digest()
PY
```

En la salida verás la línea `Mailer[log] | correo NO enviado (driver=log):` seguida del
**MIME completo** del correo (cabeceras `Subject`/`To`, el cuerpo HTML y el logo embebido por
CID en base64). El `BROKER_URL` apunta a `127.0.0.1:1` (un puerto donde nadie escucha): así
`Mail.queue` lanza `QueueUnavailableError` y el cron toma su rama síncrona — exactamente el
fallback que documenta [el cron del demo](#el-cron-que-manda-correo). Borra la BD con
`rm probar_correo.db` al terminar.

> En el proyecto que genera `tequio new`, el cron vive en `app.Modules.Demo.Crons.DailyDigestCron` y el modelo
> en `app.Models.Note` (no `tequio.*`): ajusta los imports del snippet a tus paquetes. Aquí van
> con el prefijo `tequio.*` porque corremos contra el repo del framework.

## Monolingüe vs. i18n

| Caso | Patrón |
|------|--------|
| **i18n** | `subject` con `t()`, template que extiende los layouts y usa `t()`. El locale es **explícito** (lo pasa quien dispara el correo) o cae al `APP_FALLBACK_LOCALE`. |
| **Monolingüe** | `subject` literal, template con texto fijo (sin `t()`, sin `extends`). |

Una app es monolingüe salvo que decidas traducir. tequio **sí** trae el i18n de los
correos (la dep `i18nice[YAML]` y el wrapper `tequio.Core.Translate`); lo que NO trae es
el i18n de la **UI** (eso vive en milpa, junto con la capa web).

Como tequio es worker-side, **no hay request ni `Accept-Language`** del cual sacar el
idioma: el locale lo eliges tú. Para un correo multilingüe, pasa el `locale` como un
primitivo más del Mailable (viaja en `init_kwargs` al encolar) y úsalo explícitamente en
`build()`; si no lo pasas, `t()` cae al `APP_FALLBACK_LOCALE` configurado.

```python
# Ejemplo ILUSTRATIVO del patrón i18n (subject + cuerpo desde catálogo, con locale explícito).
class NoteCreatedMailable(Mailable):
    def __init__(self, title: str, locale: str = "es") -> None:
        self._title = title
        self._locale = locale

    def build(self) -> MailContent:
        subject = t("demo/NoteCreated.subject", {"title": self._title}, self._locale)
        return MailContent(
            subject=subject,
            template="demo/emails/note_created.html.j2",
            # `locale` explícito en el contexto: gana sobre el current_locale() que inyecta el
            # Mailer, así el template traduce en el idioma que decidiste aunque corra en el worker.
            context={"title": self._title, "locale": self._locale},
        )
```

## Los correos del demo (`tequio new --demo`)

El módulo `Demo` trae un Mailable de referencia (en `Demo/Mail/DailyDigestMailable.py`) sobre un
**layout firmado** (`Emails/Trans/mastersigned.html.j2`: header + contenido + footer con
la firma del remitente + aviso de privacidad). El Mailable solo define `subject`, su
`template` (que `{% extends %}` el firmado) y su contexto:

| Mailable | Disparador | Demuestra |
|----------|-----------|-----------|
| `DailyDigestMailable` | Cron `demo.daily_digest` (8:00 AM) | Correo desde un **cron** sobre el layout firmado compartido; subject con el conteo; logo por CID. |

Recibe **solo primitivos** (`total`) — sin `User` ni dueño (tequio no tiene Auth; el digest
es un resumen ANÓNIMO con el conteo de notas; ver
[Eventos y Observers](15-eventos-y-observers.md)). La firma del footer es del "Equipo
tequio". El subject es monolingüe (ES) con el conteo; el plumbing i18n de `t()` sigue
disponible (lo usan el footer firmado y el aviso de privacidad del layout).

### El cron que manda correo

El demo trae un **resumen diario** (`@cron_task` en `Demo/Crons/DailyDigestCron.py`) que **sí manda un
correo** (es justo el caso que motivó traer el correo al worker): el scheduler lo dispara
a las 8:00, cuenta las notas y manda el digest.

```python
@cron_task(name="demo.daily_digest", schedule=daily_at("08:00"), output="demo_digest")
def daily_digest() -> None:
    """Corre en el WORKER cada día a las 8:00 (lo despacha `schedule run`)."""
    total = len(NoteRepository().all())
    mailable = DailyDigestMailable(total=total)
    try:
        Mail.queue(mailable, to=["admin@example.com"], queue="emails")
    except QueueUnavailableError:
        Mail.send(mailable, to=["admin@example.com"])   # broker caído: envío síncrono
```

!!! note "Transcripción simplificada"
    En el código real el destinatario es la constante `_DIGEST_TO` (= `"admin@example.com"`,
    el mismo valor) y, antes de enviar, el cron loguea el conteo con
    `logger.info("demo.daily_digest | {n} notas...", n=total)`. Aquí se omiten por brevedad;
    el flujo es idéntico.

Worker-side lo idiomático es **encolar** (`Mail.queue`) a la cola `emails`; si el broker
no está, caemos al envío **síncrono** (`Mail.send`). Con el default `smtp` el correo va a
Mailpit (`docker compose up -d`) y lo ves en la UI; con el driver `log` se vuelca al log
sin SMTP (útil en dev sin Mailpit). Ver
[Programación (cron)](14-programacion-cron.md).

## Siguiente paso

[Logging](18-logging.md).
