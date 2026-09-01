from __future__ import annotations

import hashlib
import threading

import jieba
import numpy as np
from flask import current_app


_models: dict[str, object] = {}
_model_lock = threading.Lock()


def tokenize(text: str) -> list[str]:
    words = [word.strip().lower() for word in jieba.lcut(text) if word.strip()]
    compact = "".join(character for character in text.lower() if not character.isspace())
    words.extend(compact[index : index + 2] for index in range(max(0, len(compact) - 1)))
    return words


def _hash_embeddings(texts: list[str], dimensions: int = 256) -> np.ndarray:
    matrix = np.zeros((len(texts), dimensions), dtype=np.float32)
    for row, value in enumerate(texts):
        for token in tokenize(value):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "little") % dimensions
            matrix[row, index] += -1.0 if digest[0] & 1 else 1.0
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    if current_app.config.get("EMBEDDING_BACKEND") == "hash":
        return _hash_embeddings(texts)
    model_name = str(current_app.config["EMBEDDING_MODEL"])
    with _model_lock:
        model = _models.get(model_name)
        if model is None:
            from sentence_transformers import SentenceTransformer

            try:
                model = SentenceTransformer(model_name, local_files_only=True)
            except OSError:
                model = SentenceTransformer(model_name)
            _models[model_name] = model
    result = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    return np.asarray(result, dtype=np.float32)


def start_embedding_warmup(app) -> None:
    if app.config.get("TESTING") or app.config.get("EMBEDDING_BACKEND") == "hash":
        return

    def warm() -> None:
        with app.app_context():
            try:
                embed_texts(["企业制度混合检索预热"])
                app.logger.info("embedding model warmed up")
            except Exception:
                app.logger.exception("embedding model warmup failed; first search will retry")

    threading.Thread(target=warm, name="embedding-warmup", daemon=True).start()
