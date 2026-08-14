"""Application des règles de plausibilité à un champ extrait.

Détermine si un champ passe en état ``sur`` ou ``douteux`` — voir
catalog/plausibility/rules.py pour les bornes.
"""

from __future__ import annotations

from catalog.models import EtatExtraction


def verifier(nom_champ: str, valeur: float) -> EtatExtraction:
    """Applique la règle de plausibilité connue pour ce champ, si elle existe."""
    raise NotImplementedError
