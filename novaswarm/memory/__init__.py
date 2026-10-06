"""Persistent agent memory — Supabase-backed storage and proprietary episodic memory.

Provides:
- ``EpisodicLessonStore`` — pure-Python Robertson-Spärck Jones BM25 with exponential recency decay
- ``EpisodicLessonMatch`` — dual-compatible string/dict memory match object
- ``LessonRecord`` — individual episodic lesson record
- ``InvertedIndex`` — pure-Python BM25 inverted index
- ``MemoryStore`` — load/save agent memories to Supabase
"""

from novaswarm.memory.episodic import (
    EpisodicLessonMatch,
    EpisodicLessonStore,
    InvertedIndex,
    LessonRecord,
)
from novaswarm.memory.store import MemoryStore

__all__ = [
    "EpisodicLessonMatch",
    "EpisodicLessonStore",
    "InvertedIndex",
    "LessonRecord",
    "MemoryStore",
]
