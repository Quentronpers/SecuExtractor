"""Récupération de pages et documents : requests d'abord, repli playwright.

Cadence, robots.txt, User-Agent identifiable et reprise sur erreur — voir
CLAUDE.md (section « Cadre à respecter »).

Le contact du User-Agent vient de la variable d'environnement
SECURSCOPE_CONTACT ; sans elle, aucune requête ne part (``ContactManquant``).
Chaque URL refusée ou en échec garde sa cause (``cause_echec``), que la
cascade reporte dans le journal des échecs.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import UnicodeDammit

from catalog.acquisition import robots

JETON_PRODUIT = "SecurScopeCatalogBot"

DELAI_MIN_S = 2.0
DELAI_MAX_S = 3.0
TENTATIVES_MAX = 3
TIMEOUT_S = 15
REDIRECTIONS_MAX = 5
ATTENTE_RETRY_AFTER_MAX_S = 60.0
SEUIL_CONTENU_SUFFISANT = 200  # caractères ; en dessous, suspect d'un rendu JS manquant

_dernier_acces: dict[str, float] = {}
_robots_cache: dict[str, robots.Robots] = {}
_causes: dict[str, str] = {}


class ContactManquant(RuntimeError):
    """Aucun moyen de contact configuré : le robot ne doit pas sortir."""


@dataclass
class ResultatFetch:
    """Contenu récupéré et outil qui a servi, noté au manifeste."""

    contenu: str
    outil: str  # "requests" ou "playwright"


def user_agent() -> str:
    """User-Agent identifiable, avec le contact de SECURSCOPE_CONTACT."""
    contact = os.environ.get("SECURSCOPE_CONTACT", "").strip()
    if not contact:
        raise ContactManquant(
            "SECURSCOPE_CONTACT n'est pas défini : un robot doit donner un "
            "moyen de contact réel (export SECURSCOPE_CONTACT=vous@exemple.fr)."
        )
    return f"{JETON_PRODUIT}/0.1 (+mailto:{contact})"


def cause_echec(url: str) -> str:
    """Pourquoi la dernière récupération de cette URL a échoué."""
    return _causes.get(url, "inconnue")


def _crawl_delay(domaine: str) -> float:
    """Délai imposé par le ``Crawl-delay`` du robots.txt déjà lu, 0 sinon."""
    regles = _robots_cache.get(domaine)
    if regles is None or regles.crawl_delay is None:
        return 0.0
    return regles.crawl_delay


def _attendre_cadence(domaine: str) -> None:
    """Attend 2 à 3 s (ou le ``Crawl-delay``) depuis la requête précédente."""
    dernier = _dernier_acces.get(domaine)
    delai = max(random.uniform(DELAI_MIN_S, DELAI_MAX_S), _crawl_delay(domaine))
    if dernier is not None:
        ecoule = time.monotonic() - dernier
        if ecoule < delai:
            time.sleep(delai - ecoule)
    _dernier_acces[domaine] = time.monotonic()


def _lire_robots(url_robots: str) -> robots.Robots:
    """Lit un robots.txt avec délai d'expiration, selon la RFC 9309 (§2.3.1).

    Succès → règles du fichier ; erreur 4xx, 401 et 403 compris (fichier
    indisponible, cas des stockages S3 ou Azure sans robots.txt) → tout est
    autorisé ; serveur injoignable ou erreur 5xx → tout est interdit, faute
    de savoir ce que le site autorise.
    """
    try:
        reponse = requests.get(
            url_robots, headers={"User-Agent": user_agent()}, timeout=TIMEOUT_S
        )
    except requests.RequestException:
        return robots.tout_interdit()
    if reponse.status_code >= 500:
        return robots.tout_interdit()
    if reponse.status_code >= 400:
        return robots.TOUT_AUTORISE
    return robots.analyser(reponse.text, JETON_PRODUIT)


class _Refus(Exception):
    """Requête qu'on ne fera pas, quoi qu'il arrive : inutile de réessayer."""


def _robots_autorise(url: str) -> bool:
    """Vrai si le robots.txt du domaine, lu une fois puis gardé, permet l'URL."""
    morceaux = urlparse(url)
    regles = _robots_cache.get(morceaux.netloc)
    if regles is None:
        regles = _lire_robots(f"{morceaux.scheme}://{morceaux.netloc}/robots.txt")
        _robots_cache[morceaux.netloc] = regles
    chemin = (morceaux.path or "/") + (f"?{morceaux.query}" if morceaux.query else "")
    return regles.autorise(chemin)


def _passagere(reponse: requests.Response) -> bool:
    """Vrai pour une erreur qui peut passer en réessayant : 429 et 5xx."""
    return reponse.status_code == 429 or reponse.status_code >= 500


def _attente(reponse: requests.Response | None, tentative: int) -> float:
    """Attente croissante, ou ``Retry-After`` en secondes s'il est plus long."""
    attente = float(2**tentative)
    # Une réponse en erreur vaut faux en booléen : tester ``is not None``.
    retry_after = reponse.headers.get("Retry-After", "") if reponse is not None else ""
    if retry_after.isdigit():
        attente = max(attente, min(float(retry_after), ATTENTE_RETRY_AFTER_MAX_S))
    return attente


def _get(url: str) -> requests.Response:
    """Un GET qui suit les redirections en contrôlant robots.txt à chaque saut."""
    for _ in range(REDIRECTIONS_MAX + 1):
        if not _robots_autorise(url):
            raise _Refus(f"robots.txt interdit {url}")
        _attendre_cadence(urlparse(url).netloc)
        reponse = requests.get(
            url,
            headers={"User-Agent": user_agent()},
            timeout=TIMEOUT_S,
            allow_redirects=False,
        )
        if not reponse.is_redirect:  # is_redirect exige un en-tête Location
            return reponse
        url = urljoin(url, reponse.headers["Location"])
    raise _Refus(f"plus de {REDIRECTIONS_MAX} redirections")


def _requete_avec_reprise(url: str) -> requests.Response | None:
    """GET, réessayé sur erreur réseau, 429 ou 5xx ; abandon après trois essais.

    Une autre erreur (404, 403…) ne change pas en réessayant, pas plus qu'un
    refus de robots.txt : abandon immédiat. La cause reste dans ``_causes``.
    """
    _causes.pop(url, None)
    for tentative in range(1, TENTATIVES_MAX + 1):
        reponse = None
        try:
            reponse = _get(url)
        except _Refus as refus:
            _causes[url] = str(refus)
            return None
        except requests.RequestException as erreur:
            _causes[url] = f"réseau : {type(erreur).__name__}"
        if reponse is not None and reponse.ok:
            return reponse
        if reponse is not None:
            _causes[url] = f"HTTP {reponse.status_code}"
            if not _passagere(reponse):
                return None
        if tentative < TENTATIVES_MAX:
            time.sleep(_attente(reponse, tentative))
    return None


def fetch_texte(url: str) -> ResultatFetch | None:
    """Récupère le texte d'une page, avec repli playwright si le rendu est vide."""
    reponse = _requete_avec_reprise(url)
    if reponse is None:
        return None
    texte = decoder(reponse)
    if len(texte.strip()) >= SEUIL_CONTENU_SUFFISANT:
        return ResultatFetch(contenu=texte, outil="requests")
    texte_playwright = _fetch_playwright(url)
    if texte_playwright is not None:
        return ResultatFetch(contenu=texte_playwright, outil="playwright")
    return ResultatFetch(contenu=texte, outil="requests")


def decoder(reponse: requests.Response) -> str:
    """Décode une page selon l'encodage qu'elle annonce.

    Sans charset dans l'en-tête HTTP, ``requests`` suppose Latin-1 et abîme
    une page UTF-8 (« Â± » pour « ± », Uniview le 2026-10-15). On prend
    alors l'encodage déclaré dans la page (``<meta charset>``), sinon celui
    que détecte BeautifulSoup.
    """
    if "charset" in reponse.headers.get("Content-Type", "").lower():
        return reponse.text
    detection = UnicodeDammit(reponse.content, is_html=True)
    return detection.unicode_markup or reponse.text


def fetch_binaire(url: str) -> bytes | None:
    """Télécharge un document binaire (PDF), sans repli playwright."""
    reponse = _requete_avec_reprise(url)
    return reponse.content if reponse is not None else None


def _fetch_playwright(url: str) -> str | None:
    """Rendu JavaScript de la page ; ses sous-ressources ne sont pas filtrées."""
    from playwright.sync_api import sync_playwright

    _attendre_cadence(urlparse(url).netloc)
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch()
            page = navigateur.new_page(user_agent=user_agent())
            page.goto(url, timeout=TIMEOUT_S * 1000)
            contenu = page.content()
            navigateur.close()
            return contenu
    except Exception:
        # Navigateur non installé, page inatteignable, etc. : on retombe sur
        # le texte déjà récupéré par requests plutôt que d'interrompre la
        # cascade pour un repli qui n'est jamais garanti.
        return None
