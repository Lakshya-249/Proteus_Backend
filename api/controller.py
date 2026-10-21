import hashlib
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from repository.model import get_cached_insights, upsert_insights
from schemas import DetailedAIInsights, InsightsRequest
from services.parse_dssp import parse_dssp
from services.protein_service import AIModelRouter
from services.ratelimit import limiter
from services.rcsb import (
    CHAIN_RE,
    LRU,
    fetch_chain_sequence,
    fetch_structure_file,
    validate_ids,
)
from services.structure import (
    ComplexDesignRequest,
    StructureDesignRequest,
    generate_complex_report,
    generate_pdb_report,
)
from services.validate_insights import sanitize_insights

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
DSSP_TIMEOUT = int(os.getenv("DSSP_TIMEOUT", "60"))

limit_ai = limiter("RATE_LIMIT_AI", 10, "AI")
limit_dssp = limiter("RATE_LIMIT_DSSP", 30, "analysis")
limit_design = limiter("RATE_LIMIT_DESIGN", 60, "design")
limit_predict = limiter("RATE_LIMIT_PREDICT", 5, "prediction")

_dssp_cache = LRU(32)  # sha256(structure) -> mkdssp text output


# ---------------------------------------------------------------- health
@router.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------- DSSP
class DSSPRequest(BaseModel):
    pdb_id: str
    chain_id: str


def _strip_ss_records(text: str) -> str:
    # DSSP recomputes secondary structure; header HELIX/SHEET records only risk parser errors.
    return "\n".join(l for l in text.splitlines() if not l.startswith(("HELIX", "SHEET")))


def _dssp_output(data: bytes, ext: str) -> str:
    key = hashlib.sha256(data).hexdigest() + ext
    cached = _dssp_cache.get(key)
    if cached:
        return cached
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input.{ext}"
        out = Path(tmp) / "output.dssp"
        src.write_bytes(data)
        try:
            subprocess.run(
                ["mkdssp", "--output-format=dssp", str(src), str(out)],
                check=True, capture_output=True, text=True, timeout=DSSP_TIMEOUT,
            )
        except FileNotFoundError:
            raise HTTPException(500, "mkdssp is not installed on the server.")
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "DSSP processing timed out.")
        except subprocess.CalledProcessError as exc:
            logger.warning("mkdssp failed: %s", (exc.stderr or "")[:500])
            raise HTTPException(422, "DSSP could not process this structure.")
        text = out.read_text()
    _dssp_cache.put(key, text)
    return text


def _validated_chain(chain_id: str) -> str:
    chain_id = chain_id.strip()
    if not CHAIN_RE.match(chain_id):
        raise HTTPException(400, "Invalid chain ID.")
    return chain_id


@router.post("/analysis/dssp/file", dependencies=[Depends(limit_dssp)])
def run_dssp_file(file: UploadFile = File(...), chain_id: str = Form(...)):
    chain_id = _validated_chain(chain_id)
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdb"):
        raise HTTPException(400, "Please upload a .pdb file.")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB).")
    text = _strip_ss_records(data.decode("utf-8", errors="ignore"))

    residues = parse_dssp(_dssp_output(text.encode(), "pdb"), chain_id)
    return {"method": "DSSP", "filename": filename, "chain_id": chain_id, "residues": residues}


@router.post("/analysis/dssp", dependencies=[Depends(limit_dssp)])
def run_dssp(request: DSSPRequest):
    pdb_id, chain_id = validate_ids(request.pdb_id, request.chain_id)
    data, ext = fetch_structure_file(pdb_id)
    residues = parse_dssp(_dssp_output(data, ext), chain_id)
    if not residues:
        raise HTTPException(404, f"No DSSP residues found for chain {chain_id} of {pdb_id}.")
    return {"method": "DSSP", "pdb_id": pdb_id, "chain_id": chain_id, "residues": residues}


# ---------------------------------------------------------------- design
@router.post("/design/structure", dependencies=[Depends(limit_design)])
def design_structure(request: StructureDesignRequest):
    pdb, warnings = generate_pdb_report(request.sequence, request.structure)
    return {
        "sequence": request.sequence.upper(),
        "structure": request.structure.upper(),
        "pdb": pdb,
        "warnings": warnings,
    }


@router.post("/structure/generate", dependencies=[Depends(limit_design)])
def generate_structure(request: StructureDesignRequest):
    pdb, warnings = generate_pdb_report(request.sequence, request.structure)
    return {"pdb": pdb, "warnings": warnings}


@router.post("/structure/generate-complex", dependencies=[Depends(limit_design)])
def generate_structure_complex(request: ComplexDesignRequest):
    pdb, warnings = generate_complex_report(request.chains)
    return {"pdb": pdb, "warnings": warnings}


class PredictRequest(BaseModel):
    sequence: str


@router.post("/structure/predict", dependencies=[Depends(limit_predict)])
async def predict_structure(request: PredictRequest):
    """Real fold prediction via the public ESM Metagenomic Atlas (ESMFold) API.
    The B-factor column of the returned PDB holds per-residue confidence (pLDDT)."""
    seq = "".join(request.sequence.split()).upper()
    if not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+", seq):
        raise HTTPException(400, "Sequence may only contain the 20 standard amino acids.")
    if not 16 <= len(seq) <= 400:
        raise HTTPException(400, "ESMFold supports sequences of 16-400 residues.")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.esmatlas.com/foldSequence/v1/pdb/",
                content=seq,
                headers={"Content-Type": "text/plain"},
            )
    except httpx.HTTPError as exc:
        logger.warning("ESMFold request failed: %s", exc)
        raise HTTPException(502, "Structure prediction service is unreachable.")
    if resp.status_code != 200 or "ATOM" not in resp.text:
        logger.warning("ESMFold returned %s", resp.status_code)
        raise HTTPException(502, "Structure prediction service returned an error.")
    return {"pdb": resp.text, "source": "ESMFold", "confidence": "B-factor column = pLDDT"}


# ---------------------------------------------------------------- AI insights
service = AIModelRouter()


@router.post("/ai/insights", response_model=DetailedAIInsights, dependencies=[Depends(limit_ai)])
async def get_insights(request: InsightsRequest):
    pdb_id, chain_id = validate_ids(request.pdbId, request.chainId or "A")
    sequence = await fetch_chain_sequence(pdb_id, chain_id)  # never trust the client sequence
    try:
        raw = await service.analyze_protein(pdb_id=pdb_id, chain_id=chain_id, sequence=sequence)
    except Exception:
        logger.exception("AI analysis failed for %s/%s", pdb_id, chain_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI analysis failed.")
    cleaned, dropped = sanitize_insights(raw, sequence, chain_id)
    if dropped:
        logger.info("Dropped/repaired %d inconsistent AI items for %s/%s", dropped, pdb_id, chain_id)
    return cleaned


class CachedInsightsRequest(BaseModel):
    pdbId: str
    chainId: Optional[str] = "A"
    sequence: Optional[str] = None  # accepted for backwards compatibility, ignored
    forceRefresh: bool = False


@router.post("/ai/insights/cached", response_model=DetailedAIInsights, dependencies=[Depends(limit_ai)])
async def get_or_create_insights(request: CachedInsightsRequest):
    pdb_id, chain_id = validate_ids(request.pdbId, request.chainId or "A")
    chain_id = chain_id.upper()

    if not request.forceRefresh:
        cached = await run_in_threadpool(get_cached_insights, pdb_id, chain_id)
        if cached:
            return cached

    sequence = await fetch_chain_sequence(pdb_id, chain_id)
    try:
        raw = await service.analyze_protein(pdb_id=pdb_id, chain_id=chain_id, sequence=sequence)
    except Exception:
        logger.exception("All AI providers failed for %s/%s", pdb_id, chain_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI analysis is temporarily unavailable.")

    cleaned, dropped = sanitize_insights(raw, sequence, chain_id)
    if dropped:
        logger.info("Dropped/repaired %d inconsistent AI items for %s/%s", dropped, pdb_id, chain_id)
    await run_in_threadpool(upsert_insights, pdb_id, chain_id, sequence, cleaned)
    return cleaned
