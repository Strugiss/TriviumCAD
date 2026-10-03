# -*- coding: utf-8 -*-
"""Test 2PenAxE sul CODICE REALE: funzioni pure di sketch.py + modello scena.

Anti-drift: nessuna funzione copiata; import diretto da `sketch.py` e
`core/scene.py` del progetto. Eseguibile con `python test_sketch.py` e pytest.
"""
import json
import math
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isdir(os.path.join(PROJECT_DIR, "core")):
    raise SystemExit("PROJECT_DIR non trovato: %s" % PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

from sketch import (  # noqa: E402
    plane_to_3d, entity_to_3d_paths, entity_segments_2d, entity_anchor_points,
    entity_hit_test, entity_translate, intersection_points, find_snap,
    snap_candidates, _arc_points,
)
from core.scene import Scene  # noqa: E402

LINE_XY = {"type": "line", "plane": "XY", "p1": [0.0, 0.0], "p2": [10.0, 0.0]}
LINE_XZ = {"type": "line", "plane": "XZ", "p1": [10.0, 20.0], "p2": [30.0, 40.0]}
RECT = {"type": "rect", "plane": "XY", "p1": [0.0, 0.0], "p2": [20.0, 10.0]}
CIRCLE = {"type": "circle", "plane": "XY", "center": [0.0, 0.0], "radius": 5.0}
ARC = {"type": "arc", "plane": "XY", "center": [0.0, 0.0], "radius": 5.0,
       "a1": 0.0, "a2": 90.0}


def test_plane_to_3d_mapping():
    assert plane_to_3d("XY", 10.0, 20.0) == (10.0, 20.0, 0.0)
    assert plane_to_3d("XZ", 10.0, 20.0) == (10.0, 0.0, 20.0)
    assert plane_to_3d("YZ", 10.0, 20.0) == (0.0, 10.0, 20.0)


def test_entity_to_3d_line_su_piani():
    paths = entity_to_3d_paths(LINE_XZ)
    assert paths == [[(10.0, 0.0, 20.0), (30.0, 0.0, 40.0)]], paths
    paths = entity_to_3d_paths(LINE_XY)
    assert paths == [[(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]], paths


def test_entity_to_3d_rect_chiuso():
    paths = entity_to_3d_paths(RECT)
    assert len(paths) == 1 and len(paths[0]) == 5
    assert paths[0][0] == paths[0][-1], "rettangolo non chiuso"


def test_entity_to_3d_circle_chiuso():
    paths = entity_to_3d_paths(CIRCLE)
    assert len(paths) == 1 and len(paths[0]) == 65
    assert abs(paths[0][0][0] - 5.0) < 1e-9 and abs(paths[0][0][1]) < 1e-9
    d = math.hypot(paths[0][0][0] - paths[0][-1][0], paths[0][0][1] - paths[0][-1][1])
    assert d < 1e-9, "cerchio non chiuso (dist=%s)" % d


def test_entity_to_3d_arco_90():
    pts = _arc_points(0.0, 0.0, 5.0, 0.0, 90.0, n=9)
    assert abs(pts[0][0] - 5.0) < 1e-9 and abs(pts[0][1]) < 1e-9
    assert abs(pts[-1][0]) < 1e-9 and abs(pts[-1][1] - 5.0) < 1e-9
    paths = entity_to_3d_paths(ARC)
    assert len(paths) == 1 and len(paths[0]) >= 10


def test_serializzazione_json_roundtrip():
    ents = [LINE_XY, LINE_XZ, RECT, CIRCLE, ARC]
    blob = json.dumps(ents, ensure_ascii=False)
    back = json.loads(blob)
    assert back == ents


def test_anchor_points_endpoint_midpoint_centro():
    ents = [LINE_XY, CIRCLE, ARC]
    anchors = entity_anchor_points(ents, "XY")
    assert (0.0, 0.0, "Endpoint") in anchors
    assert (10.0, 0.0, "Endpoint") in anchors
    assert (5.0, 0.0, "Midpoint") in anchors
    assert (0.0, 0.0, "Centro") in anchors
    # arco: estremi a 0 e 90 gradi
    assert any(abs(u - 5.0) < 1e-9 and abs(v) < 1e-9 and t == "Endpoint"
               for u, v, t in anchors)


def test_find_snap_endpoint_e_midpoint():
    anchors = {"endpoint": True, "midpoint": False, "centri": False,
               "intersezioni": False, "assi": False, "origine": False,
               "griglia": False}
    s = find_snap([LINE_XY], "XY", anchors, (0.5, 0.5), 10.0, 10.0)
    assert s is not None and s[2] == "Endpoint"
    assert abs(s[0]) < 1e-9 and abs(s[1]) < 1e-9
    anchors2 = dict(anchors, endpoint=False, midpoint=True)
    s2 = find_snap([LINE_XY], "XY", anchors2, (5.2, 0.3), 10.0, 10.0)
    assert s2 is not None and s2[2] == "Midpoint"
    assert abs(s2[0] - 5.0) < 1e-9 and abs(s2[1]) < 1e-9


def test_find_snap_origine_assi_griglia():
    base = {"endpoint": False, "midpoint": False, "centri": False,
            "intersezioni": False, "assi": False, "origine": False,
            "griglia": False}
    # Origine
    s = find_snap([], "XY", dict(base, origine=True), (0.2, 0.2), 10.0, 10.0)
    assert s is not None and s[2] == "Origine" and s[0] == 0.0 and s[1] == 0.0
    # Proiezione sugli assi (u, 0)
    s = find_snap([], "XY", dict(base, assi=True), (10.0, 0.4), 10.0, 10.0)
    assert s is not None and s[2] == "Assi" and abs(s[0] - 10.0) < 1e-9
    assert abs(s[1]) < 1e-9
    # Griglia: aggancia sempre al multiplo più vicino
    s = find_snap([], "XY", dict(base, griglia=True), (12.3, 7.8), 10.0, 4.0)
    assert s is not None and s[2] == "Griglia"
    assert abs(s[0] - 10.0) < 1e-9 and abs(s[1] - 10.0) < 1e-9


def test_snap_candidates_intersezioni():
    l1 = {"type": "line", "plane": "XY", "p1": [0.0, 0.0], "p2": [10.0, 10.0]}
    l2 = {"type": "line", "plane": "XY", "p1": [0.0, 10.0], "p2": [10.0, 0.0]}
    pts = intersection_points([l1, l2], "XY")
    assert len(pts) == 1
    assert abs(pts[0][0] - 5.0) < 1e-9 and abs(pts[0][1] - 5.0) < 1e-9
    anchors = {"endpoint": False, "midpoint": False, "centri": False,
               "intersezioni": True, "assi": False, "origine": False,
               "griglia": False}
    cands = snap_candidates([l1, l2], "XY", anchors)
    assert (5.0, 5.0, "Intersezione") in cands


def test_intersezioni_segmento_cerchio_e_cerchi():
    seg = {"type": "line", "plane": "XY", "p1": [-10.0, 0.0], "p2": [10.0, 0.0]}
    pts = sorted(p[0] for p in intersection_points([seg, CIRCLE], "XY"))
    assert len(pts) == 2
    assert abs(pts[0] + 5.0) < 1e-9 and abs(pts[1] - 5.0) < 1e-9
    c2 = {"type": "circle", "plane": "XY", "center": [8.0, 0.0], "radius": 5.0}
    pts2 = intersection_points([CIRCLE, c2], "XY")
    assert len(pts2) == 2
    for x, y in pts2:
        assert abs(x - 4.0) < 1e-9 and abs(abs(y) - 3.0) < 1e-9


def test_hit_test_line_circle_arc():
    assert entity_hit_test(LINE_XY, 5.0, 0.5, 1.0)
    assert not entity_hit_test(LINE_XY, 5.0, 2.0, 1.0)
    assert entity_hit_test(CIRCLE, 5.2, 0.0, 0.5)
    assert not entity_hit_test(CIRCLE, 0.0, 0.0, 0.5)
    a = math.radians(45.0)
    assert entity_hit_test(ARC, 5.0 * math.cos(a), 5.0 * math.sin(a), 0.2)
    assert not entity_hit_test(ARC, -5.0, 0.0, 0.2), "punto a 180° non è sull'arco 0-90"


def test_entity_translate():
    e = json.loads(json.dumps(LINE_XY))
    entity_translate(e, 3.0, -2.0)
    assert e["p1"] == [3.0, -2.0] and e["p2"] == [13.0, -2.0]
    c = json.loads(json.dumps(CIRCLE))
    entity_translate(c, 1.5, 2.5)
    assert c["center"] == [1.5, 2.5] and c["radius"] == 5.0


def test_segments_polyline_e_rect():
    poly = {"type": "polyline", "plane": "XY",
            "points": [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]}
    segs = entity_segments_2d(poly)
    assert len(segs) == 2
    assert entity_segments_2d(RECT) == [
        ((0.0, 0.0), (20.0, 0.0)), ((20.0, 0.0), (20.0, 10.0)),
        ((20.0, 10.0), (0.0, 10.0)), ((0.0, 10.0), (0.0, 0.0))]


def test_scene_retrocompatibile_senza_sketch():
    scene = Scene()
    assert scene.sketch_2d_entities == []
    assert scene.sketch_2d_state == {}
    # scene.json vecchio (senza chiave sketch_2d) resta valido
    old_state = {"color_idx": 0, "active_layer": "Default",
                 "snap_grid": True, "magnetic_snap": True,
                 "scale_mode": "Disattivato"}
    sketch_2d = old_state.get("sketch_2d") or {}
    assert sketch_2d.get("entities", []) == []
    assert sketch_2d.get("state", {}) == {}


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
