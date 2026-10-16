"""Fabrique de petits PDF pour les tests du lecteur, sans dépendance.

On décrit chaque page par des textes placés (police Helvetica standard, dont
pdfminer connaît les largeurs) et des traits ; le module écrit un PDF
minimal valide. Aucune notice constructeur n'entre dans les tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

LARGEUR, HAUTEUR = 595, 842


@dataclass
class PagePdf:
    """Une page : textes ``(x, y, texte, taille)`` et traits ``(x0, y0, x1, y1)``.

    Les ordonnées partent du haut de la page, comme dans pdfplumber.
    """

    textes: list[tuple[float, float, str, float]] = field(default_factory=list)
    traits: list[tuple[float, float, float, float]] = field(default_factory=list)

    def texte(self, x: float, y: float, chaine: str, taille: float = 10) -> None:
        """Place une chaîne, ``y`` étant la ligne de base mesurée depuis le haut."""
        self.textes.append((x, y, chaine, taille))

    def trait(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Trace un segment (ordonnées depuis le haut)."""
        self.traits.append((x0, y0, x1, y1))

    def flux(self) -> bytes:
        """Le flux de contenu PDF de la page."""
        ops = ["1 w"]
        for x0, y0, x1, y1 in self.traits:
            ops.append(f"{x0} {HAUTEUR - y0} m {x1} {HAUTEUR - y1} l S")
        for x, y, chaine, taille in self.textes:
            echappee = chaine.replace("\\", "\\\\").replace("(", "\\(")
            echappee = echappee.replace(")", "\\)")
            ops.append(f"BT /F1 {taille} Tf {x} {HAUTEUR - y} Td ({echappee}) Tj ET")
        return "\n".join(ops).encode("latin-1")


def ecrire_pdf(chemin: Path, pages: list[PagePdf]) -> Path:
    """Écrit un PDF dont chaque page est décrite par ``pages``."""
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, page in enumerate(pages):
        objets.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {LARGEUR} {HAUTEUR}] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {5 + 2 * i} 0 R >>".encode()
        )
        flux = page.flux()
        objets.append(
            f"<< /Length {len(flux)} >>\nstream\n".encode() + flux + b"\nendstream"
        )
    chemin.write_bytes(_assembler(objets))
    return chemin


def _assembler(objets: list[bytes]) -> bytes:
    """Numérote les objets et écrit la table des renvois."""
    sortie = bytearray(b"%PDF-1.4\n")
    positions = []
    for numero, corps in enumerate(objets, start=1):
        positions.append(len(sortie))
        sortie += f"{numero} 0 obj\n".encode() + corps + b"\nendobj\n"
    debut_xref = len(sortie)
    sortie += f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode()
    sortie += b"".join(f"{p:010d} 00000 n \n".encode() for p in positions)
    sortie += (
        f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\n"
        f"startxref\n{debut_xref}\n%%EOF\n"
    ).encode()
    return bytes(sortie)
