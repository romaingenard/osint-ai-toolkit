"""li/store_li.py — persistance SQLite du corpus LI.

Refonte : 24 avril 2026. Séparé de core/store_cti.py (pipeline CTI distinct).

Base : data/corpus.db, cinq tables :
- entities : 30-45 entités du corpus (importées depuis data/entities.csv).
- articles : contenus collectés (web, Telegram, événements ponctuels).
- classifications : DISARM + saillances + influence/ingérence, une ligne par
  source de classification (manual / llm) pour la méthode Centaure.
- reformulation_pairs : prévue pour le brief 2 (grille de reformulation).
- coordination_events : prévue pour le brief 2 (clustering temporel).

Convention JSON (champs sérialisés texte SQLite, désérialisés côté API) :
- classifications.disarm_techniques : liste de dicts [{"code":"T0115","name":"Post Content"}, ...]
- coordination_events.article_ids : liste d'entiers [123, 456, 789]
- coordination_events.countries_involved : liste de strings ["MLI", "BFA"]

Les fonctions insert_* / query_* encapsulent les json.dumps/json.loads pour
que le code appelant manipule des objets Python natifs.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from li.config import INFLUENCE_INGERENCE_STATUS


DEFAULT_DB_PATH = "data/corpus.db"


# === SCHÉMA ===============================================================
# DDL isolée en constantes pour rendre init_db() lisible et idempotent.

_DDL_ENTITIES = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    platform TEXT NOT NULL CHECK(platform IN ('web', 'telegram', 'facebook', 'tiktok', 'x', 'youtube')),
    producer_category TEXT NOT NULL CHECK(producer_category IN ('A', 'B', 'C', 'D')),
    country TEXT NOT NULL CHECK(country IN ('MLI', 'BFA', 'NER', 'SUPRA')),
    collector TEXT NOT NULL,
    html_title_selector TEXT,
    html_date_selector TEXT,
    html_content_selector TEXT,
    rate_limit_seconds REAL DEFAULT 2.0,
    status TEXT NOT NULL CHECK(status IN ('active', 'inactive', 'paywall', 'geoblocked')),
    default_language TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('primary', 'd3lta_validation')),
    notes TEXT,
    imported_at TEXT NOT NULL
);
"""

_DDL_ARTICLES = """
CREATE TABLE IF NOT EXISTS articles (
    article_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    url TEXT NOT NULL,
    title TEXT,
    date_published TEXT,
    collected_at TEXT NOT NULL,
    language TEXT NOT NULL,
    text_content TEXT NOT NULL,
    text_hash TEXT NOT NULL UNIQUE,
    archive_wayback_url TEXT,
    archive_local_path TEXT,
    collection_mode TEXT NOT NULL CHECK(collection_mode IN ('scan', 'event')),
    is_duplicate_for_d3lta INTEGER NOT NULL DEFAULT 0,
    passes_inclusion_filter INTEGER NOT NULL DEFAULT 0,
    inclusion_filter_reason TEXT
);
"""

_DDL_ARTICLES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_articles_entity ON articles(entity_id);",
    "CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date_published);",
    "CREATE INDEX IF NOT EXISTS idx_articles_language ON articles(language);",
]

_DDL_CLASSIFICATIONS = """
CREATE TABLE IF NOT EXISTS classifications (
    classification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(article_id),
    classified_at TEXT NOT NULL,
    classified_by TEXT NOT NULL CHECK(classified_by IN ('manual', 'llm')),
    model_version TEXT,

    disarm_status TEXT CHECK(disarm_status IN ('classified', 'hors_scope', 'pas_technique_disarm')),
    disarm_tactic_code TEXT,
    disarm_tactic_name TEXT,
    disarm_techniques TEXT,
    disarm_justification TEXT,
    disarm_confidence TEXT CHECK(disarm_confidence IN ('HIGH', 'MEDIUM', 'LOW')),

    salience_russe INTEGER CHECK(salience_russe IN (0, 1, 2)),
    salience_panafricaniste INTEGER CHECK(salience_panafricaniste IN (0, 1, 2)),
    salience_souverainiste INTEGER CHECK(salience_souverainiste IN (0, 1, 2)),
    salience_nationale_aes INTEGER CHECK(salience_nationale_aes IN (0, 1, 2)),
    salience_justification TEXT,

    influence_ingerence_status TEXT CHECK(
        influence_ingerence_status IN ('influence_legitime', 'ingerence_caracterisee', 'zone_grise')
    ),
    influence_ingerence_justification TEXT,
    influence_ingerence_confidence TEXT,

    signature_symbolique TEXT,
    axes_lexicaux_nkili TEXT,
    narratif_structure TEXT,
    commentaire_calibrage TEXT,
    orchestration TEXT,
    degre_orchestration TEXT,
    enonciateur TEXT,
    phrases_preuves TEXT,
    axes_nkili_justification TEXT
);
"""

_DDL_CLASSIFICATIONS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_classif_article ON classifications(article_id);",
    "CREATE INDEX IF NOT EXISTS idx_classif_source ON classifications(classified_by);",
]

_DDL_REFORMULATION_PAIRS = """
CREATE TABLE IF NOT EXISTS reformulation_pairs (
    pair_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_article_id INTEGER NOT NULL REFERENCES articles(article_id),
    relay_article_id INTEGER NOT NULL REFERENCES articles(article_id),
    country_relay TEXT,
    producer_category_relay TEXT,
    grille_colonne TEXT CHECK(grille_colonne IN ('identique', 'reformule', 'adapte', 'transforme')),
    commentaire TEXT,
    annotated_at TEXT,
    annotated_by TEXT
);
"""

_DDL_COORDINATION_EVENTS = """
CREATE TABLE IF NOT EXISTS coordination_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL,
    coordination_type TEXT NOT NULL CHECK(
        coordination_type IN ('ai_strict', 'ai_to_local_relay', 'cross_country')
    ),
    timestamp_center TEXT NOT NULL,
    article_ids TEXT NOT NULL,
    countries_involved TEXT,
    similarity_score REAL,
    method TEXT,
    commentaire TEXT
);
"""


# === INIT =================================================================

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Crée les 5 tables et leurs index si absents. Idempotent.

    Crée aussi le dossier parent du fichier DB s'il n'existe pas.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        cursor.execute(_DDL_ENTITIES)
        cursor.execute(_DDL_ARTICLES)
        for stmt in _DDL_ARTICLES_INDEXES:
            cursor.execute(stmt)
        cursor.execute(_DDL_CLASSIFICATIONS)
        for stmt in _DDL_CLASSIFICATIONS_INDEXES:
            cursor.execute(stmt)
        cursor.execute(_DDL_REFORMULATION_PAIRS)
        cursor.execute(_DDL_COORDINATION_EVENTS)
        conn.commit()


# === ENTITIES =============================================================

def import_entities_from_csv(
    csv_path: str,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Importe data/entities.csv dans la table entities (UPSERT par entity_id).

    Délègue le parsing et la validation à li.config.load_entities() pour
    éviter la duplication des règles. Retourne le nombre de lignes upsertées.
    """
    # Import local pour éviter le cycle li.config ↔ li.store_li au chargement.
    from li.config import load_entities

    entities = load_entities(csv_path)
    imported_at = datetime.now().isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        for e in entities:
            cursor.execute(
                """
                INSERT INTO entities (
                    entity_id, name, url, platform, producer_category, country,
                    collector, html_title_selector, html_date_selector,
                    html_content_selector, rate_limit_seconds, status,
                    default_language, role, notes, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    name = excluded.name,
                    url = excluded.url,
                    platform = excluded.platform,
                    producer_category = excluded.producer_category,
                    country = excluded.country,
                    collector = excluded.collector,
                    html_title_selector = excluded.html_title_selector,
                    html_date_selector = excluded.html_date_selector,
                    html_content_selector = excluded.html_content_selector,
                    rate_limit_seconds = excluded.rate_limit_seconds,
                    status = excluded.status,
                    default_language = excluded.default_language,
                    role = excluded.role,
                    notes = excluded.notes,
                    imported_at = excluded.imported_at
                """,
                (
                    e["entity_id"],
                    e["name"],
                    e["url"],
                    e["platform"],
                    e["producer_category"],
                    e["country"],
                    e["collector"],
                    e["html_title_selector"] or None,
                    e["html_date_selector"] or None,
                    e["html_content_selector"] or None,
                    e["rate_limit_seconds"],
                    e["status"],
                    e["default_language"],
                    e["role"],
                    e.get("notes") or None,
                    imported_at,
                ),
            )
        conn.commit()

    return len(entities)


def get_entity(entity_id: str, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    """Lit une entité par son id. Retourne un dict ou None."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entities WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# === ARTICLES =============================================================

_ARTICLES_COLUMNS = [
    "entity_id",
    "url",
    "title",
    "date_published",
    "collected_at",
    "language",
    "text_content",
    "text_hash",
    "archive_wayback_url",
    "archive_local_path",
    "collection_mode",
    "is_duplicate_for_d3lta",
    "passes_inclusion_filter",
    "inclusion_filter_reason",
]


def insert_article(
    article_data: dict,
    db_path: str = DEFAULT_DB_PATH,
) -> int | None:
    """Insère un article. Retourne article_id ou None si doublon text_hash.

    Attendu dans article_data : toutes les colonnes de _ARTICLES_COLUMNS.
    text_hash doit être pré-calculé (SHA-256 de text_content) côté appelant
    — le hash est utilisé pour la dédup avant même d'arriver ici.

    La dédup s'appuie sur UNIQUE(text_hash) : une IntegrityError sur cette
    contrainte est convertie en retour None (skip silencieux côté DB ;
    l'orchestrateur logue déjà le skip).
    """
    missing = [c for c in _ARTICLES_COLUMNS if c not in article_data]
    if missing:
        raise ValueError(f"insert_article : champs manquants {missing}")

    placeholders = ", ".join("?" * len(_ARTICLES_COLUMNS))
    columns = ", ".join(_ARTICLES_COLUMNS)
    values = tuple(article_data[c] for c in _ARTICLES_COLUMNS)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"INSERT INTO articles ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError as e:
            if "UNIQUE" in str(e) and "text_hash" in str(e):
                return None
            raise


def article_exists_by_hash(
    text_hash: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Vérifie présence d'un article de même hash. Utilisé avant archivage
    coûteux pour éviter de soumettre Wayback sur un contenu déjà capturé."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM articles WHERE text_hash = ? LIMIT 1",
            (text_hash,),
        )
        return cursor.fetchone() is not None


# === CLASSIFICATIONS ======================================================

# Colonnes scalaires (non-JSON) attendues. disarm_techniques est traité à
# part car c'est le seul champ sérialisé JSON de cette table.
_CLASSIF_SCALAR_COLUMNS = [
    "article_id",
    "classified_at",
    "classified_by",
    "model_version",
    "disarm_status",
    "disarm_tactic_code",
    "disarm_tactic_name",
    "disarm_justification",
    "disarm_confidence",
    "orchestration",
    "degre_orchestration",
    "enonciateur",
    "salience_russe",
    "salience_panafricaniste",
    "salience_souverainiste",
    "salience_nationale_aes",
    "salience_justification",
    "influence_ingerence_status",
    "influence_ingerence_justification",
    "influence_ingerence_confidence",
    "signature_symbolique",
    "axes_lexicaux_nkili",
    "phrases_preuves",
    "axes_nkili_justification",
    "narratif_structure",
    "commentaire_calibrage",
]


def insert_classification(
    classification_data: dict,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Insère une classification (manual ou llm). Retourne classification_id.

    disarm_techniques (liste de dicts) est sérialisé en JSON avant stockage.
    Tous les autres champs absents du dict sont stockés NULL (utile pour
    les classifications partielles, ex. seulement les saillances).
    """
    if "article_id" not in classification_data:
        raise ValueError("insert_classification : article_id obligatoire")
    if "classified_by" not in classification_data:
        raise ValueError("insert_classification : classified_by obligatoire")

    # classified_at par défaut = maintenant, si non fourni.
    classification_data.setdefault("classified_at", datetime.now().isoformat())

    all_columns = _CLASSIF_SCALAR_COLUMNS + ["disarm_techniques"]
    values = []
    for col in _CLASSIF_SCALAR_COLUMNS:
        values.append(classification_data.get(col))

    techniques = classification_data.get("disarm_techniques")
    values.append(json.dumps(techniques) if techniques is not None else None)

    placeholders = ", ".join("?" * len(all_columns))
    columns = ", ".join(all_columns)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO classifications ({columns}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
        return cursor.lastrowid


def update_influence_fields(
    conn: sqlite3.Connection,
    classification_id: int,
    statut: str,
    justification: str | None,
    confiance: str | None,
) -> int:
    """UPDATE partiel ciblé des 3 champs influence/ingérence d'UNE classification.

    Corrige uniquement influence_ingerence_status / _justification / _confidence
    de la ligne identifiée par `classification_id` (PK). Toutes les autres colonnes
    (DISARM, saillances, axes Nkili…) restent inchangées. Aucune ligne n'est créée
    ni dupliquée (UPDATE, pas INSERT).

    Transactionnel sur la connexion fournie : commit si exactement 1 ligne modifiée,
    rollback + ValueError sinon (ex. classification_id inexistant → rowcount 0).

    `statut` est validé contre INFLUENCE_INGERENCE_STATUS (domaine aligné sur le
    CHECK de la table) AVANT toute écriture : une valeur hors liste lève ValueError
    sans qu'aucun UPDATE ne soit exécuté.

    Cible par classification_id (PK), jamais par article_id, pour ne toucher qu'une
    ligne précise (la table n'a pas de contrainte d'unicité article_id+classified_by).
    """
    if statut not in INFLUENCE_INGERENCE_STATUS:
        raise ValueError(
            f"update_influence_fields : statut invalide {statut!r} "
            f"(attendu {sorted(INFLUENCE_INGERENCE_STATUS)})"
        )

    cursor = conn.execute(
        """
        UPDATE classifications
           SET influence_ingerence_status = ?,
               influence_ingerence_justification = ?,
               influence_ingerence_confidence = ?
         WHERE classification_id = ?
        """,
        (statut, justification, confiance, classification_id),
    )
    if cursor.rowcount != 1:
        conn.rollback()
        raise ValueError(
            f"update_influence_fields : rowcount={cursor.rowcount} != 1 pour "
            f"classification_id={classification_id} — rollback, aucune écriture."
        )
    conn.commit()
    return cursor.rowcount


def _row_to_classification_dict(row: sqlite3.Row) -> dict:
    """Désérialise disarm_techniques de JSON → liste[dict]."""
    d = dict(row)
    techniques_raw = d.get("disarm_techniques")
    d["disarm_techniques"] = (
        json.loads(techniques_raw) if techniques_raw else None
    )
    return d


def get_centaure_paired_classifications(
    article_id: int,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    """Retourne les classifications manual + llm d'un même article.

    Format : {'manual': <dict ou None>, 'llm': <dict ou None>}. Utilisé par
    core/analyze.compare_classifications() pour appliquer la méthode
    Centaure (Mollick 2024).

    Si plusieurs lignes existent pour une même source (ré-classification),
    la plus récente (classified_at max) l'emporte.
    """
    result: dict = {"manual": None, "llm": None}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        for source in ("manual", "llm"):
            cursor.execute(
                """
                SELECT * FROM classifications
                WHERE article_id = ? AND classified_by = ?
                ORDER BY classified_at DESC
                LIMIT 1
                """,
                (article_id, source),
            )
            row = cursor.fetchone()
            if row:
                result[source] = _row_to_classification_dict(row)
    return result


# === ANALYSE DENSITÉ CORPUS ===============================================

def get_corpus_density_by_country(db_path: str = DEFAULT_DB_PATH) -> dict:
    """Compteurs par pays × plateforme × catégorie producteur.

    Utilisé pour le tableau de densité annexé au rapport.
    Format retourné : {country: {platform: {category: count}}}.
    Ne compte que les articles qui ont passé le pré-filtre d'inclusion
    (passes_inclusion_filter=1) : c'est le corpus réellement analysable.
    """
    result: dict = {}
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT e.country, e.platform, e.producer_category, COUNT(*) AS n
            FROM articles a
            JOIN entities e ON a.entity_id = e.entity_id
            WHERE a.passes_inclusion_filter = 1
            GROUP BY e.country, e.platform, e.producer_category
            """
        )
        for country, platform, category, n in cursor.fetchall():
            result.setdefault(country, {}).setdefault(platform, {})[category] = n
    return result


# === QUERY ARTICLES =======================================================

def query_articles(
    country: str | None = None,
    platform: str | None = None,
    producer_category: str | None = None,
    language: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    passes_filter_only: bool = True,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Retourne les articles matchant les filtres, joints avec entities.

    Les colonnes des deux tables sont renvoyées (l'entité d'un article est
    souvent utile côté appelant pour la classification et l'affichage).
    """
    sql = [
        """
        SELECT
            a.*,
            e.name AS entity_name,
            e.country AS country,
            e.platform AS platform,
            e.producer_category AS producer_category,
            e.role AS role
        FROM articles a
        JOIN entities e ON a.entity_id = e.entity_id
        WHERE 1 = 1
        """
    ]
    params: list = []

    if passes_filter_only:
        sql.append(" AND a.passes_inclusion_filter = 1")
    if country is not None:
        sql.append(" AND e.country = ?")
        params.append(country)
    if platform is not None:
        sql.append(" AND e.platform = ?")
        params.append(platform)
    if producer_category is not None:
        sql.append(" AND e.producer_category = ?")
        params.append(producer_category)
    if language is not None:
        sql.append(" AND a.language = ?")
        params.append(language)
    if date_from is not None:
        sql.append(" AND a.date_published >= ?")
        params.append(date_from)
    if date_to is not None:
        sql.append(" AND a.date_published <= ?")
        params.append(date_to)

    full_sql = "".join(sql)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(full_sql, params)
        return [dict(r) for r in cursor.fetchall()]
