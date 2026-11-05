"""Exercise actual Redis/PostgreSQL outages on this project's local Compose stack."""

import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def compose(*arguments: str) -> None:
    subprocess.run(["docker", "compose", *arguments], cwd=ROOT, check=True)


def wait_ready(client: httpx.Client) -> None:
    for _ in range(30):
        try:
            if client.get("/health/ready").status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(1)
    raise RuntimeError("La API no recuperó disponibilidad")


def main() -> None:
    report = {}
    product = json.loads((ROOT / "samples/products/productos.json").read_text())[0]
    products = json.dumps([product]).encode()
    key = "resilience-" + str(uuid4())
    with httpx.Client(base_url="http://localhost:8000/api/v1", timeout=30) as client:
        wait_ready(client)
        try:
            compose("stop", "redis")
            response = client.post(
                "/batches",
                headers={"Idempotency-Key": key},
                files={"file": ("resilience.json", products)},
            )
            assert response.status_code == 503, response.text
            batch_id = response.json()["error"]["batch_id"]
            assert client.get(f"/batches/{batch_id}").json()["dispatch_error"]
            report["redis_outage"] = "503; batch persisted with dispatch error"
        finally:
            compose("start", "redis")
        wait_ready(client)
        response = client.post(
            "/batches",
            headers={"Idempotency-Key": key},
            files={"file": ("resilience.json", products)},
        )
        assert response.status_code == 202 and response.json()["id"] == batch_id
        for _ in range(30):
            batch = client.get(f"/batches/{batch_id}").json()
            if batch["terminal"]:
                break
            time.sleep(1)
        assert batch["counts"].get("succeeded") == 1, batch
        report["redis_recovery"] = "same batch completed, exactly one proposal"
        proposals = client.get("/proposals", params={"batch_id": batch_id}).json()
        assert len(proposals) == 1
        proposal = proposals[0]
        response = client.patch(
            f"/proposals/{proposal['id']}",
            json={"revision": proposal["revision"], "status": "approved"},
        )
        response.raise_for_status()
        item_id = client.get(f"/batches/{batch_id}/items").json()[0]["id"]
        compose(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import sys; from app.tasks import enrich_task; "
            "[enrich_task.delay(sys.argv[1]) for _ in range(4)]",
            item_id,
        )
        time.sleep(2)
        assert len(client.get("/proposals", params={"batch_id": batch_id}).json()) == 1
        assert client.get(f"/proposals/{proposal['id']}").json()["status"] == "approved"
        report["redelivery"] = "four duplicate Celery messages preserve one approved proposal"
        try:
            compose("stop", "db")
            response = client.get("/batches")
            assert response.status_code == 503, response.text
            assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
            report["postgres_outage"] = "503 with DATABASE_UNAVAILABLE"
        finally:
            compose("start", "db")
        wait_ready(client)
        assert client.get(f"/proposals/{proposal['id']}").json()["status"] == "approved"
        report["postgres_recovery"] = "persisted review survives database restart"
    path = ROOT / "reports/resilience.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
