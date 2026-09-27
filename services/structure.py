from math import cos, sin, radians, sqrt

from fastapi import HTTPException
from pydantic import BaseModel


AA3 = {
    "A": "ALA",
    "C": "CYS",
    "D": "ASP",
    "E": "GLU",
    "F": "PHE",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "K": "LYS",
    "L": "LEU",
    "M": "MET",
    "N": "ASN",
    "P": "PRO",
    "Q": "GLN",
    "R": "ARG",
    "S": "SER",
    "T": "THR",
    "V": "VAL",
    "W": "TRP",
    "Y": "TYR",
}


class StructureDesignRequest(BaseModel):
    sequence: str
    structure: str


class ProteinChainRequest(BaseModel):
    id: str
    sequence: str
    structure: str


class ComplexDesignRequest(BaseModel):
    chains: list[ProteinChainRequest]


BOND_N_CA = 1.458
BOND_CA_C = 1.525
BOND_C_N = 1.329
BOND_C_O = 1.229

ANGLE_C_N_CA = 121.7
ANGLE_N_CA_C = 110.4
ANGLE_CA_C_N = 116.2
ANGLE_CA_C_O = 120.8


def sub(a, b):
    return (
        a[0] - b[0],
        a[1] - b[1],
        a[2] - b[2],
    )


def add(a, b):
    return (
        a[0] + b[0],
        a[1] + b[1],
        a[2] + b[2],
    )


def scale(v, s):
    return (
        v[0] * s,
        v[1] * s,
        v[2] * s,
    )


def dot(a, b):
    return (
        a[0] * b[0]
        + a[1] * b[1]
        + a[2] * b[2]
    )


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(v):
    return sqrt(dot(v, v))


def normalize(v):
    length = norm(v)

    if length == 0:
        raise ValueError(
            "Cannot normalize zero-length vector."
        )

    return scale(v, 1.0 / length)


def place_atom(
    a,
    b,
    c,
    length,
    angle_deg,
    dihedral_deg,
):
    bc = normalize(sub(c, b))
    ba = normalize(sub(a, b))

    normal = cross(ba, bc)

    if norm(normal) < 1e-8:
        fallback = (0.0, 0.0, 1.0)

        if abs(dot(bc, fallback)) > 0.9:
            fallback = (0.0, 1.0, 0.0)

        normal = cross(fallback, bc)

    normal = normalize(normal)

    perpendicular = normalize(
        cross(normal, bc)
    )

    theta = radians(angle_deg)
    phi = radians(dihedral_deg)

    direction = add(
        add(
            scale(
                bc,
                -cos(theta),
            ),
            scale(
                perpendicular,
                sin(theta) * cos(phi),
            ),
        ),
        scale(
            normal,
            sin(theta) * sin(phi),
        ),
    )

    return add(
        c,
        scale(direction, length),
    )


# def structure_angles(state):
#     if state == "H":
#         return -57.0, -47.0
#
#     if state == "E":
#         return -135.0, 135.0
#
#     if state == "T":
#         return -60.0, 30.0
#
#     return -90.0, 60.0

AA_ORDER = "ACDEFGHIKLMNPQRSTVWY"

def structure_angles(state, aa=None):
    base = {
        "H": (-57.0, -47.0),
        "E": (-135.0, 135.0),
        "T": (-60.0, 30.0),
    }.get(state, (-90.0, 60.0))

    if aa is None or aa not in AA_ORDER:
        return base

    # Small deterministic per-residue jitter so identical
    # secondary-structure strings don't collapse to identical
    # geometry when the sequence differs. Still stays within
    # a realistic range for each SS class.
    # jitter = (AA_ORDER.index(aa) % 7) - 3  # -3..+3 degrees
    jitter = ((AA_ORDER.index(aa) % 7) - 3) * 7
    phi, psi = base
    return phi + jitter, psi - jitter

def atom_line(
    serial,
    atom,
    residue,
    chain,
    resi,
    x,
    y,
    z,
    element,
):
    return (
        f"ATOM  {serial:5d} "
        f"{atom:^4s} "
        f"{residue:>3s} "
        f"{chain}"
        f"{resi:4d}    "
        f"{x:8.3f}"
        f"{y:8.3f}"
        f"{z:8.3f}"
        f"  1.00  0.00          "
        f"{element:>2s}"
    )


def validate_chain(
    sequence: str,
    structure: str,
):
    sequence = sequence.strip().upper()
    structure = structure.strip().upper()

    if not sequence:
        raise HTTPException(
            status_code=400,
            detail="Sequence cannot be empty.",
        )

    if len(sequence) != len(structure):
        raise HTTPException(
            status_code=400,
            detail=(
                "Sequence and structure must "
                "have the same length."
            ),
        )

    invalid_residues = [
        aa
        for aa in sequence
        if aa not in AA3
    ]

    if invalid_residues:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid amino acid(s): "
                f"{sorted(set(invalid_residues))}"
            ),
        )

    allowed_structure = {
        "H",
        "E",
        "C",
        "T",
    }

    invalid_structure = [
        state
        for state in structure
        if state not in allowed_structure
    ]

    if invalid_structure:
        raise HTTPException(
            status_code=400,
            detail=(
                "Structure may only contain "
                "H, E, C, or T."
            ),
        )

    return sequence, structure


def generate_chain_atoms(
    sequence: str,
    structure: str,
):
    """
    Generate one independent peptide chain.

    Returns:

        [
            ("N",  x, y, z),
            ("CA", x, y, z),
            ...
        ]
    """

    sequence, structure = validate_chain(
        sequence,
        structure,
    )

    atoms = []

    n = (
        0.0,
        0.0,
        0.0,
    )

    ca = (
        BOND_N_CA,
        0.0,
        0.0,
    )

    c = place_atom(
        n,
        (
            -1.0,
            0.0,
            0.0,
        ),
        ca,
        BOND_CA_C,
        ANGLE_N_CA_C,
        180.0,
    )

    o = place_atom(
        n,
        ca,
        c,
        BOND_C_O,
        ANGLE_CA_C_O,
        0.0,
    )

    atoms.append(
        ("N", n)
    )

    atoms.append(
        ("CA", ca)
    )

    atoms.append(
        ("C", c)
    )

    atoms.append(
        ("O", o)
    )

    previous_n = n
    previous_ca = ca
    previous_c = c

    for i in range(1, len(sequence)):
        state = structure[i]

        phi, psi = structure_angles(
            state, sequence[i]
        )

        current_n = place_atom(
            previous_n,
            previous_ca,
            previous_c,
            BOND_C_N,
            ANGLE_CA_C_N,
            180.0,
        )

        current_ca = place_atom(
            previous_ca,
            previous_c,
            current_n,
            BOND_N_CA,
            ANGLE_C_N_CA,
            phi,
        )

        current_c = place_atom(
            previous_c,
            current_n,
            current_ca,
            BOND_CA_C,
            ANGLE_N_CA_C,
            psi,
        )

        current_o = place_atom(
            current_n,
            current_ca,
            current_c,
            BOND_C_O,
            ANGLE_CA_C_O,
            0.0,
        )

        atoms.append(
            ("N", current_n)
        )

        atoms.append(
            ("CA", current_ca)
        )

        atoms.append(
            ("C", current_c)
        )

        atoms.append(
            ("O", current_o)
        )

        previous_n = current_n
        previous_ca = current_ca
        previous_c = current_c

    return sequence, structure, atoms


def generate_pdb(
    sequence: str,
    structure: str,
) -> str:

    sequence, structure, atoms = (
        generate_chain_atoms(
            sequence,
            structure,
        )
    )

    lines = []

    for index, (atom, position) in enumerate(
        atoms,
        start=1,
    ):
        residue_index = (
            (index - 1) // 4
        ) + 1

        aa = sequence[
            residue_index - 1
        ]

        residue = AA3[aa]

        element = atom[0]

        lines.append(
            atom_line(
                index,
                atom,
                residue,
                "A",
                residue_index,
                position[0],
                position[1],
                position[2],
                element,
            )
        )

    lines.append("END")

    return "\n".join(lines) + "\n"


def generate_complex_pdb(
    chains: list[ProteinChainRequest],
) -> str:

    if not chains:
        raise HTTPException(
            status_code=400,
            detail="At least one chain is required.",
        )

    if len(chains) > 26:
        raise HTTPException(
            status_code=400,
            detail="A maximum of 26 chains is supported.",
        )

    seen_ids = set()

    all_lines = []

    serial = 1

    for chain_index, chain in enumerate(chains):

        chain_id = chain.id.strip().upper()

        if not chain_id:
            raise HTTPException(
                status_code=400,
                detail="Chain ID cannot be empty.",
            )

        if len(chain_id) != 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Chain ID '{chain_id}' "
                    "must be exactly one character."
                ),
            )

        if chain_id in seen_ids:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Duplicate chain ID: {chain_id}"
                ),
            )

        seen_ids.add(chain_id)

        sequence, structure, atoms = (
            generate_chain_atoms(
                chain.sequence,
                chain.structure,
            )
        )

        # Initial spatial separation.
        #
        # This is intentionally only an initial
        # placement. It is NOT molecular docking.
        #
        # Future versions can replace this with
        # user-controlled transformations,
        # symmetry, docking, and constraints.
        offset_x = chain_index * 30.0

        for atom_index, (
            atom,
            position,
        ) in enumerate(
            atoms,
            start=0,
        ):
            residue_index = (
                atom_index // 4
            ) + 1

            aa = sequence[
                residue_index - 1
            ]

            residue = AA3[aa]

            x = position[0] + offset_x
            y = position[1]
            z = position[2]

            element = atom[0]

            all_lines.append(
                atom_line(
                    serial,
                    atom,
                    residue,
                    chain_id,
                    residue_index,
                    x,
                    y,
                    z,
                    element,
                )
            )

            serial += 1

        # TER separates chains in the PDB.
        all_lines.append(
            f"TER   {serial:5d}      "
            f"{AA3[sequence[-1]]:>3s} "
            f"{chain_id}"
            f"{len(sequence):4d}"
        )

        serial += 1

    all_lines.append("END")

    return "\n".join(all_lines) + "\n"
