# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Générateur PDF minimal (bibliothèque standard uniquement) : texte Helvetica avec accents, formes,
liens cliquables et images PNG (transparence comprise). Suffisant pour un document propre, sans dépendance."""
import struct
import zlib

A4 = (595.28, 841.89)


def _rvb(hexa):
    return tuple(int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _texte_pdf(t):
    """Chaîne PDF en WinAnsi (cp1252), caractères spéciaux échappés ; ce qui n'existe pas devient « ? »."""
    t = t.replace("’", "'").replace(" ", " ").replace(" ", " ")
    b = t.encode("cp1252", "replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def lire_png(chemin):
    """PNG 8 bits non entrelacé (RVB ou RVBA) → (largeur, hauteur, octets RVB, octets alpha ou None)."""
    d = open(chemin, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n", "pas un PNG"
    pos, idat = 8, b""
    l = h = profondeur = type_couleur = entrelace = 0
    while pos < len(d):
        n, genre = struct.unpack(">I4s", d[pos:pos + 8])
        bloc = d[pos + 8:pos + 8 + n]
        if genre == b"IHDR":
            l, h, profondeur, type_couleur, _, _, entrelace = struct.unpack(">IIBBBBB", bloc)
        elif genre == b"IDAT":
            idat += bloc
        pos += 12 + n
    if profondeur != 8 or type_couleur not in (2, 6) or entrelace:
        raise ValueError("PNG non pris en charge (attendu : 8 bits, RVB ou RVBA, non entrelacé)")
    canaux = 4 if type_couleur == 6 else 3
    brut, ligne_len = zlib.decompress(idat), l * canaux
    pixels, prec = bytearray(), bytearray(ligne_len)
    for y in range(h):
        filtre = brut[y * (ligne_len + 1)]
        ligne = bytearray(brut[y * (ligne_len + 1) + 1:(y + 1) * (ligne_len + 1)])
        for i in range(ligne_len):
            a = ligne[i - canaux] if i >= canaux else 0
            b = prec[i]
            c = prec[i - canaux] if i >= canaux else 0
            if filtre == 1:
                ligne[i] = (ligne[i] + a) & 255
            elif filtre == 2:
                ligne[i] = (ligne[i] + b) & 255
            elif filtre == 3:
                ligne[i] = (ligne[i] + (a + b) // 2) & 255
            elif filtre == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                ligne[i] = (ligne[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        pixels += ligne
        prec = ligne
    if canaux == 3:
        return l, h, bytes(pixels), None
    return l, h, bytes(b for i in range(0, len(pixels), 4) for b in pixels[i:i + 3]), bytes(pixels[3::4])


class Document:
    def __init__(self, titre="", auteur=""):
        self.pages, self.images, self.titre, self.auteur = [], [], titre, auteur
        self.nouvelle_page()

    def nouvelle_page(self):
        self.flux, self.liens = [], []
        self.pages.append((self.flux, self.liens))

    # --- Primitives (origine en haut à gauche, en points) --------------------------------------------------
    def _y(self, y):
        return A4[1] - y

    def texte(self, x, y, t, taille=10, gras=False, couleur="#1b2733"):
        r, v, b = _rvb(couleur)
        police = "/F2" if gras else "/F1"
        self.flux.append(b"BT %s %.1f Tf %.3f %.3f %.3f rg %.2f %.2f Td (" % (police.encode(), taille, r, v, b, x,
                                                                              self._y(y)) + _texte_pdf(t) + b") Tj ET")

    def rectangle(self, x, y, l, h, remplissage="#ffffff"):
        r, v, b = _rvb(remplissage)
        self.flux.append(b"%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (r, v, b, x, self._y(y + h), l, h))

    def ligne(self, x1, y1, x2, y2, couleur="#29e0ff", epaisseur=0.6, pointille=False):
        r, v, b = _rvb(couleur)
        tirets = b"[1.5 3] 0 d " if pointille else b"[] 0 d "
        self.flux.append(tirets + b"%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S" % (
            r, v, b, epaisseur, x1, self._y(y1), x2, self._y(y2)))

    def cercle(self, cx, cy, rayon, couleur="#29e0ff", plein=False, epaisseur=0.8):
        k, (r, v, b), y = 0.5523 * rayon, _rvb(couleur), self._y(cy)
        chemin = (b"%.2f %.2f m " % (cx + rayon, y)
                  + b"%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx + rayon, y + k, cx + k, y + rayon, cx, y + rayon)
                  + b"%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx - k, y + rayon, cx - rayon, y + k, cx - rayon, y)
                  + b"%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx - rayon, y - k, cx - k, y - rayon, cx, y - rayon)
                  + b"%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx + k, y - rayon, cx + rayon, y - k, cx + rayon, y))
        if plein:
            self.flux.append(b"%.3f %.3f %.3f rg " % (r, v, b) + chemin + b"f")
        else:
            self.flux.append(b"[] 0 d %.3f %.3f %.3f RG %.2f w " % (r, v, b, epaisseur) + chemin + b"S")

    def lien(self, x, y, l, h, url):
        self.liens.append((x, self._y(y + h), x + l, self._y(y), url))

    def image_png(self, chemin, x, y, largeur):
        l, h, rvb, alpha = lire_png(chemin)
        self.images.append((l, h, rvb, alpha))
        nom = f"/Im{len(self.images)}".encode()
        hauteur = largeur * h / l
        self.flux.append(b"q %.2f 0 0 %.2f %.2f %.2f cm %s Do Q" % (largeur, hauteur, x, self._y(y + hauteur), nom))
        return hauteur

    @staticmethod
    def largeur_texte(t, taille, gras=False):
        """Estimation (Helvetica ≈ 0,52 em en moyenne, 0,56 en gras) : suffisante pour couper les lignes."""
        return len(t) * taille * (0.56 if gras else 0.52)

    def paragraphe(self, x, y, t, largeur, taille=10, interligne=1.35, **style):
        """Écrit un texte coupé à la largeur donnée ; renvoie le y suivant."""
        mots, ligne_courante = t.split(), ""
        for mot in mots:
            essai = f"{ligne_courante} {mot}".strip()
            if self.largeur_texte(essai, taille, style.get("gras", False)) > largeur and ligne_courante:
                self.texte(x, y, ligne_courante, taille, **style)
                y += taille * interligne
                ligne_courante = mot
            else:
                ligne_courante = essai
        if ligne_courante:
            self.texte(x, y, ligne_courante, taille, **style)
            y += taille * interligne
        return y

    # --- Écriture ----------------------------------------------------------------------------------------
    def enregistrer(self, chemin):
        objets = []

        def ajouter(contenu):
            objets.append(contenu)
            return len(objets)

        polices = [ajouter(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % p)
                   for p in (b"Helvetica", b"Helvetica-Bold")]
        refs_images = []
        for l, h, rvb, alpha in self.images:
            smask = b""
            if alpha is not None:
                a = zlib.compress(alpha)
                n = ajouter(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
                            b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (l, h, len(a))
                            + a + b"\nendstream")
                smask = b"/SMask %d 0 R " % n
            c = zlib.compress(rvb)
            refs_images.append(ajouter(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace "
                                       b"/DeviceRGB /BitsPerComponent 8 %s/Filter /FlateDecode /Length %d >>\n"
                                       b"stream\n" % (l, h, smask, len(c)) + c + b"\nendstream"))
        xobjets = b" ".join(b"/Im%d %d 0 R" % (i + 1, n) for i, n in enumerate(refs_images))
        ressources = b"<< /Font << /F1 %d 0 R /F2 %d 0 R >> /XObject << %s >> >>" % (*polices, xobjets)
        refs_pages = []
        for flux, liens in self.pages:
            contenu = zlib.compress(b"\n".join(flux))
            n_flux = ajouter(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(contenu) + contenu
                             + b"\nendstream")
            annots = [ajouter(b"<< /Type /Annot /Subtype /Link /Rect [%.2f %.2f %.2f %.2f] /Border [0 0 0] "
                              b"/A << /S /URI /URI (%s) >> >>" % (x1, y1, x2, y2, _texte_pdf(u)))
                      for x1, y1, x2, y2, u in liens]
            refs_pages.append(ajouter(b"<< /Type /Page /Parent PARENT_REF /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
                                      b"/Resources %s /Annots [%s] >>" % (*A4, n_flux, ressources,
                                                                         b" ".join(b"%d 0 R" % a for a in annots))))
        n_arbre = ajouter(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
            b" ".join(b"%d 0 R" % p for p in refs_pages), len(refs_pages)))
        objets[:] = [o.replace(b"PARENT_REF", b"%d 0 R" % n_arbre) for o in objets]
        n_info = ajouter(b"<< /Title (%s) /Author (%s) /Producer (Orion) >>" % (_texte_pdf(self.titre),
                                                                                 _texte_pdf(self.auteur)))
        n_cat = ajouter(b"<< /Type /Catalog /Pages %d 0 R >>" % n_arbre)
        sortie, positions = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
        for i, o in enumerate(objets, 1):
            positions.append(len(sortie))
            sortie += b"%d 0 obj\n" % i + o + b"\nendobj\n"
        xref = len(sortie)
        sortie += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
        sortie += b"".join(b"%010d 00000 n \n" % p for p in positions)
        sortie += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objets) + 1, n_cat, n_info, xref)
        with open(chemin, "wb") as f:
            f.write(sortie)
