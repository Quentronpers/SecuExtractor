"""Acquisition : URL fournies à la main et cadence imposée par robots.txt.

Aucun appel réseau : le fetcher est remplacé, les chemins pointent vers un
dossier temporaire.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from catalog.acquisition import discovery, fetcher, manifest, robots
from catalog.acquisition.adapters import generic
from catalog.acquisition.fetcher import ResultatFetch


class AdaptateurInterdit(discovery.AdaptateurGenerique):
    """Échoue si la cascade automatique est sollicitée."""

    def trouver_site(self, fabricant: str) -> str | None:
        raise AssertionError("une URL manuelle ne passe pas par la cascade")

    def trouver_notice(self, page_produit_url: str) -> str | None:
        raise AssertionError("une URL manuelle ne suit aucun lien")


@pytest.fixture
def sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(manifest, "SOURCES_DIR", tmp_path)
    monkeypatch.setattr(manifest, "MANIFESTE_PATH", tmp_path / "manifeste.json")
    monkeypatch.setattr(discovery, "ECHECS_PATH", tmp_path / "echecs.json")
    produits = tmp_path / "produits_manuels.json"
    monkeypatch.setattr(discovery, "PRODUITS_MANUELS_PATH", produits)
    produits.write_text(
        json.dumps(
            {
                "Axis": [
                    "https://exemple.test/doc/fiche.pdf",
                    "https://exemple.test/produit/xnd-8083rv",
                ]
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def appels(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    journal: list[str] = []

    def binaire(url: str) -> bytes:
        journal.append(url)
        return b"%PDF-1.7 fiche"

    def texte(url: str) -> ResultatFetch:
        journal.append(url)
        return ResultatFetch(contenu="<html>Power 12 V DC</html>", outil="requests")

    monkeypatch.setattr(fetcher, "fetch_binaire", binaire)
    monkeypatch.setattr(fetcher, "fetch_texte", texte)
    return journal


def test_url_manuelle_archive_le_document_exact(
    sources: Path, appels: list[str]
) -> None:
    discovery.decouvrir_fabricant("Axis", AdaptateurInterdit())

    entrees = manifest.charger()
    assert [(e["url"], e["type_document"]) for e in entrees] == [
        ("https://exemple.test/doc/fiche.pdf", "pdf"),
        ("https://exemple.test/produit/xnd-8083rv", "html"),
    ]
    (pdf,) = (sources / "axis").glob("fiche_*.pdf")
    assert pdf.read_bytes() == b"%PDF-1.7 fiche"


def test_url_manuelle_deja_archivee_pas_retelechargee(
    sources: Path, appels: list[str]
) -> None:
    discovery.decouvrir_fabricant("Axis", AdaptateurInterdit())
    discovery.decouvrir_fabricant("Axis", AdaptateurInterdit())

    assert len(appels) == 2
    assert len(manifest.charger()) == 2


def test_echec_d_une_url_manuelle_journalise(
    sources: Path, appels: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetcher, "fetch_binaire", lambda url: None)

    discovery.decouvrir_fabricant("Axis", AdaptateurInterdit())

    echecs = json.loads((sources / "echecs.json").read_text(encoding="utf-8"))
    assert [e["etape"] for e in echecs] == ["0c_produit_inexploitable"]


def test_crawl_delay_du_robots_txt_respecte(monkeypatch: pytest.MonkeyPatch) -> None:
    regles = robots.analyser("User-agent: *\nCrawl-delay: 100\nAllow: /", "Bot")
    monkeypatch.setitem(fetcher._robots_cache, "lent.test", regles)

    assert fetcher._crawl_delay("lent.test") == 100.0
    assert fetcher._crawl_delay("inconnu.test") == 0.0


class _Reponse:
    def __init__(self, statut: int, texte: str = "") -> None:
        self.status_code = statut
        self.text = texte


@pytest.mark.parametrize(
    ("reponse", "autorise"),
    [
        (_Reponse(200, "User-agent: *\nDisallow: /prive/"), False),
        (_Reponse(200, "User-agent: *\nDisallow: /autre/"), True),
        (_Reponse(401), True),
        (_Reponse(403), True),
        (_Reponse(404), True),
        (_Reponse(503), False),
        (None, False),
    ],
    ids=["interdit", "autorise", "401", "403", "404", "503", "injoignable"],
)
def test_robots_txt_lu_avec_delai(
    monkeypatch: pytest.MonkeyPatch, reponse: _Reponse | None, autorise: bool
) -> None:
    monkeypatch.setenv("SECURSCOPE_CONTACT", "robot@exemple.test")

    def get(url: str, **kwargs: object) -> _Reponse:
        assert kwargs["timeout"] == fetcher.TIMEOUT_S
        if reponse is None:
            raise requests.ConnectTimeout("muet")
        return reponse

    monkeypatch.setattr(fetcher.requests, "get", get)
    regles = fetcher._lire_robots("https://site.test/robots.txt")

    assert regles.autorise("/prive/a.pdf") is autorise


def _reponse_http(contenu: bytes, content_type: str) -> requests.Response:
    reponse = requests.Response()
    reponse._content = contenu
    reponse.headers["Content-Type"] = content_type
    reponse.encoding = requests.utils.get_encoding_from_headers(reponse.headers)
    return reponse


def test_page_utf8_sans_charset_http_bien_decodee() -> None:
    # requests suppose Latin-1 sans charset : « ± » deviendrait « Â± ».
    page = '<html><head><meta charset="utf-8"></head><p>12 V ± 25 %</p></html>'
    reponse = _reponse_http(page.encode("utf-8"), "text/html")
    assert "12 V ± 25 %" in fetcher.decoder(reponse)


def test_charset_http_prioritaire() -> None:
    reponse = _reponse_http(
        "<p>± 10 %</p>".encode("latin-1"), "text/html; charset=ISO-8859-1"
    )
    assert "± 10 %" in fetcher.decoder(reponse)


def test_deux_pdf_de_meme_nom_ne_s_ecrasent_pas(sources: Path) -> None:
    contenus = {
        "https://a.test/p1/datasheet.pdf": b"%PDF-1.7 premier",
        "https://a.test/p2/datasheet.pdf": b"%PDF-1.7 second",
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(fetcher, "fetch_binaire", contenus.get)
        for url in contenus:
            assert discovery._archiver_pdf(discovery._dossier("Axis"), url)

    archives = sorted(p.read_bytes() for p in (sources / "axis").glob("datasheet_*"))
    assert archives == sorted(contenus.values())


def test_un_lien_notice_qui_rend_du_html_n_est_pas_archive_en_pdf(
    sources: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetcher, "fetch_binaire", lambda url: b"<html>Specs</html>")

    assert not discovery._archiver_pdf("axis", "https://a.test/specs")
    assert manifest.charger() == []


class AdaptateurUnProduit(discovery.AdaptateurGenerique):
    """Site, catalogue et une page produit fixés ; notice cherchée dans la page."""

    def trouver_site(self, fabricant: str) -> str | None:
        return "https://a.test"

    def trouver_pages_catalogue(self, site_url: str) -> list[str]:
        return ["https://a.test/produits"]

    def trouver_pages_produit(self, page_catalogue_url: str) -> list[str]:
        return ["https://a.test/produits/cam-100"]


def test_la_page_produit_n_est_recuperee_qu_une_fois(
    sources: Path, appels: list[str]
) -> None:
    (sources / "produits_manuels.json").write_text("{}", encoding="utf-8")

    discovery.decouvrir_fabricant("Axis", AdaptateurUnProduit())

    assert appels == ["https://a.test/produits/cam-100"]
    assert [e["type_document"] for e in manifest.charger()] == ["html"]


def test_l_echec_journalise_porte_sa_cause(
    sources: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (sources / "produits_manuels.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(fetcher, "fetch_texte", lambda url: None)
    monkeypatch.setitem(fetcher._causes, "https://a.test/produits/cam-100", "HTTP 403")

    discovery.decouvrir_fabricant("Axis", AdaptateurUnProduit())

    echecs = json.loads((sources / "echecs.json").read_text(encoding="utf-8"))
    assert "HTTP 403" in echecs[0]["raison"]


def test_pages_produit_filtrees_et_plafonnees(monkeypatch: pytest.MonkeyPatch) -> None:
    liens = "".join(f'<a href="/produits/cam-{n}">c</a>' for n in range(80))
    liens += '<a href="/blog/x">b</a><a href="/a-propos">a</a>'
    liens += '<a href="https://ailleurs.test/produits/y">e</a>'
    page = ResultatFetch(contenu=f"<html>{liens}</html>", outil="requests")
    monkeypatch.setattr(fetcher, "fetch_texte", lambda url: page)

    pages = discovery.AdaptateurGenerique().trouver_pages_produit(
        "https://a.test/produits"
    )

    assert len(pages) == generic.PAGES_PRODUIT_MAX
    assert all(p.startswith("https://a.test/produits/cam-") for p in pages)


def test_notice_trouvee_dans_une_page_deja_recuperee() -> None:
    contenu = '<a href="/doc/cam-100.pdf">Télécharger</a>'
    notice = discovery.AdaptateurGenerique().notice_dans(
        contenu, "https://a.test/produits/cam-100"
    )
    assert notice == "https://a.test/doc/cam-100.pdf"
