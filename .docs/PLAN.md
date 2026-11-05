# Implementación y matriz de cumplimiento

El [enunciado](andinarag-prueba-tecnica.md) es la fuente de requisitos. Las decisiones
acordadas son Gemini/simulado, Docker local, bloqueo sin evidencia y conservación de historial.

La iteración de revisión y mantenibilidad está implementada y verificada localmente:
[plan y ejecución de mejoras](IMPROVEMENT_PLAN.md). La evidencia actual está en
[verification.md](../reports/verification.md#iteración-de-revisión-y-mantenibilidad-2026-11-05).
La ejecución remota de CI del nuevo candidato requiere publicar sus cambios.

## Etapas

| Paso | Resultado implementado | Verificación |
|---|---|---|
| 1 · Base | Monorepo, configuración, contratos y locks | Ruff, mypy, TypeScript y compilación |
| 2 · Persistencia | Migración inicial, extensión, índices y volúmenes | Alembic sobre PostgreSQL real |
| 3 · Ingesta | PDF/Markdown, límites, chunking, embeddings y versiones | Unitarias, integración y PDF sintético en demo |
| 4 · Generación | Recuperación con filtros, citas y proveedores | Validación, dobles del SDK y evaluación E5 real |
| 5 · Lotes | Deduplicación, bloqueos, reintentos y recuperación | Integración y comprobación de caídas reales |
| 6 · React | Guías, lotes y revisión persistente | Pruebas de componente, build y recorrido en Chrome |
| 7 · Calidad | CI, comparación de recuperación y trazas | Informes de `reports/` y demo con verificación Jaeger |
| 8 · Entrega | Documentación, ejemplos y revisión local; remoto público confirmado | Consultar CI del commit publicado en GitHub Actions |

Cada paso se verifica antes de declararlo terminado. Las evidencias concretas y limitaciones
de la sesión están en [verification.md](../reports/verification.md).

## Matriz

| Requisito | Implementación | Evidencia reproducible |
|---|---|---|
| API FastAPI/Pydantic | Entradas, respuestas y OpenAPI tipados | `/docs`, integración API |
| Subir guías PDF y Markdown | API, extractor pypdf y lectura UTF-8 | Demo con ambos tipos |
| Chunking justificado | Tokenizer E5, secciones, 400/60 | Pruebas de chunking; DECISIONS |
| Embeddings y pgvector | E5 local, `vector(384)` | Evaluación real e integración |
| Documento y versión | Tablas, checksum, activación atómica | Pruebas de cambio/fallo de versión |
| Metadatos, índice y umbral | Filtros marca/categoría; B-tree; coseno ≥ 0,80 | Integración y tabla de calibración |
| Propuesta estructurada | Pydantic y lista permitida de citas | Salida inválida/citas inventadas |
| Reintento de validación | Máximo dos llamadas por validación | Prueba del intento correctivo |
| Celery/Redis por producto | Tareas, prefetch y concurrencia fijados | Demo real y smoke CI |
| Idempotencia por lote/producto | Clave/hash, UNIQUE y advisory lock | Duplicados secuenciales/concurrentes |
| Backoff y límites | Tres reintentos, jitter, Retry-After | Unitarias y dobles HTTP 429/timeout |
| Estado consultable | Agregación desde ítems y error de publicación | Integración y UI de lotes |
| Lista filtrable React | Estado, lote y paginación | Recorrido UI |
| Original, propuesta y citas | Detalle comparativo con versión/página | Pruebas React y UI |
| Editar/aprobar/rechazar | PATCH transaccional y revisión optimista | Backend, componente y demo |
| Evaluación y casos esperados | 20 casos; ocho calibración y 12 verificación | `scripts.evaluate --check` |
| Comparación sencilla | Recuperación léxica con mismo generador | `reports/evaluation.json` |
| Compose de un comando | API, worker, Redis, PostgreSQL, UI, Jaeger | Build y demo completa |
| Integración contra PostgreSQL real | Base `_test`; migraciones | `TEST_DATABASE_URL=… uv run pytest` |
| LLM determinista en CI | Mock explícito y dobles del SDK | Jobs backend y smoke |
| Fallos explícitos | Errores HTTP y errores de ítem/versión | Unitarias, integración y resiliencia |
| Trazas distribuidas | API → publicación → worker → RAG → LLM | Demo con `--verify-trace` |
| Atributos y logs | Duración de spans, tokens reales, fragmentos, trace id | Jaeger y logs JSON |
| Seguridad de archivos e inyección | Límites previos al multipart, contenido validado, contexto no confiable | Pruebas y ARCHITECTURE |
| Reproducibilidad | uv.lock, package-lock, imágenes, modelo y Alembic | Arranque limpio y CI |
| Entregables documentales | README, DECISIONS y documentos técnicos | Este índice y enlaces |
| Repositorio público único | Remoto configurado del monorepo | Verificar publicación y commit antes de entregar |

No se ha enviado el enlace al portal de la prueba. Esa entrega congela el commit del remoto.
