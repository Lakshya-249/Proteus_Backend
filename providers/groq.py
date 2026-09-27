import os
from typing import Any, Dict
from groq import AsyncGroq
from prompts import SYSTEM_PROMPT
from schemas import DetailedAIInsights


def make_groq_strict_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively adapts a Pydantic JSON schema for Groq strict
    structured outputs.

    Groq requires:
    - additionalProperties: false on every object
    - every property to be listed in required
    """
    schema = schema.copy()

    if schema.get("type") == "object":
        schema["additionalProperties"] = False

        # Groq strict mode requires EVERY property to be required.
        properties = schema.get("properties", {})

        if properties:
            schema["required"] = list(properties.keys())

        # Recursively process nested properties.
        schema["properties"] = {
            key: make_groq_strict_schema(value)
            for key, value in properties.items()
        }

    if "items" in schema:
        schema["items"] = make_groq_strict_schema(schema["items"])

    if "$defs" in schema:
        schema["$defs"] = {
            key: make_groq_strict_schema(value)
            for key, value in schema["$defs"].items()
        }

    return schema


class GroqProvider:
    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("GROQ_API_KEY")
        self.client = AsyncGroq(api_key=key)

    async def analyze(self, pdb_id: str, chain_id: str, sequence: str) -> DetailedAIInsights:
        prompt = (
            f"PDB ID: {pdb_id.upper()}\n"
            f"Chain: {chain_id}\n"
            f"Sequence:\n{sequence}\n"
        )

        # Generate standard schema and strictly adapt it for Groq only
        base_schema = DetailedAIInsights.model_json_schema()
        groq_schema = make_groq_strict_schema(base_schema)

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
        )

        raw_json = response.choices[0].message.content
        return DetailedAIInsights.model_validate_json(raw_json)
