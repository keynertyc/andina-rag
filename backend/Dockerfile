FROM ghcr.io/astral-sh/uv:0.9.3 AS uv
FROM python:3.12.12-slim
COPY --from=uv /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/backend UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend ./backend
COPY alembic.ini ./
COPY scripts ./scripts
COPY samples ./samples
RUN useradd --create-home app && mkdir /app/uploads /app/model-cache && chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
