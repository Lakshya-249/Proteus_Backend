import logging
import os
from typing import Any, Dict

from groq import AsyncGroq

from prompts import SYSTEM_PROMPT
from schemas import DetailedAIInsights

logger = logging.getLogger(__name__)


def make_groq_strict_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """..."""  # unchanged
    schema = schema.copy()
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        properties = schema.get("properties", {})
        if properties:
            schema["required"] = list(properties.keys())
        schema["properties"] = {
            key: make_groq_strict_schema(value) for key, value in properties.items()
        }
    if "items" in schema:
        schema["items"] = make_groq_strict_schema(schema["items"])
    if "$defs" in schema:
        schema["$defs"] = {
            key: make_groq_strict_schema(value) for key, value in schema["$defs"].items()
        }
    return schema


class GroqProvider:
    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        self.client = AsyncGroq(api_key=key)

    async def analyze(self, pdb_id: str, chain_id: str, sequence: str) -> DetailedAIInsights:
        ctx = f"pdb={pdb_id.upper()} chain={chain_id} seq_len={len(sequence)}"
        logger.info("Groq: requesting analysis (%s)", ctx)

        prompt = f"PDB ID: {pdb_id.upper()}\nChain: {chain_id}\nSequence:\n{sequence}\n"
        base_schema = DetailedAIInsights.model_json_schema()
        groq_schema = make_groq_strict_schema(base_schema)

        try:
            response = await self.client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "detailed_ai_insights",
                        "strict": True,
                        "schema": groq_schema,
                    },
                },
                temperature=0.2,
                max_completion_tokens=8192,
                reasoning_effort="low",
                reasoning_format="hidden",
            )
        except Exception:
            logger.error("Groq: API call failed (%s)", ctx, exc_info=True)
            raise

        choice = response.choices[0]
        raw_json = choice.message.content

        if not raw_json:
            logger.error(
                "Groq: empty completion (%s) finish_reason=%s",
                ctx, choice.finish_reason,
            )
            raise ValueError(f"Groq returned empty content, finish_reason={choice.finish_reason}")

        try:
            result = DetailedAIInsights.model_validate_json(raw_json)
        except Exception:
            logger.error(
                "Groq: schema validation failed (%s) raw=%r",
                ctx, raw_json[:300], exc_info=True,
            )
            raise

        usage = getattr(response, "usage", None)
        logger.info(
            "Groq: analysis succeeded (%s) tokens=%s",
            ctx, getattr(usage, "total_tokens", "n/a"),
        )
        return result
