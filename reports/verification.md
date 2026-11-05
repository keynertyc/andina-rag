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
