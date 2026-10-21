"""Sanity-check LLM output against the real sequence before it is shown or cached."""
import re

from schemas import DetailedAIInsights, DomainRegion, FunctionalSite, MutationVariant

_MUT_RE = re.compile(r"^(?:p\.)?([A-Z])(\d+)([A-Z])$")
_AA = set("ACDEFGHIKLMNPQRSTVWY")


def sanitize_insights(
    insights: DetailedAIInsights, sequence: str, chain_id: str
) -> tuple[DetailedAIInsights, int]:
    """Return (cleaned insights, number of dropped/repaired items)."""
    n = len(sequence)
    dropped = 0

    domains: list[DomainRegion] = []
    for d in insights.domains:
        start, end = sorted((d.start, d.end))
        start, end = max(1, start), min(n, end)
        if start > end:
            dropped += 1
            continue
        domains.append(d.model_copy(update={"start": start, "end": end, "chain": chain_id}))

    sites: list[FunctionalSite] = []
    for s in insights.functionalSites:
        residues = sorted({r for r in s.residues if 1 <= r <= n})
        if not residues:
            dropped += 1
            continue
        if len(residues) != len(s.residues):
            dropped += 1
        score = s.druggabilityScore
        if score is not None:
            score = min(1.0, max(0.0, score))
        sites.append(
            s.model_copy(update={"residues": residues, "chain": chain_id, "druggabilityScore": score})
        )

    muts: list[MutationVariant] = []
    for m in insights.pathologyVariants:
        match = _MUT_RE.match(m.mutation.strip().upper())
        if not match:
            dropped += 1
            continue
        wt, pos, mut = match.group(1), int(match.group(2)), match.group(3)
        if (
            not (1 <= pos <= n)
            or sequence[pos - 1] != wt  # wild-type must match the real residue
            or mut == wt
            or mut not in _AA
        ):
            dropped += 1
            continue
        muts.append(
            m.model_copy(update={"mutation": f"{wt}{pos}{mut}", "resi": pos, "chain": chain_id})
        )

    cleaned = DetailedAIInsights(
        summary=insights.summary,
        domains=domains,
        functionalSites=sites,
        pathologyVariants=muts,
    )
    return cleaned, dropped
