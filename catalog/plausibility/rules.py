"""Règles de vraisemblance par champ.

Bornes larges à dessein : elles attrapent les erreurs d'unité et de virgule,
pas les erreurs subtiles — voir CLAUDE.md (section « Les règles de
plausibilité ») pour la table de référence.
"""

from __future__ import annotations

REGLES: dict[str, tuple[float, float]] = {
    "courant_repos_ma": (1, 2000),
    "puissance_poe_w": (1, 90),
    "angle_horizontal_deg": (1, 360),
    "capacite_batterie_ah": (0.8, 200),
    "nombre_zones_filaires": (1, 512),
    "portee_m": (0.5, 500),
}
