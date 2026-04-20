import os
import time
import json
from dotenv import load_dotenv
from anthropic import Anthropic


load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
DEFAULT_MODEL = "claude-opus-4-20250514"
MAX_RETRIES = 3

def call_claude(content, system_prompt):
    """Cette fonction envoie un contenu + un prompt système à l'API Claude. Elle retourne la réponse texte."""
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": content}]
            )
            return response.content[0].text
        
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"Erreur API(tentative{attempt + 1}/{MAX_RETRIES}):{e}")
                time.sleep(2 ** attempt)
            else: 
                print(f"Echec après {MAX_RETRIES} tentatives:{e}")
                return None

def batch_call_claude(items, system_prompt, delay=1.0):
    """Cette fonction appelle call_claude sur une liste d'items avec un délai entre chaque appel."""

    results = []
    total = len(items)

    for i, item in enumerate(items):
        print(f"Traitement {i + 1}/{total}...")

        result = call_claude(item, system_prompt)
        results.append({"input": item, "output": result})

        if i < total -1:
            time.sleep(delay)

    return results