from datetime import datetime, timezone
from typing import Optional

from schemas import DetailedAIInsights

from .database import insights_collection

def get_cached_insights(pdb_id: str, chain_id: str) -> Optional[DetailedAIInsights]:
    doc = insights_collection.find_one(
        {"pdb_id": pdb_id.upper(), "chain_id": chain_id.upper()}
    )
    if doc and "insights" in doc:
        return DetailedAIInsights.model_validate(doc["insights"])
    return None


def upsert_insights(
    pdb_id: str,
    chain_id: str,
    sequence: Optional[str],
    insights: DetailedAIInsights,
) -> None:
    now = datetime.now(timezone.utc)
    norm_pdb = pdb_id.upper()
    norm_chain = chain_id.upper()

    update_fields = {
        "insights": insights.model_dump(),
        "updated_at": now,
    }
    if sequence:
        update_fields["sequence"] = sequence

    insights_collection.update_one(
        {"pdb_id": norm_pdb, "chain_id": norm_chain},
        {
            "$set": update_fields,
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,  # Inserts if missing, updates if exists
    )
