"""Idealised backbone builder for the Structure Designer.

Builds N, CA, C, O (+ CB for non-glycine) from per-residue phi/psi using the
NeRF algorithm, writes a PDB with HELIX/SHEET records so viewers draw the
painted secondary structure, and reports steric clashes.

NOTE: this is an idealised backbone *sketch*, not a folded/packed structure.
For a physically meaningful fold use /structure/predict (ESMFold).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import BaseModel

from services.geometry import Vec, add, norm, place_atom, place_cbeta, scale, sub

AA3 = {
    "A": "ALA", "C": "CYS", "D": "ASP", "E": "GLU", "F": "PHE",
    "G": "GLY", "H": "HIS", "I": "ILE", "K": "LYS", "L": "LEU",
    "M": "MET", "N": "ASN", "P": "PRO", "Q": "GLN", "R": "ARG",
    "S": "SER", "T": "THR", "V": "VAL", "W": "TRP", "Y": "TYR",
}
AA_ORDER = "ACDEFGHIKLMNPQRSTVWY"

MAX_RESIDUES_PER_CHAIN = 2000
MAX_TOTAL_RESIDUES = 6000
MAX_CHAINS = 26
CHAIN_GAP = 12.0  # Angstrom between bounding spheres in a complex

BOND_N_CA = 1.458
BOND_CA_C = 1.525
BOND_C_N = 1.329
BOND_C_O = 1.229
ANGLE_C_N_CA = 121.7
ANGLE_N_CA_C = 111.0
ANGLE_CA_C_N = 116.2
ANGLE_CA_C_O = 120.8
OMEGA_TRANS = 180.0


class StructureDesignRequest(BaseModel):
    sequence: str
    structure: str


class ProteinChainRequest(BaseModel):
    id: str
    sequence: str
    structure: str


class ComplexDesignRequest(BaseModel):
    chains: list[ProteinChainRequest]


@dataclass
class Atom:
    resi: int  # 1-based
    name: str
    element: str
    pos: Vec


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_chain(sequence: str, structure: str) -> tuple[str, str]:
    sequence = "".join(sequence.split()).upper()
    structure = "".join(structure.split()).upper()

    if not sequence:
        raise HTTPException(400, "Sequence cannot be empty.")
    if len(sequence) > MAX_RESIDUES_PER_CHAIN:
        raise HTTPException(
            400, f"Chains are limited to {MAX_RESIDUES_PER_CHAIN} residues."
        )
    if len(sequence) != len(structure):
        raise HTTPException(400, "Sequence and structure must have the same length.")

    bad_aa = sorted({aa for aa in sequence if aa not in AA3})
    if bad_aa:
        raise HTTPException(400, f"Invalid amino acid(s): {bad_aa}")

    if any(s not in "HECT" for s in structure):
        raise HTTPException(400, "Structure may only contain H, E, C, or T.")

    return sequence, structure


# --------------------------------------------------------------------------
# Backbone angles
# --------------------------------------------------------------------------
_HELIX = (-57.0, -47.0)
_STRAND = (-125.0, 130.0)
_TURN_CYCLE = ((-60.0, -30.0), (-90.0, 0.0))  # type-I beta turn
_COIL = (-75.0, 145.0)  # polyproline-II like


def residue_angles(sequence: str, structure: str) -> list[tuple[float, float]]:
    """(phi, psi) for every residue. Index 0's phi and the last psi only affect
    the carbonyl oxygen, never the chain path."""
    angles: list[tuple[float, float]] = []
    run_pos = 0
    for i, state in enumerate(structure):
        run_pos = run_pos + 1 if i > 0 and structure[i - 1] == state else 0
        aa = sequence[i]
        aa_idx = AA_ORDER.index(aa)

        if state == "H":
            phi, psi = _HELIX
        elif state == "E":
            phi, psi = _STRAND
        elif state == "T":
            phi, psi = _TURN_CYCLE[run_pos % 2]
        else:  # coil: small deterministic variation so loops are not a perfect rod
            jitter = ((i * 7 + aa_idx * 3) % 5 - 2) * 6.0
            phi, psi = _COIL[0] + jitter, _COIL[1] - jitter

        if aa == "P":
            phi = -65.0
        elif aa == "G" and state in ("C", "T"):
            phi, psi = phi + 20.0, psi + 15.0
        angles.append((phi, psi))
    return angles


# --------------------------------------------------------------------------
# Chain builder
# --------------------------------------------------------------------------
def generate_chain_atoms(sequence: str, structure: str):
    sequence, structure = validate_chain(sequence, structure)
    angles = residue_angles(sequence, structure)
    atoms: list[Atom] = []

    # Residue 1 in an arbitrary but fixed frame.
    n: Vec = (0.0, 0.0, 0.0)
    ca: Vec = (BOND_N_CA, 0.0, 0.0)
    c = place_atom((-0.5, 1.0, 0.0), n, ca, BOND_CA_C, ANGLE_N_CA_C, 180.0)

    def emit(resi: int, aa: str, n_, ca_, c_, psi: float) -> None:
        o = place_atom(n_, ca_, c_, BOND_C_O, ANGLE_CA_C_O, psi + 180.0)
        atoms.append(Atom(resi, "N", "N", n_))
        atoms.append(Atom(resi, "CA", "C", ca_))
        atoms.append(Atom(resi, "C", "C", c_))
        atoms.append(Atom(resi, "O", "O", o))
        if aa != "G":
            atoms.append(Atom(resi, "CB", "C", place_cbeta(n_, ca_, c_)))

    emit(1, sequence[0], n, ca, c, angles[0][1])

    pn, pca, pc = n, ca, c
    for i in range(1, len(sequence)):
        phi, psi = angles[i]
        prev_psi = angles[i - 1][1]
        # N(i) is governed by psi(i-1); CA(i) by omega; C(i) by phi(i).
        cn = place_atom(pn, pca, pc, BOND_C_N, ANGLE_CA_C_N, prev_psi)
        cca = place_atom(pca, pc, cn, BOND_N_CA, ANGLE_C_N_CA, OMEGA_TRANS)
        cc = place_atom(pc, cn, cca, BOND_CA_C, ANGLE_N_CA_C, phi)
        emit(i + 1, sequence[i], cn, cca, cc, psi)
        pn, pca, pc = cn, cca, cc

    return sequence, structure, atoms


# --------------------------------------------------------------------------
# Clash detection (cell list, O(n))
# --------------------------------------------------------------------------
def count_clashes(atoms: list[Atom], cutoff: float = 2.2) -> int:
    cell = cutoff
    grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for idx, a in enumerate(atoms):
        grid[(int(a.pos[0] // cell), int(a.pos[1] // cell), int(a.pos[2] // cell))].append(idx)

    clashes = 0
    for i, a in enumerate(atoms):
        cx, cy, cz = (int(a.pos[0] // cell), int(a.pos[1] // cell), int(a.pos[2] // cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        if j <= i or abs(atoms[j].resi - a.resi) < 2:
                            continue
                        if norm(sub(a.pos, atoms[j].pos)) < cutoff:
                            clashes += 1
    return clashes


# --------------------------------------------------------------------------
# PDB writing
# --------------------------------------------------------------------------
def atom_line(serial, atom, residue, chain, resi, x, y, z, element) -> str:
    name = f" {atom:<3s}" if len(atom) < 4 else atom
    return (
        f"ATOM  {serial:5d} {name} {residue:>3s} {chain}{resi:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {element:>2s}"
    )


def _record(kind: str, fields: dict[int, str]) -> str:
    """Build an 80-col fixed-width record. fields: {1-based start col: text}."""
    buf = [" "] * 80
    for k, ch in enumerate(kind):
        buf[k] = ch
    for start, text in fields.items():
        for k, ch in enumerate(text):
            buf[start - 1 + k] = ch
    return "".join(buf).rstrip()


def _runs(structure: str, state: str, min_len: int) -> list[tuple[int, int]]:
    out, start = [], None
    for i, s in enumerate(structure + "\0"):
        if s == state and start is None:
            start = i
        elif s != state and start is not None:
            if i - start >= min_len:
                out.append((start + 1, i))  # 1-based inclusive
            start = None
    return out


def _ss_records(chains: list[tuple[str, str, str]]) -> list[str]:
    lines: list[str] = []
    h = s = 0
    for cid, seq, ss in chains:
        for a, b in _runs(ss, "H", 4):
            h += 1
            lines.append(_record("HELIX", {
                8: f"{h:3d}", 12: f"{h:>3d}", 16: AA3[seq[a - 1]], 20: cid,
                22: f"{a:4d}", 28: AA3[seq[b - 1]], 32: cid, 34: f"{b:4d}",
                39: " 1", 72: f"{b - a + 1:5d}",
            }))
        for a, b in _runs(ss, "E", 2):
            s += 1
            lines.append(_record("SHEET", {
                8: f"{s:3d}", 12: f"{s:>3d}", 15: " 1", 18: AA3[seq[a - 1]],
                22: cid, 23: f"{a:4d}", 29: AA3[seq[b - 1]], 33: cid,
                34: f"{b:4d}", 39: " 0",
            }))
    return lines


def _centre_and_radius(atoms: list[Atom]) -> tuple[Vec, float]:
    cas = [a.pos for a in atoms if a.name == "CA"] or [a.pos for a in atoms]
    centre = scale(
        (sum(p[0] for p in cas), sum(p[1] for p in cas), sum(p[2] for p in cas)),
        1.0 / len(cas),
    )
    radius = max(norm(sub(a.pos, centre)) for a in atoms)
    return centre, radius


def generate_complex_report(chains: list[ProteinChainRequest], ss_records: bool = True):
    if not chains:
        raise HTTPException(400, "At least one chain is required.")
    if len(chains) > MAX_CHAINS:
        raise HTTPException(400, f"A maximum of {MAX_CHAINS} chains is supported.")

    seen: set[str] = set()
    built = []
    total = 0
    for chain in chains:
        cid = chain.id.strip().upper()
        if len(cid) != 1 or not cid.isalnum():
            raise HTTPException(400, f"Chain ID must be a single letter or digit (got '{chain.id}').")
        if cid in seen:
            raise HTTPException(400, f"Duplicate chain ID '{cid}'.")
        seen.add(cid)

        seq, ss, atoms = generate_chain_atoms(chain.sequence, chain.structure)
        total += len(seq)
        if total > MAX_TOTAL_RESIDUES:
            raise HTTPException(400, f"Complex is limited to {MAX_TOTAL_RESIDUES} residues in total.")
        built.append((cid, seq, ss, atoms))

    # Centre each chain and lay chains out along X by bounding sphere,
    # so long chains never overlap their neighbours.
    placed: list[tuple[str, str, str, list[Atom]]] = []
    cursor = 0.0
    for cid, seq, ss, atoms in built:
        centre, radius = _centre_and_radius(atoms)
        x_off = cursor + radius
        shift = (x_off - centre[0], -centre[1], -centre[2])
        placed.append((cid, seq, ss, [Atom(a.resi, a.name, a.element, add(a.pos, shift)) for a in atoms]))
        cursor = x_off + radius + CHAIN_GAP

    lines = ["REMARK 999 IDEALISED BACKBONE SKETCH - NOT A PREDICTED OR PACKED FOLD"]
    if ss_records:
        lines += _ss_records([(c, s, t) for c, s, t, _ in placed])

    serial = 1
    clashes = 0
    for cid, seq, _ss, atoms in placed:
        clashes += count_clashes(atoms)
        for a in atoms:
            x, y, z = a.pos
            lines.append(atom_line(serial, a.name, AA3[seq[a.resi - 1]], cid, a.resi, x, y, z, a.element))
            serial += 1
        lines.append(f"TER   {serial:5d}      {AA3[seq[-1]]:>3s} {cid}{len(seq):4d}")
        serial += 1
    lines.append("END")

    warnings = []
    if clashes:
        warnings.append(
            f"{clashes} atom pair(s) are closer than 2.2 A. Idealised angles do not guarantee a "
            "self-avoiding fold; shorten loops/helices or use ESMFold for a real prediction."
        )
    return "\n".join(lines) + "\n", warnings


def generate_complex_pdb(request: ComplexDesignRequest) -> str:
    return generate_complex_report(request.chains)[0]


def generate_pdb_report(sequence: str, structure: str, ss_records: bool = True):
    return generate_complex_report(
        [ProteinChainRequest(id="A", sequence=sequence, structure=structure)], ss_records
    )


def generate_pdb(sequence: str, structure: str) -> str:
    return generate_pdb_report(sequence, structure)[0]
