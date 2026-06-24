#!/usr/bin/env python3
"""Audit qualitatif DISARM (Centaure) — export LECTURE SEULE d'un echantillon.

10 articles tires au hasard (uniforme, graine fixe) dans le corpus final
classifie, avec contenu integral (codage manuel) + classification LLM complete
(comparaison). SELECT uniquement, aucune ecriture en base, aucun commit.
"""
import csv
import random
import sqlite3
import sys

DB = "data/corpus.db"
OUT = "outputs/audit_disarm_echantillon_2026-06-18.csv"
SEED = 20260618
N = 10
EXPECTED_POP = 223

QUERY = """
SELECT
    a.article_id,
    a.date_published,
    a.entity_id,
    e.name              AS entity_name,
    e.producer_category,
    e.country,
    a.title,
    a.text_content      AS content,
    c.disarm_techniques,
    c.disarm_tactic_code,
    c.disarm_tactic_name,
    c.disarm_status,
    c.orchestration,
    c.degre_orchestration,
    c.enonciateur,
    c.phrases_preuves,
    c.axes_nkili_justification,
    c.salience_russe,
    c.salience_panafricaniste   AS salience_panafricaine,
    c.salience_souverainiste,
    c.salience_nationale_aes,
    c.influence_ingerence_status AS statut_influence,
    c.disarm_confidence,
    c.influence_ingerence_confidence,
    c.classified_at
FROM articles a
JOIN classifications c ON c.article_id = a.article_id
LEFT JOIN entities e   ON e.entity_id = a.entity_id
WHERE a.passes_inclusion_filter = 1
  AND a.in_classification_scope = 1
  AND c.classified_by = 'llm'
ORDER BY a.article_id
"""

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(QUERY).fetchall()
con.close()

pop = len(rows)
if pop != EXPECTED_POP:
    sys.exit(f"ARRET: population = {pop} (attendu {EXPECTED_POP}). Aucun tirage.")

random.seed(SEED)
sample = random.sample(rows, N)

cols = rows[0].keys()
with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, quoting=csv.QUOTE_ALL)
    w.writerow(cols)
    for r in sample:
        w.writerow([r[c] for c in cols])

print(f"population = {pop}")
print(f"lignes exportees = {len(sample)}")
print("article_id tires:", [r["article_id"] for r in sample])
