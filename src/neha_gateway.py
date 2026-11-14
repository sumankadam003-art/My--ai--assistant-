import re
import logging

from groq_brain import ask_groq
from gemini_brain import ask_gemini
from memory_selector import select_relevant_memories, _STOP_WORDS
from cloud_memory import load_cloud_memories

logger = logging.getLogger(__name__)


class NehaGateway:
    """Central gateway for AI providers and local/cloud memory."""

    def __init__(self):
        self.providers = [
            ("groq", ask_groq),
            ("gemini", ask_gemini),
        ]

    @staticmethod
    def _words(text):
        # Use the same stopword policy as local memory selection so common
        # language words cannot dominate cloud-memory relevance scoring.
        tokens = set(re.findall(r"\\b[a-zA-Z0-9]+\\b", text.lower()))
        return tokens - _STOP_WORDS

    def _get_memories(self, prompt, user_id=None):
        try:
            memories = select_relevant_memories(prompt)
            if not isinstance(memories, list):
                memories = []
            else:
                memories = [
                    fact.strip()
                    for fact in memories
                    if isinstance(fact, str) and fact.strip()
                ]
        except Exception as error:
            logger.warning(
                "Local memory retrieval failed (%s). Continuing without local memories.",
                type(error).__name__,
            )
            memories = []

        # Cloud memory is accessed only by Neha's trusted backend identity.
        if not user_id:
            return memories[:10]

        try:
            records = load_cloud_memories(user_id)
            if records is None:
                return memories
            query_words = self._words(prompt)
            if not query_words:
                return memories[:10]

            scored = []
            for record in records:
                if not isinstance(record, dict):
                    continue

                fact = record.get("memory")
                if not isinstance(fact, str) or not fact.strip():
                    continue

                fact_words = self._words(fact)
                overlap = query_words & fact_words
                if overlap:
                    score = len(overlap) / len(query_words)
                    scored.append((score, fact.strip()))

            scored.sort(key=lambda item: item[0], reverse=True)

            for _, fact in scored[:5]:
                if fact not in memories:
                    memories.append(fact)

        except Exception as error:
            # Keep local memory available if cloud access fails.
            logger.warning(
                "Cloud memory retrieval failed (%s). Using local memories.",
                type(error).__name__,
            )

        return memories[:10]

    def ask(
        self,
        prompt,
        history=None,
        user_id=None,
    ):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string.")

        if history is None:
            history = []
        elif not isinstance(history, list):
            raise ValueError("History must be a list.")
        else:
            history = [
                item for item in history
                if isinstance(item, dict)
                and item.get("role") in ("user", "assistant")
                and isinstance(item.get("content"), str)
                and item["content"].strip()
            ][-40:]

        memories = self._get_memories(
            prompt,
            user_id=user_id,
        )

        context = (
            "\\nNEHA'S RESPONSE RULES:\\n"
            "- Never invent personal memories, places, events, or conversations.\\n"
            "- Never present guesses as facts or saved memories.\\n"
            "- If you do not know a detail, say so honestly.\\n"
            "- Be warm, respectful, friendly, and concise.\\n"
        )

        if memories:
            context += (
                "\\nRELEVANT SAVED MEMORIES:\\n"
                + "\\n".join(f"- {fact}" for fact in memories)
                + "\\nUse these only when relevant.\\n"
            )

        shared_prompt = context + "\\nUser message:\\n" + prompt

        for name, provider in self.providers:
            try:
                answer = provider(shared_prompt, history)

                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("Provider returned an empty or invalid response.")

                return answer.strip()

            except Exception as error:
                print(
                    f"Neha: {name} failed "
                    f"({type(error).__name__}); trying the next provider."
                )

        return (
            "I'm temporarily unable to reach my online AI providers. "
            "Your local memories remain saved."
        )
