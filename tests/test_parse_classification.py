"""Tests synthétiques du parseur de classification (AUCUN appel LLM).

Sorties texte fabriquées à la main. Compatible pytest (fonctions test_* + assert)
et exécutable de façon autonome (bloc __main__) car pytest n'est pas installé
dans le venv du projet. Pour la vraie sortie pytest : `pip install pytest` puis
`python -m pytest tests/test_parse_classification.py`.
"""

import json
import sys
from contextlib import contextmanager

sys.path.insert(0, ".")
from li.parse_classification import (  # noqa: E402
    parse_disarm_v42,
    parse_influence_ingerence,
    ClassificationParseError,
)


@contextmanager
def raises(exc_type):
    """Mini-substitut de pytest.raises pour exécution sans pytest."""
    try:
        yield
    except exc_type:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(
            f"exception {type(e).__name__} levée, attendu {exc_type.__name__}"
        ) from e
    raise AssertionError(f"aucune exception levée, attendu {exc_type.__name__}")


# ── Fixtures texte ───────────────────────────────────────────────────────────

DISARM_NOMINAL = """ORCHESTRATION: ORCHESTRÉE_ÉTRANGÈRE
DEGRÉ_ORCHESTRATION: FORT (indices textuels présents : 3+)
ÉNONCIATEUR: PRIMAIRE_DISTINCT_SECONDAIRE
TACTIQUE(S): TA02 - Plan Objectives ; TA14 - Develop Narratives
TECHNIQUE(S): T0002 - Facilitate State Propaganda / T0003 - Leverage Existing Narratives
PHRASES-PREUVES:
  - T0002 - Facilitate State Propaganda : "le partenariat avec la Russie garantit la souveraineté"
  - T0003 - Leverage Existing Narratives : "comme depuis des décennies, l'Occident pille le continent"
JUSTIFICATION DISARM: L'opération éditoriale relaie un narratif préexistant et facilite une propagande d'État.
CONFIANCE DISARM: HIGH
SAILLANCES: R=2 PA=0 SC=1 AES=2
JUSTIFICATION SAILLANCES: Éléments de langage Audinet (R), FCFA nommé (SC), figure présidentielle AES (AES).
AXES_NKILI: Anti-impérialisme=1 Efficacité sécuritaire=0 Partenariat=1 Économique=1 Identité-affect=0 Métadiscours informationnel=1
JUSTIFICATION AXES: Anti-impérialisme et partenariat AES-Russie, critique économique du FCFA, métadiscours sur la désinformation."""

DISARM_NON_APPLICABLE = """ORCHESTRATION: NON_ORCHESTRÉE
DEGRÉ_ORCHESTRATION: ABSENT (indices textuels présents : 0)
ÉNONCIATEUR: NON_APPLICABLE
TACTIQUE(S): NON_APPLICABLE
TECHNIQUE(S): NON_APPLICABLE
PHRASES-PREUVES: NON_APPLICABLE
JUSTIFICATION DISARM: Expression politique non-orchestrée d'un compte individuel local sans dispositif.
CONFIANCE DISARM: NON_APPLICABLE
SAILLANCES: R=0 PA=1 SC=0 AES=1
JUSTIFICATION SAILLANCES: Une figure panafricaine évoquée (PA), un marqueur identitaire national isolé (AES).
AXES_NKILI: Anti-impérialisme=0 Efficacité sécuritaire=0 Partenariat=0 Économique=0 Identité-affect=1 Métadiscours informationnel=0
JUSTIFICATION AXES: Registre identité-affect uniquement."""

INFLUENCE_NOMINAL = """STATUT: ingerence_caracterisee
JUSTIFICATION: Contenu trompeur diffusé via une infrastructure dont le caractère étranger est dissimulé. Diffusion artificielle observée.
CONFIANCE: MEDIUM"""


# ── 1. DISARM nominal complet ────────────────────────────────────────────────


def test_disarm_nominal_champ_a_champ():
    r = parse_disarm_v42(DISARM_NOMINAL)
    assert r["orchestration"] == "ORCHESTRÉE_ÉTRANGÈRE"
    assert r["degre_orchestration"] == "FORT"  # commentaire parenthésé retiré
    assert r["enonciateur"] == "PRIMAIRE_DISTINCT_SECONDAIRE"
    assert r["disarm_status"] == "classified"
    assert r["disarm_tactic_code"] == "TA02;TA14"
    assert r["disarm_tactic_name"] == "Plan Objectives;Develop Narratives"
    assert r["disarm_techniques"] == [
        {"code": "T0002", "nom": "Facilitate State Propaganda"},
        {"code": "T0003", "nom": "Leverage Existing Narratives"},
    ]
    # bloc phrases-preuves conservé tel quel (2 lignes, indentation)
    assert r["phrases_preuves"].count("\n") == 1
    assert "T0002 - Facilitate State Propaganda :" in r["phrases_preuves"]
    assert "  - T0003 - Leverage Existing Narratives :" in r["phrases_preuves"]
    assert r["disarm_justification"].startswith("L'opération éditoriale relaie")
    assert r["disarm_confidence"] == "HIGH"
    assert r["salience_russe"] == 2
    assert r["salience_panafricaniste"] == 0
    assert r["salience_souverainiste"] == 1
    assert r["salience_nationale_aes"] == 2
    assert r["salience_justification"].startswith("Éléments de langage Audinet")
    axes = json.loads(r["axes_lexicaux_nkili"])
    assert axes == {
        "Anti-impérialisme": 1,
        "Efficacité sécuritaire": 0,
        "Partenariat": 1,
        "Économique": 1,
        "Identité-affect": 0,
        "Métadiscours informationnel": 1,
    }
    assert r["axes_nkili_justification"].startswith("Anti-impérialisme et partenariat")


# ── 2. DISARM NON_APPLICABLE partout ─────────────────────────────────────────


def test_disarm_non_applicable():
    r = parse_disarm_v42(DISARM_NON_APPLICABLE)
    assert r["disarm_tactic_code"] is None
    assert r["disarm_tactic_name"] is None
    assert r["disarm_techniques"] is None
    assert r["phrases_preuves"] is None
    assert r["disarm_confidence"] is None
    assert r["disarm_status"] == "pas_technique_disarm"
    # saillances et axes restent notés indépendamment de DISARM
    assert r["salience_panafricaniste"] == 1
    assert r["salience_nationale_aes"] == 1
    axes = json.loads(r["axes_lexicaux_nkili"])
    assert axes["Identité-affect"] == 1
    assert axes["Anti-impérialisme"] == 0


# ── 3. DISARM malformé : label manquant (SAILLANCES) ─────────────────────────


def test_disarm_label_manquant_leve():
    texte = "\n".join(
        ligne
        for ligne in DISARM_NOMINAL.splitlines()
        if not ligne.startswith("SAILLANCES:")
    )
    with raises(ClassificationParseError):
        parse_disarm_v42(texte)


# ── 4. DISARM malformé : SAILLANCE hors domaine (R=3) ────────────────────────


def test_disarm_saillance_hors_domaine_leve():
    texte = DISARM_NOMINAL.replace(
        "SAILLANCES: R=2 PA=0 SC=1 AES=2",
        "SAILLANCES: R=3 PA=0 SC=1 AES=2",
    )
    with raises(ClassificationParseError):
        parse_disarm_v42(texte)


# ── 4bis. TECHNIQUE(S) : sous-technique Txxxx.xxx et item malformé ───────────


def test_disarm_techniques_sous_technique():
    texte = DISARM_NOMINAL.replace(
        "TECHNIQUE(S): T0002 - Facilitate State Propaganda / T0003 - Leverage Existing Narratives",
        "TECHNIQUE(S): T0097.108 - Expert Persona / T0143.002 - Fabricated Persona",
    )
    r = parse_disarm_v42(texte)
    # le point de la sous-technique est conservé dans le code
    assert r["disarm_techniques"] == [
        {"code": "T0097.108", "nom": "Expert Persona"},
        {"code": "T0143.002", "nom": "Fabricated Persona"},
    ]


def test_disarm_technique_malformee_leve():
    # 'T002' = 3 chiffres au lieu de 4 -> hors format strict
    texte = DISARM_NOMINAL.replace(
        "TECHNIQUE(S): T0002 - Facilitate State Propaganda / T0003 - Leverage Existing Narratives",
        "TECHNIQUE(S): T002 - Code Trop Court",
    )
    with raises(ClassificationParseError):
        parse_disarm_v42(texte)


# ── 5. AXES_NKILI : anti-régression du split sur labels à espaces ────────────


def test_axes_nkili_labels_a_espaces():
    texte = DISARM_NOMINAL.replace(
        "AXES_NKILI: Anti-impérialisme=1 Efficacité sécuritaire=0 Partenariat=1 "
        "Économique=1 Identité-affect=0 Métadiscours informationnel=1",
        "AXES_NKILI: Anti-impérialisme=0 Efficacité sécuritaire=1 Partenariat=0 "
        "Économique=1 Identité-affect=1 Métadiscours informationnel=0",
    )
    r = parse_disarm_v42(texte)
    axes = json.loads(r["axes_lexicaux_nkili"])
    # les 6 valeurs sont bien attribuées au bon label malgré les espaces internes
    assert axes["Anti-impérialisme"] == 0
    assert axes["Efficacité sécuritaire"] == 1
    assert axes["Partenariat"] == 0
    assert axes["Économique"] == 1
    assert axes["Identité-affect"] == 1
    assert axes["Métadiscours informationnel"] == 0
    assert len(axes) == 6


# ── 6. Influence/ingérence nominal ───────────────────────────────────────────


def test_influence_ingerence_nominal():
    r = parse_influence_ingerence(INFLUENCE_NOMINAL)
    assert r == {
        "influence_ingerence_status": "ingerence_caracterisee",
        "influence_ingerence_justification": (
            "Contenu trompeur diffusé via une infrastructure dont le caractère "
            "étranger est dissimulé. Diffusion artificielle observée."
        ),
        "influence_ingerence_confidence": "MEDIUM",
    }


# ── 7. Influence/ingérence STATUT inconnu ────────────────────────────────────


def test_influence_ingerence_statut_inconnu_leve():
    texte = INFLUENCE_NOMINAL.replace(
        "STATUT: ingerence_caracterisee",
        "STATUT: peut_etre_ingerence",
    )
    with raises(ClassificationParseError):
        parse_influence_ingerence(texte)


# ── Runner autonome (équivalent pytest, sans dépendance) ─────────────────────


def _main() -> int:
    tests = sorted(
        (name, obj)
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    )
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASSED  {name}")
        except Exception as e:  # noqa: BLE001
            failures.append((name, e))
            print(f"FAILED  {name}: {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - len(failures)} passed, {len(failures)} failed "
          f"(sur {len(tests)} tests)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
