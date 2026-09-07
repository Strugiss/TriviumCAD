# -*- coding: utf-8 -*-
"""Test dei profili filetto sul CODICE REALE: import da core/ di TestN47Lab.

Anti-drift: nessuna funzione copiata. Nel core non esistono disp_filo/
disp_trap/disp_arrot (copie obsolete del vecchio test): i profili reali sono
_r_mod_profile (modulazione normalizzata) e _get_profile_2d (dimensioni in mm),
entrambi in core/thread.py. Eseguibile con `python test_profili.py` e pytest."""
import sys, os, math

CORE_DIR = r"C:\Users\Utente\Downloads\Esperimento\TestN47Lab"
if not os.path.isdir(CORE_DIR):
    raise SystemExit("CORE_DIR non trovato: %s" % CORE_DIR)
sys.path.insert(0, CORE_DIR)

from core.thread import _r_mod_profile, _get_profile_2d  # noqa: E402

PITCH = 2.0


def test_profondita_filo_iso60():
    prof = _get_profile_2d("Filo", PITCH)
    d = max(abs(y) for _, y in prof)
    assert abs(d - 0.6134 * PITCH) < 1e-9, "profondita Filo=%.6f attesa=%.6f (0.6134*pitch)" % (d, 0.6134 * PITCH)


def test_angoli_filo_60():
    prof = _get_profile_2d("Filo", PITCH)
    x, y = zip(*prof)
    dx = abs(x[1] - x[0])
    dy = abs(y[1] - y[0])
    ang_sx = math.degrees(math.atan2(dy, dx))
    dx = abs(x[3] - x[2])
    dy = abs(y[3] - y[2])
    ang_dx = math.degrees(math.atan2(dy, dx))
    assert abs(ang_sx - 60.0) < 1e-6, "angolo fianco sinistro=%.4f atteso 60.0" % ang_sx
    assert abs(ang_dx - 60.0) < 1e-6, "angolo fianco destro=%.4f atteso 60.0" % ang_dx


def test_simmetria_filo():
    prof = _get_profile_2d("Filo", PITCH)
    for x, y in prof:
        simm = any(abs(x2 + x) < 1e-9 and abs(y2 - y) < 1e-9 for x2, y2 in prof)
        assert simm, "punto (%s, %s) senza simmetrico rispetto a x=0" % (x, y)


def test_profondita_trapezio_arrot():
    d_t = max(abs(y) for _, y in _get_profile_2d("Trapezio", PITCH))
    assert abs(d_t - 0.5 * PITCH) < 1e-9, "profondita Trapezio=%.6f attesa=%.6f (0.5*pitch)" % (d_t, 0.5 * PITCH)
    d_a = max(abs(y) for _, y in _get_profile_2d("Arrotondato", PITCH))
    assert abs(d_a - 0.4 * PITCH) < 1e-9, "profondita Arrotondato=%.6f attesa=%.6f (0.4*pitch)" % (d_a, 0.4 * PITCH)


def test_r_mod_normalizzato():
    assert abs(_r_mod_profile(0.25, "Filo") - 1.0) < 1e-12, "Filo: rm(0.25) atteso 1.0 (cresta)"
    assert abs(_r_mod_profile(0.75, "Filo") + 1.0) < 1e-12, "Filo: rm(0.75) atteso -1.0 (valle)"
    assert abs(_r_mod_profile(0.5, "Filo")) < 1e-12, "Filo: rm(0.5) atteso 0.0"
    assert abs(_r_mod_profile(1.25, "Filo") - _r_mod_profile(0.25, "Filo")) < 1e-12, "Filo: non periodico (p+1)"
    v_filo = [_r_mod_profile(x / 1000.0, "Filo") for x in range(1000)]
    assert min(v_filo) >= -1 - 1e-12 and max(v_filo) <= 1 + 1e-12, "Filo: rm fuori da [-1, 1]"
    v_trap = [_r_mod_profile(x / 1000.0, "Trapezio") for x in range(1000)]
    assert min(v_trap) >= -1e-12 and max(v_trap) <= 1 + 1e-12, "Trapezio: rm fuori da [0, 1]"
    v_arrot = [_r_mod_profile(x / 1000.0, "Arrotondato") for x in range(1000)]
    assert min(v_arrot) >= -1e-12 and max(v_arrot) <= 1 + 1e-12, "Arrotondato: rm fuori da [0, 1]"


def main():
    tests = [test_profondita_filo_iso60, test_angoli_filo_60, test_simmetria_filo,
             test_profondita_trapezio_arrot, test_r_mod_normalizzato]
    ok = 0
    for fn in tests:
        try:
            fn()
            ok += 1
            print("[PASS] %s" % fn.__name__)
        except AssertionError as e:
            print("[FAIL] %s: %s" % (fn.__name__, e))
    print("\nEsito: %d/%d test superati" % (ok, len(tests)))
    print("\nTabella modulazione normalizzata rm(pn) dal core reale:")
    print("pn\tFilo\tTrapez\tArrot")
    for i in range(11):
        p = i / 10.0
        print("%.2f\t%.3f\t%.3f\t%.3f" % (p, _r_mod_profile(p, "Filo"), _r_mod_profile(p, "Trapezio"),
                                          _r_mod_profile(p, "Arrotondato")))
    sys.exit(0 if ok == len(tests) else 1)


if __name__ == "__main__":
    main()