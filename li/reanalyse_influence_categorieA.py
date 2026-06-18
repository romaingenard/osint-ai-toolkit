"""li/reanalyse_influence_categorieA.py — réanalyse ciblée du statut influence
des articles producteur catégorie A déjà classifiés.

POURQUOI un script séparé : li.classify_batch.select_articles_to_classify exclut
explicitement les articles déjà classés (NOT IN classified_by='llm'), donc ne
couvre PAS la réanalyse d'articles existants. Ce script s'adresse exactement à
ces lignes-là.

PÉRIMÈTRE : in_classification_scope=1 AND classified_by='llm'
AND producer_category='A'  (124 articles au 2026-06-17).

ÉCRITURE — point crucial : chaque résultat corrige la ligne EXISTANTE via
store_li.update_influence_fields(conn, classification_id, statut, justification,
confiance) — UPDATE ciblé par classification_id (PK), testé. JAMAIS
insert_classification (qui dupliquerait : la table classifications n'a pas de
contrainte d'unicité article_id+classified_by).

SEUL le statut influence/ingérence est réécrit (3 colonnes). DISARM, saillances
et axes Nkili ne sont pas touchés.

Modes :
  (défaut) --dry-run : sélection + construction des requêtes influence. AUCUN
           appel réseau, AUCUNE écriture, AUCUN crédit. Affiche le plan + un
           échantillon de payload pour preuve.
  --apply : backup corpus.db → appels influence séquentiels → UPDATE ciblé par
            ligne → log markdown old→new. Consomme des crédits API.

Usage :
  python -m li.reanalyse_influence_categorieA            # dry-run (défaut)
  python -m li.reanalyse_influence_categorieA --apply    # exécution réelle
  python -m li.reanalyse_influence_categorieA --apply --limit 5   # sous-ensemble
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import time
from datetime import datetime

import anthropic

# Briques réutilisées (aucune réécriture) :
from li.classify_batch import MODEL, MAX_TOKENS_INFLUENCE
from li.parse_classification import (
    ClassificationParseError,
    parse_influence_ingerence,
)
from li.store_li import DEFAULT_DB_PATH, update_influence_fields

OUTPUTS_DIR = "outputs"

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT INFLUENCE CORRIGÉ — À INJECTER par Romain au moment de la réanalyse.
# Tant que cette valeur est le sentinelle ci-dessous, le mode --apply REFUSE de
# s'exécuter (garde-fou anti-lancement accidentel avec un prompt non fourni).
# Forme attendue : le texte system COMPLET de l'appel influence (incluant, si
# voulu, le préfixe CONTEXT_PROMPT — au choix de Romain dans le texte corrigé).
# ─────────────────────────────────────────────────────────────────────────────
INFLUENCE_PROMPT_CORRIGE_A_INJECTER = """Tu es un analyste spécialisé en lutte informationnelle.

CONTEXTE OPÉRATIONNEL :
Tu analyses des contenus collectés dans le cadre d'une étude sur l'écosystème informationnel pro-AES / anti-français ciblant le Mali, le Burkina Faso et le Niger en 2025-2026. Le flux étudié est un flux informationnel unique (pro-AES/anti-français) analysé à travers trois terrains nationaux.

Les producteurs de ce flux relèvent de quatre catégories :
- A — Producteurs russes : African Initiative et dérivés, MOI AI-Freak documenté par Viginum, galaxie Prigojine résiduelle, GPCI.
- B — Relais institutionnels AES : médias d'État restructurés (L'Essor, ORTM, RTB, Sidwaya, Le Sahel, ORTN et équivalents).
- C — Amplificateurs cooptés : Kemi Seba, Nathalie Yamb et autres influenceurs panafricanistes cooptés.
- D — Producteurs locaux à autonomie variable : comptes locaux TikTok/Facebook, médias privés non alignés sur AI.

RÈGLE DE CADRAGE (non négociable) :
Ce rapport n'analyse pas la réponse informationnelle française. Si un contenu traite substantiellement de la riposte française (Viginum, SGDSN, MEAE, CFI, AFD, dispositifs militaires ou de renseignement), tu le signales comme "HORS_SCOPE" et tu n'effectues pas de classification DISARM.

PRINCIPE ANALYTIQUE IMPORTANT :
Un contenu qui mobilise uniquement la matrice panafricaniste ou souverainiste africaine sans aucun marqueur russe est un cas analytiquement valide (saillances 0-2-0-0 ou 0-0-2-0). Il doit être classifié normalement. Ne pas forcer une attribution russe par défaut.


INFORMATION TRANSMISE : la catégorie du producteur de cet article t'est
indiquée en tête du contenu. Tu DOIS en tenir compte pour l'évaluation
influence/ingérence, en particulier pour les producteurs catégorie A
(origine dissimulée).

TÂCHE : qualifier le contenu au regard de la distinction doctrinale influence légitime / ingérence caractérisée / zone grise (rapport CAPS-IRSEM 2018, Les manipulations de l'information).

DÉFINITIONS :
- INFLUENCE_LEGITIME : action informationnelle revendiquée d'un acteur dans l'espace public. Exemple : un média d'État AES (catégorie B) qui porte ouvertement la position de la junte. Ne s'applique qu'aux producteurs dont l'origine n'est PAS dissimulée.
- INGERENCE_CARACTERISEE : au moins un des quatre critères Viginum est rempli : contenu trompeur, diffusion artificielle, caractère étranger dissimulé, atteinte aux intérêts fondamentaux.
- ZONE_GRISE : contenu dont le statut est ambigu (ex. contenu souverainiste local possiblement amplifié par une opération russe sans que l'amplification soit établie de façon décisive).

DISTINCTION CRITIQUE — niveau du dispositif vs niveau du contenu cité :
Le critère Viginum « caractère étranger dissimulé » s'évalue au niveau du
DISPOSITIF DE DIFFUSION, pas seulement du contenu ou de la source citée.
Un contenu peut citer une source ouvertement étrangère (ex. un ambassadeur
russe nommé) tout en étant diffusé par un dispositif qui DISSIMULE son
caractère étranger. C'est le cas des producteurs catégorie A (African
Initiative et dérivés, afrinz.ru, canaux Telegram affiliés) : ils se
présentent comme des agences de presse indépendantes alors qu'ils sont des
actifs informationnels russes. Cette dissimulation du dispositif suffit à
elle seule à remplir un critère Viginum (« caractère étranger dissimulé »),
INDÉPENDAMMENT du fait que le contenu cité soit, lui, ouvertement attribué.

RÈGLE D'APPLICATION :
- Si le producteur est catégorie A (origine russe dissimulée derrière une façade d'indépendance), le critère « caractère étranger dissimulé » est rempli par construction. Cela EXCLUT le statut influence_legitime pour ces producteurs : un actif étranger dissimulé ne fait pas de l'influence revendiquée.
- En revanche, le choix entre ingerence_caracterisee et zone_grise reste à TRANCHER selon le contenu de l'article lui-même. Retiens ingerence_caracterisee si, au-delà du canal dissimulé, le contenu présente aussi de la tromperie, de la distorsion factuelle, ou s'inscrit dans une amplification coordonnée manifeste. Retiens zone_grise si le seul élément d'ingérence est le canal dissimulé, l'article relayant par ailleurs une information factuelle sans manipulation propre de son contenu.
- Ne classe jamais un producteur catégorie A en influence_legitime ; mais ne force pas ingerence_caracterisee si le contenu ne le justifie pas au-delà du canal. L'exemple d'influence_legitime (média d'État AES portant ouvertement la position de la junte) ne s'applique qu'aux producteurs catégorie B, dont l'origine n'est pas dissimulée.
- Si le producteur est catégorie C (amplificateur coopté), n'applique AUCUN présupposé de statut lié à la catégorie : l'imputation à une opération russe est un résultat à établir sur preuve dans le contenu, non un a priori. Un producteur catégorie C n'est pas un média d'État ; ne classe jamais un producteur catégorie C en influence_legitime au seul motif qu'il relaie un contenu factuel ou institutionnel (annonces de victoires FAMa, communiqués officiels), ce relais ne suffisant pas à en faire une source institutionnelle.
- Le statut d'un producteur catégorie C se TRANCHE selon le contenu de l'article lui-même. Retiens influence_legitime si le contenu relève d'une expression souverainiste ou panafricaniste authentique et assumée, sans marqueur d'amplification d'une opération étrangère. Retiens ingerence_caracterisee si le contenu amplifie manifestement une opération étrangère, par reprise d'éléments de langage russes canoniques (« multipolarité », « Occident collectif », « néocolonialisme monétaire »), renvoi ou sourcing explicite vers des actifs d'influence russes, ou alignement éditorial systématique sur leurs narratifs. Retiens zone_grise dans les cas mixtes ou lorsque les indices ne sont pas concluants.
- Distinction décisive pour la catégorie C : le simple relais ou la retransmission d'une communication institutionnelle d'État (communiqué des FAMa ou de l'état-major, annonce ministérielle, compte rendu officiel, célébration protocolaire), même sans marqueur russe, ne constitue PAS une expression souverainiste authentique au sens ci-dessus. C'est une amplification de la communication d'État, à classer zone_grise. Ne retiens influence_legitime que lorsque le producteur exprime une prise de position PROPRE et argumentée, distincte de la simple retransmission d'un contenu institutionnel tiers.

FORMAT DE RÉPONSE STRICT :
STATUT: influence_legitime | ingerence_caracterisee | zone_grise
JUSTIFICATION: [deux phrases maximum]
CONFIANCE: HIGH | MEDIUM | LOW
"""

_PROMPT_SENTINEL = "<<<INFLUENCE_PROMPT_CORRIGE_A_INJECTER>>>"


# ── 1. Sélection des articles catégorie A à réanalyser ───────────────────────

SELECT_SQL = """
    SELECT c.classification_id,
           a.article_id,
           a.text_content,
           e.producer_category,
           c.influence_ingerence_status AS old_statut
    FROM articles a
    JOIN classifications c ON c.article_id = a.article_id AND c.classified_by = 'llm'
    JOIN entities e ON e.entity_id = a.entity_id
    WHERE a.in_classification_scope = 1
      AND e.producer_category = :category
    ORDER BY a.article_id
"""


def select_articles_categorieA(db_path: str, limit: int | None = None,
                               category: str = "A") -> list[dict]:
    """Lignes llm d'un producteur (catégorie paramétrable, défaut A) dans le
    scope. Lecture seule (mode=ro)."""
    sql = SELECT_SQL + ("\n    LIMIT %d" % int(limit) if limit is not None else "")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, {"category": category})]
    finally:
        conn.close()


# ── 2. Construction de la requête influence (catégorie injectée) ─────────────


def build_influence_content(art: dict) -> str:
    """Même forme que le diff adaptation 2 : catégorie en tête du contenu."""
    return (
        f"CATÉGORIE DU PRODUCTEUR DE CET ARTICLE : {art['producer_category']}"
        f"\n\n{art['text_content']}"
    )


def _influence_system() -> list[dict]:
    """Bloc system de l'appel influence avec le PROMPT CORRIGÉ. Pas de cache
    (passe unique séquentielle)."""
    return [{"type": "text", "text": INFLUENCE_PROMPT_CORRIGE_A_INJECTER}]


# ── 3. Exécution ─────────────────────────────────────────────────────────────


def _client():
    """Réutilise le client Anthropic de core/analyze.py (import paresseux :
    jamais touché en dry-run)."""
    from core.analyze import client
    return client


# Backoff des retries sur erreurs API/réseau (secondes). 2 retries max.
_API_RETRY_BACKOFFS = [2, 5]

# Erreurs API TRANSITOIRES seules → retry. Les autres anthropic.APIError
# (4xx non transitoires : BadRequest, Auth, NotFound…) ne sont PAS attrapées :
# elles remontent comme erreurs de configuration plutôt que de finir en échecs.
_RETRYABLE_API_ERRORS = (
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def _call_influence_with_retry(client, system, content):
    """Appel influence/ingérence avec retry sur erreurs API TRANSITOIRES.

    Retry jusqu'à 2 fois (backoff 2s puis 5s) sur _RETRYABLE_API_ERRORS (timeout,
    connexion, rate-limit, 5xx). Après épuisement, relève l'exception (gérée par
    l'appelant → file d'échecs). Toute autre exception — y compris une
    anthropic.APIError non transitoire — n'est PAS capturée et remonte.
    """
    for attempt in range(len(_API_RETRY_BACKOFFS) + 1):
        try:
            return client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS_INFLUENCE,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
        except _RETRYABLE_API_ERRORS as e:
            if attempt == len(_API_RETRY_BACKOFFS):
                raise
            delay = _API_RETRY_BACKOFFS[attempt]
            print(f"    erreur API ({type(e).__name__}) — retry "
                  f"{attempt + 1}/{len(_API_RETRY_BACKOFFS)} dans {delay}s…")
            time.sleep(delay)


def run(db_path: str = DEFAULT_DB_PATH, apply: bool = False,
        limit: int | None = None, category: str = "A",
        expected: int | None = None) -> dict:
    articles = select_articles_categorieA(db_path, limit=limit, category=category)
    n = len(articles)
    print(f"Articles catégorie {category} à réanalyser (scope=1 ∧ llm ∧ cat={category}) : {n}")
    if limit is None and expected is not None:
        print(f"  (attendu {expected} — confirmer avant --apply)")

    # ── DRY-RUN : aucun réseau, aucune écriture ──
    if not apply:
        sample = []
        for art in articles[:2]:
            ic = build_influence_content(art)
            sample.append({
                "classification_id": art["classification_id"],
                "article_id": art["article_id"],
                "old_statut": art["old_statut"],
                "influence_content_preview_120": ic[:120],
                "influence_content_len_chars": len(ic),
            })
        return {
            "mode": "dry-run", "applied": False, "n_articles": n,
            "model": MODEL, "max_tokens": MAX_TOKENS_INFLUENCE,
            "prompt_corrige_fourni": INFLUENCE_PROMPT_CORRIGE_A_INJECTER != _PROMPT_SENTINEL,
            "sample": sample,
        }

    # ── APPLY : garde-fous avant tout effet ──
    if INFLUENCE_PROMPT_CORRIGE_A_INJECTER == _PROMPT_SENTINEL:
        raise SystemExit(
            "REFUS : INFLUENCE_PROMPT_CORRIGE_A_INJECTER est encore le sentinelle. "
            "Injecter le prompt corrigé avant --apply."
        )
    if n == 0:
        return {"mode": "apply", "applied": False, "reason": "aucun article"}

    # Backup corpus.db AVANT toute écriture.
    ts = datetime.now()
    backup_path = f"{db_path}.bak_{ts.strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"Backup créé : {backup_path}")

    client = _client()  # lazy : appel réseau réel à partir d'ici
    system = _influence_system()

    updated: list[dict] = []   # {article_id, classification_id, old, new, confiance}
    failed: list[tuple] = []   # (article_id, raison)

    conn = sqlite3.connect(db_path)
    try:
        for art in articles:
            aid = art["article_id"]
            cid = art["classification_id"]
            content = build_influence_content(art)

            # 1) Appel API — retry sur erreurs API/réseau uniquement. Échec
            #    persistant après retries → file d'échecs (pas de crash).
            try:
                resp = _call_influence_with_retry(client, system, content)
            except _RETRYABLE_API_ERRORS as e:
                failed.append((aid, f"API (après retries) : {type(e).__name__}: {e}"))
                print(f"  art {aid} (cid {cid}) : ÉCHEC API — {type(e).__name__}: {e}")
                continue

            # 2) Parsing strict — PAS de retry (réessayer un parse échoué est
            #    inutile et consommerait du crédit) → file d'échecs directe.
            try:
                parsed = parse_influence_ingerence(resp.content[0].text)
            except ClassificationParseError as e:
                failed.append((aid, f"parse : {e}"))
                print(f"  art {aid} (cid {cid}) : ÉCHEC parse — {e}")
                continue

            # 3) Écriture (UPDATE ciblé). Toute AUTRE exception (bug, intégrité
            #    données : rowcount≠1…) REMONTE volontairement — pas avalée.
            new_statut = parsed["influence_ingerence_status"]
            update_influence_fields(
                conn, cid, new_statut,
                parsed["influence_ingerence_justification"],
                parsed["influence_ingerence_confidence"],
            )
            updated.append({
                "article_id": aid, "classification_id": cid,
                "old": art["old_statut"], "new": new_statut,
                "confiance": parsed["influence_ingerence_confidence"],
            })
            print(f"  art {aid} (cid {cid}) : {art['old_statut']} → {new_statut}")
    finally:
        conn.close()

    log_path = _write_log(ts, backup_path, updated, failed, n, category)
    print(f"\nRéanalyse terminée : {len(updated)} mis à jour, {len(failed)} échecs.")
    print(f"Log : {log_path}")
    return {
        "mode": "apply", "applied": True, "n_articles": n,
        "updated": len(updated), "failed": len(failed),
        "backup": backup_path, "log_file": log_path,
    }


def _write_log(ts, backup_path, updated, failed, n, category="A") -> str:
    import os
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    log_path = os.path.join(
        OUTPUTS_DIR, f"reanalyse_influence_categorie{category}_{ts.strftime('%Y%m%d_%H%M%S')}_log.md")
    n_change = sum(1 for u in updated if u["old"] != u["new"])
    lines = [
        f"# Log — Réanalyse statut influence, producteurs catégorie {category}",
        f"- exécuté le : {ts.isoformat()}",
        f"- périmètre : in_classification_scope=1 ∧ classified_by='llm' ∧ producer_category='{category}' ({n})",
        f"- backup pré-écriture : `{backup_path}`",
        f"- modèle : {MODEL}",
        f"- mis à jour : {len(updated)} | dont statut CHANGÉ : {n_change} | échecs : {len(failed)}",
        "- écriture : store_li.update_influence_fields (UPDATE ciblé classification_id ; "
        "aucune ligne créée/dupliquée).",
        "",
        "## Transitions par article (article_id | classification_id | ancien → nouveau | confiance)",
    ]
    for u in updated:
        flag = "  ⟵ changé" if u["old"] != u["new"] else ""
        lines.append(
            f"- {u['article_id']} | cid {u['classification_id']} | "
            f"{u['old']} → {u['new']} | {u['confiance']}{flag}")
    lines += ["", "## Échecs (file d'attente, non écrits)"]
    lines += [f"- art {aid} : {why}" for aid, why in failed] or ["- (aucun)"]
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return log_path


# ── 4. CLI ────────────────────────────────────────────────────────────────────


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="li.reanalyse_influence_categorieA")
    p.add_argument("--apply", action="store_true",
                   help="exécution réelle (backup + appels API + UPDATE + log). "
                        "Sans ce flag : dry-run sans réseau ni écriture.")
    p.add_argument("--limit", type=int, default=None,
                   help="limiter à N articles (test).")
    p.add_argument("--category", default="A",
                   help="catégorie producteur à réanalyser (défaut A).")
    p.add_argument("--expected", type=int, default=None,
                   help="effectif attendu (affiché pour confirmation avant --apply).")
    p.add_argument("--db", default=DEFAULT_DB_PATH)
    args = p.parse_args(argv)

    summary = run(args.db, apply=args.apply, limit=args.limit,
                  category=args.category, expected=args.expected)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
