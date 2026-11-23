# -*- coding: utf-8 -*-
"""Collaudo GUI reale dei 7 fix ereditati da PenguinCAD su TriviumCAD.

Avvia la vera `CADWindow`, mostra la finestra sul desktop e pilota i widget
con QTest / eventi Qt reali. Nessun offscreen, nessuna modifica al sorgente.

Copertura:
  T1 click sul cubo nascosto (0 selezioni) e sul visibile (1); box-select
     diretto che copre entrambi: seleziona solo il visibile.
  T2 console: `obj.apply_scale(0.5)` cambia il volume al frame successivo e
     le cache `_gl_*` sono assenti subito dopo l'exec.
  T3 overlay misura: due click a 10 mm, badge "10.00 mm", stato persistente,
     Esc azzera.
  T4 outliner: doppio click sull'etichetta, dialog pilotato, nome aggiornato.
  T5 scala ancorata a Z=0: due click sulla faccia superiore, dialog "20 mm"
     (fattore 2), Z min 0 e Z max 40.
  T6 pannello Proprietà: box, cilindro, deselezione, multi-selezione.
  T7 misura 3D su Z=30: due click sulla faccia superiore, distanza 10 mm e
     quota Z=30 nei punti salvati.

Uso:  python -B harness_fix_ereditati.py
"""
import json
import math
import os
import sys
import traceback
from pathlib import Path

PROJ = Path(__file__).resolve().parents[3]
EV = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJ))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ.pop("QT_QPA_PLATFORM", None)
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from PyQt5.QtCore import Qt, QPoint, QTimer  # noqa: E402
from PyQt5.QtGui import QSurfaceFormat  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel, QInputDialog  # noqa: E402

import triviumcad  # noqa: E402
from triviumcad import CADWindow  # noqa: E402

fmt = QSurfaceFormat()
fmt.setVersion(3, 3)
fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
QSurfaceFormat.setDefaultFormat(fmt)

app = QApplication.instance() or QApplication(sys.argv)
window = CADWindow()
window.resize(1280, 800)
window.show()
window.raise_()
window.activateWindow()
window.gl_widget.setFocus()
QTest.qWait(400)

esiti = {}


def rec(test, ok, **dati):
    esiti[test] = {"ok": bool(ok), **dati}
    print(("[PASS] " if ok else "[FAIL] ") + test + " " +
          json.dumps(dati, ensure_ascii=False))


def reset():
    window.scene.objects = []
    window.scene.selected_objects = []
    window.scene.measurement_mode = None
    window.scene.measurement_points = []
    window.scene.measurement_done = False
    window.scene._needs_spatial_rebuild = True
    window._refresh_outliner()
    window.update_ui()
    window.gl_widget._invalidate_all_vbos()
    window.gl_widget.update()
    QTest.qWait(150)


def box(w=20.0, h=20.0, d=20.0, x=0.0, z=0.0, nome=None):
    o = window.scene.add_shape(
        "box", {"larghezza": w, "altezza": h, "profondità": d}, name=nome)
    zmin = float(o.bounds[0][2])
    o.apply_translation([x, 0.0, z - zmin])
    window.scene._needs_spatial_rebuild = True
    window.gl_widget._invalidate_all_vbos()
    window.gl_widget.update()
    QTest.qWait(120)
    return o


def screen(p):
    s = window.gl_widget._world_to_screen(np.array(p, dtype=float))
    return None if s is None else QPoint(int(round(s[0])), int(round(s[1])))


def click(p):
    q = screen(p)
    if q is None:
        raise RuntimeError("punto non proiettabile: %s" % (p,))
    QTest.mouseClick(window.gl_widget, Qt.LeftButton, Qt.NoModifier, q)
    QTest.qWait(100)


def t1_picking_nascosti():
    reset()
    vis = box(x=-30.0, nome="visibile")
    hid = box(x=30.0, nome="nascosto")
    hid.metadata["visible"] = False
    window.gl_widget.update()
    QTest.qWait(120)

    window.scene.clear_selection()
    click(hid.centroid)
    ok_click_nascosto = hid not in window.scene.selected_objects

    click(vis.centroid)
    ok_click_visibile = vis in window.scene.selected_objects

    window.scene.clear_selection()
    punti = []
    for o in (vis, hid):
        for cx in (o.bounds[0][0], o.bounds[1][0]):
            for cy in (o.bounds[0][1], o.bounds[1][1]):
                for cz in (o.bounds[0][2], o.bounds[1][2]):
                    q = screen([cx, cy, cz])
                    if q is not None:
                        punti.append(q)
    left = min(p.x() for p in punti) - 8
    right = max(p.x() for p in punti) + 8
    top = min(p.y() for p in punti) - 8
    bottom = max(p.y() for p in punti) + 8
    window.gl_widget._select_objects_in_box(
        QPoint(left, top), QPoint(right, bottom))
    QTest.qWait(100)
    ok_box = (vis in window.scene.selected_objects and
              hid not in window.scene.selected_objects)

    rec("1_picking_nascosti",
        ok_click_nascosto and ok_click_visibile and ok_box,
        click_nascosto=ok_click_nascosto,
        click_visibile=ok_click_visibile,
        box_select=ok_box)


def t2_console_cache():
    reset()
    o = box(nome="console")
    window.scene.selected_objects = [o]
    window.update_ui()
    window._toggle_console(True)
    QTest.qWait(150)
    con = window.console_dialog
    if con is None:
        rec("2_console_cache", False, errore="console non aperta")
        return
    vol0 = float(o.volume)
    con.input.setText("obj.apply_scale(0.5)")
    con._execute()
    cache_subito = any(
        k in o.metadata
        for k in ("_gl_verts", "_gl_normals", "_gl_vbo_verts", "_gl_vbo_normals")
    )
    QTest.qWait(200)
    vol1 = float(o.volume)
    window._toggle_console(False)
    ok = abs(vol1 / vol0 - 0.125) < 1e-6 and not cache_subito
    rec("2_console_cache", ok, volume_prima=vol0, volume_dopo=vol1,
        cache_subito=cache_subito)


def t3_overlay_misura():
    reset()
    supporto = box(x=100.0, nome="supporto")
    window.scene.selected_objects = [supporto]
    window.scene.measure_distance()
    window.scene.clear_selection()
    click([0.0, 0.0, 0.0])
    click([10.0, 0.0, 0.0])
    pts = window.scene.measurement_points
    d = math.dist(pts[0], pts[1]) if len(pts) == 2 else -1.0
    testo = window.gl_widget._testo_misura("distance", pts)
    done = bool(window.scene.measurement_done)
    QTest.keyClick(window.gl_widget, Qt.Key_Escape)
    QTest.qWait(100)
    esc = (window.scene.measurement_mode is None and
           not window.scene.measurement_done)
    # Click a pixel interi: tolleranza 0.3 mm sull'accuratezza del badge.
    ok = (done and testo.endswith(" mm") and abs(d - 10.0) < 0.3 and esc)
    rec("3_overlay_misura", ok, testo=testo, distanza=d, done=done, esc=esc)


def t4_rinomina_outliner():
    reset()
    o = box(nome="da_rinominare")
    window._refresh_outliner()
    QTest.qWait(150)
    labels = window.outliner_list.findChildren(QLabel, "outliner_name")
    if not labels:
        rec("4_rinomina_outliner", False, errore="etichetta assente")
        return
    orig = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: ("Rinominato", True))
    try:
        QTest.mouseDClick(labels[0], Qt.LeftButton)
        QTest.qWait(200)
    finally:
        QInputDialog.getText = orig
    labels2 = window.outliner_list.findChildren(QLabel, "outliner_name")
    testo = labels2[0].text() if labels2 else ""
    ok = o.metadata.get("name") == "Rinominato" and testo == "Rinominato"
    rec("4_rinomina_outliner", ok, nome=o.metadata.get("name"),
        etichetta=testo)


def t5_scala_z0():
    reset()
    o = box(w=20.0, h=20.0, d=20.0, z=0.0, nome="scala")
    window.scene.selected_objects = [o]
    window.update_ui()
    window.scene.measure_distance()
    orig = QInputDialog.getDouble
    QInputDialog.getDouble = staticmethod(lambda *a, **k: (20.0, True))
    try:
        click([-5.0, 0.0, 20.0])
        click([5.0, 0.0, 20.0])
    finally:
        QInputDialog.getDouble = orig
    pts = window.scene.measurement_points
    d = math.dist(pts[0], pts[1]) if len(pts) == 2 else -1.0
    s = (20.0 / d) if d > 1e-9 else -1.0
    z = np.asarray(o.vertices, dtype=np.float64)[:, 2]
    ok = (s > 0 and abs(float(z.min())) < 1e-6 and
          abs(float(z.max()) - 20.0 * s) < 1e-3)
    rec("5_scala_z0", ok, zmin=float(z.min()), zmax=float(z.max()),
        volume=float(o.volume), distanza=d, fattore=s)


def t6_proprieta():
    reset()
    b = box(nome="cubo")
    c = window.scene.add_shape(
        "cylinder", {"raggio": 10.0, "altezza": 30.0, "sezioni": 64},
        name="cilindro")
    window.scene._needs_spatial_rebuild = True
    window.scene.selected_objects = [b]
    window.update_ui()
    l1, s1 = window.prop_layer.text(), window.prop_shape.text()
    window.scene.selected_objects = [c]
    window.update_ui()
    l2, s2 = window.prop_layer.text(), window.prop_shape.text()
    window.scene.clear_selection()
    window.update_ui()
    l3, s3 = window.prop_layer.text(), window.prop_shape.text()
    window.scene.selected_objects = [b, c]
    window.update_ui()
    l4, s4 = window.prop_layer.text(), window.prop_shape.text()
    ok = ((l1, s1) == ("Default", "box") and
          (l2, s2) == ("Default", "cylinder") and
          (l3, s3) == ("—", "—") and l4 == "Default" and s4 == "—")
    rec("6_proprieta", ok, box=[l1, s1], cilindro=[l2, s2],
        deselezione=[l3, s3], multi=[l4, s4])


def t7_misura_3d():
    reset()
    # Cubo esplicito 20 x 20 x 10 con base a Z=20 e faccia superiore a Z=30:
    # evita l'ambiguita' dei parametri "altezza/profondita" di add_shape.
    o = trimesh.creation.box(extents=(20.0, 20.0, 10.0))
    o.apply_translation([0.0, 0.0, 25.0])
    o.metadata.update({
        "layer": "Default", "color": [0.5, 0.5, 0.5, 1.0],
        "name": "misura3d", "shape_type": "box",
        "visible": True, "locked": False,
    })
    window.scene.objects.append(o)
    window.scene._needs_spatial_rebuild = True
    window.gl_widget._invalidate_all_vbos()
    window.gl_widget.update()
    QTest.qWait(150)
    window.scene.selected_objects = [o]
    window.scene.measure_distance()
    window.scene.clear_selection()
    click([-5.0, 0.0, 30.0])
    click([5.0, 0.0, 30.0])
    pts = window.scene.measurement_points
    d = math.dist(pts[0], pts[1]) if len(pts) == 2 else -1.0
    zs = [round(float(p[2]), 6) for p in pts]
    testo = window.gl_widget._testo_misura("distance", pts)
    # Click a pixel interi: tolleranza 0.3 mm su distanza e quota.
    ok = (window.scene.measurement_done and abs(d - 10.0) < 0.3 and
          all(abs(z - 30.0) < 0.3 for z in zs) and testo.endswith(" mm"))
    rec("7_misura_3d", ok, distanza=d, z=zs, testo=testo)


def main():
    QTimer.singleShot(60000, lambda: (window.close(), app.quit()))
    try:
        t1_picking_nascosti()
        t2_console_cache()
        t3_overlay_misura()
        t4_rinomina_outliner()
        t5_scala_z0()
        t6_proprieta()
        t7_misura_3d()
    except Exception:
        traceback.print_exc()
        esiti["_errore"] = traceback.format_exc()
    finally:
        try:
            window.close()
        except Exception:
            pass
        app.quit()

    path = EV / "esiti_fix_ereditati.json"
    path.write_text(json.dumps(esiti, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    test = [k for k in esiti if not k.startswith("_")]
    ok = sum(1 for k in test if esiti[k].get("ok"))
    print("\nESITO: %d/%d" % (ok, len(test)))
    return 0 if ok == len(test) and "_errore" not in esiti else 1


if __name__ == "__main__":
    sys.exit(main())
