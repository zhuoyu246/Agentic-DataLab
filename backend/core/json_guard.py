from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class GuardResult(Generic[T]):
    ok: bool
    data: T | None = None
    raw_json: str | None = None
    error: str | None = None


class JsonDFAExtractor:
    """
    Deterministic JSON object/array extractor.

    It scans character-by-character with string/escape state, so markdown text around
    the payload cannot trick a naive regex into accepting malformed JSON.
    """

    @staticmethod
    def extract(text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty model response")
        start = -1
        opener = ""
        closer = ""
        for idx, char in enumerate(text):
            if char == "{":
                start, opener, closer = idx, "{", "}"
                break
            if char == "[":
                start, opener, closer = idx, "[", "]"
                break
        if start < 0:
            raise ValueError("no JSON object or array found")

        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            char = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
        raise ValueError("unterminated JSON payload")


class JsonGuard:
    def validate(self, text: str, schema: type[T]) -> GuardResult[T]:
        try:
            raw = JsonDFAExtractor.extract(text)
            payload = json.loads(raw)
            data = schema.model_validate(payload)
            return GuardResult(ok=True, data=data, raw_json=raw)
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            return GuardResult(ok=False, error=str(exc))

