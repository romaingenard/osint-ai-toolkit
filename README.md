# osint-ai-toolkit

> **AI-augmented OSINT toolkit** — for Cyber Threat Intelligence (CTI) and Information Warfare (LI) analysis.
> **Boîte à outils OSINT augmentée par l'IA** — pour l'analyse de la menace cyber (CTI) et informationnelle (LI).

*English version below — [version française plus bas](#français)*

---

## English

### Overview

A modular Python framework for open-source intelligence analysis, built around a shared core (collection, structured storage, LLM-assisted analysis) with two applications: one for influence-operation analysis (LI), one for cyber threat intelligence (CTI).

The toolkit was designed and built as part of a career transition toward threat analysis. Its LI application produced a complete analytical report on the anti-French information ecosystem in the Sahel (see below).

### The LI Sahel report

The toolkit's first full application is a comparative mapping of the anti-French, pro-AES information ecosystem in Mali, Burkina Faso and Niger (February–March 2026), based on a corpus of 221 open-source items classified with the DISARM framework.

Its central finding is that this ecosystem resists both simple readings. It is neither a Kremlin operation dressed up as African anger, nor a purely local mobilisation on which Russia has only marginal hold. The report documents three coexisting realities: an authentic local grievance, rooted in causes that predate Russia's arrival; an identifiable, circumscribed Russian operator (the African Initiative galaxy); and a wide zone of **recombination** where the Russian repertoire and local expression blend until the line between them blurs.

Three results stand out. Nearly half the corpus carries no detectable Russian marker, which the report reads without collapsing local agency into Russian diffusion. The three countries show distinct signatures — state-driven sovereignism in Niger, a mixed and porous ecosystem in Burkina Faso, co-opted amplifiers in Mali. And Russian influence circulates as a **repertoire of arguments and frames** that local actors rework on their own terms, not as copied text — the reformulation analysis finds no verbatim reuse.

📄 *Full report: link to be added.*

### How it works

The workflow chains four stages, each handled by a dedicated module:

1. **Collection** — source-specific collectors (WordPress API, public Telegram channels, web archives) gather open-source content.
2. **Storage** — collected items and their metadata are stored in a structured SQLite database, queryable for analysis.
3. **Classification** — content is classified by a large language model (Claude), against an explicit, injected DISARM reference, with two-stage evaluation (strategic function first, lexical markers second) and per-item evidence justification for auditability.
4. **Analysis** — extraction and audit scripts produce the material for human review, following the *Centaur method*: model output is systematically cross-checked against manual coding rather than trusted blindly.

### Repository structure

```
osint-ai-toolkit/
├── core/          # Shared modules: collection, storage, LLM analysis
│   ├── collect.py        # Generic collectors and API helpers
│   ├── store_cti.py      # CTI storage layer
│   └── analyze.py        # Generic LLM call wrappers
├── li/            # Information-warfare application
│   ├── detect.py             # Source-specific collectors
│   ├── config.py             # DISARM matrix, saliences, classification rules
│   ├── classify_batch.py     # Batch classification orchestrator
│   ├── parse_classification.py   # Strict output parser
│   ├── store_li.py           # LI storage layer
│   └── analysis/             # Read-only scripts that built the LI report
├── cti/           # CTI application (in development)
├── tests/         # Test suite
├── data/          # Sample/example inputs (operational data not versioned)
└── README.md
```

### Design notes

- The shared core (`core/`) is generic: it knows nothing about a specific framework or domain. All domain knowledge (DISARM, saliences, prompts) lives in the application layers, so the same core serves both LI and CTI.
- The DISARM v1.6 reference is injected into the model prompt rather than relied on from memory, making classification explicit and reproducible.
- Scripts in `li/analysis/` open the corpus database in read-only mode and document how the report's material was produced.

### Status

Functional. The LI application produced a complete analytical report (June 2026). The CTI application is under active development. The tag `v1.0-rapport-sahel` marks the state of the code that produced the LI report.

### Tech

Python, SQLite, Anthropic Claude API (batch). API keys are read from the environment; no operational data or credentials are versioned.

---

## Français

### Présentation

Une boîte à outils Python modulaire pour l'analyse en sources ouvertes, construite autour d'un noyau commun (collecte, stockage structuré, analyse assistée par IA) et de deux applications : l'une pour l'analyse des opérations d'influence (LI), l'autre pour la cyber threat intelligence (CTI).

Le toolkit a été conçu et développé dans le cadre d'une reconversion vers l'analyse de la menace. Son application LI a produit un rapport d'analyse complet sur l'écosystème informationnel anti-français au Sahel (voir ci-dessous).

### Le rapport LI Sahel

La première application complète du toolkit est une cartographie comparée de l'écosystème informationnel anti-français et pro-AES au Mali, au Burkina Faso et au Niger (février-mars 2026), à partir d'un corpus de 221 contenus en sources ouvertes classés selon le cadre DISARM.

Son constat central est que cet écosystème résiste aux lectures simples. Il n'est ni le seul fruit d'une opération du Kremlin déguisée en colère africaine, ni une mobilisation purement locale sur laquelle la Russie n'aurait qu'une prise marginale. Le rapport documente la coexistence de trois réalités : un grief local authentique, enraciné dans des causes antérieures à l'entrée russe sur le terrain ; une source russe identifiable et circonscrite (la galaxie African Initiative) ; et une vaste zone de **recombinaison** où le répertoire russe et l'expression locale se mêlent au point que la frontière entre eux cesse d'être lisible.

Trois résultats ressortent. Près de la moitié du corpus ne porte aucun marqueur russe détectable, un constat que le rapport lit sans réduire l'initiative locale à une diffusion russe. Les trois pays présentent des signatures distinctes — souverainisme d'État au Niger, écosystème mixte et poreux au Burkina Faso, amplificateurs cooptés au Mali. Et l'influence russe circule comme un **répertoire d'arguments et de cadres** que des acteurs locaux reformulent à leur compte, et non comme un texte recopié : l'analyse de reformulation ne relève aucune reprise textuelle.

📄 *Rapport complet : lien à venir.*

### Fonctionnement

Le workflow enchaîne quatre étapes, chacune prise en charge par un module dédié :

1. **Collecte** — des collecteurs adaptés à chaque type de source (API WordPress, canaux Telegram publics, archives web) recueillent les contenus en sources ouvertes.
2. **Stockage** — les contenus et leurs métadonnées sont rangés dans une base SQLite structurée, interrogeable pour l'analyse.
3. **Classification** — les contenus sont classés par un grand modèle de langage (Claude), contre une référence DISARM explicite injectée dans la consigne, avec une évaluation en deux temps (fonction stratégique d'abord, marqueurs lexicaux ensuite) et une justification par citation pour l'auditabilité.
4. **Analyse** — des scripts d'extraction et d'audit produisent la matière soumise à la relecture humaine, selon la *méthode Centaure* : la sortie du modèle est systématiquement confrontée au codage manuel plutôt que tenue pour acquise.

### Structure du dépôt

```
osint-ai-toolkit/
├── core/          # Modules communs : collecte, stockage, analyse LLM
│   ├── collect.py        # Collecteurs génériques et utilitaires API
│   ├── store_cti.py      # Couche de stockage CTI
│   └── analyze.py        # Wrappers génériques d'appel au LLM
├── li/            # Application lutte informationnelle
│   ├── detect.py             # Collecteurs par type de source
│   ├── config.py             # Matrice DISARM, saillances, règles de classification
│   ├── classify_batch.py     # Orchestrateur de classification par lots
│   ├── parse_classification.py   # Parseur strict des sorties
│   ├── store_li.py           # Couche de stockage LI
│   └── analysis/             # Scripts en lecture seule ayant produit le rapport LI
├── cti/           # Application CTI (en développement)
├── tests/         # Suite de tests
├── data/          # Données d'exemple (données opérationnelles non versionnées)
└── README.md
```

### Choix de conception

- Le noyau commun (`core/`) est générique : il ne connaît ni framework ni domaine particulier. Toute la connaissance métier (DISARM, saillances, prompts) vit dans les couches applicatives, si bien que le même noyau sert le LI et le CTI.
- La référence DISARM v1.6 est injectée dans la consigne du modèle plutôt que laissée à sa mémoire, ce qui rend la classification explicite et reproductible.
- Les scripts de `li/analysis/` ouvrent la base du corpus en lecture seule et documentent la manière dont la matière du rapport a été produite.

### Statut

Fonctionnel. L'application LI a produit un rapport d'analyse complet (juin 2026). L'application CTI est en cours de développement. Le tag `v1.0-rapport-sahel` marque l'état du code ayant produit le rapport LI.

### Technique

Python, SQLite, API Claude d'Anthropic (batch). Les clés d'API sont lues depuis l'environnement ; aucune donnée opérationnelle ni aucun secret n'est versionné.

---

## Author / Auteur

Romain Génard — [LinkedIn](https://www.linkedin.com/in/romain-génard-5ab80013a/)

## License / Licence

See [LICENSE](LICENSE) — voir [LICENSE](LICENSE).
