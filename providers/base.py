# ai/providers/base.py

from abc import ABC, abstractmethod

from ..schemas import DetailedAIInsights


class AIProvider(ABC):

    @abstractmethod
    async def analyze(
        self,
        pdb_id: str,
        chain_id: str,
        sequence: str,
    ) -> DetailedAIInsights:
        pass
