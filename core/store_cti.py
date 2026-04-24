"""core/store_cti.py — persistance SQLite du pipeline CTI (enrichissements IoC).

Renommé depuis core/store.py le 24 avril 2026 dans le cadre de la refonte LI
(sujet Sahel). Schéma strictement CTI — le corpus LI vit dans li/store_li.py
et data/corpus.db, avec un schéma complètement distinct.

Contrat raw_response : insert_enrichment lit data["raw_response"] et le
sérialise en JSON. Si l'appelant (core/collect.py) ne fournit pas ce champ,
on stocke un dict vide JSON — pas d'erreur. L'appelant peut enrichir data
avec `data["raw_response"] = response.json()` avant l'insert s'il veut
conserver la réponse brute de l'API externe. À date, core/collect.py ne
peuple pas raw_response : le comportement actuel est donc de stocker {}.
"""

import sqlite3
import json
from datetime import datetime


DB_PATH = "data/enrichments.db"

def create_table(db_path=DB_PATH) :
    conn = sqlite3.connect(db_path)

    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrichments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ioc TEXT NOT NULL,
            ioc_type TEXT NOT NULL,
            source TEXT NOT NULL,
            raw_data TEXT,
            enriched_at TEXT NOT NULL,
            malicious_count INTEGER,
            country TEXT,
            as_owner TEXT
        )
    """)
    conn.commit()
    conn.close()


def insert_enrichment(data, db_path=DB_PATH) :
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    enriched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_json = json.dumps(data.get("raw_response", {}))
    cursor.execute("""
        INSERT INTO enrichments (ioc, ioc_type, source, raw_data, enriched_at, malicious_count, country, as_owner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("ioc"),
            data.get("ioc_type"),
            data.get("source"),
            raw_json,
            enriched_at,
            data.get("malicious_count"),
            data.get("country"),
            data.get("as_owner")
    ))
    conn.commit()
    conn.close()


def query_enrichments(ioc=None, source=None, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM enrichments WHERE 1=1"
    params = []
    if ioc:
        query += " AND ioc = ?"
        params.append(ioc)
    if source:
        query += " AND source = ?"
        params.append(source)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows