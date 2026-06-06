# Logging

tequio usa **Loguru**. El logging se configura al arrancar (worker, beat y CLI), de forma
que todos los procesos escriban igual. Celery **no** secuestra el root logger: Loguru lo
maneja vía un `InterceptHandler` que redirige el `logging` estándar hacia Loguru.

## Usar el logger

```python
from loguru import logger

logger.info("Procesando pedido {id}", id=pedido_id)
logger.warning("Reintento {n}/{max}", n=intento, max=3)
logger.error("Falló el proveedor: {body}", body=respuesta)
```

Usa el estilo de Loguru (`{campo}` + kwargs), no f-strings, para que los campos queden
estructurados (así viajan limpios a la salida JSON).

## Configuración

| Setting | Default | Para qué |
|---------|---------|----------|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOG_JSON` | `false` | `true` añade una salida **JSON Lines** en `logs/app.jsonl`. |
| `LOG_DIR` | `logs` | Directorio de logs. |

```bash
LOG_LEVEL=DEBUG
LOG_JSON=true        # para ingestión en Loki/Grafana, Datadog, etc.
```

Estos tres son settings reales de `tequio.Core.Config` (`log_level`, `log_json`, `log_dir`).
Con `LOG_JSON=true`, además de la consola y el archivo legible, cada línea se escribe como un
objeto JSON por evento (`serialize=True`), apto para parseo automático.

!!! info "`diagnose` solo en local"
    El sink de consola activa `diagnose=True` **solo** cuando `APP_ENV=local`. `diagnose`
    agrega los **valores** de las variables al traceback (muy útil al depurar), pero puede
    **filtrar datos sensibles** (tokens, passwords) a la consola. En `qa`/`production` se apaga;
    los archivos de log siempre lo tienen en `False`.

## Qué configura `setup_logging`

`setup_logging()` (`tequio/Core/Logging/Logging.py`) arma los sinks una sola vez por proceso
(es idempotente: la segunda llamada no hace nada). Monta:

| Sink | Detalle |
|------|---------|
| **Consola** (`sys.stderr`) | Al `LOG_LEVEL`, formato legible, `enqueue=True`, `backtrace=True`. `diagnose` solo en `local`. |
| **Archivo de texto** `logs/app.log` | Rotación diaria a medianoche (`rotation="00:00"`), retención **14 días**, comprimido en `zip`. |
| **Archivo JSON** `logs/app.jsonl` | Solo si `LOG_JSON=true`. Misma rotación/retención/compresión, `serialize=True`. |

El formato de texto es:

```
{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name} | {message}
```

(expuesto como `_LOG_FORMAT`, que el módulo de [Cron](14-programacion-cron.md) reusa para sus
sinks por-cron.)

## El `InterceptHandler`: capturar el `logging` estándar

tequio define un `_InterceptHandler` (subclase de `logging.Handler`) que **redirige los
registros del `logging` estándar de Python hacia Loguru**. Así, lo que emite Celery —que usa
el `logging` de la stdlib— sale por los mismos sinks de Loguru, con el mismo formato, en vez
de por un canal aparte.

Al configurar, `setup_logging`:

1. Reemplaza los handlers del root logger por el `_InterceptHandler` (`logging.basicConfig(...,
   force=True)`).
2. Le quita a `celery` sus handlers propios y le pone el `_InterceptHandler`, con
   `propagate=False`, para que no escriba doble.

El handler mapea el nivel del record de stdlib al nivel de Loguru y ajusta la profundidad del
frame para que el origen del log apunte al sitio real, no al handler.

## Logs por cron (`output=`)

Un `@cron_task(output="demo_digest")` rutea los logs de **esa** corrida a un archivo propio
con rotación diaria y retención: `logs/cron_demo_digest.log`. Así separas la salida de cada
cron sin mezclarla con el log general. Lo monta `tequio.Core.Cron` reusando `_LOG_FORMAT` y un
`filter` por la clave `cron` del contexto de Loguru. Ver [Cron](14-programacion-cron.md).

## Dónde salen los logs

- **`tequio queue work`** (worker): la salida de las tasks sale en la terminal del worker
  y en `logs/`.
- **`tequio schedule run`** (scheduler): consola + `logs/`.
- **Crons con `output`**: además, su archivo dedicado `logs/cron_<output>.log`.

El directorio `logs/` está en `.gitignore` (no se versiona).

!!! note "Sin capa web"
    En milpa había además el sink de `jornal serve` (la API HTTP). tequio es **worker-side**: no
    tiene servidor HTTP (eso vive en [milpa](https://github.com/calcifux/milpa)), así que los logs nacen
    del worker, el scheduler y la CLI.

## Siguiente paso

Volver al [índice](README.md) o repasar los patrones: [Eventos y Observers](15-eventos-y-observers.md),
[Mediator](16-mediator.md), [Pipeline](17-pipeline.md).
