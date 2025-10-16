"""Training and inference utilities for the arkit8s assistant."""

from __future__ import annotations

import math
import pickle
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "tmp"
MODEL_PATH = MODEL_DIR / "assistant_model.pkl"

MODEL_VERSION = 2


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


def _vectorize(tokens: Sequence[str], vocab: dict[str, int]) -> list[float]:
    vector = [0.0] * len(vocab)
    for token in tokens:
        idx = vocab.get(token)
        if idx is None:
            continue
        vector[idx] += 1.0
    total = sum(vector)
    if total > 0:
        vector = [value / total for value in vector]
    return vector


def _zeros_matrix(rows: int, cols: int) -> list[list[float]]:
    return [[0.0] * cols for _ in range(rows)]


def _zeros_vector(length: int) -> list[float]:
    return [0.0] * length


def _matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    result_rows = len(left)
    result_cols = len(right[0])
    shared_dim = len(right)
    result = _zeros_matrix(result_rows, result_cols)
    for i in range(result_rows):
        left_row = left[i]
        for k in range(shared_dim):
            left_value = left_row[k]
            if left_value == 0.0:
                continue
            right_row = right[k]
            target_row = result[i]
            for j in range(result_cols):
                target_row[j] += left_value * right_row[j]
    return result


def _matrix_add_vector(matrix: list[list[float]], vector: list[float]) -> list[list[float]]:
    return [[row[j] + vector[j] for j in range(len(vector))] for row in matrix]


def _matrix_subtract(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [[left[i][j] - right[i][j] for j in range(len(left[i]))] for i in range(len(left))]


def _matrix_scalar_multiply(matrix: list[list[float]], scalar: float) -> list[list[float]]:
    return [[value * scalar for value in row] for row in matrix]


def _matrix_sum_axis0(matrix: list[list[float]]) -> list[float]:
    if not matrix:
        return []
    cols = len(matrix[0])
    totals = [0.0] * cols
    for row in matrix:
        for j, value in enumerate(row):
            totals[j] += value
    return totals


def _transpose(matrix: list[list[float]]) -> list[list[float]]:
    if not matrix:
        return []
    rows = len(matrix)
    cols = len(matrix[0])
    transposed = _zeros_matrix(cols, rows)
    for i in range(rows):
        for j in range(cols):
            transposed[j][i] = matrix[i][j]
    return transposed


def _relu(values: list[list[float]] | list[float]) -> list[list[float]] | list[float]:
    if not values:
        return values
    if isinstance(values[0], list):  # type: ignore[index]
        return [[max(value, 0.0) for value in row] for row in values]  # type: ignore[index]
    return [max(value, 0.0) for value in values]  # type: ignore[return-value]


def _relu_derivative(values: list[list[float]]) -> list[list[float]]:
    return [[1.0 if value > 0.0 else 0.0 for value in row] for row in values]


def _elementwise_multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [[left[i][j] * right[i][j] for j in range(len(left[i]))] for i in range(len(left))]


def _normalize_rows(matrix: list[list[float]]) -> list[list[float]]:
    normalized: list[list[float]] = []
    for row in matrix:
        norm = math.sqrt(sum(value * value for value in row))
        if norm == 0.0:
            normalized.append(list(row))
        else:
            normalized.append([value / norm for value in row])
    return normalized


def _vector_dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _encode_vector(vector: list[float], weights: list[list[float]], bias: list[float]) -> list[float]:
    linear = [bias[j] for j in range(len(bias))]
    for j in range(len(bias)):
        accumulator = linear[j]
        for i in range(len(vector)):
            accumulator += vector[i] * weights[i][j]
        linear[j] = accumulator
    activated = [max(value, 0.0) for value in linear]
    norm = math.sqrt(sum(value * value for value in activated))
    if norm == 0.0:
        return activated
    return [value / norm for value in activated]


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

    vectors = [_vectorize(tokens, vocab) for tokens in tokenized]
    vocab_size = len(vocab)
    rng = random.Random(42)

    W1 = [[rng.gauss(0.0, 0.1) for _ in range(hidden_size)] for _ in range(vocab_size)]
    b1 = _zeros_vector(hidden_size)
    W2 = [[rng.gauss(0.0, 0.1) for _ in range(vocab_size)] for _ in range(hidden_size)]
    b2 = _zeros_vector(vocab_size)

    num_samples = len(vectors)
    indices = list(range(num_samples))

    for _epoch in range(epochs):
        rng.shuffle(indices)
        for start in range(0, num_samples, batch_size):
            end = min(start + batch_size, num_samples)
            batch = [vectors[idx] for idx in indices[start:end]]

            hidden_linear = _matrix_add_vector(_matmul(batch, W1), b1)
            hidden = _relu(hidden_linear)
            reconstruction = _matrix_add_vector(_matmul(hidden, W2), b2)

            error = _matrix_subtract(reconstruction, batch)
            squared_error_sum = sum(value * value for row in error for value in row)
            total_elements = len(error) * len(error[0]) if error else 0
            loss = squared_error_sum / total_elements if total_elements else 0.0
            if math.isnan(loss):
                raise RuntimeError("El entrenamiento del asistente produjo un valor NaN en la pérdida.")

            grad_reconstruction = _matrix_scalar_multiply(error, 2.0 / len(batch))
            grad_W2 = _matmul(_transpose(hidden), grad_reconstruction)
            grad_b2 = _matrix_sum_axis0(grad_reconstruction)

            grad_hidden = _matmul(grad_reconstruction, _transpose(W2))
            grad_hidden = _elementwise_multiply(grad_hidden, _relu_derivative(hidden_linear))
            grad_W1 = _matmul(_transpose(batch), grad_hidden)
            grad_b1 = _matrix_sum_axis0(grad_hidden)

            for i in range(len(W2)):
                row = W2[i]
                grad_row = grad_W2[i]
                for j in range(len(row)):
                    row[j] -= learning_rate * grad_row[j]
            for j in range(len(b2)):
                b2[j] -= learning_rate * grad_b2[j]
            for i in range(len(W1)):
                row = W1[i]
                grad_row = grad_W1[i]
                for j in range(len(row)):
                    row[j] -= learning_rate * grad_row[j]
            for j in range(len(b1)):
                b1[j] -= learning_rate * grad_b1[j]

    embeddings = _normalize_rows(
        _relu(_matrix_add_vector(_matmul(vectors, W1), b1))  # type: ignore[arg-type]
    )

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


def _encode(vector: list[float], weights: list[list[float]], bias: list[float]) -> list[float]:
    return _encode_vector(vector, weights, bias)


def _cosine_similarity(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [_vector_dot(row, vector) for row in matrix]


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
    weights: list[list[float]] = state["encoder_weights"]
    bias: list[float] = state["encoder_bias"]
    chunk_texts: list[str] = state["chunk_texts"]
    chunk_sources: list[tuple[str, str]] = state["chunk_sources"]
    chunk_embeddings: list[list[float]] = state["chunk_embeddings"]

    question_tokens = _tokenize(question)
    query_vector = _vectorize(question_tokens, vocab)
    if sum(query_vector) == 0.0:
        raise ValueError("La pregunta no contiene vocabulario conocido por el asistente.")

    query_embedding = _encode(query_vector, weights, bias)

    similarities = _cosine_similarity(chunk_embeddings, query_embedding)
    top_k = min(top_k_chunks, len(similarities))
    ordered_indices = sorted(range(len(similarities)), key=lambda idx: similarities[idx], reverse=True)[:top_k]

    supporting = []
    for idx in ordered_indices:
        score = similarities[idx]
        snippet = chunk_texts[idx].strip()
        source = chunk_sources[idx]
        supporting.append((f"{source[0]} (relevancia {score:.2f})", snippet))

    command_suggestions: list[tuple[str, str]] = []
    if command_corpus:
        command_vectors: list[list[float]] = []
        command_refs: list[str] = []
        for name, description in command_corpus:
            tokens = _tokenize(f"{name} {description}")
            vector = _vectorize(tokens, vocab)
            if sum(vector) == 0.0:
                continue
            command_vectors.append(vector)
            command_refs.append(name)

        if command_vectors:
            command_embeddings = [_encode(vector, weights, bias) for vector in command_vectors]
            cmd_scores = [_vector_dot(embedding, query_embedding) for embedding in command_embeddings]
            top_cmd = min(top_k_commands, len(cmd_scores))
            ordered_cmd = sorted(range(len(cmd_scores)), key=lambda idx: cmd_scores[idx], reverse=True)[:top_cmd]
            for idx in ordered_cmd:
                command_suggestions.append((command_refs[idx], f"Coincidencia {cmd_scores[idx]:.2f}"))

    answer = supporting[0][1] if supporting else "No encontré un fragmento relevante en el repositorio."
    return AssistantReply(answer=answer, supporting_chunks=supporting, command_suggestions=command_suggestions)

