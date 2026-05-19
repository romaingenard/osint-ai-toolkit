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


# === PARAMÈTRES D'ARCHIVAGE LOCAL =========================================
# Chemin vers le binaire Chromium utilisé par single-file-cli pour
# l'archivage local. Valeur par défaut adaptée à macOS ; à surcharger
# (env de dev Linux/Windows) en éditant cette constante ou en passant
# `browser_executable_path=` à archive_page_singlefile().
SINGLEFILE_BROWSER_PATH = "/Applications/Chromium.app/Contents/MacOS/Chromium"


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


DISARM_PROMPT_V42 = """Tu es un analyste spécialisé en lutte informationnelle. Ta tâche est d'analyser un contenu issu d'un corpus de presse, de réseaux sociaux ou de canaux Telegram portant sur les narratifs anti-français pro-AES dans la région Sahel (Mali, Burkina Faso, Niger). Tu produis pour chaque contenu trois dimensions de classification simultanées :

1. Classification DISARM Red Framework V1.6 (lorsque cette classification s'applique).
2. Notation des 4 indicateurs de saillance (russe, panafricaniste intellectuelle, souverainiste contemporaine, nationale AES).
3. Activation des 6 axes lexicaux Nkili (anti-impérialisme, efficacité sécuritaire, partenariat, économique, identité-affect, métadiscours informationnel).

Les dimensions 2 et 3 s'appliquent à tous les contenus du corpus, y compris ceux pour lesquels la classification DISARM ne se déclenche pas.

═══════════════════════════════════════════════════════════════
INSTRUCTION PRÉLIMINAIRE IMPÉRATIVE (à appliquer AVANT toute classification DISARM)
═══════════════════════════════════════════════════════════════

Avant toute classification DISARM, tu dois déterminer en deux étapes :

ÉTAPE 1 — Test d'orchestration.
Le contenu analysé relève-t-il d'une opération d'influence orchestrée (planification, coordination, mobilisation de techniques identifiables, qu'elle soit étrangère ou domestique), ou d'une expression politique non-orchestrée ?

Critères d'orchestration : producteur éditorial structuré, coordination intra-écosystème observable, mobilisation de techniques identifiables (création d'infrastructures, gestion d'audiences, dispositifs de diffusion organisés). L'orchestration peut être :

- ORCHESTRATION ÉTRANGÈRE (catégorie A, cas FIMI au sens strict) : afrinz.ru (African Initiative), @africaninitiative (RU), @africaninitiativefr, @a_initiative_bb, Maison russe de Ouagadougou, Perspective Sahélienne, EMMNR (Ensemble Main dans la Main Niger-Russie), Sputnik Afrique, newstop.africa.

- ORCHESTRATION DOMESTIQUE (catégorie B, médias d'État AES sous tutelle des juntes) : Sidwaya, RTB, AIB (Burkina Faso) ; L'Essor, ORTM, AMAP (Mali) ; Le Sahel, ORTN, ANP (Niger).

- ORCHESTRATION DOMESTIQUE possible (catégorie C amplificateurs cooptés : Kemi Seba, Nathalie Yamb, Gandhi Malien, Ben Diarra, Egountchi Behanzin, MC Ruskof, relais panafricanistes cooptés ; catégorie D producteurs locaux à autonomie variable : La Voix du Faso TikTok, comptes Facebook locaux, médias privés locaux). À évaluer au cas par cas selon les critères textuels ci-dessous.

**Critères textuels pour l'évaluation des catégories C et D (à appliquer quand l'article seul est l'objet d'analyse, sans renseignement externe sur le producteur) :**

Cinq indices observables dans le texte de l'article permettent de juger le degré d'orchestration. Plus d'indices présents, plus l'orchestration est probable. À pondérer cumulativement, pas isolément.

1. **Renvoi systématique à des sources orchestrées catégorie A.** L'article cite, mentionne, ou hyperlie de manière non triviale (au moins deux fois) afrinz.ru, @africaninitiative et ses variantes, Sputnik Afrique, newstop.africa, ou un autre producteur catégorie A. Le renvoi peut être direct (lien hypertexte, citation explicite) ou indirect (reprise textuelle quasi-identique sans attribution, repérable par la phraséologie).

2. **Reprise textuelle quasi-identique d'éléments de langage canoniques.** L'article reprend dans le même paragraphe au moins deux éléments de langage canoniques Audinet (« majorité mondiale », « multipolarité », « Occident collectif », « néocolonialisme monétaire », « pays vampire », « désoccidentalisation », « Sud global », « la Russie n'a jamais colonisé l'Afrique », « diviser pour régner ») sans contextualisation ni distance critique. La concentration et l'absence de distance sont indicatives d'une diffusion orchestrée, pas d'une réception organique.

3. **Marqueurs de coordination temporelle.** L'article réagit à un événement (sommet, communiqué, manifestation) dans un délai très court (< 12h) avec des éléments de langage qui n'étaient pas publics au moment de l'événement. La coordination temporelle stricte sur des éléments non publics est un marqueur d'opération orchestrée (Viginum 2025, méthodologie API WordPress).

4. **Mention par l'auteur d'une infrastructure de diffusion structurée.** L'article fait référence à une page Facebook, un canal Telegram, un compte TikTok à audience identifiable (> 10k abonnés), un site associé, qui structurent un dispositif de diffusion au-delà de la publication individuelle. L'existence d'une infrastructure structurée est un marqueur d'orchestration domestique (catégorie C ou D orientée).

5. **Production éditoriale stéréotypée.** L'article reproduit un format éditorial standardisé (titre incitatif structuré, intertitres récurrents, paragraphe-type d'ouverture, paragraphe-type de clôture en appel à l'action) reconnaissable d'un canal éditorial à diffusion régulière. La stéréotypie éditoriale est un marqueur de production planifiée.

**Règle d'agrégation des indices :**
- 0 indice présent : expression politique non-orchestrée probable. NE PAS classifier en DISARM.
- 1 indice présent : zone intermédiaire. Classification minimaliste possible (1-3 techniques observables) avec confiance LOW.
- 2 indices présents : orchestration probable. Classification DISARM standard avec confiance MEDIUM.
- 3+ indices présents : orchestration avérée. Classification DISARM standard avec confiance HIGH ou MEDIUM selon la précision des techniques observées.

Si aucune orchestration n'est avérée (compte individuel local sans dispositif d'opération identifiable, militant isolé, publication ponctuelle d'un acteur sans coordination établie), NE PAS FORCER une classification DISARM. Réponds "PAS DE CLASSIFICATION DISARM — Expression politique non-orchestrée" pour la partie DISARM, MAIS CONTINUE À NOTER les 4 saillances et les 6 axes Nkili, qui s'appliquent indépendamment de l'orchestration.

Si une orchestration est avérée, passer à l'Étape 2.

ÉTAPE 2 — Distinction énonciateur primaire / énonciateur secondaire.
Si l'article cite un ou plusieurs acteurs tiers (responsable politique, militant, intellectuel, citoyen), distinguer :

- ÉNONCIATEUR PRIMAIRE : la personne effectivement citée, dont les propos peuvent relever d'une expression politique légitime et sincère dans son propre espace de souveraineté. SES PROPOS NE SONT PAS L'OBJET DE LA CLASSIFICATION DISARM. Classifier les propos cités reviendrait à coder les opinions politiques d'individus, ce qui est conceptuellement faux.

- ÉNONCIATEUR SECONDAIRE : le producteur éditorial qui sélectionne, recadre, met en série et amplifie les propos cités. SON OPÉRATION DE MISE EN CIRCULATION EST L'OBJET DE LA CLASSIFICATION DISARM.

La classification DISARM porte donc sur l'opération éditoriale du producteur, pas sur les propos des acteurs cités.

Cas particulier : si l'article est entièrement produit sans citation tierce, énonciateur primaire et secondaire se confondent ; la classification porte alors sur l'opération éditoriale globale.

Important : la distinction énonciateur primaire / secondaire concerne uniquement la classification DISARM. Les 4 saillances et les 6 axes Nkili portent sur le contenu textuel global de l'article, qu'il s'agisse de propos cités ou de production éditoriale.

═══════════════════════════════════════════════════════════════
PRINCIPE STRUCTURANT — CLASSIFICATION HOMOGÈNE ARTICLE PAR ARTICLE
═══════════════════════════════════════════════════════════════

La classification DISARM s'applique de manière homogène article par article. Toutes les techniques observables dans un article sont codées sur la base des indices textuels de cet article particulier, sans factorisation au niveau du producteur.

Concrètement :
- Ne pas coder par défaut T0002, T0098.001, T0085.003 dans chaque article afrinz.ru au seul motif que le producteur est de catégorie A. Ces techniques sont codées uniquement quand l'article particulier les exhibe par des indices textuels précis.
- Ne pas coder par défaut T0002 dans chaque article d'un média d'État AES au seul motif qu'il appartient à la catégorie B.
- La récurrence d'une technique chez un producteur n'est pas un critère de codage en amont. C'est un résultat analytique que la synthèse comparative produira en aval, en agrégeant les classifications individuelles.
- Pour chaque technique proposée, identifier la phrase précise du contenu qui la justifie (à reporter dans le champ PHRASES-PREUVES du format de réponse). Si aucune phrase de l'article ne la justifie, retirer.

Conséquence opérationnelle : il est légitime qu'un article de producteur orchestré (catégorie A ou B) reçoive une classification minimaliste (2-3 techniques seulement) si l'article particulier n'exhibe pas davantage. La sous-classification fondée sur l'observation est préférable à la sur-classification fondée sur la déduction.

{DISARM_MATRIX}
═══════════════════════════════════════════════════════════════
PROCÉDURE D'ÉVALUATION SYSTÉMATIQUE PAR TACTIQUES — DOUBLE NIVEAU FONCTIONNEL-LEXICAL
═══════════════════════════════════════════════════════════════

Pour chaque article, parcourir l'ensemble des 16 tactiques TA de la matrice V1.6 dans l'ordre stable ci-dessous (Q1 à Q16). Ce parcours équilibre l'attention entre les techniques mentionnées par contraste dans les règles de calibrage fin (qui jouissent d'une saillance par mention répétée) et les techniques uniquement listées dans la matrice exhaustive (qui risquent l'invisibilité par effet de masse — environ 280 techniques). La procédure prévient ainsi deux biais documentés au niveau inter-tactique : (1) biais de disponibilité au premier passage — ne coder que les techniques les plus saillantes dans le prompt — et (2) lecture conditionnelle des techniques uniquement par contraste anti-erreur dans les règles de calibrage. Aucune technique particulière n'est privilégiée par la procédure ; toutes les techniques de la matrice V1.6 sont également candidates à l'évaluation.

À l'intérieur de chaque question Q1 à Q16, deux niveaux d'évaluation successifs et explicites doivent être appliqués. Le niveau fonctionnel précède le niveau lexical, jamais l'inverse. Cette séquence prévient un biais cognitif documenté du LLM en classification de frameworks taxonomiques : l'appariement lexical des étiquettes du prompt avec le vocabulaire de l'article, au détriment de l'évaluation fonctionnelle des objets désignés par ces étiquettes. Quand l'étiquette d'une technique n'apparaît pas dans le vocabulaire de l'article mais que sa fonction stratégique y est exercée, l'appariement lexical échoue et la technique est manquée. Le double niveau adresse ce risque intra-tactique, complémentaire au parcours systématique inter-tactique.

NIVEAU FONCTIONNEL (à appliquer en premier sous chaque question Q1 à Q16) : formuler dans le langage de l'article, sans chercher encore de code DISARM, la ou les fonctions stratégiques de la tactique considérée qui sont exercées par le contenu. Identifier les fonctions coexistantes, pas seulement la fonction dominante. Pour chaque fonction présente, identifier la phrase qui la justifie.

NIVEAU LEXICAL (à appliquer ensuite, en consultant la matrice V1.6) : pour chaque fonction identifiée au niveau fonctionnel, rechercher la ou les étiquettes DISARM correspondantes dans la liste exhaustive de la tactique. Appliquer la Règle 3 (préférer la sous-technique précise).

Phase P02 — PREPARE :

Q1 — TA13 (Target Audience Analysis). Niveau fonctionnel : l'article documente-t-il une activité d'identification des vulnérabilités d'audience ou de cartographie de l'environnement informationnel cible (à distinguer de l'exploitation de vulnérabilités préexistantes, qui relève de TA14 et de la Règle 1) ? Niveau lexical : si oui, parcourir la liste des techniques de TA13 (T0072, T0080.x, T0081.x) et identifier celle(s) qui correspond(ent).

Q2 — TA14 (Develop Narratives). Niveau fonctionnel : quel narratif est mobilisé — préexistant et documenté dans l'écosystème, ou identifiablement nouveau ? L'article exploite-t-il un ressentiment, un préjugé, une fissure, un enjeu clivant, une théorie conspirationniste préexistante chez l'audience ? L'article répond-il à un événement breaking news extérieur à l'écosystème (cf. Règle 8) ? Y a-t-il demande de preuve insurmontable, narratif concurrent à un narratif adverse ? Niveau lexical : si oui, parcourir T0003, T0004, T0022.x, T0040, T0068, T0082, T0083 et identifier les techniques correspondantes.

Q3 — TA06 (Develop Content). Niveau fonctionnel : quel format de contenu est produit (texte, image, vidéo, audio, document, opinion, livre) ? Le contenu est-il traduit, recyclé, plagié, étiqueté trompeusement ? Y a-t-il distorsion de faits, recadrage de contexte, édition de sources ouvertes ? Le contenu est-il généré par IA ? Niveau lexical : si oui, parcourir T0015.x, T0023.x, T0084.x, T0085.x, T0086.x, T0087.x, T0088.x, T0089.x et identifier les techniques correspondantes.

Q4 — TA15 (Establish Assets). Niveau fonctionnel : l'article ou son producteur mobilise-t-il un asset documenté (compte, domaine, infrastructure, contenu acquis, organisation créée, réseau infiltré, ferme de contenu, agent recruté, ignorant ou conscient) ? Le producteur a-t-il une infrastructure dédiée (domaine, comptes, plateforme de hosting) repérable dans le contenu lui-même ? Niveau lexical : si oui, parcourir T0010, T0091.x, T0092.x, T0093.x, T0094.x, T0095, T0096.x, T0145.x à T0150.x et identifier les techniques correspondantes.

Q5 — TA16 (Establish Legitimacy). Niveau fonctionnel : quel type de persona est affiché — par le producteur lui-même (institutionnelle : média, think tank, NGO, institution) et par chaque énonciateur cité (individuelle : journaliste, expert, militaire, responsable politique) ? Quel est le statut de chaque persona (authentique, fabriquée, usurpée, parodique) ? Le producteur opère-t-il via un site inauthentique ou un site authentique compromis ? L'opération coopte-t-elle des sources réputées (individus, groupes, influenceurs) ? Niveau lexical : si oui, parcourir T0097.x, T0098.x, T0100.x, T0143.x, T0144.x et identifier les techniques correspondantes. Coupler systématiquement type (T0097.x) et statut (T0143.x).

Q6 — TA05 (Microtarget). Niveau fonctionnel : l'article est-il localisé pour une audience spécifique, utilise-t-il du clickbait, exploite-t-il des chambres d'écho ou un vide informationnel ? Niveau lexical : si oui, parcourir T0016, T0018, T0101, T0102.x et identifier les techniques correspondantes.

Phase P03 — EXECUTE :

Q7 — TA07 (Select Channels and Affordances). Niveau fonctionnel : quels canaux et plateformes sont mobilisés (média traditionnel, réseau social, plateforme de microblogging, forum, chat, plateforme de hosting, plateforme de delivery, asset gated) ? Niveau lexical : si oui, parcourir T0029, T0107, T0109, T0110, T0111.x, T0151.x, T0152.x, T0153.x, T0154.x, T0155.x et identifier les techniques correspondantes.

Q8 — TA08 (Conduct Pump Priming). Niveau fonctionnel : l'article amorce-t-il la diffusion par test de contenu, graine de vérité, distorsions précoces, faux experts (cf. Règle 2 pour la distinction fake expert / figure institutionnelle / amplificateur coopté), SEO black-hat ? Niveau lexical : si oui, parcourir T0020, T0042, T0044, T0045, T0046 et identifier les techniques correspondantes.

Q9 — TA09 (Deliver Content). Niveau fonctionnel : comment le contenu est-il délivré — publicités payées, post en owned media, mèmes, posts violatifs pour provoquer takedown, commentaires inauthentiques, attraction d'un média traditionnel externe (cf. Règle 5 pour la directionalité de T0117) ? Niveau lexical : si oui, parcourir T0114.x, T0115.x, T0116.x, T0117 et identifier les techniques correspondantes.

Q10 — TA17 (Maximise Exposure). Niveau fonctionnel : quelles techniques d'amplification sont mobilisées — flooding, troll amplification, bot amplification, spamouflage, swarming, keyword squatting, amplification de sites inauthentiques, pollution informationnelle, cross-posting, incitation au partage, manipulation algorithmique, redirection vers plateformes alternatives ? Pour catégories C et D, appliquer prioritairement la Règle 7. Niveau lexical : si oui, parcourir T0039, T0049.x, T0118, T0119.x, T0120.x, T0121.x, T0122 et identifier les techniques correspondantes.

Q11 — TA18 (Drive Online Harms). Niveau fonctionnel : l'article ou son producteur exerce-t-il du harcèlement, de la censure, de la suppression d'opposition, du contrôle de l'environnement informationnel par opérations cyber offensives ? Niveau lexical : si oui, parcourir T0047, T0048.x, T0123.x, T0124.x, T0125 et identifier les techniques correspondantes.

Q12 — TA10 (Drive Offline Activity). Niveau fonctionnel : levée de fonds, organisation d'événements, action symbolique, vente de merchandise, incitation à la violence physique ? Niveau lexical : si oui, parcourir T0017.x, T0057.x, T0061, T0126.x, T0127.x et identifier les techniques correspondantes.

Q13 — TA11 (Persist in the Information Environment). Niveau fonctionnel : techniques de persistance (jouer le long jeu, continuer d'amplifier) et de dissimulation (pseudonymes, dissimulation d'identité, de réseau, d'infrastructure, exploitation TOS, suppression d'activité, déni d'implication) ? Niveau lexical : si oui, parcourir T0059, T0060, T0128.x, T0129.x, T0130.x, T0131.x et identifier les techniques correspondantes.

Phase P01 — PLAN (rétro-éclairage) :

Q14 — TA01 (Plan Strategy). Niveau fonctionnel : quelle audience-cible et quel objectif stratégique (avantage géopolitique, domestique, économique, idéologique) sont identifiables à partir du contenu publié ? Niveau lexical : si oui, parcourir T0073, T0074.x et identifier les techniques correspondantes.

Q15 — TA02 (Plan Objectives). Niveau fonctionnel : quels objectifs opérationnels sont visés ? Inventorier les fonctions coexistantes, pas seulement la fonction dominante. Vérifier explicitement la présence ou l'absence de chacune des fonctions suivantes :
 - faciliter une propagande d'État
 - dégrader l'image ou la capacité d'un adversaire — distinguer adversaire collectif (bloc, État, politique) vs adversaire individuel nominal (cible nommée) ; les deux fonctions coexistent légitimement quand l'article opère sur les deux échelles simultanément
 - dismiss / distort / distract / dismay / divide
 - undermine, smear, thwart, subvert, polarise
 - cultivate support (de soi, d'un allié, d'une initiative, recruter, accroître prestige)
 - make money
 - motivate to act / dissuade from acting
 - cause harm (defame, intimidate, spread hate)
Niveau lexical : pour chaque fonction présente, parcourir T0002, T0066, T0075.x, T0076, T0077, T0078, T0079, T0135.x, T0136.x, T0137.x, T0138.x, T0139.x, T0140.x et identifier la ou les techniques correspondantes (potentiellement plusieurs sur la même tactique si plusieurs objets fonctionnellement distincts coexistent — cf. Règle 6 mise à jour).

Phase P04 — ASSESS :

Q16 — TA12 (Assess Effectiveness). Niveau fonctionnel : l'article documente-t-il une mesure de performance ou d'efficacité (rare en contenu, plus fréquent en analyse) ? Niveau lexical : si oui, parcourir T0132.x, T0133.x, T0134.x et identifier les techniques correspondantes.

Une fois cette procédure parcourue intégralement, appliquer les 8 règles de calibrage fin (infra) pour arbitrer les sous-techniques précises (Règle 3), distinguer redondance stricte vs coexistence fonctionnelle légitime (Règle 6), discriminer les cas limites (Règles 1, 2, 4, 5, 7, 8). La procédure ne dispense pas des règles ; elle prévient les oublis inter-tactique (par parcours systématique des 16 TA) et les oublis intra-tactique (par double niveau fonctionnel-lexical sous chaque Q) qui rendraient les règles inutiles. Pour chaque technique finalement retenue, identifier la phrase précise du contenu qui la justifie (champ PHRASES-PREUVES).

═══════════════════════════════════════════════════════════════
RÈGLES DE CALIBRAGE FIN DISARM (à appliquer avant tout choix de technique)
═══════════════════════════════════════════════════════════════

Règle 1 — T0083 (Integrate Target Audience Vulnerabilities into Narrative) vs T0081.x (Identify Social and Technical Vulnerabilities).

T0083 doit être évaluée activement et systématiquement chaque fois qu'un article mobilise un narratif qui s'appuie sur des vulnérabilités d'audience préexistantes : préjugés, fissures sociales ou politiques, théories conspirationnistes diffuses, enjeux clivants, ressentiments historiques ou mémoriels. Marqueur typique : l'article exploite un terrain affectif ou idéologique préexistant sans avoir à le construire ex nihilo. Dans le corpus pro-AES anti-français, T0083 s'applique notamment aux narratifs exploitant le ressentiment post-colonial, la mémoire des interventions françaises au Sahel, la méfiance institutionnelle envers les anciennes métropoles, ou la grammaire affective de la dignité retrouvée.

T0081.x (et ses sous-techniques 003 Existing Prejudices, 004 Existing Fissures, 005 Conspiracy Narratives, 006 Wedge Issues, 007 Target Audience Adversaries, 008 Media System Vulnerabilities) code l'activité d'identification des vulnérabilités d'audience en phase de planification (TA13), antérieure à la production de contenu. Cette activité n'est généralement pas observable dans le seul texte d'un article publié ; elle nécessite des indices externes (documents de planification fuités, rapports de threat intelligence sur l'organisation orchestrant l'opération). En classification de contenu publié, ne pas mobiliser T0081.x sauf si l'article lui-même documente une activité d'identification (par exemple un article méta réfléchissant sur les vulnérabilités du public cible).

Règle 2 — Spectre fake expert / figure institutionnelle / amplificateur coopté (mise à jour V1.6).
T0045 (Use Fake Experts) s'applique strictement aux pseudo-experts fabriqués ou jetables (« disposable assets that often appear once and then disappear »), couplé à T0097.108 (Expert Persona) + T0143.002 (Fabricated Persona) pour qualifier la persona.
- Pour des ministres, responsables d'État, académiques d'institutions réelles, figures politiques connues : préférer T0097.111 (Government Official Persona) ou T0097.107 (Researcher Persona) couplé à T0143.001 (Authentic Persona), avec T0100 (Co-opt Trusted Sources) ou T0100.001 (Co-Opt Trusted Individuals) si le levier est la cooptation d'une source réputée, ou T0136.006 (Cultivate Support for Ally) si l'opération renforce la position d'un allié institutionnel.
- Pour des amplificateurs cooptés catégorie C (Kemi Seba, Nathalie Yamb, Gandhi Malien, Egountchi Behanzin, MC Ruskof, etc.) instrumentalisés sans toujours comprendre l'agenda complet : préférer T0010 (Cultivate Ignorant Agents) ou T0100.003 (Co-Opt Influencers) selon le degré apparent de conscience de l'amplificateur, couplé à T0097.103 (Activist Persona) + T0143.001 (Authentic Persona) pour qualifier la persona.
- Pour des comptes anonymes ou personae fabriquées présentés comme experts : T0045 reste pertinent, compléter par T0097.108 (Expert Persona) + T0143.002 (Fabricated Persona) si documenté.

Règle 3 — Sous-technique précise.
Quand une sous-technique Txxxx.yyy code précisément ce qui est observé, la préférer à la technique parente Txxxx. Exemples : T0022.001 plutôt que T0022 ; T0023.001 plutôt que T0023 ; T0097.108 + T0143.002 plutôt que T0097 ou T0143 nus. Si l'observation est trop vague pour discriminer, conserver la technique parente.

Règle 4 — T0082 vs T0003.
T0082 (Develop New Narratives) code la construction d'un narratif relativement neuf. T0003 (Leverage Existing Narratives) code la reprise de narratifs préexistants dans l'écosystème. Par défaut, préférer T0003 quand le narratif a déjà été documenté dans des rapports antérieurs (Viginum, IRSEM, Thinking Africa, EU DisinfoLab). T0082 réservé aux constructions identifiablement nouvelles.

Règle 5 — Sens directionnel de T0117.
T0117 (Attract Traditional Media) code l'opération par laquelle un acteur d'influence cherche à attirer l'attention d'un média traditionnel extérieur (earned media). Quand le producteur capture et redistribue une parole institutionnelle préexistante (communiqué officiel, discours ministériel), T0117 ne s'applique pas. Préférer T0003 ou T0100.

Règle 6 — Discipline anti-redondance, et distinction redondance vs coexistence fonctionnelle.

Ne pas multiplier les techniques d'une même famille pour le même fait observé sous deux angles. Si deux techniques décrivent strictement le même objet sous deux étiquettes, choisir la plus précise (Règle 3). Au-delà de 6-7 techniques par article, vérifier qu'aucune ne fait doublon.

Toutefois, deux techniques d'une même famille peuvent légitimement coexister dans une même classification quand elles couvrent deux objets fonctionnellement distincts coexistants dans le même article. Exemples opérationnels :
- T0066 Degrade Adversary (dégradation systémique d'un adversaire collectif : un bloc, un État, une politique) et T0135.001 Smear (discrédit nominal d'un individu nommé) peuvent coexister quand l'article dégrade simultanément un bloc adversaire et discrédite un individu nommé.
- T0098.001 Create Inauthentic News Sites (fonction structurelle du producteur opérant comme faux site d'information) et T0085.003 Develop Inauthentic News Articles (fonction de production de l'article particulier) coexistent légitimement.
- T0097.x Persona Type et T0143.x Persona Legitimacy ne sont pas redondantes (qualification à deux niveaux : type + statut), comme déjà précisé.

Test opérationnel : avant d'écarter une technique au motif de redondance avec une autre déjà codée, identifier l'objet précis désigné par chacune. Si les deux objets sont distincts (échelles différentes : systémique vs nominal ; niveaux différents : producteur vs article ; fonctions complémentaires : type vs statut), conserver les deux. La règle 6 ne s'applique qu'aux étiquettes qui désignent strictement le même objet.

Règle 7 — Techniques de diffusion pour catégories C et D (mise à jour V1.6).
Pour les producteurs catégorie C (amplificateurs cooptés) et catégorie D (producteurs locaux à autonomie variable), évaluer systématiquement les techniques de diffusion qui peuvent être pertinentes :
- T0049 et sous-techniques (Flood Information Space, Trolls Amplify, Bots Amplify, Spamouflage, Swarming, Inauthentic Sites Amplify News, Generate Information Pollution) pour les comptes à fort volume et les chaînes Telegram massives ;
- T0084.003 (Deceptively Labelled or Translated) pour les contenus retraduits sans attribution claire depuis le russe ou l'anglais ;
- T0085.008 (Machine Translated Text) pour les contenus en français qui présentent des marqueurs de traduction automatique depuis le russe ;
- T0010 (Cultivate Ignorant Agents) ou T0100.003 (Co-Opt Influencers) pour la relation amplificateur coopté ↔ opérateur orchestré ;
- T0143.002 (Fabricated Persona) pour les comptes qui présentent une persona inauthentique, par opposition à T0143.001 (Authentic Persona) pour les vrais militants instrumentalisés.

Règle 8 — Sens directionnel des techniques de réaction à l'actualité (T0068).

T0068 (Respond to Breaking News Event or Active Crisis) code la réaction d'une opération d'influence à un événement extérieur à l'écosystème orchestré : crise réelle, catastrophe, breaking news indépendante, déclaration d'un acteur tiers non aligné. Marqueur typique : opportunité d'amplification d'un événement non scripté par l'opération elle-même.

T0068 ne s'applique pas quand un producteur orchestré relaie le jour même une déclaration émanant d'un acteur intérieur à son écosystème (ministre russe relayé par afrinz.ru, communiqué d'État AES relayé par un média d'État AES, communiqué d'African Initiative relayé par un amplificateur catégorie C coordonné). Dans ce cas, la coordination temporelle est un indice d'orchestration interne (cf. Étape 1, indice 3 de l'instruction préliminaire impérative), pas une réaction à breaking news. Préférer T0002 (Facilitate State Propaganda) + T0003 (Leverage Existing Narratives) + T0100.001 (Co-Opt Trusted Individuals) pour qualifier l'opération éditoriale.

Symétriquement avec la Règle 5 sur T0117 : T0117 et T0068 sont les deux techniques fréquemment sur-codées par méconnaissance de leur directionalité (T0117 « attirer un média externe » ≠ « relayer un acteur interne » ; T0068 « réagir à un événement extérieur » ≠ « relayer un acteur interne en coordination temporelle »).

═══════════════════════════════════════════════════════════════
DIMENSION 2 — QUATRE INDICATEURS DE SAILLANCE (échelle 0/1/2)
═══════════════════════════════════════════════════════════════

À appliquer à chaque contenu, indépendamment du résultat de la classification DISARM. Les saillances mesurent la densité de chaque matrice conceptuelle dans le contenu textuel global de l'article (propos cités inclus), indépendamment du producteur éditorial. Une saillance s'active en fonction du contenu textuel observé, jamais en fonction de l'identité du locuteur ou du producteur.

Saillance russe (R).
Définition : présence du récit stratégique russe documenté par Audinet (IRSEM n°119, 2024), dans une ou plusieurs de ses trois composantes :
(a) éléments de langage canoniques : « majorité mondiale », « multipolarité », « Occident collectif », « néocolonialisme monétaire », « pays vampire », « désoccidentalisation », « Sud global », « la Russie n'a jamais colonisé l'Afrique », « diviser pour régner » dans la version russe ;
(b) trois sous-récits structurels : Russie héritière de l'anti-impérialisme soviétique / Occident collectif néocolonial / Sud global partenaire naturel ;
(c) critique du néocolonialisme occidental général sans cible française spécifique (« pays occidentaux » au pluriel, « anciennes métropoles » au pluriel, « Occident » comme bloc) — cf. conventions R vs SC et R vs PA ci-dessous.

Seuils :
- 0 : aucun élément de langage Audinet, aucun des 3 sous-récits explicitement présent, aucune critique du néocolonialisme occidental général.
- 1 : 1 ou 2 occurrences d'éléments de langage canoniques OU 1 sous-récit explicitement présent OU 1 occurrence isolée de critique du néocolonialisme occidental général sans articulation structurée.
- 2 : 3+ occurrences d'éléments de langage canoniques OU 2+ sous-récits structurellement articulés OU critique structurée du néocolonialisme occidental général articulée à des éléments de langage Audinet ou à un sous-récit russe.

Saillance panafricaniste intellectuelle (PA).
Définition : mobilisation du registre panafricain continental et diasporique, dans une ou plusieurs de ses trois composantes :
(a) figures intellectuelles panafricaines : Diop, Nkrumah, Sankara, Césaire, Lumumba, Mbembe, Fanon, Senghor et leurs continuateurs contemporains ;
(b) concepts panafricains : négritude, décolonialité, panafricanisme socialiste, unité africaine, États-Unis d'Afrique, néocolonialisme au sens de Nkrumah (1965), antériorité africaine au sens de Diop ;
(c) thématiques panafricaines contemporaines structurées : démarches Union africaine, mouvement des réparations historiques pour la traite et la colonisation, mouvements diasporiques CARICOM, intellectuels panafricains contemporains.

Seuils :
- 0 : aucune référence à une figure panafricaine, aucun concept panafricain, aucune thématique panafricaine contemporaine structurée.
- 1 : 1 figure mentionnée nominalement OU 1 concept utilisé sans développement OU 1 thématique panafricaine contemporaine évoquée sans développement substantiel.
- 2 : développement substantiel d'une référence (citation, paraphrase argumentée) OU 2+ figures convoquées dans une argumentation structurée OU thématique panafricaine contemporaine traitée comme objet central de l'article et inscrite dans une généalogie panafricaine (mention de figures historiques, référence à l'Union africaine comme institution panafricaine, articulation à la diaspora ou aux mouvements diasporiques). La simple évocation d'une thématique panafricaine contemporaine sans cadre généalogique ou institutionnel panafricain reste à PA=1.

Saillance souverainiste africaine contemporaine (SC).
Définition : critique spécifiquement anti-française portée dans le registre du souverainisme africain contemporain, dans une ou plusieurs de ses trois composantes :
(a) dispositifs français nommés ou clairement identifiés : FCFA, bases militaires françaises (Barkhane, Serval, Épervier), accords de défense et de coopération, AFD, francophonie comme instrument politique, OIF, présence économique française (Areva-Orano, Bolloré, Total, Air France) ;
(b) désignations indirectes reconnaissables de la France dans le contexte sahélien post-2022 : « France-Afrique » au sens systémique, « la métropole », « l'ancienne puissance coloniale » quand la France est clairement la cible visée, « puissances nostalgiques d'un passé révolu », « impérialisme français » ;
(c) cautions intellectuelles et associatives du souverainisme franco-africain : ONG type Survie, intellectuels type Felwine Sarr et apparentés directs.

Seuils :
- 0 : aucun dispositif français spécifiquement nommé, aucune désignation indirecte reconnaissable de la France comme cible, aucune référence aux cautions intellectuelles ou associatives du souverainisme franco-africain.
- 1 : 1 dimension activée parmi les trois composantes (par ex. critique du FCFA seul, ou désignation indirecte de la France via « puissances nostalgiques d'un passé révolu » sans multi-dimensionnalité, ou référence isolée à Survie ou Sarr sans développement) sans articulation structurée à d'autres dimensions.
- 2 : critique structurée multi-dimensionnelle (2+ dimensions articulées : par ex. FCFA + bases françaises, ou désignation indirecte de la France + critique d'un dispositif spécifique, ou dispositif français spécifiquement nommé + caution Survie ou Sarr) OU développement substantiel d'une dimension unique (paragraphe entier consacré à la critique structurée du FCFA, ou article entièrement construit autour de la dénonciation de la « France-Afrique » au sens systémique).

Saillance nationale AES (AES).
Définition : mobilisation du registre national spécifique au pays considéré (Burkina, Mali, ou Niger), dans une ou plusieurs de ses quatre composantes :
(a) figures présidentielles AES avec leurs titres officiels complets : Capitaine Ibrahim Traoré (Président du Faso, Chef de l'État burkinabè), Général d'armée Assimi Goïta (Président de la Transition du Mali, Chef de l'État et Chef suprême des armées), Général Abdourahamane Tiani (Président du Conseil National pour la Sauvegarde de la Patrie au Niger) ;
(b) forces armées nationales et leurs partenariats : FAMa (Mali), FDS (Burkina), FAN (Niger), Africa Corps en partenariat, Bataillon d'intervention rapide, Force unifiée AES ;
(c) institutions et symboles de la Confédération AES : traité de juillet 2024 instituant la Confédération, Banque confédérale, drapeau vert-rouge, sommets présidentiels, ressources nationales reprises en main (uranium nigérien, or burkinabè et malien) ;
(d) figures historiques nationales et marqueurs identitaires locaux : Sankara comme inspirateur de Traoré (Burkina), Modibo Keïta et Soumangourou Kanté (Mali), victoire diplomatique du Niger face à la CEDEAO en juillet 2023, « Pays des hommes intègres » (Burkina), « Maliba » (Mali).

Seuils :
- 0 : aucune figure présidentielle AES, aucun marqueur des forces armées nationales AES, aucune référence aux institutions ou symboles de la Confédération AES, aucun marqueur identitaire national spécifique.
- 1 : 1 figure présidentielle mentionnée OU 1 marqueur isolé des forces armées nationales OU 1 référence isolée aux institutions ou symboles AES OU 1 marqueur identitaire national isolé.
- 2 : reprise structurée des titres officiels complets (citations, paraphrases longues d'un discours présidentiel) OU 2+ marqueurs nationaux articulés (par ex. figure présidentielle + force armée nationale + institution AES, ou figure présidentielle + référence historique nationale + marqueur symbolique).

Cas limites saillances :
- Doute entre deux niveaux : noter le niveau inférieur (principe de prudence).
- Contenu très court (< 100 mots) : appliquer les seuils tels quels.
- Saillance multiple : un contenu peut avoir plusieurs saillances à 2 simultanément. C'est précisément ce que mesure le protocole — l'hybridation maximale.
- **Souveraineté ressourcière (uranium nigérien, or burkinabè et malien, FCFA comme ressource monétaire) : activations multiples attendues.** La thématique de la souveraineté ressourcière est conceptuellement à l'intersection des matrices. Coder simultanément AES (si la ressource nationale est nommée comme reprise en main), R (si la critique est articulée structurellement au pillage occidental dans la phraséologie Audinet ou aux sous-récits russes), SC (si la France est nommée ou désignée indirectement comme acteur du pillage). Pas de hiérarchie entre les trois saillances. Les chevauchements sur cette thématique sont attendus et analytiquement informatifs (cf. §4.2 du doc 05 sur l'hybridation comme objet de mesure).

═══════════════════════════════════════════════════════════════
CONVENTIONS DE DÉLIMITATION ENTRE INDICATEURS DE SAILLANCE
═══════════════════════════════════════════════════════════════

Six conventions précisent les frontières entre indicateurs. Elles s'appliquent à chaque codage de saillance pour discriminer les cas limites. Principe général : les chevauchements entre indicateurs sont attendus et acceptés ; ils mesurent l'hybridation. Les conventions ci-dessous ne servent pas à éliminer les chevauchements naturels mais à discriminer là où c'est analytiquement nécessaire.

Convention R vs SC — France désignée vs Occident comme bloc.
SC s'active dès que la France est désignée comme cible de la critique, soit explicitement par les dispositifs nommés (composante a de SC), soit par désignation indirecte reconnaissable dans le contexte sahélien post-2022 (composante b de SC), soit par référence aux cautions intellectuelles ou associatives du souverainisme franco-africain (composante c de SC). R s'active sur le sous-récit « Occident collectif néocolonial » quand la critique vise l'Occident comme bloc sans singulariser la France (« pays occidentaux », « anciennes métropoles » au pluriel, « Occident » comme bloc), et sur les éléments de langage Audinet indépendamment de la cible.

Les chevauchements R + SC sont attendus et acceptés. Un article qui mobilise simultanément les éléments de langage Audinet (R) ET désigne la France comme cible (SC) doit recevoir une activation des deux indicateurs. Cette double activation est le marqueur opérationnel de l'hybridation maximale (dimension générique du récit russe au sens d'Audinet IRSEM n°119).

Critère opérationnel pour la composante b de SC (désignations indirectes reconnaissables) : la désignation doit être reconnaissable dans le contexte sahélien post-2022 sans recours à des inférences spéculatives. Test : un lecteur informé du contexte sahélien identifie-t-il sans ambiguïté la France comme cible de la critique ? Si oui, SC s'active. Si la cible reste ambiguë (par exemple « les puissances coloniales » sans contexte qui singularise la France), conserver la lecture la plus restrictive et coder R sans SC. En cas de doute sur la reconnaissabilité de la cible française, ne pas activer SC (principe de prudence).

Convention R vs PA — Critique du néocolonialisme général dans un contexte panafricain.
La critique du néocolonialisme occidental général (« pays occidentaux », « anciennes métropoles », « Occident » comme bloc) relève **par défaut de R** (composante c, sous-récit « Occident collectif néocolonial »), conformément à la prévalence statistique dans le corpus pro-AES anti-français : dans ce corpus, la critique structurée du néocolonialisme général est dominée par la diffusion russe documentée par Audinet.

**Exception — basculement vers PA :** quand la critique du néocolonialisme général s'accompagne dans le même contenu d'au moins un marqueur historiquement panafricain (figure intellectuelle panafricaine : Diop, Nkrumah, Sankara, Césaire, Lumumba, Mbembe, Fanon, Senghor ; OU concept spécifiquement panafricain : négritude, décolonialité, panafricanisme socialiste, unité africaine, États-Unis d'Afrique, antériorité africaine au sens de Diop, néocolonialisme **au sens de Nkrumah 1965 explicitement référencé** ; OU thématique panafricaine contemporaine structurée : démarche UA, réparations historiques inscrites dans une généalogie panafricaine, mouvement diasporique CARICOM), alors la critique du néocolonialisme général relève de PA, pas de R. Le néocolonialisme est dans ce cas mobilisé dans sa signification panafricaine historique (concept fondateur de Nkrumah 1965, antérieur de 60 ans à Audinet) et non comme reprise de l'élément de langage russe.

Test opérationnel : le marqueur panafricain doit être présent **dans le même contenu** que la critique du néocolonialisme général (pas dans un autre article, pas inféré). Si la critique du néocolonialisme général est isolée sans marqueur panafricain co-présent, elle reste à R.

Cas de double activation R + PA : si la critique du néocolonialisme général s'accompagne **simultanément** d'éléments de langage canoniques Audinet (« multipolarité », « majorité mondiale », « Sud global ») ET de marqueurs historiquement panafricains, activer R et PA conjointement. La double activation est le marqueur opérationnel du recouvrement entre la matrice panafricaine et le récit russe (Audinet documente précisément ce recouvrement comme stratégie de la dimension générique).

Convention PA vs SC — Frontière thématique, pas temporelle.
PA couvre le registre panafricain continental et diasporique (figures intellectuelles panafricaines, concepts panafricains, thématiques panafricaines contemporaines incluant la démarche réparations et les mouvements diasporiques). SC couvre la critique spécifiquement franco-centrée des dispositifs français en Afrique. Un article peut activer simultanément PA et R sans activer SC (cas d'un article continental sur les réparations relayé par un producteur russe), et un article peut activer SC sans activer PA ni R (cas d'une critique franco-centrée spécifique sans cadre panafricain ni relais russe explicite).

Convention PA vs R sur les thématiques contemporaines (chevauchement attendu).
Les thématiques panafricaines contemporaines (notamment les réparations) sont systématiquement relayées par la diplomatie russe depuis 2024-2025 (Lavrov, Berdyev, Abramova). Un article qui mobilise la thématique des réparations peut activer simultanément R=2 (relais russe explicite avec éléments de langage Audinet) et PA=1 ou 2 (thématique panafricaine contemporaine structurée). Cette double activation n'est pas un problème de codage : c'est ce que mesure l'hybridation.

Convention AES vs PA — Ancrage national vs continental.
AES capte le registre national spécifique au pays (figures présidentielles AES, forces armées nationales, institutions confédérales, marqueurs identitaires locaux). PA capte le registre panafricain continental et diasporique. Un article peut activer simultanément AES et PA (cas typique d'un discours présidentiel AES citant Sankara : AES activé par la formulation officielle et la figure présidentielle, PA activé par l'invocation de Sankara comme figure panafricaine).

Convention AES vs R — Ancrage national vs récit stratégique russe.
AES capte ce qui est spécifiquement AES (figures, institutions, symboles). R capte le récit stratégique russe (éléments de langage Audinet, sous-récits). Un discours présidentiel AES peut activer simultanément AES=2 (sa qualité de discours présidentiel AES) et R=1 ou 2 (s'il reprend des éléments de langage Audinet ou un sous-récit russe). Cette double activation est le marqueur opérationnel de la recombinaison opérée par les juntes AES (recombinateurs de matrices, pas matrice autonome).

═══════════════════════════════════════════════════════════════
PRÉCAUTION ANALYTIQUE — PRÉSENCE TEXTUELLE VS ORIGINE CAUSALE
═══════════════════════════════════════════════════════════════

Les quatre indicateurs de saillance mesurent la présence dans le contenu des matrices conceptuelles documentées. Ils ne mesurent pas l'origine causale du contenu (qui le produit, qui le commande, qui le diffuse). Un contenu codé SC=2 ne signifie pas que la matrice souverainiste africaine est la matrice productrice du contenu ; il signifie que la matrice souverainiste africaine est lexicalement et narrativement présente dans le contenu, indépendamment de qui le produit. Symétriquement pour R, PA et AES. L'attribution causale d'un contenu à un producteur (russe orchestré, amplificateur coopté, acteur local autonome) se fait par croisement avec la typologie des producteurs et avec l'analyse de reformulation, pas par la grille de saillances seule.

Conséquence opérationnelle pour le codage : ne jamais retirer une saillance au motif que le producteur est de catégorie A (afrinz.ru et autres). Si afrinz.ru produit un article qui mobilise les marqueurs SC (par exemple Lavrov critiquant le FCFA), SC doit s'activer dans le codage de cet article. Si un ministre AES cité dans un article afrinz.ru critique la France par désignation reconnaissable, SC doit s'activer. Le codage suit le contenu textuel global, jamais l'identité du producteur.

═══════════════════════════════════════════════════════════════
DIMENSION 3 — SIX AXES LEXICAUX NKILI (activation binaire 0 ou 1)
═══════════════════════════════════════════════════════════════

**Avertissement méthodologique sur l'évaluation fonctionnelle des axes Nkili.** Les marqueurs lexicaux listés pour chaque axe ci-dessous sont indicatifs, pas exhaustifs. Ils donnent des exemples typiques du concept fonctionnel couvert par chaque axe. Le critère d'activation est fonctionnel — la mécanique désignée par les marqueurs est-elle exercée par le texte ? — pas lexical strict — les expressions exactes sont-elles présentes dans le texte ? Quand un texte exerce la fonction d'un axe sans mobiliser les expressions-types listées, l'axe s'active. Symétriquement, quand un texte mobilise une expression-type sans exercer la fonction (par exemple emploi ironique, citation distanciée), l'axe ne s'active pas.

Exemple opérationnel sur l'axe 6 (métadiscours informationnel) : un article qui dénonce un dispositif occidental de manipulation du débat public (« tentatives de détourner le débat », « création de fonds sous leur contrôle pour renverser l'ordre du jour ») active l'axe 6 même s'il n'emploie ni « médias occidentaux menteurs » ni « bataille informationnelle ». La fonction de dénonciation d'une manipulation occidentale du discours public est exercée ; les marqueurs listés en sont des cas particuliers, pas la définition exhaustive.

**À appliquer à chaque contenu, indépendamment du résultat de la classification DISARM.** Pour chaque axe, indiquer 1 si activé, 0 sinon. Un contenu peut activer plusieurs axes simultanément.

Axe 1 — Anti-impérialisme.
Activé si le contenu mobilise un ou plusieurs marqueurs : « néocolonialisme », « France colonise », « souveraineté retrouvée », « impérialisme occidental », « pays vampire », « #FranceDégage », « Russie n'a jamais colonisé l'Afrique », critique structurée de la présence française en Afrique.

Axe 2 — Efficacité sécuritaire.
Activé si le contenu mobilise : « échec Barkhane », « Paris arme les djihadistes », « France soutient les terroristes », « bilan sécuritaire FAMa », « victoires Africa Corps », mention chiffrée d'opérations militaires, comparaison des résultats sécuritaires France vs Russie.

Axe 3 — Partenariat.
Activé si le contenu mobilise : « partenaire sans agenda », « choisir ses propres partenaires », « souveraineté du choix », « bases co-gérées », « projets de développement », « coopération mutuellement bénéfique », mention valorisante du partenariat AES-Russie ou AES-Chine.

Axe 4 — Économique.
Activé si le contenu mobilise : « pillage des ressources », « billets CFA brûlés », « FCFA monnaie coloniale », paiements roubles/or, « banque africaine », critique AFD/FMI, « réparations », nationalisation de ressources.

Axe 5 — Identité-affect.
Activé si le contenu mobilise : « dignité africaine », « résistance », « fierté », drapeaux russes mentionnés textuellement, figures Sankara/Lumumba/Kadhafi, « francophonie » (critique ou défense), « valeurs partagées », registre émotionnel de fierté ou de colère.

Axe 6 — Métadiscours informationnel.
Activé si le contenu mobilise : « vérité cachée », « médias occidentaux menteurs », « fake news françaises », « propagande coloniale », « bataille informationnelle », mentions explicites de désinformation occidentale, fact-checking inverse.

Cas limites axes Nkili :
- Marqueur isolé sans développement : activation = 1.
- Doute sur la frontière entre deux axes : activer les deux et le signaler dans le champ JUSTIFICATION AXES.

═══════════════════════════════════════════════════════════════
PROCÉDURE DE CLASSIFICATION ET FORMAT DE RÉPONSE
═══════════════════════════════════════════════════════════════

Pour chaque contenu soumis :

1. Applique l'instruction préliminaire impérative (Étapes 1 et 2, dont la grille de 5 indices textuels pour C/D le cas échéant).
2. Si la classification DISARM s'applique :
   a. Identifie la ou les tactiques DISARM pertinentes. Un article peut mobiliser des techniques de plusieurs tactiques simultanément ; lister toutes les tactiques actives séparées par des points-virgules.
   b. Identifie les techniques DISARM pertinentes (code Txxxx + nom). Appliquer le principe de classification homogène article par article et les 7 règles de calibrage fin. Mobiliser exclusivement les codes V1.6.
   c. Fournis une justification : 1-2 phrases pour les cas simples ; 3-5 phrases pour les cas où une distinction primaire/secondaire est opérée ou où un arbitrage entre techniques nécessite explication. Pour chaque technique retenue, identifier la phrase précise du contenu qui la justifie (à reporter dans le champ PHRASES-PREUVES).
   d. Indique un niveau de confiance DISARM : HIGH, MEDIUM ou LOW.
   e. Indique un degré d'orchestration apparent : FORT / MOYEN / FAIBLE / ABSENT, à partir de la grille de 5 indices textuels de l'instruction préliminaire impérative. Ce champ est distinct du champ ORCHESTRATION (catégoriel) et permet une lecture continue du spectre d'orchestration (cf. doc 05 §13.3.2).
3. Si la classification DISARM ne s'applique pas (expression non-orchestrée, ou marqueur technique involontaire), indique le motif en une phrase.
4. Quel que soit le statut de la classification DISARM, indique les 4 saillances (en appliquant les 6 conventions de délimitation et la précaution analytique) et les 6 axes Nkili.

Cas particulier — opération éditoriale minimale dans un écosystème orchestré : si le producteur est orchestré (catégorie A ou B) mais que l'opération éditoriale est minimaliste (relais factuel d'un communiqué officiel sans recadrage explicite), une classification DISARM minimaliste reste valide (T0003 et T0136 ou T0136.006 selon le contexte, typiquement) avec confiance MEDIUM assumée. Ne pas sur-classifier par excès de zèle ; ne pas refuser la classification en se réfugiant derrière « non-orchestré ».

Si le contenu décrit un marqueur technique involontaire (erreur d'OPSEC, artefact technique non intentionnel), indique pour la partie DISARM "PAS UNE TECHNIQUE DISARM — Marqueur technique involontaire" et continue à noter saillances et axes Nkili.

Réponds uniquement au format suivant :

ORCHESTRATION: ORCHESTRÉE_ÉTRANGÈRE / ORCHESTRÉE_DOMESTIQUE / NON_ORCHESTRÉE / TECHNIQUE_INVOLONTAIRE
DEGRÉ_ORCHESTRATION: FORT / MOYEN / FAIBLE / ABSENT (indices textuels présents : 3+ / 2 / 1 / 0)
ÉNONCIATEUR: PRIMAIRE_DISTINCT_SECONDAIRE / PRIMAIRE_SECONDAIRE_CONFONDUS / NON_APPLICABLE
TACTIQUE(S): TAxx - Nom (séparer par ; si plusieurs tactiques actives, ou NON_APPLICABLE)
TECHNIQUE(S): Txxxx - Nom / Txxxx.xxx - Nom (séparer par / ou NON_APPLICABLE — codes V1.6 exclusivement)
PHRASES-PREUVES:
  - Txxxx - Nom : "citation exacte ou paraphrase resserrée de la phrase du contenu qui justifie la technique"
  - Txxxx.xxx - Nom : "citation exacte ou paraphrase resserrée"
  [Une ligne par technique listée dans TECHNIQUE(S). NON_APPLICABLE si aucune classification DISARM.]

JUSTIFICATION DISARM: [1-2 phrases pour cas simple, 3-5 phrases si distinction énonciation ou arbitrages requis]
CONFIANCE DISARM: HIGH / MEDIUM / LOW (ou NON_APPLICABLE)
SAILLANCES: R=[0/1/2] PA=[0/1/2] SC=[0/1/2] AES=[0/1/2]
JUSTIFICATION SAILLANCES: [une phrase listant les marqueurs principaux observés par saillance ; signaler explicitement l'application des conventions R vs SC, R vs PA, ou autres conventions de délimitation quand elles ont été décisives]
AXES_NKILI: Anti-impérialisme=[0/1] Efficacité sécuritaire=[0/1] Partenariat=[0/1] Économique=[0/1] Identité-affect=[0/1] Métadiscours informationnel=[0/1]
JUSTIFICATION AXES: [une phrase listant les marqueurs principaux observés par axe activé]
"""


def build_disarm_prompt() -> str:
    """Construit le prompt DISARM v4.2 en interpolant la matrice V1.6.

    DISARM_PROMPT_V42 (~7300 mots, stable) contient un placeholder
    {DISARM_MATRIX} remplacé par le contenu de li/disarm_matrix.md à
    chaque appel. Le bloc complet est marqué cache_control=ephemeral
    côté core/analyze.py::call_claude.
    """
    matrix_path = Path(__file__).parent / "disarm_matrix.md"
    matrix_content = matrix_path.read_text(encoding="utf-8")
    return DISARM_PROMPT_V42.format(DISARM_MATRIX=matrix_content)


# WARNING: redondance potentielle avec DISARM_PROMPT_V42 (saillances+Nkili déjà inclus). À auditer post-publication rapport.
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
