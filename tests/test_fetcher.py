"""Fetcher : contact obligatoire, reprises, redirections contrôlées, causes d'échec.

Aucun appel réseau : ``requests.get`` et ``time.sleep`` sont remplacés.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import requests

from catalog.acquisition import fetcher, robots

CADENCE_S = 2.5


def _reponse(statut: int, headers: dict[str, str] | None = None) -> requests.Response:
    reponse = requests.Response()
    reponse.status_code = statut
    reponse._content = b"%PDF-1.7 contenu"
    reponse.headers.update(headers or {})
    return reponse


@pytest.fixture
def faux_reseau(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, list]]:
    """Contact défini, robots.txt tout permis, attentes enregistrées sans dormir."""
    monkeypatch.setenv("SECURSCOPE_CONTACT", "robot@exemple.test")
    monkeypatch.setattr(fetcher, "_robots_cache", {})
    monkeypatch.setattr(fetcher, "_dernier_acces", {})
    monkeypatch.setattr(fetcher, "_causes", {})
    monkeypatch.setattr(fetcher, "_lire_robots", lambda url: robots.TOUT_AUTORISE)
    journal: dict[str, list] = {"attentes": [], "urls": []}
    monkeypatch.setattr(fetcher.time, "sleep", journal["attentes"].append)
    monkeypatch.setattr(fetcher.random, "uniform", lambda a, b: CADENCE_S)
    monkeypatch.setattr(fetcher.time, "monotonic", lambda: 100.0)
    yield journal


def _servir(
    monkeypatch: pytest.MonkeyPatch, journal: dict[str, list], reponses: list
) -> None:
    def get(url: str, **kwargs: object) -> requests.Response:
        assert kwargs["allow_redirects"] is False
        journal["urls"].append(url)
        suivante = reponses.pop(0)
        if isinstance(suivante, Exception):
            raise suivante
        return suivante

    monkeypatch.setattr(fetcher.requests, "get", get)


def _attentes_de_reprise(journal: dict[str, list]) -> list[float]:
    """Les attentes de reprise, hors attentes de cadence entre deux requêtes."""
    return [a for a in journal["attentes"] if a != CADENCE_S]


def test_sans_contact_aucune_requete_ne_part(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECURSCOPE_CONTACT", raising=False)

    with pytest.raises(fetcher.ContactManquant):
        fetcher.user_agent()


def test_user_agent_porte_le_jeton_et_le_contact(
    faux_reseau: dict[str, list],
) -> None:
    assert fetcher.user_agent() == (
        "SecurScopeCatalogBot/0.1 (+mailto:robot@exemple.test)"
    )


def test_trois_erreurs_serveur_abandonnent_apres_trois_tentatives(
    faux_reseau: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    _servir(monkeypatch, faux_reseau, [_reponse(503)] * 3)

    assert fetcher.fetch_binaire("https://s.test/a.pdf") is None
    assert len(faux_reseau["urls"]) == 3
    assert _attentes_de_reprise(faux_reseau) == [2.0, 4.0]
    assert fetcher.cause_echec("https://s.test/a.pdf") == "HTTP 503"


def test_une_erreur_reseau_puis_un_succes_rend_le_document(
    faux_reseau: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    _servir(monkeypatch, faux_reseau, [requests.ConnectTimeout(), _reponse(200)])

    assert fetcher.fetch_binaire("https://s.test/a.pdf") == b"%PDF-1.7 contenu"
    assert len(faux_reseau["urls"]) == 2


@pytest.mark.parametrize("statut", [403, 404, 410])
def test_une_erreur_client_n_est_pas_retentee(
    faux_reseau: dict[str, list], monkeypatch: pytest.MonkeyPatch, statut: int
) -> None:
    _servir(monkeypatch, faux_reseau, [_reponse(statut)])

    assert fetcher.fetch_binaire("https://s.test/a.pdf") is None
    assert len(faux_reseau["urls"]) == 1
    assert fetcher.cause_echec("https://s.test/a.pdf") == f"HTTP {statut}"


def test_un_429_attend_le_retry_after_plafonne(
    faux_reseau: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    reponses = [
        _reponse(429, {"Retry-After": "30"}),
        _reponse(429, {"Retry-After": "900"}),
    ]
    _servir(monkeypatch, faux_reseau, [*reponses, _reponse(200)])

    assert fetcher.fetch_binaire("https://s.test/a.pdf") is not None
    assert _attentes_de_reprise(faux_reseau) == [30.0, 60.0]


def test_une_redirection_vers_un_chemin_interdit_n_est_pas_suivie(
    faux_reseau: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    interdit = robots.analyser("User-agent: *\nDisallow: /prive/\n", "Bot")
    monkeypatch.setattr(fetcher, "_lire_robots", lambda url: interdit)
    redirection = _reponse(302, {"Location": "/prive/a.pdf"})
    _servir(monkeypatch, faux_reseau, [redirection])

    assert fetcher.fetch_binaire("https://s.test/public/a.pdf") is None
    assert faux_reseau["urls"] == ["https://s.test/public/a.pdf"]
    assert "robots.txt" in fetcher.cause_echec("https://s.test/public/a.pdf")


def test_une_redirection_autorisee_est_suivie(
    faux_reseau: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    redirection = _reponse(301, {"Location": "https://cdn.s.test/a.pdf"})
    _servir(monkeypatch, faux_reseau, [redirection, _reponse(200)])

    assert fetcher.fetch_binaire("https://s.test/a.pdf") is not None
    assert faux_reseau["urls"] == ["https://s.test/a.pdf", "https://cdn.s.test/a.pdf"]


def test_trop_de_redirections_abandonnent(
    faux_reseau: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    boucle = [_reponse(302, {"Location": "/a"}) for _ in range(10)]
    _servir(monkeypatch, faux_reseau, boucle)

    assert fetcher.fetch_binaire("https://s.test/a") is None
    assert len(faux_reseau["urls"]) == fetcher.REDIRECTIONS_MAX + 1


def test_cadence_de_deux_a_trois_secondes_par_domaine(
    faux_reseau: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:

    fetcher._attendre_cadence("s.test")
    fetcher._attendre_cadence("s.test")
    fetcher._attendre_cadence("autre.test")

    (attente,) = faux_reseau["attentes"]
    assert attente == CADENCE_S
