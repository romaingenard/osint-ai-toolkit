"""li/classify_batch.py — orchestrateur de classification batch (Batch API).

1 batch = N articles × 2 appels (DISARM v4.2 + influence/ingérence).
Réutilise les briques existantes sans en réécrire aucune :
- li.parse_classification : parse_disarm_v42, parse_influence_ingerence, ClassificationParseError
- li.config : build_disarm_prompt(), INFLUENCE_INGERENCE_PROMPT
- li.store_li : insert_classification, DEFAULT_DB_PATH
- core.analyze : client Anthropic déjà configuré (importé en LAZY, voir _client())

Le client Anthropic n'est PAS importé au niveau module : son import déclenche la
création du client (clé API). On l'importe paresseusement uniquement dans les
chemins qui appellent réellement l'API (submit réel, collect). Le mode --dry-run
n'importe donc jamais le client et ne fait aucun appel réseau.

CLI :
  python -m li.classify_batch submit  [--limit N] [--dry-run] [--db PATH]
  python -m li.classify_batch collect --state outputs/batch_state_xxx.json [--db PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime

from li.config import build_disarm_prompt, INFLUENCE_INGERENCE_PROMPT
from li.parse_classification import (
    ClassificationParseError,
    parse_disarm_v42,
    parse_influence_ingerence,
)
from li.store_li import DEFAULT_DB_PATH, insert_classification

# Modèle = DEFAULT_MODEL_HIGH_QUALITY de core/analyze.py. Figé ici pour éviter
# d'importer core.analyze (et donc de créer le client) hors des chemins réseau.
MODEL = "claude-opus-4-7"

# max_tokens. DISARM v4.2 est verbeux : bloc PHRASES-PREUVES multi-lignes (1 ligne
# par technique), JUSTIFICATION DISARM 3-5 phrases, SAILLANCES + JUSTIFICATION
# SAILLANCES, AXES_NKILI + JUSTIFICATION AXES. Plafond mesuré : 2569 tokens pour un
# article à 10 techniques (smoke 16/06, art.4). 2048 tronquait → relevé à 6000
# (~2,3× le pire cas observé). max_tokens est un plafond facturé sur l'output réel
# uniquement : la marge inutilisée est gratuite.
# Influence/ingérence = 3 lignes courtes (<150 tokens) → 1024 largement suffisant.
MAX_TOKENS_DISARM = 6000
MAX_TOKENS_INFLUENCE = 1024

# Cache prompt : TTL 1h (batch peut dépasser 5 min ; doc Anthropic recommande 1h
# pour le contexte partagé en batch). Bloc IDENTIQUE sur toutes les requêtes d'un
# même type → entrée de cache partagée.
CACHE_CONTROL = {"type": "ephemeral", "ttl": "1h"}

CUSTOM_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

OUTPUTS_DIR = "outputs"


# ── 1. Sélection des articles à classifier ───────────────────────────────────


def select_articles_to_classify(
    db_path: str = DEFAULT_DB_PATH, limit: int | None = None
) -> list[dict]:
    """Articles dans le scope de classification, PAS déjà classés llm.

    Colonne texte = `text_content` (vérifié dans le schéma de `articles`).
    Idempotence : exclut les article_id ayant déjà une ligne classified_by='llm'.
    """
    sql = """
        SELECT a.article_id, a.text_content, e.producer_category
        FROM articles a
        JOIN entities e ON e.entity_id = a.entity_id
        WHERE a.passes_inclusion_filter = 1
          AND a.in_classification_scope = 1
          AND a.article_id NOT IN (
              SELECT article_id FROM classifications WHERE classified_by = 'llm'
          )
        ORDER BY a.article_id
    """
    if limit is not None:
        sql += f"\n        LIMIT {int(limit)}"

    # Lecture seule explicite (mode=ro) : ce SELECT n'écrit jamais.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()
    return rows


# ── 2. Construction des requêtes batch ───────────────────────────────────────


def _system_block(prompt_text: str, use_cache: bool = True) -> list[dict]:
    """Bloc system list[dict] (format Messages API).

    use_cache=True : ajoute cache_control ttl:1h (utilisé par prewarm_disarm_cache).
    use_cache=False : bloc system simple, sans cache_control → facturé en input
    normal, pas en cache-write.
    """
    block = {"type": "text", "text": prompt_text}
    if use_cache:
        block["cache_control"] = dict(CACHE_CONTROL)
    return [block]


def prewarm_disarm_cache() -> dict:
    """Pré-chauffe le cache du préfixe system DISARM (1 appel sync, hors batch).

    Écrit l'entrée de cache du gros bloc system DISARM (ttl 1h) via un appel
    synchrone trivial, de sorte que les requêtes _disarm du batch soumis juste
    après LISENT ce préfixe au lieu de le réécrire. Le bloc system est construit
    par _system_block(build_disarm_prompt()) — STRICTEMENT identique à celui de
    build_batch_requests (même texte + même cache_control), condition nécessaire
    pour que ce soit la même entrée de cache.

    Retourne le usage (cache_creation_input_tokens / cache_read_input_tokens).
    """
    client = _client()  # lazy import : appel réseau réel
    disarm_system = _system_block(build_disarm_prompt())
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1,
        system=disarm_system,
        messages=[{"role": "user", "content": "ok"}],
    )
    u = resp.usage
    created = u.cache_creation_input_tokens or 0
    read = u.cache_read_input_tokens or 0
    print(f"pré-chauffe : created={created} read={read} input={u.input_tokens}")
    return {
        "cache_creation_input_tokens": created,
        "cache_read_input_tokens": read,
        "input_tokens": u.input_tokens,
    }


def build_batch_requests(articles: list[dict]) -> list[dict]:
    """2 requêtes (Request {custom_id, params}) par article : _disarm + _influence.

    build_disarm_prompt() et INFLUENCE_INGERENCE_PROMPT sont évalués UNE fois et
    réutilisés à l'identique sur toutes les requêtes de leur type.

    Cache désactivé pour le batch (use_cache=False) : hit 0% mesuré le 16/06
    (deux smokes, pré-chauffe comprise) ; garder cache_control ttl:1h ferait payer
    la prime d'écriture (~2× input) sans aucune lecture. Réactivable en repassant
    use_cache=True si le comportement du cache batch change.
    """
    disarm_system = _system_block(build_disarm_prompt(), use_cache=False)
    influence_system = _system_block(INFLUENCE_INGERENCE_PROMPT, use_cache=False)

    requests: list[dict] = []
    for art in articles:
        article_id = art["article_id"]
        content = art["text_content"]
        # Contexte producteur injecté dans l'appel influence/ingérence UNIQUEMENT :
        # le modèle doit savoir qu'il qualifie un actif de catégorie A/B/C/D
        # (critère Viginum « caractère étranger dissimulé » du dispositif).
        influence_content = (
            f"CATÉGORIE DU PRODUCTEUR DE CET ARTICLE : {art['producer_category']}"
            f"\n\n{content}"
        )

        requests.append(
            {
                "custom_id": f"{article_id}_disarm",
                "params": {
                    "model": MODEL,
                    "max_tokens": MAX_TOKENS_DISARM,
                    "system": disarm_system,
                    "messages": [{"role": "user", "content": content}],
                },
            }
        )
        requests.append(
            {
                "custom_id": f"{article_id}_influence",
                "params": {
                    "model": MODEL,
                    "max_tokens": MAX_TOKENS_INFLUENCE,
                    "system": influence_system,
                    "messages": [{"role": "user", "content": influence_content}],
                },
            }
        )
    return requests


def _validate_requests(requests: list[dict], n_articles: int) -> dict:
    """Validations locales (aucun réseau). Retourne un dict de checks bool."""
    custom_ids = [r["custom_id"] for r in requests]
    checks = {
        "n_articles": n_articles,
        "n_requests": len(requests),
        "n_requests_ok": len(requests) == 2 * n_articles,
        "custom_ids_uniques": len(custom_ids) == len(set(custom_ids)),
        "custom_ids_conformes_regex": all(CUSTOM_ID_RE.match(c) for c in custom_ids),
        "systems_non_vides": all(
            r["params"]["system"] and r["params"]["system"][0]["text"] for r in requests
        ),
        # Batch en mode cache désactivé : on vérifie l'ABSENCE de cache_control
        # (hit 0% mesuré le 16/06 → la prime d'écriture serait payée sans lecture).
        "cache_control_absent_batch": all(
            "cache_control" not in r["params"]["system"][0] for r in requests
        ),
        "model": MODEL,
        "max_tokens_disarm": MAX_TOKENS_DISARM,
        "max_tokens_influence": MAX_TOKENS_INFLUENCE,
    }
    return checks


# ── 3. Submit ─────────────────────────────────────────────────────────────────


def submit_batch(
    db_path: str = DEFAULT_DB_PATH, limit: int | None = None, dry_run: bool = False
) -> dict:
    """Construit (et en mode réel soumet) le batch. dry_run => zéro appel réseau."""
    articles = select_articles_to_classify(db_path, limit=limit)
    requests = build_batch_requests(articles)
    checks = _validate_requests(requests, len(articles))

    if dry_run:
        # Échantillon des 2 premières requêtes (system tronqué à 200 car) pour preuve.
        sample = []
        for r in requests[:2]:
            sys_text = r["params"]["system"][0]["text"]
            sample.append(
                {
                    "custom_id": r["custom_id"],
                    "params_keys": sorted(r["params"].keys()),
                    "model": r["params"]["model"],
                    "max_tokens": r["params"]["max_tokens"],
                    "system_cache_control": r["params"]["system"][0].get("cache_control"),
                    "system_len_chars": len(sys_text),
                    "system_preview_200": sys_text[:200],
                    "user_content_len_chars": len(r["params"]["messages"][0]["content"]),
                }
            )
        summary = {"mode": "dry-run", "submitted": False, "checks": checks, "sample": sample}
        return summary

    # ── Chemin réel (NON exécuté dans cette tâche) ──
    if not articles:
        return {"mode": "submit", "submitted": False, "reason": "aucun article à classifier"}

    client = _client()  # lazy import : crée/réutilise le client Anthropic
    batch = client.messages.batches.create(requests=requests)

    ts = datetime.now()
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    state_path = os.path.join(OUTPUTS_DIR, f"batch_state_{ts.strftime('%Y%m%d_%H%M%S')}.json")
    state = {
        "batch_id": batch.id,
        "submitted_at": ts.isoformat(),
        "n_requests": len(requests),
        "article_ids": [a["article_id"] for a in articles],
        "model": MODEL,
        "status": "submitted",
    }
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    return {"mode": "submit", "submitted": True, "batch_id": batch.id,
            "n_requests": len(requests), "state_file": state_path}


# ── 4. Collect (écrit complètement ; NON exécuté dans cette tâche) ────────────


def _result_type(resp) -> str:
    return resp.result.type if resp is not None else "absent"


def process_batch_results(
    results,
    batch_id: str,
    db_path: str = DEFAULT_DB_PATH,
    output_dir: str = OUTPUTS_DIR,
) -> dict:
    """Dépouillement PUR (aucun réseau) : prend un itérable de résultats batch.

    Regroupe par article_id, applique le tout-ou-rien (2 moitiés succeeded +
    parsing strict), insère, instrumente le cache et écrit le log. Testable en
    injectant des résultats factices. `results` = itérable d'objets exposant
    custom_id, result.type, result.message.content[0].text, result.message.usage.
    """
    # Passe unique : regroupement par article (custom_id = "<article_id>_<kind>")
    # ET agrégation cache/facturation sur TOUTES les requêtes succeeded,
    # indépendamment du gate tout-ou-rien (c'est ce qui a réellement été facturé,
    # qu'un article finisse inséré ou en file d'échecs).
    by_article: dict[str, dict] = {}
    cache_read = cache_creation = input_tokens = output_tokens = 0
    n_requests_succeeded = 0
    service_tiers: set[str] = set()

    for resp in results:
        art_str, kind = resp.custom_id.rsplit("_", 1)
        by_article.setdefault(art_str, {})[kind] = resp
        if resp.result.type == "succeeded":
            n_requests_succeeded += 1
            u = resp.result.message.usage
            cache_read += u.cache_read_input_tokens or 0
            cache_creation += u.cache_creation_input_tokens or 0
            input_tokens += u.input_tokens or 0
            output_tokens += u.output_tokens or 0
            if u.service_tier:
                service_tiers.add(u.service_tier)

    # Insertion : gate tout-ou-rien strict (indépendant de la compta cache ci-dessus).
    inserted: list[int] = []
    failed: list[tuple[int, str]] = []

    for art_str, halves in by_article.items():
        article_id = int(art_str)
        d_resp = halves.get("disarm")
        i_resp = halves.get("influence")

        # Tout-ou-rien : les 2 moitiés présentes ET succeeded.
        if (
            d_resp is None
            or i_resp is None
            or d_resp.result.type != "succeeded"
            or i_resp.result.type != "succeeded"
        ):
            failed.append(
                (article_id, f"moitié manquante/échouée : "
                 f"disarm={_result_type(d_resp)} influence={_result_type(i_resp)}")
            )
            continue

        # Parsing strict : tout-ou-rien.
        try:
            disarm = parse_disarm_v42(d_resp.result.message.content[0].text)
            infl = parse_influence_ingerence(i_resp.result.message.content[0].text)
        except ClassificationParseError as e:
            failed.append((article_id, f"parse : {e}"))
            continue

        record = {
            **disarm,
            **infl,
            "article_id": article_id,
            "classified_by": "llm",
            "model_version": MODEL,
        }
        try:
            insert_classification(record, db_path=db_path)
            inserted.append(article_id)
        except Exception as e:  # noqa: BLE001
            failed.append((article_id, f"insert : {type(e).__name__}: {e}"))

    total_input = cache_read + cache_creation + input_tokens
    hit_rate = (cache_read / total_input) if total_input else 0.0

    # Log markdown dans output_dir.
    ts = datetime.now()
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, f"batch_collect_{ts.strftime('%Y%m%d_%H%M%S')}_log.md")
    lines = [
        f"# Collecte batch {batch_id}",
        f"- collecté le : {ts.isoformat()}",
        f"- articles insérés (gate tout-ou-rien) : {len(inserted)}",
        f"- articles en échec : {len(failed)}",
        "",
        "## Cache / facturation (sur requêtes succeeded)",
        f"- compté pour le cache : {n_requests_succeeded} requêtes succeeded (insérées ou non)",
        f"- cache_read_input_tokens : {cache_read}",
        f"- cache_creation_input_tokens : {cache_creation}",
        f"- input_tokens (non cachés) : {input_tokens}",
        f"- output_tokens : {output_tokens}",
        f"- taux de hit cache (read / total input) : {hit_rate:.1%}",
        f"- service_tier(s) observés : {sorted(service_tiers) or '(aucun)'}",
        "",
        "## File d'échecs",
    ]
    if failed:
        lines += [f"- article {aid} : {reason}" for aid, reason in failed]
    else:
        lines.append("- (aucun)")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return {
        "status": "collected",
        "inserted": len(inserted),
        "failed": len(failed),
        "inserted_ids": inserted,
        "failed_details": failed,
        "n_requests_succeeded": n_requests_succeeded,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_hit_rate": hit_rate,
        "service_tiers": sorted(service_tiers),
        "log_file": log_path,
    }


def collect_batch(state_file: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    """Récupère les résultats d'un batch terminé et délègue le dépouillement.

    Non bloquant : si le batch n'est pas 'ended', affiche le décompte et sort.
    Seul ce wrapper touche le réseau ; toute la logique est dans
    process_batch_results (testable hors-ligne).
    """
    client = _client()  # lazy import

    with open(state_file, encoding="utf-8") as f:
        state = json.load(f)
    batch_id = state["batch_id"]

    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        rc = batch.request_counts
        print(f"Batch {batch_id} : statut = {batch.processing_status} (non terminé).")
        print(
            f"  processing={rc.processing} succeeded={rc.succeeded} "
            f"errored={rc.errored} canceled={rc.canceled} expired={rc.expired}"
        )
        print("Aucune insertion. Relancer collect plus tard.")
        return {"status": batch.processing_status, "inserted": 0, "failed": 0}

    result = process_batch_results(
        client.messages.batches.results(batch_id), batch_id, db_path=db_path
    )

    # Mise à jour du state_file.
    state.update(
        {"status": "collected", "n_inserted": result["inserted"], "n_failed": result["failed"]}
    )
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(
        f"Collecte terminée : {result['inserted']} insérés, "
        f"{result['failed']} échecs. Log : {result['log_file']}"
    )
    return result


# ── Client Anthropic (lazy, réutilise celui de core/analyze.py) ───────────────


def _client():
    """Réutilise le client déjà configuré dans core/analyze.py (pas de nouvelle clé)."""
    from core.analyze import client  # import paresseux : jamais en dry-run
    return client


# ── 5. CLI ────────────────────────────────────────────────────────────────────


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="li.classify_batch")
    sub = parser.add_subparsers(dest="command", required=True)

    p_submit = sub.add_parser("submit", help="construit (et soumet) le batch")
    p_submit.add_argument("--limit", type=int, default=None)
    p_submit.add_argument("--dry-run", action="store_true")
    p_submit.add_argument("--db", default=DEFAULT_DB_PATH)

    p_collect = sub.add_parser("collect", help="récupère les résultats d'un batch")
    p_collect.add_argument("--state", required=True)
    p_collect.add_argument("--db", default=DEFAULT_DB_PATH)

    sub.add_parser("prewarm", help="pré-chauffe le cache du préfixe system DISARM")

    args = parser.parse_args(argv)

    if args.command == "prewarm":
        prewarm_disarm_cache()
        return 0

    if args.command == "submit":
        summary = submit_batch(args.db, limit=args.limit, dry_run=args.dry_run)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.command == "collect":
        collect_batch(args.state, db_path=args.db)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
