"""Multi-provider LLM router with per-provider timeout and graceful skipping of
providers that have no API key configured."""
import asyncio
import logging
import os

from providers.gemini import GeminiProvider
from providers.groq import GroqProvider
from providers.openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)
PROVIDER_TIMEOUT = float(os.getenv("AI_PROVIDER_TIMEOUT", "45"))


class AIModelRouter:
    def __init__(self):
        self.providers = []
        for name, factory in (
            ("groq", GroqProvider),
            ("gemini", GeminiProvider),
            ("openrouter", OpenRouterProvider),
        ):
            try:
                self.providers.append((name, factory()))
            except Exception as exc:  # missing key / bad config
                logger.warning("AI provider '%s' disabled: %s", name, exc)
        if not self.providers:
            logger.error("No AI providers configured; insights will be unavailable.")

    async def analyze_protein(self, pdb_id: str, chain_id: str, sequence: str):
        errors = []
        for name, provider in self.providers:
            try:
                logger.info("Trying AI provider: %s", name)
                result = await asyncio.wait_for(
                    provider.analyze(pdb_id, chain_id, sequence), timeout=PROVIDER_TIMEOUT
                )
                logger.info("AI provider succeeded: %s", name)
                return result
            except asyncio.TimeoutError:
                logger.warning("AI provider timed out: %s", name)
                errors.append(f"{name}: timeout")
            except Exception as exc:
                if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                    logger.warning("AI provider quota exhausted: %s", name)
                else:
                    logger.exception("AI provider failed: %s", name)
                errors.append(f"{name}: {type(exc).__name__}")
        raise RuntimeError("All AI providers failed: " + " | ".join(errors) if errors else "No AI providers configured")
