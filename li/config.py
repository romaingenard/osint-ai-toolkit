"""li/config.py — paramètres, constantes méthodologiques, prompts LLM.

Refonte : 24 avril 2026.
Projet : "Narratifs anti-français au Sahel 2025-2026 : cartographie comparée
de l'écosystème informationnel pro-AES au Mali, Burkina Faso et Niger."

Cadrage méthodologique complet dans le doc 05 du projet. Les décisions A/B/C/D
sont tracées dans les constantes et prompts ci-dessous.

Ne contient PAS :
- la matrice DISARM (externalisée dans li/disarm_matrix.md, chargée via
  load_disarm_matrix()) ;
- les entités du corpus (externalisées dans data/entities.csv, chargées via
  load_entities()).
"""

import csv
import functools
from pathlib import Path


# === MÉTADONNÉES DU PROJET ================================================

PROJECT_NAME = "Narratifs anti-français au Sahel 2025-2026"

# Période d'observation par défaut. À figer définitivement en semaine 5 du
# planning du rapport. Modifiable ici sans toucher au reste du code :
# detect.py lit OBSERVATION_PERIOD comme default de son CLI.
OBSERVATION_PERIOD = {
    "start": "2026-02-01",
    "end": "2026-03-31",
}


# === CONSTANTES MÉTHODOLOGIQUES ===========================================
# Valeurs autorisées pour les champs catégoriels du schéma. Documentées dans
# le doc 05 (sections 1.1, 1.5, 1.7). Utilisées pour validation côté Python
# en complément des CHECK constraints SQLite.

PRODUCER_CATEGORIES = {"A", "B", "C", "D"}
# A : producteurs russes (African Initiative et dérivés, MOI AI-Freak, GPCI)
# B : relais institutionnels AES (médias d'État Mali/Burkina/Niger)
# C : amplificateurs cooptés (Kemi Seba, Nathalie Yamb, etc.)
# D : producteurs locaux à autonomie variable

COUNTRIES = {"MLI", "BFA", "NER", "SUPRA"}
# SUPRA : acteurs supra-nationaux (African Initiative, galaxie Prigojine,
# amplificateurs panafricains non rattachés à un pays AES spécifique).

INFLUENCE_INGERENCE_STATUS = {
    "influence_legitime",
    "ingerence_caracterisee",
    "zone_grise",
}

SALIENCE_SCALE = {0, 1, 2}
# 0 absent, 1 marginal, 2 central.

CLASSIFICATION_SOURCES = {"manual", "llm"}
# "both" n'existe pas comme valeur stockable. La méthode Centaure produit
# deux lignes distinctes (classified_by='manual' puis 'llm') qu'on couple
# en lecture via store_li.get_centaure_paired_classifications().

PLATFORMS = {"web", "telegram", "facebook", "tiktok", "x", "youtube"}

COLLECTORS = {
    "wordpress_api",
    "html_generic",
    "telegram_channel",
    "manual_event",
}

ENTITY_STATUSES = {"active", "inactive", "paywall", "geoblocked"}

ROLES = {"primary", "d3lta_validation"}
# primary : entité du corpus principal d'analyse.
# d3lta_validation : doublon multilingue servant uniquement à valider la
# reformulation côté D3lta (flag is_duplicate_for_d3lta=1 dans articles).


# === MOTS-CLÉS LEXICAUX POUR PRÉ-FILTRAGE ================================
# Objectif : décider de l'inclusion d'un contenu dans le corpus avant
# d'engager un appel LLM (coûteux). La classification fine reste à la charge
# des prompts saillances + DISARM + influence/ingérence.
#
# Recherche insensible à la casse, frontières de mots non strictes (les
# expressions contiennent déjà leurs séparateurs). Les listes sont
# volontairement incomplètes : elles seront enrichies par Romain au fil des
# lectures.

# Éléments de langage russes (Audinet, IRSEM n°119, octobre 2024).
AUDINET_LANGUAGE_MARKERS = [
    "majorité mondiale",
    "multipolarité",
    "multipolaire",
    "occident collectif",
    "néocolonialisme monétaire",
    "pays vampire",
]

# Figures et concepts panafricanistes pré-2020.
PANAFRICAN_MARKERS = [
    "sankara",
    "nkrumah",
    "lumumba",
    "césaire",
    "mbembe",
    "diop",
    "décolonialité",
    "négritude",
    "panafricanisme",
]

# Critique souverainiste contemporaine sans référence russe.
# "néocolonialisme" est volontairement présent ici ET dans AUDINET (via
# "néocolonialisme monétaire") : l'overlap est résolu par la détection LLM
# au moment de la classification, pas dans le pré-filtre.
SOVEREIGNIST_MARKERS = [
    "françafrique",
    "fcfa",
    "franc cfa",
    "bases militaires",
    "néocolonialisme",
    "survie",
]

# Marqueurs nationaux AES par pays. Dictionnaire indexé par code ISO.
NATIONAL_AES_MARKERS = {
    "MLI": ["goïta", "assimi goïta", "mali kura", "ortm", "l'essor"],
    "BFA": ["traoré", "ibrahim traoré", "rtb", "sidwaya", "faso mêbo"],
    "NER": ["tiani", "abdourahamane tiani", "cnsp", "ortn"],
}

# Règle anti-superposition (doc 05 §1.4) : un contenu traitant
# substantiellement de la réponse informationnelle française est exclu.
EXCLUSION_MARKERS_FRENCH_RESPONSE = [
    "viginum",
    "sgdsn",
    "french response",
    "contre-discours français",
    "meae",
    "cfi",
]


def passes_inclusion_filter(
    text: str,
    country: str | None = None,
) -> tuple[bool, str]:
    """Pré-filtre lexical : décide si un contenu mérite une classification LLM.

    Critères d'inclusion (doc 05 §1.7 décision D) — au moins un thème parmi :
    - dénigrement de la France / valorisation juntes AES / partenariat
      Russie-Afrique / matrice panafricaniste ou souverainiste anti-française.

    Exclusion stricte : contenu traitant la réponse informationnelle
    française (règle anti-superposition Henry, doc 05 §1.4). L'exclusion
    prime sur l'inclusion : si un marqueur d'exclusion est présent, le
    contenu est rejeté même s'il contient par ailleurs des marqueurs
    d'inclusion.

    Logique par axe :
    - russe : AUDINET_LANGUAGE_MARKERS
    - panafricaniste : PANAFRICAN_MARKERS
    - souverainiste : SOVEREIGNIST_MARKERS
    - national AES : NATIONAL_AES_MARKERS[country] si country ∈
      {MLI, BFA, NER}, union des 3 pays si country=None. Pour country=
      'SUPRA', l'axe national est ignoré (une entité supra-nationale comme
      African Initiative peut parfaitement entrer dans le corpus via les
      trois autres axes sans marqueur AES local).

    Cette logique vaut pour l'INCLUSION uniquement. Au moment de la
    classification par le prompt saillances, l'axe national AES reste
    scoré 0/1/2 pour tous les contenus, SUPRA compris.

    Retour : (True, "matched: <type>") si inclus, (False, "reason") sinon.
    Le premier marqueur trouvé détermine le type retourné (ordre : exclusion
    d'abord, puis russe, panafrican, sovereignist, national).
    """
    text_lower = text.lower()

    for marker in EXCLUSION_MARKERS_FRENCH_RESPONSE:
        if marker.lower() in text_lower:
            return (False, f"excluded: french response marker '{marker}'")

    for marker in AUDINET_LANGUAGE_MARKERS:
        if marker.lower() in text_lower:
            return (True, f"matched: audinet '{marker}'")

    for marker in PANAFRICAN_MARKERS:
        if marker.lower() in text_lower:
            return (True, f"matched: panafrican '{marker}'")

    for marker in SOVEREIGNIST_MARKERS:
        if marker.lower() in text_lower:
            return (True, f"matched: sovereignist '{marker}'")

    if country == "SUPRA":
        # Axe national volontairement ignoré pour l'inclusion des entités
        # supra-nationales. Si aucun des 3 axes précédents n'a matché,
        # le contenu est rejeté.
        return (False, "no inclusion marker (SUPRA, national axis skipped)")

    if country in ("MLI", "BFA", "NER"):
        for marker in NATIONAL_AES_MARKERS[country]:
            if marker.lower() in text_lower:
                return (True, f"matched: national_aes_{country} '{marker}'")
        return (False, f"no inclusion marker (tested national={country})")

    # country is None : tester l'union des marqueurs nationaux des 3 pays.
    for code, markers in NATIONAL_AES_MARKERS.items():
        for marker in markers:
            if marker.lower() in text_lower:
                return (True, f"matched: national_aes_{code} '{marker}'")

    return (False, "no inclusion marker found")


# === PARAMÈTRES DE DÉTECTION DE COORDINATION ==============================
# Valeurs prêtes pour l'algorithme de détection (brief 2). Non utilisées
# dans ce brief — le schéma coordination_events existe mais aucune fonction
# de détection ne tourne encore.

COORDINATION_PARAMS = {
    # Coordination stricte entre canaux AI officiels (afrinz.ru + Telegram AI).
    # Fenêtre serrée car on attend un quasi-sync éditorial.
    "ai_strict": {
        "time_window_hours": 2,
        "similarity_threshold": 0.85,
        "min_channels": 2,
    },
    # Coordination AI → relais locaux avec reformulation tolérée.
    # Fenêtre large : la reformulation et la traduction prennent du temps.
    # Seuil bas : l'adaptation dégrade la similarité brute.
    "ai_to_local_relay": {
        "time_window_hours": 72,
        "similarity_threshold": 0.65,
        "min_channels": 2,
    },
    # Coordination inter-pays (même narratif dans MLI + BFA + NER).
    # Spécificité du sujet Sahel, absente du sujet CopyCop.
    "cross_country": {
        "time_window_hours": 48,
        "similarity_threshold": 0.70,
        "min_countries": 2,
    },
}

# Seuil en dessous duquel une entité est ignorée pour l'analyse de
# coordination (trop peu d'articles pour que le signal soit fiable).
COORDINATION_MIN_ARTICLES_PER_ENTITY = 5


# === CHARGEMENT DE LA MATRICE DISARM =====================================

# Chemin par défaut de la matrice : sibling de ce fichier.
_DISARM_MATRIX_PATH = Path(__file__).parent / "disarm_matrix.md"


@functools.lru_cache(maxsize=1)
def load_disarm_matrix(path: str | None = None) -> str:
    """Lit la matrice DISARM depuis li/disarm_matrix.md.

    Résultat caché (lru_cache) : le fichier est lu une seule fois par
    processus Python, évite les IO répétées quand build_disarm_prompt()
    est appelée pour chaque classification du corpus.

    Si Romain modifie le fichier pendant une session interactive, il doit
    appeler load_disarm_matrix.cache_clear() pour forcer un rechargement.
    """
    p = Path(path) if path else _DISARM_MATRIX_PATH
    return p.read_text(encoding="utf-8")


# === CHARGEMENT DES ENTITÉS DU CORPUS ====================================

# Colonnes obligatoires de data/entities.csv. Validation stricte : toute
# absence lève une exception explicite.
ENTITY_REQUIRED_COLUMNS = [
    "entity_id",
    "name",
    "url",
    "platform",
    "producer_category",
    "country",
    "collector",
    "html_title_selector",
    "html_date_selector",
    "html_content_selector",
    "rate_limit_seconds",
    "status",
    "default_language",
    "role",
    "notes",
]


def load_entities(path: str = "data/entities.csv") -> list[dict]:
    """Lit data/entities.csv et retourne la liste des entités actives.

    Convention de lecture :
    - Le fichier peut commencer par un bloc de commentaires '#' décrivant
      la convention (ex. définition des colonnes). Ce bloc est skippé
      silencieusement jusqu'à la première ligne non-vide et non-# qui
      sert de header CSV.
    - Après le header, toute ligne dont la première cellule commence par
      '#' est traitée comme exemple commenté, non parsé. Chaque skip est
      loggué sur stdout : 'skipping commented example row: <slug>'.
    - Les colonnes de ENTITY_REQUIRED_COLUMNS doivent toutes être
      présentes. Toute colonne manquante lève ValueError.
    - Les valeurs producer_category / country / platform / collector /
      status / role sont validées contre leurs sets respectifs.
    - rate_limit_seconds est converti en float, défaut 2.0 si vide.
    """
    entities: list[dict] = []

    # Le bloc de documentation en tête (#...) doit être filtré avant que
    # csv.DictReader ne parse le header, sinon la 1ʳᵉ ligne # est prise
    # pour fieldnames.
    with open(path, newline="", encoding="utf-8") as f:
        raw_lines = f.readlines()

    csv_lines: list[str] = []
    header_found = False
    for line in raw_lines:
        stripped = line.lstrip()
        if not header_found:
            if stripped == "" or stripped.startswith("#"):
                continue
            header_found = True
            csv_lines.append(line)
        else:
            csv_lines.append(line)

    if not header_found:
        raise ValueError(f"entities.csv ({path}) : aucun header CSV trouvé")

    reader = csv.DictReader(csv_lines)

    missing = [c for c in ENTITY_REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise ValueError(
            f"entities.csv manque les colonnes : {missing}. "
            f"Colonnes attendues : {ENTITY_REQUIRED_COLUMNS}"
        )

    for row_idx, row in enumerate(reader, start=2):
        first_cell = (row.get("entity_id") or "").strip()
        if first_cell.startswith("#"):
            # Slug réel sans le '#' de tête pour un log lisible.
            slug = first_cell.lstrip("#").strip() or "(anonyme)"
            print(f"skipping commented example row: {slug}")
            continue

        if not first_cell:
            # Ligne vide (sans # mais sans entity_id) — ignorer
            # silencieusement, c'est probablement une ligne blanche
            # de mise en forme.
            continue

        if row["producer_category"] not in PRODUCER_CATEGORIES:
            raise ValueError(
                f"entities.csv ligne {row_idx} ({first_cell}) : "
                f"producer_category='{row['producer_category']}' invalide, "
                f"attendu dans {sorted(PRODUCER_CATEGORIES)}"
            )
        if row["country"] not in COUNTRIES:
            raise ValueError(
                f"entities.csv ligne {row_idx} ({first_cell}) : "
                f"country='{row['country']}' invalide, "
                f"attendu dans {sorted(COUNTRIES)}"
            )
        if row["platform"] not in PLATFORMS:
            raise ValueError(
                f"entities.csv ligne {row_idx} ({first_cell}) : "
                f"platform='{row['platform']}' invalide, "
                f"attendu dans {sorted(PLATFORMS)}"
            )
        if row["collector"] not in COLLECTORS:
            raise ValueError(
                f"entities.csv ligne {row_idx} ({first_cell}) : "
                f"collector='{row['collector']}' invalide, "
                f"attendu dans {sorted(COLLECTORS)}"
            )
        if row["status"] not in ENTITY_STATUSES:
            raise ValueError(
                f"entities.csv ligne {row_idx} ({first_cell}) : "
                f"status='{row['status']}' invalide, "
                f"attendu dans {sorted(ENTITY_STATUSES)}"
            )
        if row["role"] not in ROLES:
            raise ValueError(
                f"entities.csv ligne {row_idx} ({first_cell}) : "
                f"role='{row['role']}' invalide, "
                f"attendu dans {sorted(ROLES)}"
            )

        rls_raw = (row.get("rate_limit_seconds") or "").strip()
        row["rate_limit_seconds"] = float(rls_raw) if rls_raw else 2.0

        entities.append(row)

    return entities


# === PROMPTS LLM ==========================================================
# Trois prompts distincts, appelés séparément pour chaque article.
# Justification (méthodologique) : découper les tâches cognitives réduit la
# dérive du modèle et améliore la parsabilité de la sortie.
# Justification (coût) : chaque prompt est long ; le prompt caching
# Anthropic (cache_control: ephemeral) rend la répétition négligeable —
# voir core/analyze.py::call_claude(cache_system=True).

CONTEXT_PROMPT = """Tu es un analyste spécialisé en lutte informationnelle.

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
"""


DISARM_INSTRUCTIONS = """MATRICE DISARM (référence complète ci-dessus). Utilise EXCLUSIVEMENT les codes et noms de cette référence. Ne te fie pas à ta mémoire du framework.

TÂCHE :
Pour chaque contenu soumis, tu dois :
1. Vérifier l'éligibilité : si le contenu traite substantiellement de la réponse française, répondre uniquement "HORS_SCOPE: raison en une phrase" et t'arrêter.
2. Identifier la tactique DISARM la plus pertinente (code TAxx + nom).
3. Identifier la ou les techniques DISARM les plus pertinentes (code Txxxx + nom).
4. Fournir une justification en une phrase.
5. Indiquer un niveau de confiance : HIGH, MEDIUM ou LOW.

Si le contenu décrit un marqueur technique involontaire (erreur d'OPSEC, artefact technique) plutôt qu'une technique d'influence, réponds "PAS UNE TECHNIQUE DISARM" avec une phrase d'explication.

FORMAT DE RÉPONSE STRICT :
TACTIQUE: TAxx - Nom
TECHNIQUE(S): Txxxx - Nom / Txxxx.xxx - Nom
JUSTIFICATION: [une phrase]
CONFIANCE: HIGH/MEDIUM/LOW
"""


def build_disarm_prompt() -> str:
    """Construit le prompt DISARM : contexte + matrice + consignes.

    Concaténation dynamique pour bénéficier du prompt caching Anthropic :
    le bloc (CONTEXT_PROMPT + matrice) est stable entre tous les appels
    DISARM et sera marqué cache_control=ephemeral côté core/analyze.py.
    """
    return CONTEXT_PROMPT + "\n\n" + load_disarm_matrix() + "\n\n" + DISARM_INSTRUCTIONS


SALIENCE_PROMPT = CONTEXT_PROMPT + """

TÂCHE : scorer le contenu soumis sur quatre indicateurs de saillance, chacun sur une échelle 0/1/2.

ÉCHELLE :
- 0 : absent
- 1 : présent mais marginal ou accessoire
- 2 : présent et central dans le contenu

INDICATEURS :

1. SAILLANCE RUSSE : présence d'éléments de langage Audinet ("majorité mondiale", "multipolarité", "Occident collectif", "néocolonialisme monétaire", "pays vampire") et des sous-récits russes (partenariat Russie-Afrique présenté comme modèle, condamnation de l'Occident, multipolarité anti-occidentale).

2. SAILLANCE PANAFRICANISTE INTELLECTUELLE : mobilisation de figures ou concepts pré-2020 (Diop, Nkrumah, Sankara, Césaire, Lumumba, Mbembe ; décolonialité, négritude, panafricanisme historique).

3. SAILLANCE SOUVERAINISTE AFRICAINE CONTEMPORAINE : critique FCFA, bases militaires, Françafrique SANS référence russe. Références à Survie, Felwine Sarr, ONG africaines.

4. SAILLANCE NATIONALE AES : références spécifiques au pays (figures Traoré/Goïta/Tiani, symboles locaux, formulations officielles du pouvoir en place).

PRINCIPE : un contenu qui mobilise uniquement la matrice panafricaniste (saillance 2-0-0-0 sur l'axe panafricain) ou souverainiste (saillance 0-0-2-0) est un résultat analytiquement valide, pas une erreur.

NE PAS tenter de documenter la signature symbolique (drapeaux, cérémonies, images rituelles). Elle est hors de ta portée (tu ne vois pas les images) et sera documentée manuellement.

FORMAT DE RÉPONSE STRICT :
SAILLANCE_RUSSE: 0|1|2
SAILLANCE_PANAFRICANISTE: 0|1|2
SAILLANCE_SOUVERAINISTE: 0|1|2
SAILLANCE_NATIONALE_AES: 0|1|2
JUSTIFICATION: [deux phrases maximum]
"""


INFLUENCE_INGERENCE_PROMPT = CONTEXT_PROMPT + """

TÂCHE : qualifier le contenu au regard de la distinction doctrinale influence légitime / ingérence caractérisée / zone grise (rapport CAPS-IRSEM 2018, Les manipulations de l'information).

DÉFINITIONS :
- INFLUENCE_LEGITIME : action informationnelle revendiquée d'un acteur dans l'espace public. Exemple : un média d'État AES qui porte ouvertement la position de la junte.
- INGERENCE_CARACTERISEE : au moins un des quatre critères Viginum est rempli : contenu trompeur, diffusion artificielle, caractère étranger dissimulé, atteinte aux intérêts fondamentaux.
- ZONE_GRISE : contenu dont le statut est ambigu (ex. contenu souverainiste local possiblement amplifié par une opération russe sans que l'amplification soit établie de façon décisive).

FORMAT DE RÉPONSE STRICT :
STATUT: influence_legitime | ingerence_caracterisee | zone_grise
JUSTIFICATION: [deux phrases maximum]
CONFIANCE: HIGH | MEDIUM | LOW
"""
