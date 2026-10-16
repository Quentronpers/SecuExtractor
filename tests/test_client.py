"""Client compatible OpenAI et réponses brutes, avec un faux transport.

Aucun appel réseau : le transport rend des réponses écrites à la main et
l'attente entre reprises est enregistrée au lieu d'être subie.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from catalog.extraction import brut
from catalog.extraction.brut import (
    EchecReponse,
    Message,
    RequeteModele,
)
from catalog.extraction.client import (
    ATTENTE_MAX_S,
    TENTATIVES_HTTP,
    ClientCompatibleOpenAI,
    ContexteInsuffisant,
    EchecAppel,
    ReponseHTTP,
    attente_reprise,
)


class Sortie(BaseModel):
    model_config = ConfigDict(extra="forbid")

    power_w_peak: float | None


SCHEMA = {
    "type": "object",
    "properties": {"power_w_peak": {"type": ["number", "null"]}},
    "required": ["power_w_peak"],
    "additionalProperties": False,
}


def requete(**changements: Any) -> RequeteModele:
    base: dict[str, Any] = {
        "modele": "qwen3:14b",
        "version_prompt": "v1",
        "messages": (Message(role="user", content="Max. 12,5 W"),),
        "nom_schema": "alimentation",
        "schema_sortie": SCHEMA,
    }
    return RequeteModele(**(base | changements))


def ok(contenu: str, finish_reason: str = "stop", **usage: int) -> ReponseHTTP:
    corps = {
        "choices": [
            {
                "message": {"content": contenu, "reasoning": "je lis"},
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 10},
    }
    return ReponseHTTP(statut=200, corps=corps)


class FauxTransport:
    """Rend les réponses prévues dans l'ordre et garde les requêtes reçues."""

    def __init__(self, *reponses: ReponseHTTP | OSError) -> None:
        """Les réponses sont rendues dans l'ordre ; une ``OSError`` est levée."""
        self.reponses = list(reponses)
        self.recus: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def __call__(
        self, url: str, entetes: dict[str, str], corps: dict[str, Any], delai_s: float
    ) -> ReponseHTTP:
        self.recus.append((url, entetes, corps))
        reponse = self.reponses.pop(0)
        if isinstance(reponse, OSError):
            raise reponse
        return reponse


def client(
    transport: FauxTransport, attentes: list[float], **options: Any
) -> ClientCompatibleOpenAI:
    return ClientCompatibleOpenAI(
        "http://ollama.test/v1/",
        transport=transport,
        dormir=attentes.append,
        **options,
    )


def test_json_valide_donne_un_objet_valide() -> None:
    transport = FauxTransport(ok('{"power_w_peak": 12.5}'))
    enregistrement = client(transport, [], cle_api="k").executer(requete(), Sortie)
    reponse = brut.interpreter(enregistrement, Sortie)
    assert reponse.valeur == Sortie(power_w_peak=12.5)
    assert reponse.reflexion == "je lis"
    assert reponse.finish_reason == "stop"
    url, entetes, corps = transport.recus[0]
    assert url == "http://ollama.test/v1/chat/completions"
    assert entetes["Authorization"] == "Bearer k"
    assert corps["response_format"]["json_schema"]["strict"] is True
    assert corps["temperature"] == 0.0
    assert "reasoning_effort" not in corps and "seed" not in corps


def test_reglages_fixes_sont_envoyes() -> None:
    transport = FauxTransport(ok('{"power_w_peak": null}'))
    client(transport, []).executer(requete(reasoning_effort="none", graine=7), Sortie)
    _, entetes, corps = transport.recus[0]
    assert corps["reasoning_effort"] == "none" and corps["seed"] == 7
    assert "Authorization" not in entetes


def test_troncature_est_un_echec_sans_nouvel_essai() -> None:
    transport = FauxTransport(ok('{"power_w_peak": 12.5}', finish_reason="length"))
    enregistrement = client(transport, []).executer(requete(), Sortie)
    assert len(enregistrement.essais) == 1
    with pytest.raises(EchecReponse) as echec:
        brut.interpreter(enregistrement, Sortie)
    assert echec.value.motif == "troncature"


@pytest.mark.parametrize(
    ("entree", "sortie", "motif"),
    [
        (8150, 10, "troncature_entree"),  # prompt coupé à la taille du contexte
        (4000, 4200, "decalage_contexte"),  # fenêtre décalée pendant la sortie
    ],
)
def test_coupe_silencieuse_d_ollama(entree: int, sortie: int, motif: str) -> None:
    reponse = ok('{"power_w_peak": 1}', prompt_tokens=entree, completion_tokens=sortie)
    transport = FauxTransport(reponse)
    r = requete(contexte_jetons=8192, max_jetons=512)
    enregistrement = client(transport, []).executer(r, Sortie)
    with pytest.raises(EchecReponse) as echec:
        brut.interpreter(enregistrement, Sortie)
    assert echec.value.motif == motif


def test_usage_sans_valeurs_ne_plante_pas() -> None:
    corps = ok('{"power_w_peak": 1}').corps or {}
    corps["usage"] = {"prompt_tokens": None, "completion_tokens": None}
    transport = FauxTransport(ReponseHTTP(statut=200, corps=corps))
    r = requete(contexte_jetons=8192, max_jetons=512)
    enregistrement = client(transport, []).executer(r, Sortie)
    assert brut.interpreter(enregistrement, Sortie).valeur.power_w_peak == 1


def test_contexte_trop_court_refuse_avant_envoi() -> None:
    transport = FauxTransport()
    r = requete(contexte_jetons=4096, max_jetons=4096)
    with pytest.raises(ContexteInsuffisant):
        client(transport, []).executer(r, Sortie)
    assert transport.recus == []


def test_json_malforme_redemande_une_fois_avec_une_autre_graine() -> None:
    transport = FauxTransport(ok('{"power_w_peak": '), ok('{"power_w_peak": 7}'))
    enregistrement = client(transport, []).executer(requete(graine=5), Sortie)
    assert len(enregistrement.essais) == 2
    assert [corps["seed"] for _, _, corps in transport.recus] == [5, 6]
    assert [e.graine for e in enregistrement.essais] == [5, 6]
    reponse = brut.interpreter(enregistrement, Sortie)
    assert reponse.essai == 1 and reponse.valeur.power_w_peak == 7


def test_400_de_schema_de_groq_archive_et_redemande() -> None:
    erreur = {"error": {"code": "json_validate_failed", "message": "Generated JSON"}}
    transport = FauxTransport(
        ReponseHTTP(statut=400, corps=erreur), ReponseHTTP(statut=400, corps=erreur)
    )
    attentes: list[float] = []
    enregistrement = client(transport, attentes).executer(requete(), Sortie)
    assert len(enregistrement.essais) == 2 and attentes == []
    with pytest.raises(EchecReponse) as echec:
        brut.interpreter(enregistrement, Sortie)
    assert echec.value.motif == "schema_invalide"


def test_nouvel_essai_coupe_garde_le_premier() -> None:
    erreur_client = ReponseHTTP(statut=400, corps=None)
    transport = FauxTransport(ok("pas du json"), erreur_client)
    enregistrement = client(transport, []).executer(requete(), Sortie)
    assert len(enregistrement.essais) == 1


def test_champ_de_limite_par_fournisseur() -> None:
    transport = FauxTransport(ok('{"power_w_peak": 1}'))
    groq = client(transport, [], champ_max_jetons="max_completion_tokens")
    groq.executer(requete(max_jetons=900), Sortie)
    corps = transport.recus[0][2]
    assert corps["max_completion_tokens"] == 900 and "max_tokens" not in corps


@pytest.mark.parametrize(
    ("contenu", "motif"),
    [("pas du json", "json_malforme"), ('{"autre": 1}', "schema_invalide")],
)
def test_reponse_illisible_deux_fois_est_un_echec(contenu: str, motif: str) -> None:
    transport = FauxTransport(ok(contenu), ok(contenu))
    enregistrement = client(transport, []).executer(requete(), Sortie)
    assert len(enregistrement.essais) == 2
    with pytest.raises(EchecReponse) as echec:
        brut.interpreter(enregistrement, Sortie)
    assert echec.value.motif == motif


def test_429_attend_puis_reussit() -> None:
    limite = ReponseHTTP(statut=429, corps=None, entetes={"retry-after": "7"})
    transport = FauxTransport(limite, ok('{"power_w_peak": 3}'))
    attentes: list[float] = []
    enregistrement = client(transport, attentes).executer(requete(), Sortie)
    assert attentes == [7.0]
    assert brut.interpreter(enregistrement, Sortie).valeur.power_w_peak == 3


def test_erreur_reseau_reprise_avec_attente_croissante() -> None:
    coupe = OSError("coupé")
    transport = FauxTransport(coupe, coupe, ok('{"power_w_peak": 1}'))
    attentes: list[float] = []
    client(transport, attentes).executer(requete(), Sortie)
    assert attentes == [attente_reprise(0, {}), attente_reprise(1, {})]
    assert attentes[0] < attentes[1]


def test_429_persistant_abandonne() -> None:
    limite = ReponseHTTP(statut=429, corps=None)
    transport = FauxTransport(*[limite] * TENTATIVES_HTTP)
    attentes: list[float] = []
    with pytest.raises(EchecAppel, match="429"):
        client(transport, attentes).executer(requete(), Sortie)
    assert len(attentes) == TENTATIVES_HTTP - 1


def test_erreur_client_sans_reprise() -> None:
    transport = FauxTransport(ReponseHTTP(statut=400, corps=None, texte="schema"))
    attentes: list[float] = []
    with pytest.raises(EchecAppel, match="400"):
        client(transport, attentes).executer(requete(), Sortie)
    assert attentes == []


def test_attente_plafonnee() -> None:
    assert attente_reprise(30, {}) == ATTENTE_MAX_S
    assert attente_reprise(0, {"Retry-After": "demain"}) == attente_reprise(0, {})


def test_quota_du_jour_epuise_arrete_net() -> None:
    limite = ReponseHTTP(statut=429, corps=None, entetes={"Retry-After": "9999"})
    transport = FauxTransport(limite)
    attentes: list[float] = []
    with pytest.raises(EchecAppel, match="quota"):
        client(transport, attentes).executer(requete(), Sortie)
    assert attentes == [] and len(transport.recus) == 1


@pytest.mark.parametrize(
    "panne",
    [ReponseHTTP(statut=503, corps=None), ReponseHTTP(statut=200, corps=None)],
)
def test_panne_serveur_reprise_puis_reussite(panne: ReponseHTTP) -> None:
    transport = FauxTransport(panne, ok('{"power_w_peak": 2}'))
    attentes: list[float] = []
    enregistrement = client(transport, attentes).executer(requete(), Sortie)
    assert len(attentes) == 1 and len(enregistrement.essais) == 1


def test_200_sans_corps_persistant_dit_pourquoi() -> None:
    transport = FauxTransport(*[ReponseHTTP(statut=200, corps=None)] * TENTATIVES_HTTP)
    with pytest.raises(EchecAppel, match="sans corps JSON"):
        client(transport, []).executer(requete(), Sortie)
