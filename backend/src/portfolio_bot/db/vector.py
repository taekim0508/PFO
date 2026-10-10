"""Passing vectors to pgvector.

Shared by the write path, which stores chunk vectors, and the read path, which sends a
question's vector to compare against them.
"""

from __future__ import annotations

from collections.abc import Sequence


def vector_literal(vector: Sequence[float]) -> str:
    """pgvector's text form, '[0.1,0.2,...]'. Saves a dependency on pgvector's adapter."""
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"
