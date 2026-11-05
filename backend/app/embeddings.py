"""The hash adapter is a test double; production retrieval uses multilingual E5."""

import hashlib
import math
import re
import unicodedata
from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.telemetry import tracer

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MODEL_ID = f"{MODEL_NAME}@{MODEL_REVISION}"
HASH_MODEL_ID = "test-only/lexical-hash-v1"


class Tokenizer(Protocol):
    def spans(self, text: str) -> list[tuple[int, int]]: ...


class Embedder(Protocol):
    model_id: str
    tokenizer: Tokenizer

    def passages(self, texts: list[str]) -> list[list[float]]: ...
    def query(self, text: str) -> list[float]: ...


class RegexTokenizer:
    def spans(self, text: str) -> list[tuple[int, int]]:
        return [(match.start(), match.end()) for match in re.finditer(r"\S+", text)]


class HashEmbedder:
    model_id = HASH_MODEL_ID
    tokenizer: Tokenizer = RegexTokenizer()

    def query(self, text: str) -> list[float]:
        vector = [0.0] * 384
        normalized = unicodedata.normalize("NFKD", text.casefold())
        for word in re.findall(r"[a-z0-9]{3,}", normalized):
            position = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4]) % 384
            vector[position] += 1
        norm = math.sqrt(sum(value * value for value in vector)) or 1
        return [value / norm for value in vector]

    def passages(self, texts: list[str]) -> list[list[float]]:
        return [self.query(text) for text in texts]


class E5Tokenizer:
    def __init__(self, path: str) -> None:
        from tokenizers import Tokenizer as NativeTokenizer

        self.native = NativeTokenizer.from_file(path)
        self.native.no_truncation()
        self.native.no_padding()

    def spans(self, text: str) -> list[tuple[int, int]]:
        return self.native.encode(text, add_special_tokens=False).offsets


class FastEmbedder:
    model_id = MODEL_ID
    tokenizer: Tokenizer

    def __init__(self) -> None:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType
        from huggingface_hub import snapshot_download

        with tracer.start_as_current_span("embedding.load"):
            path = snapshot_download(
                repo_id=MODEL_NAME,
                revision=MODEL_REVISION,
                cache_dir=str(get_settings().model_cache_dir),
                allow_patterns=[
                    "config.json",
                    "tokenizer*",
                    "special_tokens_map.json",
                    "sentencepiece.bpe.model",
                    "onnx/model.onnx",
                ],
            )
            if not any(m["model"] == MODEL_NAME for m in TextEmbedding.list_supported_models()):
                TextEmbedding.add_custom_model(
                    model=MODEL_NAME,
                    pooling=PoolingType.MEAN,
                    normalization=True,
                    sources=ModelSource(hf=MODEL_NAME),
                    dim=384,
                    model_file="onnx/model.onnx",
                )
            self.model = TextEmbedding(
                model_name=MODEL_NAME,
                specific_model_path=path,
                threads=2,
                providers=["CPUExecutionProvider"],
            )
            self.tokenizer = E5Tokenizer(path + "/tokenizer.json")

    def passages(self, texts: list[str]) -> list[list[float]]:
        with tracer.start_as_current_span("embedding.passages") as span:
            span.set_attribute("embedding.model", self.model_id)
            span.set_attribute("embedding.count", len(texts))
            return [
                vector.tolist()
                for vector in self.model.embed(
                    ["passage: " + text for text in texts], batch_size=16
                )
            ]

    def query(self, text: str) -> list[float]:
        with tracer.start_as_current_span("embedding.query"):
            return next(iter(self.model.embed(["query: " + text]))).tolist()


def configured_model_id() -> str:
    return HASH_MODEL_ID if get_settings().embedding_provider == "hash" else MODEL_ID


@lru_cache
def get_embedder() -> Embedder:
    return HashEmbedder() if get_settings().embedding_provider == "hash" else FastEmbedder()
