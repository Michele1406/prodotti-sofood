#!/usr/bin/env python3
"""
check_integrita.py — Structural validator for PRODOTTI SOFOOD repository.

Usage:
    python check_integrita.py [REPO_ROOT] [--log PATH]

Exit codes:
    0   Repository is structurally sound.
    1   One or more anomalies detected. Details printed to stdout and appended to log.
"""

import os
import sys
import re
import csv
import json
import datetime
import argparse
from collections import Counter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPLIER_REGEX = re.compile(r"^19\d{6}$")
# Aggiornata la whitelist dei file autorizzati nella root
KNOWN_ROOT_FILES = {
    "fornitori.csv", 
    "FINE SINGOLO PRODOTTO.txt",
    "CLAUDE.md",
    "CLAUDE.old",
    "check_integrita.py",
    "anomalies_log.json"
}
SUPPLIER_WITH_LOOSE_FILE = "19010117"  # known legitimate loose .txt at Level 1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    # Aggiornato per rimuovere il DeprecationWarning di datetime.utcnow()
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def make_entry(supplier: str, product: str, file: str, error_type: str) -> dict:
    return {
        "supplier": supplier,
        "product": product,
        "file": file,
        "error_type": error_type,
        "timestamp": now_iso(),
    }

def append_log(log_path: str, entries: list) -> None:
    """Append entries to anomalies_log.json (creates file if absent)."""
    existing = []
    if os.path.isfile(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []
    existing.extend(entries)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

def load_supplier_index(fornitori_path: str) -> dict:
    """Build { an_forn -> { nome_azienda, an_descr1, an_descr2 } } from CSV."""
    index = {}
    with open(fornitori_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"nome_azienda", "an_forn", "an_descr1"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                f"fornitori.csv is missing required columns. "
                f"Found: {reader.fieldnames}. Required: {required}"
            )
        for row in reader:
            code = row["an_forn"].strip()
            index[code] = {
                "nome_azienda": row.get("nome_azienda", "").strip(),
                "an_descr1": row.get("an_descr1", "").strip(),
                "an_descr2": row.get("an_descr2", "").strip(),
            }
    return index

# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def validate_repo(repo_root: str) -> list:
    anomalies = []

    # ------------------------------------------------------------------
    # 0. Root — load fornitori.csv (fatal if missing or malformed)
    # ------------------------------------------------------------------
    fornitori_path = os.path.join(repo_root, "fornitori.csv")
    if not os.path.isfile(fornitori_path):
        print("[FATAL] fornitori.csv not found at repository root. Aborting.")
        sys.exit(1)

    try:
        supplier_index = load_supplier_index(fornitori_path)
    except ValueError as exc:
        print(f"[FATAL] {exc}")
        sys.exit(1)

    # Flag unexpected files at root
    for entry in os.scandir(repo_root):
        if entry.is_file() and entry.name not in KNOWN_ROOT_FILES:
            anomalies.append(make_entry("UNKNOWN", "UNKNOWN", entry.name, "NAMING_VIOLATION"))
            print(f"  [WARN] Unexpected file at root: {entry.name}")

    # ------------------------------------------------------------------
    # 1. Level-1 — supplier folders
    # ------------------------------------------------------------------
    for l1_entry in sorted(os.scandir(repo_root), key=lambda e: e.name):
        if l1_entry.is_file():
            continue  # already handled above

        # Ignora cartelle nascoste e di sistema come .git o .vscode
        if l1_entry.name.startswith("."):
            continue

        if not l1_entry.is_dir():
            continue

        folder_name = l1_entry.name

        if not SUPPLIER_REGEX.match(folder_name):
            anomalies.append(make_entry(folder_name, "UNKNOWN", folder_name, "UNREGISTERED_SUPPLIER"))
            print(f"  [ERROR] Level-1 folder does not match supplier pattern: {folder_name}")
            continue

        if folder_name not in supplier_index:
            anomalies.append(make_entry(folder_name, "UNKNOWN", folder_name, "UNKNOWN_SUPPLIER"))
            print(f"  [ERROR] Supplier {folder_name} not found in fornitori.csv")
            continue

        # ------------------------------------------------------------------
        # 2. Level-1 contents — dirs are products, files are appendices
        # ------------------------------------------------------------------
        for l1_item in sorted(os.scandir(l1_entry.path), key=lambda e: e.name):

            if l1_item.is_file():
                # Ignora file di sistema come desktop.ini a Livello 1
                if l1_item.name.lower() in ("desktop.ini", ".ds_store"):
                    continue
                    
                if folder_name == SUPPLIER_WITH_LOOSE_FILE and l1_item.name.endswith(".txt"):
                    print(f"  [INFO] Supplier appendix in {folder_name}: {l1_item.name} — skipped from pipeline.")
                else:
                    anomalies.append(make_entry(folder_name, "UNKNOWN", l1_item.name, "NAMING_VIOLATION"))
                    print(f"  [WARN] Loose file at Level 1 in {folder_name}: {l1_item.name}")
                continue

            if not l1_item.is_dir():
                continue

            # ------------------------------------------------------------------
            # 3. Level-2 — product folder
            # ------------------------------------------------------------------
            product_code = l1_item.name
            product_path = l1_item.path

            has_txt = False
            has_jpg = False

            for l2_item in os.scandir(product_path):
                fname = l2_item.name
                
                # Ignora file di sistema come desktop.ini dentro le cartelle dei prodotti
                if fname.lower() in ("desktop.ini", ".ds_store"):
                    continue
                    
                base, ext = os.path.splitext(fname)
                ext = ext.lower()

                if ext == ".txt":
                    if base == product_code:
                        if l2_item.stat().st_size == 0:
                            anomalies.append(make_entry(folder_name, product_code, fname, "INCOMPLETE_TEXT"))
                            print(f"  [ERROR] Empty .txt: {folder_name}/{product_code}/{fname}")
                        else:
                            has_txt = True
                    else:
                        anomalies.append(make_entry(folder_name, product_code, fname, "NAMING_VIOLATION"))
                        print(f"  [WARN] Unexpected .txt in {folder_name}/{product_code}: {fname}")

                elif ext == ".jpg":
                    if base == product_code:
                        has_jpg = True
                    elif base.startswith(product_code + "_"):
                        pass  # valid secondary image
                    else:
                        anomalies.append(make_entry(folder_name, product_code, fname, "NAMING_VIOLATION"))
                        print(f"  [WARN] NAMING_VIOLATION .jpg in {folder_name}/{product_code}: {fname}")

                elif ext == ".pdf":
                    if base != product_code:
                        anomalies.append(make_entry(folder_name, product_code, fname, "NAMING_VIOLATION"))
                        print(f"  [WARN] NAMING_VIOLATION .pdf in {folder_name}/{product_code}: {fname}")

                else:
                    anomalies.append(make_entry(folder_name, product_code, fname, "NAMING_VIOLATION"))
                    print(f"  [WARN] Unknown file type in {folder_name}/{product_code}: {fname}")

            if not has_txt:
                anomalies.append(make_entry(folder_name, product_code, f"{product_code}.txt", "INCOMPLETE_TEXT"))
                print(f"  [ERROR] Missing .txt: {folder_name}/{product_code}/{product_code}.txt")

            if not has_jpg:
                anomalies.append(make_entry(folder_name, product_code, f"{product_code}.jpg", "INCOMPLETE_PRIMARY_IMAGE"))
                print(f"  [ERROR] Missing primary image: {folder_name}/{product_code}/{product_code}.jpg")

    return anomalies

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Structural integrity validator for PRODOTTI SOFOOD repository."
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=os.getcwd(),
        help="Path to the repository root (default: current directory).",
    )
    parser.add_argument(
        "--log",
        default="anomalies_log.json",
        metavar="PATH",
        help="Path to anomalies_log.json (default: ./anomalies_log.json).",
    )
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    log_path = os.path.abspath(args.log)

    if not os.path.isdir(repo_root):
        print(f"[FATAL] Repository root not found: {repo_root}")
        sys.exit(1)

    print("=== check_integrita.py ===")
    print(f"Repository : {repo_root}")
    print(f"Anomaly log: {log_path}")
    print(f"Started    : {now_iso()}")
    print("")

    anomalies = validate_repo(repo_root)

    print("")
    print("=== Summary ===")
    print(f"Total anomalies found: {len(anomalies)}")

    if anomalies:
        counts = Counter(a["error_type"] for a in anomalies)
        for etype, count in sorted(counts.items()):
            print(f"  {etype}: {count}")
        append_log(log_path, anomalies)
        print(f"\nAnomalies appended to: {log_path}")
        print("EXIT CODE 1 — pipeline must not proceed.")
        sys.exit(1)
    else:
        print("  No anomalies. Repository is structurally sound.")
        print("EXIT CODE 0 — pipeline may proceed.")
        sys.exit(0)

if __name__ == "__main__":
    main()