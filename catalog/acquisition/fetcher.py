"""Récupération de pages et documents : requests d'abord, repli playwright.

Cadence, robots.txt, User-Agent identifiable et reprise sur erreur — voir
CLAUDE.md (section « Cadre à respecter »).

Le contact dans le User-Agent se configure via la variable d'environnement
SECURSCOPE_CONTACT ; à défaut, un placeholder est utilisé et doit être changé
avant toute campagne réelle.
"""

from __future__ import annotations

import os
import random
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

CONTACT = os.environ.get("SECURSCOPE_CONTACT", "contact@example.com")
USER_AGENT = f"SecurScopeCatalogBot/0.1 (+mailto:{CONTACT})"

DELAI_MIN_S = 2.0
DELAI_MAX_S = 3.0
TENTATIVES_MAX = 3
TIMEOUT_S = 15
SEUIL_CONTENU_SUFFISANT = 200  # caractères ; en dessous, suspect d'un rendu JS manquant

_dernier_acces: dict[str, float] = {}
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


@dataclass
class ResultatFetch:
    """Contenu récupéré et outil qui a servi, noté au manifeste."""

    contenu: str
    outil: str  # "requests" ou "playwright"


def _crawl_delay(domaine: str) -> float:
    """Délai imposé par le ``Crawl-delay`` du robots.txt déjà lu, 0 sinon."""
    parseur = _robots_cache.get(domaine)
    delai = parseur.crawl_delay(USER_AGENT) if parseur is not None else None
    return float(delai) if delai else 0.0


def _attendre_cadence(domaine: str) -> None:
    dernier = _dernier_acces.get(domaine)
    delai = max(random.uniform(DELAI_MIN_S, DELAI_MAX_S), _crawl_delay(domaine))
    if dernier is not None:
        ecoule = time.monotonic() - dernier
        if ecoule < delai:
            time.sleep(delai - ecoule)
    _dernier_acces[domaine] = time.monotonic()


def _lire_robots(url_robots: str) -> urllib.robotparser.RobotFileParser:
    """Lit un robots.txt avec délai d'expiration, selon la RFC 9309 (§2.3.1).

    ``RobotFileParser.read`` n'a pas de délai (un site muet bloquait chaque
    URL de longues minutes) et suit une règle antérieure à la norme. Ici :
    succès → règles du fichier ; erreur 4xx, 401 et 403 compris (fichier
    indisponible, cas des stockages S3 ou Azure sans robots.txt) → tout est
    autorisé ; serveur injoignable ou erreur 5xx → tout est interdit, faute
    de savoir ce que le site autorise.
    """
    parseur = urllib.robotparser.RobotFileParser(url_robots)
    tout_interdit = ["User-agent: *", "Disallow: /"]
    try:
        reponse = requests.get(
            url_robots, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S
        )
    except requests.RequestException:
        parseur.parse(tout_interdit)
        return parseur
    if reponse.status_code >= 500:
        parseur.parse(tout_interdit)
    elif reponse.status_code >= 400:
        parseur.parse([])  # vide : tout est autorisé
    else:
        parseur.parse(reponse.text.splitlines())
    return parseur


def _robots_autorise(url: str) -> bool:
    morceaux = urlparse(url)
    parseur = _robots_cache.get(morceaux.netloc)
    if parseur is None:
        parseur = _lire_robots(f"{morceaux.scheme}://{morceaux.netloc}/robots.txt")
        _robots_cache[morceaux.netloc] = parseur
    return parseur.can_fetch(USER_AGENT, url)


def _requete_avec_reprise(url: str) -> requests.Response | None:
    """GET avec attente croissante entre tentatives, abandon après trois essais."""
    domaine = urlparse(url).netloc
    for tentative in range(1, TENTATIVES_MAX + 1):
        _attendre_cadence(domaine)
        try:
            reponse = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S
            )
            reponse.raise_for_status()
            return reponse
        except requests.RequestException:
            if tentative == TENTATIVES_MAX:
                return None
            time.sleep(2**tentative)
    return None


def fetch_texte(url: str) -> ResultatFetch | None:
    """Récupère le texte d'une page, avec repli playwright si le rendu est vide."""
    if not _robots_autorise(url):
        return None
    reponse = _requete_avec_reprise(url)
    if reponse is None:
        return None
    texte = reponse.text
    if len(texte.strip()) >= SEUIL_CONTENU_SUFFISANT:
        return ResultatFetch(contenu=texte, outil="requests")
    texte_playwright = _fetch_playwright(url)
    if texte_playwright is not None:
        return ResultatFetch(contenu=texte_playwright, outil="playwright")
    return ResultatFetch(contenu=texte, outil="requests")


def fetch_binaire(url: str) -> bytes | None:
    """Télécharge un document binaire (PDF), sans repli playwright."""
    if not _robots_autorise(url):
        return None
    reponse = _requete_avec_reprise(url)
    if reponse is None:
        return None
    return reponse.content


def _fetch_playwright(url: str) -> str | None:
    from playwright.sync_api import sync_playwright

    _attendre_cadence(urlparse(url).netloc)
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch()
            page = navigateur.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=TIMEOUT_S * 1000)
            contenu = page.content()
            navigateur.close()
            return contenu
    except Exception:
        # Navigateur non installé, page inatteignable, etc. : on retombe sur
        # le texte déjà récupéré par requests plutôt que d'interrompre la
        # cascade pour un repli qui n'est jamais garanti.
        return None
