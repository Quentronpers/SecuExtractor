"""Ligne de commande : chaque sous-commande livrée se lit sans erreur."""

from __future__ import annotations

from pathlib import Path

import pytest

from catalog.acquisition import fetcher, manifest
from catalog.cli import build_parser, main


@pytest.mark.parametrize(
    "argv",
    [
        ["discover", "--fabricants", "data/fabricants.txt"],
        ["acquire", "--fabricant", "axis"],
        ["extract", "--jeu", "miseaupoint", "--ids", "axis-03"],
        ["evaluate", "--ligne-de-base", "--jeu", "test"],
        ["evaluate", "--comparer", "a.json", "b.json"],
        ["recuperer", "--ids", "axis-03"],
    ],
    ids=lambda argv: "_".join(argv[:2]),
)
def test_parser_connait_chaque_sous_commande(argv: list[str]) -> None:
    args = build_parser().parse_args(argv)
    assert callable(args.func)


@pytest.mark.parametrize("prevue", ["export", "status"])
def test_les_commandes_prevues_ne_sont_pas_proposees(prevue: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([prevue])


def test_sans_contact_un_message_clair_et_un_code_d_erreur(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SECURSCOPE_CONTACT", raising=False)
    monkeypatch.setattr(fetcher, "_robots_cache", {})
    monkeypatch.setattr(manifest, "SOURCES_DIR", tmp_path)
    monkeypatch.setattr(manifest, "MANIFESTE_PATH", tmp_path / "manifeste.json")

    assert main(["recuperer", "--ids", "axis-01"]) == 2
    assert "SECURSCOPE_CONTACT" in capsys.readouterr().err
