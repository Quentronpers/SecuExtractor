"""Export du catalogue : tous les champs, avec leur niveau de fiabilité.

Prévu, pas encore construit. Voir docs/pipeline.md (§ 7, « L'export ») pour
le format de sortie. Rien
n'attend la relecture : les champs ``extrait`` sont exportés au même titre
que les champs ``verifie``, avec leur niveau porté explicitement.
"""

from __future__ import annotations

from pathlib import Path


def exporter(chemin_sortie: Path) -> None:
    """Écrit le catalogue complet au format JSON documenté."""
    raise NotImplementedError
