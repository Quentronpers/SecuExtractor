"""Bootstrap apparié et intervalle : verdicts « départagés » sur des cas connus."""

from __future__ import annotations

from catalog.evaluation import comparaison
from catalog.evaluation.metriques import Compte, _intervalle


def _notice(justes: int, cellules: int = 10) -> Compte:
    return Compte(cellules=cellules, justes=justes)


def test_intervalle_a_95_pour_cent_d_une_liste_de_0_a_1999() -> None:
    assert _intervalle([float(v) for v in range(2000)]) == (49.0, 1950.0)


def test_intervalle_vide_sans_tirage() -> None:
    assert _intervalle([]) is None


def test_ecart_constant_sur_chaque_notice_donne_un_intervalle_qui_exclut_zero() -> None:
    a = {f"n{i}": _notice(10) for i in range(5)}
    b = {f"n{i}": _notice(7) for i in range(5)}

    resultat = comparaison.comparer(a, b)
    bas, haut = resultat["exactitude"]["ic"]

    assert bas > 0
    assert "| exactitude | 100.0 % | 70.0 % | +30.0 | [+30.0 ; +30.0] | oui |" in (
        comparaison.markdown("a", "b", resultat)
    )


def test_systemes_qui_se_croisent_ne_sont_pas_departages() -> None:
    a = {"n1": _notice(10), "n2": _notice(2)}
    b = {"n1": _notice(2), "n2": _notice(10)}

    resultat = comparaison.comparer(a, b)
    bas, haut = resultat["exactitude"]["ic"]

    assert bas < 0 < haut
    assert resultat["exactitude"]["ecart"] == 0.0
    assert "| non |" in comparaison.markdown("a", "b", resultat).splitlines()[6]


def test_seules_les_notices_communes_comptent() -> None:
    a = {"a": _notice(0), "b": _notice(10)}
    b = {"b": _notice(5), "c": _notice(0)}

    resultat = comparaison.comparer(a, b)

    assert resultat["notices"] == {"communes": 1}
    assert resultat["exactitude"]["a"] == 1.0
    assert resultat["exactitude"]["b"] == 0.5


def test_rapports_sans_notice_commune_donnent_un_intervalle_vide() -> None:
    resultat = comparaison.comparer({"a": _notice(10)}, {"b": _notice(10)})

    assert resultat["exactitude"]["ic"] is None
    assert "| — | — |" in comparaison.markdown("a", "b", resultat)
