# Auditoría de cumplimiento y mantenibilidad

Fecha: 5 de noviembre de 2026. Fuente: [enunciado completo](andinarag-prueba-tecnica.md).
Base de la revisión: `e043ab8`, publicado en el único [repositorio público](https://github.com/keynertyc/andina-rag).
Su [CI remoto](https://github.com/keynertyc/andina-rag/actions/runs/42045149124) terminó correctamente.
Esta auditoría y sus regresiones se incorporan en el commit posterior; su resultado remoto
debe consultarse en Actions para ese commit.

Los 22 puntos técnicos y documentales del enunciado tienen implementación y evidencia
identificadas abajo. No se encontraron funcionalidades obligatorias pendientes después
de las correcciones. Esto no demuestra ausencia de bugs ni calidad perfecta del modelo:
la evaluación es pequeña, conserva un falso negativo y no mide un catálogo real.
Las condiciones personales y la entrega al portal se distinguen al final.

## Requisitos funcionales

| ID | Punto del enunciado | Implementación y evidencia |
|---|---|---|
| R1 | FastAPI y Pydantic: guías, lotes, estado y propuestas | [`schemas.py`](../backend/app/schemas.py), [`routers/`](../backend/app/routers/) y [contratos HTTP](API.md). `test_api_ingest_retrieve_edit_approve_and_idempotency` recorre subida, lote, consulta y PATCH. |
| R2 | Extraer, fragmentar, embeber y guardar documento/versiones en pgvector | [`ingestion.py`](../backend/app/ingestion.py), [`processing.py`](../backend/app/processing.py), [`embeddings.py`](../backend/app/embeddings.py) y [`models.py`](../backend/app/models.py). Pruebas de tokens/solapamiento/metadatos y versión fallida; evaluación extrae PDF y Markdown con E5 real. |
| R3 | Recuperación vectorial con filtro; esquema, índice y umbral documentados | [`retrieval.py`](../backend/app/retrieval.py) filtra marca, categoría, versiones y modelo; usa distancia coseno y umbral 0,80. [Arquitectura](ARCHITECTURE.md#recuperación), migración en [`backend/migrations/`](../backend/migrations/) y [decisión de índice](../DECISIONS.md#chunking-embeddings-llm-e-índice). Integración sobre PostgreSQL/pgvector real y evaluación de recuperación. |
| R4 | Título, descripción, etiquetas y citas validados; corrección acotada y fallo registrado | [`llm.py`](../backend/app/llm.py) y `GeneratedProposal`: máximo dos llamadas ante salida inválida, citas limitadas al contexto y evento `invalid_llm_output`. Pruebas Pydantic, citas inventadas y reintento; regresión del transporte real del SDK Gemini. |
| R5 | Celery/Redis, idempotencia por producto, backoff, concurrencia y estados | [`tasks.py`](../backend/app/tasks.py), [`services.py`](../backend/app/services.py), [`dispatch.py`](../backend/app/dispatch.py) y advisory locks en `processing.py`. Pruebas de claves repetidas/conflictivas, entrega duplicada/ocupada, agotamiento y recuperación. Demo con worker real; estados `pending/running/completed/with_errors`. |
| R6 | React: filtro, original, propuesta, citas y edición/aprobación/rechazo persistidos | [`features/review/`](../frontend/src/features/review/), [`reviews.py`](../backend/app/reviews.py). Pruebas de componente y tres recorridos Chromium con API, worker y Nginx; aprobación/rechazo de solo lectura hasta reapertura, revisión optimista y conservación de borrador. |
| R7 | Casos esperados y script con métricas de calidad | [`samples/cases.json`](../samples/cases.json), [`scripts/evaluate.py`](../scripts/evaluate.py) y [`reports/evaluation.json`](../reports/evaluation.json). `--check` comprueba citas, reglas, recuperación, cobertura positiva y bloqueo; compara recuperación léxica con el mismo generador. |
| R8 | Compose de un comando con API, worker, Redis, pgvector, UI y OTel local | [`compose.yaml`](../compose.yaml), Jaeger OTLP y `docker compose up --build` en README. Build y arranque de los seis servicios; demo verifica una traza distribuida real. |

## Nivel de calidad

| ID | Punto del enunciado | Implementación y evidencia |
|---|---|---|
| Q1 | Unitarias, integración PostgreSQL, componente React y LLM determinista en CI | [`backend/tests/`](../backend/tests/), pruebas junto a componentes/cliente HTTP y [`ci.yml`](../.github/workflows/ci.yml). 55 pruebas backend, 20 frontend; PostgreSQL real, sin SQLite ni llamadas a Gemini. CI también evalúa E5 real y ejecuta navegador/worker. |
| Q2 | Timeout/429, archivos corruptos, salida inválida y caída Redis/DB con errores HTTP/estado | `test_gemini.py`, `test_core.py`, `test_integration.py`; [`http.py`](../backend/app/http.py) y persistencia del error bajo lock. Cortes reales y recuperación registrados en [`resilience.json`](../reports/resilience.json) y [verificación histórica](../reports/verification.md). Esta iteración no vuelve a detener los servicios del usuario; sí repite las regresiones deterministas. PostgreSQL no puede registrar en sí mismo su propia caída: se documentan logs y reconciliación posterior. |
| Q3 | OTel API → Celery → RAG → LLM, latencia/tokens/chunks y logs correlacionados | [`telemetry.py`](../backend/app/telemetry.py), spans en ingesta/recuperación/generación, propagación Celery y `scripts.demo --verify-trace`. Duración del span mide latencia; tokens cuando el proveedor los informa; logs JSON con `trace_id/span_id`. Nuevas pruebas exportan spans reales en memoria y verifican que las excepciones no incluyen contenido privado del proveedor. |
| Q4 | Secretos, límites de archivos y mitigación de prompt injection con límites explícitos | `.env` ignorado, [configuración de ejemplo](../.env.example) sin clave y archivos rastreados revisados. Límite previo al multipart, validación de firma/extensión/UTF-8, páginas y texto; pruebas de documentos corruptos y tamaño. Contexto no confiable separado del sistema, modelo sin herramientas y lista permitida de citas; [seguridad y límites](ARCHITECTURE.md#seguridad). No se promete inmunidad semántica a inyecciones. |
| Q5 | Dependencias fijadas, migraciones, ejemplos sintéticos y CI de linters/pruebas | `uv.lock`, `frontend/package-lock.json`, versiones de imágenes/modelo, Alembic, [`samples/`](../samples/) y los tres jobs de GitHub Actions. README usa instalación congelada (`uv sync --frozen` / `npm ci`). |

## Decisiones exigidas

| ID | Pregunta | Respuesta documentada y comprobación |
|---|---|---|
| D1 | Evidencia insuficiente y umbral | [Bloqueo sin llamar al LLM](../DECISIONS.md#evidencia-insuficiente), umbral calibrado 0,80, falsos positivos/negativos explícitos. Unitarias y evaluación con negativos del mismo ámbito. |
| D2 | Nuevas versiones, coste y riesgo | [Versiones inmutables y activación transaccional](../DECISIONS.md#versiones-de-guías), histórico conservado, propuestas desactualizadas y regeneración explícita. Integración de activación fallida, historial y carrera aprobación/activación. |
| D3 | API síncrona/Celery e idempotencia | [Frontera y garantías](../DECISIONS.md#frontera-síncrona-y-asíncrona-idempotencia): validar/persistir/despachar frente a extraer/recuperar/generar; hash, claves únicas y lock. Se explica la ventana commit/publicación y recuperación manual; no se promete exactamente una llamada externa. |
| D4 | Chunking, embeddings, proveedor y comparación sencilla | [400 tokens/60 de solapamiento, E5 multilingüe y adaptadores Gemini/simulado](../DECISIONS.md#chunking-embeddings-llm-e-índice). Comparación con fragmentos sin solapamiento y recuperación léxica, mismo generador; evidencia esperada 10/10 frente a 9/10 positivos de verificación. Resultado exploratorio, no superioridad general. |

## Entregables

| ID | Entregable | Evidencia |
|---|---|---|
| E1 | Un repositorio público con backend, frontend e infraestructura | [keynertyc/andina-rag](https://github.com/keynertyc/andina-rag), visibilidad `PUBLIC` comprobada con GitHub CLI. Todo vive en el mismo monorepo. |
| E2 | README: desde cero, arquitectura, terminado/fuera de alcance, pruebas y evaluación | [`README.md`](../README.md), comandos Docker/uv/npm y enlaces operativos. La evaluación predeterminada ahora fuerza simulado + E5 aun si la aplicación usa Gemini. |
| E3 | DECISIONS: ambigüedades, trade-offs, IA, revisión y límites | [`DECISIONS.md`](../DECISIONS.md), incluidas limitaciones de evaluación, recuperación, seguridad, llamadas externas y revisión humana pendiente. No se atribuye revisión manual humana al trabajo de Codex. |
| E4 | Pruebas y evaluación con comandos documentados | [Guía de pruebas](TESTING.md), suites backend/frontend/navegador y `make evaluate`; ejecución real resumida abajo y en [`verification.md`](../reports/verification.md). |
| E5 | Guías/productos sintéticos y configuración sin secretos | [`samples/`](../samples/) incluye PDF/Markdown, CSV/JSON, casos y versión alternativa; `.env.example` permite iniciar con simulado sin clave. `scripts.demo` recorre el flujo. |

## Defectos encontrados y correcciones mínimas

Cada caso se reprodujo con una prueba que fallaba antes del cambio. Se conservan los
adaptadores, las transacciones de SQLAlchemy y la organización por funcionalidades;
no se introducen nuevas capas ni dependencias.

| Hallazgo | Corrección | Regresión |
|---|---|---|
| Una excepción saneada encadenaba el error del SDK/Pydantic; OTel podía exportar respuesta privada en `exception.stacktrace` | Suprimir la causa en las cuatro conversiones a errores de dominio; conservar código seguro, estado ERROR y stacktrace útil | Cinco casos en `test_llm_telemetry.py`: salida inválida, timeout, 400, 429 y 503, comprobando también el span padre |
| El simulado fallaba con una descripción válida de entrada mayor de 4.000 caracteres o con etiquetas Unicode ampliadas por `casefold` | Ajustar salida a sus límites; deduplicar después de normalizar y truncar | Dos casos de `test_core.py`, con original intacto y citas válidas |
| `make evaluate` heredaba Gemini pese a prometer una evaluación sin llamadas externas | Forzar `LLM_PROVIDER=mock` y `EMBEDDING_PROVIDER=fastembed`; Gemini queda como comando explícito | Comando revisado con `make -n evaluate`; evaluación real con E5 y simulado, `--check` correcto |
| Timeout/cancelación al leer el cuerpo HTTP se convertía en error de JSON | Preservar el error de aborto antes de clasificar una respuesta inválida | Dos casos en `client.test.ts`, después de recibir cabeceras |
| Descartar un borrador y cargar la revisión actual conservaba el error 409 anterior | Limpiar resultado de mutaciones y aviso al confirmar descarte; simplificar payload de acciones con tipos explícitos | Caso de conflicto y carga actual en `ProposalDetail.test.tsx` |
| Un error al refrescar detalle con datos en caché quedaba oculto | Mostrar el error sin desmontar el formulario ni perder el borrador | Caso de refetch 503 con borrador conservado en `ProposalDetail.test.tsx` |
| Un lote seleccionado fuera de los 50 recientes no refrescaba sus propuestas al terminar | Consultar su progreso por ID y actualizar propuestas al cambiar; detener polling cuando es terminal | `Review.test.tsx`, lote antiguo ausente de la página reciente |

## Secuencia de verificación

1. Leer los 22 puntos, las decisiones y contratos; inspeccionar rutas, SQL, locks, adaptadores
   y estados React. Revisar el backend de forma independiente, sin editar datos del usuario.
2. Consultar Context7 para el registro automático de excepciones de OTel, errores de refetch
   con caché de TanStack Query y aborto durante lectura del cuerpo con Fetch.
3. Reproducir los defectos, aplicar correcciones locales y conservar las regresiones.
4. Ejecutar Ruff/formato, mypy, 55 pruebas backend con PostgreSQL real, 20 frontend,
   ESLint, TypeScript y compilación de producción: correctos.
5. Ejecutar E5 real + simulado en base `_test`, transacción revertida: 20 casos,
   15/16 positivos, cuatro negativos bloqueados, citas/reglas 100 % sobre generados;
   `--check` correcto. Se conserva MA-004 como falso negativo conocido.
6. Construir el stack separado `andinarag-check`, con clave vacía, simulado/hash y volúmenes
   propios; verificar los tres recorridos Chromium y la demo con Celery/trazas reales.
   La evidencia concreta se incorpora en `reports/verification.md`; hash solo mide integración.
7. Revisar el diff, publicar el commit y comprobar los tres jobs remotos. La ejecución se
   identifica por SHA en GitHub Actions; no basta con un CI verde de un commit anterior.

## Mantenibilidad y límites de la revisión

La estructura actual es adecuada al alcance: monolito modular con workers; routers como
adaptadores HTTP, reglas de revisión centralizadas, consultas de páginas acotadas y adaptadores
pequeños para LLM/embeddings. React separa datos del servidor, borradores y navegación.
Material UI ya cubre los controles; el CSS residual tiene una responsabilidad concreta.
No se necesita añadir repositorios genéricos, microservicios, otro estado global o un kit UI.

Como mejora futura, puede medirse y reducirse la transacción de lectura durante el calentamiento
del embedder en recuperación. La llamada generativa ya ocurre fuera de la transacción.
No se modifica ahora el ciclo de vida de objetos SQLAlchemy por una optimización sin medición.
HNSW, outbox, OCR, autenticación y pruebas de carga requieren un objetivo operativo adicional;
el enunciado no obliga a incorporarlos para esta entrega. La referencia a 100k productos es
contexto del marketplace, no un benchmark exigido ni una capacidad demostrada.

## Condiciones externas pendientes

- El documento fija **5 de noviembre de 2026, 23:22 UTC** y 72 horas desde la recepción.
  No se dispone de evidencia de la hora original de recepción para auditar ese intervalo.
- La persona que entrega debe comprender y defender el código. Las pruebas y esta revisión
  asistida no sustituyen esa preparación ni una revisión humana.
- **No se ha enviado el enlace al portal**. Solo admite una entrega y congela el último commit
  publicado en ese momento; debe realizarla el usuario cuando decida que es la versión final.
