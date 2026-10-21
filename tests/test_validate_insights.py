from schemas import DetailedAIInsights, DomainRegion, FunctionalSite, MutationVariant
from services.validate_insights import sanitize_insights

SEQ = "MKTAYIAKQR"  # pos1=M pos2=K pos3=T ...


def _mut(mutation, resi):
    return MutationVariant(
        mutation=mutation, resi=resi, impact="x", chain="Z", clinicalSignificance="x"
    )


def test_wrong_wildtype_and_out_of_range_mutations_are_dropped():
    ins = DetailedAIInsights(
        summary="s",
        domains=[DomainRegion(name="d", start=5, end=999, chain="Q", function="f", type="binding")],
        functionalSites=[
            FunctionalSite(label="l", chain="Q", residues=[2, 3, 500], description="d",
                           chemicalRole="r", druggabilityScore=7.0),
            FunctionalSite(label="bad", chain="Q", residues=[900], description="d", chemicalRole="r"),
        ],
        pathologyVariants=[_mut("K2R", 2), _mut("R2K", 2), _mut("T3T", 3), _mut("A400G", 400), _mut("junk", 1)],
    )
    out, dropped = sanitize_insights(ins, SEQ, "A")
    assert [m.mutation for m in out.pathologyVariants] == ["K2R"]
    assert out.domains[0].end == len(SEQ) and out.domains[0].chain == "A"
    assert len(out.functionalSites) == 1 and out.functionalSites[0].residues == [2, 3]
    assert out.functionalSites[0].druggabilityScore == 1.0
    assert dropped >= 5
