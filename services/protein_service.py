# ai/router.py

import logging

from providers.gemini import GeminiProvider
from providers.groq import GroqProvider
from providers.openrouter import OpenRouterProvider




logger = logging.getLogger(__name__)


class AIModelRouter:

    def __init__(self):

        self.providers = [
            ("groq", GroqProvider()),
            ("gemini", GeminiProvider()),
            ("openrouter", OpenRouterProvider()),
        ]

    async def analyze_protein(
        self,
        pdb_id: str,
        chain_id: str,
        sequence: str,
    ):

        errors = []

        for name, provider in self.providers:

            try:

                logger.info(
                    "Trying AI provider: %s",
                    name,
                )

                try:
                    result = await provider.analyze(
                        pdb_id,
                        chain_id,
                        sequence,
                    )

                    return result

                except Exception as e:
                    provider_name = provider.__class__.__name__

                    if "RESOURCE_EXHAUSTED" in str(e):
                        logger.warning(
                            "Provider quota exhausted: %s",
                            provider_name,
                        )
                        continue

                    logger.exception(
                        "Provider failed: %s",
                        provider_name,
                    )
                    continue

                logger.info(
                    "AI provider succeeded: %s",
                    name,
                )

                return result

            except Exception as exc:

                logger.exception(
                    "AI provider failed: %s",
                    name,
                )

                errors.append(
                    f"{name}: {exc}"
                )

        raise RuntimeError(
            "All AI providers failed: "
            + " | ".join(errors)
        )
