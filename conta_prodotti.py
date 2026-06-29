import os
import re
import csv

def carica_nomi_fornitori(repo_root):
    """Legge il file fornitori.csv e crea un dizionario {codice: nome_azienda}"""
    csv_path = os.path.join(repo_root, 'fornitori.csv')
    mappa_fornitori = {}
    
    if not os.path.isfile(csv_path):
        print(f"[ATTENZIONE] File {csv_path} non trovato. Verranno mostrati solo i codici.\n")
        return mappa_fornitori
        
    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                codice = row.get('an_forn', '').strip()
                nome = row.get('nome_azienda', '').strip()
                if codice:
                    # Se ci sono più brand separati da ' | ', prende solo il primo per il report
                    nome_principale = nome.split(' | ')[0] if ' | ' in nome else nome
                    mappa_fornitori[codice] = nome_principale
    except Exception as e:
        print(f"[ERRORE] Impossibile leggere fornitori.csv: {e}\n")
        
    return mappa_fornitori

def conta_prodotti_completati(repo_root):
    supplier_regex = re.compile(r"^19\d{6}$")
    totale_prodotti = 0
    dettaglio_fornitori = {}
    
    # 1. Carica le anagrafiche dal CSV
    mappa_nomi = carica_nomi_fornitori(repo_root)

    print(f"Avvio conteggio nella directory: {repo_root}\n")

    # 2. Livello 1: Ricerca cartelle Fornitori
    for l1_entry in os.scandir(repo_root):
        if l1_entry.is_dir() and supplier_regex.match(l1_entry.name):
            codice_fornitore = l1_entry.name
            prodotti_per_questo_fornitore = 0
            
            # 3. Livello 2: Ricerca cartelle Prodotti
            for l2_entry in os.scandir(l1_entry.path):
                if l2_entry.is_dir():
                    
                    # 4. Livello 3: Ricerca del file .txt del prodotto
                    ha_txt = False
                    for l3_entry in os.scandir(l2_entry.path):
                        if l3_entry.is_file() and l3_entry.name.lower().endswith('.txt'):
                            if not l3_entry.name.startswith('.'):
                                ha_txt = True
                                break # Ne basta uno per confermare che il prodotto esiste
                    
                    if ha_txt:
                        prodotti_per_questo_fornitore += 1
                        totale_prodotti += 1
            
            if prodotti_per_questo_fornitore > 0:
                dettaglio_fornitori[codice_fornitore] = prodotti_per_questo_fornitore

    # 5. Stampa dei risultati
    print("=== DETTAGLIO PER FORNITORE ===")
    
    # Ordina i fornitori per codice crescente
    for codice, conteggio in sorted(dettaglio_fornitori.items()):
        # Recupera il nome dell'azienda, se non esiste nel CSV scrive "NOME SCONOSCIUTO"
        nome_azienda = mappa_nomi.get(codice, "NOME SCONOSCIUTO")
        
        # Allinea a destra i numeri per rendere la colonna leggibile
        print(f"[{codice}] {nome_azienda:<35} : {conteggio:>3} prodotti")

    print("\n" + "="*55)
    print(f"TOTALE PRODOTTI ELABORATI: {totale_prodotti}")
    print("="*55)

if __name__ == "__main__":
    cartella_corrente = os.getcwd()
    conta_prodotti_completati(cartella_corrente)