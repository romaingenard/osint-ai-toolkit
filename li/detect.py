"""li/detect.py — collecte + archivage + pré-filtrage + stockage (P1).

Refonte : 24 avril 2026. Nouveau sujet : "Narratifs anti-français au Sahel
2025-2026".

Scope de ce brief :
- 4 collecteurs P1 : fetch_wordpress_api, fetch_html_site,
  fetch_telegram_channel, fetch_manual_event.
- Archivage double (Wayback + SingleFile) obligatoire avant stockage.
- Orchestrateur collect_entity() qui enchaîne collecte → archivage →
  pré-filtre lexical (config.passes_inclusion_filter) → insert DB.

Hors scope (brief 2) : collecteurs Facebook/TikTok, similarité de
reformulation, détection de coordination. Pas de stubs.

Prérequis externes :
- single-file-cli installé globalement (npm install -g single-file-cli).
- Accès sortant HTTPS vers web.archive.org et les sources cibles.
"""

import argparse
import hashlib
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from li import config
from li import store_li


HEADERS = {
    # User-Agent générique. Certaines sources bloquent les UA vides ou
    # "python-requests/…" par défaut.
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class ArchiveError(RuntimeError):
    """Levée quand les deux archivages (Wayback + SingleFile) échouent.
    Par contrat méthodologique (doc 05 §A), on refuse de stocker un
    article qui n'a aucune trace archivée."""


# === COUCHE COLLECTE ======================================================

def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _retry_request(
    func,
    entity_id: str,
    max_attempts: int = 3,
    base_delay_ms: int = 200,
    retry_status: tuple[int, ...] = (500, 502, 503, 504),
) -> "requests.Response":
    """Retry un appel HTTP avec backoff exponentiel sur 5xx + Timeout.

    Délais entre tentatives : base_delay_ms * 2^(attempt-1).
    Par défaut : 200ms, 400ms, 800ms (cf. Q4 brief 2bis pré-tranchée).

    Comportement après max_attempts échouées :
    - Timeout persistant : raise la dernière requests.Timeout
      (le caller la catche dans son try/except RequestException).
    - 5xx persistant : return la response (status >= 500), le caller
      doit vérifier explicitement resp.status_code >= 500 et break.

    Réutilisable par fetch_wordpress_api (C1.2) et fetch_wayback_cdx (C3).
    """
    last_exc: requests.Timeout | None = None
    resp = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = func()
            if resp.status_code not in retry_status:
                return resp
            print(f"[retry] {entity_id} attempt {attempt}/{max_attempts}: HTTP {resp.status_code}")
        except requests.Timeout as e:
            last_exc = e
            print(f"[retry] {entity_id} attempt {attempt}/{max_attempts}: timeout {e}")
        if attempt < max_attempts:
            time.sleep((base_delay_ms / 1000.0) * (2 ** (attempt - 1)))
    if resp is None and last_exc is not None:
        raise last_exc
    return resp


def fetch_wordpress_api(
    entity: dict,
    since: str,
    until: str,
) -> list[dict]:
    """Collecte via l'API REST WordPress native (/wp-json/wp/v2/posts).

    Cible primaire : afrinz.ru et dérivés WP de la catégorie A. Méthode
    documentée par Viginum (rapport African Initiative, juin 2025) comme
    moyen d'extraction structuré du corpus afrinz.ru.

    Pagination native via `page` / `per_page`. L'API WP retourne les dates
    au format ISO 8601 dans le champ `date` (timezone locale du site) et
    le contenu dans `content.rendered` (HTML, à stripper).

    En cas d'indisponibilité de l'API (404, 403, timeout), on log et on
    retourne une liste vide. Pas de fallback HTML silencieux : un site WP
    dont l'API est coupée devrait être requalifié en collector=html_generic
    dans entities.csv par Romain.
    """
    base_url = entity["url"].rstrip("/")
    api_url = f"{base_url}/wp-json/wp/v2/posts"
    rate_limit = entity.get("rate_limit_seconds", 2.0)

    # L'API WP accepte ISO 8601 complet. On passe la date seule, elle sera
    # interprétée comme 00:00:00 du jour.
    params = {
        "after": f"{since}T00:00:00",
        "before": f"{until}T23:59:59",
        "per_page": 100,
        "page": 1,
        "orderby": "date",
        "order": "desc",
    }

    articles: list[dict] = []
    max_pages = 50  # garde-fou : 50 pages × 100 posts = 5000 articles max

    while params["page"] <= max_pages:
        try:
            resp = _retry_request(
                lambda: requests.get(api_url, params=params, headers=HEADERS, timeout=30),
                entity_id=entity["entity_id"],
                max_attempts=3,
                base_delay_ms=200,
                retry_status=(500, 502, 503, 504),
            )
        except requests.RequestException as e:
            print(f"[WP-API] {api_url} requête échouée (page {params['page']}) : {e}")
            break
        if resp.status_code >= 500:
            print(f"[WP-API] {api_url} 5xx persistant après 3 tentatives (page {params['page']})")
            break

        if resp.status_code == 400 and params["page"] > 1:
            # WordPress renvoie 400 "rest_post_invalid_page_number" quand
            # on dépasse. Fin normale de pagination.
            break
        if resp.status_code != 200:
            print(f"[WP-API] {api_url} status={resp.status_code} — abandon.")
            break

        batch = resp.json()
        if not batch:
            break

        for post in batch:
            text_html = post.get("content", {}).get("rendered", "")
            text = BeautifulSoup(text_html, "html.parser").get_text("\n", strip=True)
            title = BeautifulSoup(
                post.get("title", {}).get("rendered", ""), "html.parser"
            ).get_text(strip=True)
            articles.append({
                "url": post.get("link") or "",
                "title": title,
                "date_published": post.get("date") or None,
                "text_content": text,
                "language": entity["default_language"],
            })

        params["page"] += 1
        time.sleep(rate_limit)

    print(f"[WP-API] {entity['entity_id']} : {len(articles)} article(s) collecté(s)")
    return articles


def fetch_html_site(
    entity: dict,
    since: str,
    until: str,
) -> list[dict]:
    """Collecte HTML paramétrable via sélecteurs CSS définis dans l'entité.

    Cible primaire : médias d'État AES (catégorie B) et sites sans API.
    Les trois sélecteurs CSS (title/date/content) viennent de l'entité.
    La détection des URLs d'articles sur la home est une heuristique
    générique (liens internes non-catégorie, non-tag).

    Filtrage par date : tolérant. Si date_published ne peut être extraite
    ou parsée (site mal balisé), l'article est inclus quand même — on
    préfère un corpus un peu plus large à un corpus amputé silencieusement.
    """
    base_url = entity["url"].rstrip("/")
    rate_limit = entity.get("rate_limit_seconds", 2.0)

    title_sel = entity.get("html_title_selector") or ""
    date_sel = entity.get("html_date_selector") or ""
    content_sel = entity.get("html_content_selector") or ""

    if not (title_sel and content_sel):
        raise ValueError(
            f"fetch_html_site : entité {entity['entity_id']} — "
            f"html_title_selector et html_content_selector obligatoires "
            f"pour ce collecteur."
        )

    # Home : récupérer les liens d'articles.
    try:
        home = requests.get(base_url, headers=HEADERS, timeout=30)
        home.raise_for_status()
    except requests.RequestException as e:
        print(f"[HTML] {base_url} home inaccessible : {e}")
        return []

    soup = BeautifulSoup(home.text, "html.parser")
    parsed_base = urlparse(base_url)

    article_urls: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url + "/", href)
        parsed = urlparse(full)
        if parsed.netloc != parsed_base.netloc:
            continue
        if any(x in parsed.path for x in ("/tag/", "/category/", "/wp-", "/auteur/", "/author/")):
            continue
        if parsed.path in ("", "/"):
            continue
        article_urls.add(full)

    articles: list[dict] = []
    for url in sorted(article_urls):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[HTML] {url} erreur fetch : {e} — skip")
            time.sleep(rate_limit)
            continue

        art_soup = BeautifulSoup(resp.text, "html.parser")

        title_node = art_soup.select_one(title_sel)
        if title_node is None:
            print(f"[HTML] {url} sélecteur title '{title_sel}' ne matche rien — skip")
            time.sleep(rate_limit)
            continue
        title = title_node.get_text(strip=True)

        date_val: str | None = None
        if date_sel:
            date_node = art_soup.select_one(date_sel)
            if date_node is not None:
                date_val = (
                    date_node.get("datetime")
                    or date_node.get_text(strip=True)
                    or None
                )

        content_node = art_soup.select_one(content_sel)
        if content_node is None:
            print(f"[HTML] {url} sélecteur content '{content_sel}' ne matche rien — skip")
            time.sleep(rate_limit)
            continue
        text = content_node.get_text("\n", strip=True)

        if date_val:
            date_only = date_val[:10]
            if date_only < since or date_only > until:
                time.sleep(rate_limit)
                continue

        articles.append({
            "url": url,
            "title": title,
            "date_published": date_val,
            "text_content": text,
            "language": entity["default_language"],
        })
        time.sleep(rate_limit)

    print(f"[HTML] {entity['entity_id']} : {len(articles)} article(s) collecté(s)")
    return articles


# Regex pré-compilée, extraction d'un message_id depuis un permalink
# Telegram (data-post="channel/123").
_TG_MSG_ID_RE = re.compile(r"/(\d+)$")


def fetch_telegram_channel(
    entity: dict,
    since: str,
    until: str,
) -> list[dict]:
    """Collecte via la vue web publique https://t.me/s/<channel>.

    Choix d'option A (cf. brief §7.2) : scraping t.me/s/<channel> pour les
    chaînes publiques. Pas besoin d'API Telegram ni de compte utilisateur,
    suffisant pour les 5 chaînes AI officielles + secondaires publiques.
    Option B (Telethon) reportée au brief 2 si besoin de chaînes privées.

    Pagination : ?before=<msg_id> avec le message_id le plus ancien de la
    page précédente. Arrêt sur (a) première page vide, (b) premier message
    antérieur à `since`, ou (c) garde-fou 50 pages (~1000 messages).

    Pas de détection automatique de langue (décision C doc 05) : on utilise
    entity['default_language']. Pour les versions RU/EN/AR d'une chaîne,
    créer des entités distinctes avec role='d3lta_validation'.
    """
    base_handle = entity["url"].rstrip("/")
    # Accepter les URLs t.me/... ou t.me/s/... en entrée : on force /s/.
    if "/s/" not in base_handle:
        parts = base_handle.rstrip("/").split("/")
        channel = parts[-1]
        base_handle = f"https://t.me/s/{channel}"

    rate_limit = entity.get("rate_limit_seconds", 2.0)
    lang = entity["default_language"]
    is_d3lta = 1 if entity.get("role") == "d3lta_validation" else 0

    articles: list[dict] = []
    seen_msg_ids: set[str] = set()
    before: str | None = None
    max_pages = 50
    pages_done = 0
    should_stop = False

    while pages_done < max_pages and not should_stop:
        url = base_handle if before is None else f"{base_handle}?before={before}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[TG] {url} erreur : {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        messages = soup.select(".tgme_widget_message")
        if not messages:
            break

        oldest_msg_id: str | None = None

        for msg in messages:
            data_post = msg.get("data-post", "")
            m = _TG_MSG_ID_RE.search(data_post)
            if not m:
                continue
            msg_id = m.group(1)
            if msg_id in seen_msg_ids:
                continue
            seen_msg_ids.add(msg_id)

            time_node = msg.select_one("time")
            date_val = time_node.get("datetime") if time_node else None

            text_node = msg.select_one(".tgme_widget_message_text")
            text = text_node.get_text("\n", strip=True) if text_node else ""

            if not text:
                # Posts image-seule ou média-seul : on saute (pas de contenu
                # textuel pour la classification DISARM).
                oldest_msg_id = msg_id
                continue

            if date_val:
                date_only = date_val[:10]
                if date_only < since:
                    should_stop = True
                    break
                if date_only > until:
                    oldest_msg_id = msg_id
                    continue

            msg_url = f"https://t.me/{data_post}" if data_post else url

            articles.append({
                "url": msg_url,
                "title": text[:120],
                "date_published": date_val,
                "text_content": text,
                "language": lang,
                "_is_duplicate_for_d3lta": is_d3lta,
            })
            oldest_msg_id = msg_id

        if oldest_msg_id is None:
            break
        before = oldest_msg_id
        pages_done += 1
        time.sleep(rate_limit)

    if pages_done >= max_pages:
        print(
            f"[TG] {entity['entity_id']} : garde-fou {max_pages} pages atteint — "
            "chaîne anormalement active ou détection de date défaillante."
        )

    print(f"[TG] {entity['entity_id']} : {len(articles)} message(s) collecté(s)")
    return articles


def fetch_manual_event(entity: dict, event_url: str) -> dict:
    """Collecte ponctuelle d'un événement (URL unique, ex. vidéo TikTok/FB).

    Extraction minimale via OpenGraph (og:title, og:description,
    article:published_time si présent). Le contenu détaillé est à compléter
    manuellement par Romain après insertion (update de text_content en DB).

    collection_mode='event' dans l'article résultant (vs 'scan' pour les
    autres collecteurs).
    """
    try:
        resp = requests.get(event_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"fetch_manual_event : {event_url} inaccessible : {e}")

    soup = BeautifulSoup(resp.text, "html.parser")

    def og(prop: str) -> str | None:
        node = soup.find("meta", property=prop)
        return node.get("content") if node and node.get("content") else None

    title = og("og:title") or (
        soup.find("title").get_text(strip=True) if soup.find("title") else ""
    )
    description = og("og:description") or ""
    date_val = og("article:published_time")

    # text_content non vide obligatoire (CHECK côté schéma). On remplit
    # avec la description OG — Romain remplacera par un verbatim transcrit
    # manuellement.
    text = description or f"[À COMPLÉTER MANUELLEMENT] Événement collecté depuis {event_url}"

    return {
        "url": event_url,
        "title": title or "[Titre à compléter]",
        "date_published": date_val,
        "text_content": text,
        "language": entity["default_language"],
    }


# === COUCHE ARCHIVAGE =====================================================

_WAYBACK_URL_RE = re.compile(r"https?://web\.archive\.org/web/\d+/\S+")


def archive_page_wayback(url: str, timeout: int = 60) -> str | None:
    """Soumet `url` à l'API Wayback (web.archive.org/save/) et retourne
    l'URL archivée, ou None si les 3 tentatives échouent.

    L'URL d'archive peut être exposée par Wayback de plusieurs façons
    selon le chemin (cas nominal, redirection, ou directement dans le
    body HTML du snapshot). On teste dans l'ordre :
      1. header Content-Location (cas nominal récent),
      2. header Location (redirection HTTP),
      3. parsing du body pour un lien /web/<timestamp>/...

    Gestion du 429 : on respecte Retry-After si présent, sinon backoff
    exponentiel 10s / 20s / 40s entre tentatives. Max 3 tentatives.
    """
    save_url = f"https://web.archive.org/save/{url}"
    backoffs = [10, 20, 40]

    for attempt in range(3):
        try:
            resp = requests.get(
                save_url, headers=HEADERS, timeout=timeout,
                allow_redirects=False,
            )
        except requests.RequestException as e:
            print(f"[WAYBACK] tentative {attempt+1} exception : {e}")
            if attempt < 2:
                time.sleep(backoffs[attempt])
            continue

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else backoffs[attempt]
            print(f"[WAYBACK] 429 — wait {wait}s")
            time.sleep(wait)
            continue

        # (1) Content-Location
        cl = resp.headers.get("Content-Location")
        if cl:
            if cl.startswith("/web/"):
                return f"https://web.archive.org{cl}"
            if cl.startswith("http"):
                return cl

        # (2) Location (redirection)
        loc = resp.headers.get("Location")
        if loc and "/web/" in loc:
            return loc if loc.startswith("http") else f"https://web.archive.org{loc}"

        # (3) parsing du body
        if resp.status_code in (200, 302):
            match = _WAYBACK_URL_RE.search(resp.text)
            if match:
                return match.group(0)

        print(
            f"[WAYBACK] tentative {attempt+1} — status={resp.status_code}, "
            f"body[:200]={resp.text[:200]!r}"
        )
        if attempt < 2:
            time.sleep(backoffs[attempt])

    return None


def archive_page_singlefile(
    url: str,
    entity_id: str,
    output_dir: str = "data/archives",
    browser_executable_path: str = config.SINGLEFILE_BROWSER_PATH,
) -> str | None:
    """Sauvegarde locale via le CLI single-file-cli.

    Chemin : <output_dir>/<entity_id>/<YYYY-MM-DD>/<sha256_url>.html. Le
    hash est calculé sur l'URL (pas sur le contenu) pour obtenir un nom
    déterministe avant même d'avoir téléchargé la page.

    Retourne None si le binaire `single-file` est absent ou si l'appel
    échoue.
    """
    date_segment = datetime.now().strftime("%Y-%m-%d")
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    out_dir = Path(output_dir) / entity_id / date_segment
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{url_hash}.html"

    try:
        result = subprocess.run(
            [
                "single-file",
                "--browser-executable-path", browser_executable_path,
                url,
                str(out_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        print(
            "[SINGLEFILE] binaire 'single-file' introuvable. "
            "Installer via : npm install -g single-file-cli"
        )
        return None
    except subprocess.TimeoutExpired:
        print(f"[SINGLEFILE] timeout 180s pour {url}")
        return None

    if result.returncode != 0 or not out_path.exists():
        print(
            f"[SINGLEFILE] échec {url} — rc={result.returncode} "
            f"stderr={result.stderr[:200]!r}"
        )
        return None

    return str(out_path)


def archive_page(url: str, entity: dict) -> tuple[str | None, str | None]:
    """Orchestre les deux archivages. Retourne (wayback_url, local_path).

    Règle méthodologique (doc 05 décision A) : si les DEUX archivages
    échouent, on lève ArchiveError — l'article n'est pas stocké. Si un
    seul échoue, on log et on continue avec None pour le champ manquant.
    """
    wb = archive_page_wayback(url)
    sf = archive_page_singlefile(url, entity["entity_id"])
    if wb is None and sf is None:
        raise ArchiveError(
            f"Archivage double échec pour {url} — "
            "aucune trace Wayback ni SingleFile. Article non stocké."
        )
    if wb is None:
        print(f"[ARCHIVE] {url} — Wayback échec, SingleFile OK")
    if sf is None:
        print(f"[ARCHIVE] {url} — SingleFile échec, Wayback OK")
    return (wb, sf)


# === COUCHE ORCHESTRATION ================================================

_COLLECTORS = {
    "wordpress_api": fetch_wordpress_api,
    "html_generic": fetch_html_site,
    "telegram_channel": fetch_telegram_channel,
}


def collect_entity(
    entity: dict,
    since: str,
    until: str,
    db_path: str = store_li.DEFAULT_DB_PATH,
) -> dict:
    """Collecte + archivage + pré-filtre + stockage pour une entité.

    - manual_event n'est PAS dispatché ici (il prend une event_url au lieu
      d'une fenêtre since/until) ; appeler collect_manual_event() à la place.
    - Retour : dict bilan exploitable depuis le CLI.
    """
    collector_name = entity["collector"]
    if collector_name == "manual_event":
        raise ValueError(
            "collect_entity ne gère pas manual_event. "
            "Utilisez collect_manual_event(entity, event_url, ...)."
        )
    fetcher = _COLLECTORS.get(collector_name)
    if fetcher is None:
        raise ValueError(f"Collector inconnu : {collector_name}")

    raw_articles = fetcher(entity, since, until)

    is_d3lta = 1 if entity.get("role") == "d3lta_validation" else 0
    stats = {
        "entity_id": entity["entity_id"],
        "collected": len(raw_articles),
        "stored": 0,
        "skipped_dedup": 0,
        "skipped_filter": 0,
        "archive_failures": 0,
    }

    for art in raw_articles:
        text = art["text_content"]
        h = _text_hash(text)

        if store_li.article_exists_by_hash(h, db_path):
            stats["skipped_dedup"] += 1
            continue

        passed, reason = config.passes_inclusion_filter(text, country=entity["country"], title=art.get("title"))

        try:
            wb_url, local_path = archive_page(art["url"], entity)
        except ArchiveError as e:
            print(f"[ORCH] {e}")
            stats["archive_failures"] += 1
            continue

        article_data = {
            "entity_id": entity["entity_id"],
            "url": art["url"],
            "title": art.get("title"),
            "date_published": art.get("date_published"),
            "collected_at": datetime.now().isoformat(),
            "language": art.get("language") or entity["default_language"],
            "text_content": text,
            "text_hash": h,
            "archive_wayback_url": wb_url,
            "archive_local_path": local_path,
            "collection_mode": "scan",
            # _is_duplicate_for_d3lta peut être fourni par le collecteur
            # Telegram ; sinon on retombe sur role.
            "is_duplicate_for_d3lta": art.get("_is_duplicate_for_d3lta", is_d3lta),
            "passes_inclusion_filter": 1 if passed else 0,
            "inclusion_filter_reason": reason,
        }

        inserted = store_li.insert_article(article_data, db_path)
        if inserted is None:
            # Race condition : un autre process a inséré entre le check et
            # l'insert. Compter comme dédup.
            stats["skipped_dedup"] += 1
        else:
            stats["stored"] += 1
            if not passed:
                stats["skipped_filter"] += 1

    return stats


def collect_manual_event(
    entity: dict,
    event_url: str,
    db_path: str = store_li.DEFAULT_DB_PATH,
) -> int | None:
    """Collecte d'un événement ponctuel. Retourne l'article_id inséré."""
    if entity["collector"] != "manual_event":
        raise ValueError(
            f"collect_manual_event : entité {entity['entity_id']} a "
            f"collector='{entity['collector']}', attendu 'manual_event'."
        )
    art = fetch_manual_event(entity, event_url)
    text = art["text_content"]
    h = _text_hash(text)
    if store_li.article_exists_by_hash(h, db_path):
        print(f"[EVENT] article déjà en DB (hash match) : {event_url}")
        return None

    passed, reason = config.passes_inclusion_filter(text, country=entity["country"], title=art.get("title"))
    wb_url, local_path = archive_page(event_url, entity)

    article_data = {
        "entity_id": entity["entity_id"],
        "url": event_url,
        "title": art["title"],
        "date_published": art.get("date_published"),
        "collected_at": datetime.now().isoformat(),
        "language": art.get("language") or entity["default_language"],
        "text_content": text,
        "text_hash": h,
        "archive_wayback_url": wb_url,
        "archive_local_path": local_path,
        "collection_mode": "event",
        "is_duplicate_for_d3lta": 1 if entity.get("role") == "d3lta_validation" else 0,
        "passes_inclusion_filter": 1 if passed else 0,
        "inclusion_filter_reason": reason,
    }
    return store_li.insert_article(article_data, db_path)


# === CLI ==================================================================

def _find_entity(entity_id: str, entities: list[dict]) -> dict:
    for e in entities:
        if e["entity_id"] == entity_id:
            return e
    raise SystemExit(
        f"entity_id '{entity_id}' introuvable. "
        f"Disponibles : {[e['entity_id'] for e in entities]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collecte P1 (WP / HTML / Telegram) d'une entité du corpus LI."
    )
    parser.add_argument(
        "entity_id", nargs="?",
        help="entity_id (slug) de l'entité à collecter. Si absent, prompt interactif.",
    )
    parser.add_argument(
        "--since", default=config.OBSERVATION_PERIOD["start"],
        help=f"Date de début YYYY-MM-DD (défaut : {config.OBSERVATION_PERIOD['start']})",
    )
    parser.add_argument(
        "--until", default=config.OBSERVATION_PERIOD["end"],
        help=f"Date de fin YYYY-MM-DD (défaut : {config.OBSERVATION_PERIOD['end']})",
    )
    parser.add_argument(
        "--db", default=store_li.DEFAULT_DB_PATH,
        help=f"Chemin de la base SQLite (défaut : {store_li.DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--entities-csv", default="data/entities.csv",
        help="Chemin de entities.csv",
    )
    args = parser.parse_args()

    store_li.init_db(args.db)
    store_li.import_entities_from_csv(args.entities_csv, args.db)
    entities = config.load_entities(args.entities_csv)
    if not entities:
        print(
            "Aucune entité active dans entities.csv. "
            "Retirer le '#' d'au moins une ligne d'exemple ou ajouter "
            "une entité réelle."
        )
        sys.exit(1)

    entity_id = args.entity_id or input("entity_id à collecter : ").strip()
    entity = _find_entity(entity_id, entities)

    if entity["collector"] == "manual_event":
        event_url = input("event_url : ").strip()
        aid = collect_manual_event(entity, event_url, args.db)
        print(f"Événement inséré : article_id={aid}")
        return

    stats = collect_entity(entity, args.since, args.until, args.db)
    print(f"Bilan : {stats}")


if __name__ == "__main__":
    main()
