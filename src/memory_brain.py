import json
import re

from groq_brain import ask_groq


_SECRET_PATTERNS = [
    re.compile(
        r"\b(?:password|passwd|pwd|api[_ -]?key|access[_ -]?token|"
        r"auth[_ -]?token|refresh[_ -]?token|client[_ -]?secret|"
        r"secret[_ -]?key)\b\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|"
        r"github_pat_[A-Za-z0-9_]{20,}|gsk_[A-Za-z0-9_-]{16,}|"
        r"xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[A-Z0-9]{16})\b"
    ),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"
    ),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?<!\d)(?:\+?91[- .]?)?[6-9]\d{9}(?!\d)"),
    re.compile(
        r"\b(?:my|our)\s+(?:date of birth|dob|birthday)\b|"
        r"\b(?:born on|date of birth is)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:password|passcode|pin)\s+(?:is|:|=)\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:cancer|diabetes|HIV|AIDS|depression|bipolar|"
        r"schizophrenia|epilepsy|kidney disease|heart disease|"
        r"medical diagnosis|medication|taking chemotherapy)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d{1,5}\s+[\w .'-]{2,40}\b"
        r"(?:street|st|road|rd|lane|nagar|colony|avenue|"
        r"apt|apartment|flat)\b",
        re.IGNORECASE,
    ),
]

_MAX_CONVERSATION_CHARS = 20_000
_MAX_SUGGESTION_CHARS = 500
_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because",
    "been", "being", "but", "can", "could", "from", "have", "her",
    "here", "him", "his", "how", "into", "its", "just", "like",
    "more", "most", "not", "our", "she", "should", "that", "the",
    "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "want", "was", "were", "what", "when",
    "where", "which", "while", "will", "with", "would", "you",
    "your", "i", "me", "my", "we", "us", "to", "of", "in", "on",
    "for", "at", "as", "is", "it", "be", "do", "does", "a", "an",
}


def _contains_obvious_secret(value):
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def _is_grounded_suggestion(item, conversation):
    words = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", item.casefold()))
    words = words - _STOP_WORDS
    if not words:
        return False

    conversation_words = set(
        re.findall(r"\b[a-zA-Z0-9]{3,}\b", conversation.casefold())
    ) - _STOP_WORDS

    return bool(words & conversation_words) and (
        len(words & conversation_words) / len(words) >= 0.5
    )


def suggest_memories(conversation):
    if (
        not isinstance(conversation, str)
        or not conversation.strip()
        or len(conversation) > _MAX_CONVERSATION_CHARS
        or _contains_obvious_secret(conversation)
    ):
        return []

    prompt = f"""Identify useful, factual long-term memories explicitly supported by this conversation.
Consider stable preferences, goals, and ongoing projects.
Do not infer, invent, or guess facts.
Exclude credentials, contact details, addresses, dates of birth,
medical information, and other sensitive personal information.
Return ONLY a JSON array of at most five short memory suggestions.
Return [] if nothing qualifies.

Conversation:
{conversation}
"""
    try:
        result = ask_groq(prompt)
        if not isinstance(result, str):
            return []

        start = result.find("[")
        end = result.rfind("]") + 1
        if start < 0 or end <= start:
            return []

        data = json.loads(result[start:end])
        if not isinstance(data, list):
            return []

        suggestions = []
        seen = set()

        for item in data:
            if not isinstance(item, str):
                continue

            item = item.strip()
            if (
                not item
                or len(item) > _MAX_SUGGESTION_CHARS
                or "\n" in item
                or _contains_obvious_secret(item)
                or not _is_grounded_suggestion(item, conversation)
            ):
                continue

            normalized = item.casefold()
            if normalized in seen:
                continue

            seen.add(normalized)
            suggestions.append(item)

            if len(suggestions) == 5:
                break

        return suggestions
    except Exception:
        return []
