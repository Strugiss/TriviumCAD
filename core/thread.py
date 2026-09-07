"""TriviumCAD core - filettatura (estratte da triviumcad.py)."""
import math
import numpy as np
import trimesh
from core.cam import _surface_radius_at

# --- GENERAZIONE FILETTATURA SU FORMA ---
def _r_mod_profile(p, profile):
    """Calcola la modulazione radiale del profilo filetto."""
    p = p % 1.0
    if profile == "Filo":
        # ISO 60°: root flat H/8, crest flat H/4 (BOSL2, SolidPython)
        if p < 0.125:
            return p / 0.125
        elif p < 0.375:
            return 1.0
        elif p < 0.5:
            return 1.0 - (p - 0.375) / 0.125
        elif p < 0.625:
            return -(p - 0.5) / 0.125
        elif p < 0.875:
            return -1.0
        else:
            return -1.0 + (p - 0.875) / 0.125
    elif profile == "Trapezio":
        flat = 0.25; ramp = 0.5 - flat
        if p < flat: return 0.0
        if p < 0.5: return (p - flat) / ramp
        if p < 0.5 + flat: return 1.0
        return 1.0 - (p - 0.5 - flat) / ramp if ramp > 0 else 0.0
    else:
        return 0.5 - 0.5 * math.cos(2 * math.pi * p)

def _apply_thread_profile(mesh, pitch, depth, profile):
    """Applica filettatura esterna su mesh esistente tramite vertex displacement radiale.
    Scava il materiale tra le spire; le creste restano alla superficie originale."""
    verts = mesh.vertices
    angles = np.arctan2(verts[:, 1], verts[:, 0])
    radii = np.sqrt(verts[:, 0]**2 + verts[:, 1]**2)
    phases = (angles + verts[:, 2] * 2 * np.pi / pitch) % (2 * np.pi)
    pn = phases / (2 * np.pi)

    if profile == "Filo":
        p = pn % 1.0
        rm = np.where(p < 0.5, 1 - 4 * p, -1 + 4 * (p - 0.5))
        disp = rm * depth * 0.5
    elif profile == "Trapezio":
        flat = 0.25; ramp = 0.5 - flat
        p = pn % 1.0
        rm = np.zeros(len(verts))
        m1 = p < flat
        m2 = (p >= flat) & (p < 0.5)
        m3 = (p >= 0.5) & (p < 0.5 + flat)
        m4 = p >= 0.5 + flat
        rm[m1] = 0.0
        rm[m2] = (p[m2] - flat) / ramp if ramp > 0 else 0.0
        rm[m3] = 1.0
        rm[m4] = 1.0 - (p[m4] - 0.5 - flat) / ramp if ramp > 0 else 0.0
        disp = (rm - 0.5) * depth
    else:
        rm = 0.5 - 0.5 * np.cos(2 * np.pi * pn)
        disp = (rm - 0.5) * depth

    # Guardia tappi: i vertici centrali dei tappi (r≈0) non devono essere
    # deformati dal profilo filetto (raggio deve restare 0).
    central_mask = (np.abs(verts[:, 0]) < 1e-9) & (np.abs(verts[:, 1]) < 1e-9)
    new_radii = np.maximum(0.01, radii + disp)
    new_radii[central_mask] = 0.0
    verts[:, 0] = new_radii * np.cos(angles)
    verts[:, 1] = new_radii * np.sin(angles)

def _generate_thread_on_shape(mesh: trimesh.Trimesh, turns: int = 8, thread_radius: float = 1.5, segments_per_turn: int = 24, circle_segments: int = 12, profile: str = "Filo") -> trimesh.Trimesh:
    """Genera un filetto elicoidale che segue la superficie della mesh."""
    MAX_TOTAL_VERTS = 500_000
    n = turns * segments_per_turn + 1
    estimated_verts = n * circle_segments
    if estimated_verts > MAX_TOTAL_VERTS:
        print(f"ERRORE: thread genererebbe {estimated_verts} vertici (max {MAX_TOTAL_VERTS}). Riduci turns/segmenti.")
        return trimesh.Trimesh()
    bounds = mesh.bounds
    if bounds is None:
        return trimesh.Trimesh()
    size = bounds[1] - bounds[0]
    verts = mesh.vertices
    centroid = np.mean(verts, axis=0)
    radii = np.linalg.norm(verts - centroid, axis=1)
    r_mean = radii.mean()
    
    # Determina la forma dal bounding box
    is_sphere = max(size) / max(min(size), 1e-8) < 1.3 and abs(size[0] - size[1]) / max((size[0] + size[1]) / 2, 1e-8) < 0.2
    
    if is_sphere:
        R = r_mean
        h = 0.0
    else:
        R = (size[0] + size[1]) / 4
        h = size[2]
    
    n = turns * segments_per_turn + 1
    all_verts = []
    all_faces = []
    
    try:
        for i in range(n):
            t = i / max(n - 1, 1)
            
            if is_sphere:
                theta = -np.pi / 2 + t * np.pi
                phi = t * 2 * np.pi * turns
                px = R * np.cos(theta) * np.cos(phi) + centroid[0]
                py = R * np.cos(theta) * np.sin(phi) + centroid[1]
                pz = R * np.sin(theta) + centroid[2]
                nx = (px - centroid[0]) / R
                ny = (py - centroid[1]) / R
                nz = (pz - centroid[2]) / R
            else:
                phi = t * 2 * np.pi * turns
                px = R * np.cos(phi) + centroid[0]
                py = R * np.sin(phi) + centroid[1]
                pz = -h / 2 + t * h + centroid[2]
                nx = np.cos(phi)
                ny = np.sin(phi)
                nz = 0.0
            
            # Tangente del percorso (analitica)
            if is_sphere:
                d_theta = np.pi
                d_phi = 2 * np.pi * turns
                tx = -R * np.sin(theta) * np.cos(phi) * d_theta - R * np.cos(theta) * np.sin(phi) * d_phi
                ty = -R * np.sin(theta) * np.sin(phi) * d_theta + R * np.cos(theta) * np.cos(phi) * d_phi
                tz = R * np.cos(theta) * d_theta
            else:
                d_phi = 2 * np.pi * turns
                d_z = h
                tx = -R * np.sin(phi) * d_phi
                ty = R * np.cos(phi) * d_phi
                tz = d_z
            
            tl = np.sqrt(tx*tx + ty*ty + tz*tz)
            if tl > 1e-8:
                tx /= tl; ty /= tl; tz /= tl
            else:
                tx, ty, tz = 1.0, 0.0, 0.0
            
            # u = cross(T, N), normalizzato
            ux = ty * nz - tz * ny
            uy = tz * nx - tx * nz
            uz = tx * ny - ty * nx
            ul = np.sqrt(ux*ux + uy*uy + uz*uz)
            if ul > 1e-8:
                ux /= ul; uy /= ul; uz /= ul
            else:
                ux, uy, uz = 1.0, 0.0, 0.0
            
            # v = cross(T, u) — il terzo asse del cerchio
            vx = ty * uz - tz * uy
            vy = tz * ux - tx * uz
            vz = tx * uy - ty * ux
            
            # Cerchio con raggio modulato dal profilo nel piano perpendicolare al percorso
            for j in range(circle_segments):
                alpha = j / circle_segments * 2 * np.pi
                pn = alpha / (2 * np.pi)
                rm = _r_mod_profile(pn, profile)
                if profile == "Filo":
                    r_factor = 1.0 + rm * 0.5  # rm∈[-1,1] → r∈[0.5, 1.5]
                else:
                    r_factor = 0.5 + rm * 0.5  # rm∈[0,1] → r∈[0.5, 1.0]
                r_eff = thread_radius * r_factor
                c = np.cos(alpha)
                s = np.sin(alpha)
                cvx = ux * c * r_eff + vx * s * r_eff
                cvy = uy * c * r_eff + vy * s * r_eff
                cvz = uz * c * r_eff + vz * s * r_eff
                all_verts.append([px - vx * thread_radius + cvx,
                                  py - vy * thread_radius + cvy,
                                  pz - vz * thread_radius + cvz])
            
            if i > 0:
                base = (i - 1) * circle_segments
                for j in range(circle_segments):
                    jn = (j + 1) % circle_segments
                    a = base + j
                    b = base + jn
                    c = base + circle_segments + j
                    d = base + circle_segments + jn
                    all_faces.append([a, c, b])
                    all_faces.append([b, c, d])
        
        result = trimesh.Trimesh(vertices=np.array(all_verts), faces=np.array(all_faces))
        result.remove_unreferenced_vertices()
        result.fix_normals()
        return result
    except MemoryError:
        print("ERRORE: memoria insufficiente per generare il thread")
        return trimesh.Trimesh()


def _get_profile_2d(profile: str, pitch: float, depth_scale: float = 1.0):
    """Restituisce profilo 2D (x_mm, y_mm) per filettatura stile BOSL2.
    x = offset Z dal centro giro (mm), y = displacement radiale (mm, negativo = verso l'interno)."""
    if profile == "Filo":
        d = 0.6134 * pitch
        cw = pitch / 8
        prof = [(-d/math.sqrt(3) - cw/2, -d), (-cw/2, 0), (cw/2, 0), (d/math.sqrt(3) + cw/2, -d)]
    elif profile == "Trapezio":
        d = pitch * 0.5
        flat = 0.25 * pitch
        prof = [(-pitch/2, -d), (-flat, 0), (flat, 0), (pitch/2, -d)]
    else:
        d = pitch * 0.4
        prof = [(-pitch/2 + pitch*i/8, -d*(1-math.cos(2*math.pi*i/8))/2) for i in range(9)]
    if depth_scale != 1.0:
        prof = [(px, py * depth_scale) for px, py in prof]
    return prof

def _generate_base_mesh(shape_type, params, bounds, cx, cy, base_z, height, pitch, turns):
    """Genera mesh cilindrica (N sezioni × M anelli) seguendo la forma nativa.
    N = sezioni radiali (chord tolerance ~1.5mm), M = n_turns × 6 anelli Z.
    Include tappi (vertici condivisi). Usata da _compute_thread_mesh per forme native."""
    rr = math.sqrt((bounds[1][0]-bounds[0][0])**2 + (bounds[1][1]-bounds[0][1])**2) * 0.5
    N = min(max(24, int(2 * math.pi * rr / 1.5), 16), 96)
    n_turns = max(2, turns)
    M = min(n_turns * 6, 120)
    verts = []
    # Superficie laterale: (M+1) anelli × N vertici
    for j in range(M + 1):
        z = base_z + j * height / M
        for i in range(N):
            theta = 2 * math.pi * i / N
            surf_r = _surface_radius_at(shape_type, params, theta, z, bounds, cx, cy, "Esterna")
            r = max(0.01, surf_r)
            verts.append([cx + r * math.cos(theta), cy + r * math.sin(theta), z])
    # Centri tappi
    vi_lo_center = len(verts)
    verts.append([cx, cy, base_z])
    vi_hi_center = len(verts)
    verts.append([cx, cy, base_z + height])
    faces = []
    # Facce laterali
    for j in range(M):
        row0 = j * N
        row1 = (j + 1) * N
        for i in range(N):
            nxt = (i + 1) % N
            faces.append([row0 + i, row1 + i, row0 + nxt])
            faces.append([row0 + nxt, row1 + i, row1 + nxt])
    # Tappo fondo: centro + anello-0, winding antiorario da sotto
    for i in range(N):
        nxt = (i + 1) % N
        faces.append([vi_lo_center, i, nxt])
    # Tappo top: centro + anello-M, winding antiorario da sopra
    row_top = M * N
    for i in range(N):
        nxt = (i + 1) % N
        faces.append([vi_hi_center, row_top + nxt, row_top + i])
    return trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces), process=False)

def _compute_thread_mesh(obj, thr_type, pitch, turns, profile, depth=None):
    """Filettatura esterna: genera mesh ottimizzata (forme native) o subdivide (importate/cave).
    Vertex displacement per scavare valli. Creste = superficie originale."""
    if thr_type == "Interna":
        d_nom = 0.6134 * pitch if profile == "Filo" else (0.5 * pitch if profile == "Trapezio" else 0.4 * pitch)
        return _compute_subtraction_volume(obj, pitch, turns, profile, depth if depth else d_nom)
    depth_nom = 0.6134 * pitch if profile == "Filo" else (0.5 * pitch if profile == "Trapezio" else 0.4 * pitch)
    depth_val = depth if depth else depth_nom
    bounds = obj.bounds
    if bounds is None: return None
    shape_type = obj.metadata.get("shape_type", "imported")
    solid_types = {"cylinder", "sphere", "cone", "box", "hexagon", "arc", "donut"}
    if shape_type in solid_types:
        cx = (bounds[1][0] + bounds[0][0]) / 2
        cy = (bounds[1][1] + bounds[0][1]) / 2
        height = bounds[1][2] - bounds[0][2]
        if height < 1: height = 20.0
        n_turns = max(2, int(height / pitch)) if turns is None or turns < 2 else turns
        mesh = _generate_base_mesh(shape_type, obj.metadata.get("params", {}), bounds, cx, cy, base_z=bounds[0][2], height=height, pitch=pitch, turns=n_turns)
    else:
        import math
        mesh = obj.copy()
        height = bounds[1][2] - bounds[0][2]
        if height < 1: height = 20.0
        n_turns = max(2, int(height / pitch)) if turns is None or turns < 2 else turns
        n_sub = max(2, min(3, int(math.ceil(math.log2(max(2, int(n_turns * 3)) / 2)))))
        for _ in range(n_sub):
            try:
                mesh = mesh.subdivide()
            except Exception as e:
                # Fallback non bloccante: se la suddivisione fallisce si procede
                # con la mesh non suddivisa (profilo meno dettagliato).
                print(f"[TriviumCAD] thread: suddivisione fallita ({e})")
                break
    with np.errstate(divide='ignore', invalid='ignore'):
        _apply_thread_profile(mesh, pitch, depth_val, profile)
        mesh.fix_normals()
    mesh.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_filettato"
    for key in ["_gl_verts", "_gl_normals", "_gl_vbo_verts", "_gl_vbo_normals"]:
        mesh.metadata.pop(key, None)
    return mesh

def _compute_subtraction_volume(obj, pitch, turns, profile, h_thread):
    """Genera volume watertight per boolean difference su filettatura interna."""
    bounds = obj.bounds
    if bounds is None:
        return None
    shape_type = obj.metadata.get("shape_type", "imported")
    params = obj.metadata.get("params", {})
    height = bounds[1][2] - bounds[0][2]
    if height < 1: height = 20.0
    cx = (bounds[1][0] + bounds[0][0]) / 2
    cy = (bounds[1][1] + bounds[0][1]) / 2
    segs_r = 32
    segs_z = max(4, int(turns * 24))
    base_z = bounds[0][2]
    eps = 0.01

    rows = []
    for i in range(segs_z + 1):
        z = base_z + height * i / max(1, segs_z)
        for j in range(segs_r):
            theta = 2 * math.pi * j / segs_r
            surf_r = _surface_radius_at(shape_type, params, theta, z, bounds, cx, cy, "Interna")
            phase = (theta + z * 2 * math.pi / pitch) % (2 * math.pi)
            rm = _r_mod_profile(phase / (2 * math.pi), profile)
            rows.append((surf_r, rm, theta, z))

    n = len(rows)
    verts = []
    # Layer 0: sempre dentro il foro (nessun overlap con l'oggetto)
    hole_r = max(r for r, _, _, _ in rows) - h_thread * 1.1
    hole_r = max(hole_r, 0.01)
    for (surf_r, rm, theta, z) in rows:
        verts.append([cx + hole_r * math.cos(theta), cy + hole_r * math.sin(theta), z])
    # Layer 1: modulato nella parete (penetra dove rm>0)
    for (surf_r, rm, theta, z) in rows:
        r = surf_r + h_thread * max(0, rm)
        verts.append([cx + r * math.cos(theta), cy + r * math.sin(theta), z])

    n_outer = n
    faces = []
    for i in range(segs_z):
        for j in range(segs_r):
            v0 = i * segs_r + j
            v1 = i * segs_r + (j + 1) % segs_r
            v2 = (i + 1) * segs_r + j
            v3 = (i + 1) * segs_r + (j + 1) % segs_r
            faces.append([v0, v1, v2])
            faces.append([v1, v3, v2])
            v0n = v0 + n_outer
            v1n = v1 + n_outer
            v2n = v2 + n_outer
            v3n = v3 + n_outer
            faces.append([v2n, v1n, v0n])
            faces.append([v2n, v3n, v1n])

    top0 = segs_z * segs_r
    top1 = n_outer + segs_z * segs_r
    for j in range(segs_r):
        nj = (j + 1) % segs_r
        faces.append([top0 + j, top0 + nj, top1 + j])
        faces.append([top0 + nj, top1 + nj, top1 + j])
    for j in range(segs_r):
        nj = (j + 1) % segs_r
        faces.append([j, n_outer + j, nj])
        faces.append([n_outer + j, n_outer + nj, nj])

    result = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces))
    result.remove_unreferenced_vertices()
    result.fix_normals()
    return result

def _compute_thread_surface_projection(obj, thr_type, pitch, turns, profile, h_thread):
    """Filettatura per forme importate: proietta percorso elicoidale sulla mesh."""
    bounds = obj.bounds
    height = bounds[1][2] - bounds[0][2]
    cx = (bounds[1][0] + bounds[0][0]) / 2
    cy = (bounds[1][1] + bounds[0][1]) / 2
    segs_r = 24
    segs_z = max(4, int(turns * 16))
    base_z = bounds[0][2]

    verts = []
    half_diag = math.hypot(bounds[1][0] - cx, bounds[1][1] - cy)
    ray_dist = half_diag * 2 + 1.0
    for i in range(segs_z + 1):
        z = base_z + height * i / max(1, segs_z)
        for j in range(segs_r):
            theta = 2 * math.pi * j / segs_r
            phase = (theta + z * 2 * math.pi / pitch) % (2 * math.pi)
            pn = phase / (2 * math.pi)
            rm = _r_mod_profile(pn, profile)
            ray_origin = [cx + ray_dist * math.cos(theta), cy + ray_dist * math.sin(theta), z]
            ray_dir = [-math.cos(theta), -math.sin(theta), 0.0]
            try:
                hits = obj.ray.intersects_location([ray_origin], [ray_dir])
                if len(hits) > 0:
                    nominal_r = math.hypot(hits[0][0] - cx, hits[0][1] - cy)
                else:
                    nominal_r = half_diag
            except Exception:
                # Intenzionale: ray miss su questo raggio -> si usa la diagonale
                # metà del bounding box come raggio nominale di fallback.
                nominal_r = half_diag
            if thr_type == "Esterna":
                r = nominal_r + h_thread * rm
            else:
                r = nominal_r - h_thread * max(0, rm)
            verts.append([cx + r * math.cos(theta), cy + r * math.sin(theta), z])

    n_outer = len(verts)
    cap_r = max(half_diag * 0.3, 0.1)
    for i in range(segs_z + 1):
        z = base_z + height * i / max(1, segs_z)
        for j in range(segs_r):
            theta = 2 * math.pi * j / segs_r
            verts.append([cx + cap_r * math.cos(theta), cy + cap_r * math.sin(theta), z])

    faces = []
    for i in range(segs_z):
        for j in range(segs_r):
            v0 = i * segs_r + j
            v1 = i * segs_r + (j + 1) % segs_r
            v2 = (i + 1) * segs_r + j
            v3 = (i + 1) * segs_r + (j + 1) % segs_r
            faces.append([v0, v1, v2])
            faces.append([v1, v3, v2])
    for i in range(segs_z):
        for j in range(segs_r):
            v0 = n_outer + i * segs_r + j
            v1 = n_outer + i * segs_r + (j + 1) % segs_r
            v2 = n_outer + (i + 1) * segs_r + j
            v3 = n_outer + (i + 1) * segs_r + (j + 1) % segs_r
            faces.append([v1, v0, v2])
            faces.append([v3, v1, v2])

    result = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces))
    result.remove_unreferenced_vertices()
    result.fix_normals()
    result.metadata.update(obj.metadata.copy())
    result.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_thread_{thr_type}"
    for key in ["_gl_verts", "_gl_normals", "_gl_vbo_verts", "_gl_vbo_normals"]:
        result.metadata.pop(key, None)
    return result