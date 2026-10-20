# Guide d'annotation — bloc alimentation des caméras IP

Ce guide dit comment écrire le corrigé d'une notice, `eval/reference/<id>.json`.
Il tranche les cas ambigus **avant** l'annotation, pour que la bonne réponse
ne dépende pas de l'humeur du jour. Une règle qui manque s'ajoute ici, datée,
jamais au cas par cas dans un fichier.

Le corrigé a été annoté par Claude le 2026-10-16 (`annotateur: "Claude"`),
notice lue et citée ; les champs incertains sont en `douteux` et relus par
Quentin. Aucun des modèles évalués n'y a touché. Pour contrôler un fichier :

```bash
docker exec dev_catalog sh -c "cd /app && python -m catalog.evaluation.reference"
```

## 1. Les onze champs

Ils viennent du modèle SecurScope (`catalog/extraction/cibles/camera_alimentation.json`,
commit SecurScope `3e1f26b`).

| Clé | Type | Ce que c'est |
|---|---|---|
| `ports.poe` | booléen | la caméra a une entrée PoE (propriétaire compris) |
| `ports.dc` | booléen | la caméra a une entrée en courant **continu** |
| `power_w` | W | consommation **typique** |
| `power_w_peak` | W | consommation **maximale**, toutes alimentations confondues |
| `ports.poe.class` | `"0"`…`"8"` | classe PoE annoncée |
| `ports.poe.power_w` | W | pire cas annoncé **en PoE** |
| `ports.poe.min_standard` | `802.3af` / `802.3at` / `802.3bt` | norme minimale exigée |
| `ports.dc.voltage_min_v` | V | tension mini de l'entrée continue |
| `ports.dc.voltage_max_v` | V | tension maxi de l'entrée continue |
| `ports.dc.current_standby_ma` | mA | courant au repos sur l'entrée continue |
| `ports.dc.current_peak_ma` | mA | courant maximal sur l'entrée continue |

## 2. Format d'un fichier

**Les onze clés sont toujours présentes.** Un champ que la notice ne donne
pas s'écrit `{"valeur": null, "etat_attendu": "absent"}` : un oubli ne doit
jamais passer pour un absent.

```json
{
  "id": "axis-01",
  "reference": "AXIS P3265-LVE 9 mm",
  "sha256": "<empreinte de eval/notices.csv>",
  "annotateur": "Quentin",
  "date_annotation": "2026-10-20",
  "champs": {
    "ports.poe": {"valeur": true, "etat_attendu": "sur", "page": 5,
                  "extrait": "Power over Ethernet (PoE) IEEE 802.3af/802.3at Type 1 Class 3"},
    "ports.dc": {"valeur": false, "etat_attendu": "sur", "page": 5,
                 "extrait": "Power over Ethernet (PoE) IEEE 802.3af/802.3at Type 1 Class 3",
                 "note": "PoE seul, aucune entrée DC listée"},
    "power_w": {"valeur": 4.8, "etat_attendu": "sur", "page": 5, "extrait": "Typical 4.8 W"},
    "power_w_peak": {"valeur": 10.7, "etat_attendu": "sur", "page": 5, "extrait": "max 10.7 W"},
    "ports.poe.class": {"valeur": "3", "etat_attendu": "sur", "page": 5, "extrait": "Type 1 Class 3"},
    "ports.poe.power_w": {"valeur": 10.7, "etat_attendu": "sur", "page": 5, "extrait": "max 10.7 W"},
    "ports.poe.min_standard": {"valeur": "802.3af", "etat_attendu": "sur", "page": 5,
                               "extrait": "IEEE 802.3af/802.3at Type 1 Class 3"},
    "ports.dc.voltage_min_v": {"valeur": null, "etat_attendu": "absent"},
    "ports.dc.voltage_max_v": {"valeur": null, "etat_attendu": "absent"},
    "ports.dc.current_standby_ma": {"valeur": null, "etat_attendu": "absent"},
    "ports.dc.current_peak_ma": {"valeur": null, "etat_attendu": "absent"}
  }
}
```

(L'exemple illustre la forme ; les valeurs se relisent sur la notice. La
page est celle du fichier : la puissance d'axis-01 est page 5.)

- **`valeur`** : nombre (point décimal) dans l'unité du tableau, booléen, ou
  chaîne pour la classe et la norme. Jamais d'unité dans la valeur.
- **`etat_attendu`** : `sur` si la notice le dit sans ambiguïté ; `douteux`
  si un humain hésiterait lui-même (deux valeurs contradictoires, colonne
  mal attribuée) ; `absent` si la notice ne le dit pas.
- **`page`** (PDF, numérotée à partir de 1, page du fichier et non le
  folio imprimé) **ou `section`** (page web : titre de la section, tel
  qu'affiché). Exactement l'un des deux dès qu'une valeur est présente.
- **`extrait`** : le texte exact d'où vient la valeur, recopié tel qu'il
  apparaît à l'écran. Obligatoire dès qu'une valeur est présente. (La
  lecture automatique colle parfois les mots, « Typical4.8W,max10.7W »
  chez Axis : le contrôle de citation compare sans tenir compte des
  espaces, inutile de les reproduire.)
- **`note`** (facultative) : ce que le modèle SecurScope ne sait pas dire
  (« 24 VAC », « chauffage inclus », « approx. »).
- La réannotation de contrôle (10 notices, deux semaines plus tard) va dans
  `eval/reference/reannotation/<id>.json`, même format, **sans relire la
  première annotation**.

## 3. Règles

### Une notice, une référence
- On annote **la référence de `eval/notices.csv`**, suffixe compris
  (-I, -Z, -H, -LU…). Fiche multi-références : la ligne ou la colonne de
  cette référence ; si la fiche ne permet pas de la distinguer, le champ est
  `absent` avec une note.

### Ports
- `ports.poe` vrai dès qu'une entrée PoE existe, **y compris propriétaire**
  (Hi-PoE, ePoE, High PoE, HPoE, midspan constructeur).
- `ports.dc` vrai dès qu'une entrée en courant **continu** existe.
- **24 V AC** (décidé le 2026-10-15) : ce n'est pas un port `dc`. Une
  caméra sans entrée continue — 24 V AC seul, ou 24 V AC et PoE — a
  `ports.dc` faux, tensions et courants absents, et la note « 24 VAC ».
  Une caméra qui accepte 24 V AC **ou** une tension continue a `ports.dc`
  vrai, avec la seule tension continue : UNV IPC6858SR-X22 « AC 24V±25%
  (Default), DC 24V±25% » → 18 / 30 V ; Bosch AUTODOME 7100i
  « 24 VAC/36 VDC » → 36 / 36 V.
- Une notice qui liste son alimentation sans PoE a `ports.poe` faux (et
  réciproquement pour `ports.dc`) : la section alimentation est réputée
  complète. Une notice muette sur l'alimentation : les deux `absent`.
  Une notice qui nomme ses entrées sans chiffrer aucune consommation
  (Bosch AUTODOME 7100i) : ports renseignés, puissances absentes.
- Port absent ⇒ ses attributs absents.

### Puissances
- `power_w_peak` = **la plus haute consommation annoncée**, toutes
  alimentations confondues, IR, chauffage et moteur compris, **24 V AC
  compris** (décidé le 2026-10-15). Hanwha XNP-6550RH : 92 W en 24 V AC,
  60 W en PoE → `power_w_peak` 92, `ports.poe.power_w` 60. C'est
  SecurScope qui lira `ports.poe.power_w` d'abord pour le budget PoE.
- `power_w` = la **typique**, seulement si la fiche donne aussi une maximale.
  Une seule valeur de consommation ⇒ `power_w_peak` seul.
- **Plusieurs typiques, une par alimentation** (décidé le 2026-10-16) →
  `power_w` = **la typique en PoE** : c'est elle qui sert au
  dimensionnement du switch ; une entrée DC passe par une alimentation
  dédiée, sans dimensionnement prévu. Vaut aussi pour « Basic » (Dahua) et
  la moyenne 24 h (Milesight). Sans PoE, la règle ne s'applique pas.
- `ports.poe.power_w` = le **pire cas annoncé en PoE**. PoE propriétaire
  non chiffré (Hikvision « Hi-PoE » sans watts) ⇒ absent.
- « 6,4 W (12V DC) ; 7,7 W (PoE) » → `power_w_peak` 7,7, `ports.poe.power_w`
  7,7, `power_w` absent.
- **Typique – maximale** sur une ligne : Bosch DINION 5100i « Power
  consumption PoE (W) (typical – maximum) 6.79 W – 10.73 W » (en-tête coupé
  sur deux lignes) → `power_w` 6,79, `ports.poe.power_w` 10,73 ;
  `power_w_peak` = le maximum des entrées PoE, VDC et VAC **du bloc de la
  référence visée** ; bloc non attribuable ⇒ `douteux`.
- **Maximum global sans détail par alimentation** (décidé le 2026-10-16),
  la caméra ayant un port PoE → `power_w_peak` et aussi
  `ports.poe.power_w` : en PoE, elle peut tirer ce maximum sur le switch
  (UNV « Max. 8.5 W », Dahua Hi-PoE « Max: 45 W », Vivotek « Max. 81.8 W »).
- Consommation **sans libellé** donnée en plage (UNV « 16 ~ 56W ») →
  `power_w_peak` 56, `power_w` absent.
- **Min / moyenne 24 h / max** (Milesight) → `power_w` = la moyenne 24 h,
  note « moyenne 24 h » ; `power_w_peak` = le max.
- **Chauffage marche / arrêt** (Vivotek « PoE max 24,7 W / 11,4 W ») →
  `power_w_peak` et `ports.poe.power_w` 24,7, `power_w` absent : le second
  chiffre est un maximum dans un autre état, pas une typique.
- **Profils de puissance** (AXIS Q6225-LE : full power typ 16 / max 71 W,
  low power max 32 W, bt Type 4 « max 90 W ») → `power_w_peak` et
  `ports.poe.power_w` 71, `power_w` 16 ; le 90 W est la capacité de la
  norme, pas une consommation. Note « power profiles ».
- « approx. 8,7 W » : la valeur est retenue, note « approx. ».
- **VA ≠ W** : une valeur en VA n'entre dans aucun champ. W et VA donnés
  ensemble (Mobotix « max 59.05 watt, max 87.12 VA ») : les watts, VA en
  note. « 24V at 100VA » (Bosch MIC) est une recommandation
  d'alimentation, pas une consommation.

### PoE : classe et norme
- « PoE+ » = 802.3at ; « PoE++ » = 802.3bt ; « Class 4 » = `"4"`.
- `min_standard` = la norme **la plus basse** avec laquelle la caméra
  fonctionne (« 802.3af/802.3at » → `802.3af`).
- **Plusieurs modes PoE normés** (AXIS Q1806-LE : « 802.3at Class 4 max
  25,5 W, ou 802.3bt Type 3 Class 6 max 51 W ») → `class`,
  `ports.poe.power_w` et `power_w_peak` du **pire cas** ("6", 51) : la
  classe et la puissance forment une paire cohérente pour SecurScope ;
  `min_standard` reste la norme la plus basse (802.3at), celle sur laquelle
  la caméra fonctionne ; note « fonctionne en 802.3at Class 4 (25,5 W) sans
  PoE-out ».
  Tranché par Quentin le 2026-10-20 ; avant, la classe était celle du mode
  bas, avec la puissance du mode haut (paire incohérente).
- On ne déduit pas une classe d'un type : « Type 4 » sans numéro de classe
  ⇒ `class` absent.
- **Classe seule** (sans norme écrite) → `min_standard` absent. On ne
  déduit pas la norme de la classe. Règle gardée pour mémoire : aucune
  notice constructeur lue le 2026-10-15 (Pelco, Avigilon, Vicon, Arecont,
  Canon et les dix fabricants du jeu) ne donne une classe sans norme ; le
  jeu ne la teste donc pas (limite publiée).
- **PoE propriétaire seul** (Hi-PoE, HPoE…) → port PoE présent,
  `min_standard` absent, note du nom commercial. S'il existe **aussi** un
  mode normé (AXIS Q6135-LE : « High PoE … max 51 W » et « IEEE802.3at
  Type2 Class4 … max 25 W ») → la norme et la classe de ce mode,
  `ports.poe.power_w` = le pire cas (51). Exception assumée à la paire
  cohérente : le mode propriétaire n'a pas de classe, et la classe du mode
  normé dit sur quel port de switch la caméra démarre (Quentin,
  2026-10-20 ; de même pour un injecteur testé, i-PRO WV-X6533LNS).

### Tensions
- « 12 V DC ± 25 % » → `voltage_min_v` 9, `voltage_max_v` 15.
- Tolérance asymétrique collée à la tension : « 12 VDC (–10% to +25%) »
  → 10,8 / 15.
- **Tolérance placée après le courant, symétrique ou asymétrique** →
  tension nominale : Dahua « 36 VDC, 2.23 A ± 25% » → 36 / 36 ; Dahua
  « 12 VDC, 4 A (–10% to +25%) » → 12 / 12 (décidé le 2026-10-16 : on ne
  sait pas si elle porte sur la tension ; des bornes trop larges feraient
  accepter une alimentation inadaptée, des bornes trop étroites ne font que
  refuser une alimentation qui aurait convenu).
- Un courant qui est le calibre de l'alimentation et non une consommation
  (Dahua 4G « 12 VDC, 4 A » pour 27 W max) → `absent`.
- « 12 V DC » seul → min = max = 12.
- « 10–28 V DC » → 10 et 28.
- **Jamais** 44 à 57 V venant du PoE dans les tensions du port `dc`.
- **Sortie d'alimentation pour accessoires** (2026-10-16) : « 12VDC output »
  (borne d'alarme Hanwha) n'est pas une entrée ; ni `ports.dc`, ni tension,
  ni courant n'en viennent.

### Courants
- A → mA permis (0,4 A → 400). **W → mA jamais.**
- **Courant unique** (décidé le 2026-10-15) → `current_peak_ma`,
  `current_standby_ma` absent. Les fiches le donnent avec la puissance
  maximale (Hikvision « 12 VDC ± 25%, 0.4 A, max. 5 W » ; « 1.19 A,
  max. 14.28 W », et 1,19 A × 12 V = 14,28 W ; i-PRO « 720 mA, Approx.
  8.6 W ») : il dimensionne l'alimentation 12 V, le mettre au repos
  fausserait un calcul d'autonomie.
- Typique et maximale → `current_standby_ma` et `current_peak_ma`.
- Un courant mesuré **en PoE** (« PoE 180 mA ») n'est pas un courant du
  port `dc` : note seulement.

### Fiche multi-références illisible
- Une valeur dont la ligne n'est pas lisible sur la notice est `absent`
  avec une note, ou `douteux` si on la lit mais sans certitude sur la
  colonne.
- Une ligne **sans préfixe de modèle** vaut pour chaque référence de la
  fiche (2026-10-16). Vivotek SD9364 : EH et EHL sont distinguées partout
  où elles diffèrent, mais « Power Consumption Max. 81.8 W (Heater on) »
  n'a qu'une ligne commune ; 81,8 W vaut donc pour l'EH, en `sur`.
  (L'ancienne lecture « ligne EH lisible, EHL non » venait de colonnes
  mêlées par l'extraction de texte, corrigée au lot L2.)
