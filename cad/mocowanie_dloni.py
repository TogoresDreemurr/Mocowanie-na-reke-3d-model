"""
Mocowanie na grzbiet dłoni (baza pod czujniki/silniki do rejestracji ruchu palców).

Parametryczny model w build123d. Uruchomienie:
    pip install build123d
    python cad/mocowanie_dloni.py

Generuje do katalogów step/ i stl/:
  - plytka_dloni_{prawa,lewa}  - płytka zakładana na grzbiet dłoni, mocowana rzepami
  - prowadnica_palcow_{prawa,lewa} - opcjonalna prowadnica pasków od palców (przykręcana)

Układ współrzędnych (dłoń w pozycji "grzbietem do góry", prawa ręka):
  +Y  - w stronę palców
  +X  - w stronę małego palca (kciuk jest po stronie -X)
  +Z  - od grzbietu dłoni w górę
  z = 0 to najwyższy punkt skóry pod płytką (środek łuku od spodu).

Pliki STEP są w układzie dłoni (wygodne do dalszej edycji w CAD),
pliki STL są już obrócone do druku (płaska strona na stole, bez podpór).
"""

from dataclasses import dataclass
from math import atan2, degrees, hypot, sqrt
from pathlib import Path

from build123d import (
    Axis,
    Box,
    BuildLine,
    BuildSketch,
    Cylinder,
    Line,
    Location,
    Plane,
    Polygon,
    Pos,
    Rectangle,
    Rot,
    SlotCenterToCenter,
    Text,
    ThreePointArc,
    Vector,
    chamfer,
    export_step,
    export_stl,
    extrude,
    fillet,
    make_face,
    mirror,
    offset,
)


# ---------------------------------------------------------------------------
# PARAMETRY - zmieniaj tutaj (wymiary w mm)
# ---------------------------------------------------------------------------
@dataclass
class Param:
    # --- rozmiar dłoni -----------------------------------------------------
    # Długość płytki (od strony nadgarstka do strony kłykci).
    # Zmierz grzbiet dłoni od zgięcia nadgarstka do kłykci i odejmij ~25 mm,
    # żeby płytka nie blokowała zgięcia nadgarstka ani zaciśnięcia pięści.
    dlugosc: float = 76.0
    # Szerokość przy kłykciach (zmierz szerokość dłoni na kłykciach II-V
    # i odejmij ~10 mm).
    szerokosc_przod: float = 74.0
    # Szerokość od strony nadgarstka.
    szerokosc_tyl: float = 62.0
    # O ile krawędź przednia cofa się od strony palca wskazującego / małego
    # (linia kłykci jest skośna - kłykieć małego palca jest najbardziej z tyłu).
    cofniecie_wskazujacy: float = 5.0
    cofniecie_maly: float = 12.0
    # Położenie (X) najdalej wysuniętego punktu krawędzi przedniej - kłykieć
    # palca środkowego.
    x_srodkowy: float = -10.0
    # Wklęśnięcie krawędzi od strony nadgarstka (luz przy odgięciu nadgarstka).
    wklesniecie_tyl: float = 3.0
    # Promień łuku poprzecznego grzbietu dłoni (spód płytki).
    # Mniejszy = bardziej wygięta. 80-100 pasuje na większość dłoni,
    # resztę wyrównuje pianka 2-3 mm przyklejona od spodu.
    promien_luku: float = 90.0
    # Grubość płytki w najcieńszym miejscu (środek). Boki są grubsze, bo góra
    # jest płaska (płaski blat pod Twoje czujniki/silniki).
    grubosc: float = 6.0
    # Promień zaokrąglenia narożników w widoku z góry.
    promien_naroznikow: float = 8.0
    # Faza na górnych krawędziach (strona stołu przy druku -> 45 st., bez podpór).
    faza_gora: float = 2.5
    # Zaokrąglenie dolnych krawędzi (strona skóry).
    zaokraglenie_dol: float = 2.0

    # --- paski (rzepy) -------------------------------------------------------
    szerokosc_paska: float = 20.0   # rzep 20 mm (dla 25 mm daj 25 i dlugosc ~85)
    grubosc_szczeliny: float = 3.5  # szerokość szczeliny na pasek
    luz_paska: float = 2.0          # szczelina dłuższa o tyle od szerokości paska
    odsuniecie_szczeliny: float = 7.0  # środek szczeliny od krawędzi bocznej
    # Pozycje (Y) środków pasków. Przedni idzie przez dłoń między kciukiem
    # a palcem wskazującym, tylny wokół nasady dłoni.
    paski_y: tuple = (19.0, 45.0)

    # --- siatka otworów montażowych na blacie ------------------------------
    raster: float = 10.0            # rozstaw otworów (siatka 10 x 10 mm)
    otwor_d: float = 2.8            # 2.8 = wkręt M3 wkręcany w plastik,
                                    # 4.0 = wtopiona tulejka M3 (heat-set)
    otwor_glebokosc: float = 4.5    # nieprzelotowe - min. 1.5 mm materiału od skóry
    margines_otworow: float = 6.5   # min. odległość środka otworu od krawędzi
    luz_od_szczelin: float = 2.5    # min. ścianka między otworem a szczeliną

    # --- oznaczenie --------------------------------------------------------
    grawer_glebokosc: float = 0.6

    # --- prowadnica pasków od palców (opcjonalna część) ---------------------
    # X osi palców (prawa ręka): wskazujący, środkowy, serdeczny, mały.
    palce_x: tuple = (-29.0, -10.0, 9.0, 27.0)
    okno_szer: float = 12.0         # szerokość okna na pasek(-ki) jednego palca
    okno_wys: float = 5.0           # wysokość okna
    okno_z: float = 9.0             # wysokość środka okna nad blatem płytki
    prowadnica_wys: float = 15.0    # całkowita wysokość prowadnicy
    prowadnica_sciana: float = 6.0  # grubość ściany z oknami
    prowadnica_stopka: float = 4.0  # grubość stopki przykręcanej do blatu
    sruba_otwor_d: float = 3.4      # otwór przelotowy M3
    prowadnica_sruby_x: tuple = (-20.0, 20.0)


# ---------------------------------------------------------------------------
# Geometria
# ---------------------------------------------------------------------------
def kontur(p: Param):
    """Obrys płytki w widoku z góry (prawa ręka)."""
    L = p.dlugosc
    a = (-p.szerokosc_tyl / 2, 0)
    b = (p.szerokosc_tyl / 2, 0)
    c = (p.szerokosc_przod / 2, L - p.cofniecie_maly)
    d = (p.x_srodkowy, L)
    e = (-p.szerokosc_przod / 2, L - p.cofniecie_wskazujacy)
    with BuildSketch() as sk:
        with BuildLine():
            ThreePointArc(a, (0, p.wklesniecie_tyl), b)
            Line(b, c)
            ThreePointArc(c, d, e)
            Line(e, a)
        make_face()
        fillet(sk.vertices(), radius=p.promien_naroznikow)
    return sk.sketch.face()


def szczeliny(p: Param):
    """Lista (x, y, kąt) środków szczelin na paski - po dwie z każdej strony."""
    wynik = []
    for strona, cofniecie in ((1, p.cofniecie_maly), (-1, p.cofniecie_wskazujacy)):
        x0, y0 = strona * p.szerokosc_tyl / 2, 0.0
        x1, y1 = strona * p.szerokosc_przod / 2, p.dlugosc - cofniecie
        dx, dy = x1 - x0, y1 - y0
        n = hypot(dx, dy)
        kat = degrees(atan2(dy, dx))
        # normalna do krawędzi skierowana do środka płytki
        nx, ny = -strona * dy / n, strona * dx / n
        for y in p.paski_y:
            t = (y - y0) / dy
            xe = x0 + t * dx
            wynik.append((xe + nx * p.odsuniecie_szczeliny,
                          y + ny * p.odsuniecie_szczeliny, kat))
    return wynik


def ksztalt_szczeliny(p: Param, x, y, kat, powiekszenie=0.0):
    dl = p.szerokosc_paska + p.luz_paska
    sz = p.grubosc_szczeliny + 2 * powiekszenie
    return Pos(x, y) * SlotCenterToCenter(dl - p.grubosc_szczeliny, sz, rotation=kat)


def strefa_etykiety():
    """Miejsce na grawer (bez otworów) - środek przy nadgarstku."""
    return Pos(0, 11) * Rectangle(14, 12)


def punkty_otworow(p: Param):
    dozwolone = offset(kontur(p), -p.margines_otworow)
    for (x, y, kat) in szczeliny(p):
        dozwolone -= ksztalt_szczeliny(p, x, y, kat,
                                       p.luz_od_szczelin + p.otwor_d / 2)
    dozwolone -= strefa_etykiety()
    pkt = []
    n = int(60 / p.raster) + 1
    for i in range(-n, n + 1):
        for j in range(0, int(p.dlugosc / p.raster) + 1):
            x, y = i * p.raster, j * p.raster
            if any(f.is_inside(Vector(x, y, 0)) for f in dozwolone.faces()):
                pkt.append((x, y))
    return pkt


def wysokosc_spodu(p: Param, x):
    """Z spodu płytki (powierzchnia skóry) dla danego X."""
    R = p.promien_luku
    return sqrt(R * R - x * x) - R


def plytka(p: Param, prawa: bool = True):
    R = p.promien_luku
    obrys = kontur(p)

    # Pryzmat z obrysu, od dołu przycięty walcem (łuk grzbietu dłoni).
    bryla = Pos(0, 0, -40) * extrude(obrys, amount=40 + p.grubosc)
    walec = Location((0, p.dlugosc / 2, -R), (90, 0, 0)) * Cylinder(R, p.dlugosc + 40)
    bryla = bryla - walec

    # Zaokrąglenie krawędzi od strony skóry.
    if p.zaokraglenie_dol > 0:
        spod = max((f for f in bryla.faces() if f.normal_at(f.center()).Z < -0.3),
                   key=lambda f: f.area)
        bryla = fillet(spod.edges(), radius=p.zaokraglenie_dol)

    # Faza na krawędziach blatu.
    if p.faza_gora > 0:
        gora = bryla.faces().sort_by(Axis.Z)[-1]
        bryla = chamfer(gora.edges(), length=p.faza_gora)

    # Szczeliny na rzepy (pionowe, przelotowe) z fazami dla wygody paska.
    for (x, y, kat) in szczeliny(p):
        ksztalt = ksztalt_szczeliny(p, x, y, kat)
        bryla -= Pos(0, 0, -30) * extrude(ksztalt, amount=30 + p.grubosc + 1)
        f = 0.8
        faza = Pos(0, 0, p.grubosc - f) * extrude(ksztalt, amount=f, taper=-45)
        bryla -= faza

    # Siatka otworów montażowych (nieprzelotowe, od góry).
    for (x, y) in punkty_otworow(p):
        bryla -= Pos(x, y, p.grubosc - p.otwor_glebokosc / 2 + 0.5) * Cylinder(
            p.otwor_d / 2, p.otwor_glebokosc + 1)

    if not prawa:
        bryla = mirror(bryla, Plane.YZ)

    # Grawer: litera ręki + strzałka w stronę palców (zawsze czytelny z góry).
    litera = "P" if prawa else "L"
    g = p.grawer_glebokosc
    znak = Pos(-3.5, 10.5, p.grubosc - g) * extrude(
        Text(litera, font_size=8), amount=g + 1)
    strzalka = Pos(3.5, 10.5, p.grubosc - g) * extrude(
        Polygon((0, 4.5), (-2.8, 0), (-1, 0), (-1, -4), (1, -4), (1, 0), (2.8, 0)),
        amount=g + 1)
    bryla = bryla - znak - strzalka
    return bryla


def prowadnica(p: Param, prawa: bool = True):
    """Opcjonalna prowadnica pasków od palców, przykręcana do siatki otworów."""
    otwory = punkty_otworow(p)
    xs = p.prowadnica_sruby_x
    rzedy = sorted({y for (x, y) in otwory
                    if all((xx, y) in otwory for xx in xs)})
    y_rzad = rzedy[-1]  # najbliższy palcom rząd z oboma otworami

    x_min = min(p.palce_x) - p.okno_szer / 2 - 5
    x_max = max(p.palce_x) + p.okno_szer / 2 + 5
    dl = x_max - x_min
    xc = (x_min + x_max) / 2
    y0, y1 = y_rzad - 6, y_rzad + 10
    s = p.prowadnica_stopka

    # Stopka tylko między szczelinami na rzepy (żeby ich nie zasłaniała),
    # ściana z oknami na całą szerokość.
    sx = max(abs(x) for x in xs) + 5
    stopka = Pos(0, (y0 + y1) / 2, s / 2) * Box(2 * sx, y1 - y0, s)
    sciana = Pos(xc, y1 - p.prowadnica_sciana / 2, p.prowadnica_wys / 2) * Box(
        dl, p.prowadnica_sciana, p.prowadnica_wys)
    bryla = stopka + sciana
    bryla = fillet(bryla.edges().filter_by(Axis.Z), radius=1.0)

    for x in p.palce_x:
        okno = Pos(x, y1 + 1, p.okno_z) * (Rot(90, 0, 0) * extrude(
            SlotCenterToCenter(p.okno_szer - p.okno_wys, p.okno_wys),
            amount=p.prowadnica_sciana + 2))
        bryla -= okno
        # fazy wejściowe po obu stronach, żeby pasek nie zahaczał
        for yy, kier in ((y1, 1), (y1 - p.prowadnica_sciana, -1)):
            fz = Pos(x, yy + kier * 0.01, p.okno_z) * (Rot(90 * kier, 0, 0) * extrude(
                SlotCenterToCenter(p.okno_szer - p.okno_wys, p.okno_wys + 1.6),
                amount=0.8, taper=45))
            bryla -= fz

    for x in xs:
        bryla -= Pos(x, y_rzad, s / 2) * Cylinder(p.sruba_otwor_d / 2, s + 2)

    # Ustawienie na blacie płytki.
    bryla = Pos(0, 0, p.grubosc) * bryla
    if not prawa:
        bryla = mirror(bryla, Plane.YZ)
    return bryla


def do_druku(bryla, odwroc: bool):
    """Obrót do pozycji druku i postawienie na z = 0."""
    if odwroc:
        bryla = Rot(0, 180, 0) * bryla
    bb = bryla.bounding_box()
    return Pos(-bb.center().X, -bb.center().Y, -bb.min.Z) * bryla


def main():
    p = Param()
    root = Path(__file__).resolve().parent.parent
    (root / "step").mkdir(exist_ok=True)
    (root / "stl").mkdir(exist_ok=True)

    for prawa, nazwa in ((True, "prawa"), (False, "lewa")):
        pl = plytka(p, prawa)
        pr = prowadnica(p, prawa)
        export_step(pl, str(root / "step" / f"plytka_dloni_{nazwa}.step"))
        export_step(pr, str(root / "step" / f"prowadnica_palcow_{nazwa}.step"))
        export_stl(do_druku(pl, odwroc=True),
                   str(root / "stl" / f"plytka_dloni_{nazwa}.stl"),
                   tolerance=0.02, angular_tolerance=0.1)
        export_stl(do_druku(pr, odwroc=False),
                   str(root / "stl" / f"prowadnica_palcow_{nazwa}.stl"),
                   tolerance=0.02, angular_tolerance=0.1)
        if prawa:  # lewa to lustro, wystarczy sprawdzić raz
            kolizja = sum((pr & (Pos(0, 0, p.grubosc) * extrude(
                ksztalt_szczeliny(p, x, y, kat), amount=3))).volume
                for (x, y, kat) in szczeliny(p))
            if kolizja > 0.01:
                print(f"UWAGA: prowadnica zasłania szczeliny na rzepy ({kolizja:.1f} mm3)")
        bb = pl.bounding_box()
        print(f"{nazwa}: płytka {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, "
              f"objętość {pl.volume / 1000:.1f} cm3, otwory: {len(punkty_otworow(p))}")


if __name__ == "__main__":
    main()
