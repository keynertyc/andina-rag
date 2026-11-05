# Pruebas y evaluación

## Comprobaciones rápidas

Desde la raíz con uv y Node instalados:

```sh
uv sync --frozen
uv run ruff check backend scripts
uv run ruff format --check backend scripts
uv run mypy
uv run pytest -q -m 'not integration'
cd frontend
npm ci
npm run lint
npm test
npm run build
```

Las unitarias cubren límites y solapamiento del chunking, metadatos de origen, PDF corrupto,
validación Pydantic, citas inventadas, corrección acotada, bloqueo sin llamada al LLM,
backoff, agotamiento, duplicado ocupado y contrato del SDK Gemini (timeout, 429, 5xx y 400).
Las de React ejercitan edición/aprobación, error 409 y bloqueo desactualizado con citas visibles.

La regresión de Gemini usa el SDK real con `httpx.MockTransport`, sin una llamada de pago:
comprueba que el cuerpo contiene `responseJsonSchema` y `additionalProperties: false`,
en lugar del campo incompatible del esquema legado. Así cubre la serialización que no
ejercitan los dobles del método `generate_content`.

## PostgreSQL real

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d db redis
docker compose exec -T db createdb -U andina andina_test
TEST_DATABASE_URL=postgresql+psycopg://andina:local-demo-only@localhost:55432/andina_test uv run pytest -q --cov=app
```

Omite `createdb` si ya existe. El fixture verifica el sufijo `_test`, aplica Alembic y limpia
solo esa base. Sin la variable, integración se omite explícitamente. Los vectores deterministas
de prueba permiten comprobar SQL/filtros sin descargar modelos; la evaluación siguiente sí usa E5.

Integración cubre ingesta, búsqueda vectorial con metadatos, persistencia de revisión,
claves repetidas/conflictivas, tarea repetida, lock concurrente, versiones vigentes/históricas,
versión corrupta, bloqueo sin evidencia y publicación fallida recuperable.

## Worker y trazas reales

```sh
docker compose up -d --build
docker compose exec -T api python -m scripts.demo --url http://localhost:8000/api/v1 \
  --key demo-traza-001 --approve --verify-trace --jaeger-url http://jaeger:16686
```

Una clave nueva permite comprobar una traza de creación nueva. El script espera trabajo
real de Celery, comprueba citas y aprobación persistida, y consulta Jaeger para exigir
servicios API/worker y spans de recuperación/LLM en el mismo trace id. CI ejecuta este flujo
con el LLM simulado y embeddings hash explícitos; la demo normal usa E5.

Para comprobar caídas reales, con las guías de la demo indexadas:

```sh
uv run python -m scripts.check_resilience
```

Este comando detiene y reinicia **Redis y PostgreSQL de este proyecto**. Usa `finally` para
restaurarlos. Comprueba `503`, conservación del lote, reenvío idempotente, cuatro mensajes
Celery duplicados y persistencia de aprobación tras reinicio. Genera `reports/resilience.json`.
No lo ejecutes durante trabajo importante en este entorno local.

## Evaluación de calidad

```sh
make evaluate
```

También desde el host, con los puertos del override de desarrollo activos:

```sh
PYTHONPATH=backend DATABASE_URL=postgresql+psycopg://andina:local-demo-only@localhost:55432/andina \
  uv run python -m scripts.evaluate --check
```

Utiliza `samples/cases.json`: 20 casos, ocho de calibración y 12 de verificación. Crea
registros aislados en una transacción PostgreSQL y los revierte al terminar. No limpia datos
del usuario. Los documentos se extraen y embeben realmente, incluyendo el PDF.

La calibración recorre 0,70/0,75/0,80/0,85/0,90 y prioriza: menos generaciones negativas,
mayor recuperación de la regla esperada, mayor cobertura positiva y mayor umbral en empate.
El conjunto de calibración incluye reglas de título y descripción. El umbral resultante es 0,80;
también hay negativos ajenos al contenido aunque coincidan marca/categoría, para comprobar
que un ámbito coincidente no baste como evidencia. Los encabezados solos no son fragmentos.
si otro corpus produce otro valor, debe revisarse y configurarse explícitamente antes de usarlo.

La comparación usa recuperación léxica con fragmentos fijos de 400 tokens sin solapamiento y
el mismo generador. La métrica denominada Recall@5 mide presencia de la regla anotada entre
los cinco fragmentos; cada caso positivo tiene una regla relevante anotada. No se considera
una evaluación exhaustiva de todas las reglas del documento.

Objetivos del modo `--check`: citas válidas y bloqueos esperados 100 %, cumplimiento, evidencia
y cobertura positiva ≥ 90 % sobre los 20 casos. Se publican agregados de calibración,
verificación y total, con sus casos. El total conserva el falso negativo MA-004 (gorro rojo):
15/16 positivos generados y cuatro negativos correctamente bloqueados. Los porcentajes de
generación y bloqueo se reportan juntos para
que bloquear todo no apruebe la evaluación. La latencia media por caso corresponde a generación
y validación; la recuperación tiene su propia medida. El calentamiento del modelo queda fuera.

El reporte versionado se obtuvo con E5 real y plantilla simulada. No prueba calidad de Gemini,
entailment de cada afirmación ni robustez ante todos los ataques. La primera evaluación y su
corrección están conservadas: es una evaluación exploratoria, no un test ciego independiente.

## CI

Tres jobs: backend (lint/tipos/PostgreSQL real/evaluación E5), frontend (lint/componentes/build)
y smoke (stack completo con dobles deterministas y trazas). Sin claves de Gemini en GitHub.
`uv.lock` y `package-lock.json` controlan las versiones. Confirma el resultado remoto antes de entregar.

## Navegador con Nginx y worker reales

Se requiere Compose 2.24.4 o posterior para `!override`. La configuración separada fuerza
LLM simulado y embeddings hash, elimina la clave Gemini de API/worker y usa volúmenes/puertos
propios. No reutilices el nombre del proyecto de tu entorno de trabajo.

```sh
docker compose -p andinarag-check -f compose.yaml -f compose.test.yaml up -d --build --wait --wait-timeout 180
cd frontend
npm ci
npx playwright install chromium
npm run test:e2e
cd ..
docker compose -p andinarag-check -f compose.yaml -f compose.test.yaml stop
```

La UI de prueba es `http://localhost:18080`; la API es `18000`, PostgreSQL `_test` es `55433`
y Jaeger es `17686`. El navegador se puede dirigir a otra instancia determinista con
`E2E_BASE_URL=http://localhost:8080 npm run test:e2e`. CI ejecuta esta variante en su stack efímero.

Playwright comprueba carga de guía, lote real de Celery, conflicto con otro analista,
conservación de borrador, aprobación de solo lectura, reapertura, rechazo con descarte,
nueva versión y regeneración, además de menús, nonce renovado y diseño de 360 px.
Los datos son sintéticos y llevan ámbitos propios para permitir repetir la prueba.
Las capturas/trazas se guardan en `frontend/test-results/`, fuera de Git.

La suite backend incluye decisiones concurrentes, aprobación frente a activación, persistencia
fallida bajo bloqueo, recuperación manual y agotamiento real del presupuesto de intentos.
También mide que las listas de lotes y propuestas usan dos consultas por página con uno o
varios resultados, y verifica la última página exacta con `X-Has-More`.
Las pruebas React/HTTP cubren solo lectura, no-op en formulario, validación, borradores remotos,
reapertura, rechazo sin contenido, respuestas inválidas, detalles de error y contexto en la URL.

El recorrido adicional de navegación móvil comprueba sticky durante scroll, menú de tres
opciones, sección activa, Escape y retorno de foco, cambio a escritorio con menú abierto,
ancho de 320 px, navegación desde una posición desplazada y cancelación con borrador intacto.
La navegación se prueba sobre el mismo Nginx de producción, con CSP activa.
