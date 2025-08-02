"""
Deduplication Helpers
---------------------

This module defines helper functions used by the versioning system to
identify duplicate test cases within a single test set.  Duplicate
detection is performed within the scope of a specific version; tests
from different versions are never considered duplicates.  A duplicate
test is one whose `identifier` appears more than once.  The caller
should mark such tests appropriately but still preserve all
instances.
"""

from collections import Counter
from typing import Dict, List


def find_exact_duplicates(test_cases: List[Dict[str, any]]) -> List[str]:
    """
    Return identifiers that appear more than once within a list of test cases.

    This helper performs a simple count of the ``identifier`` field on each
    test case and returns a list of identifiers that are repeated.  It
    should be used when exact duplication by identifier needs to be
    detected.
    """
    counts = Counter(tc.get("identifier") for tc in test_cases)
    return [identifier for identifier, count in counts.items() if count > 1]


def find_semantic_duplicates(test_cases: List[Dict[str, any]], threshold: float = 0.9) -> List[str]:
    """
    Identify semantically duplicate test cases based on their step contents.

    Two test cases are considered duplicates if the cosine similarity of
    their flattened step representations exceeds ``threshold``.  The
    similarity is computed using TF‑IDF vectors.  When scikit‑learn is
    unavailable the function falls back to using difflib's sequence
    matcher.  The first occurrence of each semantic group is retained
    and subsequent identifiers are returned as duplicates.

    :param test_cases: List of test case dictionaries with ``identifier`` and
       ``steps`` fields.
    :param threshold: Similarity threshold between 0 and 1 above which
       cases are considered duplicates.
    :return: List of identifiers of test cases considered duplicates
    """
    if not test_cases:
        return []
    # Prepare textual representations of each test case's steps for vectorisation
    import json as _json
    texts = ["\n".join(_json.dumps(step, sort_keys=True) for step in tc.get("steps", [])) for tc in test_cases]
    # Attempt to use scikit‑learn for embeddings
    duplicates: List[str] = []
    seen: set[int] = set()
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
        vectorizer = TfidfVectorizer().fit(texts)
        vectors = vectorizer.transform(texts)
        for i in range(len(test_cases)):
            if i in seen:
                continue
            for j in range(i + 1, len(test_cases)):
                if j in seen:
                    continue
                try:
                    sim = cosine_similarity(vectors[i], vectors[j])[0][0]
                except Exception:
                    sim = 0.0
                if sim >= threshold:
                    duplicates.append(test_cases[j].get("identifier"))
                    seen.add(j)
    except Exception:
        # Fallback to sequence matcher
        from difflib import SequenceMatcher
        for i in range(len(test_cases)):
            if i in seen:
                continue
            for j in range(i + 1, len(test_cases)):
                if j in seen:
                    continue
                sm = SequenceMatcher(None, texts[i], texts[j])
                if sm.ratio() >= threshold:
                    duplicates.append(test_cases[j].get("identifier"))
                    seen.add(j)
    return duplicates


__all__ = ["find_exact_duplicates", "find_semantic_duplicates"]