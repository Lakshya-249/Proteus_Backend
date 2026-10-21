import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo.errors import PyMongoError

from prompts import PROMPT_VERSION
from schemas import DetailedAIInsights

from .database import get_insights_collection

logger = logging.getLogger(__name__)
CACHE_TTL_DAYS = int(os.getenv("AI_CACHE_TTL_DAYS", "30"))


def get_cached_insights(pdb_id: str, chain_id: str) -> Optional[DetailedAIInsights]:
    coll = get_insights_collection()
    if coll is None:
        return None
    try:
        doc = coll.find_one({"pdb_id": pdb_id.upper(), "chain_id": chain_id.upper()})
        if not doc or "insights" not in doc:
            return None
        if doc.get("prompt_version") != PROMPT_VERSION:
            return None  # produced by an older prompt: regenerate
        updated = doc.get("updated_at")
        if updated is not None:
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - updated > timedelta(days=CACHE_TTL_DAYS):
                return None
        return DetailedAIInsights.model_validate(doc["insights"])
    except (PyMongoError, ValueError):
        logger.warning("Cache read failed for %s/%s", pdb_id, chain_id, exc_info=True)
        return None


def upsert_insights(
    pdb_id: str, chain_id: str, sequence: Optional[str], insights: DetailedAIInsights
) -> None:
    coll = get_insights_collection()
    if coll is None:
        return
    now = datetime.now(timezone.utc)
    fields = {
        "insights": insights.model_dump(),
        "updated_at": now,
        "prompt_version": PROMPT_VERSION,
    }
    if sequence:
        fields["sequence"] = sequence
    try:
        coll.update_one(
            {"pdb_id": pdb_id.upper(), "chain_id": chain_id.upper()},
            {"$set": fields, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except PyMongoError:
        logger.warning("Cache write failed for %s/%s", pdb_id, chain_id, exc_info=True)
