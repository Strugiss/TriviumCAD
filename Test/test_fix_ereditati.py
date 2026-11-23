# -*- coding: utf-8 -*-
"""Test dei fix ereditati da PenguinCAD sul CODICE REALE di TriviumCAD.

Anti-drift: import diretti da `core/scene.py` e `triviumcad.py`; nessuna
funzione copiata. Coprono le parti verificabili senza GUI: scala ancorata a
Z=0, angolo 3D, testo dell'overlay e reset di `measurement_done`.
Eseguibile con `python test_fix_ereditati.py` e pytest.
"""
import math
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isdir(os.path.join(PROJECT_DIR, "core")):
    raise SystemExit("PROJECT_DIR non trovato: %s" % PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from core.scene import Scene  # noqa: E402
from triviumcad import GLWidget  # noqa: E402


def _cubo_z0_20():
    """Cubo 10x10x20 con base sul piano Z=0 (Z da 0 a 20)."""
    obj = trimesh.creation.box(extents=(10.0, 10.0, 20.0))
    obj.apply_translation([0.0, 0.0, 10.0])
    return obj


def test_scala_uniforme_ancorata_a_z0():
    scene = Scene()
    obj = _cubo_z0_20()
    scene.objects.append(obj)
    scene.selected_objects = [obj]
    vol_0 = float(obj.volume)

    assert scene.scale_selection_uniform(2.0) is True

    z = np.asarray(obj.vertices, dtype=np.float64)[:, 2]
    assert abs(float(z.min()) - 0.0) < 1e-9, "Z min=%.9f, atteso 0.0" % z.min()
    assert abs(float(z.max()) - 40.0) < 1e-9, "Z max=%.9f, atteso 40.0" % z.max()
    assert abs(float(obj.volume) / vol_0 - 8.0) < 1e-6, "volume non x8"


def test_scala_uniforme_ancora_esplicita():
    scene = Scene()
    obj = _cubo_z0_20()
    scene.objects.append(obj)
    scene.selected_objects = [obj]

    assert scene.scale_selection_uniform(0.5, ancora_z=20.0) is True

    z = np.asarray(obj.vertices, dtype=np.float64)[:, 2]
    assert abs(float(z.min()) - 10.0) < 1e-9, "Z min=%.9f, atteso 10.0" % z.min()
    assert abs(float(z.max()) - 20.0) < 1e-9, "Z max=%.9f, atteso 20.0" % z.max()


def test_measurement_done_reset_alla_nuova_misura():
    scene = Scene()
    obj = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    scene.objects.append(obj)
    scene.selected_objects = [obj]

    assert scene.measure_distance() is True
    assert scene.measurement_done is False
    scene.measurement_done = True
    assert scene.measure_distance() is True
    assert scene.measurement_done is False


def test_angolo_3d_su_piano_z20():
    a = GLWidget._angle_between([0.0, 0.0, 20.0],
                                [10.0, 0.0, 20.0],
                                [10.0, 10.0, 20.0])
    assert abs(math.degrees(a) - 90.0) < 1e-9


def test_testo_misura_distanza_e_angolo():
    assert GLWidget._testo_misura(
        "distance", [[0.0, 0.0, 20.0], [10.0, 0.0, 20.0]]) == "10.00 mm"
    assert GLWidget._testo_misura(
        "angle", [[0.0, 0.0, 20.0], [10.0, 0.0, 20.0], [10.0, 10.0, 20.0]]
    ) == "90.0°"
    assert GLWidget._testo_misura("distance", [[0.0, 0.0, 0.0]]) == ""


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    ok = 0
    for fn in tests:
        try:
            fn()
            ok += 1
            print("[PASS] %s" % fn.__name__)
        except AssertionError as e:
            print("[FAIL] %s: %s" % (fn.__name__, e))
    print("\nEsito: %d/%d test superati" % (ok, len(tests)))
    sys.exit(0 if ok == len(tests) else 1)


if __name__ == "__main__":
    main()
