"""Runner : état final des champs à partir d'une réponse simulée du modèle.

Aucun appel réseau : le modèle est remplacé par une fonction qui rend un
enregistrement brut écrit à la main.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from catalog.extraction import runner
from catalog.extraction.brut import (
    ArchiveBrute,
    EnregistrementBrut,
    EssaiBrut,
    RequeteModele,
)
from catalog.extraction.cible import charger_cible
from catalog.extraction.client import EchecAppel
from catalog.extraction.runner import (
    ConfigModele,
    Document,
    Moteur,
    ResultatBloc,
    construire_requete,
    executer_lot,
    extraire_document,
)
from catalog.reading.page import Page

CIBLE = charger_cible("camera", "alimentation")
PAGES = [
    Page(
        numero=5,
        texte="Power\nPower over Ethernet (PoE) IEEE 802.3af/802.3at Type 1 Class 3\n"
        "Typical 4.8 W, max 10.7 W",
    )
]
DOCUMENT = Document(id="axis-01", reference="AXIS P3265-LVE", chemin=Path("x.pdf"))
CONFIG = ConfigModele(modele="qwen3:14b", contexte_jetons=16384, empreinte_modele="d")


def rendu(
    valeur: Any, extrait: str | None = None, page: int | None = 5, doute: bool = False
) -> dict[str, Any]:
    return {"extrait": extrait, "page": page, "valeur": valeur, "doute": doute}


def reponse_correcte() -> dict[str, Any]:
    vide = rendu(None, page=None)
    poe = "Power over Ethernet (PoE) IEEE 802.3af/802.3at Type 1 Class 3"
    return {
        "ports.poe": rendu(True, poe),
        "ports.dc": rendu(False, poe),
        "power_w": rendu(4.8, "Typical 4.8 W, max 10.7 W"),
        "power_w_peak": rendu(10.7, "Typical 4.8 W, max 10.7 W"),
        "ports.poe.class": rendu("3", poe),
        "ports.poe.power_w": rendu(10.7, "Typical 4.8 W, max 10.7 W"),
        "ports.poe.min_standard": rendu("802.3af", poe),
        "ports.dc.voltage_min_v": vide,
        "ports.dc.voltage_max_v": vide,
        "ports.dc.current_standby_ma": vide,
        "ports.dc.current_peak_ma": vide,
    }


class FauxModele:
    """Rend une réponse écrite à la main et compte les appels."""

    def __init__(self, contenu: dict[str, Any] | str, finish: str = "stop") -> None:
        """``contenu`` : objet sérialisé en JSON, ou texte brut tel quel."""
        self.texte = contenu if isinstance(contenu, str) else json.dumps(contenu)
        self.finish = finish
        self.appels = 0

    def __call__(self, requete: RequeteModele) -> EnregistrementBrut:
        self.appels += 1
        corps = {
            "choices": [
                {"message": {"content": self.texte}, "finish_reason": self.finish}
            ],
            "usage": {"prompt_tokens": 900, "completion_tokens": 300},
        }
        essai = EssaiBrut(corps=corps, duree_s=12.0, horodatage="2026-10-16T10:00:00")
        return EnregistrementBrut(cle=requete.cle(), requete=requete, essais=[essai])


def extraire(
    contenu: dict[str, Any] | str, tmp_path: Path, finish: str = "stop"
) -> ResultatBloc:
    moteur = Moteur(CONFIG, ArchiveBrute(tmp_path), FauxModele(contenu, finish))
    return extraire_document(DOCUMENT, PAGES, CIBLE, 0, moteur)


def test_reponse_correcte_donne_sur(tmp_path: Path) -> None:
    resultat = extraire(reponse_correcte(), tmp_path)
    assert resultat.motif_echec is None
    champs = resultat.champs
    assert champs["power_w_peak"].etat == "sur"
    assert champs["power_w_peak"].valeur == 10.7
    assert champs["ports.poe.class"].etat == "sur"
    assert champs["ports.dc.voltage_min_v"].etat == "absent"
    assert all(c.regle_echouee is None for c in champs.values())
    assert resultat.duree_s == 12.0 and resultat.pages == [5]


def test_extrait_introuvable_donne_douteux(tmp_path: Path) -> None:
    contenu = reponse_correcte()
    contenu["power_w_peak"] = rendu(10.7, "Maximum consumption 10.7 W")
    champ = extraire(contenu, tmp_path).champs["power_w_peak"]
    assert champ.etat == "douteux"
    assert champ.regle_echouee == "citation_introuvable"


def test_valeur_nulle_donne_absent_meme_avec_doute(tmp_path: Path) -> None:
    contenu = reponse_correcte()
    contenu["ports.poe.class"] = rendu(None, "Class 3", doute=True)
    champ = extraire(contenu, tmp_path).champs["ports.poe.class"]
    assert (champ.etat, champ.valeur) == ("absent", None)


def test_champ_non_rendu_est_un_echec(tmp_path: Path) -> None:
    contenu = reponse_correcte()
    del contenu["power_w"]
    resultat = extraire(contenu, tmp_path)
    assert resultat.motif_echec == "schema_invalide"
    assert resultat.champs == {}


def test_doute_du_modele_donne_douteux(tmp_path: Path) -> None:
    contenu = reponse_correcte()
    contenu["power_w"] = rendu(4.8, "Typical 4.8 W, max 10.7 W", doute=True)
    champ = extraire(contenu, tmp_path).champs["power_w"]
    assert (champ.etat, champ.regle_echouee) == ("douteux", "doute_modele")


def test_type_invalide_donne_douteux_et_echappe_aux_regles(tmp_path: Path) -> None:
    contenu = reponse_correcte()
    contenu["power_w_peak"] = rendu("10.7", "Typical 4.8 W, max 10.7 W")
    champs = extraire(contenu, tmp_path).champs
    assert champs["power_w_peak"].regle_echouee == "type_invalide"
    # Sans maximale lisible, power_w n'est pas comparé à une chaîne.
    assert champs["power_w"].etat == "sur"


def test_plausibilite_en_echec_donne_douteux(tmp_path: Path) -> None:
    contenu = reponse_correcte()
    pages = [Page(numero=5, texte=PAGES[0].texte + "\nMax 1070 W")]
    contenu["power_w_peak"] = rendu(1070.0, "Max 1070 W")
    moteur = Moteur(CONFIG, ArchiveBrute(tmp_path), FauxModele(contenu))
    champ = extraire_document(DOCUMENT, pages, CIBLE, 0, moteur).champs["power_w_peak"]
    assert champ.etat == "douteux"
    assert champ.regle_echouee is not None and "hors_bornes" in champ.regle_echouee


def test_motifs_cumules(tmp_path: Path) -> None:
    contenu = reponse_correcte()
    contenu["power_w_peak"] = rendu(10.7, "max 10.7 W", page=2, doute=True)
    champ = extraire(contenu, tmp_path).champs["power_w_peak"]
    assert champ.regle_echouee == "citation_autre_page; doute_modele"


def test_troncature_est_un_echec_sans_champs(tmp_path: Path) -> None:
    resultat = extraire(reponse_correcte(), tmp_path, finish="length")
    assert resultat.motif_echec == "troncature"
    assert resultat.champs == {}


def test_json_malforme_est_un_echec(tmp_path: Path) -> None:
    resultat = extraire('{"ports.poe": ', tmp_path)
    assert resultat.motif_echec == "json_malforme"


def test_echec_d_appel_n_est_pas_archive(tmp_path: Path) -> None:
    def en_panne(requete: RequeteModele) -> EnregistrementBrut:
        raise EchecAppel("réseau : refusé")

    moteur = Moteur(CONFIG, ArchiveBrute(tmp_path), en_panne)
    resultat = extraire_document(DOCUMENT, PAGES, CIBLE, 0, moteur)
    assert resultat.motif_echec == "echec_appel"
    assert list(tmp_path.iterdir()) == []


def test_reponse_archivee_rejouee_sans_appel(tmp_path: Path) -> None:
    modele = FauxModele(reponse_correcte())
    moteur = Moteur(CONFIG, ArchiveBrute(tmp_path), modele)
    premier = extraire_document(DOCUMENT, PAGES, CIBLE, 0, moteur)
    second = extraire_document(DOCUMENT, PAGES, CIBLE, 0, moteur)
    assert modele.appels == 1
    assert premier == second


def test_requete_porte_reference_reglages_et_execution() -> None:
    requete = construire_requete(CIBLE, "AXIS P3265-LVE", PAGES, CONFIG, 2)
    assert "Target reference: AXIS P3265-LVE" in requete.messages[1].content
    assert "=== Page 5 ===" in requete.messages[1].content
    assert requete.reasoning_effort == "none"
    assert (requete.contexte_jetons, requete.empreinte_modele) == (16384, "d")
    autre = construire_requete(CIBLE, "AXIS P3265-LVE", PAGES, CONFIG, 3)
    assert requete.cle() != autre.cle()


def test_lot_lit_une_fois_et_ecrit_chaque_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lectures: list[Path] = []

    def lire(chemin: Path) -> list[Page]:
        lectures.append(chemin)
        return PAGES

    monkeypatch.setattr(runner, "lire_document", lire)
    modele = FauxModele(reponse_correcte())
    moteur = Moteur(CONFIG, ArchiveBrute(tmp_path / "brut"), modele)
    sortie = tmp_path / "resultats"
    resultats = list(executer_lot([DOCUMENT], CIBLE, moteur, 2, sortie))
    assert lectures == [DOCUMENT.chemin]
    assert [r.execution for r in resultats] == [0, 1]
    assert modele.appels == 2
    relu = json.loads((sortie / "axis-01_e1.json").read_text(encoding="utf-8"))
    assert relu["champs"]["power_w_peak"]["etat"] == "sur"
