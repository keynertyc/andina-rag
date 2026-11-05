# Plan de mejoras de arquitectura y experiencia de revisión

Estado: **implementación completada y verificación local realizada**. Iteración del 5 de
noviembre de 2026. Se mantienen el diagnóstico y el plan originales como registro; las
rutas de los hallazgos describen el código anterior a la reorganización. La publicación
del candidato y su CI remoto quedan fuera de la verificación local.

## Registro de ejecución

| Paso | Resultado comprobado |
|---|---|
| 1 | Política en `reviews.py`, `allowed_actions`, no-op y reapertura explícita; pruebas de API y formulario |
| 2 | Fallos y recuperación bajo advisory lock; regresiones de intercalación, duplicados y agotamiento |
| 3 | Listas de lotes/propuestas con dos consultas por página; `X-Has-More` y errores completos |
| 4 | TanStack Query, borradores separados, conflictos sin pérdida de campos, navegación y URL |
| 5 | Tres vistas con Material UI, CSS reducido, carga dinámica y CSP con nonce verificada en Nginx |
| 6 | 48 pruebas backend, 15 frontend, dos recorridos Chromium, evaluación E5 y trazas locales; CI actualizado |

Comandos, resultados y límites: [evidencia de verificación](../reports/verification.md).
El catálogo de documentos se carga por páginas para el selector y la vigilancia de versiones;
la biblioteca y cada historial mantienen paginaciones independientes visibles en la URL.

La referencia de alcance sigue siendo la [prueba técnica](andinarag-prueba-tecnica.md).
El usuario confirmó que las propuestas aprobadas y rechazadas deben ser de solo lectura
hasta pulsar **Reabrir revisión**.

## 1. Diagnóstico y prioridades

La base es adecuada para la prueba: monorepo, monolito con workers, PostgreSQL como fuente
del estado, modelos Pydantic, migraciones, adaptadores de generación, citas históricas y
revisiones optimistas. Conviene conservar estos mecanismos y sus pruebas.

Los problemas principales están en las reglas de revisión, la coordinación de las vistas
y algunas operaciones de persistencia. Cambiar de biblioteca visual por sí solo no los resuelve.

| Prioridad | Hallazgo y evidencia | Consecuencia | Corrección mínima |
|---|---|---|---|
| P1 | `frontend/src/components/ProposalDetail.tsx`: los botones solo comprueban `busy` y, para aprobar, `is_stale`; los campos siempre son editables | Se puede aprobar repetidamente o cambiar una decisión sin reabrir | Acciones permitidas por estado, aplicadas también en el servidor |
| P1 | `backend/app/api.py`, `update_proposal`: la presencia de campos cuenta como cambio; todo PATCH incrementa `revision` | Guardar contenido idéntico puede devolver una aprobada/rechazada a revisión | Comparar contenido normalizado; no-op sin escritura ni incremento; reapertura explícita |
| P1 | `backend/app/processing.py`, `record_task_error`, llamado desde `tasks.py` después de liberar `entity_session` | Existe una intercalación en la que un error tardío puede sobrescribir un éxito concurrente | Persistir el resultado del intento mientras se conserva el mismo bloqueo |
| P1 | `Review.tsx` y `ProposalDetail.tsx`: lista y detalle se consultan por separado; el formulario se remonta por revisión | Selección incoherente con filtros, detalle desactualizado y riesgo de perder borradores al navegar o recargar | Separar borrador y datos del servidor; selección estable, invalidación y protección de cambios |
| P2 | `frontend/src/api.ts`: descarta filas/campos/estado HTTP/trace ID y acepta JSON inválido como `{}` | Mensajes sin detalle accionable y posibles errores de renderizado | Contrato de errores tipado y fallo explícito de protocolo |
| P2 | `Batches.tsx`: solicita hasta 1.000 ítems y permite reenviar aunque no haya trabajo recuperable; `useResource.ts` consulta periódicamente sin condición terminal | Renderizado innecesario, consultas continuas y tareas duplicadas evitables | Paginación, consultas condicionadas y acciones de recuperación diferenciadas |
| P2 | `services.py`, `batch_view` y `proposal_view`: consultas adicionales dentro de cada fila de las listas | El número de consultas crece con la página y se multiplica con el polling | Cargar ítems/versiones y agregar contadores para toda la página |
| P2 | `api.py` mezcla HTTP, revisión, archivos y publicación; los componentes mezclan consulta, formulario y presentación | Cambios difíciles de aislar y validar | Extraer responsabilidades al modificar cada funcionalidad |

Los fallos de formularios y PATCH se comprueban directamente en el código. La carrera del
worker se identifica por una intercalación posible; falta reproducirla con una prueba
determinista. Esta revisión no ejecutó operaciones de escritura ni llamadas a Gemini.

## 2. Decisiones de producto y contrato

### Estados y acciones

`is_stale` seguirá siendo independiente del estado de revisión. Una guía nueva no reescribe
una decisión histórica ni elimina sus citas.

| Estado | Vigencia | Edición | Acciones disponibles |
|---|---|---|---|
| Pendiente | Vigente | Sí | Guardar si hay cambios válidos, aprobar, rechazar |
| Aprobada | Vigente | No | Reabrir revisión |
| Rechazada | Vigente | No | Reabrir revisión |
| Pendiente | Obsoleta | No | Regenerar o rechazar el contenido persistido |
| Aprobada/rechazada | Obsoleta | No | Regenerar; conservar la decisión histórica |

Reglas concretas:

1. El servidor será la autoridad. Una función pequeña en `reviews.py` expresará las
   transiciones; no hace falta una biblioteca de máquinas de estados.
2. El DTO incluirá `allowed_actions`, calculado con las mismas reglas. El frontend añadirá
   las condiciones locales de formulario válido, cambios pendientes y operación en curso.
3. El PATCH existente seguirá exigiendo `revision`. Reabrir enviará exclusivamente
   `status: pending_review` y la revisión actual, sin editar contenido en esa petición.
4. Cambiar contenido de una aprobada/rechazada sin reabrir devolverá `409` con código
   específico. También se rechazará el cambio directo entre decisiones terminales.
5. Un PATCH idéntico, con revisión vigente y sin transición, devolverá el recurso sin
   modificar `revision`. Una revisión antigua seguirá devolviendo `409`, incluso en un no-op.
6. Aprobar podrá guardar el borrador válido y aprobarlo en una misma transacción. La
   validación será común a Guardar y Aprobar; no dependerá de que el botón dispare submit.
7. Rechazar será una decisión sobre el contenido persistido. Si hay cambios sin guardar,
   se pedirá confirmar **Descartar cambios y rechazar** o seguir editando; no se guardarán
   silenciosamente. Descartar cambios también tendrá una acción explícita en el editor.
8. Un conflicto conservará el borrador y mostrará la versión actual para recargar o
   comparar. No se reintentará una decisión automáticamente ni se sobrescribirá otra revisión.
9. Una propuesta obsoleta no se aprobará aunque la pantalla todavía la muestre vigente.
   Se conservará el bloqueo que serializa aprobación y activación de versiones.

### Biblioteca visual: Material UI

Se elige **Material UI** para formularios, tablas, filtros, alertas y diálogos de esta
aplicación de gestión. Un tema compartido permitirá conservar identidad y consistencia
con menos controles propios. CSS sigue siendo válido para distribución y ajustes puntuales.

La alternativa shadcn/ui ofrece más control sobre componentes locales, pero su instalación
en este Vite incorporaría Tailwind y más código de componentes dentro del repositorio.
Para este alcance, se prioriza la uniformidad de Material UI sobre esa personalización.
Referencia: [instalación oficial de shadcn en Vite](https://ui.shadcn.com/docs/installation/vite).

La migración incluirá la CSP de producción desde el principio: Emotion inserta estilos y
la configuración actual de Nginx solo admite `style-src 'self'`. Se entregará un nonce por
respuesta HTML, compartido entre cabecera, HTML y caché de Emotion; el HTML no podrá reutilizar
una cabecera con un nonce distinto. Los atributos de estilo dinámicos tendrán la directiva
específica que requiere MUI, manteniendo `script-src 'self'`. No se quitará la CSP para
resolver errores visuales. Se comprobarán también diálogos, menús y recarga de página con
la imagen real de Nginx. Referencia: [CSP oficial de Material UI](https://mui.com/material-ui/guides/content-security-policy/).

Se usarán componentes de Material UI Core; para tablas basta `Table` con paginación del
servidor. No se necesita Data Grid Pro, otro kit visual, un motor experimental de estilos
ni una plataforma propia de componentes.

### Datos del servidor y navegación

Se incorporará **TanStack Query** para sustituir el polling y la caché manual de
`useResource`. Aquí resuelve una necesidad existente: coordinar listas, detalle, progreso
y nuevas versiones. Los borradores seguirán en estado local del editor, separados de la
caché. Sus actualizaciones no podrán sustituir campos que el analista está editando.

Habrá claves de consulta por recurso/filtros/página, cancelación de GET con AbortSignal,
actualización del detalle desde la respuesta de la mutación e invalidación de listas.
Se configurarán explícitamente intervalos, caducidad y reintentos, en vez de depender de
los valores predeterminados. Solo GET transitorios podrán reintentarse de forma acotada;
las mutaciones no se reintentarán automáticamente. Referencia:
[valores predeterminados de TanStack Query](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults).

Las consultas periódicas se limitarán al trabajo activo y a vistas visibles. Al terminar
un lote se hará una actualización final. Las guías se actualizarán mientras indexan y
al recuperar el foco; si cambian las versiones activas se invalidarán las propuestas.
La comprobación transaccional del servidor seguirá protegiendo la aprobación.

Vista, lote, filtro, página y propuesta se reflejarán en parámetros de URL para conservar
el contexto al recargar y compartir un enlace. Por ahora basta una utilidad pequeña con
`URLSearchParams` y `replaceState`; no se añadirá un router para tres pestañas.
Los cambios de selección, filtros, página o pestaña pasarán por una comprobación de borrador.
Se advertirá al cerrar o recargar la página solo cuando haya cambios sin guardar.

Después de aprobar/rechazar se conservará el detalle de solo lectura para confirmar la
decisión. Si desaparece de la lista filtrada, se explicará que ya no pertenece al filtro
actual; el sondeo de fondo no seleccionará otra propuesta por su cuenta.

## 3. Estructura objetivo y límites

La organización se cambiará por funcionalidad, sin una reescritura completa:

```text
backend/app/
  api.py                  # Creación de app, middleware, errores y salud
  routers/
    documents.py          # Contratos HTTP de guías/versiones
    batches.py            # Contratos HTTP de lotes/recuperación
    proposals.py          # Contratos HTTP de revisión/regeneración
  reviews.py              # Transiciones y revisión optimista
  documents.py            # Creación de versiones y almacenamiento de fuentes
  dispatch.py             # Publicación y errores del broker
  queries.py              # Lecturas por página y agregaciones
  services.py             # Creación idempotente de lotes existente
  processing.py           # Trabajo y persistencia bajo bloqueo
  tasks.py                # Celery, clasificación y planificación de reintentos
  ...                     # Mantener modelos, esquemas y módulos RAG existentes

frontend/src/
  app/                    # Composición, proveedores, tema y navegación
  features/
    review/               # Lista, detalle, editor, consultas y pruebas
    batches/              # Importación, progreso, recuperación y pruebas
    guides/               # Carga, versiones, consultas y pruebas
  shared/
    api/                  # Cliente HTTP, errores, tipos y consultas comunes
    ui/                   # Estado, vacío y confirmación realmente compartidos
```

Los componentes de Material UI se usarán directamente; no habrá un wrapper por cada
control. Se extraerán componentes cuando tengan una responsabilidad concreta o reutilización
real, no por una cantidad arbitraria de líneas.

Patrones que sí aportan: servicios de aplicación para operaciones transaccionales,
adaptadores existentes para proveedor/modelo y composición de componentes por funcionalidad.
SQLAlchemy seguirá gestionando sesiones y transacciones. No se añaden repositorios genéricos,
Unit of Work propio, buses de eventos, CQRS, microservicios, Redux ni un framework de formularios.

## 4. Ejecución por etapas

Cada etapa debe quedar verificable antes de continuar; los arreglos de revisión no esperarán
a que termine la migración visual. Las extracciones de archivos acompañarán a los cambios
de su funcionalidad, conservando endpoints y entrada de arranque.

| Etapa | Trabajo | Criterio de salida |
|---|---|---|
| 1 · Revisión correcta | Función de transiciones, `allowed_actions`, no-op, reapertura, botones/campos según estado y validación común | Pruebas API y React de la matriz; ninguna decisión terminal cambia sin reabrir |
| 2 · Persistencia concurrente | Guardar errores dentro del mismo bloqueo que posee el intento; coordinar reenvío manual con ese bloqueo | Una ejecución fallida tardía no revierte éxito ni activación; duplicados no cambian resultados |
| 3 · Lecturas y contratos | Consultas por página sin N+1, orden estable por fecha e ID, metadatos de paginación, errores completos | Consultas acotadas al crecer la página; filas/campos/trace ID llegan al cliente |
| 4 · Estado del frontend | TanStack Query, borradores separados, protección al navegar, URL, estados de carga/error/vacío | Cambios conservados ante refresh de datos y `409`; selección y filtros coherentes |
| 5 · Vistas con Material UI | Tema y CSP primero; migración progresiva de revisión, lotes y guías | Recorrido funcional y accesible con la compilación servida por Nginx |
| 6 · Cierre de entrega | Regresión, evaluación, CI, documentación y matriz de requisitos | Evidencia actual del commit candidato; pasos pendientes documentados sin afirmar cumplimiento no probado |

### Concurrencia y recuperación

El manejo de errores deberá hacer rollback de la transacción fallida y persistir el estado
del intento antes de liberar el advisory lock, cuando la base siga disponible. Celery
planificará el siguiente intento después de ese resultado. `ITEM_BUSY` nunca guardará un
error sobre la entidad de otra ejecución. Si se pierde PostgreSQL, se mantendrán logs y
recuperación explícita; no se fingirá que el estado quedó persistido.

El reenvío manual de fallidos también respetará el bloqueo y releerá el estado antes de
reiniciar intentos. Debe distinguirse **Reintentar fallidos** de **Recuperar pendientes**
tras un error de despacho o interrupción. Se conservará una opción explícita de recuperación
para trabajo abandonado, sin habilitar reenvíos normales mientras todo progresa correctamente.
Podrá reutilizarse el endpoint de retry con un modo validado, sin introducir otro servicio.
Éxitos y bloqueados por falta de evidencia no se reiniciarán; estos últimos requieren un
lote nuevo con evidencia adecuada. El límite y backoff existentes seguirán siendo acotados.

Las listas mantendrán su forma de array; `X-Has-More`, calculado solicitando una fila adicional,
permitirá avanzar sin adivinar si existen más resultados. Un helper del cliente leerá esa
cabecera. Se paginarán propuestas, ítems, lotes y versiones; el tamaño inicial será 50.
No hace falta contar todo el catálogo ni virtualizar una tabla de 50 filas.

### Detalles de las vistas

- **Revisión:** original/propuesta/citas visibles; estado y vigencia separados; motivo junto
  a acciones no disponibles; operación en curso con texto específico; feedback sin duplicados.
- **Lotes:** carga y retry con estados independientes; formulario bloqueado durante envío;
  errores de CSV/JSON con fila y campo; resumen que distinga propuestas, sin evidencia y fallidos;
  recuperación del ID persistido aunque falle Redis; acciones según trabajo recuperable.
- **Guías:** diferenciar nueva guía y nueva versión; agrupar historial por documento y señalar
  versión activa; mostrar errores de indexación; paginar sin ocultar destinos del selector;
  bloquear cambios durante upload y evitar que un reset borre una selección posterior.
- **Comunes:** error HTTP tipado con código/estado/detalle/trace ID, timeout acotado,
  JSON inválido como error de protocolo y Error Boundary para fallos inesperados de renderizado.
  Validar tamaño/extensión antes de enviar como ayuda, manteniendo toda validación del servidor.
- **Idempotencia en la UI:** conservar la clave durante un envío ambiguo o reintento del mismo
  archivo; generar otra solo al cambiar deliberadamente la importación. Advertir antes de
  abandonar un envío aún pendiente y ofrecer abrir el recurso ya creado.

## 5. Verificación y cobertura de la prueba técnica

Las pruebas nuevas cubrirán comportamiento y fallos relevantes, no la estructura de carpetas:

1. API: matriz de estados, reapertura, no-op sin incrementar revisión, validación, conflicto
   entre dos revisiones y aprobación simultánea a activación de guía. Conservar las citas.
2. PostgreSQL real: intercalación controlada de fallo/éxito para producto y documento;
   reenvío concurrente; contador de consultas acotado en listas de distinto tamaño.
3. React: botones por estado, edición bloqueada, dirty state, rechazo con borrador,
   conflictos sin pérdida de campos, lista filtrada después de decidir y errores por fila.
4. Navegador contra Compose/Nginx: cargar guía, importar, revisar, aprobar, reabrir y rechazar;
   cambio de versión y regeneración; menús/diálogos con CSP; recarga con nonce renovado;
   navegación por teclado, foco de errores y diseño móvil/escritorio. Usar proveedor determinista.
5. Regresión existente: linters, tipos, build, integración, chunking, recuperación, backoff,
   generación inválida, transporte real del SDK con HTTP simulado, evaluación y trazas.

| Requisito original | Protección durante la mejora |
|---|---|
| FastAPI/Pydantic y contratos | Mantener rutas, revisar OpenAPI y probar nuevos códigos/cabeceras |
| Ingesta, metadatos, versiones y pgvector | Mantener esquema, activación atómica, filtros y recuperación real |
| Generación estructurada, citas y ausencia de evidencia | Mantener validación y adaptadores; no alterar umbral/modelo en este refactor |
| Celery/Redis, idempotencia y backoff | Corregir persistencia concurrente sin perder límites ni recuperación |
| Lista, detalle y revisión persistente en React | Verificar matriz de estados y recorridos completos de las tres vistas |
| Evaluación y ejemplos | Reejecutar evaluación reproducible y conservar comparación y casos negativos |
| Fallos explícitos y seguridad | Mantener límites del servidor, claves fuera del código, CSP y errores operativos |
| OpenTelemetry | Mantener continuidad API → Celery → recuperación → LLM y logs correlacionados |
| Docker, migraciones y CI | Probar imagen de producción, fijar dependencias y ejecutar checks del commit candidato |

No se requieren llamadas pagadas para verificar estas mejoras. Una comprobación real
opcional de Gemini se distinguirá de las métricas de calidad con el proveedor simulado.

## 6. Documentación y cierre

Durante la implementación se mantendrán actualizados:

| Documento | Actualización |
|---|---|
| Este plan | Marcar etapas con evidencia y pendientes reales |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Responsabilidades, estados, bloqueo y coordinación del frontend |
| [API.md](API.md) | Reapertura, no-op, acciones, errores, retry y cabeceras de paginación |
| [TESTING.md](TESTING.md) | Comandos y cobertura de las nuevas regresiones |
| [RUNBOOK.md](RUNBOOK.md) | Qué hacer con aprobadas/rechazadas, versiones, conflictos y recuperación |
| [DECISIONS.md](../DECISIONS.md) | Justificación de Material UI, TanStack Query y política de revisión |
| [PLAN.md](PLAN.md) y [README.md](../README.md) | Matriz de cumplimiento, estructura y funcionamiento final |
| [verification.md](../reports/verification.md) | Comprobaciones ejecutadas, resultado y limitaciones del commit candidato |

La entrega al portal congela el commit público: se hará después de verificar el candidato
y sus checks. Este plan no publica código ni entrega el repositorio al portal.
