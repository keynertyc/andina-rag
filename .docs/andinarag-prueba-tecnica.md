# AndinaRAG

Nombre propuesto del proyecto: AndinaRAG.

> Contenido de la prueba técnica convertido desde el PDF original. Se ha adaptado el formato a Markdown y se han omitido los encabezados y pies de página repetidos.

## TopDevCrew · Prueba técnica Enriquecimiento de catálogo con RAG: FastAPI, Celery, pgvector y React con trazabilidad OpenTelemetry

Ingeniero AI Full Stack Semi-Senior · Entrégala antes del 5 de noviembre de 2026 a las 23:22 UTC

## Cómo funciona

- Tienes 72 horas desde que te enviamos este proyecto.

- Puedes usar IA generativa (Claude, Copilot, ChatGPT…) como quieras.

- Solo puedes entregar UNA VEZ. Al pegar el link, congelamos el último commit de tu repositorio en ese momento. Esa es la versión que evaluamos y la que revisamos en la entrevista; los commits posteriores se ignoran y no hay una segunda entrega. Asegúrate de que el repositorio esté listo antes de pegar el link.

- Sube tu trabajo a UN repositorio PÚBLICO de GitHub. Si el proyecto tiene varias partes (backend, frontend, infraestructura), van juntas en ese único repositorio (monorepo). No aceptamos repositorios privados, varios repositorios ni archivos zip.

- En la entrevista técnica vas a recorrer tu código en tu propia pantalla y defender tus decisiones. Entrega solo lo que entiendas.

- Donde algo sea ambiguo, decide y explica por qué en DECISIONS.md.

## El proyecto

Mercadia Andina, un marketplace ficticio con unos 100k productos, tiene guías de marca y políticas de contenido en PDF y Markdown, y cada vendedor las aplica a su manera. El equipo de merchandising publica fichas con títulos inconsistentes y descripciones que incumplen esas guías. Te pedimos un servicio que ingiera los documentos de guías, los trocee y los indexe en PostgreSQL con pgvector, y que genere propuestas de enriquecimiento (título, descripción y etiquetas) para productos de un CSV o JSON. Cada propuesta debe estar fundamentada en fragmentos recuperados de las guías y debe citarlos. El procesamiento por lotes corre en workers Celery con Redis. Un analista revisa, edita, aprueba o rechaza las propuestas desde una UI en React. Todo el flujo, desde la petición HTTP hasta la llamada al LLM, debe poder seguirse con trazas de OpenTelemetry. Puedes usar Gemini, Ollama o un LLM simulado, detrás de la abstracción que prefieras (LiteLLM o Pydantic AI son opcionales).

## Requisitos

- API en FastAPI con modelos Pydantic para: subir documentos de guías, lanzar un lote de enriquecimiento a partir de productos, consultar el estado del lote y listar o actualizar propuestas.

- Pipeline de ingesta de documentos: extrae texto (Docling es opcional, puedes usar otra herramienta), lo divide en fragmentos con una estrategia justificada, genera embeddings y los guarda en PostgreSQL con pgvector, con metadatos de documento y versión.

- Recuperación de los fragmentos más relevantes por producto, con búsqueda vectorial y al menos un filtro por metadatos (por ejemplo, categoría o marca). Documenta el esquema, el índice y el umbral de similitud elegidos.

- Generación de propuestas con salida estructurada validada con Pydantic (título, descripción, etiquetas, lista de citas a fragmentos). Si la salida no valida, reintenta de forma acotada y registra el fallo.

- Procesamiento por lotes con Celery y Redis: tareas idempotentes por producto, reintentos con backoff, límite de concurrencia y estado de lote consultable (pendiente, en curso, completado, con errores).

- UI en React para revisar propuestas: lista filtrable por estado, vista de detalle con el producto original, la propuesta y las citas visibles, y acciones de editar, aprobar y rechazar con persistencia.

- Evaluación mínima de calidad: un pequeño conjunto de casos de prueba (productos con resultado esperado) y un script que reporte métricas simples, como porcentaje de propuestas con citas válidas o que respetan reglas de las guías.

- Docker Compose que levante API, worker, Redis, PostgreSQL con pgvector y la UI con un solo comando, además de un colector o exportador OpenTelemetry local.

## Nivel de calidad

- Pruebas automatizadas: unitarias para chunking, validación Pydantic y lógica de reintentos; integración de la API y de la recuperación contra PostgreSQL real; al menos una prueba de componente en React. El LLM debe poder sustituirse por un doble determinista en CI.

- Manejo de errores explícito ante timeouts o límites de tasa del proveedor LLM, documentos corruptos, salidas inválidas del modelo y caída de Redis o de la base de datos. Los errores se devuelven con respuestas HTTP coherentes y se reflejan en el estado del lote.

- Observabilidad con OpenTelemetry: trazas que atraviesen API, tarea Celery, recuperación y llamada al LLM, con atributos útiles (latencia, tokens, número de fragmentos recuperados) y logs estructurados correlacionados con el trace id.

- Seguridad: sin secretos en el repositorio, validación de tamaño y tipo de los archivos subidos, y protección contra prompt injection incrustada en los documentos (explica qué mitigas y qué no).

- Reproducibilidad: dependencias fijadas, migraciones versionadas, datos de ejemplo sintéticos incluidos y un CI sencillo (GitHub Actions) que ejecute linters y pruebas.

## Decide y justifica

- ¿Cómo tratas una propuesta cuando la recuperación no encuentra evidencia suficiente en las guías: la generas con una advertencia, la bloqueas o la envías a revisión manual? Justifica el umbral.

- ¿Qué haces cuando se sube una nueva versión de una guía: reindexas todo, versionas los fragmentos o marcas como obsoletas las propuestas ya aprobadas? Explica el coste y el riesgo de cada opción.

- ¿Dónde fijas la frontera entre la lógica síncrona de la API y el trabajo asíncrono en Celery, y cómo garantizas idempotencia si un lote se lanza dos veces?

- ¿Qué estrategia de chunking, embeddings y proveedor LLM eliges, y cómo sabes con tu evaluación mínima que esa elección es mejor que una alternativa sencilla?

## Entregables

- Un único repositorio público de GitHub con todo el proyecto como monorepo (backend FastAPI, workers Celery, frontend React e infraestructura con Docker Compose). Lo que haya en el commit más reciente en el momento de tu entrega es lo único que evaluaremos; no habrá segunda entrega.

- README con instrucciones para ejecutarlo desde cero, arquitectura resumida, qué está terminado, qué queda fuera y cómo ejecutar pruebas y evaluación.

- DECISIONS.md con tus respuestas razonadas a las preguntas abiertas, los trade-offs principales y una nota breve sobre cómo usaste IA generativa, qué revisaste o corregiste a mano y qué no verificaste.

- Pruebas automatizadas (backend y frontend) y el script de evaluación con su conjunto de casos, ejecutables con comandos documentados.

- Datos de ejemplo sintéticos (guías y productos) y un archivo de configuración de ejemplo sin secretos para reproducir el flujo completo.

## Entrega

Pega el link de tu repositorio público de GitHub en:

https://app.topdevcrew.com/test/9cf54515415497640be6eaf4edb2711f
