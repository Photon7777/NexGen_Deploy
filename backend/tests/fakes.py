"""Stand-ins for the OpenAI model, so AI endpoints are tested without a key or network."""
import hashlib
import math
import re

from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from pydantic import Field


class FakeToolModel(GenericFakeChatModel):
    """Replays scripted replies (including tool calls) and records every prompt it sees."""

    seen: list = Field(default_factory=list)
    disable_streaming: bool = True  # the agent streams; tool-call-only replies have no text chunks

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class FakeFlashcardModel:
    """Answers with_structured_output(...).invoke(...) with numbered cards, or raises `error`."""

    def __init__(self, error: Exception | None = None):
        self.error = error

    def with_structured_output(self, schema):
        fake = self

        class _Runner:
            def invoke(self, prompt):
                if fake.error:
                    raise fake.error
                return schema(cards=[{"question": f"Q{i}", "answer": f"A{i}"} for i in range(1, 11)])

        return _Runner()


class FakeExtractionModel:
    """Answers with_structured_output(schema).invoke(prompt) with a fixed result (or raises), recording prompts."""

    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result, self.error, self.prompts = result, error, []

    def with_structured_output(self, schema, include_raw: bool = False):
        fake = self

        class _Runner:
            def invoke(self, prompt):
                fake.prompts.append(prompt)
                if fake.error:
                    raise fake.error
                parsed = schema.model_validate(fake.result)
                if not include_raw:
                    return parsed
                raw = AIMessage(content="", usage_metadata={"input_tokens": 900, "output_tokens": 100, "total_tokens": 1000})
                return {"raw": raw, "parsed": parsed, "parsing_error": None}

        return _Runner()


def fake_embed(texts: list[str]) -> list[list[float]]:
    """Bag-of-words vectors: texts that share words come out close, as real embeddings would for these tests."""
    vectors = []
    for text in texts:
        v = [0.0] * 1536
        for word in re.findall(r"[a-z]{3,}", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % 1536] += 1.0
        v[0] += 0.01  # never the zero vector, which has no cosine distance
        norm = math.sqrt(sum(x * x for x in v))
        vectors.append([x / norm for x in v])
    return vectors
