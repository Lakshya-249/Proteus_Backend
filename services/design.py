"""Backwards-compatible shim: single-chain design now lives in services.structure."""
from services.structure import (  # noqa: F401
    StructureDesignRequest,
    generate_pdb,
    generate_pdb_report,
)
