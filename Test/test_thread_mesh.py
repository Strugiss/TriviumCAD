# -*- coding: utf-8 -*-
"""Test della mesh filettata sul CODICE REALE: import da core/ di TestN47Lab.

Anti-drift: nessuna funzione copiata nel test. Le funzioni testate sono
_compute_thread_mesh, _generate_base_mesh, _get_profile_2d, _r_mod_profile
(core/thread.py) e _surface_radius_at (core/cam.py), importate dal progetto.
Eseguibile con `python test_thread_mesh.py` e con pytest."""
import sys, os, math
import numpy as np
import trimesh

CORE_DIR = r"C:\Users\Utente\Downloads\Esperimento\TestN47Lab"
if not os.path.isdir(CORE_DIR):
    raise SystemExit("CORE_DIR non trovato: %s" % CORE_DIR)
sys.path.insert(0, CORE_DIR)

from core.thread import _compute_thread_mesh, _generate_base_mesh, _get_profile_2d, _r_mod_profile  # noqa: E402
from core.cam import _surface_radius_at  # noqa: E402

R, H, PITCH, TURNS = 10.0, 30.0, 2.0, 12
D = 0.6134 * PITCH


def _cilindro(radius=R, height=H, sections=32):
    cyl = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    cyl.metadata.update({"shape_type": "cylinder", "params": {"raggio": radius}, "name": "cilindro_test"})
    return cyl


def _attesi(radius, height, turns):
    bounds = np.array([[-radius, -radius, -height / 2], [radius, radius, height / 2]])
    rr = math.hypot(bounds[1][0] - bounds[0][0], bounds[1][1] - bounds[0][1]) * 0.5
    N = min(max(24, int(2 * math.pi * rr / 1.5), 16), 96)
    M = min(max(2, turns) * 6, 120)
    return N, M, (M + 1) * N + 2


def test_vertici_attesi():
    m = _compute_thread_mesh(_cilindro(), "Esterna", pitch=PITCH, turns=TURNS, profile="Filo")
    N, M, attesi = _attesi(R, H, TURNS)
    assert N == 59 and M == 72 and attesi == 4309, "formula attesi: N=%d M=%d vertici=%d" % (N, M, attesi)
    assert len(m.vertices) == attesi, "vertici=%d attesi=%d (formula (M+1)*N+2)" % (len(m.vertices), attesi)
    assert len(m.faces) == 2 * N * (M + 1), "facce=%d attese=%d" % (len(m.faces), 2 * N * (M + 1))


def test_pitch():
    m = _compute_thread_mesh(_cilindro(), "Esterna", pitch=PITCH, turns=TURNS, profile="Filo")
    v = m.vertices
    r = np.linalg.norm(v[:, :2], axis=1)
    a = np.arctan2(v[:, 1], v[:, 0])
    lat = r > 1.0
    pn = ((a + v[:, 2] * 2 * np.pi / PITCH) % (2 * np.pi)) / (2 * np.pi)
    bins = np.floor(pn[lat] * 96).astype(int)
    stds = []
    for b in range(96):
        sel = bins == b
        if sel.sum() > 5:
            stds.append(r[lat][sel].std())
    max_std = max(stds)
    assert max_std < 0.03, "pitch non rispettato: max std raggio per bin di fase = %.4f" % max_std
    mask = (np.abs(a) < 0.05) & lat
    zs, rs = v[mask, 2], r[mask]
    order = np.argsort(zs)
    zs, rs = zs[order], rs[order]
    d = np.diff(rs)
    crest_idx = np.where((d[:-1] > 0) & (d[1:] < 0))[0]
    n_creste = len(crest_idx)
    giri_attesi = round(H / PITCH)
    assert n_creste == giri_attesi, "giri=%d attesi=%d (H/pitch)" % (n_creste, giri_attesi)
    if len(crest_idx) > 1:
        sp = np.diff(zs[crest_idx]).mean()
        assert abs(sp - PITCH) < 0.1, "pitch medio misurato=%.3f atteso=%.3f" % (sp, PITCH)


def test_bounds_radiali():
    m = _compute_thread_mesh(_cilindro(), "Esterna", pitch=PITCH, turns=TURNS, profile="Filo")
    r = np.linalg.norm(m.vertices[:, :2], axis=1)
    r_min_lat = r[r > 1.0].min()
    assert abs(r_min_lat - (R - D / 2)) < 0.01, \
        "minimo radiale superficie=%.4f atteso=%.4f (r-d/2)" % (r_min_lat, R - D / 2)
    assert abs(r.max() - (R + D / 2)) < 0.01, \
        "massimo radiale=%.4f atteso=%.4f (r+d/2, creste)" % (r.max(), R + D / 2)
    z = m.vertices[:, 2]
    assert abs(z.min() + H / 2) < 1e-9 and abs(z.max() - H / 2) < 1e-9, \
        "bounds Z=[%.3f, %.3f] attesi [-%.1f, %.1f]" % (z.min(), z.max(), H / 2, H / 2)
    centri = r <= 1.0
    assert int(centri.sum()) == 2, "attesi 2 vertici centrali tappo, trovati %d" % int(centri.sum())
    assert np.allclose(r[centri], 0.0, atol=1e-6), \
        "FIX TAPPI NON APPLICATO: centri tappo fuori asse, raggio=%s atteso 0.0" % np.round(r[centri], 4)


def test_watertight():
    m = _compute_thread_mesh(_cilindro(), "Esterna", pitch=PITCH, turns=TURNS, profile="Filo")
    assert m.is_watertight, "mesh non watertight"
    assert m.euler_number == 2, "numero di Eulero=%d atteso 2" % m.euler_number


def test_volume():
    m = _compute_thread_mesh(_cilindro(), "Esterna", pitch=PITCH, turns=TURNS, profile="Filo")
    v_pieno = math.pi * R * R * H
    scarto = abs(m.volume - v_pieno) / v_pieno
    assert scarto < 0.05, "volume=%.1f vs cilindro pieno=%.1f (scarto %.1f%%)" % (m.volume, v_pieno, 100 * scarto)


def analyze_mesh(mesh, label):
    print("\n=== ANALISI: %s ===" % label)
    print("Vertici: %d  Facce: %d" % (len(mesh.vertices), len(mesh.faces)))
    areas = mesh.area_faces
    degenerate = int(np.sum(areas < 1e-10))
    print("[Facce] degenerate (area<1e-10): %d  area media: %.6f" % (degenerate, np.mean(areas)))
    faceless_normals = mesh.face_normals
    face_centers = mesh.triangles_center
    radial = face_centers[:, :2]
    radial_norm = np.linalg.norm(radial, axis=1)
    radial_unit = np.zeros_like(radial)
    mask = radial_norm > 1e-8
    radial_unit[mask] = radial[mask] / radial_norm[mask, np.newaxis]
    n_xy = faceless_normals[:, :2]
    n_xy_norm = np.linalg.norm(n_xy, axis=1)
    n_xy_unit = np.zeros_like(n_xy)
    m2 = n_xy_norm > 1e-8
    n_xy_unit[m2] = n_xy[m2] / n_xy_norm[m2, np.newaxis]
    dot = np.sum(n_xy_unit * radial_unit, axis=1)
    inverted = int(np.sum(dot < 0))
    print("[Normali] facce con normale verso l'interno: %d/%d (%.1f%%)" % (inverted, len(dot), 100 * inverted / len(dot)))
    if inverted > len(dot) * 0.1:
        print("[NORMALE] => ALTA PERCENTUALE DI NORMALI INVERTITE.")
    else:
        print("[NORMALE] => Normali per lo piu corrette (verso esterno).")
    print("[Manifold] watertight: %s  Eulero: %d" % (mesh.is_watertight, mesh.euler_number))
    radii = np.linalg.norm(mesh.vertices[:, :2], axis=1)
    print("[Raggio] min: %.4f  max: %.4f  (senza centri tappo: %.4f)" % (
        radii.min(), radii.max(), radii[radii > 1.0].min()))
    print("[Z] min: %.3f  max: %.3f" % (mesh.vertices[:, 2].min(), mesh.vertices[:, 2].max()))


def _configurazioni():
    yield "Filo nominale (R=10 H=30 p=2 t=12)", _compute_thread_mesh(_cilindro(), "Esterna", pitch=PITCH, turns=TURNS, profile="Filo")
    yield "Filo profondita 2x", _compute_thread_mesh(_cilindro(), "Esterna", pitch=PITCH, turns=TURNS, profile="Filo", depth=2 * D)
    yield "Filo profondita 4x", _compute_thread_mesh(_cilindro(), "Esterna", pitch=PITCH, turns=TURNS, profile="Filo", depth=4 * D)
    yield "Raggio 3, Filo nominale", _compute_thread_mesh(_cilindro(radius=3, height=20), "Esterna", pitch=2, turns=8, profile="Filo")


def main():
    tests = [test_vertici_attesi, test_pitch, test_bounds_radiali, test_watertight, test_volume]
    ok = 0
    for fn in tests:
        try:
            fn()
            ok += 1
            print("[PASS] %s" % fn.__name__)
        except AssertionError as e:
            print("[FAIL] %s: %s" % (fn.__name__, e))
    print("\nEsito: %d/%d test superati" % (ok, len(tests)))
    for desc, m in _configurazioni():
        analyze_mesh(m, desc)
    sys.exit(0 if ok == len(tests) else 1)


if __name__ == "__main__":
    main()