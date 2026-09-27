#!/usr/bin/env python3
"""orbit-cinema dogrulama kapilari (Blender'siz: python3 tests/verify.py)

Birlesimin kanunlari: pad-cinema kulesi + rocket-cinema fizi ayni sahnede
bulusunca firlatmanin kurallari:
    1. klepeler acilana kadar z = 0 (tutulma)
    2. acildiktan sonra z(t) monoton artar (kalkis)
    3. TWR > 1 (kalkis olasi)
    4. kule kafesi simetrik (geometri)
"""

import math
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.join(KOK, "..", "pad-cinema"))
sys.path.insert(0, os.path.join(KOK, "..", "rocket-cinema"))

import geometri as g  # noqa: E402
import roket_fizik as rf  # noqa: E402

KALKIS_T = 0.9
HIZLAN = 1.35


def z_ornekleri(dt=0.1, t_son=6.0):
    """firlatma.py'deki yerlesim kuralinin matematik karsiligi."""
    T, Z, V, M, K, DV = rf.ucus_sim(dt=0.05)

    def z_of(t):
        if t < KALKIS_T:
            return 0.0
        tt = max(0.0, min(T[-1], (t - KALKIS_T) * HIZLAN))
        i = min(range(len(T)), key=lambda k: abs(T[k] - tt))
        return max(0.0, Z[i])
    zler = []
    t = 0.0
    while t <= t_son + 1e-9:
        zler.append((round(t, 3), z_of(t)))
        t += dt
    return zler


def main():
    ok, fail = 0, 0

    def kapil(ad, kosul, detay=""):
        nonlocal ok, fail
        if kosul:
            ok += 1
            print(f"  [ok] {ad} {detay}")
        else:
            fail += 1
            print(f"  [FAIL] {ad} {detay}")

    # 1) tutulma: klepeler acilana kadar z = 0
    zler = z_ornekleri()
    tutulan = all(z == 0.0 for (t, z) in zler if t < KALKIS_T)
    kapil("klepeler acilana kadar z = 0", tutulan)

    # 2) kalkis: acilistan sonra monoton artis
    sonra = [z for (t, z) in zler if t >= KALKIS_T]
    monoton = all(sonra[i] <= sonra[i + 1] + 1e-9 for i in range(len(sonra) - 1))
    kapil("kalkis monoton yukselir", monoton,
          f"(z(6s) = {sonra[-1]:.1f} m)")

    # 3) TWR
    twr = rf.kalkis_twr()
    kapil("kalkis TWR > 1", twr > 1.0, f"(TWR = {twr:.2f})")

    # 4) kule kafesi simetrisi
    mesafeler = [math.hypot(x, y) for (x, y) in g.kose_kolonlari()]
    kapil("kule kafesi simetrik", max(mesafeler) - min(mesafeler) < 1e-9)

    # 5) ucuncu kapidan: gecis sonrasi apogee
    T, Z, V, M, K, DV = rf.ucus_sim()
    kapil("sim apogee > 100 km", Z[-1] > 100_000, f"({Z[-1] / 1000:.0f} km)")

    print(f"\n{'TUM KAPILAR GECTI' if fail == 0 else 'KAPILARDA FAIL VAR'}"
          f" ({ok} ok, {fail} fail)")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
