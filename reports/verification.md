# Evidencia de verificación local

Ejecutada durante la implementación, 4 de noviembre de 2026 (America/Lima).

| Comprobación | Resultado |
|---|---|
| PostgreSQL 17 + pgvector 0.8.2 y Redis reales | Arranque y migraciones correctos |
| Backend: unitarias + integración PostgreSQL | 34 pruebas; ver comando reproducible en TESTING |
| Cobertura medida antes de la última prueba de regresión | 85 % de `backend/app` |
| Ruff + formato + mypy | Correctos |
| React: Vitest / Testing Library | Tres pruebas correctas |
| ESLint + TypeScript + build Vite | Correctos, también durante build Docker con Node 24 |
| npm audit | Cero vulnerabilidades reportadas en la verificación |
| Compose | Seis servicios levantados, API/worker saludables |
| Demo final con E5 real + simulado | 20 productos, 15 propuestas, cuatro negativos bloqueados y un falso negativo conservador |
| Persistencia de aprobación | Comprobada por lectura posterior |
| Traza distribuida real | API y worker, SQL, recuperación y LLM en un mismo trace id |
| Logs JSON | `trace_id` y `span_id` no nulos durante procesamiento |
| Caída real de Redis | `503`, lote persistido, reenvío del mismo lote y una propuesta |
| Redelivery real | Cuatro mensajes duplicados no cambian una aprobación |
| Caída real de PostgreSQL | `503`; revisión conservada al recuperarlo |
| Inspección visual | Chrome: original, editor y citas visibles en escritorio |

La prueba final de trazas produjo 336 spans en `561e6e20019b04453fe667929d6fd58a`, con servicios
`andinarag-api` y `andinarag-worker`, y operaciones SQL, `rag.retrieve`, `llm.generate`
y `run/andina.enrich`. Las trazas son efímeras; la demo permite recrear otra.

Los informes JSON adjuntos conservan evaluación actual, resultado inicial y resiliencia.
La evaluación actual usa embeddings reales y un LLM simulado; no se atribuyen estos resultados
a Gemini. El conjunto exploratorio fue ampliado al detectar fallos y no constituye un test ciego.

El workflow de GitHub Actions está incluido; el resultado remoto se consulta en Actions del
repositorio. La carga de 100 mil productos y una revisión visual móvil no se han verificado.
No se ha enviado el enlace al portal de entrega.

## Actualización del 5 de noviembre: Gemini real

- La clave fue aceptada al consultar modelos; el modelo configurado estaba disponible.
- Se reprodujo HTTP 400 `INVALID_ARGUMENT` por el campo `additional_properties` de
  `generation_config.response_schema`.
- Se cambió al esquema JSON nativo con `response_json_schema` y se conservó validación local estricta.
- La prueba del transporte real del SDK falló antes del cambio y pasó después. Backend: **35 pruebas**.
- Se reconstruyeron y actualizaron API/worker sin cambiar la clave ni los productos originales.
- El mismo lote pasó de 15 fallidos a **15 propuestas y cero fallos**; cinco productos
  permanecieron bloqueados por evidencia. Se comprobaron las referencias de citas de las 15 propuestas.
- La evidencia funcional está en [gemini-verification.json](gemini-verification.json).
  No convierte las métricas del informe con simulado en un benchmark de calidad de Gemini.

## Iteración de revisión y mantenibilidad (2026-11-05)

Implementación de `.docs/IMPROVEMENT_PLAN.md`; solo datos sintéticos en el proyecto separado
`andinarag-check`, con clave Gemini vacía y adaptadores deterministas. Las credenciales y
volúmenes del entorno de trabajo no se usaron para generar resultados de prueba.

| Comprobación | Resultado |
|---|---|
| Backend con PostgreSQL real, base `_test` | **48 pruebas correctas** |
| Ruff, formato y mypy | Correctos sobre backend/scripts y 26 módulos de aplicación |
| Frontend: React/cliente HTTP/navegación | **15 pruebas correctas** |
| ESLint, TypeScript y build | Correctos; vistas bajo demanda, sin aviso de chunk mayor de 500 kB |
| Navegador Chromium contra Nginx y Celery | **Dos pruebas correctas**; ingesta, importación, conflicto, aprobación, reapertura, rechazo, versión y regeneración |
| CSP de producción | Nonce distinto al recargar, coincidente con cabecera; menús/diálogos sin violaciones detectadas; scripts limitados al origen |
| Inspección visual | Escritorio y 360 px sin desbordamiento horizontal; lista acotada, acceso al detalle y etiquetas visibles en Todos/Nueva guía |
| Concurrencia | Decisiones simultáneas, activación frente a aprobación, error bajo lock para documento/ítem y recuperación que omite trabajo ocupado |
| Listas SQL | Dos SELECT por página con uno y cuatro resultados; última página exacta y orden estable verificados |
| Evaluación E5 real + LLM simulado | 20 casos: 15 generados; cobertura positiva 93,75 %, citas válidas 100 %, cuatro negativos bloqueados |
| Split de verificación de calidad | 12 casos, diez positivos generados, citas/reglas/recuperación y bloqueo comprobados |
| Smoke con worker y embeddings hash | 14 propuestas, seis bloqueos; aprobación persistida y citas verificadas. Comprueba integración, no calidad E5/Gemini |
| Traza distribuida | API y worker, recuperación y LLM: 405 spans en `2d655a86a7f3a6d7b9c7e9a7d4169832` |
| CI | Workflow ampliado con navegador y artefactos de fallo; resultado remoto del candidato pendiente de publicación |

Las capturas y trazas Playwright están en `frontend/test-results/` (ignoradas por Git).
La evaluación se ejecutó con la versión actual del código y caché del modelo, escribiendo
`/tmp/andinarag-improvement-evaluation.json`; no modificó el informe histórico de evaluación.
Las trazas Jaeger son efímeras y se pueden reproducir mediante `scripts.demo`.

No hubo llamadas nuevas a Gemini para probar este refactor. Se conserva el falso negativo
conservador de E5 y no se atribuyen las métricas del simulado a Gemini. El aviso de deprecación
Starlette/httpx del entorno de pruebas sigue presente; la suite termina correctamente.
No se midió rendimiento con 100 mil productos, ni se repitieron en esta iteración los cortes
reales de Redis/PostgreSQL registrados antes. La entrega al portal no se ha realizado.

Se reconstruyeron y actualizaron API, worker y UI del entorno de trabajo. La lectura posterior
confirmó **63 propuestas y cinco lotes conservados**, comparando IDs, contenido, estado y
revisión con un snapshot previo; no había lotes activos al iniciar la actualización.
API y worker quedaron saludables, la UI responde en `http://localhost:8080` con nonce válido
y el proveedor sigue configurado como Gemini. Esta comprobación solo leyó datos.
El entorno de prueba separado se detuvo al terminar, conservando sus volúmenes para reproducirlo.

## Encabezado móvil y menú de navegación (2026-11-05)

- Header sticky por debajo de 600 px, con icono de menú de 44 px, marca y proveedor compacto.
- Menú Material UI con sección actual, Escape, retorno de foco y cierre antes de confirmar
  un borrador. Al pasar a escritorio se desmonta para no dejar un overlay invisible.
- Navegar a otra sección empieza arriba; cancelar conserva borrador y vista. Las anclas
  respetan el espacio del header. Se corrigió el mínimo intrínseco de la rejilla de Guías
  que desbordaba la página en 320 px.
- ESLint, TypeScript/build y **15 pruebas frontend** correctos. **Tres recorridos Chromium**
  correctos contra Nginx, incluyendo scroll, menú, cambio de ancho y cancelación con borrador.
- Captura: `frontend/test-results/mobile-navigation.png`, fuera de Git. Comprobación en
  viewports emulados de 320/360 px y escritorio; no equivale a probar teléfonos físicos.
- Detector mecánico de Impeccable sin hallazgos en los archivos revisados.
- UI local reconstruida y actualizada en `http://localhost:8080`; no se modificó el backend
  para este ajuste ni se hicieron llamadas a Gemini durante las pruebas.

A solicitud del usuario se actualizó la instalación personal de Impeccable a 4.8.0;
las nuevas instrucciones de la skill se aplicarán en la siguiente sesión.
