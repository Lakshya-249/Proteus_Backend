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


# Approximate peptide backbone geometry.
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
        raise ValueError("Cannot normalize zero-length vector.")

    return scale(v, 1.0 / length)


def place_atom(
    a,
    b,
    c,
    length,
    angle_deg,
    dihedral_deg,
):
    """
    Place a new atom D using:

        A - B - C - D

    with:
      |C-D| = length
      angle B-C-D = angle
      dihedral A-B-C-D = dihedral
    """

    bc = normalize(sub(c, b))

    ba = normalize(sub(a, b))

    normal = cross(ba, bc)

    if norm(normal) < 1e-8:
        # Degenerate reference frame.
        # Pick an arbitrary perpendicular direction.
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
            scale(bc, -cos(theta)),
            scale(perpendicular, sin(theta) * cos(phi)),
        ),
        scale(normal, sin(theta) * sin(phi)),
    )

    return add(c, scale(direction, length))


def structure_angles(state):
    """
    Return representative backbone phi/psi angles.

    These are idealized values used to create
    recognizable secondary-structure geometry.
    """

    if state == "H":
        # Alpha helix
        return -57.0, -47.0

    if state == "E":
        # Extended beta strand
        return -135.0, 135.0

    if state == "T":
        # Turn-like geometry
        return -60.0, 30.0

    # Coil
    return -90.0, 60.0


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


def generate_pdb(sequence: str, structure: str) -> str:
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
        aa for aa in sequence
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

    allowed_structure = {"H", "E", "C", "T"}

    invalid_structure = [
        state for state in structure
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

    atoms = []

    # --------------------------------------------------
    # First residue
    #
    # Start with a simple coordinate frame.
    # --------------------------------------------------

    n = (0.0, 0.0, 0.0)

    ca = (
        BOND_N_CA,
        0.0,
        0.0,
    )

    # Initial C atom.
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

    # Oxygen attached to C.
    o = place_atom(
        n,
        ca,
        c,
        BOND_C_O,
        ANGLE_CA_C_O,
        0.0,
    )

    atoms.append((1, "N", n))
    atoms.append((2, "CA", ca))
    atoms.append((3, "C", c))
    atoms.append((4, "O", o))

    serial = 5

    previous_n = n
    previous_ca = ca
    previous_c = c

    # --------------------------------------------------
    # Remaining residues
    # --------------------------------------------------

    for i in range(1, len(sequence)):
        state = structure[i]
        phi, psi = structure_angles(state)

        # ----------------------------------------------
        # N(i)
        #
        # Omega ≈ 180° for a trans peptide bond.
        # ----------------------------------------------

        current_n = place_atom(
            previous_n,
            previous_ca,
            previous_c,
            BOND_C_N,
            ANGLE_CA_C_N,
            180.0,
        )

        # ----------------------------------------------
        # CA(i)
        #
        # Phi determines the local backbone direction.
        # ----------------------------------------------

        current_ca = place_atom(
            previous_ca,
            previous_c,
            current_n,
            BOND_N_CA,
            ANGLE_C_N_CA,
            phi,
        )

        # ----------------------------------------------
        # C(i)
        #
        # Psi controls the next backbone direction.
        # ----------------------------------------------

        current_c = place_atom(
            previous_c,
            current_n,
            current_ca,
            BOND_CA_C,
            ANGLE_N_CA_C,
            psi,
        )

        # ----------------------------------------------
        # O(i)
        # ----------------------------------------------

        current_o = place_atom(
            current_n,
            current_ca,
            current_c,
            BOND_C_O,
            ANGLE_CA_C_O,
            0.0,
        )

        atoms.append(
            (serial, "N", current_n)
        )
        serial += 1

        atoms.append(
            (serial, "CA", current_ca)
        )
        serial += 1

        atoms.append(
            (serial, "C", current_c)
        )
        serial += 1

        atoms.append(
            (serial, "O", current_o)
        )
        serial += 1

        previous_n = current_n
        previous_ca = current_ca
        previous_c = current_c

    # --------------------------------------------------
    # Convert atoms to PDB
    # --------------------------------------------------

    lines = []

    for index, atom, position in atoms:
        residue_index = ((index - 1) // 4) + 1
        aa = sequence[residue_index - 1]
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
