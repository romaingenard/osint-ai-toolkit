#!/usr/bin/env python3
"""Assemble le livrable paire B#8 (Transformé) en lecture seule.
Lit data/corpus.db (mode=ro), écrit outputs/paire_b8_textes_2026-06-23.md."""
import sqlite3, json

DB = "data/corpus.db"
OUT = "outputs/paire_b8_textes_2026-06-23.md"
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
    if not j: return "—"
    try: return "; ".join(f"{x['code']} {x['nom']}" for x in json.loads(j))
    except Exception: return j

def fmt_axes(j):
    try:
        a = json.loads(j); p = [k for k,v in a.items() if v]
        return ", ".join(p) if p else "(aucun)"
    except Exception: return j

def block(r, role):
    lf = "  ⚠ **>6000 car. (texte intégral ci-dessous)**" if r['len'] > 6000 else ""
    return (f"#### {role} — article {r['article_id']} : « {r['title']} »\n\n"
            f"- **Entité** : {r['name']} ({r['platform']}) | **pays** : {r['country']} | **catégorie** : {r['cat']}\n"
            f"- **Date** : {r['date_published']}\n"
            f"- **Longueur** : {r['len']} caractères{lf}\n"
            f"- **Saliences (R/PA/SC/AES)** : {r['R']}/{r['PA']}/{r['SC']}/{r['AES']}\n"
            f"- **disarm_status** : {r['disarm_status']}\n"
            f"- **disarm_techniques** : {fmt_disarm(r['disarm_techniques'])}\n"
            f"- **Axes Nkili présents** : {fmt_axes(r['axes_lexicaux_nkili'])}\n\n"
            f"**Texte intégral :**\n\n```\n{(r['text_content'] or '').strip()}\n```\n")

s, r, twin = meta(1900), meta(925), meta(2463)
ds, dr = s['date_published'][:10], r['date_published'][:10]
ant = "✅ **Antériorité vérifiée** : la source précède le relais" if ds <= dr else "❌ **ANOMALIE**"

p = []
p.append("# Paire de reformulation B#8 (« Transformé ») — textes en regard — 2026-06-23\n")
p.append("Lecture seule sur `data/corpus.db` (`mode=ro`). Population : "
         "`passes_inclusion_filter=1 AND in_classification_scope=1 AND classified_by='llm'` (221). "
         "Source et relais in-scope.\n")
p.append("> **Source retenue** : afrinz.ru art. 1900 (web, version éditoriale complète de la déclaration Meshkov). "
         "**Jumeau Telegram** : @africaninitiativefr art. 2463 (même déclaration, même jour 2026-02-09 mais plus tard "
         "— 19:51 vs 16:17 — et tronqué : sans le paragraphe Nebenzia/ONU). On retient 1900 comme source canonique de B#8 ; "
         "2463 est une syndication Telegram du même contenu.\n")
p.append("> **Qualité** : les trois sont du contenu **web/Telegram propre**, aucune dégradation ASR (le relais 925 est "
         "un éditorial « En ordre de bataille » de Le Sahel).\n")
p.append(f"> **Sens de dérivation (§15.4)** : source African Initiative (SUPRA, cat A, {ds}) → relais Le Sahel (NER, cat B, {dr}). "
         f"{ant} (source {ds} → relais {dr}, +2 jours).\n")
p.append("\n---\n")

p.append("## Lecture de la transformation (factuel)\n")
p.append("**Ce que le relais REPREND de la source** : la thèse centrale « la France [arme/]soutient les groupes terroristes » "
         "au Sahel (source : « Divers groupes terroristes sont soutenus afin d'affaiblir ces gouvernements indépendants » ; "
         "relais : « mercenaires en guenilles, armés, instruits, encadrés et enjoints par la France »).\n")
p.append("\n**Ce que le relais SUPPRIME** : (1) l'**Ukraine** — co-accusée centrale de la source (« France ET Ukraine », "
         "« services spéciaux ukrainiens », Nebenzia/ONU) — totalement absente du relais ; (2) toute **attribution russe** — "
         "l'ambassadeur **Meshkov**, « Russie-24 », Nebenzia, le cadre rivalité Russie-France disparaissent. "
         "Conséquence mesurable : **salience_russe = 2 (source) → 0 (relais)**. La signature russe est effacée.\n")
p.append("\n**Ce que le relais TRANSFORME et ANCRE localement** : passage d'une **déclaration diplomatique abstraite** "
         "(géopolitique Russie/France/Sahel) à un **éditorial mobilisateur** accroché à deux objets nigériens concrets — "
         "l'**attaque de la Base 101 de Niamey** et l'**ordonnance de mobilisation générale** — porté par la figure de Tiani, "
         "l'histoire anticoloniale et l'appel à l'« unité des cœurs ». D'où le codage « **Transformé** » (re-genrage + "
         "localisation + dé-russification), distinct des paires « Adapté » #14/#18.\n")
p.append("\n---\n")

p.append("## ▼ SOURCE (African Initiative, SUPRA, cat A)\n")
p.append(block(s, "SOURCE"))
p.append("\n### Jumeau Telegram (référence, non retenu comme source primaire)\n")
p.append(block(twin, "JUMEAU TELEGRAM"))
p.append("\n---\n")
p.append("## ▼ RELAIS (Le Sahel, NER, cat B)\n")
p.append(block(r, "RELAIS"))
p.append("\n---\n")

with open(OUT, "w") as f:
    f.write("\n".join(p))
print("OK écrit:", OUT)
