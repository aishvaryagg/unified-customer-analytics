"""Thin wrapper around the Anthropic SDK for structured (Pydantic) responses."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5"


class LLMRefusal(RuntimeError):
    """Claude (and its fallback) declined the request."""


class LLMError(RuntimeError):
    """The response could not be used (cut off, or not valid for the schema)."""


class ClaudeLLM:
    """Calls Claude with structured outputs.

    - Responses are parsed straight into a Pydantic model (``output_format``).
    - ``fallbacks="default"`` re-runs a request Claude declines on Anthropic's
      recommended fallback model, server-side.
    - The system prompt (instructions + table catalog) is stable, so it is cached.
    """

    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, model: str = DEFAULT_MODEL, client=None, max_tokens: int = 16000):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def structured(self, system: str, user: str, output_type: type[T], effort: str = "high") -> T:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=output_type,
            output_config={"effort": effort},
            betas=[self.FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMRefusal(getattr(details, "explanation", None) or "The request was declined.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The response was cut off before it finished.")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise LLMError("The response did not match the expected format.")
        return parsed
