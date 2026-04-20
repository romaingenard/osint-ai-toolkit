"""
li/detect.py - Collecte d'articles depuis les faux sites CopyCop/Storm-1516.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import os
import time


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }


def fetch_article(url: str) -> dict | None:
    """
    Récupère le contenu d'un article depuis une URL.
    Retourne un dict avec titre, date, texte, url - ou None si échec.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERREUR] {url} - {e}")
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Sans titre"

    time_tag = soup.find("time")
    date_str = time_tag.get("datetime", "") if time_tag else ""

    content_div = soup.find("div", class_="entry-content")
    if content_div:
        paragraphs = content_div.find_all("p") 
        text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    else:
        paragraphs = soup.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs)

    return {
        "url" : url,
        "title": title,
        "date" : date_str,
        "text": text,
        "collected_at": datetime.now().isoformat(),
    }

def fetch_site_articles(site_url: str, max_articles: int = 50) -> list[dict]:
    """
    Parcourt un site et collecte les articles via fetch_article
    Retourne une liste de dicts (un par article collecté).
    """
    print(f"\n[SCAN] {site_url} - recherche d'articles...")
    try:
        response = requests.get(site_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERREUR] {site_url} - {e}")
        return []
    soup = BeautifulSoup(response.text, "html.parser")

    links = soup.find_all("a", href=True)
    article_urls = set()
    for link in links:
        href = link["href"]
        if href.startswith("/") and len(href) > 1:
            href = site_url.rstrip("/") + href
        if href.startswith(site_url) and href != site_url and href != site_url + "/":
            if "/wp-" not in href and "/tag/" not in href and "/category/" not in href:
                article_urls.add(href)

    print(f"[INFO] {len(article_urls)} URLs d'articles trouvées.")

    articles = []
    for i, url in enumerate(list(article_urls)[:max_articles]):
        print(f" [{i+1}/{min(len(article_urls), max_articles)}] {url}")
        article = fetch_article(url)
        if article:
            articles.append(article)
        time.sleep(1)
    return articles
    

def save_articles(articles: list[dict], output_dir: str = "data/li_corpus") -> str:
    """ Sauvegarde les articles collectés en JSON. Retourne le chemin du fichier."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n[SAUVEGARDE] {len(articles)} articles → {filepath}")
    return filepath


if __name__ == "__main__":
    site = input("URL du site à scanner : ")
    articles = fetch_site_articles(site)
    if articles:
        filepath = save_articles(articles)
        print(f"Terminé. {len(articles)} articles sauvegardés.")
    else:
        print("Aucun article collecté.")

