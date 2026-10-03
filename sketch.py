# -*- coding: utf-8 -*-
"""TriviumCAD — 2PenAxE: sketch 2D multi-piano (modulo autonomo).

Implementa la finestra modale "2PenAxE" approvata dal laboratorio N47Lab:
due pannelli affiancati, ognuno con piano di lavoro libero (XY/XZ/YZ) e
vista 3D orbitabile a 360 gradi (rotazione, zoom, pan); strumenti di disegno
(linea, polilinea, rettangolo, cerchio, arco, selezione/sposta, gomma,
misure live); ancore di snap selezionabili con evidenziazione al cursore;
viste predefinite; undo/redo; WYSIWYG (quote e coordinate in mm reali).

Il modulo non dipende da triviumcad.py: espone funzioni pure (geometria,
snap, serializzazione) usate anche dal GLWidget della finestra principale
per disegnare le linee dello sketch in scena, e la classe SketchDialog usata
dal pulsante omonimo della toolbar.

Modello entità (dizionari JSON-safe, tutti i punti in mm sul piano):
    {"type": "line",     "plane": "XY", "p1": [u, v], "p2": [u, v]}
    {"type": "polyline", "plane": "XY", "points": [[u, v], ...]}
    {"type": "rect",     "plane": "XY", "p1": [u, v], "p2": [u, v]}
    {"type": "circle",   "plane": "XY", "center": [u, v], "radius": r}
    {"type": "arc",      "plane": "XY", "center": [u, v], "radius": r,
                         "a1": gradi, "a2": gradi}

Convenzione piani (standard CAD, coerente col mockup approvato):
    XY -> (u, v, 0)   [vista Alto]    XZ -> (u, 0, v)   [vista Fronte]
    YZ -> (0, u, v)   [vista Lato]
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QPointF, QRectF, QSize, pyqtSignal
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen,
    QPixmap, QPolygonF,
)
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
    QLabel, QPushButton, QShortcut, QSizePolicy, QVBoxLayout, QWidget,
)

from core.constants import (
    AMBER, AMBER_DARK, AMBER_DIM, AMBER_FAINT, AMBER_LIGHT,
    BG_CARD, BG_ELEV, BG_PAGE, BG_PANEL, BORDER_SOFT, BRASS,
    FONT_BODY, FONT_HEAD, FONT_MONO, GREEN_CRT, GREEN_DIM,
    TEXT_BODY, TEXT_MUTED, TEXT_ON_AMBER,
)

# Blu del precetto per l'asse Z e la bussola.
BLUE_AXIS = "#5ba3e6"
# Azzurro chiaro per le entità dei piani non attivi: ben contrastato sul
# fondo scuro e visibile in prospettiva in entrambi i pannelli (fix N47
# 2026-10-04, feature 2PenAxE).
BLUE_ENTITY = "#83CBFF"

PLANES = ("XY", "XZ", "YZ")

# Definizione ancore: (chiave, etichetta italiana, attiva di default).
# Default 4/7 come nel mockup approvato (Endpoint, Midpoint, Assi, Origine).
ANCHOR_DEFS: List[Tuple[str, str, bool]] = [
    ("endpoint", "Endpoint", True),
    ("midpoint", "Midpoint", True),
    ("centri", "Centri", False),
    ("intersezioni", "Intersezioni", False),
    ("assi", "Proiezioni assi", True),
    ("origine", "Origine", True),
    ("griglia", "Griglia", False),
]

TOOL_DEFS: List[Tuple[str, str, str]] = [
    ("line", "Linea", "Disegna una linea (2 clic)"),
    ("polyline", "Polilinea", "Disegna una polilinea (clic, doppio clic o Invio per terminare)"),
    ("rect", "Rettangolo", "Disegna un rettangolo (2 clic, angoli opposti)"),
    ("circle", "Cerchio", "Disegna un cerchio (centro + punto sul bordo)"),
    ("arc", "Arco", "Disegna un arco (centro, inizio, fine)"),
    ("select", "Selezione", "Seleziona e sposta un'entità (trascina)"),
    ("eraser", "Gomma", "Elimina un'entità con un clic"),
    ("measure", "Misure", "Misura distanza e angolo tra due punti"),
]

VIEW_DEFS: List[Tuple[str, str]] = [
    ("Alto", "Vista dall'alto (piano XY)"),
    ("Fronte", "Vista frontale (piano XZ)"),
    ("Lato", "Vista laterale (piano YZ)"),
    ("Isometrica", "Vista isometrica 3D"),
]

# Viste standard: (yaw attorno a Z, pitch attorno a X schermo), in gradi.
# Con questa convenzione schermo X = asse u, schermo Y = asse v del piano.
STANDARD_VIEWS: Dict[str, Tuple[float, float]] = {
    "Alto": (0.0, 0.0),
    "Fronte": (0.0, -90.0),
    "Lato": (-90.0, -90.0),
    "Isometrica": (-45.0, 30.0),
}

DEFAULT_VIEW_BY_PLANE = {"XY": "Alto", "XZ": "Fronte", "YZ": "Lato"}


# =============================================================================
# GEOMETRIA PURA (nessuna dipendenza Qt: testabile senza QApplication)
# =============================================================================

def plane_to_3d(plane: str, u: float, v: float) -> Tuple[float, float, float]:
    """Converte un punto 2D del piano nelle coordinate 3D mondo (mm)."""
    if plane == "XY":
        return (float(u), float(v), 0.0)
    if plane == "XZ":
        return (float(u), 0.0, float(v))
    if plane == "YZ":
        return (0.0, float(u), float(v))
    raise ValueError("piano sconosciuto: %r" % (plane,))


def _arc_points(cx: float, cy: float, r: float, a1: float, a2: float,
                n: Optional[int] = None) -> List[Tuple[float, float]]:
    """Punti campione dell'arco a1->a2 (gradi, sweep positivo, max 360)."""
    sweep = (a2 - a1) % 360.0
    if sweep <= 1e-9:
        sweep = 360.0
    if n is None:
        n = max(8, int(sweep / 6.0) + 1)
    pts = []
    for i in range(n + 1):
        a = math.radians(a1 + sweep * i / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _circle_points(cx: float, cy: float, r: float,
                   n: int = 64) -> List[Tuple[float, float]]:
    """Punti campione del cerchio chiuso (primo punto ripetuto in coda)."""
    pts = []
    for i in range(n + 1):
        a = 2.0 * math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def entity_segments_2d(entity: Dict[str, Any]):
    """Segmenti 2D dell'entità (per hit test, snap e intersezioni)."""
    t = entity.get("type")
    if t == "line":
        p1, p2 = entity["p1"], entity["p2"]
        return [((p1[0], p1[1]), (p2[0], p2[1]))]
    if t == "polyline":
        pts = entity.get("points", [])
        return [((a[0], a[1]), (b[0], b[1])) for a, b in zip(pts, pts[1:])]
    if t == "rect":
        (u1, v1), (u2, v2) = entity["p1"], entity["p2"]
        corners = [(u1, v1), (u2, v1), (u2, v2), (u1, v2)]
        return [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    if t == "circle":
        c = entity["center"]
        pts = _circle_points(c[0], c[1], entity["radius"])
        return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if t == "arc":
        c = entity["center"]
        pts = _arc_points(c[0], c[1], entity["radius"],
                          entity["a1"], entity["a2"])
        return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    return []


def entity_circle_2d(entity: Dict[str, Any]):
    """(centro, raggio, a1, a2) per cerchi/archi; None per le altre entità.

    Per il cerchio a1/a2 sono None (giro completo).
    """
    t = entity.get("type")
    if t == "circle":
        c = entity["center"]
        return ((float(c[0]), float(c[1])), float(entity["radius"]), None, None)
    if t == "arc":
        c = entity["center"]
        return ((float(c[0]), float(c[1])), float(entity["radius"]),
                float(entity["a1"]), float(entity["a2"]))
    return None


def entity_to_3d_paths(entity: Dict[str, Any]):
    """Percorsi 3D dell'entità (mm) per il rendering OpenGL e per il canvas."""
    plane = entity.get("plane", "XY")
    t = entity.get("type")

    def to3(p):
        return plane_to_3d(plane, p[0], p[1])

    if t == "line":
        return [[to3(entity["p1"]), to3(entity["p2"])]]
    if t == "polyline":
        pts = entity.get("points", [])
        return [[to3(p) for p in pts]] if len(pts) >= 2 else []
    if t == "rect":
        (u1, v1), (u2, v2) = entity["p1"], entity["p2"]
        corners = [(u1, v1), (u2, v1), (u2, v2), (u1, v2), (u1, v1)]
        return [[to3(p) for p in corners]]
    if t == "circle":
        c = entity["center"]
        return [[to3(p) for p in _circle_points(c[0], c[1], entity["radius"])]]
    if t == "arc":
        c = entity["center"]
        pts = _arc_points(c[0], c[1], entity["radius"], entity["a1"], entity["a2"])
        return [[to3(p) for p in pts]]
    return []


def entity_translate(entity: Dict[str, Any], du: float, dv: float) -> None:
    """Trasla l'entità di (du, dv) mm nel proprio piano (in place)."""
    t = entity.get("type")
    if t == "line":
        entity["p1"] = [entity["p1"][0] + du, entity["p1"][1] + dv]
        entity["p2"] = [entity["p2"][0] + du, entity["p2"][1] + dv]
    elif t == "polyline":
        entity["points"] = [[p[0] + du, p[1] + dv] for p in entity.get("points", [])]
    elif t == "rect":
        entity["p1"] = [entity["p1"][0] + du, entity["p1"][1] + dv]
        entity["p2"] = [entity["p2"][0] + du, entity["p2"][1] + dv]
    elif t in ("circle", "arc"):
        entity["center"] = [entity["center"][0] + du, entity["center"][1] + dv]


def _dist_point_seg(px: float, py: float, ax: float, ay: float,
                    bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _point_on_arc(cx: float, cy: float, a1: float, a2: float,
                  p: Tuple[float, float]) -> bool:
    ang = math.degrees(math.atan2(p[1] - cy, p[0] - cx))
    sweep = (a2 - a1) % 360.0
    if sweep <= 1e-9:
        sweep = 360.0
    rel = (ang - a1) % 360.0
    return rel <= sweep + 1e-6


def entity_hit_test(entity: Dict[str, Any], u: float, v: float, tol: float) -> bool:
    """True se il punto (u, v) è entro `tol` mm dall'entità."""
    circ = entity_circle_2d(entity)
    if circ is not None:
        (cx, cy), r, a1, a2 = circ
        d = math.hypot(u - cx, v - cy)
        if abs(d - r) > tol:
            return False
        if a1 is not None and not _point_on_arc(cx, cy, a1, a2, (u, v)):
            return False
        return True
    for (ax, ay), (bx, by) in entity_segments_2d(entity):
        if _dist_point_seg(u, v, ax, ay, bx, by) <= tol:
            return True
    return False


# --- INTERSEZIONI -----------------------------------------------------------

def _seg_seg_intersection(p1, p2, p3, p4):
    d1x, d1y = p2[0] - p1[0], p2[1] - p1[1]
    d2x, d2y = p4[0] - p3[0], p4[1] - p3[1]
    den = d1x * d2y - d1y * d2x
    if abs(den) < 1e-12:
        return None
    qx, qy = p3[0] - p1[0], p3[1] - p1[1]
    t = (qx * d2y - qy * d2x) / den
    s = (qx * d1y - qy * d1x) / den
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= s <= 1.0 + 1e-9:
        return (p1[0] + t * d1x, p1[1] + t * d1y)
    return None


def _seg_circle_intersections(p1, p2, c, r):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    fx, fy = p1[0] - c[0], p1[1] - c[1]
    a = dx * dx + dy * dy
    if a < 1e-12:
        return []
    b = 2.0 * (fx * dx + fy * dy)
    cc = fx * fx + fy * fy - r * r
    disc = b * b - 4.0 * a * cc
    if disc < 0.0:
        return []
    sq = math.sqrt(disc)
    out = []
    for t in ((-b - sq) / (2.0 * a), (-b + sq) / (2.0 * a)):
        if -1e-9 <= t <= 1.0 + 1e-9:
            out.append((p1[0] + t * dx, p1[1] + t * dy))
    return out


def _circle_circle_intersections(c1, r1, c2, r2):
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    d = math.hypot(dx, dy)
    if d < 1e-12 or d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h2 = r1 * r1 - a * a
    if h2 < 0.0:
        return []
    h = math.sqrt(max(0.0, h2))
    xm, ym = c1[0] + a * dx / d, c1[1] + a * dy / d
    rx, ry = -dy * (h / d), dx * (h / d)
    return [(xm + rx, ym + ry), (xm - rx, ym - ry)]


def intersection_points(entities: List[Dict[str, Any]], plane: str,
                        exclude: int = -1) -> List[Tuple[float, float]]:
    """Intersezioni tra le entità del piano (segmenti, cerchi, archi)."""
    prims: List[Tuple] = []
    for i, e in enumerate(entities):
        if i == exclude or e.get("plane") != plane:
            continue
        t = e.get("type")
        if t in ("line", "polyline", "rect"):
            for a, b in entity_segments_2d(e):
                prims.append(("seg", a, b))
        else:
            circ = entity_circle_2d(e)
            if circ is not None:
                (c, r, a1, a2) = circ
                prims.append(("circ", c, r, a1, a2))

    def valid(p, prim):
        if p is None:
            return False
        if prim[0] == "circ" and prim[3] is not None:
            return _point_on_arc(prim[1][0], prim[1][1], prim[3], prim[4], p)
        return True

    out: List[Tuple[float, float]] = []
    for i in range(len(prims)):
        for j in range(i + 1, len(prims)):
            pi, pj = prims[i], prims[j]
            pts: List = []
            if pi[0] == "seg" and pj[0] == "seg":
                pts = [_seg_seg_intersection(pi[1], pi[2], pj[1], pj[2])]
            elif pi[0] == "seg" and pj[0] == "circ":
                pts = _seg_circle_intersections(pi[1], pi[2], pj[1], pj[2])
            elif pi[0] == "circ" and pj[0] == "seg":
                pts = _seg_circle_intersections(pj[1], pj[2], pi[1], pi[2])
            else:
                pts = _circle_circle_intersections(pi[1], pi[2], pj[1], pj[2])
            for p in pts:
                if valid(p, pi) and valid(p, pj):
                    out.append((float(p[0]), float(p[1])))
    return out


# --- ANCORE E SNAP ----------------------------------------------------------

def entity_anchor_points(entities: List[Dict[str, Any]], plane: str,
                         exclude: int = -1) -> List[Tuple[float, float, str]]:
    """Ancore geometriche (endpoint, midpoint, centri) delle entità del piano."""
    out: List[Tuple[float, float, str]] = []
    for i, e in enumerate(entities):
        if i == exclude or e.get("plane") != plane:
            continue
        t = e.get("type")
        if t == "line":
            out.append((e["p1"][0], e["p1"][1], "Endpoint"))
            out.append((e["p2"][0], e["p2"][1], "Endpoint"))
            out.append(((e["p1"][0] + e["p2"][0]) / 2.0,
                        (e["p1"][1] + e["p2"][1]) / 2.0, "Midpoint"))
        elif t == "polyline":
            pts = e.get("points", [])
            if pts:
                out.append((pts[0][0], pts[0][1], "Endpoint"))
                out.append((pts[-1][0], pts[-1][1], "Endpoint"))
            for a, b in zip(pts, pts[1:]):
                out.append(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, "Midpoint"))
        elif t == "rect":
            (u1, v1), (u2, v2) = e["p1"], e["p2"]
            corners = [(u1, v1), (u2, v1), (u2, v2), (u1, v2)]
            for c in corners:
                out.append((c[0], c[1], "Endpoint"))
            for a, b in zip(corners, corners[1:] + corners[:1]):
                out.append(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, "Midpoint"))
        elif t == "circle":
            c = e["center"]
            out.append((c[0], c[1], "Centro"))
        elif t == "arc":
            c = e["center"]
            out.append((c[0], c[1], "Centro"))
            r, a1, a2 = e["radius"], e["a1"], e["a2"]
            for a in (a1, a2):
                ar = math.radians(a)
                out.append((c[0] + r * math.cos(ar), c[1] + r * math.sin(ar),
                            "Endpoint"))
            sweep = (a2 - a1) % 360.0
            if sweep <= 1e-9:
                sweep = 360.0
            am = math.radians(a1 + sweep / 2.0)
            out.append((c[0] + r * math.cos(am), c[1] + r * math.sin(am),
                        "Midpoint"))
    return out


def snap_candidates(entities: List[Dict[str, Any]], plane: str,
                    anchors: Dict[str, bool],
                    cursor_uv: Optional[Tuple[float, float]] = None,
                    grid_mm: float = 10.0,
                    exclude: int = -1) -> List[Tuple[float, float, str]]:
    """Candidati di snap attivi per il piano e il cursore correnti."""
    out: List[Tuple[float, float, str]] = []
    if anchors.get("endpoint") or anchors.get("midpoint") or anchors.get("centri"):
        for u, v, tipo in entity_anchor_points(entities, plane, exclude):
            if tipo == "Endpoint" and not anchors.get("endpoint"):
                continue
            if tipo == "Midpoint" and not anchors.get("midpoint"):
                continue
            if tipo == "Centro" and not anchors.get("centri"):
                continue
            out.append((u, v, tipo))
    if anchors.get("intersezioni"):
        for u, v in intersection_points(entities, plane, exclude):
            out.append((u, v, "Intersezione"))
    if anchors.get("origine"):
        out.append((0.0, 0.0, "Origine"))
    if cursor_uv is not None:
        cu, cv = cursor_uv
        if anchors.get("assi"):
            out.append((cu, 0.0, "Assi"))
            out.append((0.0, cv, "Assi"))
        if anchors.get("griglia") and grid_mm and grid_mm > 0.0:
            gu = round(cu / grid_mm) * grid_mm
            gv = round(cv / grid_mm) * grid_mm
            out.append((gu, gv, "Griglia"))
    return out


def find_snap(entities: List[Dict[str, Any]], plane: str,
              anchors: Dict[str, bool], cursor_uv: Optional[Tuple[float, float]],
              grid_mm: float, scale_px_per_mm: float, tol_px: float = 12.0,
              exclude: int = -1):
    """Miglior ancora di snap per il cursore.

    Priorità (standard CAD): ancore geometriche (endpoint, midpoint, centri,
    intersezioni, origine) e proiezioni assi entro la tolleranza in pixel;
    se nessuna, la griglia aggancia sempre (quando attiva).
    Ritorna (u, v, tipo, dist_px) oppure None.
    """
    if cursor_uv is None or scale_px_per_mm <= 0.0:
        return None
    cu, cv = cursor_uv
    cands = snap_candidates(entities, plane, anchors, cursor_uv, grid_mm, exclude)
    best = None
    best_d = tol_px
    for u, v, tipo in cands:
        if tipo == "Griglia":
            continue
        d = math.hypot(u - cu, v - cv) * scale_px_per_mm
        if d <= best_d:
            best_d = d
            best = (u, v, tipo, d)
    if best is not None:
        return best
    if anchors.get("griglia") and grid_mm and grid_mm > 0.0:
        gu = round(cu / grid_mm) * grid_mm
        gv = round(cv / grid_mm) * grid_mm
        return (gu, gv, "Griglia", math.hypot(gu - cu, gv - cv) * scale_px_per_mm)
    return None


# =============================================================================
# ICONE (QPainter, stile a linee del mockup)
# =============================================================================

def _tool_icon(kind: str, size: int = 24, color: str = TEXT_BODY) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = float(size)
    if kind == "line":
        p.drawLine(QPointF(4, s - 5), QPointF(s - 5, 4))
    elif kind == "polyline":
        pts = [QPointF(3, s - 6), QPointF(s * 0.38, 5), QPointF(s - 7, s * 0.6),
               QPointF(s - 4, 5)]
        p.drawPolyline(QPolygonF(pts))
    elif kind == "rect":
        p.drawRect(QRectF(4, 6, s - 9, s - 13))
    elif kind == "circle":
        p.drawEllipse(QPointF(s / 2, s / 2), s * 0.33, s * 0.33)
    elif kind == "arc":
        p.drawArc(QRectF(4, 5, s - 9, s - 9), 30 * 16, 230 * 16)
    elif kind == "select":
        path = QPainterPath()
        path.moveTo(6, 3)
        path.lineTo(6, s - 6)
        path.lineTo(10, s - 10)
        path.lineTo(13, s - 4)
        path.lineTo(16, s - 6)
        path.lineTo(12, s - 12)
        path.lineTo(s - 4, s - 13)
        path.closeSubpath()
        p.setBrush(QColor(color))
        p.drawPath(path)
    elif kind == "eraser":
        path = QPainterPath()
        path.moveTo(5, s - 8)
        path.lineTo(s - 9, 5)
        path.lineTo(s - 4, 10)
        path.lineTo(10, s - 3)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(3, s - 3), QPointF(s - 3, s - 3))
    elif kind == "measure":
        p.drawRect(QRectF(3, s * 0.36, s - 7, s * 0.34))
        for i in range(1, 4):
            x = 3 + i * (s - 7) / 4.0
            p.drawLine(QPointF(x, s * 0.36), QPointF(x, s * 0.52))
    elif kind == "rotate":
        p.drawArc(QRectF(4, 4, s - 8, s - 8), 20 * 16, 300 * 16)
        path = QPainterPath()
        path.moveTo(s - 4, 4)
        path.lineTo(s - 4, s * 0.42)
        path.lineTo(s * 0.58, 4)
        path.closeSubpath()
        p.setBrush(QColor(color))
        p.drawPath(path)
    elif kind == "zoom":
        p.drawEllipse(QPointF(s * 0.44, s * 0.44), s * 0.26, s * 0.26)
        p.drawLine(QPointF(s * 0.63, s * 0.63), QPointF(s - 4, s - 4))
        p.drawLine(QPointF(s * 0.33, s * 0.44), QPointF(s * 0.55, s * 0.44))
        p.drawLine(QPointF(s * 0.44, s * 0.33), QPointF(s * 0.44, s * 0.55))
    elif kind == "pan":
        p.drawLine(QPointF(s / 2, 4), QPointF(s / 2, s - 4))
        p.drawLine(QPointF(4, s / 2), QPointF(s - 4, s / 2))
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            tipx, tipy = s / 2 + dx * (s / 2 - 4), s / 2 + dy * (s / 2 - 4)
            bx, by = s / 2 + dx * (s / 2 - 9), s / 2 + dy * (s / 2 - 9)
            p.drawLine(QPointF(bx - dy * 3, by - dx * 3), QPointF(tipx, tipy))
            p.drawLine(QPointF(bx + dy * 3, by + dx * 3), QPointF(tipx, tipy))
    elif kind == "undo":
        p.drawArc(QRectF(4, 5, s - 8, s - 9), 30 * 16, 200 * 16)
        path = QPainterPath()
        path.moveTo(4, 6)
        path.lineTo(4, s * 0.48)
        path.lineTo(s * 0.46, 6)
        path.closeSubpath()
        p.setBrush(QColor(color))
        p.drawPath(path)
    elif kind == "redo":
        p.drawArc(QRectF(4, 5, s - 8, s - 9), -50 * 16, 200 * 16)
        path = QPainterPath()
        path.moveTo(s - 4, 6)
        path.lineTo(s - 4, s * 0.48)
        path.lineTo(s * 0.54, 6)
        path.closeSubpath()
        p.setBrush(QColor(color))
        p.drawPath(path)
    p.end()
    return QIcon(pm)


def _load_app_icon(size: int = 48) -> QIcon:
    """Icona 2PenAxE approvata (Immagini/2penaxe_64.png), fallback a glifo."""
    try:
        from pathlib import Path
        path = Path(__file__).resolve().parent / "Immagini" / "2penaxe_64.png"
        if path.exists():
            pm = QPixmap(str(path))
            if not pm.isNull():
                return QIcon(pm.scaled(size, size, Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))
    except Exception as e:
        print("[2PenAxE] icona non caricata: %s" % e)
    return _tool_icon("measure", size)


# =============================================================================
# CANVAS (vista orbitabile QPainter + strumenti + snap)
# =============================================================================

class SketchCanvas(QWidget):
    """Vista 3D orbitabile di un piano di lavoro con disegno 2D in mm reali."""

    changed = pyqtSignal()            # entità modificate (live update scena)
    about_to_edit = pyqtSignal()      # modifica in arrivo (snapshot undo)
    status_changed = pyqtSignal(str)  # testo status (coordinate/snap)

    def __init__(self, parent=None, plane: str = "XY"):
        super().__init__(parent)
        self.setMinimumSize(320, 260)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)

        self.plane = plane if plane in PLANES else "XY"
        self.grid_mm = 10.0
        self.entities: List[Dict[str, Any]] = []
        self.anchors: Dict[str, bool] = {k: d for k, _, d in ANCHOR_DEFS}

        self.tool = "line"
        self.draft: List[Tuple[float, float]] = []
        self.selected_index = -1
        self._measure: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None

        # Camera ortografica: yaw/pitch in gradi, scale in px/mm, pan in px.
        self.yaw = 0.0
        self.pitch = 0.0
        self.scale = 4.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.view_name = "Alto"

        self._view_mode: Optional[str] = None
        self._drag_mode: Optional[str] = None
        self._drag_last = None
        self._move_start = None
        self._move_orig = None
        self._move_dirty = False
        self._cursor_uv: Optional[Tuple[float, float]] = None
        self._snap = None
        self.set_plane(self.plane)

    # --- CONTESTO -----------------------------------------------------------
    def set_context(self, entities: List[Dict[str, Any]],
                    anchors: Dict[str, bool], grid_mm: float) -> None:
        self.entities = entities
        self.anchors = anchors
        self.grid_mm = grid_mm
        self.update()

    def set_plane(self, plane: str) -> None:
        if plane not in PLANES:
            return
        self.plane = plane
        self.draft = []
        self.selected_index = -1
        self._measure = None
        self.set_standard_view(DEFAULT_VIEW_BY_PLANE[plane], apply_only=True)
        self.update()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.draft = []
        self.selected_index = -1
        self._measure = None
        cursors = {"select": Qt.ArrowCursor, "eraser": Qt.CrossCursor}
        self.setCursor(cursors.get(tool, Qt.CrossCursor))
        self.update()

    def set_view_mode(self, mode: Optional[str]) -> None:
        self._view_mode = mode
        if mode:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor if self.tool == "select" else Qt.CrossCursor)

    # --- CAMERA -------------------------------------------------------------
    def _rot(self, p):
        """Rotazione camera (yaw su Z, poi pitch su X schermo)."""
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        x, y = cy * x - sy * y, sy * x + cy * y
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        y, z = cp * y - sp * z, sp * y + cp * z
        return x, y, z

    def project(self, p3) -> QPointF:
        """Proiezione ortografica 3D -> 2D schermo (px)."""
        x, y, _ = self._rot(p3)
        return QPointF(self.width() / 2.0 + x * self.scale + self.pan_x,
                       self.height() / 2.0 - y * self.scale + self.pan_y)

    def _plane_matrix(self):
        """Origine e matrice 2x2 della proiezione del piano attivo (per unproject)."""
        o = self.project(plane_to_3d(self.plane, 0.0, 0.0))
        pu = self.project(plane_to_3d(self.plane, 1.0, 0.0))
        pv = self.project(plane_to_3d(self.plane, 0.0, 1.0))
        a00, a10 = pu.x() - o.x(), pu.y() - o.y()
        a01, a11 = pv.x() - o.x(), pv.y() - o.y()
        return o, a00, a01, a10, a11

    def unproject(self, sx: float, sy: float) -> Optional[Tuple[float, float]]:
        """Punto (u, v) sul piano attivo dal pixel schermo; None se vista di taglio."""
        o, a00, a01, a10, a11 = self._plane_matrix()
        det = a00 * a11 - a01 * a10
        if abs(det) < 1e-3:
            return None
        dx, dy = sx - o.x(), sy - o.y()
        u = (a11 * dx - a01 * dy) / det
        v = (-a10 * dx + a00 * dy) / det
        return (u, v)

    def set_standard_view(self, name: str, apply_only: bool = False) -> None:
        if name not in STANDARD_VIEWS:
            return
        yaw, pitch = STANDARD_VIEWS[name]
        self.yaw, self.pitch = yaw, pitch
        self.pan_x = self.pan_y = 0.0
        self.view_name = name
        if not apply_only:
            self.update()

    # --- SNAP ---------------------------------------------------------------
    def _snap_point(self, uv: Optional[Tuple[float, float]]):
        """(u, v, tipo) agganciati; None se vista di taglio."""
        if uv is None:
            return None
        snap = find_snap(self.entities, self.plane, self.anchors, uv,
                         self.grid_mm, self.scale)
        if snap is not None:
            return (snap[0], snap[1], snap[2])
        return (uv[0], uv[1], None)

    def _cursor_mm(self, pos):
        return self.unproject(pos.x(), pos.y())

    def _emit_status(self):
        if self._cursor_uv is None:
            self.status_changed.emit("Vista di taglio — ruota la vista per disegnare")
            return
        u, v = self._cursor_uv
        x, y, z = plane_to_3d(self.plane, u, v)
        snap_txt = ""
        if self._snap is not None and self._snap[2]:
            snap_txt = "  ·  Snap: %s" % self._snap[2]
        self.status_changed.emit(
            "X: %.2f   Y: %.2f   Z: %.2f%s" % (x, y, z, snap_txt))

    # --- PAINT --------------------------------------------------------------
    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            p.fillRect(self.rect(), QColor(BG_PAGE))
            self._draw_grid(p)
            self._draw_axes(p)
            self._draw_entities(p)
            self._draw_draft(p)
            self._draw_measure(p)
            self._draw_snap_marker(p)
            self._draw_compass(p)
            p.end()
        except Exception as e:
            print("[2PenAxE] Errore paint canvas: %s" % e)

    def _visible_bounds(self):
        corners = [self.unproject(0, 0), self.unproject(self.width(), 0),
                   self.unproject(0, self.height()),
                   self.unproject(self.width(), self.height())]
        pts = [c for c in corners if c is not None]
        if len(pts) < 4:
            return None
        us = [p[0] for p in pts]
        vs = [p[1] for p in pts]
        return min(us), max(us), min(vs), max(vs)

    def _draw_grid(self, p: QPainter):
        b = self._visible_bounds()
        if b is None:
            return
        u0, u1, v0, v1 = b
        step = self.grid_mm if self.grid_mm and self.grid_mm > 0 else 10.0
        guard = 0
        while step * self.scale < 6.0 and guard < 8:
            step *= 5.0
            guard += 1
        if step <= 0 or (u1 - u0) / step > 500 or (v1 - v0) / step > 500:
            return
        p.setPen(QPen(QColor(120, 160, 220, 40), 1))
        u = math.floor(u0 / step) * step
        while u <= u1:
            p.drawLine(self.project(plane_to_3d(self.plane, u, v0)),
                       self.project(plane_to_3d(self.plane, u, v1)))
            u += step
        v = math.floor(v0 / step) * step
        while v <= v1:
            p.drawLine(self.project(plane_to_3d(self.plane, u0, v)),
                       self.project(plane_to_3d(self.plane, u1, v)))
            v += step

    def _axis_colors(self):
        """Colori degli assi u/v del piano (X ambra, Y verde, Z blu)."""
        if self.plane == "XY":
            return QColor(AMBER), QColor(GREEN_CRT)
        if self.plane == "XZ":
            return QColor(AMBER), QColor(BLUE_AXIS)
        return QColor(GREEN_CRT), QColor(BLUE_AXIS)

    def _draw_axes(self, p: QPainter):
        b = self._visible_bounds()
        if b is None:
            u0, u1, v0, v1 = -100.0, 100.0, -100.0, 100.0
        else:
            u0, u1, v0, v1 = b
        eu = max(abs(u0), abs(u1)) * 1.15 + 10.0
        ev = max(abs(v0), abs(v1)) * 1.15 + 10.0
        cu, cv = self._axis_colors()
        p.setPen(QPen(cu, 1.6))
        p.drawLine(self.project(plane_to_3d(self.plane, -eu, 0.0)),
                   self.project(plane_to_3d(self.plane, eu, 0.0)))
        p.setPen(QPen(cv, 1.6))
        p.drawLine(self.project(plane_to_3d(self.plane, 0.0, -ev)),
                   self.project(plane_to_3d(self.plane, 0.0, ev)))
        # Etichette degli assi mondo alle estremità positive.
        labels = {"XY": ("X", "Y"), "XZ": ("X", "Z"), "YZ": ("Y", "Z")}
        lu, lv = labels[self.plane]
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.setPen(QPen(cu, 1))
        pu = self.project(plane_to_3d(self.plane, eu, 0.0))
        p.drawText(QRectF(pu.x() + 3, pu.y() - 8, 18, 16), Qt.AlignLeft, lu)
        p.setPen(QPen(cv, 1))
        pv = self.project(plane_to_3d(self.plane, 0.0, ev))
        p.drawText(QRectF(pv.x() + 3, pv.y() - 8, 18, 16), Qt.AlignLeft, lv)

    def _draw_entities(self, p: QPainter):
        for i, e in enumerate(self.entities):
            on_plane = e.get("plane") == self.plane
            if i == self.selected_index:
                pen = QPen(QColor(GREEN_CRT), 2.4)
            elif on_plane:
                pen = QPen(QColor(TEXT_BODY), 2.0)
            else:
                other = QColor(BLUE_ENTITY)
                other.setAlpha(230)
                pen = QPen(other, 1.8)
            p.setPen(pen)
            for path in entity_to_3d_paths(e):
                p.drawPolyline(QPolygonF([self.project(pt) for pt in path]))

    def _draw_draft(self, p: QPainter):
        if not self.draft:
            return
        sp = self._snap_point(self._cursor_uv)
        if sp is None:
            return
        u, v, _ = sp
        pen = QPen(QColor(AMBER), 2.0)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p1 = self.draft[0]
        if self.tool == "line" and len(self.draft) == 1:
            p.drawLine(self.project(plane_to_3d(self.plane, *p1)),
                       self.project(plane_to_3d(self.plane, u, v)))
            self._pill(p, self.project(plane_to_3d(self.plane, (p1[0] + u) / 2,
                                                   (p1[1] + v) / 2)),
                       "%.2f mm" % math.hypot(u - p1[0], v - p1[1]))
        elif self.tool == "polyline":
            pts = list(self.draft) + [(u, v)]
            p.drawPolyline(QPolygonF(
                [self.project(plane_to_3d(self.plane, *q)) for q in pts]))
            seg = math.hypot(u - self.draft[-1][0], v - self.draft[-1][1])
            tot = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                      for i in range(len(pts) - 1))
            self._pill(p, self.project(plane_to_3d(self.plane, (self.draft[-1][0] + u) / 2,
                                                   (self.draft[-1][1] + v) / 2)),
                       "%.2f mm  (tot %.2f)" % (seg, tot))
        elif self.tool == "rect" and len(self.draft) == 1:
            (u1, v1) = p1
            corners = [(u1, v1), (u, v1), (u, v), (u1, v)]
            p.drawPolygon(QPolygonF(
                [self.project(plane_to_3d(self.plane, *q)) for q in corners]))
            self._pill(p, self.project(plane_to_3d(self.plane, (u1 + u) / 2, (v1 + v) / 2)),
                       "%.2f × %.2f mm" % (abs(u - u1), abs(v - v1)))
        elif self.tool == "circle" and len(self.draft) == 1:
            r = math.hypot(u - p1[0], v - p1[1])
            p.drawEllipse(self.project(plane_to_3d(self.plane, *p1)),
                          r * self.scale, r * self.scale)
            self._pill(p, self.project(plane_to_3d(self.plane, p1[0], p1[1] + r)),
                       "R %.2f mm" % r)
        elif self.tool == "arc" and len(self.draft) == 1:
            r = math.hypot(u - p1[0], v - p1[1])
            a1 = math.degrees(math.atan2(v - p1[1], u - p1[0]))
            p.drawLine(self.project(plane_to_3d(self.plane, *p1)),
                       self.project(plane_to_3d(self.plane, u, v)))
            self._pill(p, self.project(plane_to_3d(self.plane, (p1[0] + u) / 2,
                                                   (p1[1] + v) / 2)),
                       "R %.2f mm · %.1f°" % (r, (a1 + 360.0) % 360.0))
        elif self.tool == "arc" and len(self.draft) == 2:
            c = self.draft[0]
            s = self.draft[1]
            r = math.hypot(s[0] - c[0], s[1] - c[1])
            a1 = math.degrees(math.atan2(s[1] - c[1], s[0] - c[0]))
            a2 = math.degrees(math.atan2(v - c[1], u - c[0]))
            pts = _arc_points(c[0], c[1], r, a1, a2)
            p.drawPolyline(QPolygonF(
                [self.project(plane_to_3d(self.plane, *q)) for q in pts]))
            sweep = (a2 - a1) % 360.0
            self._pill(p, self.project(plane_to_3d(self.plane, *c)),
                       "R %.2f mm · %.1f°" % (r, sweep))
        elif self.tool == "measure":
            p.drawLine(self.project(plane_to_3d(self.plane, *p1)),
                       self.project(plane_to_3d(self.plane, u, v)))
            self._pill(p, self.project(plane_to_3d(self.plane, (p1[0] + u) / 2,
                                                   (p1[1] + v) / 2)),
                       "%.2f mm · %.1f°" % (
                           math.hypot(u - p1[0], v - p1[1]),
                           math.degrees(math.atan2(v - p1[1], u - p1[0]))))

    def _draw_measure(self, p: QPainter):
        """Misura pinnata (strumento Misure): linea tratteggiata + quota."""
        if self._measure is None:
            return
        (u1, v1), (u2, v2) = self._measure
        pen = QPen(QColor(AMBER_LIGHT), 1.6)
        pen.setStyle(Qt.DashDotLine)
        p.setPen(pen)
        p.drawLine(self.project(plane_to_3d(self.plane, u1, v1)),
                   self.project(plane_to_3d(self.plane, u2, v2)))
        dist = math.hypot(u2 - u1, v2 - v1)
        ang = math.degrees(math.atan2(v2 - v1, u2 - u1))
        self._pill(p, self.project(plane_to_3d(self.plane, (u1 + u2) / 2,
                                               (v1 + v2) / 2)),
                   "%.2f mm · %.1f°" % (dist, ang))

    def _draw_snap_marker(self, p: QPainter):
        if self._snap is None or not self._snap[2]:
            return
        u, v, tipo = self._snap
        pt = self.project(plane_to_3d(self.plane, u, v))
        p.setPen(QPen(QColor(AMBER_DARK), 1.4))
        p.setBrush(QColor(AMBER))
        p.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))
        if tipo != "Griglia":
            p.setFont(QFont("Segoe UI", 7))
            p.setPen(QPen(QColor(AMBER_LIGHT), 1))
            p.drawText(QRectF(pt.x() + 7, pt.y() - 16, 90, 14), Qt.AlignLeft, tipo)

    def _draw_compass(self, p: QPainter):
        ox, oy = self.width() - 56.0, self.height() - 56.0
        scale = 22.0
        axes = [("X", (1.0, 0.0, 0.0), QColor(AMBER)),
                ("Y", (0.0, 1.0, 0.0), QColor(GREEN_CRT)),
                ("Z", (0.0, 0.0, 1.0), QColor(BLUE_AXIS))]
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        for name, vec, color in axes:
            x, y, _ = self._rot(vec)
            ex, ey = ox + x * scale, oy - y * scale
            p.setPen(QPen(color, 1.6))
            p.drawLine(QPointF(ox, oy), QPointF(ex, ey))
            p.drawText(QRectF(ex + 2, ey - 7, 14, 14), Qt.AlignLeft, name)
        p.setPen(QPen(QColor(TEXT_MUTED), 1))
        p.setBrush(QColor(BG_PANEL))
        p.drawEllipse(QPointF(ox, oy), 2.5, 2.5)

    def _pill(self, p: QPainter, pt: QPointF, text: str):
        """Pillola scura con testo mono (quote live), stile CAD del mockup."""
        f = QFont("Consolas", 8)
        p.setFont(f)
        fm = QFontMetrics(f)
        w = fm.width(text) + 14
        h = fm.height() + 6
        rect = QRectF(pt.x() - w / 2, pt.y() - h - 10, w, h)
        p.setPen(QPen(QColor(AMBER_DARK), 1))
        p.setBrush(QColor(16, 36, 63, 235))
        p.drawRoundedRect(rect, 6, 6)
        p.setPen(QPen(QColor(TEXT_BODY), 1))
        p.drawText(rect, Qt.AlignCenter, text)

    # --- EVENTI WIDGET ------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        ctl = getattr(self, "_view_ctl", None)
        if ctl is not None:
            ctl.move(max(8, self.width() - ctl.width() - 10), 10)

    # --- MOUSE --------------------------------------------------------------
    def mousePressEvent(self, event):
        self.setFocus()
        pos = event.pos()
        uv = self._cursor_mm(pos)
        self._cursor_uv = uv
        if event.button() == Qt.MiddleButton:
            self._drag_mode = "pan"
            self._drag_last = pos
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.RightButton:
            self._drag_mode = "rotate"
            self._drag_last = pos
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() != Qt.LeftButton:
            return
        if self._view_mode:
            self._drag_mode = self._view_mode
            self._drag_last = pos
            self.setCursor(Qt.ClosedHandCursor)
            return
        sp = self._snap_point(uv)
        if sp is None:
            self.status_changed.emit("Vista di taglio — ruota la vista per disegnare")
            return
        u, v, _ = sp
        if self.tool in ("line", "rect", "circle", "measure"):
            if not self.draft:
                self.draft = [(u, v)]
            else:
                self._finalize_2pt((u, v))
        elif self.tool == "polyline":
            if not self.draft or math.hypot(u - self.draft[-1][0],
                                            v - self.draft[-1][1]) > 1e-6:
                self.draft.append((u, v))
        elif self.tool == "arc":
            if not self.draft:
                self.draft = [(u, v)]
            elif len(self.draft) == 1:
                if math.hypot(u - self.draft[0][0], v - self.draft[0][1]) > 1e-6:
                    self.draft.append((u, v))
            else:
                self._finalize_arc((u, v))
        elif self.tool == "select":
            self._select_at(u, v)
            if self.selected_index >= 0:
                self._move_start = (u, v)
                self._move_orig = self.entities[self.selected_index].copy()
                self._move_dirty = False
        elif self.tool == "eraser":
            idx = self._hit_entity(u, v)
            if idx >= 0:
                self.about_to_edit.emit()
                del self.entities[idx]
                self.selected_index = -1
                self.changed.emit()
        self.update()
        self._emit_status()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        uv = self._cursor_mm(pos)
        self._cursor_uv = uv
        self._snap = self._snap_point(uv) if uv is not None else None
        if self._drag_mode == "pan" and self._drag_last is not None:
            d = pos - self._drag_last
            self.pan_x += d.x()
            self.pan_y += d.y()
            self._drag_last = pos
            self.update()
        elif self._drag_mode == "rotate" and self._drag_last is not None:
            d = pos - self._drag_last
            self.yaw += d.x() * 0.5
            self.pitch = max(-90.0, min(90.0, self.pitch - d.y() * 0.5))
            self.view_name = ""
            self._drag_last = pos
            self.update()
        elif self._drag_mode == "zoom" and self._drag_last is not None:
            dy = pos.y() - self._drag_last.y()
            self._zoom_at(pos, math.exp(-dy * 0.01))
            self._drag_last = pos
        elif self._move_start is not None and self.selected_index >= 0:
            if uv is not None:
                du = uv[0] - self._move_start[0]
                dv = uv[1] - self._move_start[1]
                if abs(du) > 1e-9 or abs(dv) > 1e-9:
                    if not self._move_dirty:
                        self.about_to_edit.emit()
                        self._move_dirty = True
                    e = self.entities[self.selected_index]
                    e.clear()
                    e.update(self._move_orig)
                    entity_translate(e, du, dv)
                    self.changed.emit()
                self.update()
        else:
            self.update()
        self._emit_status()

    def mouseReleaseEvent(self, event):
        if self._drag_mode in ("pan", "rotate", "zoom"):
            self._drag_mode = None
            self.set_view_mode(self._view_mode)
            self.update()
        elif event.button() == Qt.LeftButton:
            self._move_start = None
            self._move_orig = None
            self._move_dirty = False

    def mouseDoubleClickEvent(self, event):
        if self.tool == "polyline" and event.button() == Qt.LeftButton:
            if len(self.draft) >= 2:
                self.about_to_edit.emit()
                self.entities.append({"type": "polyline", "plane": self.plane,
                                      "points": [[p[0], p[1]] for p in self.draft]})
                self.draft = []
                self.changed.emit()
                self.update()

    def wheelEvent(self, event):
        factor = 1.1 if event.angleDelta().y() > 0 else 1.0 / 1.1
        self._zoom_at(event.pos(), factor)

    def _zoom_at(self, pos, factor):
        before = self.unproject(pos.x(), pos.y())
        new_scale = max(0.05, min(400.0, self.scale * factor))
        if abs(new_scale - self.scale) < 1e-12:
            return
        self.scale = new_scale
        if before is not None:
            after = self.project(plane_to_3d(self.plane, before[0], before[1]))
            self.pan_x += pos.x() - after.x()
            self.pan_y += pos.y() - after.y()
        self.update()

    # --- TASTIERA -----------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.draft = []
            self.selected_index = -1
            self._measure = None
            self.update()
        elif event.key() == Qt.Key_Delete and self.selected_index >= 0:
            self.about_to_edit.emit()
            del self.entities[self.selected_index]
            self.selected_index = -1
            self.changed.emit()
            self.update()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.tool == "polyline":
            if len(self.draft) >= 2:
                self.about_to_edit.emit()
                self.entities.append({"type": "polyline", "plane": self.plane,
                                      "points": [[p[0], p[1]] for p in self.draft]})
                self.draft = []
                self.changed.emit()
                self.update()
        else:
            super().keyPressEvent(event)

    # --- FINALIZZAZIONE ENTITÀ ----------------------------------------------
    def _hit_entity(self, u: float, v: float) -> int:
        tol = 6.0 / max(self.scale, 1e-6)
        for i in range(len(self.entities) - 1, -1, -1):
            e = self.entities[i]
            if e.get("plane") == self.plane and entity_hit_test(e, u, v, tol):
                return i
        return -1

    def _select_at(self, u: float, v: float):
        self.selected_index = self._hit_entity(u, v)

    def _finalize_2pt(self, p2):
        p1 = self.draft[0]
        if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 1e-9:
            return
        self.about_to_edit.emit()
        if self.tool == "line":
            ent = {"type": "line", "plane": self.plane,
                   "p1": [p1[0], p1[1]], "p2": [p2[0], p2[1]]}
        elif self.tool == "rect":
            ent = {"type": "rect", "plane": self.plane,
                   "p1": [p1[0], p1[1]], "p2": [p2[0], p2[1]]}
        elif self.tool == "circle":
            r = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            ent = {"type": "circle", "plane": self.plane,
                   "center": [p1[0], p1[1]], "radius": r}
        else:  # measure: non è un'entità, resta visualizzata
            self._measure = (p1, p2)
            self.draft = []
            self.update()
            return
        self.entities.append(ent)
        self.draft = []
        self.changed.emit()
        self.update()

    def _finalize_arc(self, p3):
        c, s = self.draft[0], self.draft[1]
        r = math.hypot(s[0] - c[0], s[1] - c[1])
        if r < 1e-9:
            self.draft = []
            return
        a1 = math.degrees(math.atan2(s[1] - c[1], s[0] - c[0]))
        a2 = math.degrees(math.atan2(p3[1] - c[1], p3[0] - c[0]))
        self.about_to_edit.emit()
        self.entities.append({"type": "arc", "plane": self.plane,
                              "center": [c[0], c[1]], "radius": r,
                              "a1": a1, "a2": a2})
        self.draft = []
        self.changed.emit()
        self.update()


# =============================================================================
# DIALOG MODALE 2PenAxE
# =============================================================================

def _dialog_stylesheet() -> str:
    return f"""
        QDialog {{
            background-color: {BG_PAGE};
        }}
        QFrame#penaxePanel {{
            background-color: {BG_PANEL};
            border: 1px solid {BORDER_SOFT};
            border-radius: 10px;
        }}
        QFrame#penaxeAnchors {{
            background-color: {BG_PANEL};
            border: 1px solid {BORDER_SOFT};
            border-radius: 10px;
        }}
        QLabel#penaxeTitle {{
            color: {AMBER};
            font-family: {FONT_HEAD};
            font-size: 22px;
            font-weight: 900;
        }}
        QLabel#penaxeSubtitle {{
            color: {TEXT_MUTED};
            font-size: 11px;
        }}
        QLabel#panelTitle {{
            color: {AMBER};
            font-family: {FONT_HEAD};
            font-size: 12px;
            font-weight: bold;
        }}
        QLabel#panelStatus {{
            color: {TEXT_MUTED};
            font-family: {FONT_MONO};
            font-size: 11px;
        }}
        QLabel#snapLed {{
            color: {GREEN_CRT};
            font-family: {FONT_MONO};
            font-size: 11px;
        }}
        QLabel#snapLedOff {{
            color: {TEXT_MUTED};
            font-family: {FONT_MONO};
            font-size: 11px;
        }}
        QLabel#anchorCount {{
            color: {TEXT_ON_AMBER};
            background: {AMBER};
            border-radius: 9px;
            font-family: {FONT_MONO};
            font-size: 10px;
            font-weight: bold;
            padding: 1px 6px;
        }}
        QPushButton#toolBtn {{
            background: {BG_CARD};
            border: 1px solid {BORDER_SOFT};
            border-radius: 8px;
            padding: 4px;
        }}
        QPushButton#toolBtn:hover {{
            background: {BG_ELEV};
            border-color: {AMBER_DARK};
        }}
        QPushButton#toolBtn:checked {{
            background: {AMBER_FAINT};
            border: 2px solid {AMBER};
        }}
        QPushButton#segBtn {{
            background: {BG_CARD};
            color: {TEXT_MUTED};
            border: 1px solid {BORDER_SOFT};
            border-radius: 7px;
            font-family: {FONT_HEAD};
            font-size: 10px;
            font-weight: bold;
            padding: 2px 10px;
        }}
        QPushButton#segBtn:hover {{
            background: {BG_ELEV};
            color: {TEXT_BODY};
        }}
        QPushButton#segBtn:checked {{
            background: {AMBER};
            color: {TEXT_ON_AMBER};
            border-color: {AMBER_DARK};
        }}
        QPushButton#viewBtn {{
            background: {BG_CARD};
            color: {TEXT_BODY};
            border: 1px solid {BORDER_SOFT};
            border-radius: 8px;
            font-family: {FONT_HEAD};
            font-size: 11px;
            padding: 4px 12px;
        }}
        QPushButton#viewBtn:hover {{
            background: {BG_ELEV};
            border-color: {AMBER_DARK};
        }}
        QPushButton#viewBtn:checked {{
            background: {BG_ELEV};
            border: 2px solid {AMBER};
            color: {AMBER_LIGHT};
        }}
        QPushButton#viewCtlBtn {{
            background: {BG_CARD};
            border: 1px solid {BORDER_SOFT};
            border-radius: 6px;
            padding: 2px;
        }}
        QPushButton#viewCtlBtn:checked {{
            background: {AMBER_FAINT};
            border: 2px solid {AMBER};
        }}
        QFrame#viewCtlBox {{
            background: rgba(12, 30, 54, 200);
            border: 1px solid {BORDER_SOFT};
            border-radius: 8px;
        }}
        QLabel#viewCtlLabel {{
            color: {TEXT_MUTED};
            font-size: 9px;
        }}
        QPushButton#okBtn {{
            background: {AMBER};
            color: {TEXT_ON_AMBER};
            border: 2px solid {AMBER_DARK};
            border-radius: 10px;
            font-family: {FONT_HEAD};
            font-size: 12px;
            font-weight: bold;
            padding: 6px 26px;
        }}
        QPushButton#okBtn:hover {{
            background: {AMBER_LIGHT};
        }}
        QPushButton#applyBtn {{
            background: {BG_CARD};
            color: {AMBER};
            border: 2px solid {AMBER};
            border-radius: 10px;
            font-family: {FONT_HEAD};
            font-size: 12px;
            font-weight: bold;
            padding: 6px 20px;
        }}
        QPushButton#applyBtn:hover {{
            background: {BG_ELEV};
            color: {AMBER_LIGHT};
        }}
        QPushButton#cancelBtn {{
            background: {BG_CARD};
            color: {TEXT_BODY};
            border: 1px solid {BORDER_SOFT};
            border-radius: 10px;
            font-family: {FONT_HEAD};
            font-size: 12px;
            padding: 6px 20px;
        }}
        QPushButton#cancelBtn:hover {{
            background: {BG_ELEV};
            border-color: {AMBER_DARK};
        }}
        QPushButton#closeBtn {{
            background: {BG_CARD};
            color: {TEXT_BODY};
            border: 1px solid {BORDER_SOFT};
            border-radius: 8px;
            font-size: 13px;
            font-weight: bold;
            padding: 2px 10px;
        }}
        QPushButton#closeBtn:hover {{
            background: {BRASS};
            color: {TEXT_ON_AMBER};
        }}
        QLabel#footerInfo {{
            color: {TEXT_MUTED};
            font-family: {FONT_MONO};
            font-size: 11px;
        }}
    """


class SketchDialog(QDialog):
    """Finestra modale 2PenAxE: due pannelli sketch multi-piano con live update.

    `on_change(entities, state)` viene chiamata a ogni modifica (live update
    della scena 3D) e al commit; su Annulla/chiusura viene ripristinato lo
    snapshot iniziale e richiamata la callback.
    """

    def __init__(self, parent=None, scene=None, on_change=None):
        super().__init__(parent)
        self.scene = scene
        self.on_change = on_change
        self.setWindowTitle("2PenAxE — Sketch 2D multi-piano")
        self.setWindowIcon(_load_app_icon(48))
        self.setModal(True)
        self.resize(1600, 900)
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(_dialog_stylesheet())

        state = dict(getattr(scene, "sketch_2d_state", {}) or {})
        self.entities: List[Dict[str, Any]] = [
            dict(e) for e in (getattr(scene, "sketch_2d_entities", []) or [])]
        self._baseline_entities = [dict(e) for e in self.entities]
        self._baseline_state = dict(state)

        self.grid_mm = float(state.get("grid_mm", 10.0) or 10.0)
        self.anchors: Dict[str, bool] = {k: d for k, _, d in ANCHOR_DEFS}
        saved_anchors = state.get("anchors") or {}
        for k, _, _ in ANCHOR_DEFS:
            if k in saved_anchors:
                self.anchors[k] = bool(saved_anchors[k])
        self._panel_planes = [state.get("panel_a", "XY"), state.get("panel_b", "XZ")]
        for i, pl in enumerate(self._panel_planes):
            if pl not in PLANES:
                self._panel_planes[i] = PLANES[i]
        self._tool = state.get("tool", "line")
        if self._tool not in dict((k, 1) for k, _, _ in TOOL_DEFS):
            self._tool = "line"

        self._undo_stack: List[List[Dict[str, Any]]] = []
        self._redo_stack: List[List[Dict[str, Any]]] = []
        self._view_ctl_groups: List[Dict[str, QPushButton]] = []

        self._build_ui()
        self._push_context()
        self._update_anchor_count()
        self._refresh_status()

    # --- COSTRUZIONE UI -----------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # Header: icona + titolo + chiusura.
        header = QHBoxLayout()
        header.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_load_app_icon(44).pixmap(44, 44))
        header.addWidget(icon_lbl)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("2PenAxE")
        title.setObjectName("penaxeTitle")
        subtitle = QLabel("Sketch 2D multi-piano · TriviumCAD")
        subtitle.setObjectName("penaxeSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setToolTip("Chiudi senza salvare (come Annulla)")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        root.addLayout(header)

        # Riga strumenti + viste standard.
        tools_row = QHBoxLayout()
        tools_row.setSpacing(4)
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_buttons: Dict[str, QPushButton] = {}
        for key, label, tip in TOOL_DEFS:
            b = QPushButton()
            b.setObjectName("toolBtn")
            b.setCheckable(True)
            b.setIcon(_tool_icon(key, 24))
            b.setIconSize(QSize(24, 24))
            b.setFixedSize(42, 36)
            b.setToolTip("%s — %s" % (label, tip))
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(key == self._tool)
            b.clicked.connect(lambda _c, k=key: self._set_tool(k))
            self._tool_group.addButton(b)
            self._tool_buttons[key] = b
            tools_row.addWidget(b)
        tools_row.addSpacing(8)
        for key, tip in (("undo", "Annulla (Ctrl+Z)"), ("redo", "Ripristina (Ctrl+Y)")):
            b = QPushButton()
            b.setObjectName("toolBtn")
            b.setIcon(_tool_icon(key, 24))
            b.setIconSize(QSize(24, 24))
            b.setFixedSize(42, 36)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            if key == "undo":
                b.clicked.connect(self.undo)
            else:
                b.clicked.connect(self.redo)
            tools_row.addWidget(b)
        tools_row.addStretch()
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self._view_buttons: Dict[str, QPushButton] = {}
        for name, tip in VIEW_DEFS:
            b = QPushButton(name)
            b.setObjectName("viewBtn")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, n=name: self._apply_view(n))
            self._view_group.addButton(b)
            self._view_buttons[name] = b
            tools_row.addWidget(b)
        root.addLayout(tools_row)

        # Corpo: due pannelli + colonna ancore.
        body = QHBoxLayout()
        body.setSpacing(10)
        self.canvas_a, panel_a = self._build_panel("Pannello A", 0)
        self.canvas_b, panel_b = self._build_panel("Pannello B", 1)
        body.addWidget(panel_a, 1)
        body.addWidget(panel_b, 1)
        body.addWidget(self._build_anchors_panel(), 0)
        root.addLayout(body, 1)

        # Footer: info + griglia + pulsanti.
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._footer_info = QLabel("")
        self._footer_info.setObjectName("footerInfo")
        footer.addWidget(self._footer_info)
        footer.addStretch()
        footer.addWidget(QLabel("Griglia:"))
        self.grid_combo = QComboBox()
        for mm in (1, 2, 5, 10, 20, 50):
            self.grid_combo.addItem("%d mm" % mm, mm)
        idx = self.grid_combo.findData(int(self.grid_mm))
        self.grid_combo.setCurrentIndex(idx if idx >= 0 else 3)
        self.grid_combo.setToolTip("Passo della griglia in mm (snap e disegno)")
        self.grid_combo.currentIndexChanged.connect(self._on_grid_changed)
        footer.addWidget(self.grid_combo)
        footer.addSpacing(10)
        cancel_btn = QPushButton("Annulla")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setToolTip("Chiudi e annulla tutte le modifiche di questa sessione")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("Applica")
        apply_btn.setObjectName("applyBtn")
        apply_btn.setToolTip("Conferma le modifiche correnti senza chiudere")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.clicked.connect(self._apply)
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("okBtn")
        ok_btn.setToolTip("Conferma e chiudi (Ctrl+Invio)")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        footer.addWidget(cancel_btn)
        footer.addWidget(apply_btn)
        footer.addWidget(ok_btn)
        root.addLayout(footer)

        QShortcut("Ctrl+Z", self).activated.connect(self.undo)
        QShortcut("Ctrl+Y", self).activated.connect(self.redo)
        QShortcut("Ctrl+Shift+Z", self).activated.connect(self.redo)
        QShortcut("Ctrl+Return", self).activated.connect(self.accept)

    def _build_panel(self, title: str, index: int):
        panel = QFrame()
        panel.setObjectName("penaxePanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(6)
        lbl = QLabel(title)
        lbl.setObjectName("panelTitle")
        head.addWidget(lbl)
        head.addStretch()
        head.addWidget(QLabel("Piano:"))
        group = QButtonGroup(self)
        group.setExclusive(True)
        for pl in PLANES:
            b = QPushButton(pl)
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setToolTip("Piano di lavoro %s (disegno su questo piano)" % pl)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(pl == self._panel_planes[index])
            b.clicked.connect(lambda _c, p=pl, i=index: self._set_panel_plane(i, p))
            group.addButton(b)
            head.addWidget(b)
        lay.addLayout(head)

        canvas = SketchCanvas(self, self._panel_planes[index])
        # All'apertura del dialogo ogni pannello parte in vista Isometrica:
        # così le entità di tutti i piani restano visibili in prospettiva in
        # entrambi i pannelli (fix N47 2026-10-04). I pulsanti Alto/Fronte/
        # Lato/Iso restano invariati per orientarsi.
        canvas.set_standard_view("Isometrica")
        canvas.status_changed.connect(
            lambda s, c=canvas: self._on_canvas_status(c, s))
        canvas.changed.connect(self._on_canvas_changed)
        canvas.about_to_edit.connect(self._push_undo)
        lay.addWidget(canvas, 1)

        status = QHBoxLayout()
        status.setSpacing(6)
        coords = QLabel("X: 0.00   Y: 0.00   Z: 0.00")
        coords.setObjectName("panelStatus")
        led = QLabel("● Snap ON")
        led.setObjectName("snapLed")
        status.addWidget(coords)
        status.addStretch()
        status.addWidget(led)
        lay.addLayout(status)
        canvas._status_label = coords
        canvas._led_label = led

        # Controlli vista 3D (overlay in alto a destra del canvas).
        ctl = QFrame(canvas)
        ctl.setObjectName("viewCtlBox")
        ctl_lay = QVBoxLayout(ctl)
        ctl_lay.setContentsMargins(4, 4, 4, 4)
        ctl_lay.setSpacing(2)
        ctl_title = QLabel("Controlli vista 3D")
        ctl_title.setObjectName("viewCtlLabel")
        ctl_lay.addWidget(ctl_title)
        ctl_group = QButtonGroup(self)
        ctl_group.setExclusive(False)
        ctl_buttons: Dict[str, QPushButton] = {}
        for key, tip in (("rotate", "Trascina per ruotare la vista (360°)"),
                         ("zoom", "Trascina su/giù per zoomare"),
                         ("pan", "Trascina per spostare la vista")):
            b = QPushButton()
            b.setObjectName("viewCtlBtn")
            b.setCheckable(True)
            b.setIcon(_tool_icon(key, 20))
            b.setIconSize(QSize(20, 20))
            b.setFixedSize(30, 28)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, k=key, btn=b: self._toggle_view_mode(k, btn))
            ctl_group.addButton(b)
            ctl_buttons[key] = b
            ctl_lay.addWidget(b, 0, Qt.AlignRight)
        self._view_ctl_groups.append(ctl_buttons)
        ctl.adjustSize()
        ctl.move(10, 10)
        ctl.show()
        canvas._view_ctl = ctl
        return canvas, panel

    def _build_anchors_panel(self):
        frame = QFrame()
        frame.setObjectName("penaxeAnchors")
        frame.setFixedWidth(240)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("Ancore selezionabili")
        title.setObjectName("panelTitle")
        head.addWidget(title)
        head.addStretch()
        self._anchor_count = QLabel("4 / 7")
        self._anchor_count.setObjectName("anchorCount")
        head.addWidget(self._anchor_count)
        lay.addLayout(head)
        self._anchor_checks: Dict[str, QCheckBox] = {}
        for key, label, _default in ANCHOR_DEFS:
            cb = QCheckBox(label)
            cb.setChecked(self.anchors.get(key, False))
            cb.setToolTip("Attiva/disattiva l'ancora «%s»" % label)
            cb.setCursor(Qt.PointingHandCursor)
            cb.toggled.connect(lambda _c, k=key: self._on_anchor_toggled(k))
            self._anchor_checks[key] = cb
            lay.addWidget(cb)
        lay.addStretch()
        info = QLabel("Le ancore agganciano il cursore durante disegno e misure. "
                      "Il marcatore ambra mostra l'aggancio attivo.")
        info.setWordWrap(True)
        info.setObjectName("panelStatus")
        lay.addWidget(info)
        return frame

    # --- CONTESTO E STATO ---------------------------------------------------
    def _push_context(self):
        for c in (self.canvas_a, self.canvas_b):
            c.set_context(self.entities, self.anchors, self.grid_mm)
            c.set_tool(self._tool)

    def _panel_canvas(self, index: int) -> SketchCanvas:
        return self.canvas_a if index == 0 else self.canvas_b

    def _set_tool(self, key: str):
        self._tool = key
        for c in (self.canvas_a, self.canvas_b):
            c.set_tool(key)

    def _set_panel_plane(self, index: int, plane: str):
        self._panel_planes[index] = plane
        self._panel_canvas(index).set_plane(plane)
        self._push_context()
        self._notify_change()

    def _on_grid_changed(self, _idx: int):
        self.grid_mm = float(self.grid_combo.currentData())
        self._push_context()
        self._notify_change()

    def _on_anchor_toggled(self, key: str):
        self.anchors[key] = self._anchor_checks[key].isChecked()
        self._update_anchor_count()
        self._refresh_status()
        for c in (self.canvas_a, self.canvas_b):
            c.update()
        self._notify_change()

    def _update_anchor_count(self):
        n = sum(1 for k in self.anchors if self.anchors[k])
        self._anchor_count.setText("%d / %d" % (n, len(ANCHOR_DEFS)))
        for c in (self.canvas_a, self.canvas_b):
            if hasattr(c, "_led_label"):
                if n > 0:
                    c._led_label.setText("● Snap ON")
                    c._led_label.setObjectName("snapLed")
                else:
                    c._led_label.setText("● Snap OFF")
                    c._led_label.setObjectName("snapLedOff")
                c._led_label.style().unpolish(c._led_label)
                c._led_label.style().polish(c._led_label)

    def _refresh_status(self):
        n = sum(1 for k in self.anchors if self.anchors[k])
        self._footer_info.setText(
            "2 pannelli · %d/%d ancore attive · snap %s"
            % (n, len(ANCHOR_DEFS), "ON" if n > 0 else "OFF"))

    def _on_canvas_status(self, canvas: SketchCanvas, text: str):
        if hasattr(canvas, "_status_label"):
            canvas._status_label.setText(text)

    # --- VISTE E MODALITÀ ---------------------------------------------------
    def _apply_view(self, name: str):
        # La vista si applica al pannello con il focus, altrimenti a entrambi.
        target = None
        fw = self.focusWidget()
        for c in (self.canvas_a, self.canvas_b):
            if fw is c or (fw is not None and c.isAncestorOf(fw)):
                target = c
                break
        targets = [target] if target is not None else [self.canvas_a, self.canvas_b]
        for c in targets:
            c.set_standard_view(name)
        self._view_buttons[name].setChecked(True)

    def _toggle_view_mode(self, key: str, btn: QPushButton):
        active = btn.isChecked()
        for group in self._view_ctl_groups:
            for k, b in group.items():
                if b is not btn and b.isChecked():
                    b.blockSignals(True)
                    b.setChecked(False)
                    b.blockSignals(False)
        mode = key if active else None
        for c in (self.canvas_a, self.canvas_b):
            c.set_view_mode(mode)

    # --- UNDO/REDO ----------------------------------------------------------
    def _push_undo(self):
        self._undo_stack.append([dict(e) for e in self.entities])
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append([dict(e) for e in self.entities])
        self.entities[:] = self._undo_stack.pop()
        self._after_undo_redo()

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append([dict(e) for e in self.entities])
        self.entities[:] = self._redo_stack.pop()
        self._after_undo_redo()

    def _after_undo_redo(self):
        for c in (self.canvas_a, self.canvas_b):
            c.selected_index = -1
            c.update()
        self._notify_change()

    # --- LIVE UPDATE E COMMIT -----------------------------------------------
    def _state_dict(self) -> Dict[str, Any]:
        return {
            "panel_a": self._panel_planes[0],
            "panel_b": self._panel_planes[1],
            "grid_mm": self.grid_mm,
            "anchors": dict(self.anchors),
            "tool": self._tool,
        }

    def _notify_change(self):
        if self.on_change is not None:
            try:
                self.on_change(self.entities, self._state_dict())
            except Exception as e:
                print("[2PenAxE] errore callback live update: %s" % e)

    def _on_canvas_changed(self):
        self._notify_change()

    def _apply(self):
        self._notify_change()
        self._baseline_entities = [dict(e) for e in self.entities]
        self._baseline_state = self._state_dict()
        self._footer_info.setText(
            "Sketch applicato · %d entità" % len(self.entities))

    def _rollback(self):
        self.entities[:] = [dict(e) for e in self._baseline_entities]
        if self.on_change is not None:
            try:
                self.on_change(self.entities, dict(self._baseline_state))
            except Exception as e:
                print("[2PenAxE] errore callback rollback: %s" % e)

    def accept(self):
        self._notify_change()
        super().accept()

    def reject(self):
        self._rollback()
        super().reject()

