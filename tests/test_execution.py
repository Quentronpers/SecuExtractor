"""Sous-commande ``extract`` : choix des notices, réglages, commit, contrôle de fin.

Aucun appel réseau : Ollama est remplacé par des fonctions écrites à la main.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from catalog.evaluation import execution, notices
from catalog.evaluation.execution import (
    commit_courant,
    configurer,
    controler_fin,
    documents,
)
from catalog.extraction.client import EchecAppel
from catalog.extraction.ollama import ModeleCharge
from catalog.extraction.runner import ConfigModele

SHA = "a" * 64
CSV = (
    "id,fabricant,reference,type,format,url,pieges,sha256,jeu\n"
    f"axis-03,Axis,M3215-LVE,camera_dome,pdf,https://e.com/a.pdf,,{SHA},miseaupoint\n"
    f"axis-01,Axis,P3265,camera_dome,pdf,https://e.com/b.pdf,,{'b' * 64},test\n"
)


def _args(**changements: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "notices": Path("eval/notices.csv"),
        "jeu": "miseaupoint",
        "ids": "",
        "executions": 1,
        "fournisseur": "ollama",
        "reflexion": "none",
        "max_jetons": None,
    }
    return argparse.Namespace(**(base | changements))


@pytest.fixture
def jeu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un CSV de deux notices et un manifeste ; seule axis-03 a son fichier."""
    sources = tmp_path / "sources"
    (sources / "axis").mkdir(parents=True)
    (sources / "axis" / "a.pdf").write_bytes(b"%PDF")
    manifeste = sources / "manifeste.json"
    entree = {"fichier": "axis/a.pdf", "empreinte_sha256": SHA, "statut": "archive"}
    manifeste.write_text(json.dumps([entree]), encoding="utf-8")
    monkeypatch.setattr(notices, "MANIFESTE_PATH", manifeste)
    monkeypatch.setattr(execution, "MANIFESTE_PATH", manifeste)
    csv = tmp_path / "notices.csv"
    csv.write_text(CSV, encoding="utf-8")
    return csv


def test_documents_du_jeu_avec_leur_fichier(jeu: Path) -> None:
    trouves = documents(_args(notices=jeu))
    assert [d.id for d in trouves] == ["axis-03"]
    assert trouves[0].chemin.name == "a.pdf" and trouves[0].sha256 == SHA


def test_id_hors_du_jeu_refuse(jeu: Path) -> None:
    with pytest.raises(SystemExit, match="axis-01"):
        documents(_args(notices=jeu, ids="axis-03,axis-01"))


def test_fichier_archive_introuvable_refuse(jeu: Path) -> None:
    with pytest.raises(SystemExit, match="axis-01 : fichier archivé introuvable"):
        documents(_args(notices=jeu, jeu="test"))


def test_groq_sans_contexte_ni_digest() -> None:
    config, serveur = configurer(_args(fournisseur="groq", reflexion="low"), "u", "m")
    assert (config.contexte_jetons, config.empreinte_modele) == (None, None)
    assert config.max_jetons == 8192 and serveur == {}


def test_ollama_lit_contexte_digest_et_previent_du_debordement(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    charge = ModeleCharge(contexte_jetons=16384, empreinte="d1", part_gpu=0.8)
    monkeypatch.setattr(execution, "decrire_modele", lambda url, modele: charge)
    monkeypatch.setattr(execution, "version_ollama", lambda url: "0.12.6")
    config, serveur = configurer(_args(), "http://h/v1", "qwen3:14b")
    assert (config.contexte_jetons, config.empreinte_modele) == (16384, "d1")
    assert config.max_jetons == 2048 and config.reasoning_effort == "none"
    assert serveur == {"part_gpu": 0.8, "version_ollama": "0.12.6"}
    assert "80% du modèle" in capsys.readouterr().out


def test_ollama_injoignable_arrete_proprement(monkeypatch: pytest.MonkeyPatch) -> None:
    def en_panne(url: str, modele: str) -> ModeleCharge:
        raise EchecAppel("refusé")

    monkeypatch.setattr(execution, "decrire_modele", en_panne)
    with pytest.raises(SystemExit, match="Ollama injoignable"):
        configurer(_args(), "http://h/v1", "qwen3:14b")


@pytest.mark.parametrize("changement", [(16384, "d1", False), (8192, "d2", True)])
def test_controle_de_fin(
    monkeypatch: pytest.MonkeyPatch, changement: tuple[int, str, bool]
) -> None:
    contexte, digest, ecart = changement
    charge = ModeleCharge(contexte_jetons=contexte, empreinte=digest, part_gpu=1.0)
    monkeypatch.setattr(execution, "decrire_modele", lambda url, modele: charge)
    config = ConfigModele("qwen3:14b", 16384, "d1")
    assert controler_fin("http://h/v1", config)["fin_ecart"] is ecart


def test_commit_par_reference_et_packed_refs(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")
    (git / "packed-refs").write_text("c0ffee refs/heads/master\n", encoding="utf-8")
    assert commit_courant(tmp_path) == "c0ffee"
    (git / "refs" / "heads" / "master").write_text("58613f2\n", encoding="utf-8")
    assert commit_courant(tmp_path) == "58613f2"
    (git / "HEAD").write_text("deadbeef\n", encoding="utf-8")
    assert commit_courant(tmp_path) == "deadbeef"


def test_commit_inconnu_hors_depot(tmp_path: Path) -> None:
    assert commit_courant(tmp_path) == ""


def test_variables_d_environnement_exigees(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(SystemExit, match="LLM_BASE_URL"):
        execution.cmd_extract(_args())
