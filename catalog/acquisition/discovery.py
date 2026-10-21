"""Orchestration de la cascade d'acquisition : site → catalogue → produits → archivage.

Chaque échec est journalisé dans data/sources/echecs.json plutôt que
silencieux, avec l'action manuelle attendue — voir CLAUDE.md (section
« L'acquisition ») et docs/pipeline.md (section « 1 bis »).

Trois fichiers permettent de fournir à la main ce que la cascade n'a pas su
trouver, et sont relus à chaque étape avant toute tentative automatique :
data/sources/sites_manuels.json, catalogues_manuels.json, produits_manuels.json.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from catalog.acquisition import fetcher, manifest
from catalog.acquisition.adapters.generic import AdaptateurGenerique

SITES_MANUELS_PATH = manifest.SOURCES_DIR / "sites_manuels.json"
CATALOGUES_MANUELS_PATH = manifest.SOURCES_DIR / "catalogues_manuels.json"
PRODUITS_MANUELS_PATH = manifest.SOURCES_DIR / "produits_manuels.json"
ECHECS_PATH = manifest.SOURCES_DIR / "echecs.json"


def _charger_json(chemin: Path, defaut: Any) -> Any:
    if not chemin.exists():
        return defaut
    with chemin.open(encoding="utf-8") as f:
        return json.load(f)


def _horodatage() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def journaliser_echec(
    fabricant: str, etape: str, raison: str, action_attendue: str
) -> None:
    """Ajoute une entrée au journal des échecs, jamais silencieux."""
    echecs = _charger_json(ECHECS_PATH, [])
    echecs.append(
        {
            "fabricant": fabricant,
            "etape": etape,
            "raison": raison,
            "action_attendue": action_attendue,
            "date": _horodatage(),
        }
    )
    ECHECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ECHECS_PATH.open("w", encoding="utf-8") as f:
        json.dump(echecs, f, ensure_ascii=False, indent=2)


def _trouver_site(fabricant: str, adaptateur: AdaptateurGenerique) -> str | None:
    sites_manuels = _charger_json(SITES_MANUELS_PATH, {})
    if fabricant in sites_manuels:
        return sites_manuels[fabricant]

    site = adaptateur.trouver_site(fabricant)
    if site is None:
        journaliser_echec(
            fabricant,
            "0a_site_officiel",
            "Aucun domaine candidat n'a répondu ou correspondu au fabricant",
            f"Fournir l'URL dans {SITES_MANUELS_PATH.name}",
        )
    return site


def _trouver_pages_produit(
    fabricant: str, site_url: str, adaptateur: AdaptateurGenerique
) -> list[str]:
    catalogues_manuels = _charger_json(CATALOGUES_MANUELS_PATH, {})
    pages_catalogue = catalogues_manuels.get(
        fabricant
    ) or adaptateur.trouver_pages_catalogue(site_url)
    if not pages_catalogue:
        journaliser_echec(
            fabricant,
            "0b_pages_catalogue",
            "Aucune section produit identifiée depuis la racine",
            f"Fournir les URL de catalogue dans {CATALOGUES_MANUELS_PATH.name}",
        )
        return []

    pages_produit: list[str] = []
    for page_catalogue in pages_catalogue:
        pages_produit.extend(adaptateur.trouver_pages_produit(page_catalogue))
    if not pages_produit:
        journaliser_echec(
            fabricant,
            "0c_pages_produit",
            "Aucune page produit repérée depuis les pages catalogue",
            f"Fournir les URL de produit dans {PRODUITS_MANUELS_PATH.name}",
        )
    return pages_produit


def _archiver_pdf(dossier: str, url: str) -> bool:
    """Télécharge et archive un PDF ; faux si échec ou si ce n'est pas un PDF.

    Le nom porte le début de l'empreinte : deux « datasheet.pdf » de produits
    différents ne s'écrasent pas, et un document déjà archivé n'est pas
    réécrit. Un lien « notice » qui renvoie une page HTML est refusé.
    """
    contenu = fetcher.fetch_binaire(url)
    if contenu is None or not contenu.startswith(b"%PDF"):
        return False
    base = Path(urlparse(url).path).stem or _slug(url)
    nom_fichier = f"{dossier}/{base}_{manifest.empreinte_sha256(contenu)[:12]}.pdf"
    chemin = manifest.SOURCES_DIR / nom_fichier
    if not chemin.exists():
        chemin.write_bytes(contenu)
        manifest.enregistrer(nom_fichier, url, "pdf", "requests")
    return True


def _ecrire_page(dossier: str, url: str, resultat: fetcher.ResultatFetch) -> None:
    """Archive une page HTML, figée par l'horodatage du nom de fichier."""
    nom_fichier = f"{dossier}/{_slug(url)}_{_horodatage_fichier()}.html"
    (manifest.SOURCES_DIR / nom_fichier).write_text(resultat.contenu, encoding="utf-8")
    manifest.enregistrer(nom_fichier, url, "html", resultat.outil)


def _archiver_page(dossier: str, url: str) -> bool:
    """Télécharge et archive une page produit HTML ; faux si l'accès échoue."""
    resultat = fetcher.fetch_texte(url)
    if resultat is None:
        return False
    _ecrire_page(dossier, url, resultat)
    return True


def _dossier(fabricant: str) -> str:
    dossier = _slug(fabricant)
    (manifest.SOURCES_DIR / dossier).mkdir(parents=True, exist_ok=True)
    return dossier


def _echec_produit(fabricant: str, url: str) -> None:
    journaliser_echec(
        fabricant,
        "0c_produit_inexploitable",
        f"Ni PDF ni page exploitable pour {url} ({fetcher.cause_echec(url)})",
        f"Saisie manuelle de la référence dans {PRODUITS_MANUELS_PATH.name}",
    )


def _archiver_produit(
    fabricant: str, page_produit_url: str, adaptateur: AdaptateurGenerique
) -> None:
    """Applique [0c] à une page produit : PDF, sinon page elle-même, sinon échec.

    La page n'est récupérée qu'une fois : on y cherche la notice, et c'est
    elle qu'on archive s'il n'y en a pas.
    """
    dossier = _dossier(fabricant)
    page = fetcher.fetch_texte(page_produit_url)
    if page is None:
        _echec_produit(fabricant, page_produit_url)
        return
    notice_url = adaptateur.notice_dans(page.contenu, page_produit_url)
    if notice_url is not None and _archiver_pdf(dossier, notice_url):
        return
    _ecrire_page(dossier, page_produit_url, page)


def _archiver_manuel(fabricant: str, url: str) -> None:
    """Archive le document exact désigné à la main : le PDF, ou la page elle-même.

    Aucun lien n'est suivi : une URL fournie à la main est le document voulu.
    Une URL déjà au manifeste n'est pas retéléchargée.
    """
    if any(entree["url"] == url for entree in manifest.charger()):
        return
    dossier = _dossier(fabricant)
    archiver = _archiver_pdf if _est_pdf(url) else _archiver_page
    if not archiver(dossier, url):
        _echec_produit(fabricant, url)


def decouvrir_fabricant(
    fabricant: str, adaptateur: AdaptateurGenerique | None = None
) -> None:
    """Exécute la cascade [0a]→[0c] pour un fabricant et archive ce qui est trouvé.

    Sert aussi bien à `discover` (première passe) qu'à `acquire` (reprise
    ciblée après complément manuel), les deux appelant cette même fonction.
    Les URL de ``produits_manuels.json`` court-circuitent la cascade : chacune
    désigne le document exact à archiver.
    """
    produits_manuels = _charger_json(PRODUITS_MANUELS_PATH, {})
    if fabricant in produits_manuels:
        for url in produits_manuels[fabricant]:
            _archiver_manuel(fabricant, url)
        return
    adaptateur = adaptateur or AdaptateurGenerique()
    site = _trouver_site(fabricant, adaptateur)
    if site is None:
        return
    pages_produit = _trouver_pages_produit(fabricant, site, adaptateur)
    for page_produit_url in pages_produit:
        _archiver_produit(fabricant, page_produit_url, adaptateur)


def decouvrir(fabricants: list[str]) -> None:
    """Lance la cascade pour chaque fabricant de la liste (data/fabricants.txt)."""
    for fabricant in fabricants:
        decouvrir_fabricant(fabricant)


def _est_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _slug(texte: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texte.lower()).strip("-")


def _horodatage_fichier() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")
