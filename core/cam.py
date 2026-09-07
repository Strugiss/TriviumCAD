"""TriviumCAD core - CAM (estratte da triviumcad.py)."""
import math
import numpy as np

# --- CAM: PERCORSI UTENSILE ---
def _compute_adaptive_path(mesh, tool_diameter, stepover, clearance, feed_rate):
    """Versione puramente computazionale di generate_adaptive_path (thread-safe)."""
    if not hasattr(mesh, 'bounds') or mesh.bounds is None:
        return []
    if not hasattr(mesh, 'ray') or not hasattr(mesh.ray, 'intersects_location'):
        return []
    min_bounds, max_bounds = mesh.bounds
    safe_z = max_bounds[2] + clearance
    y_current = min_bounds[1]
    direction_x = 1
    gcode_paths = []
    while y_current <= max_bounds[1]:
        x_points = np.arange(min_bounds[0], max_bounds[0] + stepover, stepover)
        if direction_x == -1:
            x_points = x_points[::-1]
        origins = np.array([[x, y_current, safe_z] for x in x_points])
        vectors = np.tile([0, 0, -1], (len(x_points), 1))
        locations, indices, _ = mesh.ray.intersects_location(origins, vectors, multiple_hits=False)
        path, previous_z = [], safe_z
        for i, x in enumerate(x_points):
            hits = locations[indices == i]
            target = hits[0][2] + tool_diameter / 2 if len(hits) > 0 else previous_z
            path.append([x, y_current, target])
        if len(path) > 1:
            gcode_paths.append({"type": "ext", "pts": path, "s": feed_rate})
        y_current += stepover
        direction_x *= -1
    return gcode_paths

# --- FILETTATURA ---
def _sample_mesh_radius(obj, z, num_rays=16):
    """Campiona il raggio della mesh a una data altezza Z proiettando raggi."""
    bounds = obj.bounds
    cx = (bounds[1][0] + bounds[0][0]) / 2
    cy = (bounds[1][1] + bounds[0][1]) / 2
    radii = []
    for j in range(num_rays):
        theta = 2 * math.pi * j / num_rays
        origin = [cx + 1000 * math.cos(theta), cy + 1000 * math.sin(theta), z]
        direction = [-math.cos(theta), -math.sin(theta), 0.0]
        try:
            loc = obj.ray.intersects_location([origin], [direction])
            if len(loc) > 0:
                d = math.hypot(loc[0][0] - cx, loc[0][1] - cy)
                radii.append(d)
        except Exception:
            # Intenzionale: il singolo raggio puo' non colpire la mesh; se nessun
            # raggio riesce, _sample_mesh_radius ritorna None (fallback del chiamante).
            pass
    if not radii:
        return None
    return max(radii)

def _surface_radius_at(shape_type, params, theta, z, bounds, cx, cy, thr_type):
    """Restituisce il raggio della superficie della forma nativa a (theta, z)."""
    b_min, b_max = bounds
    if shape_type == "cylinder":
        return params.get("raggio", (b_max[0] - b_min[0]) / 2)
    elif shape_type == "sphere":
        R = params.get("raggio", (b_max[0] - b_min[0]) / 2)
        cz = (b_max[2] + b_min[2]) / 2
        dz = z - cz
        if abs(dz) >= R:
            return max(R * 0.05, 0.1)
        return math.sqrt(max(0.01, R * R - dz * dz))
    elif shape_type == "cone":
        r_base = params.get("raggio_base", (b_max[0] - b_min[0]) / 2)
        h = params.get("altezza", b_max[2] - b_min[2])
        if h < 0.001: h = 0.001
        t = (z - b_min[2]) / h
        r_top = r_base * 0.1
        return r_base * (1 - t) + r_top * t
    elif shape_type == "hexagon":
        R = params.get("raggio", (b_max[0] - b_min[0]) / 2)
        apothem = R * 0.8660254037844386
        s = math.pi / 3
        theta_mod = (theta + math.pi / 6) % s
        if theta_mod > s / 2:
            theta_mod = s - theta_mod
        theta_mod = max(theta_mod, 1e-10)
        r = apothem / math.cos(theta_mod)
        return min(r, R * 1.05)
    elif shape_type == "box":
        w = params.get("larghezza", b_max[0] - b_min[0]) / 2
        d = params.get("profondità", b_max[1] - b_min[1]) / 2
        ct = abs(math.cos(theta))
        st = abs(math.sin(theta))
        rx = w / ct if ct > 1e-10 else float('inf')
        ry = d / st if st > 1e-10 else float('inf')
        return min(rx, ry)
    elif shape_type == "hollow_box":
        w = params.get("larghezza", b_max[0] - b_min[0]) / 2
        d = params.get("profondità", b_max[1] - b_min[1]) / 2
        wall = params.get("spessore_muro", 2.5)
        if thr_type == "Interna":
            w = max(w - wall, 0.1)
            d = max(d - wall, 0.1)
        ct = abs(math.cos(theta))
        st = abs(math.sin(theta))
        rx = w / ct if ct > 1e-10 else float('inf')
        ry = d / st if st > 1e-10 else float('inf')
        return min(rx, ry)
    elif shape_type == "collare":
        if thr_type == "Esterna":
            return params.get("raggio_esterno", (b_max[0] - b_min[0]) / 2)
        else:
            return params.get("raggio_interno", max((b_max[0] - b_min[0]) / 2 - 8, 1.0))
    elif shape_type == "arc":
        return params.get("raggio_est", (b_max[0] - b_min[0]) / 2)
    elif shape_type == "donut":
        R = params.get("raggio_magg", (b_max[0] - b_min[0]) / 2)
        r = params.get("raggio_min", (b_max[2] - b_min[2]) / 2)
        cz = (b_max[2] + b_min[2]) / 2
        phi = math.asin(max(-1, min(1, (z - cz) / max(r, 0.01))))
        return max(R + r * math.cos(phi), 0.1)
    return (b_max[0] - b_min[0]) / 2