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
# GitHub (e altri tool di clone/sync) collassa automaticamente una cartella fornitore che contiene
# UNA SOLA sottocartella prodotto in un'unica entry "cod_forn\cod_prod" (o con "/"). Questo regex
# rileva tale collassamento per poterlo gestire come coppia fornitore→prodotto invece che come
# anomalia di naming o fornitore non registrato.
COLLAPSED_SUPPLIER_PRODUCT_REGEX = re.compile(r"^(19\d{6})[\\/](.+)$")
# Aggiornata la whitelist dei file autorizzati nella root
KNOWN_ROOT_FILES = {
    "fornitori.csv", 
    "FINE SINGOLO PRODOTTO.txt",
    "CLAUDE.md",
    "CLAUDE.old",
    "check_integrita.py",
    "anomalies_log.json",
    "varianti_prodotto.csv",
    "riassunto_prodotti.xlsx",
}
SUPPLIER_WITH_LOOSE_FILE = "19010117"  # known legitimate loose .txt at Level 1
SUPPLIERS_WITHOUT_PHOTOS = {"19010770", "19010883"}  # DI TRIA, OBERTO: non forniscono foto prodotto, eccezione nota
# Eccezioni puntuali: singoli prodotti senza foto presso fornitori che invece
# la foto la forniscono normalmente per gli altri articoli (quindi non vanno
# esentati per intero, solo per questi specifici codici).
PRODOTTI_SENZA_FOTO_NOTI = {("19010890", "NOB060")}  # LATTE NOBILE: articolo senza foto disponibile
SYSTEM_DIRS = {"sofood"}  # known legitimate Level-0 config directories (not suppliers)

# File di sistema non pertinenti ai dati prodotto: metadata generati da Windows Explorer,
# macOS Finder, o strumenti di sync/versionamento. Vanno ignorati silenziosamente a QUALSIASI
# livello (root, L1, L2) — mai loggati come anomalia, mai conteggiati.
IRRELEVANT_SYSTEM_FILES = {"desktop.ini", ".ds_store", "thumbs.db", ".localized"}
# Nome file (case-insensitive) da rimuovere automaticamente e esplicitamente se rilevato.
AUTO_REMOVE_SYSTEM_FILES = {"desktop.ini"}


def is_irrelevant_system_file(filename: str) -> bool:
    return filename.lower() in IRRELEVANT_SYSTEM_FILES

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

def remove_desktop_ini_files(repo_root: str) -> list:
    """Cammina l'intero albero del repo e rimuove esplicitamente ogni desktop.ini
    rilevato (case-insensitive), a qualsiasi livello. Ritorna la lista dei path
    rimossi. Errori di rimozione (permessi, file già assente, ecc.) vengono
    catturati e loggati senza interrompere lo script."""
    removed = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        # non scendere in .git o simili
        dirnames[:] = [d for d in dirnames if not d.startswith(".git")]
        for fname in filenames:
            if fname.lower() in AUTO_REMOVE_SYSTEM_FILES:
                full_path = os.path.join(dirpath, fname)
                try:
                    os.remove(full_path)
                    removed.append(full_path)
                    print(f"  [INFO] Rimosso automaticamente: {full_path}")
                except OSError as exc:
                    print(f"  [WARN] Impossibile rimuovere {full_path}: {exc}")
    return removed

# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def validate_product_folder(folder_name: str, product_code: str, product_path: str, anomalies: list) -> None:
    """Validate the Level-2 contents of a single product folder.

    Appends anomalies in place. Shared between the normal nested-folder case
    (fornitore/prodotto) and the GitHub-collapsed single-child case
    (fornitore\\prodotto rendered as one folder).
    """
    has_txt = False
    has_jpg = False

    try:
        l2_items = list(os.scandir(product_path))
    except OSError as exc:
        # File di sistema non pertinenti (link rotti, permessi, ecc.) non devono far
        # crashare il validatore: logga e prosegui saltando questo prodotto.
        anomalies.append(make_entry(folder_name, product_code, product_path, "NAMING_VIOLATION"))
        print(f"  [WARN] Impossibile leggere {folder_name}/{product_code}: {exc} — prodotto saltato")
        return

    for l2_item in l2_items:
        fname = l2_item.name

        # Ignora file di sistema non pertinenti (desktop.ini, .DS_Store, Thumbs.db, ...)
        if is_irrelevant_system_file(fname):
            continue

        try:
            base, ext = os.path.splitext(fname)
            ext = ext.lower()
        except OSError:
            continue

        if ext == ".txt":
            if base == product_code:
                try:
                    empty = l2_item.stat().st_size == 0
                except OSError as exc:
                    anomalies.append(make_entry(folder_name, product_code, fname, "NAMING_VIOLATION"))
                    print(f"  [WARN] Impossibile leggere stat di {fname}: {exc}")
                    continue
                if empty:
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

    fornitore_esente = folder_name in SUPPLIERS_WITHOUT_PHOTOS
    prodotto_esente = (folder_name, product_code) in PRODOTTI_SENZA_FOTO_NOTI
    if not has_jpg and not (fornitore_esente or prodotto_esente):
        anomalies.append(make_entry(folder_name, product_code, f"{product_code}.jpg", "INCOMPLETE_PRIMARY_IMAGE"))
        print(f"  [ERROR] Missing primary image: {folder_name}/{product_code}/{product_code}.jpg")
    elif not has_jpg:
        motivo = "fornitore senza foto" if fornitore_esente else "eccezione puntuale prodotto"
        print(f"  [INFO] Foto assente in {folder_name}/{product_code} — eccezione nota ({motivo}), non loggata come anomalia")


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
    try:
        root_entries = list(os.scandir(repo_root))
    except OSError as exc:
        print(f"[FATAL] Impossibile leggere la root del repository: {exc}")
        sys.exit(1)

    for entry in root_entries:
        if entry.is_file():
            # Ignora file di sistema non pertinenti anche a livello root (fix: in
            # precedenza venivano erroneamente segnalati come NAMING_VIOLATION)
            if is_irrelevant_system_file(entry.name):
                continue
            if entry.name not in KNOWN_ROOT_FILES:
                anomalies.append(make_entry("UNKNOWN", "UNKNOWN", entry.name, "NAMING_VIOLATION"))
                print(f"  [WARN] Unexpected file at root: {entry.name}")

    # ------------------------------------------------------------------
    # 1. Level-1 — supplier folders
    # ------------------------------------------------------------------
    for l1_entry in sorted(root_entries, key=lambda e: e.name):
        if l1_entry.is_file():
            continue  # already handled above

        # Ignora cartelle nascoste e di sistema come .git o .vscode
        if l1_entry.name.startswith("."):
            continue

        if not l1_entry.is_dir():
            continue

        folder_name = l1_entry.name

        # Cartella di sistema (config logistica/anagrafica) — whitelisted, mai trattata come fornitore
        if folder_name in SYSTEM_DIRS:
            print(f"  [INFO] System config directory skipped from supplier validation: {folder_name}")
            continue

        # ------------------------------------------------------------------
        # Caso speciale: GitHub (o altro tool) ha collassato fornitore+prodotto
        # in un'unica cartella "cod_forn\cod_prod" perché il fornitore ha un
        # solo prodotto. La trattiamo direttamente come cartella di Livello 2.
        # ------------------------------------------------------------------
        collapsed_match = COLLAPSED_SUPPLIER_PRODUCT_REGEX.match(folder_name)
        if collapsed_match:
            collapsed_supplier, collapsed_product = collapsed_match.groups()

            if collapsed_supplier not in supplier_index:
                anomalies.append(make_entry(collapsed_supplier, collapsed_product, folder_name, "UNKNOWN_SUPPLIER"))
                print(f"  [ERROR] Supplier {collapsed_supplier} (collapsed folder) not found in fornitori.csv")
                continue

            print(f"  [INFO] Collapsed single-product supplier folder detected: {folder_name} "
                  f"→ treated as {collapsed_supplier}/{collapsed_product}")
            validate_product_folder(collapsed_supplier, collapsed_product, l1_entry.path, anomalies)
            continue

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
        try:
            l1_items = list(os.scandir(l1_entry.path))
        except OSError as exc:
            anomalies.append(make_entry(folder_name, "UNKNOWN", l1_entry.path, "NAMING_VIOLATION"))
            print(f"  [WARN] Impossibile leggere fornitore {folder_name}: {exc} — saltato")
            continue

        for l1_item in sorted(l1_items, key=lambda e: e.name):

            if l1_item.is_file():
                # Ignora file di sistema non pertinenti a Livello 1
                if is_irrelevant_system_file(l1_item.name):
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

            validate_product_folder(folder_name, product_code, product_path, anomalies)

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

    removed = remove_desktop_ini_files(repo_root)
    if removed:
        print(f"[INFO] desktop.ini rimossi automaticamente: {len(removed)}")
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
        print("EXIT CODE 1 — non-conforming products detected: agents must OMIT/SKIP the")
        print("flagged products (see anomalies_log.json) and PROCEED with all others (§R1 CLAUDE.md).")
        sys.exit(1)
    else:
        print("  No anomalies. Repository is structurally sound.")
        print("EXIT CODE 0 — pipeline may proceed.")
        sys.exit(0)

if __name__ == "__main__":
    main()