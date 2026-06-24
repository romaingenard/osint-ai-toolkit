"""Export LISIBLE de la classification LLM des 10 articles de l'échantillon de contrôle.

LECTURE + export CSV uniquement — aucune écriture en base.

Mêmes article_id que outputs/echantillon_controle_20260617.csv (seed 20260617).
Sortie : 6 colonnes dont les intitulés sont IDENTIQUES au tableau de saisie
manuelle Notion (disarm_manuel, saillances_manuel, …) pour alignement
copier-coller, MAIS dont le contenu provient du LLM (classified_by='llm'),
reformaté en texte lisible (pas le format parseur strict).
"""

import csv
import json
import sqlite3

DB_PATH = "data/corpus.db"
SAMPLE_CSV = "outputs/echantillon_controle_20260617.csv"
OUT_PATH = "outputs/echantillon_llm_20260617.csv"

NKILI_ORDER = [
    "Anti-impérialisme", "Efficacité sécuritaire", "Partenariat",
    "Économique", "Identité-affect", "Métadiscours informationnel",
]

ROW_SQL = """
SELECT
    a.article_id,
    c.disarm_status, c.disarm_tactic_code, c.disarm_tactic_name,
    c.disarm_techniques,
    c.salience_russe, c.salience_panafricaniste,
    c.salience_souverainiste, c.salience_nationale_aes,
    c.axes_lexicaux_nkili,
    c.influence_ingerence_status, c.influence_ingerence_confidence,
    c.disarm_justification, c.salience_justification,
    c.axes_nkili_justification, c.influence_ingerence_justification
FROM articles a
JOIN classifications c ON c.article_id = a.article_id
WHERE c.classified_by = 'llm' AND a.article_id = ?
"""


def fmt_techniques(raw):
    """JSON [{code,nom}] -> 'T0002 Facilitate State Propaganda; T0003 …'. None -> NON_APPLICABLE."""
    if not raw:
        return "NON_APPLICABLE"
    items = json.loads(raw)
    return "; ".join(f"{t['code']} {t['nom']}" for t in items)


def fmt_disarm(status, tac_code, tac_name, techniques_raw):
    techs = fmt_techniques(techniques_raw)
    if status == "classified":
        tactiques = ""
        if tac_code:
            codes = tac_code.split(";")
            names = (tac_name or "").split(";")
            tactiques = "; ".join(
                f"{c.strip()} {n.strip()}".strip() for c, n in zip(codes, names)
            )
        prefix = f"[{status}] tactiques: {tactiques} | techniques: " if tactiques else f"[{status}] techniques: "
        return prefix + techs
    return f"[{status}] {techs}"


def fmt_saillances(r, pa, sc, aes):
    return f"R={r} PA={pa} SC={sc} AES={aes}"


def fmt_nkili(raw):
    """JSON dict -> 'Anti-impérialisme=1 · Efficacité sécuritaire=0 · …' (ordre canonique)."""
    if not raw:
        return ""
    d = json.loads(raw)
    return " · ".join(f"{axe}={d.get(axe, '?')}" for axe in NKILI_ORDER)


def fmt_statut(status, conf):
    if not status:
        return ""
    return f"{status} (confiance {conf})" if conf else status


def fmt_justif(disarm_j, sal_j, axes_j, inf_j):
    parts = []
    if disarm_j:
        parts.append(f"[DISARM] {disarm_j}")
    if sal_j:
        parts.append(f"[Saillances] {sal_j}")
    if axes_j:
        parts.append(f"[Axes Nkili] {axes_j}")
    if inf_j:
        parts.append(f"[Influence/ingérence] {inf_j}")
    return "\n".join(parts)


def main():
    with open(SAMPLE_CSV, encoding="utf-8") as f:
        ids = sorted(int(r["article_id"]) for r in csv.DictReader(f))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = []
        for aid in ids:
            r = conn.execute(ROW_SQL, (aid,)).fetchone()
            if r is None:
                raise SystemExit(f"article_id {aid} absent en classification llm — incohérence.")
            rows.append(r)
    finally:
        conn.close()

    header = [
        "article_id", "disarm_manuel", "saillances_manuel",
        "nkili_manuel", "statut_influence_manuel", "justification_manuel",
    ]
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([
                r["article_id"],
                fmt_disarm(r["disarm_status"], r["disarm_tactic_code"],
                           r["disarm_tactic_name"], r["disarm_techniques"]),
                fmt_saillances(r["salience_russe"], r["salience_panafricaniste"],
                               r["salience_souverainiste"], r["salience_nationale_aes"]),
                fmt_nkili(r["axes_lexicaux_nkili"]),
                fmt_statut(r["influence_ingerence_status"], r["influence_ingerence_confidence"]),
                fmt_justif(r["disarm_justification"], r["salience_justification"],
                           r["axes_nkili_justification"], r["influence_ingerence_justification"]),
            ])

    print(f"article_id exportés : {[r['article_id'] for r in rows]}")
    print(f"Lignes              : {len(rows)}")
    print(f"Colonnes            : {header}")
    print(f"CSV écrit           : {OUT_PATH}")


if __name__ == "__main__":
    main()
