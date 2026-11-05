# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Analistas de merchandising que revisan fichas de un marketplace ficticio. El evaluador
técnico debe poder reproducir y recorrer el flujo en una máquina local.

## Product Purpose
Proponer títulos, descripciones y etiquetas fundamentados en guías versionadas,
con citas visibles y decisión humana persistente.

## Operating Context
Guías PDF/Markdown y productos CSV/JSON sintéticos; procesamiento por lotes,
Docker Compose local y trazabilidad OpenTelemetry. Interfaz en español.

## Capabilities and Constraints
Subir guías, observar lotes, comparar original y propuesta, editar, aprobar y rechazar.
Sin evidencia no se genera contenido. Las versiones anteriores se conservan.
Gemini y simulado explícito; sin autenticación ni despliegue público en esta entrega.

## Product Principles
- La evidencia está al lado del contenido que debe revisarse.
- Bloqueos y errores deben explicar cómo continuar.
- Cada acción de revisión persiste y se confirma.
- El flujo debe poder entenderse y defenderse sin infraestructura adicional.
