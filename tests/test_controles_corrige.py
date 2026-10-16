"""Les contrôles de citation et de plausibilité ne refusent pas le corrigé.

Les 50 notices annotées (eval/reference/) servent de garde-fou : une règle
qui met en douteux une valeur juste coûte de la relecture sur toutes les
notices de ce genre.
"""

from __future__ import annotations

from catalog.evaluation.reference import REFERENCE_DIR, charger_corriges
from catalog.extraction.cible import charger_cible
from catalog.extraction.citations import verifier_citation
from catalog.plausibility.checker import verifier_plausibilite
from catalog.reading.page import Page

CIBLE = charger_cible("camera", "alimentation")
CHAMPS = CIBLE.par_cle()

# Valeurs justes du corrigé que le contrôle met en douteux, à dessein.
DOUTEUX_VOULUS = {
    "dahua-04 power_w",  # « 7.4 (pulling stream in 4G) » : pas d'unité
}


def test_chaque_valeur_du_corrige_est_justifiee_par_son_extrait() -> None:
    """Contrôle de la valeur dans l'extrait, sur les 50 notices du corrigé.

    Le texte des notices n'est pas versionné : la présence de l'extrait dans
    la page a été vérifiée hors dépôt (plan, L3b) ; ici l'extrait tient lieu
    de page.
    """
    echecs = set()
    for id_, corrige in charger_corriges(REFERENCE_DIR, CIBLE).items():
        for cle, annotee in corrige.champs.items():
            if annotee.valeur is None or annotee.extrait is None:
                continue
            pages = [Page(numero=1, texte=annotee.extrait)]
            motif = verifier_citation(
                CHAMPS[cle], annotee.valeur, 1, annotee.extrait, pages
            )
            if motif:
                echecs.add(f"{id_} {cle}")
    assert echecs == DOUTEUX_VOULUS


def test_aucune_valeur_sure_du_corrige_n_echoue() -> None:
    """Les règles ne marquent pas en douteux une valeur juste du corrigé.

    Le texte des notices n'est pas versionné : extraits et notes du corrigé
    tiennent lieu de texte envoyé (classes citées, PoE propriétaire).
    """
    echecs = []
    for id_, corrige in charger_corriges(REFERENCE_DIR, CIBLE).items():
        champs = corrige.champs
        texte = "\n".join(f"{a.extrait or ''} {a.note or ''}" for a in champs.values())
        motifs = verifier_plausibilite(
            {cle: a.valeur for cle, a in champs.items()},
            {cle: a.extrait for cle, a in champs.items()},
            [Page(numero=1, texte=texte)],
        )
        echecs += [
            f"{id_} {cle} : {motif}"
            for cle, motif in motifs.items()
            if champs[cle].etat_attendu == "sur"
        ]
    assert echecs == []
