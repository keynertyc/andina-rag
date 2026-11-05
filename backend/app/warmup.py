"""Download/cache the pinned model before accepting worker tasks, outside their time limit."""

from app.embeddings import get_embedder

if __name__ == "__main__":
    embedder = get_embedder()
    embedder.query("consulta de preparación")
    print(f"Embeddings listos: {embedder.model_id}")
