# CLAUDE.md — Repository Behavioral Directive
> **Scope:** Authoritative system prompt for any AI agent (Claude Code, Cursor, Windsurf) or human
> developer operating on this repository. **Read entirely before executing any task. All rules are
> mandatory and non-negotiable.**

---

## 0. AGENT DECISION FLOWCHART — Read First

```
START → item encountered in repo tree
│
├─ Is it at Level 0 (root)?
│   ├─ "fornitori.csv"             → LOAD into memory as supplier index
│   ├─ "FINE SINGOLO PRODOTTO.txt" → LOAD disclaimer text into memory (see §4 + §R3)
│   └─ any other file/folder       → FLAG anomaly → SKIP
│
├─ Is it at Level 1 (inside root)?
│   ├─ Is it a directory?
│   │   ├─ name matches ^19\d{6}$ AND found in fornitori.csv → DESCEND into Level 2
│   │   └─ otherwise               → FLAG UNREGISTERED_SUPPLIER → SKIP (await operator)
│   └─ Is it a loose file?         → FLAG appendix/anomaly → SKIP (never treat as product)
│       └─ Exception: 19010117/ loose .txt → store as supplier metadata, skip from pipeline
│
└─ Is it at Level 2 (inside a supplier folder)?
    ├─ Is it a directory?          → PROCESS as product entry (see §2 + §RULEBOOK)
    └─ Is it a loose file?         → FLAG anomaly → SKIP
```

**Pre-pipeline mandatory gate:**
```
RUN: python check_integrita.py
  exit 0 → proceed
  exit 1 → HALT, read error output, request operator intervention
```

---

## 1. Repository Purpose

Stores product data (text + images) for food products from partner suppliers. Dual use:
- **E-commerce ingestion** — bulk import pipeline
- **AI model training** — product recognition and description

**All agents operate in READ-ONLY mode.** Writing, renaming, moving, or deleting any file or
directory inside the repository tree is strictly forbidden. All outputs must be written to paths
**outside** the repository tree, explicitly specified by the operator.

---

## 2. Repository Architecture — 3-Level Tree

```
PRODOTTI SOFOOD/                          ← LEVEL 0 — root
├── fornitori.csv                         ← supplier master dictionary
├── FINE SINGOLO PRODOTTO.txt             ← global legal disclaimer (load, do not skip)
├── {an_forn}/                            ← LEVEL 1 — supplier folder (8-digit, starts with 19)
│   └── {PRODUCT_CODE}/                   ← LEVEL 2 — product folder
│       ├── {PRODUCT_CODE}.txt            ← product data (mandatory)
│       ├── {PRODUCT_CODE}.jpg            ← primary image (mandatory)
│       ├── {PRODUCT_CODE}.pdf            ← technical datasheet (optional)
│       └── {PRODUCT_CODE}_*.jpg          ← secondary images (optional)
```

### 2.1 File Matrix — Naming, Requirements & Content

| File Pattern | Required | Naming Invariant Rule | Content Specification & Guardrails |
|---|---|---|---|
| `{CODE}.txt` | ✅ Yes | Exact folder name + `.txt` | Commercial name, description, ingredients, nutritional values, producer info, certifications (DOP, BIO, IGP…). **After parsing, apply disclaimer deduplication (§R3).** Empty file (0 bytes) = `INCOMPLETE_TEXT`. |
| `{CODE}.jpg` | ✅ Yes | Exact folder name + `.jpg` | Primary product photograph (front-facing / packshot). Absence = `INCOMPLETE_PRIMARY_IMAGE`. |
| `{CODE}.pdf` | ⬜ No | Exact folder name + `.pdf` | Producer technical datasheet (scheda tecnica). Supplementary source only; never replaces `.txt`. Absence must not trigger any flag. Any `.pdf` whose name does not exactly match `{CODE}.pdf` = `NAMING_VIOLATION`. |
| `{CODE}_2.jpg`, `{CODE}_3.jpg`, … `{CODE}_{N}.jpg` | ⬜ No | `{CODE}` + `_` + numeric suffix | Secondary photographs (back label, detail, variant…). Sort alphanumerically after primary. |
| `{CODE}_{label}.jpg` | ⬜ No | `{CODE}` + `_` + lowercase alphanumeric label (no spaces) | Descriptive secondary image (e.g. `_retro`, `_detail`, `_label`). Same sort rule as above. |
| Any file not matching `{CODE}*` | ❌ Invalid | — | `NAMING_VIOLATION` → append to `anomalies_log.json`, exclude from pipeline. |

---

## 3. Supplier Master Dictionary — `fornitori.csv`

Schema: `nome_azienda, an_forn, an_descr1, an_descr2`

| Column | Type | Description |
|---|---|---|
| `nome_azienda` | string | Commercial/brand name (use as display name; split on ` \| ` for multi-brand entries) |
| `an_forn` | string (8-digit) | Supplier code → matches Level 1 folder name |
| `an_descr1` | string | Official legal name (ragione sociale) |
| `an_descr2` | string \| null | Secondary legal entity (present only for some suppliers) |

**Known edge cases:**
- **Multi-brand supplier (`19010004`):** `nome_azienda` = `"Amodio | Conserve Gentile | Forni Gentile | Pastificio Gentile"`. Split on ` | `; each token is a valid brand alias for the same `an_forn`.
- **Dual legal entity (`19010901`):** both `an_descr1 = FILIERA FOOD SRL` and `an_descr2 = AZIENDA AGRICOLA CAPUANO` are valid legal names for the same folder.

**Lookup procedure:**
```
1. Load fornitori.csv → build index { an_forn → { nome_azienda, an_descr1, an_descr2 } }
2. For each Level 1 folder:
   - name matches ^19\d{6}$ AND found in index → use nome_azienda as display name
   - fails regex OR not found → FLAG UNREGISTERED_SUPPLIER, skip without operator confirmation
```

---

## 4. Special Files — Appendices & Service Files

- **`FINE SINGOLO PRODOTTO.txt` (Level 0):** Global legal disclaimer applicable to all products.
  **Do NOT skip.** At pipeline startup, load its full text into memory as `DISCLAIMER_TEXT`.
  Apply deduplication logic during product parsing (§R3).

- **Loose `.txt` file in `19010117/` (Level 1):** Shelf-life and conservation notes for supplier
  Agricola Buongiorno. It sits directly inside the supplier folder, not inside any product
  subfolder. Detect via `item.is_file()` check; store as supplier-level metadata, exclude from
  product pipeline. General rule: at Level 1, only **directories** are valid product entries.

---

## AGENT RULEBOOK

### R1 — Pre-Pipeline Mandatory Gate

Before executing any extraction, import, or training pipeline, the agent **MUST** run:

```bash
python check_integrita.py
```

- **Exit code 0:** repository is structurally sound → proceed.
- **Exit code 1:** structural anomalies detected → **HALT immediately**. Read the terminal output
  and `anomalies_log.json`. Do not proceed until the operator has reviewed and resolved all issues.

This check is not optional and cannot be bypassed.

---

### R2 — Anomaly Logging Protocol

Every structural or naming anomaly **must** be appended to `anomalies_log.json` (at the external
path specified by the operator). **Never use generic text flags.**

**Schema per entry:**
```json
{
  "supplier": "an_forn value or UNKNOWN",
  "product": "PRODUCT_CODE or UNKNOWN",
  "file": "filename or path that triggered the anomaly",
  "error_type": "INCOMPLETE_TEXT | INCOMPLETE_PRIMARY_IMAGE | NAMING_VIOLATION | UNKNOWN_SUPPLIER | UNREGISTERED_SUPPLIER",
  "timestamp": "ISO 8601 datetime, e.g. 2025-06-15T14:32:00Z"
}
```

Append-only. Never overwrite or truncate the log between runs.

---

### R3 — Legal Disclaimer Deduplication

At pipeline startup:
1. Read `FINE SINGOLO PRODOTTO.txt` from the repository root.
2. Store its full text as `DISCLAIMER_TEXT` in memory.

For each `{PRODUCT_CODE}.txt` parsed:
- If `DISCLAIMER_TEXT` is **not** present verbatim in the file content → **append** it to the end
  of the extracted description before writing to output. Do not modify the source file.
- If `DISCLAIMER_TEXT` **is already present** → output the content unchanged.

---

### R4 — Standardized Output Schema (E-commerce Export)

All keys required; use `null` for absent optional values.

```json
{
  "sku": "an_forn/PRODUCT_CODE",
  "nome_commerciale": "string",
  "descrizione": "string (with disclaimer appended if needed per R3)",
  "ingredienti": "string | null",
  "valori_nutrizionali": "string | null",
  "info_produttore": "string | null",
  "certificazioni": ["string"],
  "immagine_principale": "relative path to {CODE}.jpg",
  "immagini_secondarie": ["relative path", "..."],
  "scheda_tecnica_pdf": "relative path to {CODE}.pdf | null"
}
```

---

### R5 — Image Extraction Rules

- **Primary image:** select exclusively `{CODE}.jpg`.
- **All images:** select all `.jpg` files whose base name starts with `{CODE}`, sort primary first,
  secondaries alphanumerically.
- `.jpg` files not starting with `{CODE}` → `NAMING_VIOLATION`, log and exclude.

---

### R6 — READ-ONLY Guardrail

Agents must never rename, move, delete, or create any file or directory inside the repository tree,
and must never write logs, outputs, or temporary files inside it. All outputs go to an external
path explicitly provided by the operator before pipeline execution begins.

---

## 5. Quick Reference

```
┌──────────────────────────────────────────────────────────────────────┐
│  WHAT YOU FIND               │  WHAT IT IS          │  ACTION        │
├──────────────────────────────┼──────────────────────┼────────────────┤
│  fornitori.csv (root)        │  Supplier index       │  LOAD          │
│  FINE SINGOLO PRODOTTO.txt   │  Legal disclaimer     │  LOAD (§R3)    │
│  19010117/ loose .txt        │  Supplier note        │  STORE, SKIP   │
│  19XXXXXX/ folder            │  Supplier             │  LOOKUP CSV    │
│  19XXXXXX/{CODE}/ dir        │  Product entry        │  PROCESS       │
│  {CODE}.txt inside dir       │  Product data         │  READ + §R3    │
│  {CODE}.jpg inside dir       │  Primary image        │  READ          │
│  {CODE}.pdf inside dir       │  Technical sheet      │  READ (opt.)   │
│  {CODE}_*.jpg inside dir     │  Secondary images     │  READ          │
│  Any file at L2 w/o {CODE}   │  Naming anomaly       │  LOG + SKIP    │
│  Unrecognised L1 folder      │  Unknown supplier     │  FLAG + HALT   │
└──────────────────────────────┴──────────────────────┴────────────────┘
```

---

## 6. External Tooling

| Tool | Purpose | Trigger |
|---|---|---|
| `check_integrita.py` | Deterministic structural validation of the full repository | Mandatory before any pipeline (§R1) |
| `anomalies_log.json` | Append-only structured anomaly log | Written by agents and `check_integrita.py`; reviewed by operator on exit code 1 |
