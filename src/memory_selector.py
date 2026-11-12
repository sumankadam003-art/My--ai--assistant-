import re
from memory import load_memories


def select_relevant_memories(prompt, limit=5):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        return []

    memories = load_memories()

    if not memories or not isinstance(prompt, str):
        return []

    def words(text):
        return set(re.findall(r"\b[a-zA-Z0-9]+\b", text.lower()))

    query_words = words(prompt)

    if not query_words:
        return []

    scored = []

    for memory in memories:
        memory_words = words(memory)
        overlap = query_words & memory_words

        if overlap:
            score = len(overlap) / len(query_words)
            scored.append((score, memory))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [memory for score, memory in scored[:limit]]
