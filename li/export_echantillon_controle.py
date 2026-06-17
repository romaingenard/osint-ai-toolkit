"""Export d'un échantillon de contrôle pour confrontation manuelle vs classification LLM.

LECTURE + export CSV uniquement — aucune écriture en base.
Le report ultérieur de la classification manuelle devra passer par
li/parse_classification.py (validation des enums), jamais par INSERT manuel.

Population : 318 articles classifiés
  classified_by='llm' AND passes_inclusion_filter=1 AND in_classification_scope=1
Tirage : random.sample(n=10), seed fixe 20260617 (traçabilité).

Structure CSV : [métadonnées article] | [saisie manuelle VIDE] | [classification LLM préfixée llm_].
"""

import csv
import random
import sqlite3

DB_PATH = "data/corpus.db"
OUT_PATH = "outputs/echantillon_controle_20260617.csv"
SEED = 20260617
N = 10

# Filtre de population OBLIGATOIRE.
POPULATION_SQL = """
SELECT
    a.article_id,
    e.country,
    e.producer_category,
    a.title,
    a.date_published,
    a.url,
    a.text_content,
    c.disarm_status,
    c.disarm_techniques,
    c.disarm_justification,
    c.salience_russe,
    c.salience_panafricaniste,
    c.salience_souverainiste,
    c.salience_nationale_aes,
    c.salience_justification,
    c.influence_ingerence_status,
    c.influence_ingerence_justification,
    c.axes_lexicaux_nkili,
    c.axes_nkili_justification,
    c.orchestration,
    c.degre_orchestration,
    c.enonciateur,
    c.phrases_preuves
FROM articles a
JOIN classifications c ON c.article_id = a.article_id
JOIN entities e ON e.entity_id = a.entity_id
WHERE c.classified_by = 'llm'
  AND a.passes_inclusion_filter = 1
  AND a.in_classification_scope = 1
"""

# Bloc 1 — métadonnées descriptives.
META_COLS = [
    "article_id", "country", "producer_category",
    "title", "date_published", "url", "text_content",
]

# Bloc 2 — saisie manuelle (colonnes vides à remplir dans Notion).
MANUEL_COLS = [
    "disarm_manuel",
    "saillances_manuel",       # R/PA/SC/AES
    "nkili_manuel",            # axes 1-6
    "statut_influence_manuel",
    "justification_manuel",
]

# Bloc 3 — classification LLM (champs persistés), préfixée llm_ et placée à droite.
LLM_SRC_COLS = [
    "disarm_status", "disarm_techniques", "disarm_justification",
    "salience_russe", "salience_panafricaniste",
    "salience_souverainiste", "salience_nationale_aes", "salience_justification",
    "influence_ingerence_status", "influence_ingerence_justification",
    "axes_lexicaux_nkili", "axes_nkili_justification",
    "orchestration", "degre_orchestration", "enonciateur",
    "phrases_preuves",
]


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(POPULATION_SQL)]
    finally:
        conn.close()

    pop = len(rows)
    assert pop == 318, f"Population filtrée attendue=318, obtenue={pop} — export interrompu."

    rng = random.Random(SEED)
    sample = rng.sample(rows, N)
    sample.sort(key=lambda r: r["article_id"])  # ordre stable pour relecture

    header = META_COLS + MANUEL_COLS + ["llm_" + c for c in LLM_SRC_COLS]

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in sample:
            line = [r[c] for c in META_COLS]
            line += [""] * len(MANUEL_COLS)
            line += [r[c] for c in LLM_SRC_COLS]
            w.writerow(line)

    print(f"Population filtrée : {pop} (attendu 318)")
    print(f"Échantillon tiré   : {len(sample)} (seed={SEED})")
    print(f"article_id retenus : {[r['article_id'] for r in sample]}")
    print(f"Colonnes CSV       : {len(header)} ({len(META_COLS)} méta + {len(MANUEL_COLS)} manuel + {len(LLM_SRC_COLS)} llm)")
    print(f"CSV écrit          : {OUT_PATH}")


if __name__ == "__main__":
    main()
