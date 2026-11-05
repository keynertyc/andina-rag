import csv
import hashlib
import json
from io import StringIO

from pydantic import ValidationError

from app.errors import AppError
from app.schemas import Product


def parse_products(filename: str, content: bytes) -> list[Product]:
    if len(content) > 5 * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", "El lote supera el límite de 5 MiB", 413)
    try:
        decoded = content.decode("utf-8-sig")
        if filename.lower().endswith(".json"):
            rows = json.loads(decoded)
        elif filename.lower().endswith(".csv"):
            rows = list(csv.DictReader(StringIO(decoded)))
            for row in rows:
                if "tags" in row:
                    row["tags"] = [
                        value.strip() for value in row["tags"].split("|") if value.strip()
                    ]
        else:
            raise AppError("UNSUPPORTED_FILE", "Sube productos como CSV o JSON", 415)
    except (UnicodeDecodeError, ValueError, csv.Error, AttributeError) as exc:
        raise AppError(
            "INVALID_PRODUCTS_FILE", "El archivo debe contener CSV o JSON UTF-8 válido"
        ) from exc
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise AppError("INVALID_BATCH_SIZE", "Un lote debe contener entre 1 y 1000 productos")
    products = []
    errors = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        try:
            product = Product.model_validate(row)
            if product.id in seen:
                errors.append({"row": index, "code": "DUPLICATE_PRODUCT_ID"})
            seen.add(product.id)
            products.append(product)
        except ValidationError as exc:
            errors.append(
                {"row": index, "fields": [".".join(str(p) for p in e["loc"]) for e in exc.errors()]}
            )
    if errors:
        raise AppError(
            "INVALID_PRODUCTS", "Corrige las filas indicadas y vuelve a importar", rows=errors[:50]
        )
    return products


def request_fingerprint(products: list[Product]) -> str:
    normalized = [
        product.model_dump() for product in sorted(products, key=lambda product: product.id)
    ]
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
