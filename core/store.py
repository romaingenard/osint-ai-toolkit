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