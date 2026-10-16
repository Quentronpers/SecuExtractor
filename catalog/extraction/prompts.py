"""Gabarits de prompt et schéma de sortie, par famille d'équipement et par bloc.

Le gabarit rappelle les règles non négociables de CLAUDE.md (citation
obligatoire, jamais d'inférence, valeur maximale, plages conservées, pas de
conversion hasardeuse) et les cas tranchés par ``eval/GUIDE.md``. Il est en
anglais, comme les notices. Toute modification du texte change
``VERSION_PROMPT`` : la version entre dans la clé des réponses brutes et dans
les résultats, et le jeu de test n'est mesuré qu'une fois par version.

Le schéma est strict (tous les champs requis, ``additionalProperties: false``,
nullables en ``[type, "null"]``) : le plus petit commun dénominateur d'Ollama
et de Groq (plan eval-alimentation, §2). Dans chaque champ, l'extrait vient
avant la valeur : la génération contrainte suit l'ordre des propriétés, le
modèle recopie la source avant de conclure.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, RootModel, model_validator

from catalog.extraction.cible import ChampCible, Cible, Valeur
from catalog.reading.page import Page

VERSION_PROMPT = "camera-alimentation-v1"

_TYPES_JSON = {"booleen": "boolean", "nombre": "number", "enum": "string"}

_INTRO = """\
You extract the power-supply characteristics of ONE IP camera from excerpts \
of its manufacturer datasheet. The target reference is given with the \
document; the datasheet may describe several references.

For every field, return:
- "extrait": the exact text of the document that states the value, copied \
verbatim (a short contiguous span, typically one line or one table row, \
including the value and its unit), or null;
- "page": the number of the page (or section) where that text appears, as \
given in the "=== Page N ===" headers, or null;
- "valeur": the value, or null when the document does not state it;
- "doute": true if you are not sure (conflicting values, unclear column or \
row, value that may belong to another reference), false otherwise."""

_REGLES = """\
Rules:
1. Citation is mandatory. Copy the extract character for character. Never \
paraphrase, never join pieces taken from different places.
2. Never infer. A field the document does not state is null (valeur, \
extrait and page all null). Do not compute, do not deduce a PoE class from \
a standard or a type, nor a standard from a class, and never borrow a value \
from another reference or a similar product. false is a value: a port \
declared false is quoted like any other value.
3. The maximum wins. When a base value and a maximum are given, the \
maximum goes to the peak and worst-case fields. Underestimating a \
consumption undersizes a PoE switch.
4. Ranges keep both bounds: "10-28 V DC" gives 10 and 28; "12 V DC" alone \
gives 12 and 12. A voltage tolerance applies to the nominal voltage: \
"12 V DC ±25%" gives 9 and 15, "12 VDC (-10% to +25%)" gives \
10.8 and 15. A tolerance written after a current may apply to the current: \
keep the nominal voltage ("36 VDC, 2.23 A ±25%" gives 36 and 36).
5. No other arithmetic. Watts never become milliamperes. Amperes may \
become milliamperes (0.4 A gives 400). Volt-amperes (VA) are not watts.
6. Numbers are plain numbers in the unit of the field, with a decimal \
point, no unit inside the value. Approximate values ("approx. 8.7 W") are \
kept as they are.
7. Multi-reference datasheets: use only the line or column of the target \
reference; the model suffix (-H, -Z, -IR...) is part of the reference. A \
line without any model prefix applies to every reference. If you cannot \
tell which value belongs to the target, set "doute" to true.
8. Port attributes (ports.poe.*, ports.dc.*) are null when that port is \
false or null.
9. Only what the camera itself accepts or consumes counts. A power output \
for accessories ("12 VDC output", aux power) is not an input. The rating \
of a recommended power supply, injector or switch port, and the capacity of \
a PoE standard or class (15.4, 30, 60, 90 W), are not consumptions. If \
voltage × current is far above the maximum power, the current is probably \
the supply rating: set "doute" to true."""

# Ce que chaque champ veut dire pour le modèle, repris de eval/GUIDE.md.
CONSIGNES: dict[str, str] = {
    "ports.poe": "true if the camera can be powered over Ethernet, "
    "proprietary PoE included (Hi-PoE, ePoE, High PoE); false if the power "
    "section lists the power inputs and PoE is not among them. For true or "
    "false, quote the line that lists the power inputs.",
    "ports.dc": "true if the camera has a direct-current (DC) power input; "
    "false for a 24 V AC input alone, or if the power section lists the "
    "inputs and none is DC. For true or false, quote the line that lists "
    "the power inputs.",
    "power_w": "typical consumption, only if the document also gives a "
    "maximum; with one typical per power input, the PoE one. A single "
    'consumption value goes to power_w_peak, not here. "Basic" and a 24 h '
    "average count as typical; a maximum in another state (heater off, "
    "low-power profile) does not.",
    "power_w_peak": "highest consumption stated, any power input (PoE, DC "
    "or 24 V AC), IR, heater and motor included. A single consumption value "
    'goes here; an unlabeled range ("16 ~ 56W") gives its upper bound.',
    "ports.poe.class": 'PoE class written in the document ("Class 4" gives '
    '"4"). With several PoE modes, the class of the lowest mode. Never '
    "deduced from a type or a standard.",
    "ports.poe.power_w": "worst-case consumption stated for PoE. A global "
    "maximum without detail per power input also goes here. The capacity of "
    'a standard ("802.3bt max 90 W") is not a consumption.',
    "ports.poe.min_standard": "lowest IEEE standard the camera works with "
    '("802.3af/802.3at" gives 802.3af). "PoE+" means 802.3at, "PoE++" means '
    "802.3bt. null for a proprietary PoE alone or a class alone.",
    "ports.dc.voltage_min_v": "minimum voltage of the DC input. Never an AC "
    "voltage, never the 44-57 V of PoE.",
    "ports.dc.voltage_max_v": "maximum voltage of the DC input. Never an AC "
    "voltage, never the 44-57 V of PoE.",
    "ports.dc.current_standby_ma": "typical current on the DC input, only "
    "if a maximum current is also given.",
    "ports.dc.current_peak_ma": "maximum current on the DC input; a single "
    "current goes here. Not a current measured in PoE, not the rating of "
    "the recommended power supply.",
}


class ChampRendu(BaseModel):
    """Ce que le modèle rend pour un champ."""

    model_config = ConfigDict(frozen=True)

    extrait: str | None
    page: int | None
    valeur: Valeur
    doute: bool


class ReponseBloc(RootModel[dict[str, ChampRendu]]):
    """La réponse du modèle pour un bloc : un ``ChampRendu`` par clé.

    Une clé de la cible manquante rend la réponse invalide : un champ non
    rendu est un échec (``schema_invalide``), jamais un ``absent``.
    """

    @model_validator(mode="after")
    def _toutes_les_cles(self) -> Self:
        manquantes = [cle for cle in CONSIGNES if cle not in self.root]
        if manquantes:
            raise ValueError(f"champs non rendus : {manquantes}")
        return self


def _ligne_champ(champ: ChampCible) -> str:
    """Une ligne de la liste des champs : clé, type, unité, consigne."""
    if champ.valeurs:
        nature = "one of " + ", ".join(f'"{v}"' for v in champ.valeurs)
    elif champ.type == "nombre":
        nature = f"number in {champ.unite}"
    else:
        nature = "boolean"
    return f"- {champ.cle} ({nature}): {CONSIGNES[champ.cle]}"


def gabarit(cible: Cible) -> str:
    """Prompt système d'un bloc : rôle, règles et liste des champs visés."""
    champs = "\n".join(_ligne_champ(champ) for champ in cible.champs)
    return f"{_INTRO}\n\n{_REGLES}\n\nFields:\n{champs}\n"


def message_utilisateur(reference: str, pages: Sequence[Page]) -> str:
    """Message utilisateur : la référence visée et les pages retenues."""
    blocs = []
    for page in pages:
        titre = f" - {page.titre}" if page.titre else ""
        blocs.append(f"=== Page {page.numero}{titre} ===\n{page.texte}")
    corps = "\n\n".join(blocs)
    return f"Target reference: {reference}\n\nDocument excerpts:\n\n{corps}\n"


def _schema_valeur(champ: ChampCible) -> dict[str, Any]:
    """Type nullable ; une énumération nullable passe par ``anyOf``.

    ``enum`` contenant ``null`` n'est documenté ni par Ollama ni par Groq.
    """
    if champ.valeurs:
        return {
            "anyOf": [{"type": "string", "enum": list(champ.valeurs)}, {"type": "null"}]
        }
    return {"type": [_TYPES_JSON[champ.type], "null"]}


def schema_sortie(cible: Cible) -> dict[str, Any]:
    """Schéma JSON strict de la réponse, bâti sur les champs de la cible."""
    proprietes = {}
    for champ in cible.champs:
        proprietes[champ.cle] = {
            "type": "object",
            "properties": {
                "extrait": {"type": ["string", "null"]},
                "page": {"type": ["integer", "null"]},
                "valeur": _schema_valeur(champ),
                "doute": {"type": "boolean"},
            },
            "required": ["extrait", "page", "valeur", "doute"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": proprietes,
        "required": list(proprietes),
        "additionalProperties": False,
    }
