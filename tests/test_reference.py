"""Format du corrigé d'évaluation (eval/reference/<id>.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from catalog.evaluation.reference import (
    CorrigeInvalide,
    charger_corrige,
    charger_corriges,
    valider_dossier,
)
from catalog.extraction.cible import Cible, charger_cible

SHA = "a" * 64


@pytest.fixture(scope="module")
def cible() -> Cible:
    return charger_cible("camera", "alimentation")


def _absent() -> dict[str, Any]:
    return {"valeur": None, "etat_attendu": "absent"}


def _corrige(cible: Cible, **champs: dict[str, Any]) -> dict[str, Any]:
    """Un corrigé valide : tout absent, sauf les champs donnés."""
    valeurs = {champ.cle: _absent() for champ in cible.champs}
    valeurs.update({cle.replace("__", "."): v for cle, v in champs.items()})
    return {
        "id": "axis-01",
        "reference": "AXIS P3265-LVE 9 mm",
        "sha256": SHA,
        "annotateur": "Quentin",
        "date_annotation": "2026-10-20",
        "champs": valeurs,
    }


def _ecrire(dossier: Path, donnees: dict[str, Any], nom: str = "axis-01") -> Path:
    chemin = dossier / f"{nom}.json"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    return chemin


def _present(valeur: Any, **en_plus: Any) -> dict[str, Any]:
    return {
        "valeur": valeur,
        "etat_attendu": "sur",
        "page": 2,
        "extrait": "Class 3, typical 4.8 W, max 10.7 W",
        **en_plus,
    }


def test_la_cible_porte_les_onze_champs_securscope(cible: Cible) -> None:
    assert len(cible.champs) == 11
    assert cible.source.commit == "3e1f26b"
    assert "power_w_peak" in cible.par_cle()


def test_corrige_valide_se_charge(cible: Cible, tmp_path: Path) -> None:
    donnees = _corrige(
        cible,
        power_w_peak=_present(10.7),
        ports__poe=_present(True),
        ports__poe__class=_present("3", note="Type 1"),
    )
    corrige = charger_corrige(_ecrire(tmp_path, donnees), cible)

    assert corrige.champs["power_w_peak"].valeur == 10.7
    assert corrige.champs["ports.poe"].valeur is True
    assert corrige.champs["ports.poe.class"].valeur == "3"


def test_nombre_entier_accepte_comme_nombre(cible: Cible, tmp_path: Path) -> None:
    donnees = _corrige(cible, power_w_peak=_present(12))
    corrige = charger_corrige(_ecrire(tmp_path, donnees), cible)

    assert corrige.champs["power_w_peak"].valeur == 12.0


def test_section_tient_lieu_de_page_pour_une_page_web(
    cible: Cible, tmp_path: Path
) -> None:
    annotee = _present(8.3)
    del annotee["page"]
    annotee["section"] = "Power"
    charger_corrige(_ecrire(tmp_path, _corrige(cible, power_w_peak=annotee)), cible)


@pytest.mark.parametrize(
    ("champs", "motif"),
    [
        ({"ports__poe__class": _present("9")}, "hors énumération"),
        ({"ports__poe__min_standard": _present("PoE+")}, "hors énumération"),
        ({"power_w_peak": _present("10.7")}, "nombre attendu"),
        ({"ports__poe": _present(1.0)}, "booléen attendu"),
        ({"power_w_peak": _present(True)}, "nombre attendu"),
        ({"puissance_poe_w": _present(10.7)}, "champ inconnu"),
    ],
)
def test_valeur_ou_champ_hors_cible_refuse(
    cible: Cible, tmp_path: Path, champs: dict[str, Any], motif: str
) -> None:
    with pytest.raises(CorrigeInvalide, match=motif):
        charger_corrige(_ecrire(tmp_path, _corrige(cible, **champs)), cible)


def test_champ_oublie_refuse(cible: Cible, tmp_path: Path) -> None:
    donnees = _corrige(cible)
    del donnees["champs"]["ports.dc.current_peak_ma"]

    with pytest.raises(CorrigeInvalide, match="champ manquant"):
        charger_corrige(_ecrire(tmp_path, donnees), cible)


@pytest.mark.parametrize(
    "annotee",
    [
        {"valeur": 10.7, "etat_attendu": "sur", "extrait": "max 10.7 W"},
        {"valeur": 10.7, "etat_attendu": "sur", "page": 2},
        {
            "valeur": 10.7,
            "etat_attendu": "sur",
            "page": 2,
            "section": "Power",
            "extrait": "max 10.7 W",
        },
        {"valeur": 10.7, "etat_attendu": "absent", "page": 2, "extrait": "x"},
        {"valeur": None, "etat_attendu": "sur"},
        {"valeur": 10.7, "etat_attendu": "sur", "page": 0, "extrait": "x"},
        {"valeur": 10.7, "etat_attendu": "certain", "page": 2, "extrait": "x"},
    ],
    ids=[
        "page_manquante",
        "extrait_manquant",
        "page_et_section",
        "absent_avec_valeur",
        "valeur_nulle_non_absente",
        "page_zero",
        "etat_inconnu",
    ],
)
def test_annotation_incoherente_refusee(
    cible: Cible, tmp_path: Path, annotee: dict[str, Any]
) -> None:
    with pytest.raises(CorrigeInvalide):
        charger_corrige(_ecrire(tmp_path, _corrige(cible, power_w_peak=annotee)), cible)


@pytest.mark.parametrize(
    ("cle", "valeur"),
    [("sha256", "abc"), ("id", "Axis_01"), ("annotateur", ""), ("inconnu", 1)],
)
def test_entete_malforme_refuse(
    cible: Cible, tmp_path: Path, cle: str, valeur: Any
) -> None:
    donnees = _corrige(cible)
    donnees[cle] = valeur

    with pytest.raises(CorrigeInvalide):
        charger_corrige(_ecrire(tmp_path, donnees), cible)


def test_id_different_du_nom_de_fichier_refuse(cible: Cible, tmp_path: Path) -> None:
    with pytest.raises(CorrigeInvalide, match="nom de fichier"):
        charger_corrige(_ecrire(tmp_path, _corrige(cible), nom="axis-02"), cible)


def test_dossier_charge_par_id_et_signale_les_malformes(
    cible: Cible, tmp_path: Path
) -> None:
    _ecrire(tmp_path, _corrige(cible))
    (tmp_path / "hik-01.json").write_text("{pas du json", encoding="utf-8")

    assert set(valider_dossier(tmp_path, cible)) == {"hik-01.json"}
    (tmp_path / "hik-01.json").unlink()
    assert list(charger_corriges(tmp_path, cible)) == ["axis-01"]
