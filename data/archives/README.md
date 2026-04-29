# Archives du corpus LI

Archivage double obligatoire (Wayback Machine + SingleFile) de tous les contenus collectés dans le cadre du workflow LI.

Conformément au cadrage méthodologique (document 05 du plan d'action, décision A), aucun contenu n'est intégré au corpus s'il n'a pas été doublement archivé. En cas d'échec d'un seul des deux archivages, le contenu est mis en file de retry. Si les deux échouent, le contenu est rejeté.

## Structure

data/archives/
- entity_slug/
  - YYYY-MM-DD/
    - article_id__short-title-slug.html
    - article_id__short-title-slug.wayback.txt
    - article_id__metadata.json

## Conventions de nommage

- entity_slug : identifiant kebab-case de l'entité, correspond à la colonne slug de data/entities.csv.
- YYYY-MM-DD : date de publication de l'article (pas date de collecte). Tri chronologique facilité.
- article_id : identifiant alphanumérique généré par li/store_li.py (préfixe a, ex : a042).
- short-title-slug : 3 à 5 mots du titre en kebab-case, longueur maximale 50 caractères.

## Trois fichiers par article

- .html : Archive SingleFile autonome (HTML + CSS + images inline). Producteur : single-file-cli via subprocess Python.
- .wayback.txt : URL d'archive Wayback Machine (ligne unique). Producteur : API web.archive.org/save/.
- _metadata.json : Titre, date publication, URL source, hash de contenu, langue, statut archivage. Producteur : li/detect.py.

## OPSEC

- VPN obligatoire actif sur la machine hôte avant toute session de collecte.
- Navigateur dédié (pas le navigateur personnel) pour single-file-cli, configuré via la constante SINGLEFILE_BROWSER_PATH de li/config.py.
- Aucun fichier d'archive n'est commité dans Git. Le dossier data/archives/ est exclu via .gitignore. Seule la base SQLite (data/corpus.db) référence les chemins.

## Dossier _template/

Contient une structure d'exemple vide pour rappel visuel de la convention. Ne pas supprimer, ne pas y placer de contenu réel.
