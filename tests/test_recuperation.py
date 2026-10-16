"""Récupération des notices par empreinte, sans réseau."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from catalog.acquisition import fetcher, manifest, recuperation
from catalog.acquisition.fetcher import ResultatFetch
from catalog.acquisition.recuperation import Demande, recuperer

PDF = b"%PDF-1.7 notice"
PAGE = "<html>fiche é</html>"


def demande(contenu: bytes = PDF, format_: str = "pdf") -> Demande:
    return Demande(
        id="axis-03",
        fabricant="Axis Communications",
        url=f"https://exemple.test/notice.{format_}",
        format=format_,
        sha256=hashlib.sha256(contenu).hexdigest(),
    )


@pytest.fixture
def sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(manifest, "SOURCES_DIR", tmp_path)
    monkeypatch.setattr(manifest, "MANIFESTE_PATH", tmp_path / "manifeste.json")
    monkeypatch.setattr(fetcher, "fetch_binaire", lambda url: PDF)
    monkeypatch.setattr(
        fetcher, "fetch_texte", lambda url: ResultatFetch(PAGE, "requests")
    )
    return tmp_path


def test_verification_seule_n_ecrit_rien(sources: Path) -> None:
    assert recuperer(demande()) == "conforme"
    assert not (sources / "manifeste.json").exists()


def test_archive_puis_present(sources: Path) -> None:
    assert recuperer(demande(), archiver=True) == "recupere"
    assert (sources / "axis-communications" / "axis-03.pdf").read_bytes() == PDF
    entree = manifest.charger()[0]
    assert entree["empreinte_sha256"] == demande().sha256
    assert recuperer(demande(), archiver=True) == "present"


def test_notice_modifiee_jamais_archivee(sources: Path) -> None:
    assert recuperer(demande(b"autre version"), archiver=True) == "modifie"
    assert manifest.charger() == []


def test_page_web_reencodee_en_utf8(sources: Path) -> None:
    attendue = demande(PAGE.encode("utf-8"), "html")
    assert recuperer(attendue, archiver=True) == "recupere"


def test_echec_de_telechargement(
    sources: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetcher, "fetch_binaire", lambda url: None)
    assert recuperation.recuperer(demande()) == "echec"
