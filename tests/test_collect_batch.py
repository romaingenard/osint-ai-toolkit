"""Tests de collect_batch sur résultats SIMULÉS (aucun réseau, base jetable /tmp).

Faux résultats reproduisant la structure SDK MessageBatchIndividualResponse :
  resp.custom_id
  resp.result.type
  resp.result.message.content[0].text   (sur succeeded)
  resp.result.message.usage.{input_tokens, output_tokens,
      cache_read_input_tokens, cache_creation_input_tokens, service_tier}

corpus.db n'est JAMAIS touché : tout sur /tmp, log de collecte écrit dans /tmp.
Compatible pytest + runner autonome (__main__), comme les autres tests du projet.
"""

import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from types import SimpleNamespace as NS

sys.path.insert(0, ".")
import li.classify_batch as cb  # noqa: E402
from li.classify_batch import collect_batch, process_batch_results, MODEL  # noqa: E402
from li.store_li import _DDL_CLASSIFICATIONS  # noqa: E402
from tests.test_parse_classification import (  # noqa: E402
    DISARM_NOMINAL,
    INFLUENCE_NOMINAL,
)

# DISARM malformé : SAILLANCES retirée -> parse_disarm_v42 lève.
DISARM_MALFORMED = "\n".join(
    l for l in DISARM_NOMINAL.splitlines() if not l.startswith("SAILLANCES:")
)


@contextmanager
def raises(exc_type):
    try:
        yield
    except exc_type:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(
            f"exception {type(e).__name__} levée, attendu {exc_type.__name__}"
        ) from e
    raise AssertionError(f"aucune exception levée, attendu {exc_type.__name__}")


# ── Fabriques de faux résultats ──────────────────────────────────────────────


def _usage(input_tokens, cache_read, cache_creation, tier="batch", output_tokens=200):
    return NS(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
        service_tier=tier,
    )


def _succeeded(custom_id, text, usage):
    msg = NS(content=[NS(text=text)], usage=usage)
    return NS(custom_id=custom_id, result=NS(type="succeeded", message=msg))


def _failed(custom_id, rtype="errored"):
    # pas de .message : le code n'y accède jamais quand type != "succeeded"
    return NS(custom_id=custom_id, result=NS(type=rtype, message=None))


def _setup_db(path):
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE articles (article_id INTEGER PRIMARY KEY);")
    conn.executescript(_DDL_CLASSIFICATIONS)
    conn.executemany(
        "INSERT INTO articles (article_id) VALUES (?)", [(1,), (2,), (3,), (4,)]
    )
    conn.commit()
    conn.close()


# ── Test principal : dépouillement complet (cas a-e) ─────────────────────────


def test_collect_depouillement_tout_ou_rien_et_cache():
    DB = "/tmp/test_collect_batch.db"
    _setup_db(DB)

    results = [
        # a. article 1 : 2 moitiés succeeded -> insérée
        _succeeded("1_disarm", DISARM_NOMINAL, _usage(1800, 0, 20000)),       # création cache
        _succeeded("1_influence", INFLUENCE_NOMINAL, _usage(1800, 20000, 0)),  # hit cache
        # b. article 2 : influence ERRORED -> tout-ou-rien, échec
        _succeeded("2_disarm", DISARM_NOMINAL, _usage(1800, 20000, 0)),
        _failed("2_influence", "errored"),
        # c. article 3 : disarm malformé -> ClassificationParseError, échec
        _succeeded("3_disarm", DISARM_MALFORMED, _usage(1800, 20000, 0)),
        _succeeded("3_influence", INFLUENCE_NOMINAL, _usage(1800, 20000, 0)),
        # d. article 4 : moitié influence absente -> tout-ou-rien, échec
        _succeeded("4_disarm", DISARM_NOMINAL, _usage(1800, 20000, 0)),
    ]

    summary = process_batch_results(results, "fake_batch_test", db_path=DB, output_dir="/tmp")

    # 4. Vérifications en base jetable
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM classifications").fetchone()[0]
    assert total == 1, f"attendu 1 ligne, trouvé {total}"

    # article 1 présent avec champs fusionnés des 2 appels
    row = dict(conn.execute("SELECT * FROM classifications WHERE article_id=1").fetchone())
    assert row["orchestration"] == "ORCHESTRÉE_ÉTRANGÈRE"
    assert row["salience_russe"] == 2
    assert row["influence_ingerence_status"] == "ingerence_caracterisee"
    assert row["influence_ingerence_confidence"] == "MEDIUM"
    assert row["classified_by"] == "llm"
    assert row["model_version"] == MODEL
    assert row["classified_at"] is not None
    # disarm_techniques re-désérialisé = liste de dicts
    techniques = json.loads(row["disarm_techniques"])
    assert techniques == [
        {"code": "T0002", "nom": "Facilitate State Propaganda"},
        {"code": "T0003", "nom": "Leverage Existing Narratives"},
    ]

    # articles 2,3,4 absents de la base
    absent = conn.execute(
        "SELECT COUNT(*) FROM classifications WHERE article_id IN (2,3,4)"
    ).fetchone()[0]
    conn.close()
    assert absent == 0, f"articles 2/3/4 ne doivent pas être insérés, trouvé {absent}"

    # file d'échecs = 2,3,4 avec raisons
    assert summary["inserted"] == 1
    assert summary["failed"] == 3
    assert summary["inserted_ids"] == [1]
    failed_ids = {aid for aid, _ in summary["failed_details"]}
    assert failed_ids == {2, 3, 4}, failed_ids
    reasons = {aid: reason for aid, reason in summary["failed_details"]}
    assert "errored" in reasons[2]            # influence errored
    assert reasons[3].startswith("parse :")   # SAILLANCES manquante
    assert "manquante" in reasons[4]           # influence absent

    # e. cache compté sur TOUTES les requêtes succeeded (gate-indépendant).
    #    succeeded = 6 requêtes (toutes sauf 2_influence errored) :
    #      1_disarm  : read=0     creation=20000 input=1800
    #      1_influence: read=20000               input=1800
    #      2_disarm  : read=20000               input=1800   <- ORPHELIN (art.2 non inséré)
    #      3_disarm  : read=20000               input=1800
    #      3_influence: read=20000               input=1800
    #      4_disarm  : read=20000               input=1800   <- ORPHELIN (art.4 non inséré)
    #    => read=100000, creation=20000, input=10800, output=6*200=1200
    assert summary["n_requests_succeeded"] == 6
    assert summary["cache_read"] == 100000      # 60000 (gate) + 40000 (2 orphelins comptés)
    assert summary["cache_creation"] == 20000
    assert summary["input_tokens"] == 10800
    assert summary["output_tokens"] == 1200
    expected_hit = 100000 / (100000 + 20000 + 10800)
    assert abs(summary["cache_hit_rate"] - expected_hit) < 1e-9
    assert summary["service_tiers"] == ["batch"]
    # preuve : les orphelins succeeded sont comptés alors que leur article n'est PAS inséré
    assert summary["inserted_ids"] == [1]  # seul l'article 1 inséré
    # 6 succeeded comptés > 2 requêtes de l'unique article inséré -> orphelins inclus
    assert summary["n_requests_succeeded"] > 2 * len(summary["inserted_ids"])

    # log écrit dans /tmp, contient cache (avec ligne explicite) + file d'échecs
    assert summary["log_file"].startswith("/tmp/")
    with open(summary["log_file"], encoding="utf-8") as f:
        log = f.read()
    assert "taux de hit cache" in log
    assert "compté pour le cache : 6 requêtes succeeded (insérées ou non)" in log
    assert "article 2 :" in log and "article 3 :" in log and "article 4 :" in log

    print("\n----- LOG DE COLLECTE GÉNÉRÉ -----")
    print(log.rstrip())
    print("----------------------------------")

    os.remove(DB)
    os.remove(summary["log_file"])


# ── Test f : batch non terminé -> non bloquant, aucune insertion ─────────────


def test_collect_batch_non_termine_non_bloquant():
    DB = "/tmp/test_collect_inprog.db"
    _setup_db(DB)
    state_path = "/tmp/test_state_inprog.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"batch_id": "fake_in_progress"}, f)

    # faux client : retrieve renvoie un batch in_progress ; results NE doit PAS être appelé
    fake_batch = NS(
        processing_status="in_progress",
        request_counts=NS(processing=658, succeeded=0, errored=0, canceled=0, expired=0),
    )

    def _no_results(_bid):
        raise AssertionError("batches.results ne doit pas être appelé si non terminé")

    fake_client = NS(
        messages=NS(batches=NS(retrieve=lambda bid: fake_batch, results=_no_results))
    )

    original = cb._client
    cb._client = lambda: fake_client  # monkeypatch : zéro réseau
    try:
        res = collect_batch(state_path, db_path=DB)
    finally:
        cb._client = original

    assert res["status"] == "in_progress"
    assert res["inserted"] == 0 and res["failed"] == 0

    conn = sqlite3.connect(DB)
    count = conn.execute("SELECT COUNT(*) FROM classifications").fetchone()[0]
    conn.close()
    assert count == 0, f"aucune insertion attendue, trouvé {count}"

    os.remove(DB)
    os.remove(state_path)


# ── Runner autonome ──────────────────────────────────────────────────────────


def _main() -> int:
    tests = sorted(
        (name, obj)
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    )
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASSED  {name}")
        except Exception as e:  # noqa: BLE001
            failures.append((name, e))
            print(f"FAILED  {name}: {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - len(failures)} passed, {len(failures)} failed (sur {len(tests)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
