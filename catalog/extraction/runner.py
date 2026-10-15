"""Orchestration d'un lot d'extraction.

Découpage, appel modèle, plausibilité, stockage — un appel par bloc de
champs, jamais par type d'équipement complet.
"""

from __future__ import annotations


def executer_lot(fabricant: str) -> None:
    """Extrait tous les documents archivés et non encore extraits d'un fabricant."""
    raise NotImplementedError
