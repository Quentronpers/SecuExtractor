"""Lecture de robots.txt selon la RFC 9309 : groupes, jokers, règle la plus longue."""

from __future__ import annotations

import pytest

from catalog.acquisition import robots

BOT = "SecurScopeCatalogBot"


@pytest.mark.parametrize(
    ("motif", "chemin", "couvert"),
    [
        ("/prive/", "/prive/a.pdf", True),
        ("/prive/", "/public/a.pdf", False),
        ("/*.pdf$", "/doc/notice.pdf", True),
        ("/*.pdf$", "/doc/notice.pdf?v=2", False),
        ("/*.pdf", "/doc/notice.pdf?v=2", True),
        ("/fiche$", "/fiche", True),
        ("/fiche$", "/fiche/2", False),
        ("/*/download/", "/fr/download/a.pdf", True),
        ("/a.b", "/axb", False),
    ],
    ids=[
        "prefixe",
        "autre_prefixe",
        "joker_et_fin",
        "fin_avec_requete",
        "joker_sans_fin",
        "fin_exacte",
        "fin_depassee",
        "joker_au_milieu",
        "point_litteral",
    ],
)
def test_un_motif_couvre_un_chemin_selon_jokers_et_ancre(
    motif: str, chemin: str, couvert: bool
) -> None:
    assert robots.Regle(autorise=False, motif=motif).correspond(chemin) is couvert


def test_disallow_avec_joker_pdf_bloque_les_pdf() -> None:
    regles = robots.analyser("User-agent: *\nDisallow: /*.pdf$\n", BOT)

    assert not regles.autorise("/doc/notice.pdf")
    assert regles.autorise("/produit/cam-100")


def test_la_regle_la_plus_longue_l_emporte_dans_les_deux_sens() -> None:
    texte = "User-agent: *\nDisallow: /doc/\nAllow: /doc/notices/\n"
    regles = robots.analyser(texte, BOT)

    assert regles.autorise("/doc/notices/a.pdf")
    assert not regles.autorise("/doc/interne/a.pdf")


def test_a_longueur_egale_allow_l_emporte() -> None:
    texte = "User-agent: *\nDisallow: /doc\nAllow: /doc\n"
    assert robots.analyser(texte, BOT).autorise("/doc/a.pdf")


def test_le_groupe_du_robot_remplace_celui_de_l_etoile() -> None:
    texte = (
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: securscopecatalogbot\nDisallow: /prive/\nCrawl-delay: 7\n"
    )
    regles = robots.analyser(texte, BOT)

    assert regles.autorise("/produit/a")
    assert not regles.autorise("/prive/a")
    assert regles.crawl_delay == 7.0


def test_sans_groupe_du_robot_celui_de_l_etoile_s_applique() -> None:
    texte = "User-agent: googlebot\nDisallow: /\n\nUser-agent: *\nDisallow: /tmp/\n"
    regles = robots.analyser(texte, BOT)

    assert regles.autorise("/produit/a")
    assert not regles.autorise("/tmp/a")


def test_plusieurs_user_agent_partagent_un_groupe() -> None:
    texte = "User-agent: autre\nUser-agent: SecurScopeCatalogBot\nDisallow: /x/\n"
    assert not robots.analyser(texte, BOT).autorise("/x/a")


def test_disallow_vide_commentaires_et_cles_inconnues_n_interdisent_rien() -> None:
    texte = "# entête\nUser-agent: * # tous\nDisallow:\nSitemap: https://s.test/s.xml\n"
    regles = robots.analyser(texte, BOT)

    assert regles.autorise("/tout")
    assert regles.crawl_delay is None


def test_robots_txt_toujours_permis_meme_si_tout_est_interdit() -> None:
    regles = robots.tout_interdit()

    assert regles.autorise("/robots.txt")
    assert not regles.autorise("/")


def test_crawl_delay_illisible_ignore() -> None:
    texte = "User-agent: *\nCrawl-delay: lent\nDisallow: /x/\n"
    assert robots.analyser(texte, BOT).crawl_delay is None


def test_un_bom_en_tete_ne_masque_pas_la_premiere_ligne() -> None:
    regles = robots.analyser("\N{BYTE ORDER MARK}User-agent: *\nDisallow: /\n", BOT)
    assert not regles.autorise("/a")


def test_un_agent_qui_n_est_qu_une_partie_du_jeton_ne_vaut_pas_pour_le_robot() -> None:
    texte = "User-agent: bot\nDisallow: /\n\nUser-agent: *\nDisallow: /tmp/\n"
    regles = robots.analyser(texte, BOT)

    assert regles.autorise("/produit/a")
    assert not regles.autorise("/tmp/a")


def test_un_disallow_vide_referme_le_groupe() -> None:
    texte = (
        "User-agent: SecurScopeCatalogBot\nDisallow:\n\nUser-agent: *\nDisallow: /\n"
    )
    assert robots.analyser(texte, BOT).autorise("/produit/a")


@pytest.mark.parametrize("chemin", ["/café/a", "/caf%C3%A9/a", "/caf%c3%a9/a"])
def test_motif_et_chemin_compares_apres_normalisation_des_pourcents(
    chemin: str,
) -> None:
    regles = robots.analyser("User-agent: *\nDisallow: /café/\n", BOT)
    assert not regles.autorise(chemin)
