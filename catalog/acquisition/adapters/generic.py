"""Adaptateur générique : cas courant, à essayer en premier.

Recherche du site, repérage des liens catalogue, détection des pages produit,
extraction des liens de notice. Un adaptateur spécifique par fabricant
n'hérite de celui-ci qu'après un échec constaté (CLAUDE.md, section
« Générique d'abord, adaptateur ensuite »).

Les heuristiques ci-dessous sont volontairement grossières : il ne s'agit pas
de deviner juste à tous les coups, mais de traiter gratuitement les cas
simples et de laisser la cascade journaliser proprement le reste.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from catalog.acquisition import fetcher

CANDIDATS_TLD = ("com", "fr", "eu")

MOTS_CATALOGUE = (
    "produit",
    "product",
    "catalogue",
    "catalog",
    "gamme",
    "range",
    "shop",
)
MOTS_NOTICE = ("datasheet", "notice", "specification", "spec", "manual", "fiche", "pdf")

PAGES_PRODUIT_MAX = 50

PREFIXES_EXCLUS = ("mailto:", "tel:", "javascript:", "#")
CHEMINS_EXCLUS = (
    "about",
    "contact",
    "news",
    "blog",
    "legal",
    "privacy",
    "cookie",
    "support",
    "career",
    "jobs",
    "login",
    "cart",
    "compte",
    "account",
)


def _href(lien: Tag) -> str:
    """Retourne l'attribut href d'un lien, toujours sous forme de chaîne."""
    return str(lien.get("href", ""))


class AdaptateurGenerique:
    """Comportement par défaut de la cascade de découverte et d'acquisition."""

    def trouver_site(self, fabricant: str) -> str | None:
        """Devine le domaine officiel à partir du nom du fabricant.

        Quelques variantes de domaine sont essayées ; la première page qui
        répond et dont le titre mentionne le fabricant est retenue.
        """
        base = _normaliser_nom(fabricant)
        mots = _mots_significatifs(fabricant)
        for tld in CANDIDATS_TLD:
            for candidat in (f"https://www.{base}.{tld}", f"https://{base}.{tld}"):
                resultat = fetcher.fetch_texte(candidat)
                if resultat is None:
                    continue
                soup = BeautifulSoup(resultat.contenu, "html.parser")
                titre = soup.title.get_text(strip=True).lower() if soup.title else ""
                if mots & set(re.split(r"\W+", titre)):
                    return candidat
        return None

    def trouver_pages_catalogue(self, site_url: str) -> list[str]:
        """Repère les liens de catalogue depuis la page d'accueil du site."""
        resultat = fetcher.fetch_texte(site_url)
        if resultat is None:
            return []
        soup = BeautifulSoup(resultat.contenu, "html.parser")
        liens: set[str] = set()
        for a in soup.find_all("a", href=True):
            texte = a.get_text(strip=True).lower()
            href = _href(a).lower()
            if any(mot in texte or mot in href for mot in MOTS_CATALOGUE):
                liens.add(urljoin(site_url, _href(a)))
        return sorted(liens)

    def trouver_pages_produit(self, page_catalogue_url: str) -> list[str]:
        """Repère les pages produit individuelles depuis une page catalogue.

        Heuristique générique : liens internes au même domaine, rangés sous
        le chemin de la page catalogue ou dans une rubrique produit, hors
        rubriques manifestement hors sujet (about, contact, blog…). Au plus
        ``PAGES_PRODUIT_MAX`` par page catalogue : on cible des notices, on ne
        parcourt pas un site. Un fabricant dont la structure y résiste reçoit
        un adaptateur dédié.
        """
        resultat = fetcher.fetch_texte(page_catalogue_url)
        if resultat is None:
            return []
        soup = BeautifulSoup(resultat.contenu, "html.parser")
        liens = {
            url
            for a in soup.find_all("a", href=True)
            if (url := _lien_produit(page_catalogue_url, _href(a))) is not None
        }
        return sorted(liens)[:PAGES_PRODUIT_MAX]

    def trouver_notice(self, page_produit_url: str) -> str | None:
        """Retourne l'URL du PDF de notice si la page produit en propose un."""
        resultat = fetcher.fetch_texte(page_produit_url)
        if resultat is None:
            return None
        return self.notice_dans(resultat.contenu, page_produit_url)

    def notice_dans(self, contenu: str, page_produit_url: str) -> str | None:
        """Le lien de notice d'une page produit déjà récupérée, s'il y en a un."""
        soup = BeautifulSoup(contenu, "html.parser")
        for a in soup.find_all("a", href=True):
            href = _href(a)
            texte = a.get_text(strip=True).lower()
            if href.lower().split("?")[0].endswith(".pdf") or any(
                mot in texte for mot in MOTS_NOTICE
            ):
                return urljoin(page_produit_url, href)
        return None


def _lien_produit(page_catalogue_url: str, href: str) -> str | None:
    """L'URL absolue d'un lien qui ressemble à une page produit, sinon ``None``."""
    if href.startswith(PREFIXES_EXCLUS):
        return None
    url = urljoin(page_catalogue_url, href).split("#")[0]
    catalogue = urlparse(page_catalogue_url)
    cible = urlparse(url)
    if cible.netloc != catalogue.netloc or url == page_catalogue_url:
        return None
    chemin = cible.path.lower()
    if any(mot in chemin for mot in CHEMINS_EXCLUS):
        return None
    sous_catalogue = chemin.startswith(catalogue.path.lower().rstrip("/") + "/")
    rubrique_produit = any(mot in chemin for mot in MOTS_CATALOGUE)
    return url if sous_catalogue or rubrique_produit else None


def _normaliser_nom(fabricant: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", fabricant.lower())


def _mots_significatifs(fabricant: str) -> set[str]:
    return {mot.lower() for mot in re.split(r"\s+", fabricant) if len(mot) > 2}
