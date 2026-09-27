# ai/providers/openrouter.py

import json
import os
import re

from openai import AsyncOpenAI

from schemas import DetailedAIInsights
from prompts import SYSTEM_PROMPT


class OpenRouterProvider:

    def __init__(self):
        key = os.getenv("OPENROUTER_API_KEY")

        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not configured"
            )

        self.client = AsyncOpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
        )

    async def analyze(
        self,
        pdb_id: str,
        chain_id: str,
        sequence: str,
    ) -> DetailedAIInsights:

        prompt = (
            f"PDB ID: {pdb_id.upper()}\n"
            f"Chain: {chain_id}\n"
            f"Sequence:\n{sequence}"
        )

        response = await self.client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.2,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "detailed_ai_insights",
                    "schema": DetailedAIInsights.model_json_schema(),
                },
            },
        )

        content = response.choices[0].message.content

        if not content or not content.strip():
            raise ValueError("OpenRouter returned empty content.")

        # Extract the substring starting at the first '{' and ending at the last '}'
        start_idx = content.find("{")
        end_idx = content.rfind("}")

        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            raise ValueError(f"No JSON object detected in OpenRouter response: {content[:200]}")

        clean_json_str = content[start_idx : end_idx + 1]

        try:
            parsed_json = json.loads(clean_json_str)
            return DetailedAIInsights.model_validate(parsed_json)
        except Exception as err:
            raise ValueError(f"Failed to validate JSON from OpenRouter: {clean_json_str[:200]}") from err
