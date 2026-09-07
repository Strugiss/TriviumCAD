"""TriviumCAD core - generatori di forme e testo 3D (estratte da triviumcad.py)."""
import math
import numpy as np
import trimesh
from shapely.geometry import Polygon as ShapelyPolygon

# --- GENERATORI BLENDER (compatibilita) ---
def _generate_blender_donut(R: float, r: float, major_segs: int, minor_segs: int) -> trimesh.Trimesh:
    major_segs = max(8, int(major_segs))
    minor_segs = max(4, int(minor_segs))
    if R <= r + 0.1:
        R = r + 0.2
    u = np.linspace(0, 2 * np.pi, major_segs, endpoint=False)
    v = np.linspace(0, 2 * np.pi, minor_segs, endpoint=False)
    U, V = np.meshgrid(u, v, indexing='ij')
    X = (R + r * np.cos(V)) * np.cos(U)
    Y = (R + r * np.cos(V)) * np.sin(U)
    Z = r * np.sin(V)
    verts = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
    i = np.arange(major_segs)
    j = np.arange(minor_segs)
    i_next = (i + 1) % major_segs
    j_next = (j + 1) % minor_segs
    I, J = np.meshgrid(i, j, indexing='ij')
    I_next, J_next = np.meshgrid(i_next, j_next, indexing='ij')
    v00 = I * minor_segs + J
    v10 = I_next * minor_segs + J
    v11 = I_next * minor_segs + J_next
    v01 = I * minor_segs + J_next
    faces_1 = np.stack([v00, v10, v11], axis=-1).reshape(-1, 3)
    faces_2 = np.stack([v00, v11, v01], axis=-1).reshape(-1, 3)
    faces = np.vstack([faces_1, faces_2])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)
    mesh.fix_normals()
    return mesh

def _generate_blender_collare(outer_radius: float, inner_radius: float, height: float) -> trimesh.Trimesh:
    n = 64
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)
    
    outer_xy = np.column_stack([outer_radius * cos_a, outer_radius * sin_a])
    inner_xy = np.column_stack([inner_radius * cos_a, inner_radius * sin_a])
    
    top = height
    bot = 0.0
    
    # Vertices: [top_outer(0..n-1), top_inner(0..n-1), bot_outer(0..n-1), bot_inner(0..n-1)]
    to = np.column_stack([outer_xy, np.full(n, top)])
    ti = np.column_stack([inner_xy, np.full(n, top)])
    bo = np.column_stack([outer_xy, np.full(n, bot)])
    bi = np.column_stack([inner_xy, np.full(n, bot)])
    verts = np.vstack([to, ti, bo, bi])
    
    faces = []
    # Helper: add quad as two tris (v0,v1,v2) and (v0,v2,v3)
    def add_quad(a, b, c, d):
        faces.append((a, b, c))
        faces.append((a, c, d))
    
    for i in range(n):
        j = (i + 1) % n
        
        to_i, to_j = i, j
        ti_i, ti_j = n + i, n + j
        bo_i, bo_j = 2 * n + i, 2 * n + j
        bi_i, bi_j = 3 * n + i, 3 * n + j
        
        # Top face
        add_quad(to_i, to_j, ti_j, ti_i)
        # Bottom face (reversed winding for outward normal)
        add_quad(bo_i, bi_i, bi_j, bo_j)
        # Outer wall
        add_quad(to_i, bo_i, bo_j, to_j)
        # Inner wall
        add_quad(ti_i, ti_j, bi_j, bi_i)
    
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    # Ensure bottom faces point DOWN and top faces point UP
    fn = mesh.face_normals
    for i in range(len(faces)):
        a, b, c = faces[i]
        if verts[a][2] == bot and verts[b][2] == bot and verts[c][2] == bot:
            if fn[i][2] > 0:
                fn[i] = [0, 0, -1]
        elif verts[a][2] == top and verts[b][2] == top and verts[c][2] == top:
            if fn[i][2] < 0:
                fn[i] = [0, 0, 1]
    return mesh

def _generate_blender_cylinder(radius: float, height: float, sections: int) -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(radius=radius, height=height, sections=int(sections))
    mesh.fix_normals()
    return mesh

def _generate_blender_sphere(radius: float, subdivisions: int) -> trimesh.Trimesh:
    mesh = trimesh.creation.icosphere(radius=radius, subdivisions=min(6, int(subdivisions)))
    mesh.fix_normals()
    return mesh

def _generate_blender_cone(radius: float, height: float, sections: int) -> trimesh.Trimesh:
    mesh = trimesh.creation.cone(radius=radius, height=height, sections=int(sections))
    mesh.fix_normals()
    return mesh

def _generate_blender_box(width: float, height: float, depth: float) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=[width, depth, height])
    mesh.fix_normals()
    return mesh

def _generate_blender_hexagon(radius: float, height: float) -> trimesh.Trimesh:
    from shapely.geometry import Polygon as SPolygon
    angles = [2 * math.pi * i / 6 for i in range(6)]
    pts = [(radius * math.cos(a), radius * math.sin(a)) for a in angles]
    mesh = trimesh.creation.extrude_polygon(SPolygon(pts), height=height)
    mesh.fix_normals()
    return mesh

def _generate_blender_spiral(radius: float, height: float, turns: int, thickness: float) -> trimesh.Trimesh:
    turns = max(1, int(turns))
    thickness = max(0.5, thickness)
    r_tube = thickness / 2
    segs = int(turns * 48)
    ring_segs = max(12, int(thickness * 4))
    
    verts = []
    faces = []
    
    def helix_point(t):
        theta = t * 2 * np.pi * turns
        x = radius * np.cos(theta)
        y = radius * np.sin(theta)
        z = t * height
        return np.array([x, y, z]), theta
    
    def frenet_frame(theta):
        h_per_turn = height / max(1, turns)
        T = np.array([-radius * np.sin(theta), radius * np.cos(theta), h_per_turn / (2 * np.pi)])
        T = T / (np.linalg.norm(T) + 1e-12)
        N = np.array([-np.cos(theta), -np.sin(theta), 0.0])
        N = N / (np.linalg.norm(N) + 1e-12)
        B = np.cross(T, N)
        B = B / (np.linalg.norm(B) + 1e-12)
        N = np.cross(B, T)
        return T, N, B
    
    for i in range(segs + 1):
        t = i / segs
        pt, theta = helix_point(t)
        T, N, B = frenet_frame(theta)
        for j in range(ring_segs):
            phi = j / ring_segs * 2 * np.pi
            rv = r_tube * (N * np.cos(phi) + B * np.sin(phi))
            verts.append(pt + rv)
    
    n_ring = ring_segs
    for i in range(segs):
        for j in range(ring_segs):
            jn = (j + 1) % ring_segs
            v00 = i * n_ring + j
            v01 = i * n_ring + jn
            v10 = (i + 1) * n_ring + j
            v11 = (i + 1) * n_ring + jn
            faces.append((v00, v10, v11))
            faces.append((v00, v11, v01))
    
    # End caps
    offset = len(verts)
    for t_val, sign in [(0.0, -1), (1.0, 1)]:
        pt, theta = helix_point(t_val)
        T, N, B = frenet_frame(theta)
        cap_center = len(verts)
        verts.append(pt)
        for j in range(ring_segs):
            phi = j / ring_segs * 2 * np.pi
            rv = r_tube * (N * np.cos(phi) + B * np.sin(phi))
            verts.append(pt + rv)
        for j in range(ring_segs):
            jn = (j + 1) % ring_segs
            if sign == 1:
                faces.append((cap_center, cap_center + jn + 1, cap_center + j + 1))
            else:
                faces.append((cap_center, cap_center + j + 1, cap_center + jn + 1))
    
    verts = np.array(verts, dtype=np.float32)
    faces = np.array(faces, dtype=np.uint32)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)
    mesh.fix_normals()
    return mesh

def _generate_blender_arc(outer_r: float, inner_r: float, angle_deg: float, height: float) -> trimesh.Trimesh:
    from shapely.geometry import Point
    angle_deg = min(360, max(1, angle_deg))
    angle_rad = math.radians(angle_deg)
    outer = Point(0, 0).buffer(outer_r, resolution=64)
    inner = Point(0, 0).buffer(inner_r, resolution=64)
    ring = outer.difference(inner)
    if angle_deg >= 360:
        mesh = trimesh.creation.extrude_polygon(ring, height=height)
        mesh.fix_normals()
        return mesh
    from shapely.affinity import rotate
    from shapely.geometry import box as sbox
    cut = sbox(-outer_r * 2, -outer_r * 2, 0, outer_r * 2)
    cut = rotate(cut, -(90 - angle_deg / 2), origin=(0, 0), use_radians=False)
    sector = ring.intersection(cut)
    if sector.is_empty:
        return _generate_blender_collare(outer_r, inner_r, height)
    polys = [sector] if sector.geom_type == 'Polygon' else [g for g in sector.geoms if g.geom_type == 'Polygon']
    all_verts, all_faces, offset = [], [], 0
    for p in polys:
        m = trimesh.creation.extrude_polygon(p, height=height)
        if m and len(m.vertices) > 0:
            all_verts.append(m.vertices)
            all_faces.append(m.faces + offset)
            offset += len(m.vertices)
    if not all_verts:
        return _generate_blender_collare(outer_r, inner_r, height)
    mesh = trimesh.Trimesh(vertices=np.vstack(all_verts), faces=np.vstack(all_faces))
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    return mesh

# --- GENERAZIONE TESTO 3D ---
def _qpath_to_mesh(qpath, thickness):
    from PyQt5.QtGui import QPainterPath
    polys = qpath.toFillPolygons()
    if not polys:
        return trimesh.Trimesh()
    all_polys, holes = [], []
    for poly in polys:
        if len(poly) < 3:
            continue
        pts = [(pt.x(), -pt.y()) for pt in poly]
        if len(pts) < 3:
            continue
        area = 0.0
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
        if area < 0:
            all_polys.append(pts)
        else:
            holes.append(pts)
    if not all_polys:
        return trimesh.Trimesh()
    from shapely.ops import unary_union
    shapely_solids = []
    for pts in all_polys:
        poly = ShapelyPolygon(pts)
        if poly.is_empty:
            continue
        inner = []
        for hp in holes:
            h = ShapelyPolygon(hp)
            if h.is_valid and not h.is_empty and poly.contains(h.representative_point()):
                inner.append(h)
        if inner:
            poly = ShapelyPolygon(pts, inner)
        shapely_solids.append(poly)
    tol = 0.001 * max(1.0, (max(sp.bounds[2] - sp.bounds[0] for sp in shapely_solids if not sp.is_empty)) / 10.0) if shapely_solids else 0.001
    shapely_solids = [sp.buffer(tol) if not sp.is_valid else sp.buffer(0) for sp in shapely_solids if not sp.is_empty]
    shapely_solids = [sp for sp in shapely_solids if sp.is_valid and not sp.is_empty]
    if not shapely_solids:
        return trimesh.Trimesh()
    merged = unary_union(shapely_solids)
    if merged.is_empty:
        return trimesh.Trimesh()
    if merged.geom_type == 'Polygon':
        polys_to_extrude = [merged]
    elif merged.geom_type == 'MultiPolygon':
        polys_to_extrude = list(merged.geoms)
    else:
        return trimesh.Trimesh()
    all_verts, all_faces, offset = [], [], 0
    for poly in polys_to_extrude:
        try:
            ext_mesh = trimesh.creation.extrude_polygon(poly, height=thickness)
            if ext_mesh and len(ext_mesh.vertices) > 0:
                all_verts.append(ext_mesh.vertices)
                all_faces.append(ext_mesh.faces + offset)
                offset += len(ext_mesh.vertices)
        except Exception:
            print("ERRORE: _qpath_to_mesh fallito per un percorso")
            continue
    if not all_verts:
        return trimesh.Trimesh()
    combined = trimesh.Trimesh(vertices=np.vstack(all_verts), faces=np.vstack(all_faces))
    combined.remove_unreferenced_vertices()
    return combined

def _generate_text_mesh(text, font_name, font_size, thickness, spacing):
    from core.mesh_ops import _ensure_volume
    from PyQt5.QtGui import QPainterPath, QFont, QFontMetricsF, QFontDatabase
    from PyQt5.QtCore import QPointF
    if font_name not in QFontDatabase().families():
        font = QFont()
        print(f"ATTENZIONE: font '{font_name}' non trovato: uso il font di sistema ({font.family()})")
    else:
        font = QFont(font_name)
    font.setPointSizeF(float(font_size))
    font_metrics = QFontMetricsF(font)
    all_verts, all_faces, offset = [], [], 0
    x_cursor = 0.0
    y_cursor = 0.0
    line_height = font_metrics.height() * 1.2 if hasattr(font_metrics, 'height') else font_metrics.lineSpacing()
    warned = set()
    for ch in text:
        if ch == '\n':
            x_cursor = 0.0
            y_cursor -= line_height
            continue
        path = QPainterPath()
        path.addText(QPointF(0, 0), font, ch)
        ch_w = font_metrics.horizontalAdvance(ch) if hasattr(font_metrics, 'horizontalAdvance') else font_metrics.width(ch)
        ch_mesh = _qpath_to_mesh(path, thickness)
        if ch_mesh and len(ch_mesh.vertices) > 0:
            if not ch_mesh.is_watertight:
                ch_mesh = _ensure_volume(ch_mesh)
            ch_mesh.apply_translation([x_cursor, y_cursor, 0])
            all_verts.append(ch_mesh.vertices)
            all_faces.append(ch_mesh.faces + offset)
            offset += len(ch_mesh.vertices)
        elif ch not in (' ', '\t') and ch not in warned:
            warned.add(ch)
            print(f"ATTENZIONE: glifo mancante per il carattere {ch!r} nel font '{font_name}': carattere saltato")
        x_cursor += ch_w + spacing
    if not all_verts:
        return trimesh.Trimesh()
    combined = trimesh.Trimesh(vertices=np.vstack(all_verts), faces=np.vstack(all_faces))
    combined.remove_unreferenced_vertices()
    bb = combined.bounds
    if bb is not None and font_size > 0:
        h = bb[1][1] - bb[0][1]
        if h > 1e-9:
            factor = float(font_size) / h
            combined.apply_scale([factor, factor, 1.0])
    return combined


def _generate_blender_hollow_box(width: float, height: float, depth: float, wall: float) -> trimesh.Trimesh:
    from core.mesh_ops import boolean_safe
    outer = trimesh.creation.box(extents=[width, depth, height])
    inner_w = max(0.1, width - 2 * wall)
    inner_h = max(0.1, height - 2 * wall)
    inner_d = max(0.1, depth - 2 * wall)
    inner = trimesh.creation.box(extents=[inner_w, inner_d, inner_h])
    try:
        result = boolean_safe([outer, inner], "difference")
        if result is None or result.is_empty:
            return outer
        cut_h = height - wall
        if cut_h > 0:
            plane_orig = [0, 0, cut_h - height / 2]
            plane_norm = [0, 0, -1]
            sliced = trimesh.intersections.slice_mesh_plane(result, plane_norm, plane_orig, cap=True)
            if sliced is not None and not sliced.is_empty:
                result = sliced
        result.fix_normals()
        return result
    except Exception:
        return outer