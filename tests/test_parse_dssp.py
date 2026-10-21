from services.parse_dssp import parse_dssp


def _line(num, chain, aa, ss, acc, phi, psi):
    buf = [" "] * 136
    buf[5:10] = f"{num:5d}"
    buf[11] = chain
    buf[13] = aa
    buf[16] = ss
    buf[34:38] = f"{acc:4d}"
    buf[103:109] = f"{phi:6.1f}"
    buf[109:115] = f"{psi:6.1f}"
    return "".join(buf)


DSSP = "\n".join(
    [
        "  #  RESIDUE AA STRUCTURE BP1 BP2  ACC",
        _line(1, "A", "M", " ", 140, 360.0, 143.1),
        _line(2, "A", "A", "H", 0, -57.3, -47.2),
        _line(3, "A", "!", " ", 0, 0, 0),
        _line(4, "B", "G", "E", 52, -120.0, 130.0),
        _line(5, "A", "a", "E", 30, -100.0, 120.0),
    ]
)


def test_parses_requested_chain_only_and_skips_breaks():
    res = parse_dssp(DSSP, "A")
    assert [r["resi"] for r in res] == [1, 2, 5]


def test_undefined_angles_are_none_and_relative_asa_computed():
    res = parse_dssp(DSSP, "A")
    assert res[0]["phi"] is None and res[0]["psi"] == 143.1
    assert res[0]["rel_accessibility"] == round(140 / 224 * 100, 1)  # Met max ASA 224
    assert res[2]["resn"] == "C"  # lowercase = disulfide cysteine
