"""Jeu de notices : CSV, empreintes reprises du manifeste, tirage stratifié."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from catalog.evaluation.notices import (
    Notice,
    charger_notices,
    completer_empreintes,
    ecrire_notices,
    tirer,
)

TYPES = ["camera_dome"] * 20 + ["camera_tube"] * 18 + ["camera_ptz"] * 12
FABRICANTS = ["axis", "hik", "dahua", "hanwha", "bosch"]


def _jeu() -> list[Notice]:
    """50 notices : 20 dômes, 18 tubes, 12 PTZ, cinq fabricants en alternance."""
    return [
        Notice(
            id=f"{FABRICANTS[i % 5]}-{i:02d}",
            fabricant=FABRICANTS[i % 5],
            reference=f"REF-{i}",
            type=type_,
            format="pdf",
            url=f"https://exemple.test/{i}.pdf",
        )
        for i, type_ in enumerate(TYPES)
    ]


def test_tirage_reproductible_a_graine_fixe() -> None:
    assert tirer(_jeu()) == tirer(_jeu())
    assert tirer(_jeu(), graine=1) != tirer(_jeu(), graine=2)


def test_tirage_stratifie_par_type() -> None:
    tirage = tirer(_jeu())
    mise_au_point = [n for n in tirage if n.jeu == "miseaupoint"]

    assert len(mise_au_point) == 15
    assert {n.jeu for n in tirage} == {"miseaupoint", "test"}
    # 15 × 20/50 = 6, 15 × 18/50 = 5,4, 15 × 12/50 = 3,6 → plus fort reste.
    assert Counter(n.type for n in mise_au_point) == {
        "camera_dome": 6,
        "camera_tube": 5,
        "camera_ptz": 4,
    }


def test_tirage_etale_sur_les_fabricants() -> None:
    mise_au_point = [n for n in tirer(_jeu()) if n.jeu == "miseaupoint"]

    assert len({n.fabricant for n in mise_au_point}) == len(FABRICANTS)


def test_csv_relu_a_l_identique(tmp_path: Path) -> None:
    chemin = tmp_path / "notices.csv"
    notices = tirer(_jeu())
    ecrire_notices(notices, chemin)

    assert charger_notices(chemin) == notices


@pytest.mark.parametrize("attribut", ["id", "url"])
def test_doublon_refuse(tmp_path: Path, attribut: str) -> None:
    notices = _jeu()[:2]
    notices[1] = notices[1].model_copy(update={attribut: getattr(notices[0], attribut)})
    chemin = tmp_path / "notices.csv"
    ecrire_notices(notices, chemin)

    with pytest.raises(ValueError, match=f"{attribut} en double"):
        charger_notices(chemin)


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [("type", "camera_thermique"), ("format", "docx"), ("sha256", "abc")],
)
def test_valeur_invalide_refusee(champ: str, valeur: str) -> None:
    donnees = _jeu()[0].model_dump() | {champ: valeur}
    with pytest.raises(ValidationError):
        Notice.model_validate(donnees)


def test_empreinte_reprise_du_manifeste_par_url() -> None:
    notices = _jeu()[:2]
    manifeste = [{"url": notices[0].url, "empreinte_sha256": "b" * 64}]

    completes = completer_empreintes(notices, manifeste)

    assert [n.sha256 for n in completes] == ["b" * 64, ""]


def test_le_jeu_versionne_est_complet_et_tire() -> None:
    notices = charger_notices()

    assert len(notices) == 50
    assert len({n.fabricant for n in notices}) >= 8
    assert Counter(n.jeu for n in notices) == {"miseaupoint": 15, "test": 35}
    assert all(n.sha256 for n in notices)
