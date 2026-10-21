"""Parse classic-format DSSP output into per-residue records."""

# Theoretical maximum solvent accessibility in A^2 (Tien et al., 2013)
MAX_ASA = {
    "A": 129.0, "R": 274.0, "N": 195.0, "D": 193.0, "C": 167.0,
    "Q": 225.0, "E": 223.0, "G": 104.0, "H": 224.0, "I": 197.0,
    "L": 201.0, "K": 236.0, "M": 224.0, "F": 240.0, "P": 159.0,
    "S": 155.0, "T": 172.0, "W": 285.0, "Y": 263.0, "V": 174.0,
}


def _angle(text: str):
    try:
        value = float(text)
    except ValueError:
        return None
    return None if abs(value - 360.0) < 1e-6 else value  # 360.0 = undefined


def parse_dssp(content: str, chain_id: str):
    residues = []
    started = False
    for line in content.splitlines():
        if line.startswith("  #  RESIDUE"):
            started = True
            continue
        if not started or len(line) < 38:
            continue
        try:
            if line[13] == "!":  # chain break marker
                continue
            if line[11].strip() != chain_id:
                continue

            resn = line[13]
            if resn.islower():  # lowercase = half of a disulfide-bonded cysteine
                resn = "C"
            acc = int(line[34:38])
            max_asa = MAX_ASA.get(resn)
            insertion = line[10].strip()

            residues.append(
                {
                    "resi": int(line[5:10]),
                    "icode": insertion,
                    "resn": resn,
                    "secondary_structure": line[16].strip() or "C",
                    "accessibility": acc,  # absolute, A^2
                    "rel_accessibility": (
                        round(min(100.0, acc / max_asa * 100.0), 1) if max_asa else None
                    ),
                    "phi": _angle(line[103:109]) if len(line) >= 109 else None,
                    "psi": _angle(line[109:115]) if len(line) >= 115 else None,
                }
            )
        except (ValueError, IndexError):
            continue
    return residues
