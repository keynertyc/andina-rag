# Operación local y entrega

## Arranque y diagnóstico

1. Ejecuta `docker compose up --build`. Espera la descarga inicial del modelo y al worker.
2. Comprueba `docker compose ps` y `http://localhost:8000/api/v1/health/ready`.
3. Ejecuta la demo del README o sube guías y productos desde la UI.
4. Si falla una operación, consulta su código y `docker compose logs --tail=100 api worker`.
5. Abre Jaeger, selecciona `andinarag-api` y busca el `X-Trace-ID` devuelto por la petición.
   Deben aparecer tareas, recuperación y LLM. Los tokens solo aparecen cuando el proveedor
   los proporciona; no se inventan conteos para la plantilla.

Los volúmenes conservan DB, Redis, fuentes y modelo. `docker compose down` detiene el stack
sin borrarlos. No uses `down -v` salvo que quieras eliminar explícitamente todos los datos locales.
Jaeger usa memoria: sus trazas sí desaparecen al reiniciarlo.

## Configuración

| Variable | Predeterminado | Uso |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` o `gemini`; visible en la UI |
| `GEMINI_API_KEY` | vacía | Obligatoria al seleccionar Gemini |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Modelo generativo |
| `EMBEDDING_PROVIDER` | `fastembed` | `hash` solo para pruebas deterministas |
| `SIMILARITY_THRESHOLD` | `0.80` | Similitud mínima por fragmento |
| `POSTGRES_*` | valores locales de ejemplo | Nunca reutilizarlos fuera de la demo |

Otros límites viven en `Settings` y código de validación. Si cambias proveedor/modelo, crea
lotes nuevos. Los existentes conservan configuración y pueden exigir restaurarla para reintentar.
No mezcles documentos indexados con hash y E5; el filtro de modelo impide compararlos.

## Recuperación

| Incidencia | Acción |
|---|---|
| Guía `error` | Corrige el archivo y sube nueva versión; para reintentar el mismo archivo, envíalo al mismo documento lógico |
| Redis no disponible | `docker compose start redis`; reutiliza `Idempotency-Key` o `POST /batches/{id}/retry` |
| Corte entre persistencia y envío | Consulta lotes pendientes y reenvíalos; el resultado ya persistido no se sobrescribe |
| PostgreSQL no disponible | `docker compose start db`; espera readiness y reenvía trabajo no finalizado si agotó recuperación automática |
| Timeout/429/5xx | Espera los tres reintentos; revisa cuota/configuración si termina fallido |
| Salida inválida | Consulta error del producto; tras una corrección fallida se requiere reintento explícito |
| Producto sin evidencia | Sube una guía pertinente y crea otro lote; reenviar el anterior no cambia su snapshot |
| Propuesta desactualizada | Usa «Regenerar con guías vigentes»; se conserva la anterior |
| Revisión 409 | Recarga la propuesta y revisa los cambios antes de guardar |

Para actualizaciones de código: `docker compose build api ui` y `docker compose up -d api worker ui`.
Durante desarrollo usa el mismo par de archivos Compose de manera consistente: cambiar entre
Compose normal y `compose.dev.yaml` recrea DB/Redis para aplicar o quitar puertos del host.

## Recorrido de demostración

1. Mostrar `/docs`, subir Puna Markdown y Kintu PDF; esperar versiones activas.
2. Importar productos CSV; mostrar progreso, cuatro negativos bloqueados y el falso negativo
   conservador MA-004. Explicar el coste del umbral con la evaluación.
3. Abrir una propuesta, comparar original, editar y guardar; aprobar otra y rechazar otra.
4. Cambiar filtros y recargar para comprobar persistencia; abrir citas y su página/versión.
5. Añadir Puna v2; mostrar la marca de desactualización y regenerar un producto.
6. Buscar el trace id de un lote nuevo en Jaeger y recorrer API → Celery → recuperación → LLM.
7. Ejecutar pruebas/evaluación y explicar comparación, límites e idempotencia con DECISIONS.md.

## Antes de entregar una única vez

- Confirmar `make check`, las pruebas con PostgreSQL real, la evaluación y el smoke completo.
- Repetir el arranque desde una copia limpia y revisar `.env.example`, ejemplos y enlaces.
- Revisar cambios con Git y verificar que no se incluyen `.env`, claves, cachés o archivos locales.
- Crear y publicar el commit en **un repositorio público**; comprobar que todo el monorepo
  está en el remoto y que GitHub Actions termina correctamente.
- Recorrer el código personalmente y confirmar que puedes defenderlo.
- Solo entonces pegar el enlace en el portal de la prueba. No se ha automatizado esa acción.
- Fecha del enunciado: 5 de noviembre de 2026, 23:22 UTC (18:22 en Lima).
