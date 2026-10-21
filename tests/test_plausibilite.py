"""Règles de plausibilité du bloc alimentation des caméras."""

from __future__ import annotations

import pytest

from catalog.extraction.cible import Valeur
from catalog.plausibility.checker import (
    mentionne_poe_proprietaire,
    normes_citees,
    plus_haute_classe,
    verifier_plausibilite,
)
from catalog.reading.page import Page

POE_DC = {"ports.poe": True, "ports.dc": True}


def _motifs(
    valeurs: dict[str, Valeur],
    extraits: dict[str, str | None] | None = None,
    texte: str = "",
) -> dict[str, str]:
    pages = [Page(numero=1, texte=texte)] if texte else []
    return verifier_plausibilite({**POE_DC, **valeurs}, extraits or {}, pages)


def test_valeurs_ordinaires_sans_motif() -> None:
    valeurs: dict[str, Valeur] = {
        "power_w": 4.8,
        "power_w_peak": 10.7,
        "ports.poe.class": "3",
        "ports.poe.power_w": 10.7,
        "ports.poe.min_standard": "802.3af",
        "ports.dc.voltage_min_v": 9.0,
        "ports.dc.voltage_max_v": 15.0,
        "ports.dc.current_peak_ma": 900.0,
    }
    assert _motifs(valeurs) == {}


# --- Bornes -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("cle", "dedans", "dehors"),
    [
        ("power_w", (1.0, 200.0), (0.99, 200.01)),
        ("power_w_peak", (1.0, 200.0), (0.99, 200.01)),
        ("ports.poe.power_w", (1.0, 90.0), (0.99, 90.01)),
        ("ports.dc.current_standby_ma", (20.0, 2000.0), (19.9, 2000.1)),
        ("ports.dc.current_peak_ma", (100.0, 5000.0), (99.9, 5000.1)),
    ],
)
def test_bornes_exactes(
    cle: str, dedans: tuple[float, float], dehors: tuple[float, float]
) -> None:
    for v in dedans:
        assert "hors_bornes" not in _motifs({cle: v}).get(cle, "")
    for v in dehors:
        assert "hors_bornes" in _motifs({cle: v})[cle]


# --- Tensions ---------------------------------------------------------------


@pytest.mark.parametrize("tension", [9.0, 15.0, 18.0, 30.0, 36.0, 45.0, 60.0])
def test_tension_dans_la_gamme(tension: float) -> None:
    assert "ports.dc.voltage_max_v" not in _motifs({"ports.dc.voltage_max_v": tension})


@pytest.mark.parametrize("tension", [5.0, 8.9, 15.1, 17.9, 60.1, 230.0])
def test_tension_hors_gamme(tension: float) -> None:
    motifs = _motifs({"ports.dc.voltage_max_v": tension})
    assert motifs["ports.dc.voltage_max_v"] == "tension_hors_gamme"


def test_tension_du_poe_prise_pour_une_entree_continue() -> None:
    valeurs: dict[str, Valeur] = {"ports.dc.voltage_min_v": 48.0}
    extrait = "Power-over-Ethernet (48 VDC nominal)"
    motifs = _motifs(valeurs, {"ports.dc.voltage_min_v": extrait})
    assert motifs["ports.dc.voltage_min_v"] == "tension_poe"
    # Vivotek « DC 48V power input » : vraie entrée continue, admise.
    assert _motifs(valeurs, {"ports.dc.voltage_min_v": "DC 48V power input"}) == {}


def test_tension_poe_bornes_exactes() -> None:
    extrait: dict[str, str | None] = {"ports.dc.voltage_max_v": "PoE 802.3at"}
    for v in (44.0, 57.0):
        motifs = _motifs({"ports.dc.voltage_max_v": v}, extrait)
        assert "tension_poe" in motifs["ports.dc.voltage_max_v"]
    for v in (43.9, 57.1):
        motifs = _motifs({"ports.dc.voltage_max_v": v}, extrait)
        assert "tension_poe" not in motifs.get("ports.dc.voltage_max_v", "")


def test_tension_min_superieure_a_max() -> None:
    motifs = _motifs({"ports.dc.voltage_min_v": 15.0, "ports.dc.voltage_max_v": 9.0})
    assert motifs == {
        "ports.dc.voltage_min_v": "min_superieur_max",
        "ports.dc.voltage_max_v": "min_superieur_max",
    }


def test_plage_de_tension() -> None:
    # Axis « 10–28 V DC » : admis ; 12 V pris avec 57 V du PoE : refusé.
    assert (
        _motifs({"ports.dc.voltage_min_v": 10.0, "ports.dc.voltage_max_v": 28.0}) == {}
    )
    assert (
        _motifs({"ports.dc.voltage_min_v": 12.0, "ports.dc.voltage_max_v": 36.0}) == {}
    )
    motifs = _motifs({"ports.dc.voltage_min_v": 12.0, "ports.dc.voltage_max_v": 57.0})
    assert motifs["ports.dc.voltage_min_v"] == "plage_trop_large"


# --- PoE --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("norme", "classe", "admis"),
    [
        ("802.3af", "3", True),
        ("802.3af", "4", False),
        ("802.3at", "4", True),
        ("802.3at", "5", False),
        ("802.3bt", "0", False),
        ("802.3bt", "8", True),
    ],
)
def test_classe_et_norme(norme: str, classe: str, admis: bool) -> None:
    motifs = _motifs({"ports.poe.class": classe, "ports.poe.min_standard": norme})
    assert (motifs == {}) is admis
    if not admis:
        assert motifs["ports.poe.class"] == "classe_norme_incoherentes"


def test_classe_4_avec_30_w() -> None:
    motifs = _motifs({"ports.poe.class": "4", "ports.poe.power_w": 30.0})
    assert motifs == {
        "ports.poe.power_w": "depasse_plafond_classe",
        "ports.poe.class": "depasse_plafond_classe",
    }


@pytest.mark.parametrize(
    ("classe", "plafond"), [("2", 6.49), ("3", 12.95), ("4", 25.5), ("8", 71.3)]
)
def test_plafond_de_classe_exact(classe: str, plafond: float) -> None:
    assert _motifs({"ports.poe.class": classe, "ports.poe.power_w": plafond}) == {}
    motifs = _motifs({"ports.poe.class": classe, "ports.poe.power_w": plafond + 0.01})
    assert motifs["ports.poe.power_w"] == "depasse_plafond_classe"


def test_paire_classe_puissance_du_pire_cas() -> None:
    # AXIS Q1806-LE : at Class 4 max 25,5 W, ou bt Class 6 max 51 W. Le GUIDE
    # (2026-10-20) veut la paire du pire cas : classe 6 avec 51 W.
    texte = "IEEE 802.3at Class 4 max 25.5 W, or IEEE 802.3bt Type 3 Class 6 max 51 W"
    pire: dict[str, Valeur] = {"ports.poe.class": "6", "ports.poe.power_w": 51.0}
    assert _motifs(pire, texte=texte) == {}
    bas: dict[str, Valeur] = {"ports.poe.class": "4", "ports.poe.power_w": 51.0}
    assert set(_motifs(bas, texte=texte)) == {"ports.poe.class", "ports.poe.power_w"}


def test_sans_classe_extraite_plafond_de_la_plus_haute_citee() -> None:
    texte = "IEEE 802.3bt Type 3 Class 6 max 51 W"
    assert _motifs({"ports.poe.power_w": 51.0}, texte=texte) == {}
    assert _motifs({"ports.poe.power_w": 51.0}, texte="Class 4") != {}


def test_poe_proprietaire_sans_plafond() -> None:
    # AXIS Q6135-LE : classe du mode normé, puissance du High PoE (GUIDE).
    valeurs: dict[str, Valeur] = {"ports.poe.class": "4", "ports.poe.power_w": 51.0}
    assert _motifs(valeurs, texte="High PoE, IEEE 802.3at Class 4") == {}


def test_sans_classe_citee_plafond_de_la_classe_8() -> None:
    # « max 90 W » : capacité du PSE en Type 4, pas une consommation.
    assert _motifs({"ports.poe.power_w": 71.3}) == {}
    assert _motifs({"ports.poe.power_w": 90.0}) == {
        "ports.poe.power_w": "depasse_plafond_classe"
    }


def test_norme_af_et_plus_de_12_95_w() -> None:
    valeurs: dict[str, Valeur] = {
        "ports.poe.min_standard": "802.3af",
        "ports.poe.power_w": 16.8,
    }
    assert _motifs(valeurs, texte="PoE IEEE 802.3af") == {
        "ports.poe.min_standard": "norme_insuffisante",
        "ports.poe.power_w": "norme_insuffisante",
    }
    # af/at : la caméra démarre en af, tire 16,8 W en at.
    assert _motifs(valeurs, texte="IEEE 802.3af/802.3at") == {}
    assert _motifs({**valeurs, "ports.poe.power_w": 12.95}) == {}


def test_normes_citees() -> None:
    pages = [Page(numero=1, texte="IEEE 802.3af/at, PoE++")]
    assert normes_citees(pages) == {"802.3af", "802.3at", "802.3bt"}


def test_pas_de_plafond_avec_un_poe_proprietaire() -> None:
    texte = "High PoE max 51 W ; IEEE 802.3at Type 2 Class 4"
    valeurs: dict[str, Valeur] = {"ports.poe.class": "4", "ports.poe.power_w": 51.0}
    assert _motifs(valeurs, texte=texte) == {}


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Hi-PoE", True),
        ("High Power over Ethernet", True),
        ("High PoE 95 W", True),
        ("Tested POE Injector (60 W)", True),
        ("IEEE 802.3bt midspan", False),
        ("PoH/PoE 95 W", True),
        ("ePoE long distance", False),
        ("PoE+ Class 4", False),
    ],
)
def test_poe_proprietaire(texte: str, attendu: bool) -> None:
    assert mentionne_poe_proprietaire([Page(numero=1, texte=texte)]) is attendu


def test_plus_haute_classe() -> None:
    pages = [
        Page(numero=1, texte="Class 4"),
        Page(numero=2, texte="PoE Class6, Class 40"),
    ]
    assert plus_haute_classe(pages) == 6
    assert plus_haute_classe([Page(numero=1, texte="Type 4")]) is None


# --- Cohérence entre champs -------------------------------------------------


def test_typique_et_poe_au_plus_la_maximale() -> None:
    motifs = _motifs({"power_w": 11.0, "ports.poe.power_w": 12.0, "power_w_peak": 10.0})
    assert motifs == {
        "power_w": "typique_superieure_max",
        "power_w_peak": "typique_superieure_max; poe_superieure_max",
        "ports.poe.power_w": "poe_superieure_max",
    }
    assert (
        _motifs({"power_w": 10.0, "ports.poe.power_w": 10.0, "power_w_peak": 10.0})
        == {}
    )


def test_attribut_d_un_port_declare_absent() -> None:
    motifs = verifier_plausibilite(
        {"ports.poe": False, "ports.poe.class": "3", "ports.dc": None,
         "ports.dc.voltage_min_v": 12.0},
        {},
        [],
    )  # fmt: skip
    assert motifs == {
        "ports.poe": "port_absent",
        "ports.poe.class": "port_absent",
        "ports.dc.voltage_min_v": "port_absent",
    }


def test_courant_de_repos_superieur_au_maximal() -> None:
    motifs = _motifs(
        {"ports.dc.current_standby_ma": 600.0, "ports.dc.current_peak_ma": 500.0}
    )
    assert set(motifs.values()) == {"repos_superieur_max"}


def test_courant_coherent_avec_la_puissance() -> None:
    # Hikvision : 12 V ± 20 %, 1,19 A, max. 14,28 W.
    valeurs: dict[str, Valeur] = {
        "ports.dc.voltage_min_v": 9.6,
        "ports.dc.voltage_max_v": 14.4,
        "ports.dc.current_peak_ma": 1190.0,
        "power_w_peak": 14.28,
    }
    assert _motifs(valeurs) == {}
    # 0,119 A lu 119 mA au lieu de 1 190 : V × I dix fois trop petit.
    motifs = _motifs({**valeurs, "ports.dc.current_peak_ma": 119.0})
    assert motifs == {"ports.dc.current_peak_ma": "courant_incoherent"}


@pytest.mark.parametrize(
    ("courant", "admis"),
    [(600.0, True), (594.0, False), (2375.0, True), (2390.0, False)],
)
def test_rapport_vi_bornes(courant: float, admis: bool) -> None:
    # 12 V, 14,28 W : 0,5 → 595 mA, 2 → 2 380 mA.
    valeurs: dict[str, Valeur] = {
        "ports.dc.voltage_min_v": 12.0,
        "ports.dc.voltage_max_v": 12.0,
        "power_w_peak": 14.28,
        "ports.dc.current_peak_ma": courant,
    }
    assert (_motifs(valeurs) == {}) is admis
