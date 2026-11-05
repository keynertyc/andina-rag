# Decisiones técnicas

## Evidencia insuficiente

Se bloquea el producto y se registra `INSUFFICIENT_EVIDENCE`. No se llama al LLM ni se crea
una propuesta aprobable. Evita presentar contenido sin una base documental verificable.
El analista puede cargar una guía pertinente y crear otro lote.

Se usa similitud coseno `1 - distancia`, `top_k=5` y umbral **0,80** por fragmento.
E5 concentra sus puntuaciones en un rango alto: el valor no representa una probabilidad.
Se calibró en ocho casos buscando primero evitar generaciones sin evidencia, después
recuperar la regla esperada, mantener cobertura y elegir el umbral mayor en empate.
El informe conserva la tabla de candidatos y 12 casos de verificación.

La primera calibración solo medía presencia de algún fragmento y eligió 0,85. Recuperó
insuficientemente reglas de descripción (60 %). Se amplió la cobertura de reglas del
conjunto de calibración y el criterio de selección. Se conserva ese resultado inicial en
`reports/evaluation-initial.json`. Es una evaluación exploratoria pequeña; no se presenta
como un benchmark independiente ni una garantía para catálogos reales.

Se añadieron negativos con marca/categoría coincidentes pero contenido ajeno. Revelaron
que un encabezado aislado podía parecer evidencia por repetir la marca. Se excluyen
secciones sin cuerpo y la consulta semántica usa título/descripción; marca y categoría
se aplican como filtros. Esto evita contar la mera coincidencia de ámbito como evidencia.

## Versiones de guías

Un documento lógico tiene versiones inmutables y un máximo de una activa. Se extraen e
indexan solo los fragmentos de la versión nueva; su activación y el guardado de fragmentos
son transaccionales. Un error conserva activa la anterior. Si dos versiones terminan en
orden inverso, la más antigua no sustituye a una posterior ya activa.

Cada lote conserva las versiones vigentes al crearse y cada producto guarda las usadas
como contexto. Una propuesta queda desactualizada cuando alguna de esas versiones deja
de estar activa. Conserva su estado anterior, original, contenido generado, edición y citas.
No se permite aprobarla de nuevo sin regenerar. Aprobación y activación bloquean las filas
de documento en PostgreSQL para resolver carreras.

Reindexar todo simplificaría la selección, pero repetiría embeddings sin necesidad y
dificultaría reproducir citas antiguas. Reescribir aprobaciones alteraría decisiones humanas.
Conservar versiones cuesta almacenamiento; señalar cambios exige una nueva revisión.
No se hace regeneración automática masiva porque consume recursos y podría ocultar cambios.

## Frontera síncrona y asíncrona; idempotencia

La API limita y valida archivos/productos, guarda fuentes y metadatos y publica tareas.
Celery extrae documentos, calcula embeddings, recupera evidencia y genera propuestas.
Los estados de dominio viven en PostgreSQL; no se necesita un backend de resultados Celery.

`Idempotency-Key` identifica un envío. El hash se calcula sobre productos normalizados
ordenados por ID, no sobre detalles accidentales del CSV. Misma clave y contenido devuelve
el lote original incluso si cambiaron las guías; otra carga con esa clave produce `409`.
Una clave nueva solicita otro procesamiento. La UI conserva la clave tras un fallo de red.

La combinación lote/producto y la propuesta por producto tienen restricciones únicas.
Un bloqueo asesor de sesión PostgreSQL impide procesamiento concurrente y se libera
si muere la conexión. Las transacciones se cierran durante el trabajo del modelo.
Una entrega duplicada no cambia resultados ni revisiones ya persistidos. Reconocimiento
tardío y redelivery implican que la llamada al proveedor puede repetirse después de una caída;
no se promete exactamente una llamada externa.

Tres reintentos Celery con backoff/jitter para errores transitorios, cuatro intentos persistidos
como límite de recuperación automática, y una sola corrección de salida inválida. El SDK
de Gemini no hace reintentos adicionales. Concurrencia 2, prefetch 1 y límites de tiempo 110/120 s.

Existe una ventana entre commit y publicación en Redis. Si falla, se conserva el recurso,
se devuelve `503` con su ID y se puede reenviar. Un cierre abrupto en esa ventana puede dejar
pendientes: el runbook describe su reenvío. Un outbox con publicador daría recuperación
automática, pero añade otro ciclo operativo que no exige esta prueba; se eligió recuperación
explícita y verificable. Los bloqueados por evidencia requieren nuevas guías y un nuevo lote.

## Chunking, embeddings, LLM e índice

Fragmentos por sección/página con cuerpo, máximo 400 tokens del tokenizer real y 60 de solapamiento;
cuando es posible, el corte respeta párrafos. Metadatos conservan página o encabezado.
Los prefijos de E5 se añaden en el adaptador y el texto queda bajo su límite de 512 tokens.
La revisión del modelo y las dependencias están fijadas. FastEmbed/ONNX evita instalar PyTorch.

El umbral conserva un falso negativo de calibración: MA-004 (gorro rojo). En los 20 casos
se generan 15 de 16 positivos (93,75 %) y se bloquean los cuatro negativos. Se acepta ese coste
de cobertura para no generar el producto ajeno de marca/categoría coincidentes. El informe
incluye también los casos y métricas de calibración; no se oculta el fallo en el agregado.

La búsqueda exacta de pgvector se filtra por marca, categoría, versiones del lote y modelo.
Índices B-tree para metadatos y claves externas. No se añade HNSW: son pocas guías y la búsqueda
exacta no introduce pérdida de recall por filtros aproximados. Un índice ANN se justificaría
con un corpus de guías grande y mediciones, no por los 100 mil productos del contexto.

Gemini se integra directamente mediante un adaptador y esquema Pydantic; no se necesita un
framework de agentes. Se eligió Flash-Lite por el alcance de generación estructurada y la
operación sin un modelo generativo local. El simulado es una plantilla explícita que permite
probar contratos y CI sin claves; no demuestra la calidad semántica de Gemini.

La comparación usa el mismo generador, consulta de título/descripción y filtros, con
fragmentos fijos sin solapamiento y recuperación léxica. E5 recuperó la evidencia anotada
para 10/10 positivos de verificación; la alternativa, 9/10 (falló la chalina por variación
léxica). Ambas bloquearon los dos negativos. Es una mejora en este conjunto pequeño,
no evidencia suficiente para afirmar superioridad general. Se necesitaría un corpus mayor.

## Patrones y operación

Servicios de aplicación, adaptadores sustituibles e inyección de dependencias. SQLAlchemy
provee transacciones y consultas explícitas; no se añade un repositorio genérico ni una clase
propia de Unit of Work. React usa formularios controlados y polling con cancelación.
Las revisiones llevan un contador para detectar escrituras desde pantallas desactualizadas.

Se fijó SQLAlchemy 2.0.55 porque la instrumentación OpenTelemetry instalada declara compatibilidad
anterior a 2.1. Se activó explícitamente la inyección de contexto en logs en la versión actual
del instrumentador. Jaeger all-in-one almacena trazas en memoria: un reinicio las elimina.

Seguridad y límites concretos están en `.docs/ARCHITECTURE.md`. No se expone este entorno sin
autenticación a Internet. Los valores de PostgreSQL incluidos son exclusivos de la demo local.

## Uso de IA y verificaciones

Codex generó código, pruebas, ejemplos y documentación, consultando Context7 y fuentes
oficiales. Durante esta sesión se inspeccionaron contratos, restricciones, transacciones,
idempotencia, validación, efectos de versiones, configuración de reintentos y propagación.
Se corrigieron la calibración incompleta, la compatibilidad SQLAlchemy/OTel, la correlación
de logs y estados de UI. Las verificaciones ejecutadas están en `reports/verification.md`.

No se atribuye una revisión humana al código generado. No se verificaron llamadas reales
a Gemini sin credenciales, ni rendimiento a escala, OCR o escenarios multiusuario. GitHub
Actions debe confirmarse en el remoto después de publicar el commit. La persona que entregue
debe revisar y comprender las decisiones que defenderá en entrevista.

## Referencias consultadas

- [FastAPI: archivos y formularios](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/)
- [Celery: tareas y reconocimiento tardío](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [pgvector: índices y filtrado](https://github.com/pgvector/pgvector#filtering)
- [E5 multilingüe](https://huggingface.co/intfloat/multilingual-e5-small)
- [FastEmbed: modelos personalizados](https://github.com/qdrant/fastembed)
- [Google Gen AI SDK](https://github.com/googleapis/python-genai)
- [OpenTelemetry Python Contrib](https://github.com/open-telemetry/opentelemetry-python-contrib)
- [React: efectos y limpieza](https://react.dev/learn/synchronizing-with-effects)
