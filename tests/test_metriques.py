"""Métriques : un cas construit à la main donne exactement les taux attendus."""

from __future__ import annotations

import pytest

from catalog.evaluation.metriques import (
    Cellule,
    Compte,
    bootstrap,
    bootstrap_apparie,
    compter,
    egales,
    proches,
    regrouper,
    taux,
    total,
)

# A : une valeur juste, un absent des deux côtés, une valeur manquée.
# B : une maximale sous-estimée (douteux), une typique inventée (sur).
# C : notice en échec technique.
CAS = [
    Cellule("a", 0, "power_w_peak", 10.7, 10.7, "sur"),
    Cellule("a", 0, "ports.dc.voltage_min_v", None, None, "absent"),
    Cellule("a", 0, "power_w", 4.8, None, "absent"),
    Cellule("b", 0, "power_w_peak", 12.0, 10.0, "douteux", "valeur_non_maximale"),
    Cellule("b", 0, "power_w", None, 5.0, "sur"),
    Cellule("c", 0, "power_w_peak", 8.0, None, None),
]


def test_cas_construit_a_la_main() -> None:
    assert taux(total(CAS)) == {
        "precision": pytest.approx(1 / 3),
        "precision_sur": 0.5,
        "rappel": 0.25,
        "exactitude": pytest.approx(2 / 6),
        "invention": 0.5,
        "sous_estimation": 0.5,
        "citations_suspectes": 0.0,
        "tri_douteux": 0.5,
        "tri_douteux_controles": 0.5,
        "proches": 0.0,
        "echecs": pytest.approx(1 / 6),
    }


def test_absent_des_deux_cotes_juste_et_hors_precision() -> None:
    c = compter(Cellule("a", 0, "power_w", None, None, "absent"))
    assert (c.justes, c.produits, c.presents, c.absents) == (1, 0, 0, 1)


def test_valeur_fausse_est_faux_positif_et_faux_negatif() -> None:
    c = compter(Cellule("a", 0, "power_w", 4.8, 5.2, "sur"))
    assert (c.produits, c.vp, c.presents, c.erreurs) == (1, 0, 1, 1)


def test_surestimation_n_est_pas_sous_estimation() -> None:
    c = compter(Cellule("a", 0, "ports.poe.power_w", 10.0, 12.0, "sur"))
    assert (c.puissances, c.sous_estimations) == (1, 0)
    autre = compter(Cellule("a", 0, "power_w", 10.0, 8.0, "sur"))
    assert autre.puissances == 0


def test_doute_du_modele_seul_hors_tri_des_controles() -> None:
    c = compter(Cellule("a", 0, "power_w", 4.8, 5.2, "douteux", "doute_modele"))
    assert (c.erreurs_douteux, c.erreurs_douteux_controles) == (1, 0)


def test_citation_suspecte_comptee() -> None:
    regle = "citation_recomposee; doute_modele"
    c = compter(Cellule("a", 0, "power_w", 4.8, 4.8, "douteux", regle))
    assert c.citations_suspectes == 1 and c.vp == 1


def test_egalite_normalisee() -> None:
    assert egales(10.7, 10.704)
    assert not egales(10.7, 10.8)
    assert egales("3", "3") and not egales("3", 3.0)
    assert egales(False, False) and not egales(True, 1.0)
    assert egales(None, None)


def test_proches_a_un_pour_cent_jamais_justes() -> None:
    assert proches(100.0, 100.9)
    assert not proches(100.0, 102.0)
    assert not proches(10.7, 10.7)
    assert not proches(True, True)


def test_taux_sans_denominateur() -> None:
    assert all(v is None for v in taux(Compte()).values())


def test_regrouper_par_document() -> None:
    groupes = regrouper(CAS, "document")
    assert sorted(groupes) == ["a", "b", "c"]
    assert sum(groupes.values(), Compte()) == total(CAS)


def test_bootstrap_reproductible_et_encadrant() -> None:
    par_document = regrouper(CAS, "document")
    premier = bootstrap(par_document, tirages=300)
    assert premier == bootstrap(par_document, tirages=300)
    bas, haut = premier["exactitude"] or (1.0, 0.0)
    assert bas <= 2 / 6 <= haut


def test_bootstrap_vide() -> None:
    assert all(v is None for v in bootstrap({}).values())


def test_bootstrap_apparie_sur_soi_meme_nul() -> None:
    par_document = regrouper(CAS, "document")
    assert bootstrap_apparie(par_document, par_document, "rappel", 200) == (0.0, 0.0)
