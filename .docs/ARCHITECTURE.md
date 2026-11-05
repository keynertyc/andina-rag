# Arquitectura y reglas operativas

## Flujo

1. La API limita el cuerpo, valida archivo/metadatos y persiste una versión o lote.
2. Publica IDs en Redis. Los bytes de documentos están en un volumen compartido.
3. Celery adquiere un advisory lock PostgreSQL por entidad; marca el trabajo en curso.
4. La ingesta extrae, fragmenta e indexa; activa una versión solo al completar la transacción.
5. El enriquecimiento recupera evidencia de las versiones del lote, valida la generación
   y persiste propuesta y referencias. El trabajo externo ocurre sin una transacción abierta.
6. React consulta progreso, presenta las citas originales y guarda decisiones del analista.

## Datos

| Tabla | Responsabilidad y restricciones |
|---|---|
| `documents` | Identidad lógica y ámbito de marca/categoría; índices B-tree |
| `document_versions` | Número, checksum, fuente, configuración y estado; UNIQUE por documento/número y documento/checksum; índice único parcial de versión activa |
| `chunks` | Texto, posición, página/encabezado y `vector(384)`; FK de versión indexada; UNIQUE versión/posición |
| `batches` | Clave idempotente única, hash, versiones y configuración congelada, error de publicación |
| `batch_items` | Original inmutable, estado, intentos y versiones de contexto; UNIQUE lote/producto |
| `proposals` | Generado original, contenido editable, estado y revisión; UNIQUE por ítem |
| `proposal_citations` | Referencias con FK a propuesta y fragmento; no se borran versiones citadas |

Las migraciones son explícitas y versionadas en Alembic. No se usa `create_all` como sustituto.

## Recuperación

El ámbito coincide si marca y categoría coinciden tras recortar/casefold; un valor nulo en
una guía significa que aplica globalmente en esa dimensión. No se eliminan tildes ni se
equiparan categorías distintas de forma implícita. El lote almacena versiones y modelo;
la consulta usa ese snapshot aunque se active otra versión durante su procesamiento.

La búsqueda ordena por `embedding <=> vector_consulta`, filtra similitud `1 - distancia ≥ 0,80`
y devuelve hasta cinco fragmentos. Es exacta y utiliza los índices de metadatos para reducir
candidatos; no existe un índice ANN que pueda perder vecinos después de filtrar.
La consulta semántica utiliza título y descripción; el ámbito ya está restringido por SQL.
Los encabezados sin cuerpo no se indexan porque no proporcionan reglas verificables.
La dimensión siempre corresponde al modelo fijado; un cambio exige reindexar versiones.
Cambiar el código de chunking no reescribe versiones históricas: se requiere una nueva ingesta.

El tamaño de lote (1.000) no representa la capacidad total del catálogo. La búsqueda ocurre
en las guías y no se afirma rendimiento sobre 100 mil productos sin medirlo.

## Estados y concurrencia

- Documento: `pending → indexing → ready`; `error` si falla. Reenviar el mismo contenido
  a su documento lógico recupera una versión fallida sin crear otra.
- Producto: `pending → running → succeeded | blocked | failed`. Un fallo transitorio vuelve
  a `pending` durante el backoff. Un producto bloqueado requiere un lote nuevo.
- Lote: `pending`, `running`, `completed`, `with_errors`. `terminal` indica que todos los ítems
  terminaron. Un error de despacho también se muestra como `with_errors`, aunque no sea terminal.
- Propuesta: `pending_review`, `approved`, `rejected`; `is_stale` es independiente.

Las revisiones optimistas rechazan `revision` antigua con `409`. Una aprobada/rechazada
queda de solo lectura hasta una reapertura explícita sin contenido. Solo se editan pendientes
vigentes; guardar sin cambios no modifica estado ni revisión. `reviews.py` aplica la política
y genera `allowed_actions` para el cliente. Las citas no son editables desde PATCH. La regeneración crea un lote
nuevo y no sustituye el historial. La aprobación comprueba vigencia bajo bloqueo de documentos.

El lock asesor pertenece a una conexión dedicada, se conserva entre transacciones cortas
y se libera en `finally` o al morir la conexión. El error del intento se persiste después
del rollback y antes de liberar ese mismo lock; Celery planifica los reintentos después.
El reenvío manual también relee y modifica ítems bajo ese lock. Una tarea duplicada ocupada reintenta sin
cambiar el estado de su propietaria; si ya hay resultado, termina sin escribir.

## Errores y recuperación

PostgreSQL caído implica `503` al consultar/persistir. Redis caído permite leer datos pero no
despachar; el recurso persistido expone el error y su ID. El endpoint de reintento distingue `mode=failed` y `mode=unfinished`: el primero reinicia
fallidos y el segundo recupera pendientes/interrumpidos que no posee un worker. No se alteran
correctos ni bloqueados. Reintentar fallidos no oculta un error de despacho de otros pendientes.

El worker clasifica timeout/429/5xx e infraestructura como transitorios. Agotar intentos o
mantener salida inválida produce error de ítem; la ausencia de evidencia produce bloqueo.
Si PostgreSQL está caído, no se puede persistir un error en él: se registra en logs y, tras
recuperarlo, se reconcilian los pendientes mediante el reenvío documentado.

No existe reconciliador automático ni garantía exactamente-una-vez para llamadas externas.
Redis usa AOF; no se usa como fuente del estado de negocio.

## Seguridad

- Petición completa limitada a 11 MiB antes de parsear multipart, incluso sin Content-Length.
  Archivo de guía: 10 MiB; productos: 5 MiB. PDF: 100 páginas; texto extraído: un millón de caracteres.
- Se inspeccionan firma PDF, extensión y UTF-8; no se confía en MIME declarado. PDFs corruptos,
  cifrados o sin texto tienen errores específicos. Fuentes guardadas con UUID, no con rutas del cliente.
- Contexto de documentos/productos serializado como datos no confiables, separado de instrucciones
  de sistema. LLM sin herramientas, navegación ni ejecución. No se insertan secretos en prompts.
- Pydantic limita la forma; las citas deben existir en el contexto recuperado. React escapa texto;
  no hay `dangerouslySetInnerHTML`. Nginx aplica CSP y `nosniff`.
- Prompt injection puede influir semánticamente en el modelo: la separación no demuestra inmunidad.
  No se promete verificación de cada afirmación ni detección completa de instrucciones maliciosas.
- `.env` ignorado; API/UI/Jaeger en loopback y DB/Redis internos. No hay autenticación: es una demo local.

## Observabilidad

Propagación W3C mediante instrumentación Celery de productor y consumidor. El worker configura
exportadores después del fork y descarta conexiones heredadas. Se añaden spans de extracción,
chunking, embeddings, recuperación y LLM. Duración de spans aporta latencia; atributos incluyen
producto/lote, intentos, número de fragmentos, modelo y tokens cuando el proveedor los devuelve.

Logs JSON con `trace_id` y `span_id` inyectados explícitamente. La API devuelve `X-Trace-ID`.
No se registran prompts, claves, texto completo de guías ni salida inválida del modelo.
Los eventos de infraestructura fuera de una traza tienen ID cero. Jaeger recibe OTLP/HTTP
en la red interna y mantiene almacenamiento efímero para esta demostración.

## Organización de código y frontend

`api.py` compone FastAPI, middleware, errores y salud. `routers/` adapta HTTP; `reviews.py`
centraliza decisiones; `documents.py` crea versiones; `dispatch.py` publica trabajo y maneja
recuperación; `queries.py` carga vistas por página sin N+1; `services.py` crea lotes idempotentes.
No se añade una abstracción de repositorios ni transacciones propia.

React se divide en `app/`, `features/{review,batches,guides}` y `shared/{api,ui}`.
Material UI Core aporta controles con un tema común; el CSS restante cubre acceso rápido,
foco, saltos de línea y movimiento reducido. Las vistas se cargan por importación dinámica.
TanStack Query administra datos del servidor; los borradores permanecen fuera de su caché.

Las listas usan páginas de 50 y `X-Has-More`. Lotes y guías solo se consultan periódicamente
mientras hay trabajo activo y con la página visible. Se refrescan al recuperar foco; el detalle
usa respuestas de mutación y las invalidaciones de listas/guías. Un catálogo paginado de
últimas versiones permite seleccionar documentos aunque no estén en la página visible y
detectar la finalización de su indexación. El ítem recibe un refresco final al terminar el lote.

La URL conserva vista, lote, estado, propuesta, documento y paginaciones. Se usa `replaceState`,
sin crear un historial por cada filtro. Cambiar de contexto con un borrador requiere confirmar;
un `409` conserva campos y permite comparar la versión actual. No hay reintentos automáticos
para mutaciones. Las importaciones ambiguas conservan una clave por hash de archivo en
sessionStorage y memoria; al finalizar correctamente se elimina ese intento.

Nginx inyecta `$request_id` como nonce por respuesta HTML y en `style-src-elem`; Emotion
recibe el mismo nonce. HTML no cacheable, ETag y respuestas condicionales desactivados evitan
mezclar HTML y cabeceras de distintas solicitudes. `style-src-attr 'unsafe-inline'` permite
posicionamiento dinámico de MUI; `script-src 'self'` sigue sin permitir scripts inline.

`AppHeader.tsx` reúne marca, estado y navegación. Por debajo de 600 px queda sticky y muestra
un menú hamburguesa de Material UI; por encima se conserva la navegación horizontal.
El menú se desmonta al cambiar a escritorio para evitar overlays invisibles. La navegación
se realiza después de cerrar el menú y restaurar foco, antes de abrir una posible confirmación
de borrador. Cambiar de sección confirmado reinicia el scroll; cancelar conserva el editor.
