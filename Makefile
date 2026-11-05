.PHONY: up test check demo evaluate
up:
	docker compose up --build
test:
	uv run pytest -q
	cd frontend && npm test
check:
	uv run ruff check backend scripts
	uv run ruff format --check backend scripts
	uv run mypy
	cd frontend && npm run lint && npm run build
demo:
	docker compose exec -T api python -m scripts.demo --url http://localhost:8000/api/v1
evaluate:
	docker compose exec -T api python -m scripts.evaluate --check
	mkdir -p reports
	docker compose cp api:/app/reports/evaluation.json reports/evaluation.json
