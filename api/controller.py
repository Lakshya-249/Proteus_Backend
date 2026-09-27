import subprocess
import tempfile
from pathlib import Path
from traceback import print_stack

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing_extensions import Optional

from repository.model import get_cached_insights, upsert_insights
from schemas import DetailedAIInsights, InsightsRequest
from services.design import StructureDesignRequest, generate_pdb
from services.parse_dssp import parse_dssp

from services.protein_service import AIModelRouter
from services.structure import (
    ComplexDesignRequest,
    generate_complex_pdb,
)


router = APIRouter(prefix="/api")


class DSSPRequest(BaseModel):
    pdb_id: str
    chain_id: str


@router.post("/analysis/dssp")
def run_dssp(request: DSSPRequest):
    pdb_id = request.pdb_id.upper()
    chain_id = request.chain_id

    pdb_url = f"https://files.rcsb.org/download/{pdb_id}.pdb"

    try:
        import urllib.request

        with urllib.request.urlopen(pdb_url, timeout=15) as response:
            pdb_data = response.read()

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to download PDB structure: {exc}",
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        pdb_file = tmp_path / f"{pdb_id}.pdb"
        dssp_file = tmp_path / f"{pdb_id}.dssp"

        pdb_file.write_bytes(pdb_data)

        try:
            subprocess.run(
                [
                    "mkdssp",
                    "--output-format=dssp",
                    str(pdb_file),
                    str(dssp_file),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="mkdssp is not installed on the server.",
            )

        except subprocess.CalledProcessError as exc:
            raise HTTPException(
                status_code=500,
                detail=exc.stderr or "DSSP failed.",
            )

        residues = parse_dssp(
            dssp_file.read_text(),
            chain_id,
        )

    return {
        "method": "DSSP",
        "pdb_id": pdb_id,
        "chain_id": chain_id,
        "residues": residues,
    }

@router.post("/design/structure")
def design_structure(request: StructureDesignRequest):
    pdb = generate_pdb(
        request.sequence,
        request.structure,
    )

    return {
        "sequence": request.sequence.upper(),
        "structure": request.structure.upper(),
        "pdb": pdb,
    }





@router.post("/structure/generate")
def generate_structure(
    request: StructureDesignRequest,
):
    pdb = generate_pdb(
        request.sequence,
        request.structure,
    )

    return {
        "pdb": pdb,
    }


@router.post("/structure/generate-complex")
def generate_structure_complex(
    request: ComplexDesignRequest,
):
    pdb = generate_complex_pdb(
        request.chains
    )

    return {
        "pdb": pdb,
    }

service = AIModelRouter()

@router.post("/ai/insights", response_model=DetailedAIInsights)
async def get_insights(request: InsightsRequest):  # 1. Must be async def
    if not request.sequence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sequence is required to generate insights.",
        )

    chain_id = request.chainId or "A"

    try:
        # 2. Add 'await' right here:
        return await service.analyze_protein(
            pdb_id=request.pdbId,
            chain_id=chain_id,
            sequence=request.sequence,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI analysis failed: {exc}",
        )

class CachedInsightsRequest(BaseModel):
    pdbId: str
    chainId: Optional[str] = "A"
    sequence: Optional[str] = None
    forceRefresh: bool = False


@router.post(
    "/ai/insights/cached",
    response_model=DetailedAIInsights,
)
async def get_or_create_insights(
    request: CachedInsightsRequest,
):
    pdb_id = request.pdbId.upper()
    chain_id = (request.chainId or "A").upper()

    # 1. Cache hit
    if not request.forceRefresh:
        cached = get_cached_insights(
            pdb_id,
            chain_id,
        )

        if cached:
            return cached

    # 2. Cache miss requires sequence
    if not request.sequence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cache miss: sequence is required "
                "to generate new insights."
            ),
        )

    # 3. Generate using multi-model provider router
    try:
        fresh_insights = await service.analyze_protein(
            pdb_id=pdb_id,
            chain_id=chain_id,
            sequence=request.sequence,
        )

    except Exception:
        print(
            "All AI providers failed for PDB %s chain %s",
            pdb_id,
            chain_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis is temporarily unavailable.",
        )

    # 4. Cache successful result
    upsert_insights(
        pdb_id=pdb_id,
        chain_id=chain_id,
        sequence=request.sequence,
        insights=fresh_insights,
    )

    return fresh_insights
