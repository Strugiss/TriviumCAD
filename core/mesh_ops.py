"""TriviumCAD core - operazioni mesh e factory (estratte da triviumcad.py)."""
import numpy as np
import trimesh
import trimesh.boolean
import trimesh.smoothing
from typing import List, Optional, Dict, Any


# --- UTILITY BOOLEANE ---
def _ensure_volume(mesh):
    """Tenta di rendere una mesh un volume valido per booleane."""
    m = trimesh.Trimesh(vertices=mesh.vertices.copy(), faces=mesh.faces.copy())
    m.metadata.update(mesh.metadata)
    m.fix_normals()
    if not m.is_watertight:
        try:
            trimesh.repair.fill_holes(m)
        except Exception:
            print("[TriviumCAD] _ensure_volume: fill_holes fallito")
    if not m.is_watertight:
        try:
            m.process(validate=True)
        except Exception:
            print("[TriviumCAD] _ensure_volume: process fallito")
    return m

def boolean_safe(meshes: List[trimesh.Trimesh], operation: str) -> trimesh.Trimesh:
    """
    Esegue operazioni booleane in modo sicuro con fallback a metodi alternativi.
    """
    if len(meshes) < 2:
        raise ValueError("Servono almeno 2 mesh per l'operazione booleana")
    
    op_map = {
        "unione": "union",
        "sottrazione": "difference",
        "intersezione": "intersection"
    }
    op_type = op_map.get(operation.lower(), operation.lower())
    
    op_func_map = {
        "union": trimesh.boolean.union,
        "difference": trimesh.boolean.difference,
        "intersection": trimesh.boolean.intersection
    }
    op_func = op_func_map.get(op_type)
    if op_func is None:
        raise ValueError(f"Operazione sconosciuta: {operation}")
    
    engines_to_try = ['manifold', None]
    
    for engine in engines_to_try:
        try:
            return op_func(meshes, engine=engine)
        except Exception as e:
            print(f"[TriviumCAD] boolean_safe engine={engine}: {e}")
            continue
    
    # Riprova con check_volume=False (utile per mesh non watertight come testi incisi)
    for engine in engines_to_try:
        try:
            return op_func(meshes, engine=engine, check_volume=False)
        except Exception as e:
            print(f"[TriviumCAD] boolean_safe engine={engine} no_volume_check: {e}")
            continue
    
    # Fallback: repara mesh e riprova
    fixed = [_ensure_volume(m) for m in meshes]
    for engine in engines_to_try:
        try:
            return op_func(fixed, engine=engine)
        except Exception as e:
            print(f"[TriviumCAD] boolean_safe fallback engine={engine}: {e}")
            continue
    
    # Fallback con check_volume=False
    for engine in engines_to_try:
        try:
            return op_func(fixed, engine=engine, check_volume=False)
        except Exception as e:
            print(f"[TriviumCAD] boolean_safe fallback engine={engine} no_volume_check: {e}")
            continue
    
    # Ultimo fallback: mesh-by-mesh con scipy
    try:
        result = None
        for m in fixed:
            if result is None:
                result = m
                continue
            if op_type == "union":
                result = result.union(m)
            elif op_type == "difference":
                result = result.difference(m)
            elif op_type == "intersection":
                result = result.intersection(m)
        if result is not None and not result.is_empty:
            return result
        raise RuntimeError(f"CSG fallback: {'nessuna mesh' if result is None else 'risultato vuoto'}")
    except RuntimeError:
        raise
    except Exception as e2:
        raise RuntimeError(f"Errore CSG: tutti i motori hanno fallito: {e2}")

def _ray_first_hits(locs, ray_idx, origins):
    """Riduce gli hit del raytracer al PRIMO hit per raggio (ordine per distanza)."""
    if len(locs) == 0:
        return locs, ray_idx
    dist = np.sum((locs - origins[ray_idx]) ** 2, axis=1)
    order = np.argsort(dist, kind='stable')
    first = {}
    for i in order:
        if ray_idx[i] not in first:
            first[ray_idx[i]] = i
    keep = np.array(sorted(first.values()))
    return locs[keep], ray_idx[keep]

# --- FILLET ---
def _compute_fillet(objs, radius):
    results = []
    for idx, obj in enumerate(objs):
        try:
            mesh = obj.copy()
            if len(mesh.vertices) < 3:
                continue
            with np.errstate(divide='ignore', invalid='ignore'):
                n_faces = len(mesh.faces)
                subdivs = 0
                if n_faces < 50:
                    subdivs = min(5, max(3, int(np.ceil(radius * 1.5))))
                elif n_faces < 500:
                    subdivs = min(4, max(2, int(np.ceil(radius))))
                else:
                    subdivs = min(3, max(1, int(np.ceil(radius * 0.5))))
                max_faces = 30000
                estimated = n_faces * (4 ** subdivs)
                while estimated > max_faces and subdivs > 0:
                    subdivs -= 1
                    estimated = n_faces * (4 ** subdivs)
                for _ in range(subdivs):
                    try:
                        mesh = mesh.subdivide()
                    except Exception:
                        break
                if len(mesh.vertices) < 3:
                    continue
                if n_faces < 50:
                    strength = min(0.35, 0.06 + radius * 0.04)
                    smooth_iter = max(5, min(15, int(radius * 2.5)))
                else:
                    strength = min(0.45, 0.1 + radius * 0.06)
                    smooth_iter = max(10, min(40, int(radius * 5.0)))
                for _ in range(3):
                    original = mesh.vertices.copy()
                    trimesh.smoothing.filter_taubin(mesh, lamb=strength, nu=-(strength + 0.04), iterations=smooth_iter)
                    mesh.vertices = original + (mesh.vertices - original)
                    strength *= 0.7
                    smooth_iter = max(3, smooth_iter // 2)
                mesh.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_rounded"
                mesh.metadata["color"] = obj.metadata.get("color", [0.7, 0.7, 0.7, 1.0])
                mesh.metadata["layer"] = obj.metadata.get("layer", "Default")
                mesh.metadata["locked"] = False
                mesh.metadata["visible"] = True
                mesh.metadata["shape_type"] = "fillet"
                mesh.metadata["params"] = {}
                mesh.metadata.pop("assembly", None)
                for key in ["_gl_verts", "_gl_normals", "_gl_vbo_verts", "_gl_vbo_normals"]:
                    mesh.metadata.pop(key, None)
                mesh.fix_normals()
            results.append((idx, mesh))
        except Exception:
            pass
    return results

# --- FACTORY MESH ---
def validate_and_place_mesh(mesh: Optional[trimesh.Trimesh]) -> trimesh.Trimesh:
    from core.primitives import _generate_blender_box
    with np.errstate(divide='ignore', invalid='ignore'):
        try:
            if mesh is None or len(mesh.vertices) < 3 or len(mesh.faces) < 1:
                return _generate_blender_box(10, 10, 10)
            
            mesh.process(validate=True)
            mesh.fix_normals()
            
            if hasattr(mesh, 'bounds') and mesh.bounds is not None and len(mesh.bounds) == 2:
                z_min = mesh.bounds[0][2]
                if abs(z_min) > 1e-6:
                    mesh.apply_translation([0, 0, -z_min])
            
            return mesh
        except Exception as e:
            print(f"Errore validazione mesh: {e}")
            return _generate_blender_box(10, 10, 10)

def create_mesh(shape_type: str, params: Dict[str, Any]) -> trimesh.Trimesh:
    from core.primitives import _generate_blender_box, _generate_blender_cylinder, _generate_blender_sphere, _generate_blender_cone, _generate_blender_hexagon, _generate_blender_spiral, _generate_blender_arc, _generate_blender_hollow_box, _generate_blender_collare, _generate_blender_donut
    with np.errstate(divide='ignore', invalid='ignore'):
        try:
            if shape_type == "box":
                mesh = _generate_blender_box(
                    float(params.get("larghezza", 20)), 
                    float(params.get("altezza", 20)), 
                    float(params.get("profondità", 20))
                )
            elif shape_type == "cylinder":
                mesh = _generate_blender_cylinder(
                    float(params.get("raggio", 10)), 
                    float(params.get("altezza", 30)), 
                    int(params.get("sezioni", 64))
                )
            elif shape_type == "sphere":
                mesh = _generate_blender_sphere(
                    float(params.get("raggio", 15)), 
                    int(params.get("suddivisioni", 4))
                )
            elif shape_type == "cone":
                mesh = _generate_blender_cone(
                    float(params.get("raggio_base", 12)), 
                    float(params.get("altezza", 30)), 
                    int(params.get("sezioni", 64))
                )
            elif shape_type == "hexagon":
                mesh = _generate_blender_hexagon(float(params.get("raggio", 10)), float(params.get("altezza", 30)))
            elif shape_type == "spiral":
                mesh = _generate_blender_spiral(float(params.get("raggio", 15)), float(params.get("altezza", 30)), int(params.get("giri", 4)), float(params.get("spessore", 3)))
            elif shape_type == "arc":
                mesh = _generate_blender_arc(float(params.get("raggio_est", 20)), float(params.get("raggio_int", 12)), float(params.get("apertura", 90)), float(params.get("altezza", 8)))
            elif shape_type == "hollow_box":
                mesh = _generate_blender_hollow_box(float(params.get("larghezza", 30)), float(params.get("altezza", 20)), float(params.get("profondità", 20)), float(params.get("spessore_muro", 2.5)))
            elif shape_type == "collare":
                mesh = _generate_blender_collare(float(params.get("raggio_esterno", 20)), float(params.get("raggio_interno", 12)), float(params.get("altezza", 8)))
            elif shape_type == "donut":
                R = float(params.get("raggio_magg", 15))
                r = float(params.get("raggio_min", 5))
                if R <= r + 0.1:
                    R = r + 0.2
                mesh = _generate_blender_donut(R, r, int(params.get("sezioni", 64)), int(params.get("sezioni", 64)) // 2)
            else:
                mesh = _generate_blender_box(10, 10, 10)
            
            return validate_and_place_mesh(mesh)
        except Exception as e:
            print(f"Errore creazione mesh: {e}")
            return validate_and_place_mesh(_generate_blender_box(10, 10, 10))