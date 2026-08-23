"""Semantic search over the media catalogue.

Every similarity concern lives in this module. Callers hand it Media rows and a
plain-English description and get back ranked ids — they never see a vector, a
dimension count, or a dot product. That is deliberate: `find_similar` is the one
seam to reimplement if the catalogue ever outgrows a full scan and pgvector
becomes worth installing.

Embeddings are produced by a small model that runs locally, so this works with
no API key and, after the one-time model download, with no network at all. Like
tmdb.py, nothing here is allowed to take the app down: callers catch
EmbeddingsUnavailable and carry on without semantic search.
"""

import logging
from typing import Iterable, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# 384 dimensions, ~67 MB on disk. Small enough to load in a web process, and
# well above the quality floor for "find me something like this" over prose.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384

# A floor for obvious nonsense, and nothing more ambitious than that.
#
# Measured on this catalogue, a score depends about as much on how a question is
# phrased as on whether the answer is any good. A long, specific query scores its
# correct hit at 0.58; the short, vague "slow and melancholy" scores the same
# correct hit at 0.50; and an off-corpus "romantic comedy in Paris" still reaches
# 0.48. Relevant and irrelevant OVERLAP, so no absolute cut separates them — the
# first two attempts here were 0.60 and 0.50, and both silently discarded correct
# answers to ordinary questions.
#
# So the floor is set below the overlap, where it only rejects the genuinely
# unrelated (an off-topic query tops out around 0.39), and precision is left to
# the caller. That is the right division of labour anyway: find_similar sees a
# number, while the model reading its output sees the synopses and can tell an
# actual mismatch from a badly-worded question.
MIN_SCORE = 0.42

_model = None


class EmbeddingsUnavailable(RuntimeError):
    """Raised for anything the caller can act on: model missing, download failed."""


def _load():
    """Return the embedding model, loading it on first use.

    Loading is deferred rather than done at import because the constructor
    downloads ~67 MB the first time it runs. At import that would stall every
    `uvicorn --reload` restart, and would make the API unstartable offline
    before the first successful download — for a feature that is meant to be
    optional.
    """
    global _model
    if _model is not None:
        return _model

    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise EmbeddingsUnavailable(
            "fastembed is not installed, so semantic search is unavailable.\n"
            "  Install it: pip install -r requirements.txt"
        ) from exc

    try:
        _model = TextEmbedding(model_name=MODEL_NAME)
    except Exception as exc:
        raise EmbeddingsUnavailable(
            f"Could not load the embedding model {MODEL_NAME}: {exc}\n"
            "  The first run downloads ~67 MB, so this needs network once.\n"
            "  Afterwards it is cached and works offline."
        ) from exc

    return _model


def document_for(media) -> str:
    """The text that represents a title to the embedding model.

    Deliberately more than the synopsis. Embedding the synopsis alone throws
    away the title, year, and genre, so a query like "90s sci-fi" can only match
    a synopsis that happens to contain those words — which most do not. Feeding
    the model a sentence about the title instead lets the query match the facts
    as well as the plot.
    """
    kind = {"movie": "a film", "tv": "a TV series"}.get(media.media_type, "a title")
    opening = f"{media.title} ({media.year}), {kind}." if media.year else f"{media.title}, {kind}."

    parts = [opening]
    if media.genres:
        parts.append(f"Genres: {', '.join(media.genres)}.")
    if media.synopsis:
        parts.append(media.synopsis)
    return " ".join(parts)


def embed_documents(texts: Sequence[str]) -> list[list[float]]:
    """Vectors for catalogue entries, in the order given.

    Returns plain lists rather than numpy arrays because these go straight into
    a FLOAT8[] column, and psycopg2 has no adapter for numpy scalars.
    """
    if not texts:
        return []
    model = _load()
    return [vector.tolist() for vector in model.embed(list(texts))]


def embed_query(text: str) -> np.ndarray:
    """Vector for a search phrase.

    Uses `query_embed`, not `embed`. BGE models are trained asymmetrically: a
    question and the passage answering it are phrased differently, so the query
    side gets an instruction prefix that the document side must not have.
    Embedding both with the same call measurably degrades ranking.
    """
    model = _load()
    vectors = list(model.query_embed([text]))
    if not vectors:
        raise EmbeddingsUnavailable(f"The embedding model returned nothing for {text!r}.")
    return np.asarray(vectors[0], dtype=np.float64)


def _normalise(matrix: np.ndarray) -> np.ndarray:
    """Scale each row to unit length so a dot product is a cosine.

    Zero-length rows would divide by zero and poison the whole result with NaN,
    so they are left alone and score 0 against everything.
    """
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


def find_similar(
    query: str,
    candidates: Iterable,
    limit: int = 5,
    min_score: float = MIN_SCORE,
) -> list[tuple[int, float]]:
    """Rank `candidates` (Media rows) by how well they match `query`.

    Returns [(media_id, score), ...] best first, dropping anything below
    `min_score`. An empty list is an ordinary answer, not an error.

    Read the ranking, not the number. Scores from this model occupy a narrow
    band and are not calibrated across queries — 0.58 can be an excellent match
    for one phrasing and mediocre for another, so comparing a score against a
    constant, or against a score from a different query, will mislead you.

    This is the function to replace with a pgvector query. Its callers only know
    about ids and scores, so nothing outside this module changes.
    """
    usable = [
        m for m in candidates
        # A vector from a different model is not comparable with this query, and
        # a wrong-length one would make numpy build a ragged object array and
        # fail somewhere far less obvious than here.
        if m.embedding and m.embedding_model == MODEL_NAME and len(m.embedding) == DIMENSIONS
    ]
    if not usable:
        return []

    query_vector = embed_query(query)
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0:
        return []
    query_vector = query_vector / query_norm

    matrix = _normalise(np.asarray([m.embedding for m in usable], dtype=np.float64))
    scores = matrix @ query_vector

    ranked = sorted(
        ((m.id, float(score)) for m, score in zip(usable, scores)),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [pair for pair in ranked if pair[1] >= min_score][:limit]
