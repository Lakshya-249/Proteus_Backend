import os
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection

MONGO_URI = os.getenv("MONGO_URI", "mongodb://root:password@localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["protein_insights_db"]
insights_collection: Collection = db["insights"]

# Ensure unique index on (pdb_id, chain_id)
insights_collection.create_index(
    [("pdb_id", ASCENDING), ("chain_id", ASCENDING)],
    unique=True,
    name="idx_pdb_chain_unique",
)
