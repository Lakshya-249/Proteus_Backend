"""Lazy, failure-tolerant MongoDB access.

The API must keep working (without caching) when Mongo is down, so nothing here
connects at import time.
"""
import logging
import os
import time
from typing import Optional

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

_collection: Optional[Collection] = None
_next_retry = 0.0
_RETRY_SECONDS = 30.0


def get_insights_collection() -> Optional[Collection]:
    """Return the insights collection, or None if Mongo is unavailable."""
    global _collection, _next_retry
    if _collection is not None:
        return _collection
    if time.monotonic() < _next_retry:
        return None
    try:
        client = MongoClient(
            os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
            serverSelectionTimeoutMS=2000,
        )
        client.admin.command("ping")
        coll = client[os.getenv("MONGO_DB", "protein_insights_db")]["insights"]
        coll.create_index(
            [("pdb_id", ASCENDING), ("chain_id", ASCENDING)],
            unique=True,
            name="idx_pdb_chain_unique",
        )
        _collection = coll
        logger.info("MongoDB cache connected.")
        return _collection
    except PyMongoError as exc:
        _next_retry = time.monotonic() + _RETRY_SECONDS
        logger.warning("MongoDB unavailable, running without cache: %s", exc)
        return None
