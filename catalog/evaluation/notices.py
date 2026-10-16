"""Jeu de notices d'évaluation (``eval/notices.csv``) et tirage mise au point / test.

Le tirage est fait une fois, à graine fixe, stratifié par type d'équipement
(répartition proportionnelle) et étalé sur les fabricants au sein de chaque
type. Une fois écrit dans le CSV, il ne se refait pas : le prompt ne
s'ajuste que sur la mise au point (plan eval-alimentation, §2).

Lancé en module (``python -m catalog.evaluation.notices``), il complète les
empreintes depuis le manifeste et fait le tirage s'il n'existe pas encore.
L'empreinte est lue dans ``manifeste.json`` comme une donnée, sans importer
l'acquisition.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

RACINE = Path(__file__).resolve().parents[2]
NOTICES_PATH = RACINE / "eval" / "notices.csv"
MANIFESTE_PATH = RACINE / "data" / "sources" / "manifeste.json"

GRAINE = 20261015
TAILLE_MISE_AU_POINT = 15
COLONNES = tuple(
    ["id", "fabricant", "reference", "type", "format", "url", "pieges", "sha256", "jeu"]
)

Jeu = Literal["miseaupoint", "test", ""]


class Notice(BaseModel):
    """Une notice du jeu : la référence visée, sa source et son jeu."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*-\d{2}$")
    fabricant: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    type: Literal["camera_dome", "camera_tube", "camera_ptz"]
    format: Literal["pdf", "html"]
    url: str = Field(pattern=r"^https://")
    pieges: str = ""
    sha256: str = Field(default="", pattern=r"^([0-9a-f]{64})?$")
    jeu: Jeu = ""


def charger_notices(chemin: Path = NOTICES_PATH) -> list[Notice]:
    """Lit le CSV ; refuse un identifiant ou une URL en double."""
    with chemin.open(encoding="utf-8", newline="") as f:
        notices = [Notice.model_validate(ligne) for ligne in csv.DictReader(f)]
    for attribut in ("id", "url"):
        valeurs = [getattr(n, attribut) for n in notices]
        doublons = {v for v in valeurs if valeurs.count(v) > 1}
        if doublons:
            raise ValueError(f"{attribut} en double : {sorted(doublons)}")
    return notices


def ecrire_notices(notices: list[Notice], chemin: Path = NOTICES_PATH) -> None:
    """Écrit le CSV, colonnes dans l'ordre de ``COLONNES``."""
    with chemin.open("w", encoding="utf-8", newline="") as f:
        ecrivain = csv.DictWriter(f, fieldnames=COLONNES, lineterminator="\n")
        ecrivain.writeheader()
        ecrivain.writerows(n.model_dump() for n in notices)


def _quotas(effectifs: dict[str, int], total: int) -> dict[str, int]:
    """Répartit ``total`` proportionnellement (méthode du plus fort reste)."""
    n = sum(effectifs.values())
    exacts = {k: total * v / n for k, v in effectifs.items()}
    quotas = {k: int(x) for k, x in exacts.items()}
    restes = sorted(exacts, key=lambda k: (quotas[k] - exacts[k], k))
    for k in restes[: total - sum(quotas.values())]:
        quotas[k] += 1
    return quotas


def _etaler(notices: list[Notice], rng: random.Random) -> list[Notice]:
    """Mélange une strate en alternant les fabricants (tour de rôle)."""
    groupes: dict[str, list[Notice]] = defaultdict(list)
    for notice in sorted(notices, key=lambda n: n.id):
        groupes[notice.fabricant].append(notice)
    ordre = sorted(groupes)
    rng.shuffle(ordre)
    for fabricant in ordre:
        rng.shuffle(groupes[fabricant])
    etale: list[Notice] = []
    for rang in range(max(len(g) for g in groupes.values())):
        etale += [groupes[f][rang] for f in ordre if rang < len(groupes[f])]
    return etale


def tirer(
    notices: list[Notice], taille: int = TAILLE_MISE_AU_POINT, graine: int = GRAINE
) -> list[Notice]:
    """Affecte chaque notice à la mise au point ou au test, à graine fixe."""
    rng = random.Random(graine)
    strates: dict[str, list[Notice]] = defaultdict(list)
    for notice in notices:
        strates[notice.type].append(notice)
    quotas = _quotas({t: len(s) for t, s in strates.items()}, taille)
    retenus: set[str] = set()
    for type_ in sorted(strates):
        retenus |= {n.id for n in _etaler(strates[type_], rng)[: quotas[type_]]}
    return [
        n.model_copy(update={"jeu": "miseaupoint" if n.id in retenus else "test"})
        for n in notices
    ]


def completer_empreintes(
    notices: list[Notice], manifeste: list[dict[str, str]]
) -> list[Notice]:
    """Reprend l'empreinte SHA-256 du manifeste pour chaque notice, par URL."""
    par_url = {e["url"]: e["empreinte_sha256"] for e in manifeste}
    return [
        n.model_copy(update={"sha256": par_url.get(n.url, n.sha256)}) for n in notices
    ]


def chemin_source(notice: Notice, manifeste: list[dict[str, str]]) -> Path | None:
    """Le fichier archivé de la notice, retrouvé par son empreinte, ou ``None``.

    Une entrée remplacée (statut « remplace ») n'est pas retenue : son
    fichier n'est plus celui du jeu.
    """
    for entree in manifeste:
        if (
            notice.sha256
            and entree.get("empreinte_sha256") == notice.sha256
            and entree.get("statut") != "remplace"
        ):
            return MANIFESTE_PATH.parent / entree["fichier"]
    return None


def main() -> int:
    """Complète les empreintes et fait le tirage s'il manque ; réécrit le CSV."""
    notices = charger_notices()
    if MANIFESTE_PATH.exists():
        manifeste = json.loads(MANIFESTE_PATH.read_text(encoding="utf-8"))
        notices = completer_empreintes(notices, manifeste)
    jeux = {n.jeu for n in notices}
    if jeux == {""}:
        notices = tirer(notices)
    elif "" in jeux:
        print("Tirage partiel dans le CSV : à corriger à la main, pas de retirage.")
        return 1
    ecrire_notices(notices)
    sans_empreinte = [n.id for n in notices if not n.sha256]
    print(f"{len(notices)} notices ; sans empreinte : {sans_empreinte or 'aucune'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
