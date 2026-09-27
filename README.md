# Proteus Backend

Backend services for **Proteus**, a web-based computational protein structure analysis and design platform.

The backend provides APIs for retrieving protein structures, performing structure-based analysis, generating designed peptide/protein structures, and serving computational results to the Proteus web client.

---

## Overview

Proteus combines molecular visualization with computational structural analysis.

The backend currently supports:

* Protein structure retrieval from the **RCSB Protein Data Bank**
* DSSP-based secondary-structure assignment
* Residue-level solvent accessibility analysis
* User-defined protein/peptide structure generation
* PDB generation from amino-acid sequences and secondary-structure constraints
* REST APIs for the Proteus frontend
* External molecular-analysis executables such as `mkdssp`

The generated structures can be passed directly to the frontend molecular viewer for interactive inspection.

---

## Architecture

```text
                    ┌──────────────────────┐
                    │      Proteus Web     │
                    │      React + TS      │
                    └──────────┬───────────┘
                               │
                         HTTP / JSON
                               │
                    ┌──────────▼───────────┐
                    │    Proteus Server    │
                    │       FastAPI        │
                    └──────────┬───────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
        RCSB PDB           DSSP / mkdssp     Structure
        Retrieval          Secondary          Generator
                             Structure
             │                 │                 │
             └─────────────────┼─────────────────┘
                               │
                               ▼
                         PDB / JSON Results
```

---

## Technology Stack

| Component                 | Technology      |
| ------------------------- | --------------- |
| API framework             | FastAPI         |
| Language                  | Python          |
| Validation                | Pydantic        |
| Structure format          | PDB             |
| Secondary structure       | DSSP / `mkdssp` |
| External structure source | RCSB PDB        |
| Development server        | Uvicorn         |
| Frontend                  | Proteus Web     |
| Molecular visualization   | 3Dmol.js        |

---

## Project Structure

```text
apps/server/
│
├── api/
│   ├── controller/
│   │   └── ...
│   │
│   └── ...
│
├── ...
│
├── main.py
│
└── README.md
```

The backend is organized around API controllers and computational functionality.

---

# Running the Server

## Requirements

Python 3.10+ is recommended.

You also need the DSSP executable for structure analysis.

Check:

```bash
python --version
```

and:

```bash
mkdssp --version
```

---

## Install Dependencies

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Start the API

From:

```text
apps/server
```

run:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at:

```text
http://127.0.0.1:8000
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

---

# API

## DSSP Analysis

### Endpoint

```http
POST /api/analysis/dssp
```

Runs DSSP analysis against a PDB structure retrieved from RCSB.

### Request

```json
{
  "pdb_id": "1UBQ",
  "chain_id": "A"
}
```

### Example

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/dssp \
  -H "Content-Type: application/json" \
  -d '{
    "pdb_id": "1UBQ",
    "chain_id": "A"
  }'
```

### Response

```json
{
  "method": "DSSP",
  "pdb_id": "1UBQ",
  "chain_id": "A",
  "residues": [
    {
      "resi": 1,
      "resn": "M",
      "secondary_structure": "C",
      "accessibility": 53
    },
    {
      "resi": 2,
      "resn": "Q",
      "secondary_structure": "E",
      "accessibility": 77
    }
  ]
}
```

---

## DSSP Pipeline

The analysis endpoint follows this pipeline:

```text
PDB ID
  │
  ▼
RCSB PDB download
  │
  ▼
Temporary PDB file
  │
  ▼
mkdssp
  │
  ▼
DSSP output
  │
  ▼
Parser
  │
  ▼
Residue-level JSON
```

The backend creates a temporary workspace for each analysis request and removes it after processing.

---

## Secondary Structure

DSSP assignments are returned using the standard single-character notation.

| Code | Structure |
| ---- | --------- |
| H    | α-Helix   |
| G    | 3₁₀ helix |
| I    | π-helix   |
| E    | β-sheet   |
| B    | β-bridge  |
| T    | Turn      |
| S    | Bend      |
| C    | Coil      |

This allows the frontend to render secondary-structure-specific visualizations.

---

## Solvent Accessibility

The DSSP result also contains residue-level accessibility values.

Example:

```json
{
  "resi": 32,
  "resn": "D",
  "secondary_structure": "H",
  "accessibility": 146
}
```

The accessibility value is associated with the corresponding residue and can be used for residue inspection and visualization.

---

# Structure Design

Proteus also exposes a structure-generation endpoint that allows users to specify a sequence and a desired secondary-structure pattern.

### Endpoint

```http
POST /api/design/structure
```

### Request

```json
{
  "sequence": "MKTAAAAAAKG",
  "structure": "HHHHHHHHHCC"
}
```

The sequence and structure strings must correspond residue-by-residue.

For example:

```text
Sequence:
M K T A A A A A A K G

Structure:
H H H H H H H H H C C
```

---

## Example

```bash
curl -X POST http://127.0.0.1:8000/api/design/structure \
  -H "Content-Type: application/json" \
  -d '{
    "sequence": "MKTAAAAAAKG",
    "structure": "HHHHHHHHHCC"
  }'
```

The API returns:

```json
{
  "sequence": "MKTAAAAAAKG",
  "structure": "HHHHHHHHHCC",
  "pdb": "ATOM ..."
}
```

The returned PDB can be loaded directly into the Proteus molecular viewer.

---

# Designed Structure Pipeline

```text
User sequence
      │
      ▼
Secondary-structure specification
      │
      ▼
Structure generator
      │
      ▼
Backbone coordinates
      │
      ▼
PDB generation
      │
      ▼
3D molecular viewer
```

The generated structure currently represents a computationally constructed structure rather than an experimentally determined structure.

It should therefore be treated as a designed/generated model rather than experimental structural data.

---

# PDB Generation

Generated structures contain standard PDB `ATOM` records.

Example:

```text
ATOM      1  N   MET A   1       0.000   0.000   0.000
ATOM      2  CA  MET A   1       1.458   0.000   0.000
ATOM      3  C   MET A   1       1.990   0.000   1.429
ATOM      4  O   MET A   1       3.198   0.000   1.651
```

The generator currently produces backbone atoms:

```text
N
CA
C
O
```

for each residue.

The generated coordinates maintain peptide-bond geometry and provide a structure that can be consumed by molecular visualization tools.

---

# Structure Analysis vs Structure Design

Proteus distinguishes between experimentally determined structures and user-generated structures.

### Experimental structure

```text
RCSB PDB
   ↓
PDB coordinates
   ↓
DSSP
   ↓
Secondary structure
   +
Solvent accessibility
```

### Designed structure

```text
User sequence
   +
User structure specification
   ↓
Structure generator
   ↓
Generated PDB
   ↓
3D visualization
```

This separation is important because DSSP analysis is meaningful when applied to actual atomic coordinates, while the design endpoint creates coordinates from user-specified structural constraints.

---

# Error Handling

The backend returns HTTP errors when external or computational operations fail.

For example, if the DSSP executable is unavailable:

```json
{
  "detail": "mkdssp is not installed on the server."
}
```

If the PDB structure cannot be downloaded:

```json
{
  "detail": "Unable to download PDB structure: ..."
}
```

If DSSP itself fails:

```json
{
  "detail": "DSSP failed."
}
```

---

# Development

Start the development server with:

```bash
uvicorn main:app --reload
```

For a specific host and port:

```bash
uvicorn main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8000
```

Interactive API documentation is available at:

```text
/docs
```

---

# Example Workflow

A typical Proteus workflow is:

```text
1. User selects a PDB structure
          ↓
2. Frontend loads the structure
          ↓
3. User selects a chain
          ↓
4. Backend runs DSSP
          ↓
5. Residue-level results returned
          ↓
6. Frontend displays:
       • secondary structure
       • accessibility
       • residue table
          ↓
7. User selects a residue
          ↓
8. 3D viewer highlights the residue
```

For structure design:

```text
1. User enters sequence
          ↓
2. User specifies secondary structure
          ↓
3. Backend generates PDB
          ↓
4. Generated PDB is returned
          ↓
5. Frontend loads generated structure
          ↓
6. User explores the structure in 3D
```

---

# Design Goals

Proteus is intended to provide an interactive bridge between:

* protein sequence
* atomic structure
* secondary structure
* solvent accessibility
* residue-level analysis
* computational structure generation
* interactive 3D visualization

The backend focuses on keeping computational operations separate from visualization so that additional structural-analysis methods can be added independently.

---

# Current Capabilities

* [x] RCSB PDB retrieval
* [x] PDB parsing
* [x] DSSP integration
* [x] Secondary-structure assignment
* [x] Residue-level accessibility
* [x] Chain-aware analysis
* [x] Residue-level API output
* [x] User-defined sequence input
* [x] Secondary-structure constrained structure generation
* [x] PDB generation
* [x] Generated-structure visualization support

---

# Future Work

Potential extensions include:

* molecular surface analysis
* hydrogen-bond analysis
* residue contact maps
* distance matrices
* Ramachandran analysis
* structural alignment
* RMSD calculation
* ligand detection
* interface analysis
* residue interaction networks
* structure-quality metrics
* additional structure-generation methods
* computational protein-design models

---

## Project

**Proteus** — Interactive Protein Structure Analysis and Design Platform

The backend provides the computational services powering the Proteus web application.

```

This version deliberately presents the **structure generator as a computational/design component**, not as if it were a validated protein-folding model. That distinction will make the project description much more credible on a technical/research resume.
```
