"""Sentence Transformers wrapper that refuses all implicit model downloads."""

from __future__ import annotations

import os
from pathlib import Path


class LocalEmbeddingError(RuntimeError):
    pass


class LocalEmbedder:
    def __init__(self, model_path: str | None = None):
        configured = model_path or os.environ.get("SELLBIRD_EMBEDDING_MODEL_PATH", "").strip()
        if not configured:
            raise LocalEmbeddingError(
                "Set SELLBIRD_EMBEDDING_MODEL_PATH to a previously downloaded local Sentence Transformers model directory"
            )
        self.path = Path(configured).expanduser().resolve()
        if not self.path.is_dir() or not (self.path / "config.json").is_file():
            raise LocalEmbeddingError(f"Local embedding model directory is unavailable: {self.path}")
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(str(self.path), local_files_only=True, trust_remote_code=False)
        except ImportError as exc:
            raise LocalEmbeddingError("Sentence Transformers is not installed; install the local-embeddings extra") from exc
        except Exception as exc:
            raise LocalEmbeddingError(f"Could not load the local embedding model ({type(exc).__name__})") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        if any(not text.strip() for text in texts):
            raise ValueError("Embedding input text cannot be empty")
        try:
            values = self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
            return [[float(component) for component in vector] for vector in values.tolist()]
        except Exception as exc:
            raise LocalEmbeddingError(f"Local embedding failed ({type(exc).__name__})") from exc

