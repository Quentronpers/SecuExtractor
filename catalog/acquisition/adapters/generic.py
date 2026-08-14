"""Adaptateur générique : cas courant, à essayer en premier.

Recherche du site, repérage des liens catalogue, détection des pages produit,
extraction des liens de notice. Un adaptateur spécifique par fabricant
n'hérite de celui-ci qu'après un échec constaté (CLAUDE.md, section
« Générique d'abord, adaptateur ensuite »).
"""

from __future__ import annotations


class AdaptateurGenerique:
    """Comportement par défaut de la cascade de découverte et d'acquisition."""

    def trouver_site(self, fabricant: str) -> str | None:
        raise NotImplementedError

    def trouver_pages_produit(self, site_url: str) -> list[str]:
        raise NotImplementedError

    def trouver_notice(self, page_produit_url: str) -> str | None:
        """Retourne l'URL d'un PDF de notice si le lien existe sur la page."""
        raise NotImplementedError
