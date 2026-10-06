"""Reproducer script demonstrating the exact failure modes discovered in EpisodicLessonStore."""

from __future__ import annotations
import math
import time
from novaswarm.memory.episodic import EpisodicLessonStore

def reproduce_serialization_data_loss():
    print("=== REPRODUCING FINDING 1: Truncation Data Loss on Serialization ===")
    store = EpisodicLessonStore()
    # Scenario: User or loader sets 3 documents and 1 recommendation (mismatched array)
    store.documents = ["Situation A", "Situation B", "Situation C"]
    store.recommendations = ["Advice A"]
    store._rebuild_index()

    print(f"Original store.documents: {store.documents} (len={len(store.documents)})")
    print(f"Original store.recommendations: {store.recommendations} (len={len(store.recommendations)})")
    print(f"Original store._records: len={len(store._records)}")

    # Serialize to dictionary
    serialized = store.to_dict()
    print(f"Serialized 'documents' count: {len(serialized['documents'])}")
    print(f"Serialized 'records' count: {len(serialized['records'])}")

    # Deserialize
    restored = EpisodicLessonStore.from_dict(serialized)
    print(f"Restored store.documents: {restored.documents} (len={len(restored.documents)})")
    print(f"Restored store.recommendations: {restored.recommendations} (len={len(restored.recommendations)})")

    # The documents "Situation B" and "Situation C" were permanently lost!
    assert len(restored.documents) == len(store.documents), (
        f"Data loss bug! Expected {len(store.documents)} documents, but got {len(restored.documents)}!"
    )

def reproduce_index_out_of_range_without_rebuild():
    print("\n=== REPRODUCING FINDING 2: IndexError on Out-of-Sync Mutation ===")
    store = EpisodicLessonStore()
    # Initially 1 situation
    store.add_situations([("Short situation", "Short advice")])
    # Now total_docs in _index is 1

    # Caller mutates documents and recommendations in place (as MemoryStore.load does before rebuild)
    store.documents = ["Sit 1", "Sit 2", "Sit 3"]
    store.recommendations = ["Rec 1", "Rec 2", "Rec 3"]
    # Suppose caller queries before or forgets to call _rebuild_index():
    print(f"_records length: {len(store._records)}, _index.total_docs: {store._index.total_docs}")
    try:
        store.get_memories("Sit 1")
        print("No error")
    except IndexError as e:
        print(f"Caught expected IndexError: {e}")

if __name__ == "__main__":
    try:
        reproduce_index_out_of_range_without_rebuild()
    except Exception as e:
        print(f"IndexError test result: {e}")

    try:
        reproduce_serialization_data_loss()
    except AssertionError as e:
        print(f"Caught assertion: {e}")
