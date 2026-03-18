# osint-ai-toolkit

> Toolkit OSINT augmenté par l'IA — détection de campagnes d'influence et contextualisation de menaces CTI.

> OSINT toolkit augmented with AI — applications for Cyber Threat Intelligence and Information Warfare analysis.

## Overview

Modular Python framework built around a shared core (API collection, SQLite storage, LLM analysis via Claude API) with two distinct applications:

- **CTI application** (`cti/`): automated IoC enrichment pipeline, active pivoting, and contextualized threat briefs by organization profile
- **LI application** (`li/`): detection and analysis workflow for influence operations, DISARM framework classification, network visualization

## Repository structure
```
osint-ai-toolkit/
├── core/        # Shared modules: API collection, SQLite storage, LLM analysis
├── cti/         # CTI application: enrichment, pivoting, brief generation
├── li/          # LI application: detection, DISARM classification, reporting
├── data/        # Sample input data
├── outputs/     # Sample results
└── README.md
```

## Status

Work in progress — Phase 1 (March 2026). Core modules and applications under active development.

## Author

Romain Génard — [LinkedIn](https://linkedin.com/in/romaingenard)
