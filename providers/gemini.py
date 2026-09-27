import logging
import os

from google import genai
from google.genai import types

from prompts import SYSTEM_PROMPT
from schemas import DetailedAIInsights

logger = logging.getLogger(__name__)


class GeminiProvider:
    def __init__(self):
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Gemini API key not configured")
        self.client = genai.Client(api_key=key)

    async def analyze(self, pdb_id: str, chain_id: str, sequence: str) -> DetailedAIInsights:
        ctx = f"pdb={pdb_id.upper()} chain={chain_id} seq_len={len(sequence)}"
        logger.info("Gemini: requesting analysis (%s)", ctx)

        prompt = f"PDB ID: {pdb_id.upper()}\nChain: {chain_id}\nSequence:\n{sequence}"

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=DetailedAIInsights,
                    temperature=0.2,
                    max_output_tokens=4096,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception:
            logger.error("Gemini: API call failed (%s)", ctx, exc_info=True)
            raise

        if response.parsed is None:
            candidate = response.candidates[0] if response.candidates else None
            finish_reason = getattr(candidate, "finish_reason", "unknown")
            safety = getattr(candidate, "safety_ratings", None)
            raw_text = getattr(response, "text", None)
            logger.error(
                "Gemini: no parsed output (%s) finish_reason=%s safety=%s raw=%r",
                ctx, finish_reason, safety, (raw_text or "")[:300],
            )
            raise RuntimeError(
                f"Gemini returned invalid structured output (finish_reason={finish_reason})"
            )

        usage = getattr(response, "usage_metadata", None)
        logger.info(
            "Gemini: analysis succeeded (%s) tokens=%s",
            ctx, getattr(usage, "total_token_count", "n/a"),
        )
        return response.parsed
