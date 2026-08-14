"""Recherche du site officiel, des pages catalogue et des pages produit.

Chaque échec est journalisé dans data/sources/echecs.json plutôt que
silencieux — voir CLAUDE.md (section « L'acquisition »).
"""

from __future__ import annotations


def discover_site(fabricant: str) -> str | None:
    """Cherche le site officiel d'un fabricant."""
    raise NotImplementedError


def discover_product_pages(site_url: str) -> list[str]:
    """Cherche les pages catalogue puis les pages produit depuis un site."""
    raise NotImplementedError
