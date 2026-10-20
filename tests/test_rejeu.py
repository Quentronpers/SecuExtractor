"""Rejeu depuis les réponses brutes et rapport, sans modèle ni notice."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from catalog.evaluation import rapport
from catalog.evaluation.evaluate import evaluer_run
from catalog.evaluation.reference import Corrige, ValeurAnnotee
from catalog.evaluation.rejeu import RejeuImpossible, pages_envoyees, rejouer
from catalog.extraction.brut import ArchiveBrute, Message
from catalog.extraction.runner import (
    ResultatBloc,
    construire_requete,
    executer_lot,
)
from catalog.reading.page import Page
from tests.test_runner import (
    CIBLE,
    CONFIG,
    DOCUMENT,
    PAGES,
    FauxModele,
    extraire,
    rendu,
    reponse_correcte,
)


def corrige(peak: float = 10.7) -> Corrige:
    """Le corrigé de la notice des tests du runner."""
    champs = {}
    for cle, r in reponse_correcte().items():
        valeur = peak if cle == "power_w_peak" else r["valeur"]
        champs[cle] = ValeurAnnotee(
            valeur=valeur,
            etat_attendu="absent" if valeur is None else "sur",
            page=None if valeur is None else 5,
            extrait=r["extrait"],
        )
    return Corrige(
        id="axis-01",
        reference=DOCUMENT.reference,
        sha256="0" * 64,
        annotateur="test",
        date_annotation=date(2026, 10, 16),
        champs=champs,
    )


def test_pages_reconstruites_a_l_identique() -> None:
    pages = [
        Page(numero=2, texte="Titre\n\nPoE Class 3", titre="Power"),
        Page(numero=7, texte="12 VDC\n=== pas un en-tête"),
    ]
    requete = construire_requete(CIBLE, "REF-1", pages, CONFIG, 0)
    assert pages_envoyees(requete) == pages


def test_message_illisible_refuse() -> None:
    requete = construire_requete(CIBLE, "REF-1", PAGES, CONFIG, 0)
    abime = requete.model_copy(
        update={"messages": (Message(role="user", content="autre chose"),)}
    )
    with pytest.raises(RejeuImpossible):
        pages_envoyees(abime)


def test_rejeu_redonne_le_resultat(tmp_path: Path) -> None:
    initial = extraire(reponse_correcte(), tmp_path)
    rejoue = rejouer(initial, ArchiveBrute(tmp_path), CIBLE)
    assert rejoue == initial


def test_rejeu_applique_les_controles_courants(tmp_path: Path) -> None:
    contenu = reponse_correcte()
    contenu["power_w"] = rendu(None, "Typical 4.8 W", doute=True)
    initial = extraire(contenu, tmp_path)
    falsifie = initial.model_copy(update={"champs": {}, "incoherents": []})
    rejoue = rejouer(falsifie, ArchiveBrute(tmp_path), CIBLE)
    assert rejoue.champs == initial.champs
    assert rejoue.incoherents == ["power_w"]


def test_rejeu_d_un_echec_archive(tmp_path: Path) -> None:
    initial = extraire("pas du JSON", tmp_path)
    rejoue = rejouer(initial, ArchiveBrute(tmp_path), CIBLE)
    assert rejoue.motif_echec == "json_malforme" and rejoue.champs == {}


def test_sans_reponse_archivee_le_resultat_reste(tmp_path: Path) -> None:
    resultat = ResultatBloc(
        document="axis-01",
        reference="R",
        sha256="",
        execution=0,
        modele="m",
        version_prompt="v",
        pages=[],
        cle_brute="0" * 64,
        motif_echec="echec_appel",
    )
    assert rejouer(resultat, ArchiveBrute(tmp_path), CIBLE) == resultat


def test_evaluer_un_dossier_d_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from catalog.extraction import runner
    from catalog.extraction.runner import Moteur

    monkeypatch.setattr(runner, "lire_document", lambda chemin: PAGES)
    archive = ArchiveBrute(tmp_path / "brut")
    moteur = Moteur(CONFIG, archive, FauxModele(reponse_correcte()))
    sortie = tmp_path / "run"
    list(executer_lot([DOCUMENT], CIBLE, moteur, 2, sortie))
    (sortie / "execution.json").write_text(json.dumps({"modele": "qwen3:14b"}))
    resultats, meta = evaluer_run(sortie, CIBLE, archive)
    construit = rapport.construire(resultats, {"axis-01": corrige()}, meta)
    assert construit["global"]["exactitude"] == 1.0
    assert construit["effectifs"]["cellules"] == 22
    assert construit["meta"]["modele"] == "qwen3:14b"
    assert construit["par_execution"]["precision"]["min"] == 1.0
    assert construit["erreurs"] == []
    assert construit["meta"]["commit_evaluation"] is not None


def test_rapport_liste_les_erreurs_et_s_ecrit(tmp_path: Path) -> None:
    resultat = extraire(reponse_correcte(), tmp_path)
    construit = rapport.construire([resultat], {"axis-01": corrige(12.0)}, {})
    assert [e["cle"] for e in construit["erreurs"]] == ["power_w_peak"]
    assert construit["global"]["sous_estimation"] == 0.5
    chemin = rapport.ecrire(construit, "essai", tmp_path / "rapports")
    assert json.loads(chemin.read_text())["notices"] == ["axis-01"]
    assert "| `power_w_peak` | 1 | 1 |" in chemin.with_suffix(".md").read_text()


def test_resultat_sans_corrige_ignore(tmp_path: Path) -> None:
    resultat = extraire(reponse_correcte(), tmp_path)
    assert rapport.cellules([resultat], {}) == []


def test_comparaison_appariee(tmp_path: Path) -> None:
    from catalog.evaluation import comparaison

    juste = extraire(reponse_correcte(), tmp_path)
    bon = rapport.construire([juste], {"axis-01": corrige()}, {})
    mauvais = rapport.construire([juste], {"axis-01": corrige(12.0)}, {})
    chemins = []
    for nom, r in (("bon", bon), ("mauvais", mauvais)):
        chemins.append(rapport.ecrire(r, nom, tmp_path / "rapports"))
    a, b = (comparaison.charger_comptes(c) for c in chemins)
    resultat = comparaison.comparer(a, b)
    assert resultat["notices"] == {"communes": 1}
    assert resultat["exactitude"]["ecart"] == pytest.approx(1 / 11)
    assert resultat["exactitude"]["ic"] == pytest.approx((1 / 11, 1 / 11))
    assert "| exactitude | 100.0 % |" in comparaison.markdown(
        "bon", "mauvais", resultat
    )


def test_rapport_sans_effectifs_par_notice(tmp_path: Path) -> None:
    from catalog.evaluation import comparaison

    ancien = tmp_path / "ancien.json"
    ancien.write_text(json.dumps({"global": {}}))
    with pytest.raises(comparaison.RapportIncomplet):
        comparaison.charger_comptes(ancien)


def test_run_reduit_aux_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    from catalog.evaluation import evaluate
    from catalog.extraction import runner
    from catalog.extraction.runner import Moteur

    monkeypatch.setattr(runner, "lire_document", lambda chemin: PAGES)
    archive = ArchiveBrute(tmp_path / "brut")
    monkeypatch.setattr(evaluate, "ArchiveBrute", lambda: archive)
    moteur = Moteur(CONFIG, archive, FauxModele(reponse_correcte()))
    autre = DOCUMENT.model_copy(update={"id": "axis-02"})
    list(executer_lot([DOCUMENT, autre], CIBLE, moteur, 1, tmp_path / "run"))
    corriges = {"axis-01": corrige(), "axis-02": corrige()}
    args = argparse.Namespace(run=tmp_path / "run", ids="axis-02")
    construit, nom = evaluate._rapport_run(args, CIBLE, corriges)
    assert construit["notices"] == ["axis-02"]
    assert nom.startswith("run_ids1-") and construit["meta"]["ids"] == "axis-02"
    with pytest.raises(SystemExit):
        evaluate._rapport_run(
            argparse.Namespace(run=tmp_path / "run", ids="hik-09"), CIBLE, corriges
        )


def test_comparaison_refuse_deux_corriges(tmp_path: Path) -> None:
    from catalog.evaluation import comparaison

    resultat = extraire(reponse_correcte(), tmp_path)
    chemins = [
        rapport.ecrire(
            rapport.construire([resultat], {"axis-01": corrige(peak)}, {}),
            f"r{i}",
            tmp_path / "rapports",
        )
        for i, peak in enumerate((10.7, 12.0))
    ]
    with pytest.raises(comparaison.CorrigesDifferents):
        comparaison.provenance(chemins)
    meta = comparaison.provenance([chemins[0], chemins[0]])
    assert meta["a"] == "r0.json" and meta["tirages"] == 2000
