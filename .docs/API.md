# Contrato HTTP

Prefijo: `http://localhost:8000/api/v1`. OpenAPI es la referencia completa de esquemas:
http://localhost:8000/docs y `/openapi.json`. Entradas y respuestas tienen modelos Pydantic.

## Guías

`POST /documents`: multipart con `file` PDF/Markdown, `title`, `brand` y `category` opcionales.
Una marca/categoría vacía significa ámbito global. Devuelve `202` con `document_id`,
`version_id` y `status`; la extracción todavía puede fallar en el worker.

```sh
curl -F 'title=Guía Puna' -F 'brand=Puna' -F 'category=textiles' \
  -F 'file=@samples/guides/puna-textiles-v1.md' http://localhost:8000/api/v1/documents
```

`POST /documents/{document_id}/versions`: multipart con `file`. El ámbito pertenece al
documento lógico y se conserva. Mismo checksum devuelve la versión existente; si falló,
se vuelve a encolar. Nueva versión solo reemplaza la activa al terminar de indexarse.

`GET /documents?limit=100&offset=0`: lista de versiones con estado, error e `is_active`.

## Lotes

`POST /batches`: multipart con archivo `.csv` o `.json` y cabecera `Idempotency-Key` (1–128
caracteres). JSON es una lista de productos; CSV tiene los mismos campos y separa etiquetas con `|`.

```json
[{"id":"P-1","title":"BUFANDA AZUL","description":"Bufanda de lana azul.",
  "brand":"Puna","category":"textiles","tags":[]}]
```

Campos obligatorios: `id`, `title`, `brand`, `category`. Descripción vacía y etiquetas vacías
están permitidas. Se rechazan claves extra, IDs repetidos y filas inválidas; se indican hasta
50 filas afectadas, numeradas desde el primer producto, sin contar la cabecera CSV.

```sh
curl -H 'Idempotency-Key: importacion-001' -F 'file=@samples/products/productos.csv' \
  http://localhost:8000/api/v1/batches
```

La respuesta `202` incluye `id`, `status`, `total`, `finished`, `terminal`, `counts`,
`dispatch_error` y `configuration`. Consulta con `GET /batches/{id}`. No confundas `with_errors`
con finalización: revisa `terminal`. Los bloqueos esperados cuentan por separado de los fallidos.

- `GET /batches?limit=50&offset=0`: lotes recientes.
- `GET /batches/{id}/items?limit=100&offset=0`: originales, estado, intentos y error por producto.
- `POST /batches/{id}/retry`: reenvía trabajo pendiente/en curso y reinicia fallidos.
  Correctos y bloqueados no se regeneran. No incorpora versiones nuevas de las guías.

## Propuestas

`GET /proposals?status=pending_review&batch_id=UUID&limit=100&offset=0`: filtros opcionales;
estados `pending_review`, `approved`, `rejected`. Máximo 200 por página.

`GET /proposals/{id}`: original, contenido editable, generado original, revisión, estado,
vigencia y citas completas con documento/versión/página/encabezado.

`PATCH /proposals/{id}` exige la revisión leída y admite título, descripción, etiquetas y estado:

```json
{"revision":1,"title":"Puna Bufanda de lana azul","tags":["puna","textiles"],"status":"approved"}
```

Campos omitidos se conservan. Contenido editado sin estado explícito vuelve a `pending_review`.
Las citas permanecen inmutables. La UI permite guardar contenido y decisión juntos.
Se devuelve `409` si la revisión cambió o se intenta aprobar evidencia desactualizada.

`POST /proposals/{id}/regenerate` con `Idempotency-Key`: crea un lote de un producto con
las guías activas actuales y conserva la propuesta anterior.

## Errores

Formato: `{"error":{"code":"CODIGO","message":"Explicación",...}}`.

| HTTP | Situaciones |
|---|---|
| 404 | ID válido cuyo recurso no existe |
| 409 | Clave idempotente con contenido distinto, revisión antigua o aprobación desactualizada |
| 413 | Tamaño excedido |
| 415 | Tipo no permitido o firma PDF incompatible |
| 422 | Campos, filas, formato o contenido no válidos |
| 503 | PostgreSQL o Redis no disponibles |

Si Redis falla después de persistir, el error incluye `batch_id` o `document_id`/`version_id`.
Reutiliza la clave o reenvía el recurso. Los fallos del LLM ocurren de forma asíncrona: el
POST sigue siendo `202`; su resultado aparece en el ítem y en los contadores del lote.

`GET /health/live` comprueba el proceso; `GET /health/ready` comprueba PostgreSQL y Redis
y muestra proveedores configurados. No genera una llamada de pago al proveedor LLM.
