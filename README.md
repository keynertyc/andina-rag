# AndinaRAG

Enriquecimiento de catálogo con guías versionadas, recuperación vectorial y revisión humana.
Monorepo de la [prueba técnica](.docs/andinarag-prueba-tecnica.md).

## Ejecutar desde cero

Necesitas Docker con Compose v2 o posterior, Internet para descargar las imágenes y el modelo,
y aproximadamente 6 GB de memoria disponibles para Docker. No necesitas una API key para la demo.

```sh
docker compose up --build
```

El arranque aplica las migraciones y prepara el modelo de embeddings. La primera descarga
del modelo ocupa aproximadamente 470 MB; se conserva en un volumen. El worker estará listo
cuando aparezca `ready` en sus logs.

| Servicio | Dirección |
|---|---|
| Aplicación React | http://localhost:8080 |
| API interactiva | http://localhost:8000/docs |
| Jaeger | http://localhost:16686 |

La configuración predeterminada usa **LLM simulado y embeddings multilingües reales**.
El indicador de la UI muestra el proveedor. PostgreSQL y Redis no se exponen al host.

En otra terminal, carga los datos sintéticos y ejecuta un lote:

```sh
docker compose exec -T api python -m scripts.demo --url http://localhost:8000/api/v1
```

El resultado actual es 15 propuestas y cinco bloqueos, sobre 20 productos: cuatro negativos
esperados y un falso negativo conservador (`MA-004`, gorro rojo) por similitud inferior al umbral.
Se conserva este caso para mostrar el límite de la recuperación, sin inventar evidencia.
El estado `with_errors` incluye los bloqueos. Abre **Mesa de revisión** para
comparar originales, editar y aprobar/rechazar. En **Guías de contenido** puedes subir
`samples/guides/puna-textiles-v2.md` como nueva versión de Puna y observar las propuestas
desactualizadas. Los ejemplos son completamente ficticios.

## Utilizar Gemini

```sh
cp .env.example .env
```

Edita `.env`: `LLM_PROVIDER=gemini` y tu `GEMINI_API_KEY`. El modelo configurable por defecto es
`gemini-3.5-flash-lite`. Después:

```sh
docker compose up -d --force-recreate api worker
```

Crea un lote nuevo para usar la nueva configuración. No se cambia de proveedor silenciosamente
cuando Gemini falla. La clave queda fuera de Git. La integración real con Gemini requiere una
cuenta con acceso al modelo; las pruebas automatizadas sustituyen su transporte o usan el simulado.

## Arquitectura

```mermaid
flowchart LR
  UI[React] --> API[FastAPI]
  API --> DB[(PostgreSQL + pgvector)]
  API --> Redis[(Redis)]
  Redis --> Worker[Celery · 2 procesos]
  Worker --> DB
  Worker --> E5[Embeddings E5 locales]
  Worker --> LLM[Gemini / simulado]
  API -. OTLP .-> Jaeger[Jaeger]
  Worker -. OTLP .-> Jaeger
```

Las rutas validan y persisten; los servicios coordinan reglas de negocio; Celery ejecuta
el trabajo costoso. Interfaces pequeñas permiten sustituir LLM y embeddings. SQLAlchemy
gestiona las transacciones sin una capa genérica de repositorios. PostgreSQL es la fuente
de verdad del estado, la deduplicación y las revisiones.

```text
backend/app/          API, servicios, adaptadores y tareas
backend/migrations/  migraciones Alembic versionadas
backend/tests/       pruebas unitarias y de integración
frontend/src/        consola de guías, lotes y revisión
samples/             PDF, Markdown, CSV, JSON y casos esperados
scripts/             demo, evaluación y comprobación de resiliencia
.docs/               contratos, arquitectura, pruebas y operación
```

## Pruebas y evaluación

Para desarrollo necesitas uv 0.9.3, Python 3.12 y Node 24.11 o compatible:

```sh
uv sync --frozen
cd frontend
npm ci
npm test
npm run lint
npm run build
cd ..
uv run pytest -q -m 'not integration'
uv run ruff check backend scripts
uv run mypy
```

La integración usa PostgreSQL real y una base independiente que termina en `_test`:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d db redis
docker compose exec -T db createdb -U andina andina_test
TEST_DATABASE_URL=postgresql+psycopg://andina:local-demo-only@localhost:55432/andina_test uv run pytest -q
```

Si la base ya existe, omite `createdb`. Sin `TEST_DATABASE_URL` se omiten las pruebas de
integración; no se sustituyen por SQLite. Más escenarios en [.docs/TESTING.md](.docs/TESTING.md).

Evaluación con PostgreSQL y embeddings reales, sin llamar a un LLM externo:

```sh
make evaluate
```

El comando copia el informe a `reports/evaluation.json`. Contiene calibración, verificación
y comparación con recuperación léxica. Los registros de evaluación se revierten al terminar.
Para medir Gemini, cambia la configuración como se indica arriba antes de ejecutar el comando.

GitHub Actions define lint/tipos/pruebas backend y frontend, evaluación real de embeddings y
una prueba completa con API, Celery, Redis y propagación de trazas.
[Ver ejecuciones de CI](https://github.com/keynertyc/andina-rag/actions/workflows/ci.yml).

## Estado y límites

Implementado: ingestión PDF/Markdown, versiones, pgvector con filtros, generación estructurada,
reintentos acotados, idempotencia, revisión persistente, trazas y logs correlacionados, datos,
migraciones, Compose y CI. Consulta la [matriz de requisitos](.docs/PLAN.md) y la
[evidencia de verificación](reports/verification.md).

Fuera del alcance: OCR, autenticación multiusuario, despliegue público, publicación al catálogo
y una prueba de carga de 100 mil productos. El corpus de vectores corresponde a las guías.
La comprobación de citas verifica referencias existentes, no demuestra por sí sola que cada
afirmación esté respaldada. La aprobación humana sigue siendo necesaria.

Lee [DECISIONS.md](DECISIONS.md), [la arquitectura](.docs/ARCHITECTURE.md),
[los contratos HTTP](.docs/API.md) y [el runbook](.docs/RUNBOOK.md).
