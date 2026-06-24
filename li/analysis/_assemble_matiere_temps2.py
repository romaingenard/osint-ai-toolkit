#!/usr/bin/env python3
"""Assemble le livrable Temps 2 (extraction matière qualitative) en lecture seule.
Lit data/corpus.db, écrit outputs/matiere_qualitative_temps2_2026-06-23.md.
Aucune écriture en base (connexion read-only)."""
import sqlite3, json, textwrap

DB = "data/corpus.db"
OUT = "outputs/matiere_qualitative_temps2_2026-06-23.md"

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

def meta(aid):
    r = con.execute("""
      SELECT a.article_id, e.name, e.country, e.producer_category cat, a.date_published,
             a.url, length(a.text_content) len, a.text_content,
             c.salience_russe R, c.salience_panafricaniste PA, c.salience_souverainiste SC,
             c.salience_nationale_aes AES, c.disarm_status, c.disarm_techniques, c.axes_lexicaux_nkili
      FROM articles a JOIN classifications c ON c.article_id=a.article_id
      JOIN entities e ON e.entity_id=a.entity_id
      WHERE a.article_id=? AND c.classified_by='llm'
      """, (aid,)).fetchone()
    return r

def fmt_disarm(j):
    if not j: return "— (pas_technique_disarm)"
    try:
        t = json.loads(j)
        return "; ".join(f"{x['code']} {x['nom']}" for x in t)
    except Exception:
        return j

def fmt_axes(j):
    try:
        a = json.loads(j)
        present = [k for k,v in a.items() if v]
        return ", ".join(present) if present else "(aucun axe actif)"
    except Exception:
        return j

def header(r, besoin):
    return (f"### {besoin} — article {r['article_id']}\n\n"
            f"- **Entité** : {r['name']} | **pays** : {r['country']} | **catégorie** : {r['cat']}\n"
            f"- **Date** : {r['date_published']}\n"
            f"- **Longueur** : {r['len']} caractères\n"
            f"- **Saliences (R/PA/SC/AES)** : {r['R']}/{r['PA']}/{r['SC']}/{r['AES']}\n"
            f"- **disarm_status** : {r['disarm_status']}\n"
            f"- **disarm_techniques** : {fmt_disarm(r['disarm_techniques'])}\n"
            f"- **Axes Nkili présents** : {fmt_axes(r['axes_lexicaux_nkili'])}\n")

# ordre : (besoin, id, mode, note)
FULL = "full"; PASS = "passages"
PLAN = [
 ("M1a — cat C anti-FR/pro-AES (USABLE)", 3226, FULL,
   "Transcript YouTube **propre et exploitable** (FR cohérent ; erreurs ASR mineures : ONI=ONU, Burgina=Burkina)."),
 ("M1b — cat C anti-FR/pro-AES (DEGRADE)", 3324, FULL,
   "⚠ **Transcript auto YouTube DEGRADE** : largement bruité (« neutralisant… Oui. Oui. »). Fragments anti-FR lisibles "
   "(« Nig c'est la France et ses mercenaires », « C'est pas pour rien qu'on a remercié les russes ») mais NON citable proprement. "
   "Recommandation : remplacer la matière cat C Gandhi-YouTube par Issa Diawara (propre) ou les posts FB de Gandhi."),
 ("M2 — célébration armée malienne (USABLE)", 3290, FULL,
   "Post Facebook **propre**. Célébration Aïd/Goïta : FAMa, souveraineté, redistribution minière."),
 ("M3 — cat C salience_russe=2 (USABLE)", 3238, FULL,
   "Transcript Issa Diawara **propre**. Défense explicite du « partenariat Russie-Afrique » contre la « guerre informationnelle de la DG[SE] »."),
 ("M4 — cat C pas_technique_disarm (DEGRADE)", 3334, FULL,
   "⚠ **Transcript auto DEGRADE quasi inexploitable** (boucles « contrôle contrôle »). Confirme le statut pas_technique mais "
   "n'offre pas de narratif citable. Substitut propre à privilégier pour ce besoin."),
 ("FENETRE MALI — transcript-fleuve cat C", 3331, PASS,
   "Émission « Parole aux africains » (Gandhi Malien TV). Intro et certains segments cohérents ; le corps dégrade en bruit ASR. "
   "Document le plus riche en théorie mais à manier en passages, pas intégralement."),
 ("B1 — antenne AI Burkina @a_initiative_bb, R=0 (USABLE)", 3153, FULL,
   "Texte **propre**. R=0 confirmé. NB analytique : l'intégralité est **doublée en russe** (miroir FR/RU) — la « non-signature » "
   "russe au niveau du contenu coexiste avec une republication bilingue, marqueur d'origine."),
 ("B2 — cat B média d'État burkinabè institutionnel (USABLE)", 1354, FULL,
   "Sidwaya, bulletin militaire (source AIB). Institutionnel, efficacité sécuritaire."),
 ("B3 — souveraineté SANS nommer la France (VERIFIE OK)", 1353, FULL,
   "✅ **Vérifié** : 0 occurrence de « France », « français » ou « Occident ». Valorise la reconquête territoriale / efficacité "
   "militaire sans cible nommée. Candidat CONFORME au besoin (pas besoin de l'alternative 3306)."),
 ("FENETRE BURKINA — média d'État à signature russe dense", 3322, FULL,
   "Sidwaya FB (R2/SC2/AES2). Court mais saillant : relaie des « services de renseignements extérieurs russes, cités par Sputnik » "
   "accusant Macron de vouloir éliminer Traoré. Pic de signature russe dans un canal officiel BFA."),
 ("N1 — Le Sahel base 101 (USABLE, déjà audité)", 1038, FULL,
   "Le Sahel, compilation de communiqués société civile. Contient « mercenaires extérieurs », « sponsors au service des "
   "néocolonialistes », « contingent des militaires russes de l'Africa Corps », « Vive la Russie », « litige Orano/Niger »."),
 ("N2 — Le Sahel souverainiste, axe Identité (USABLE)", 646, FULL,
   "Le Sahel, chronique Tiani sur l'économie. Souverainisme économique ; nomme la France (« tête de pont de cette cabale »)."),
 ("N3 — Le Sahel pas_technique_disarm (USABLE)", 943, FULL,
   "Le Sahel, tribune militante panaficaniste (PA2) sans technique DISARM caractérisée."),
 ("FENETRE NIGER — interview-fleuve Tiani RTN", 869, PASS,
   "Interview exclusive Tiani (RTN), suite et fin. Texte **propre** mais très long ; passages saillants ci-dessous."),
 ("S1 — afrinz.ru partenariat Russie-Afrique, R=2 (USABLE)", 20, FULL,
   "African Initiative (afrinz.ru). Récit-mémoire URSS/Afrique (décolonisation, formation des cadres, aide militaire) : "
   "signature « partenariat » de la source."),
 ("T1 — cas transverse : cadre France-commanditaire (NUANCE)", 1015, FULL,
   "⚠ **Cadre France-commanditaire FORTEMENT présent** (« terroristes manipulés à distance par la France », « action d'éclat "
   "planifiée par la France », « perfidie de l'impérialisme français »). MAIS le critère « sans marqueur russe explicite » "
   "n'est PAS pleinement tenu : le texte crédite « leur partenaire russe » dans la riposte, alors que salience_russe=0. "
   "C'EST le cas analytique central de l'ambiguïté autonomie/infusion. L'alternative 905 ne convient pas (nomme la France "
   "mais SANS cadre terrorisme)."),
]

PASSAGES = {
 3331: [
   "février 2026, chers téléspectateurs et auditeurs de Gandi Malien TV et d'Africain TV […] Aujourd'hui, nous abordons quelques thèmes : l'élimination du fils Kaddafi, les révélations du SVR service de renseignement extérieur de la Fédération des russ[es] et la venue de cet émissaire américain selon eux, respectant cette fois-ci la souveraineté des pays de l'A[E]S.",
   "[…] les Américains devaient monter certaines pièces et tout ça. Les Américains ont bloqué ça. Mais c'est ça la demande de la France évidemment. […] ces gens-là ils tournent tous ensemble […] les Français et les Américains ont senti […] que la France ça […]",
 ],
 869: [
   "[…] C'est à nous de faire en sorte que notre volonté de souveraineté, d'indépendance soit la plus forte des volontés. Qu'Allah préserve notre pays, Allah préserve le Mali, Allah préserve le Burkina, Allah préserve la Confédération. Nous remercions tous les partenaires sincères qui ne méconnaissent pas nos intérêts et qui nous accompagn[ent].",
   "[…] Il faut consentir des sacrifices pour montrer que l'effondrement que la France compte provoquer n'aura pas lieu. Ils nous ont dit qu'ils ont produit, même au temps de la ''colonisation'' […].",
   "[…] la Confédération des États du Sahel (ou peut-être la Fédération dans quelques années) et la CEDEAO, qu'on continue à collaborer, à coexister en tant que peuples du même espace ouest-africain, mais dans des organisations différentes, parce que nos intérêts ne sont plus préservés par la CEDEAO.",
 ],
}

parts = []
parts.append("# Matière qualitative par terrain — Temps 2 (extraction) — 2026-06-23\n")
parts.append("Lecture seule sur `data/corpus.db` (connexion read-only). Population : "
             "`passes_inclusion_filter=1 AND in_classification_scope=1 AND classified_by='llm'` (221).\n")
parts.append("> **M5 (paires de reformulation #13/#14/#18) : NON EXTRAIT.** Le placeholder du §15.4 n'a pas été "
             "renseigné et la table `reformulation_pairs` est vide. Aucun appariement heuristique effectué (consigne).\n")
parts.append("> **Entités V1 absentes (AIB, ORTN, ANP) : non extraites** (0 article in-scope).\n")
parts.append("\n---\n")

for besoin, aid, mode, note in PLAN:
    r = meta(aid)
    parts.append(header(r, besoin))
    if note:
        parts.append(f"\n> {note}\n")
    if mode == FULL:
        parts.append("\n**Texte intégral :**\n\n```\n" + (r['text_content'] or "").strip() + "\n```\n")
    else:
        parts.append("\n**Passages saillants :**\n")
        for i, p in enumerate(PASSAGES[aid], 1):
            parts.append(f"\n*Passage {i}* :\n> {p}\n")
    parts.append("\n---\n")

with open(OUT, "w") as f:
    f.write("\n".join(parts))
print("OK écrit:", OUT)
print("Articles:", ", ".join(str(a) for _,a,_,_ in PLAN))
