"""Gabarits de prompt par famille d'équipement et par bloc.

Règles non négociables à rappeler dans chaque gabarit : citation obligatoire,
jamais d'inférence, valeur maximale en cas d'ambiguïté PoE, plages conservées
telles quelles — voir CLAUDE.md (section « Règles d'extraction »).
"""

from __future__ import annotations


def gabarit(famille: str, bloc: str) -> str:
    """Retourne le gabarit de prompt pour une famille d'équipement et un bloc."""
    raise NotImplementedError
