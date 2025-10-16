"""Training and inference utilities for the arkit8s assistant."""

from __future__ import annotations

import math
import pickle
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "tmp"
MODEL_PATH = MODEL_DIR / "assistant_model.pkl"

MODEL_VERSION = 1


class AssistantModelNotFoundError(FileNotFoundError):
    """Raised when the assistant model has not been trained yet."""


@dataclass(frozen=True)
class AssistantReply:
    """Container for the assistant inference result."""

    answer: str
    supporting_chunks: list[tuple[str, str]]
    command_suggestions: list[tuple[str, str]]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]+", text.lower())


def _chunk_text(text: str, max_chars: int) -> Iterable[str]:
    paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n", text) if segment.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    buffer: list[str] = []
    current = 0
    for paragraph in paragraphs:
        para_len = len(paragraph)
        if current + para_len > max_chars and buffer:
            chunks.append("\n\n".join(buffer))
            buffer = []
            current = 0
        buffer.append(paragraph)
        current += para_len

    if buffer:
        chunks.append("\n\n".join(buffer))
    return chunks


def _build_vocabulary(tokenized_chunks: Sequence[list[str]], min_frequency: int) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for tokens in tokenized_chunks:
        counter.update(tokens)

    vocab_items = [item for item in counter.items() if item[1] >= min_frequency]
    vocab_items.sort(key=lambda item: (-item[1], item[0]))
    return {token: idx for idx, (token, _freq) in enumerate(vocab_items)}


def _vectorize(tokens: Sequence[str], vocab: dict[str, int]) -> np.ndarray:
    vector = np.zeros(len(vocab), dtype=np.float32)
    for token in tokens:
        idx = vocab.get(token)
        if idx is None:
            continue
        vector[idx] += 1.0
    total = vector.sum()
    if total > 0:
        vector /= total
    return vector


def _prepare_dataset(
    repo_root: Path,
    max_chars: int,
    min_frequency: int,
    max_files: int | None = None,
) -> tuple[list[str], list[tuple[str, str]], dict[str, int], list[list[str]]]:
    candidate_extensions = {
        ".md",
        ".rst",
        ".txt",
        ".py",
        ".yaml",
        ".yml",
    }

    tokenized: list[list[str]] = []
    chunks: list[str] = []
    sources: list[tuple[str, str]] = []

    collected = 0
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in candidate_extensions:
            continue
        if "tmp" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for chunk in _chunk_text(text, max_chars):
            if not chunk.strip():
                continue
            chunk_tokens = _tokenize(chunk)
            if not chunk_tokens:
                continue
            tokenized.append(chunk_tokens)
            chunks.append(chunk)
            sources.append((str(path.relative_to(repo_root)), chunk[:80].replace("\n", " ") + ("..." if len(chunk) > 80 else "")))
            collected += 1
            if max_files is not None and collected >= max_files:
                break
        if max_files is not None and collected >= max_files:
            break

    if not chunks:
        raise RuntimeError("No se encontraron fragmentos de texto para entrenar el asistente.")

    vocab = _build_vocabulary(tokenized, min_frequency)
    if not vocab:
        raise RuntimeError(
            "La frecuencia mínima seleccionada eliminó todo el vocabulario. Usa un valor menor con --min-frequency."
        )

    return chunks, sources, vocab, tokenized


def _relu(values: np.ndarray) -> np.ndarray:
    return np.maximum(values, 0.0)


def _relu_derivative(values: np.ndarray) -> np.ndarray:
    return (values > 0).astype(np.float32)


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def train_assistant_knowledge_base(
    repo_root: Path,
    *,
    output_path: Path | None = None,
    epochs: int = 6,
    hidden_size: int = 128,
    batch_size: int = 16,
    max_chars: int = 1200,
    min_frequency: int = 2,
    max_chunks: int | None = None,
    learning_rate: float = 0.01,
) -> dict[str, int | float | str]:
    """Train the assistant model and persist the resulting artifacts."""

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    output = output_path or MODEL_PATH

    chunks, sources, vocab, tokenized = _prepare_dataset(
        repo_root,
        max_chars=max_chars,
        min_frequency=min_frequency,
        max_files=max_chunks,
    )

    vectors = np.stack([_vectorize(tokens, vocab) for tokens in tokenized])
    vocab_size = len(vocab)
    rng = np.random.default_rng(seed=42)

    W1 = rng.normal(scale=0.1, size=(vocab_size, hidden_size)).astype(np.float32)
    b1 = np.zeros(hidden_size, dtype=np.float32)
    W2 = rng.normal(scale=0.1, size=(hidden_size, vocab_size)).astype(np.float32)
    b2 = np.zeros(vocab_size, dtype=np.float32)

    num_samples = vectors.shape[0]
    indices = np.arange(num_samples)

    for _epoch in range(epochs):
        rng.shuffle(indices)
        for start in range(0, num_samples, batch_size):
            end = min(start + batch_size, num_samples)
            batch = vectors[indices[start:end]]

            hidden_linear = batch @ W1 + b1
            hidden = _relu(hidden_linear)
            reconstruction = hidden @ W2 + b2

            error = reconstruction - batch
            loss = np.mean(error**2)
            if math.isnan(float(loss)):
                raise RuntimeError("El entrenamiento del asistente produjo un valor NaN en la pérdida.")

            grad_reconstruction = (2.0 / batch.shape[0]) * error
            grad_W2 = hidden.T @ grad_reconstruction
            grad_b2 = grad_reconstruction.sum(axis=0)

            grad_hidden = grad_reconstruction @ W2.T
            grad_hidden *= _relu_derivative(hidden_linear)
            grad_W1 = batch.T @ grad_hidden
            grad_b1 = grad_hidden.sum(axis=0)

            W2 -= learning_rate * grad_W2
            b2 -= learning_rate * grad_b2
            W1 -= learning_rate * grad_W1
            b1 -= learning_rate * grad_b1

    embeddings = _relu(vectors @ W1 + b1)
    embeddings = _normalize_rows(embeddings)

    state = {
        "version": MODEL_VERSION,
        "vocab": vocab,
        "hidden_size": hidden_size,
        "encoder_weights": W1,
        "encoder_bias": b1,
        "chunk_texts": chunks,
        "chunk_sources": sources,
        "chunk_embeddings": embeddings,
    }

    with output.open("wb") as fh:
        pickle.dump(state, fh)

    return {
        "artifacts": str(output),
        "chunks": len(chunks),
        "vocab_size": len(vocab),
        "epochs": epochs,
    }


def _load_state(model_path: Path | None = None) -> dict:
    path = model_path or MODEL_PATH
    if not path.exists():
        raise AssistantModelNotFoundError(str(path))
    with path.open("rb") as fh:
        state = pickle.load(fh)
    if state.get("version") != MODEL_VERSION:
        raise RuntimeError(
            "La versión del modelo no coincide con la soportada. Vuelve a entrenar el asistente con train-assistant."
        )
    return state


def _encode(vector: np.ndarray, weights: np.ndarray, bias: np.ndarray) -> np.ndarray:
    hidden_linear = vector @ weights + bias
    embedding = _relu(hidden_linear)
    norm = np.linalg.norm(embedding)
    if norm == 0.0:
        return embedding
    return embedding / norm


def _cosine_similarity(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    dot = matrix @ vector
    return dot


def generate_assistant_reply(
    question: str,
    command_corpus: Sequence[tuple[str, str]],
    *,
    model_path: Path | None = None,
    top_k_chunks: int = 3,
    top_k_commands: int = 3,
) -> AssistantReply:
    """Generate an answer for a natural language question."""

    state = _load_state(model_path)
    vocab: dict[str, int] = state["vocab"]
    weights: np.ndarray = state["encoder_weights"]
    bias: np.ndarray = state["encoder_bias"]
    chunk_texts: list[str] = state["chunk_texts"]
    chunk_sources: list[tuple[str, str]] = state["chunk_sources"]
    chunk_embeddings: np.ndarray = state["chunk_embeddings"]

    question_tokens = _tokenize(question)
    query_vector = _vectorize(question_tokens, vocab)
    if float(query_vector.sum()) == 0.0:
        raise ValueError("La pregunta no contiene vocabulario conocido por el asistente.")

    query_embedding = _encode(query_vector, weights, bias)

    similarities = _cosine_similarity(chunk_embeddings, query_embedding)
    top_k = min(top_k_chunks, similarities.shape[0])
    indices = np.argsort(similarities)[-top_k:][::-1]
    scores = similarities[indices]

    supporting = []
    for score, idx in zip(scores.tolist(), indices.tolist()):
        snippet = chunk_texts[idx].strip()
        source = chunk_sources[idx]
        supporting.append((f"{source[0]} (relevancia {score:.2f})", snippet))

    command_suggestions: list[tuple[str, str]] = []
    if command_corpus:
        command_vectors: list[np.ndarray] = []
        command_refs: list[str] = []
        for name, description in command_corpus:
            tokens = _tokenize(f"{name} {description}")
            vector = _vectorize(tokens, vocab)
            if float(vector.sum()) == 0.0:
                continue
            command_vectors.append(vector)
            command_refs.append(name)

        if command_vectors:
            matrix = np.stack(command_vectors)
            command_embeddings = np.apply_along_axis(lambda row: _encode(row, weights, bias), 1, matrix)
            cmd_scores = command_embeddings @ query_embedding
            top_cmd = min(top_k_commands, cmd_scores.shape[0])
            cmd_indices = np.argsort(cmd_scores)[-top_cmd:][::-1]
            for score, idx in zip(cmd_scores[cmd_indices].tolist(), cmd_indices.tolist()):
                command_suggestions.append((command_refs[idx], f"Coincidencia {score:.2f}"))

    answer = supporting[0][1] if supporting else "No encontré un fragmento relevante en el repositorio."
    return AssistantReply(answer=answer, supporting_chunks=supporting, command_suggestions=command_suggestions)

