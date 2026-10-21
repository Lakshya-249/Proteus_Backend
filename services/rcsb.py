"""Server-side RCSB lookups (authoritative source for sequences and coordinate files)."""
import logging
import re
import threading
from collections import OrderedDict

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

PDB_ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
CHAIN_RE = re.compile(r"^[A-Za-z0-9]{1,4}$")
MAX_AI_SEQUENCE = 2000

_GRAPHQL = "https://data.rcsb.org/graphql"
_QUERY = """
query($id: String!) {
  entry(entry_id: $id) {
    polymer_entities {
      entity_poly { pdbx_seq_one_letter_code_can rcsb_entity_polymer_type }
      rcsb_polymer_entity_container_identifiers { auth_asym_ids asym_ids }
    }
  }
}"""


def validate_ids(pdb_id: str, chain_id: str) -> tuple[str, str]:
    pdb_id, chain_id = pdb_id.strip().upper(), chain_id.strip()
    if not PDB_ID_RE.match(pdb_id):
        raise HTTPException(400, "Invalid PDB ID (expected 4 characters, e.g. 1A3N).")
    if not CHAIN_RE.match(chain_id):
        raise HTTPException(400, "Invalid chain ID.")
    return pdb_id, chain_id


class LRU:
    def __init__(self, size: int):
        self.size, self._d, self._lock = size, OrderedDict(), threading.Lock()

    def get(self, key):
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                return self._d[key]
        return None

    def put(self, key, value):
        with self._lock:
            self._d[key] = value
            self._d.move_to_end(key)
            while len(self._d) > self.size:
                self._d.popitem(last=False)


_seq_cache = LRU(256)
_file_cache = LRU(16)


async def fetch_chain_sequence(pdb_id: str, chain_id: str) -> str:
    key = (pdb_id, chain_id)
    hit = _seq_cache.get(key)
    if hit:
        return hit
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_GRAPHQL, json={"query": _QUERY, "variables": {"id": pdb_id}})
            resp.raise_for_status()
            entry = (resp.json().get("data") or {}).get("entry")
    except httpx.HTTPError as exc:
        logger.warning("RCSB lookup failed for %s: %s", pdb_id, exc)
        raise HTTPException(502, "Could not reach RCSB to verify the sequence.")
    if not entry:
        raise HTTPException(404, f"PDB entry {pdb_id} not found.")

    for ent in entry.get("polymer_entities") or []:
        ids = ent["rcsb_polymer_entity_container_identifiers"]
        chains = (ids.get("auth_asym_ids") or []) + (ids.get("asym_ids") or [])
        if chain_id in chains:
            poly = ent["entity_poly"]
            if (poly.get("rcsb_entity_polymer_type") or "Protein") != "Protein":
                raise HTTPException(422, f"Chain {chain_id} is not a protein chain.")
            seq = "".join((poly["pdbx_seq_one_letter_code_can"] or "").split()).upper()
            if not seq:
                break
            if len(seq) > MAX_AI_SEQUENCE:
                raise HTTPException(422, f"Chain is too long for AI analysis (>{MAX_AI_SEQUENCE} residues).")
            _seq_cache.put(key, seq)
            return seq
    raise HTTPException(404, f"Chain {chain_id} not found in {pdb_id}.")


def fetch_structure_file(pdb_id: str) -> tuple[bytes, str]:
    """Return (bytes, extension). Falls back to mmCIF for entries without a .pdb file."""
    hit = _file_cache.get(pdb_id)
    if hit:
        return hit
    last_status = None
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for ext in ("pdb", "cif"):
            try:
                resp = client.get(f"https://files.rcsb.org/download/{pdb_id}.{ext}")
            except httpx.HTTPError as exc:
                raise HTTPException(502, f"Unable to download structure: {exc}")
            if resp.status_code == 200:
                _file_cache.put(pdb_id, (resp.content, ext))
                return resp.content, ext
            last_status = resp.status_code
    if last_status == 404:
        raise HTTPException(404, f"PDB entry {pdb_id} not found.")
    raise HTTPException(502, f"RCSB returned status {last_status}.")
