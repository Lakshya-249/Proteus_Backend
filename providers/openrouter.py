import json
import logging
import os

from openai import AsyncOpenAI

from prompts import SYSTEM_PROMPT
from schemas import DetailedAIInsights

logger = logging.getLogger(__name__)


class OpenRouterProvider:
    def __init__(self):
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        self.client = AsyncOpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")

    async def analyze(self, pdb_id: str, chain_id: str, sequence: str) -> DetailedAIInsights:
        ctx = f"pdb={pdb_id.upper()} chain={chain_id} seq_len={len(sequence)}"
        logger.info("OpenRouter: requesting analysis (%s)", ctx)

        prompt = f"PDB ID: {pdb_id.upper()}\nChain: {chain_id}\nSequence:\n{sequence}"

        try:
            response = await self.client.chat.completions.create(
                model="openrouter/free",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
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
        except Exception:
            logger.error("OpenRouter: API call failed (%s)", ctx, exc_info=True)
            raise

        content = response.choices[0].message.content

        if not content or not content.strip():
            logger.error("OpenRouter: empty content (%s)", ctx)
            raise ValueError("OpenRouter returned empty content.")

        start_idx = content.find("{")
        end_idx = content.rfind("}")

        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            logger.error("OpenRouter: no JSON object found (%s) raw=%r", ctx, content[:300])
            raise ValueError(f"No JSON object detected in OpenRouter response: {content[:200]}")

        clean_json_str = content[start_idx : end_idx + 1]

        try:
            parsed_json = json.loads(clean_json_str)
            result = DetailedAIInsights.model_validate(parsed_json)
        except Exception:
            logger.error(
                "OpenRouter: JSON parse/validation failed (%s) raw=%r",
                ctx, clean_json_str[:300], exc_info=True,
            )
            raise ValueError(f"Failed to validate JSON from OpenRouter: {clean_json_str[:200]}")

        logger.info("OpenRouter: analysis succeeded (%s)", ctx)
        return result
