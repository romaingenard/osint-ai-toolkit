"""Parsing strict des sorties de classification (DISARM v4.2 + influence/ingérence).

Deux appels LLM par article produisent des sorties texte à format imposé :
- DISARM v4.2 : cf. li/config.py, DISARM_PROMPT_V42 (format lignes 904-921).
- Influence/ingérence : cf. li/config.py, INFLUENCE_INGERENCE_PROMPT.

Ce module convertit ces sorties en dicts dont les clés sont les noms de colonnes
cibles de la table `classifications`.

Mode STRICT : tout label attendu manquant ou toute valeur d'enum hors domaine
lève ClassificationParseError. Aucun remplissage silencieux par NULL : None est
réservé aux NON_APPLICABLE explicites. L'appelant met l'article en file d'échecs
plutôt que d'insérer une ligne partielle.

Sérialisation axes_lexicaux_nkili : JSON compact, ensure_ascii=False, clés =
les 6 labels d'axes EXACTS du prompt (accents et espaces inclus), valeurs 0/1.
Exemple : {"Anti-impérialisme": 1, "Efficacité sécuritaire": 0, ...}
"""

from __future__ import annotations

import json
import re


class ClassificationParseError(Exception):
    """Sortie de classification non conforme au format strict attendu."""


# ── Domaines d'enums (alignés sur les CHECK de la table classifications) ──────

ORCHESTRATION_VALUES = {
    "ORCHESTRÉE_ÉTRANGÈRE",
    "ORCHESTRÉE_DOMESTIQUE",
    "NON_ORCHESTRÉE",
    "TECHNIQUE_INVOLONTAIRE",
}
DEGRE_ORCHESTRATION_VALUES = {"FORT", "MOYEN", "FAIBLE", "ABSENT"}
ENONCIATEUR_VALUES = {
    "PRIMAIRE_DISTINCT_SECONDAIRE",
    "PRIMAIRE_SECONDAIRE_CONFONDUS",
    "NON_APPLICABLE",
}
# CHECK table : disarm_confidence ∈ {HIGH, MEDIUM, LOW}. NON_APPLICABLE -> None.
CONFIANCE_VALUES = {"HIGH", "MEDIUM", "LOW"}
SALIENCE_VALUES = {0, 1, 2}
AXE_VALUES = {0, 1}

# Ordre stable des 6 axes Nkili — labels EXACTS du prompt (accents/espaces inclus).
# La présence d'espaces dans 3 labels impose un découpage par label connu, pas par
# espace (cf. piège AXES_NKILI).
AXES_NKILI_LABELS = [
    "Anti-impérialisme",
    "Efficacité sécuritaire",
    "Partenariat",
    "Économique",
    "Identité-affect",
    "Métadiscours informationnel",
]

# CHECK table : influence_ingerence_status ∈ {…}.
INFLUENCE_STATUT_VALUES = {
    "influence_legitime",
    "ingerence_caracterisee",
    "zone_grise",
}

# ── Labels attendus, dans l'ordre du prompt (accents exacts) ─────────────────

_DISARM_LABELS = [
    "ORCHESTRATION:",
    "DEGRÉ_ORCHESTRATION:",
    "ÉNONCIATEUR:",
    "TACTIQUE(S):",
    "TECHNIQUE(S):",
    "PHRASES-PREUVES:",
    "JUSTIFICATION DISARM:",
    "CONFIANCE DISARM:",
    "SAILLANCES:",
    "JUSTIFICATION SAILLANCES:",
    "AXES_NKILI:",
    "JUSTIFICATION AXES:",
]
_INFLUENCE_LABELS = ["STATUT:", "JUSTIFICATION:", "CONFIANCE:"]


# ── Découpage générique par labels ───────────────────────────────────────────


def _split_by_labels(raw_text: str, labels: list[str]) -> dict[str, str]:
    """Découpe raw_text en {label: contenu} pour les labels reconnus.

    Une ligne est une ligne-label quand, après strip, elle commence par l'un des
    labels connus. Le contenu d'un label = le reste de sa ligne + toutes les
    lignes suivantes jusqu'au prochain label reconnu (permet les blocs
    multi-lignes : PHRASES-PREUVES, justifications). En cas d'ambiguïté de
    préfixe, le label le plus long l'emporte. Première occurrence conservée.
    """
    if not isinstance(raw_text, str):
        raise ClassificationParseError(
            f"raw_text doit être une chaîne, reçu {type(raw_text).__name__}"
        )
    lines = raw_text.splitlines()
    found = []  # (index_ligne, label, contenu_inline)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        matches = [lab for lab in labels if stripped.startswith(lab)]
        if not matches:
            continue
        label = max(matches, key=len)
        inline = stripped[len(label):].strip()
        found.append((idx, label, inline))

    result: dict[str, str] = {}
    for i, (idx, label, inline) in enumerate(found):
        next_idx = found[i + 1][0] if i + 1 < len(found) else len(lines)
        block = "\n".join(lines[idx + 1:next_idx])
        if inline and block:
            content = inline + "\n" + block
        elif inline:
            content = inline
        else:
            content = block
        if label not in result:  # première occurrence prioritaire
            result[label] = content.strip("\n")
    return result


def _require(fields: dict[str, str], label: str) -> str:
    if label not in fields:
        raise ClassificationParseError(f"Label attendu manquant : {label!r}")
    return fields[label]


# ── Sous-parseurs spécialisés ────────────────────────────────────────────────


def _parse_tactiques(raw: str) -> tuple[str | None, str | None]:
    """'TAxx - Nom ; TAyy - Nom' -> ('TAxx;TAyy', 'Nom;Nom'). NON_APPLICABLE -> (None, None)."""
    if raw == "NON_APPLICABLE":
        return None, None
    codes, names = [], []
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        m = re.match(r"^(TA\d{2})\s*-\s*(.+)$", item)
        if not m:
            raise ClassificationParseError(
                f"TACTIQUE mal formée : {item!r} (attendu 'TAxx - Nom')"
            )
        codes.append(m.group(1))
        names.append(m.group(2).strip())
    if not codes:
        raise ClassificationParseError(
            "TACTIQUE(S) ni NON_APPLICABLE ni tactique valide après parsing"
        )
    return ";".join(codes), ";".join(names)


def _parse_techniques(raw: str) -> list[dict] | None:
    """'Txxxx - Nom / Txxxx.xxx - Nom' -> [{'code': 'Txxxx', 'nom': '...'}, ...].

    NON_APPLICABLE -> None (pas []). Codes acceptés : Txxxx (4 chiffres) ou
    sous-technique Txxxx.xxx (point + 3 chiffres). Tout item hors format lève
    ClassificationParseError. La liste est destinée au champ JSON
    disarm_techniques de la table (sérialisé par insert_classification).
    """
    if raw == "NON_APPLICABLE":
        return None
    techniques: list[dict] = []
    for item in raw.split("/"):
        item = item.strip()
        if not item:
            continue
        m = re.match(r"^(T\d{4}(?:\.\d{3})?)\s*-\s*(.+)$", item)
        if not m:
            raise ClassificationParseError(
                f"TECHNIQUE mal formée : {item!r} "
                "(attendu 'Txxxx - Nom' ou 'Txxxx.xxx - Nom')"
            )
        techniques.append({"code": m.group(1), "nom": m.group(2).strip()})
    if not techniques:
        raise ClassificationParseError(
            "TECHNIQUE(S) ni NON_APPLICABLE ni technique valide après parsing"
        )
    return techniques


def _parse_saillances(raw: str) -> dict[str, int]:
    """'R=2 PA=0 SC=1 AES=2' -> {colonne: int}. Valeurs validées ∈ {0,1,2}."""
    mapping = {
        "R": "salience_russe",
        "PA": "salience_panafricaniste",
        "SC": "salience_souverainiste",
        "AES": "salience_nationale_aes",
    }
    out: dict[str, int] = {}
    for token, col in mapping.items():
        m = re.search(rf"(?:^|\s){token}=\s*(\S+)", raw)
        if not m:
            raise ClassificationParseError(
                f"SAILLANCES : token {token}= absent dans {raw!r}"
            )
        val_str = m.group(1)
        if not re.fullmatch(r"\d+", val_str):
            raise ClassificationParseError(
                f"SAILLANCES {token}= valeur non entière : {val_str!r}"
            )
        val = int(val_str)
        if val not in SALIENCE_VALUES:
            raise ClassificationParseError(
                f"SAILLANCES {token}= hors domaine {sorted(SALIENCE_VALUES)} : {val}"
            )
        out[col] = val
    return out


def _parse_axes_nkili(raw: str) -> dict[str, int]:
    """Découpe sur les 6 labels connus (pas sur l'espace). Valeurs validées ∈ {0,1}."""
    out: dict[str, int] = {}
    for label in AXES_NKILI_LABELS:
        m = re.search(re.escape(label) + r"=\s*(\S+)", raw)
        if not m:
            raise ClassificationParseError(
                f"AXES_NKILI : axe {label!r} absent dans {raw!r}"
            )
        digit = re.match(r"\d+", m.group(1))
        if not digit:
            raise ClassificationParseError(
                f"AXES_NKILI : axe {label!r} valeur non entière : {m.group(1)!r}"
            )
        val = int(digit.group(0))
        if val not in AXE_VALUES:
            raise ClassificationParseError(
                f"AXES_NKILI : axe {label!r} hors domaine {sorted(AXE_VALUES)} : {val}"
            )
        out[label] = val
    return out


# ── Parseur appel 1 : DISARM v4.2 ────────────────────────────────────────────


def parse_disarm_v42(raw_text: str) -> dict:
    """Parse la sortie de l'appel DISARM v4.2 vers un dict {colonne: valeur}.

    Mode strict : lève ClassificationParseError sur label manquant ou enum hors
    domaine. NON_APPLICABLE -> None pour tactiques/techniques/phrases/confiance.
    """
    fields = _split_by_labels(raw_text, _DISARM_LABELS)

    # 1. ORCHESTRATION
    orchestration = _require(fields, "ORCHESTRATION:").strip()
    if orchestration not in ORCHESTRATION_VALUES:
        raise ClassificationParseError(
            f"ORCHESTRATION hors domaine : {orchestration!r} "
            f"(attendu parmi {sorted(ORCHESTRATION_VALUES)})"
        )

    # 2. DEGRÉ_ORCHESTRATION — enum + commentaire parenthésé à ignorer
    degre_raw = _require(fields, "DEGRÉ_ORCHESTRATION:").strip()
    degre = degre_raw.split("(", 1)[0].strip()
    if degre not in DEGRE_ORCHESTRATION_VALUES:
        raise ClassificationParseError(
            f"DEGRÉ_ORCHESTRATION hors domaine : {degre!r} (ligne brute {degre_raw!r})"
        )

    # 3. ÉNONCIATEUR
    enonciateur = _require(fields, "ÉNONCIATEUR:").strip()
    if enonciateur not in ENONCIATEUR_VALUES:
        raise ClassificationParseError(
            f"ÉNONCIATEUR hors domaine : {enonciateur!r}"
        )

    # 4. TACTIQUE(S) -> code(s) + nom(s)
    tactic_code, tactic_name = _parse_tactiques(
        _require(fields, "TACTIQUE(S):").strip()
    )

    # 5. TECHNIQUE(S) -> liste de dicts [{"code","nom"}] (NON_APPLICABLE -> None).
    #    Le store sérialise cette liste en JSON ; on ne renvoie donc pas une chaîne.
    disarm_techniques = _parse_techniques(_require(fields, "TECHNIQUE(S):").strip())

    # 6. PHRASES-PREUVES (bloc multi-ligne brut, indentation conservée)
    phrases_block = _require(fields, "PHRASES-PREUVES:")
    phrases_preuves = (
        None if phrases_block.strip() == "NON_APPLICABLE" else phrases_block
    )

    # 7. JUSTIFICATION DISARM
    disarm_justification = _require(fields, "JUSTIFICATION DISARM:").strip()

    # 8. CONFIANCE DISARM (NON_APPLICABLE -> None)
    confiance_raw = _require(fields, "CONFIANCE DISARM:").strip()
    if confiance_raw == "NON_APPLICABLE":
        disarm_confidence = None
    elif confiance_raw in CONFIANCE_VALUES:
        disarm_confidence = confiance_raw
    else:
        raise ClassificationParseError(
            f"CONFIANCE DISARM hors domaine : {confiance_raw!r} "
            f"(attendu {sorted(CONFIANCE_VALUES)} ou NON_APPLICABLE)"
        )

    # 9. SAILLANCES
    saliences = _parse_saillances(_require(fields, "SAILLANCES:").strip())

    # 10. JUSTIFICATION SAILLANCES
    salience_justification = _require(fields, "JUSTIFICATION SAILLANCES:").strip()

    # 11. AXES_NKILI -> JSON compact
    axes = _parse_axes_nkili(_require(fields, "AXES_NKILI:").strip())
    axes_lexicaux_nkili = json.dumps(axes, ensure_ascii=False)

    # 12. JUSTIFICATION AXES
    axes_nkili_justification = _require(fields, "JUSTIFICATION AXES:").strip()

    # Champ dérivé : disarm_status
    if tactic_code is None:  # TACTIQUE(S) == NON_APPLICABLE
        if orchestration in {"NON_ORCHESTRÉE", "TECHNIQUE_INVOLONTAIRE"}:
            disarm_status = "pas_technique_disarm"
        else:
            raise ClassificationParseError(
                "Incohérence : TACTIQUE(S)=NON_APPLICABLE mais "
                f"ORCHESTRATION={orchestration!r} (orchestration avérée sans tactique). "
                "Hors des règles de dérivation de disarm_status."
            )
    else:
        disarm_status = "classified"

    return {
        "orchestration": orchestration,
        "degre_orchestration": degre,
        "enonciateur": enonciateur,
        "disarm_status": disarm_status,
        "disarm_tactic_code": tactic_code,
        "disarm_tactic_name": tactic_name,
        "disarm_techniques": disarm_techniques,
        "phrases_preuves": phrases_preuves,
        "disarm_justification": disarm_justification,
        "disarm_confidence": disarm_confidence,
        "salience_russe": saliences["salience_russe"],
        "salience_panafricaniste": saliences["salience_panafricaniste"],
        "salience_souverainiste": saliences["salience_souverainiste"],
        "salience_nationale_aes": saliences["salience_nationale_aes"],
        "salience_justification": salience_justification,
        "axes_lexicaux_nkili": axes_lexicaux_nkili,
        "axes_nkili_justification": axes_nkili_justification,
    }


# ── Parseur appel 2 : influence/ingérence ────────────────────────────────────


def parse_influence_ingerence(raw_text: str) -> dict:
    """Parse la sortie de l'appel influence/ingérence vers un dict {colonne: valeur}.

    Mode strict : lève ClassificationParseError sur label manquant ou enum hors
    domaine.
    """
    fields = _split_by_labels(raw_text, _INFLUENCE_LABELS)

    statut = _require(fields, "STATUT:").strip()
    if statut not in INFLUENCE_STATUT_VALUES:
        raise ClassificationParseError(
            f"STATUT hors domaine : {statut!r} "
            f"(attendu {sorted(INFLUENCE_STATUT_VALUES)})"
        )

    justification = _require(fields, "JUSTIFICATION:").strip()

    confiance = _require(fields, "CONFIANCE:").strip()
    if confiance not in CONFIANCE_VALUES:
        raise ClassificationParseError(
            f"CONFIANCE hors domaine : {confiance!r} (attendu {sorted(CONFIANCE_VALUES)})"
        )

    return {
        "influence_ingerence_status": statut,
        "influence_ingerence_justification": justification,
        "influence_ingerence_confidence": confiance,
    }
