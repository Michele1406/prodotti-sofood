# CLAUDE.md — Repository Structural Configuration

> **Scope:** This file is the authoritative reference for any AI agent (Claude Code, Cursor, Windsurf, etc.)
> or human developer operating on this repository. Read it entirely before performing any task.
> All rules defined here are **mandatory and non-negotiable**.

---

## 1. Repository Purpose

This repository stores product data (textual descriptions and images) for food products supplied by
partner companies. The data is intended for:

- Bulk import into an e-commerce platform.
- AI model training for product recognition and description.

**Operational mode for all agents: READ-ONLY.** See Section 5 for strict guardrails.

---

## 2. Repository Architecture — 3-Level Tree (Strict)

```
PRODOTTI SOFOOD/                          ← LEVEL 0 — Repository root
│
├── fornitori.csv                         ← MASTER DICTIONARY (see Section 3)
├── FINE SINGOLO PRODOTTO.txt             ← SERVICE FILE (see Section 4)
│
├── {an_forn}/                            ← LEVEL 1 — Supplier folder
│   │   Name format : 8-digit numeric code, always starting with 19
│   │   Example     : 19010004, 19010679, 19010843
│   │   Meaning     : uniquely identifies one supplier legal entity
│   │   Lookup      : resolve via fornitori.csv → column `an_forn`
│   │
│   ├── {PRODUCT_CODE}/                   ← LEVEL 2 — Product subfolder
│   │   │   Name format : alphanumeric code assigned by the supplier
│   │   │   Examples    : 001, 002, AN54402, AN54400, PG-001
│   │   │   Invariant   : folder name == file names (without extension)
│   │   │
│   │   ├── {PRODUCT_CODE}.txt            ← Product description file
│   │   └── {PRODUCT_CODE}.jpg            ← Product image file
│   │
│   └── {PRODUCT_CODE}/                   ← next product, same pattern
│
└── {an_forn}/                            ← next supplier, same pattern
```

### 2.1 Core Naming Invariant



> **The base name of every file inside a product folder is derived from the name of that folder.**



Every product folder contains **one mandatory primary image** and **one mandatory text file**.

Secondary images are optional but, if present, must follow the naming convention below.



| File | Required | Naming rule |

|---|---|---|

| `{PRODUCT_CODE}.txt` | ✅ Mandatory | Exact folder name + `.txt` |

| `{PRODUCT_CODE}.jpg` | ✅ Mandatory | Exact folder name + `.jpg` — PRIMARY image |

| `{PRODUCT_CODE}_2.jpg` | ⬜ Optional | Primary name + `_2` suffix — first secondary image |

| `{PRODUCT_CODE}_3.jpg` | ⬜ Optional | Primary name + `_3` suffix — second secondary image |

| `{PRODUCT_CODE}_{N}.jpg` | ⬜ Optional | Pattern continues incrementally for further images |

| `{PRODUCT_CODE}_{label}.jpg` | ⬜ Optional | Descriptive suffix allowed (e.g. `_retro`, `_detail`, `_label`) |



**Concrete example — folder `AN54402/`:**

Any `.jpg` file whose base name does **not** start with `{PRODUCT_CODE}` is a **naming violation**.

Log the anomaly and skip the file; do not silently include it in pipelines.



---



### 2.2 File Content Specification



| File | Content |

|---|---|

| `{PRODUCT_CODE}.txt` | Commercial name, description, ingredients, nutritional values, producer info, certifications (DOP, BIO, IGP, …) |

| `{PRODUCT_CODE}.jpg` | Primary product photograph (front-facing or packshot) |

| `{PRODUCT_CODE}_2.jpg` … `{PRODUCT_CODE}_{N}.jpg` | Secondary photographs (back label, detail, variant, etc.) |

| `{PRODUCT_CODE}_{label}.jpg` | Secondary photograph with descriptive suffix; `{label}` is a lowercase alphanumeric string with no spaces |



**Agent rules for image handling:**

- When extracting the **primary image**, select exclusively the file named `{PRODUCT_CODE}.jpg`.

- When extracting **all images**, select all `.jpg` files whose base name starts with `{PRODUCT_CODE}`, then sort: primary first (`{PRODUCT_CODE}.jpg`), secondaries in alphanumeric order.

- A product folder with **no** `{PRODUCT_CODE}.jpg` is `INCOMPLETE_PRIMARY_IMAGE` — flag it.

- A product folder with **no** `{PRODUCT_CODE}.txt` is `INCOMPLETE_TEXT` — flag it.

- Extra `.jpg` files not matching the `{PRODUCT_CODE}*` prefix are `NAMING_VIOLATION` — flag and exclude. 

---

## 3. Master Dictionary — `fornitori.csv`

### 3.1 Mandatory lookup rule

> **Every time an agent processes a supplier folder (`{an_forn}/`), it MUST resolve the numeric
> code to the supplier name by reading `fornitori.csv`.** Never hardcode supplier names; the CSV
> is the single source of truth.

### 3.2 CSV schema

```
nome_azienda,an_forn,an_descr1,an_descr2
```

| Column | Type | Description |
|---|---|---|
| `nome_azienda` | string | Commercial/brand name used in this repository |
| `an_forn` | string (8-digit) | Numeric supplier code → matches the Level 1 folder name |
| `an_descr1` | string | Official legal company name (ragione sociale) |
| `an_descr2` | string (nullable) | Secondary legal entity or trade name, present only for some suppliers |

### 3.3 Known edge cases in `fornitori.csv`

**Multiple brands under one legal entity (`19010004`):**
```
nome_azienda                                          an_forn    an_descr1
Amodio | Conserve Gentile | Forni Gentile | Pastificio Gentile  19010004  PASTIFICIO GENTILE SRL
```
The `nome_azienda` field uses ` | ` as a delimiter between brand names. When displaying or
filtering by brand, split on ` | ` and treat each token as a distinct brand alias for the same
supplier code.

**Supplier with two legal entities (`19010901`):**
```
nome_azienda   an_forn    an_descr1          an_descr2
Capuano        19010901   FILIERA FOOD SRL   AZIENDA AGRICOLA CAPUANO
```
Both `an_descr1` and `an_descr2` are valid legal names for the same supplier folder.

### 3.4 Recommended lookup procedure

```
1. Read fornitori.csv into memory at the start of any batch operation.
2. Build an index: { an_forn → { nome_azienda, an_descr1, an_descr2 } }
3. For each Level 1 folder found on disk:
     a. Extract folder name as `code`.
     b. Lookup code in the index.
     c. If found     → use nome_azienda as the display name.
     d. If NOT found → flag as UNKNOWN_SUPPLIER, continue processing.
```

---

## 4. Special Files and Appendices — Not Products

The following files exist in the repository but are **not product entries**. They must be
**excluded from every product loop, import pipeline, and training dataset**.

### 4.1 `FINE SINGOLO PRODOTTO.txt` — Root level

| Property | Value |
|---|---|
| **Path** | `PRODOTTI SOFOOD/FINE SINGOLO PRODOTTO.txt` |
| **Level** | 0 — Repository root |
| **Type** | Service file / legal appendix |
| **Content** | Global legal disclaimers and purchase notes applicable to all products |
| **Agent rule** | Skip unconditionally. Never interpret as a product. Never include in batch loops. |

### 4.2 Shelf-life notes file — Inside `19010117/`

| Property | Value |
|---|---|
| **Path** | `PRODOTTI SOFOOD/19010117/{filename}.txt` where the file is **not inside a product subfolder** |
| **Level** | 1 — Directly inside the supplier folder, alongside product subfolders |
| **Type** | Supplier-specific textual appendix |
| **Content** | Shelf-life and storage/conservation notes specific to supplier Agricola Buongiorno |
| **Agent rule** | When iterating items inside `19010117/`: check whether each item is a **directory** (→ product entry) or a **loose file** (→ appendix, skip). Only directories are valid product entries. |

### 4.3 Detection logic for special files (pseudocode)

```python
for item in supplier_folder.iterdir():
    if item.is_dir():
        process_as_product(item)          # standard product entry
    elif item.is_file():
        log_as_appendix(item)             # service file, skip from product pipeline
        # optionally store content as supplier-level metadata
```

---

## 5. Strict System Guardrails — Mandatory for All Agents

### 5.1 READ-ONLY mode

> **Agents MUST NOT modify, rename, move, delete, or create any file or directory in this
> repository.** The only permitted operations are read and analysis.

Prohibited operations (non-exhaustive list):

- Renaming files or folders for any reason, including "normalization" or "correction".
- Creating new files (logs, outputs, temporary files) inside the repository tree.
- Altering file content, even to fix encoding or formatting issues.
- Moving files between folders.

If an output must be produced (report, export, transformed data), write it **outside** the
repository tree to a path explicitly specified by the operator.

### 5.2 Loop integrity rules

- **Never include special files** (`FINE SINGOLO PRODOTTO.txt`, loose files in `19010117/`) in
  product iteration loops. Inclusion would corrupt counts, imports, and training datasets.
- **Always verify both files exist** (`{CODE}.txt` AND `{CODE}.jpg`) before treating a product
  folder as complete. Missing either file → flag as `INCOMPLETE`, do not silently skip.
- **Do not assume folder depth.** Always explicitly check that an item is at Level 2 (inside a
  Level 1 supplier folder) before treating it as a product. Items found directly at Level 0 or
  Level 1 that are not directories are service files.

### 5.3 Supplier code validation

A valid Level 1 folder name satisfies **all** of the following:

- Matches the regex `^19\d{6}$` (8 digits, starts with `19`).
- Is present as a value in the `an_forn` column of `fornitori.csv`.

If a folder at Level 1 fails either check, flag it as `UNREGISTERED_SUPPLIER` and do not process
its contents without explicit operator confirmation.

---

## 6. Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│  WHAT YOU FIND          │  WHAT IT IS       │  ACTION        │
├─────────────────────────┼───────────────────┼────────────────┤
│  Root loose .txt file   │  Legal appendix   │  SKIP          │
│  19010117/ loose .txt   │  Supplier note    │  SKIP          │
│  19XXXXXX/ folder       │  Supplier         │  LOOKUP in CSV │
│  19XXXXXX/{CODE}/ dir   │  Product entry    │  PROCESS       │
│  {CODE}.txt inside dir  │  Product data     │  READ          │
│  {CODE}.jpg inside dir  │  Product image    │  READ          │
│  Any file at Level 2    │  Anomaly          │  FLAG + SKIP   │
│   without {CODE} prefix │                   │                │
└─────────────────────────┴───────────────────┴────────────────┘
```

---

## 7. Integrity Self-Check — Run Before Any Batch Operation

Before starting any bulk task, an agent should verify the repository state by checking:

1. `fornitori.csv` is readable and contains at least the columns `nome_azienda`, `an_forn`, `an_descr1`.
2. Every Level 1 folder name matches `^19\d{6}$`.
3. Every Level 1 folder name resolves in `fornitori.csv`.
4. Every Level 2 folder contains at least {CODE}.txt and {CODE}.jpg. Extra images must start with {CODE}_ (flag exceptions, do not abort).
5. No files exist at Level 1 except the known appendix in `19010117/` (flag any others as anomalies).

Report findings before proceeding. Abort only if `fornitori.csv` is missing or unreadable.
