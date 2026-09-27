# ai/providers/gemini.py

import os

from google import genai
from google.genai import types

from schemas import DetailedAIInsights
from prompts import SYSTEM_PROMPT


class GeminiProvider:

    def __init__(self):
        key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )

        if not key:
            raise RuntimeError("Gemini API key not configured")

        self.client = genai.Client(api_key=key)

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

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=DetailedAIInsights,  # Works natively now
                temperature=0.2,
                max_output_tokens=4096,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
        )

        if response.parsed is None:
            raise RuntimeError(
                "Gemini returned invalid structured output"
            )

        return response.parsed
