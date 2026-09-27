import os
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------------------------------------------------------
# Schemas — field names match the frontend's DetailedAIInsights exactly,
# so Gemini's parsed JSON can be returned as-is with no translation layer.
# -------------------------------------------------------------------------

class FunctionalSite(BaseModel):
    label: str = Field(description="e.g. 'ATP-Binding Loop', 'Catalytic Triad'")
    chain: str = Field(description="Chain identifier, e.g. 'A'")
    residues: List[int] = Field(description="Residue numbers involved in this site")
    description: str = Field(description="1-2 sentence description of the site and its chemistry")
    chemicalRole: str = Field(description="Short phrase, e.g. 'Proton donor / nucleophile'")
    druggabilityScore: Optional[float] = Field(
        default=None, description="Estimated pocket druggability from 0.0 to 1.0"
    )


class MutationVariant(BaseModel):
    mutation: str = Field(description="Standard notation, e.g. 'R45K'")
    resi: int = Field(description="Residue number that is mutated")
    impact: str = Field(description="Direct physical/molecular cause, e.g. 'Destroys salt bridge with Asp104'")
    chain: str = Field(description="Chain identifier this mutation applies to")
    clinicalSignificance: str = Field(description="Short human-readable significance, e.g. 'Likely pathogenic'")
    predictedDdg: Optional[float] = Field(
        default=None, description="Estimated folding free-energy change in kcal/mol (negative = destabilizing)"
    )
    phenotype: Optional[
        Literal["neutral", "destabilizing", "pathogenic_loss_of_function", "hyperactive"]
    ] = None


class DomainRegion(BaseModel):
    name: str = Field(description="Domain or fold-region name")
    start: int = Field(description="First residue number of the domain")
    end: int = Field(description="Last residue number of the domain")
    chain: str = Field(description="Chain identifier this domain belongs to")
    function: str = Field(description="1 sentence on what this domain does")
    type: Literal["catalytic", "binding", "structural"]


class DetailedAIInsights(BaseModel):
    summary: str = Field(description="2-4 short paragraphs: overall fold, function, notable features")
    domains: List[DomainRegion]
    functionalSites: List[FunctionalSite]
    pathologyVariants: List[MutationVariant]


class InsightsRequest(BaseModel):
    pdbId: str
    chainId: Optional[str] = None
    sequence: Optional[str] = None
