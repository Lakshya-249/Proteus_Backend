def parse_dssp(
    content: str,
    chain_id: str,
):
    lines = content.splitlines()

    data_started = False
    residues = []

    for line in lines:
        if line.startswith("  #  RESIDUE"):
            data_started = True
            continue

        if not data_started:
            continue

        if len(line) < 38:
            continue

        try:
            # /*
            #  * DSSP format:
            #  *
            #  * line[5:10]
            #  *     DSSP sequential residue number
            #  *
            #  * line[11]
            #  *     structure chain
            #  *
            #  * line[12:16]
            #  *     structure residue number /
            #  *     insertion code
            #  *
            #  * line[16]
            #  *     amino acid
            #  *
            #  * line[16] is actually the AA/structure
            #  * area in the legacy format, so we use
            #  * the documented fixed-width positions.
            #  */

            dssp_chain = line[11].strip()

            if dssp_chain != chain_id:
                continue

            # /*
            #  * The residue number in the structure
            #  * model occupies the second residue field.
            #  */
            residue_field = line[5:10].strip()

            residue_number = int(
                residue_field
            )

            residue_name = line[13]

            secondary_structure = (
                line[16].strip()
            )

            accessibility = int(
                line[34:38].strip()
            )

            residues.append(
                {
                    "resi": residue_number,
                    "resn": residue_name,
                    "secondary_structure": (
                        secondary_structure
                        or "C"
                    ),
                    "accessibility": accessibility,
                }
            )

        except (
            ValueError,
            IndexError,
        ):
            continue

    return residues
