"""Lecture d'un robots.txt selon la RFC 9309, sans dépendance.

``urllib.robotparser`` compare des préfixes : il ignore les jokers ``*`` et
``$`` et applique la première règle trouvée, pas la plus longue. Un
``Disallow: /*.pdf$`` y passait inaperçu, alors que le projet télécharge des
PDF. Ici :
- groupe retenu : ceux dont un ``User-agent`` est le jeton produit du robot,
  à la casse près ; à défaut, ceux de ``*`` (§ 2.2.1) ;
- règle appliquée : celle dont le motif est le plus long ; à longueur égale,
  ``Allow`` l'emporte (§ 2.2.2) ;
- ``*`` vaut toute suite de caractères, ``$`` final ancre la fin (§ 2.2.3) ;
- motifs et chemins comparés après normalisation des « %XX » (§ 2.2.2) ;
- ``Disallow`` vide n'interdit rien ; ``/robots.txt`` est toujours permis ;
- BOM toléré, fichier lu sur ses 500 premiers Kio au plus (§ 2.5).
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote

TAILLE_MAX = 500 * 1024
# Réservés et non réservés (RFC 3986) restent tels quels ; le reste est encodé.
_SURS = "/?#[]@!$&'()*+,;=:-._~"


def normaliser(chemin: str) -> str:
    """Forme canonique d'un chemin : « /café » et « /caf%c3%a9 » s'égalent."""
    return quote(unquote(chemin), safe=_SURS)


@dataclass(frozen=True)
class Regle:
    """Une ligne ``Allow`` ou ``Disallow`` d'un groupe."""

    autorise: bool
    motif: str

    def correspond(self, chemin: str) -> bool:
        """Vrai si le motif couvre le chemin (requête comprise)."""
        ancre = self.motif.endswith("$")
        corps = self.motif[:-1] if ancre else self.motif
        expression = ".*".join(re.escape(morceau) for morceau in corps.split("*"))
        return re.match(expression + ("$" if ancre else ""), chemin) is not None


@dataclass
class Robots:
    """Règles et délai qui s'appliquent à un robot sur un domaine."""

    regles: list[Regle] = field(default_factory=list)
    crawl_delay: float | None = None

    def autorise(self, chemin: str) -> bool:
        """Applique la règle au motif le plus long ; ``Allow`` en cas d'égalité."""
        chemin = normaliser(chemin)
        if chemin == "/robots.txt":
            return True
        applicables = [r for r in self.regles if r.correspond(chemin)]
        if not applicables:
            return True
        meilleure = max(applicables, key=lambda r: (len(r.motif), r.autorise))
        return meilleure.autorise


TOUT_AUTORISE = Robots()


def tout_interdit() -> Robots:
    """Règles d'un site dont on ne sait pas ce qu'il autorise."""
    return Robots(regles=[Regle(autorise=False, motif="/")])


@dataclass
class _Groupe:
    """Des ``User-agent`` et les lignes qui les suivent."""

    agents: list[str] = field(default_factory=list)
    regles: list[Regle] = field(default_factory=list)
    crawl_delay: float | None = None
    ferme: bool = False  # une règle lue, même vide : un User-agent ouvre un groupe


def _lignes(texte: str) -> list[tuple[str, str]]:
    """Paires (clé en minuscules, valeur), commentaires et lignes vides ôtés."""
    paires = []
    for brute in texte[:TAILLE_MAX].lstrip("\ufeff").splitlines():
        ligne = brute.split("#", 1)[0].strip()
        if ":" in ligne:
            cle, valeur = ligne.split(":", 1)
            paires.append((cle.strip().lower(), valeur.strip()))
    return paires


def _groupes(texte: str) -> list[_Groupe]:
    """Découpe le fichier en groupes : des ``User-agent`` suivis de règles."""
    groupes: list[_Groupe] = []
    courant: _Groupe | None = None
    for cle, valeur in _lignes(texte):
        if cle == "user-agent":
            if courant is None or courant.ferme:
                courant = _Groupe()
                groupes.append(courant)
            courant.agents.append(valeur.lower())
        elif courant is not None:
            _ajouter(courant, cle, valeur)
    return groupes


def _ajouter(groupe: _Groupe, cle: str, valeur: str) -> None:
    """Ajoute une règle ou un délai au groupe ; ignore les autres clés."""
    if cle in ("allow", "disallow", "crawl-delay"):
        groupe.ferme = True
    if cle in ("allow", "disallow") and valeur:
        motif = normaliser(valeur)
        groupe.regles.append(Regle(autorise=cle == "allow", motif=motif))
    elif cle == "crawl-delay":
        with contextlib.suppress(ValueError):
            groupe.crawl_delay = float(valeur)


def analyser(texte: str, jeton_produit: str) -> Robots:
    """Les règles du robot ``jeton_produit`` (``SecurScopeCatalogBot``…).

    Un groupe vaut pour le robot si l'un de ses ``User-agent`` est son jeton
    produit, à la casse près ; à défaut, les groupes ``*`` s'appliquent.
    """
    jeton = jeton_produit.lower()
    groupes = _groupes(texte)
    retenus = [g for g in groupes if jeton in g.agents] or [
        g for g in groupes if "*" in g.agents
    ]
    delais = [g.crawl_delay for g in retenus if g.crawl_delay is not None]
    return Robots(
        regles=[r for g in retenus for r in g.regles],
        crawl_delay=max(delais) if delais else None,
    )
