"""Seed the real asynchronous API and verify review persistence. Safe to repeat."""

import argparse
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def wait_for(predicate, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(1)
    raise RuntimeError("Tiempo agotado esperando al worker; consulta docker compose logs worker")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000/api/v1")
    parser.add_argument("--key", default="andina-demo-v2")
    parser.add_argument("--verify-trace", action="store_true")
    parser.add_argument("--jaeger-url", default="http://localhost:16686")
    parser.add_argument(
        "--approve", action="store_true", help="También comprobar aprobación persistida"
    )
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=30) as client:
        client.get("/health/ready").raise_for_status()
        existing = client.get("/documents").json()
        specs = [
            ("Puna · textiles", "Puna", "textiles", "puna-textiles-v1.md"),
            ("Valle · café", "Valle", "cafe", "valle-cafe-v1.md"),
            ("Kintu · cuidado", "Kintu", "cuidado", "kintu-cuidado.pdf"),
        ]
        for title, brand, category, filename in specs:
            if any(guide["title"] == title and guide["is_active"] for guide in existing):
                continue
            with (ROOT / "samples/guides" / filename).open("rb") as file:
                response = client.post(
                    "/documents",
                    files={"file": (filename, file)},
                    data={"title": title, "brand": brand, "category": category},
                )
            response.raise_for_status()
        wait_for(
            lambda: (
                len(
                    [
                        doc
                        for doc in client.get("/documents").json()
                        if doc["is_active"] and doc["status"] == "ready"
                    ]
                )
                >= 3
            )
        )
        with (ROOT / "samples/products/productos.csv").open("rb") as file:
            response = client.post(
                "/batches",
                files={"file": ("productos.csv", file)},
                headers={"Idempotency-Key": args.key},
            )
        response.raise_for_status()
        batch_id = response.json()["id"]
        trace_id = response.headers.get("X-Trace-ID")
        batch = wait_for(
            lambda: (
                value if (value := client.get(f"/batches/{batch_id}").json())["terminal"] else None
            )
        )
        print(f"Lote: {batch_id} | {batch['status']} | {batch['counts']}")
        print(f"Trace ID de creación: {trace_id}")
        if args.verify_trace:

            def trace_ready():
                payload = httpx.get(f"{args.jaeger_url}/api/traces/{trace_id}", timeout=5).json()
                traces = payload.get("data") or []
                if not traces:
                    return None
                item = traces[0]
                services = {value["serviceName"] for value in item["processes"].values()}
                operations = {span["operationName"] for span in item["spans"]}
                if {"andinarag-api", "andinarag-worker"} <= services and {
                    "rag.retrieve",
                    "llm.generate",
                } <= operations:
                    return {
                        "trace_id": trace_id,
                        "services": sorted(services),
                        "operations": sorted(operations),
                        "spans": len(item["spans"]),
                    }
                return None

            print(f"Traza distribuida verificada: {wait_for(trace_ready, timeout=30)}")
        proposals = client.get("/proposals", params={"batch_id": batch_id}).json()
        assert proposals, "No se generaron propuestas; comprueba umbral y modelo"
        detail = client.get(f"/proposals/{proposals[0]['id']}").json()
        assert detail["citations"], "La propuesta carece de citas"
        if args.approve:
            response = client.patch(
                f"/proposals/{detail['id']}",
                json={"revision": detail["revision"], "status": "approved"},
            )
            response.raise_for_status()
            assert client.get(f"/proposals/{detail['id']}").json()["status"] == "approved"
            print("Aprobación persistida y citas verificadas.")
        print("UI: http://localhost:8080 | Trazas: http://localhost:16686")


if __name__ == "__main__":
    main()
