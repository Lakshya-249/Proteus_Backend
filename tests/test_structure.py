"""Run with: uv run pytest"""
import pytest
from fastapi import HTTPException

from services import structure as S
from services.geometry import dihedral, norm, sub


def _by_atom(atoms):
    return {(a.resi, a.name): a.pos for a in atoms}


@pytest.mark.parametrize("state", ["H", "E", "T", "C"])
def test_requested_dihedrals_are_reproduced(state):
    seq, ss = "A" * 14, state * 14
    _, _, atoms = S.generate_chain_atoms(seq, ss)
    p, ang = _by_atom(atoms), S.residue_angles(seq, ss)
    for i in range(2, 12):
        phi = dihedral(p[(i - 1, "C")], p[(i, "N")], p[(i, "CA")], p[(i, "C")])
        psi = dihedral(p[(i, "N")], p[(i, "CA")], p[(i, "C")], p[(i + 1, "N")])
        omega = dihedral(p[(i - 1, "CA")], p[(i - 1, "C")], p[(i, "N")], p[(i, "CA")])
        assert abs((phi - ang[i - 1][0] + 180) % 360 - 180) < 0.01
        assert abs((psi - ang[i - 1][1] + 180) % 360 - 180) < 0.01
        assert abs(abs(omega) - 180) < 0.01  # planar trans peptide


def test_helix_is_helical():
    _, _, atoms = S.generate_chain_atoms("A" * 40, "H" * 40)
    ca = [a.pos for a in atoms if a.name == "CA"]
    assert 1.4 < norm(sub(ca[-1], ca[0])) / 39 < 1.7  # ~1.5 A rise per residue
    assert 5.9 < norm(sub(ca[4], ca[0])) < 6.6  # i -> i+4


def test_strand_does_not_collapse():
    _, _, atoms = S.generate_chain_atoms("A" * 30, "E" * 30)
    ca = [a.pos for a in atoms if a.name == "CA"]
    assert norm(sub(ca[-1], ca[0])) > 80


def test_glycine_has_no_cbeta():
    _, _, atoms = S.generate_chain_atoms("AGA", "CCC")
    names = {(a.resi, a.name) for a in atoms}
    assert (1, "CB") in names and (2, "CB") not in names


def test_ss_records_emitted():
    pdb, _ = S.generate_pdb_report("A" * 12, "H" * 6 + "C" * 2 + "E" * 4)
    assert any(l.startswith("HELIX") for l in pdb.splitlines())
    assert any(l.startswith("SHEET") for l in pdb.splitlines())


def test_chains_do_not_overlap():
    chains = [S.ProteinChainRequest(id=i, sequence="A" * 100, structure="H" * 100) for i in "AB"]
    pdb, _ = S.generate_complex_report(chains)
    pts = {"A": [], "B": []}
    for l in pdb.splitlines():
        if l.startswith("ATOM"):
            pts[l[21]].append((float(l[30:38]), float(l[38:46]), float(l[46:54])))
    assert min(norm(sub(a, b)) for a in pts["A"][::4] for b in pts["B"][::4]) > 8


@pytest.mark.parametrize(
    "seq,ss",
    [("", ""), ("AAA", "HH"), ("AXA", "HHH"), ("AAA", "HZH"), ("A" * 2001, "H" * 2001)],
)
def test_validation_rejects_bad_input(seq, ss):
    with pytest.raises(HTTPException):
        S.generate_chain_atoms(seq, ss)


def test_duplicate_and_bad_chain_ids():
    c = S.ProteinChainRequest(id="A", sequence="AAAA", structure="HHHH")
    with pytest.raises(HTTPException):
        S.generate_complex_report([c, c])
    with pytest.raises(HTTPException):
        S.generate_complex_report([S.ProteinChainRequest(id="AB", sequence="AAAA", structure="HHHH")])
