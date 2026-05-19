"""core/analyze.py — wrapper Anthropic + parsing des réponses LI + Centaure.

Refonte : 24 avril 2026. Adaptations pour le rapport "Narratifs anti-français
au Sahel 2025-2026" :
- modèle par défaut mis à jour (Sonnet 4.6 pour le volume, Opus 4.7 pour les
  pilotes Centaure),
- prompt caching activé par défaut (cache_control: ephemeral sur le bloc
  système stable),
- parseurs dédiés pour chaque prompt (DISARM / saillances / influence),
- fonction de comparaison manual vs llm pour la méthode Centaure.
"""

import os
import re
import time

from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Modèles par défaut. Décision brief 2bis v2 (19/05/2026) : bascule complète
# sur Opus 4.7 pour la classification DISARM v4.2 (~7300 mots prompt système).
# Le prompt caching (cache_control: ephemeral) amortit le coût du bloc
# système stable sur les appels successifs.
# Sonnet 4.6 conservé comme alternative volume (à activer manuellement si
# nécessaire pour absorber un pic de classifications post-collecte).
DEFAULT_MODEL_VOLUME = "claude-sonnet-4-6"
DEFAULT_MODEL_HIGH_QUALITY = "claude-opus-4-7"
DEFAULT_MODEL = DEFAULT_MODEL_HIGH_QUALITY

MAX_RETRIES = 3


def call_claude(
    content: str,
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    cache_system: bool = True,
    max_tokens: int = 4096,
):
    """Envoie content + system_prompt à l'API Messages. Retourne le texte.

    Prompt caching (cache_system=True, défaut) : le system_prompt est
    encodé en `[{"type":"text","text":..., "cache_control":{"type":"ephemeral"}}]`.
    Le bloc est mis en cache côté Anthropic pour 5 minutes (TTL par
    défaut). Vérifié contre la doc officielle le 24 avril 2026 :
    - format exigé : list[dict] pour `system`,
    - pas de header beta requis sur Sonnet 4.6 / Opus 4.7,
    - usage du cache exposé dans response.usage.cache_read_input_tokens
      et cache_creation_input_tokens (non exploité ici mais disponible).
    """
    if cache_system:
        system_arg = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    else:
        system_arg = system_prompt

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_arg,
                messages=[{"role": "user", "content": content}],
            )
            return response.content[0].text

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"Erreur API (tentative {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(2 ** attempt)
            else:
                print(f"Échec après {MAX_RETRIES} tentatives: {e}")
                return None


def batch_call_claude(
    items,
    system_prompt,
    model: str = DEFAULT_MODEL,
    cache_system: bool = True,
    delay: float = 1.0,
):
    """Appelle call_claude sur une liste d'items avec délai inter-appel.

    Avec cache_system=True et model fixe, le system_prompt (long) n'est
    facturé plein tarif que pour le premier appel ; les suivants bénéficient
    du tarif cache hit tant que les appels s'enchaînent sous 5 minutes.
    """
    results = []
    total = len(items)

    for i, item in enumerate(items):
        print(f"Traitement {i + 1}/{total}...")

        result = call_claude(
            item, system_prompt, model=model, cache_system=cache_system
        )
        results.append({"input": item, "output": result})

        if i < total - 1:
            time.sleep(delay)

    return results


# === PARSEURS RÉPONSES LI =================================================

# Regex compilées une fois. Parsing défensif : on ne lève pas d'exception
# si la réponse s'écarte du format — on renvoie autant de champs parsables
# que possible et la réponse brute dans `raw`.

_TACTIC_RE = re.compile(r"^TACTIQUE:\s*(TA\d+)\s*-\s*(.+)$", re.MULTILINE)
_TECHNIQUES_RE = re.compile(r"^TECHNIQUE\(S\):\s*(.+)$", re.MULTILINE)
_JUSTIF_RE = re.compile(r"^JUSTIFICATION:\s*(.+)$", re.MULTILINE)
_CONFIANCE_RE = re.compile(r"^CONFIANCE:\s*(HIGH|MEDIUM|LOW)", re.MULTILINE | re.IGNORECASE)
_HORS_SCOPE_RE = re.compile(r"HORS_SCOPE\s*:\s*(.+)", re.IGNORECASE)
_PAS_DISARM_RE = re.compile(r"PAS UNE TECHNIQUE DISARM", re.IGNORECASE)
_TECHNIQUE_ITEM_RE = re.compile(r"(T\d+(?:\.\d+)?)\s*-\s*([^/]+?)(?=\s*/|\s*$)")


def parse_disarm_response(response_text: str) -> dict:
    """Parse la réponse structurée du prompt DISARM.

    Retour : dict avec status + champs selon le status.
    - status='hors_scope' : raison dans 'justification', reste à None.
    - status='pas_technique_disarm' : justification dans 'justification'.
    - status='classified' : tactic_code/name, techniques (liste),
      justification, confidence.
    - 'raw' contient toujours la réponse brute.
    """
    result: dict = {
        "status": None,
        "tactic_code": None,
        "tactic_name": None,
        "techniques": None,
        "justification": None,
        "confidence": None,
        "raw": response_text,
    }

    if response_text is None:
        return result

    hors = _HORS_SCOPE_RE.search(response_text)
    if hors:
        result["status"] = "hors_scope"
        result["justification"] = hors.group(1).strip()
        return result

    if _PAS_DISARM_RE.search(response_text):
        result["status"] = "pas_technique_disarm"
        # Extraire la justification si le format l'a mise sur une ligne
        # JUSTIFICATION:, sinon prendre le reste de la ligne.
        j = _JUSTIF_RE.search(response_text)
        if j:
            result["justification"] = j.group(1).strip()
        return result

    tactic = _TACTIC_RE.search(response_text)
    if tactic:
        result["status"] = "classified"
        result["tactic_code"] = tactic.group(1).strip()
        result["tactic_name"] = tactic.group(2).strip()

    techs = _TECHNIQUES_RE.search(response_text)
    if techs:
        line = techs.group(1).strip()
        parsed = []
        # Découper sur " / " puis extraire code - name.
        for chunk in line.split("/"):
            m = re.match(r"\s*(T\d+(?:\.\d+)?)\s*-\s*(.+?)\s*$", chunk)
            if m:
                parsed.append({"code": m.group(1), "name": m.group(2).strip()})
        result["techniques"] = parsed if parsed else None

    j = _JUSTIF_RE.search(response_text)
    if j:
        result["justification"] = j.group(1).strip()

    c = _CONFIANCE_RE.search(response_text)
    if c:
        result["confidence"] = c.group(1).upper()

    return result


_SALIENCE_RE = {
    "salience_russe": re.compile(r"^SAILLANCE_RUSSE:\s*([012])", re.MULTILINE),
    "salience_panafricaniste": re.compile(r"^SAILLANCE_PANAFRICANISTE:\s*([012])", re.MULTILINE),
    "salience_souverainiste": re.compile(r"^SAILLANCE_SOUVERAINISTE:\s*([012])", re.MULTILINE),
    "salience_nationale_aes": re.compile(r"^SAILLANCE_NATIONALE_AES:\s*([012])", re.MULTILINE),
}


def parse_salience_response(response_text: str) -> dict:
    """Parse la réponse du prompt SAILLANCES (4 scores 0/1/2 + justif)."""
    result: dict = {
        "salience_russe": None,
        "salience_panafricaniste": None,
        "salience_souverainiste": None,
        "salience_nationale_aes": None,
        "justification": None,
        "raw": response_text,
    }
    if response_text is None:
        return result

    for key, pattern in _SALIENCE_RE.items():
        m = pattern.search(response_text)
        if m:
            result[key] = int(m.group(1))

    j = _JUSTIF_RE.search(response_text)
    if j:
        result["justification"] = j.group(1).strip()

    return result


_STATUT_RE = re.compile(
    r"^STATUT:\s*(influence_legitime|ingerence_caracterisee|zone_grise)",
    re.MULTILINE | re.IGNORECASE,
)


def parse_influence_ingerence_response(response_text: str) -> dict:
    """Parse la réponse du prompt INFLUENCE/INGERENCE."""
    result: dict = {
        "status": None,
        "justification": None,
        "confidence": None,
        "raw": response_text,
    }
    if response_text is None:
        return result

    s = _STATUT_RE.search(response_text)
    if s:
        result["status"] = s.group(1).lower()

    j = _JUSTIF_RE.search(response_text)
    if j:
        result["justification"] = j.group(1).strip()

    c = _CONFIANCE_RE.search(response_text)
    if c:
        result["confidence"] = c.group(1).upper()

    return result


# === MÉTHODE CENTAURE =====================================================

def compare_classifications(manual: dict, llm: dict) -> dict:
    """Compare une classif humaine et une classif LLM (Mollick 2024).

    Retourne un dict avec :
    - tactic_agreement : bool, même disarm_tactic_code ?
    - techniques_jaccard : float, Jaccard des codes techniques (0 si un
      des deux côtés n'a pas de techniques listées).
    - salience_distances : dict avec écart absolu sur chacun des 4 scores,
      None pour un axe si l'un des deux n'a pas été scoré.
    - status_agreement : bool, même influence_ingerence_status ?
    - overall_agreement_score : moyenne pondérée dans [0, 1].
    - divergences : list[str], description de chaque divergence.

    Les clés attendues dans manual/llm suivent le schéma de la table
    `classifications` de store_li : disarm_tactic_code, disarm_techniques
    (liste de dicts {'code','name'}), salience_*, influence_ingerence_status.
    """
    result: dict = {
        "tactic_agreement": False,
        "techniques_jaccard": 0.0,
        "salience_distances": {},
        "status_agreement": False,
        "overall_agreement_score": 0.0,
        "divergences": [],
    }

    # Tactique DISARM
    m_tac = manual.get("disarm_tactic_code")
    l_tac = llm.get("disarm_tactic_code")
    result["tactic_agreement"] = (m_tac is not None and m_tac == l_tac)
    if not result["tactic_agreement"]:
        result["divergences"].append(
            f"tactique DISARM : manual={m_tac!r} vs llm={l_tac!r}"
        )

    # Techniques : Jaccard sur l'ensemble des codes.
    def codes(classif: dict) -> set[str]:
        techs = classif.get("disarm_techniques") or []
        return {t["code"] for t in techs if isinstance(t, dict) and "code" in t}

    m_codes = codes(manual)
    l_codes = codes(llm)
    if m_codes or l_codes:
        inter = m_codes & l_codes
        union = m_codes | l_codes
        result["techniques_jaccard"] = len(inter) / len(union) if union else 0.0
        if m_codes != l_codes:
            only_m = m_codes - l_codes
            only_l = l_codes - m_codes
            result["divergences"].append(
                f"techniques : seulement manual={sorted(only_m)}, "
                f"seulement llm={sorted(only_l)}"
            )

    # Distances de saillance.
    for axis in (
        "salience_russe",
        "salience_panafricaniste",
        "salience_souverainiste",
        "salience_nationale_aes",
    ):
        mv = manual.get(axis)
        lv = llm.get(axis)
        if mv is None or lv is None:
            result["salience_distances"][axis] = None
        else:
            dist = abs(mv - lv)
            result["salience_distances"][axis] = dist
            if dist > 0:
                result["divergences"].append(
                    f"{axis} : manual={mv} vs llm={lv} (écart {dist})"
                )

    # Statut influence/ingérence.
    m_st = manual.get("influence_ingerence_status")
    l_st = llm.get("influence_ingerence_status")
    result["status_agreement"] = (m_st is not None and m_st == l_st)
    if not result["status_agreement"]:
        result["divergences"].append(
            f"statut influence : manual={m_st!r} vs llm={l_st!r}"
        )

    # Score global : moyenne pondérée.
    # Pondération : tactique 0.25, techniques 0.25, saillances 0.30 (total
    # normalisé sur les axes scorés), statut 0.20.
    components: list[tuple[float, float]] = []
    components.append((1.0 if result["tactic_agreement"] else 0.0, 0.25))
    components.append((result["techniques_jaccard"], 0.25))

    sal_scores = [
        1.0 - (d / 2.0)
        for d in result["salience_distances"].values()
        if d is not None
    ]
    if sal_scores:
        components.append((sum(sal_scores) / len(sal_scores), 0.30))

    components.append((1.0 if result["status_agreement"] else 0.0, 0.20))

    total_w = sum(w for _, w in components)
    if total_w > 0:
        result["overall_agreement_score"] = round(
            sum(s * w for s, w in components) / total_w, 3
        )

    return result


# TODO (brief 2, S7 si volume > 500 classifications) :
# Migrer batch_call_claude vers l'API Batch d'Anthropic (coût divisé par 2).
# Documentation : https://docs.claude.com/en/docs/build-with-claude/batch-processing
# Pertinent quand le corpus complet sera classifié (30-45 entités ×
# plusieurs articles × 3 prompts).
