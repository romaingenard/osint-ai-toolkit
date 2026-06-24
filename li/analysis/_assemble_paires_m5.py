#!/usr/bin/env python3
"""Assemble le livrable M5 (paires de reformulation #14 et #18) en lecture seule.
Lit data/corpus.db (mode=ro), écrit outputs/paires_m5_textes_2026-06-23.md.
Aucune écriture en base."""
import sqlite3, json

DB = "data/corpus.db"
OUT = "outputs/paires_m5_textes_2026-06-23.md"

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

def meta(aid):
    return con.execute("""
      SELECT a.article_id, a.title, e.name, e.platform, e.country, e.producer_category cat,
             a.date_published, length(a.text_content) len, a.text_content,
             c.salience_russe R, c.salience_panafricaniste PA, c.salience_souverainiste SC,
             c.salience_nationale_aes AES, c.disarm_status, c.disarm_techniques, c.axes_lexicaux_nkili
      FROM articles a JOIN classifications c ON c.article_id=a.article_id
      JOIN entities e ON e.entity_id=a.entity_id
      WHERE a.article_id=? AND c.classified_by='llm'""", (aid,)).fetchone()

def fmt_disarm(j):
    if not j: return "— (pas_technique_disarm : aucune technique caractérisée)"
    try: return "; ".join(f"{x['code']} {x['nom']}" for x in json.loads(j))
    except Exception: return j

def fmt_axes(j):
    try:
        a = json.loads(j); p = [k for k,v in a.items() if v]
        return ", ".join(p) if p else "(aucun axe actif)"
    except Exception: return j

def block(r, role):
    long_flag = "  ⚠ **>6000 car. — texte intégral donné ci-dessous**" if r['len'] > 6000 else ""
    return (f"#### {role} — article {r['article_id']} : « {r['title']} »\n\n"
            f"- **Entité** : {r['name']} ({r['platform']}) | **pays** : {r['country']} | **catégorie** : {r['cat']}\n"
            f"- **Date** : {r['date_published']}\n"
            f"- **Longueur** : {r['len']} caractères{long_flag}\n"
            f"- **Saliences (R/PA/SC/AES)** : {r['R']}/{r['PA']}/{r['SC']}/{r['AES']}\n"
            f"- **disarm_status** : {r['disarm_status']}\n"
            f"- **disarm_techniques** : {fmt_disarm(r['disarm_techniques'])}\n"
            f"- **Axes Nkili présents** : {fmt_axes(r['axes_lexicaux_nkili'])}\n\n"
            f"**Texte intégral :**\n\n```\n{(r['text_content'] or '').strip()}\n```\n")

# paires : (titre, source_id, relais_id, code, referents)
PAIRES = [
 ("PAIRE #14 — codée « Adapté »", 13, 3228, "Adapté",
  "Référents partagés repérables (factuel) : cadre « la France déstabilise le Sahel via des groupes terroristes ET le régime "
  "ukrainien » (Lavrov : « combattants des formations ukrainiennes », « Ukraine fournit des drones aux terroristes au Mali » ; "
  "relais 3228 : « drones de Zelenski qui se retrouvent ici contre nos militaires », « cargos qui viennent de chez [Z]elenski ») ; "
  "topos « diviser pour régner » / « opposer les pays africains ». **Transformation** : le relais ANCRE le cadre russe sur un "
  "objet local distinct — la visite de l'émissaire de l'Union africaine (Dr Mamadou Tangara) reçu à Ouagadougou le 09/02 — et en "
  "fait un réquisitoire contre l'« inutilité » de l'UA, registre absent de la source Lavrov."),
 ("PAIRE #18 — codée « Adapté »", 1956, 3224, "Adapté",
  "Référents partagés repérables (factuel) : thèse SVR « la France est passée au soutien direct de terroristes » + Macron / "
  "« dirigeants indésirables » + Ukraine (drones, instructeurs) → reprise par le relais 3224 (« c'est la jeune française qui a "
  "bel et bien planifié cette opération », « détourner la fameuse aide à Zelenski pour que ça se retrouve ici », « État islamique "
  "= mercenaires » de la France). **Transformation / ancrage local** : le relais accroche le cadre russe à l'actualité nigérienne "
  "immédiate — l'attaque de l'aéroport/base de Niamey et la vidéo du journaliste Wassim Nasr — et substitue au trio de la source "
  "(présidents-cibles) le trio nommé par Tiani : « Macron, Ouattara, Talon »."),
]

parts = []
parts.append("# Paires de reformulation #14 et #18 — textes en regard (M5) — 2026-06-23\n")
parts.append("Lecture seule sur `data/corpus.db` (`mode=ro`). Population : "
             "`passes_inclusion_filter=1 AND in_classification_scope=1 AND classified_by='llm'` (221). "
             "Les 4 articles sont in-scope.\n")
parts.append("> **Contrôle qualité transcripts Issa Diawara** : 3224 et 3228 sont **propres** (français cohérent), "
             "comme 3226/3238. Erreurs ASR mineures à lire en clair : « jeune/gente française » = *junte française*, "
             "« AS / espace AS » = *AES*, « ONI » = *ONU*, « CDO/CDAO » = *CEDEAO*, « Tiani », « Wassim Nasr ».\n")
parts.append("> **Sens de dérivation (§15.4)** : source = afrinz (SUPRA, cat A) → relais = Issa Diawara (MLI, cat C).\n")
parts.append("\n---\n")

for titre, sid, rid, code, ref in PAIRES:
    s, r = meta(sid), meta(rid)
    # antériorité
    ds, dr = s['date_published'][:10], r['date_published'][:10]
    anteriorite = ("✅ **Antériorité vérifiée** : la source précède le relais"
                   if ds <= dr else "❌ **ANOMALIE** : la source ne précède PAS le relais")
    parts.append(f"## {titre}\n")
    parts.append(f"- **Source** : afrinz art. {sid} — {ds}\n"
                 f"- **Relais** : Issa Diawara art. {rid} — {dr}\n"
                 f"- {anteriorite} (source {ds} → relais {dr}).\n")
    parts.append(f"\n> {ref}\n")
    parts.append("\n### ▼ SOURCE (afrinz, cat A)\n")
    parts.append(block(s, "SOURCE"))
    parts.append("\n### ▼ RELAIS (Issa Diawara, cat C)\n")
    parts.append(block(r, "RELAIS"))
    parts.append("\n---\n")

with open(OUT, "w") as f:
    f.write("\n".join(parts))
print("OK écrit:", OUT)
