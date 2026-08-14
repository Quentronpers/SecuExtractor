"""Découpage d'un document lu en sections exploitables par bloc d'extraction.

Blocs typiques : identification, alimentation, environnement, physique,
metier, accessoires — voir CLAUDE.md (section « Le découpage en blocs »).
"""

from __future__ import annotations


def decouper(texte: str) -> dict[str, str]:
    """Associe à chaque bloc connu la portion de texte qui le concerne."""
    raise NotImplementedError
