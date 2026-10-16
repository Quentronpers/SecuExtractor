"""Réponses brutes : clé d'empreinte, archive et relecture sans appel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from catalog.extraction import brut
from catalog.extraction.brut import (
    ArchiveBrute,
    EchecReponse,
    EnregistrementBrut,
    RequeteModele,
)
from catalog.extraction.client import EchecAppel, ReponseHTTP
from tests.test_client import FauxTransport, Sortie, client, ok, requete


def test_meme_cle_rejouee_sans_appel(tmp_path: Path) -> None:
    transport = FauxTransport(ok('{"power_w_peak": 12.5}'))
    appel = client(transport, [])

    def executer(r: RequeteModele) -> EnregistrementBrut:
        return appel.executer(r, Sortie)

    premier = brut.obtenir(ArchiveBrute(tmp_path), requete(), executer)
    second = brut.obtenir(ArchiveBrute(tmp_path), requete(), executer)
    assert len(transport.recus) == 1
    assert second == premier


def test_cle_depend_de_l_execution_pas_du_serveur() -> None:
    assert requete().cle() == requete().cle()
    assert requete(execution=1).cle() != requete().cle()
    assert requete(reasoning_effort="low").cle() != requete().cle()
    assert "url" not in json.dumps(requete().model_dump()).lower()


def test_cle_depend_du_contexte_et_du_digest() -> None:
    # Un contexte relevé ou un modèle retiré sous le même nom : nouvel appel.
    assert requete(contexte_jetons=8192).cle() != requete(contexte_jetons=16384).cle()
    assert requete(empreinte_modele="a1").cle() != requete(empreinte_modele="b2").cle()


def test_echec_de_transport_n_est_pas_archive(tmp_path: Path) -> None:
    transport = FauxTransport(ReponseHTTP(statut=401, corps=None))
    appel = client(transport, [])
    archive = ArchiveBrute(tmp_path)
    with pytest.raises(EchecAppel):
        brut.obtenir(archive, requete(), lambda r: appel.executer(r, Sortie))
    assert archive.lire(requete().cle()) is None


def test_fichier_qui_ne_correspond_pas_a_sa_cle(tmp_path: Path) -> None:
    archive = ArchiveBrute(tmp_path)
    enregistrement = EnregistrementBrut(cle="faux", requete=requete(), essais=[])
    archive.ecrire(enregistrement)
    with pytest.raises(ValueError, match="ne correspond pas"):
        archive.lire("faux")


def test_enregistrement_sans_essai() -> None:
    vide = EnregistrementBrut(cle=requete().cle(), requete=requete(), essais=[])
    with pytest.raises(EchecReponse) as echec:
        brut.interpreter(vide, Sortie)
    assert echec.value.motif == "aucune_reponse"
