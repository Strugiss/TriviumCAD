"""TriviumCAD core - scena e undo manager (estratte da triviumcad.py)."""
import math
import time
import numpy as np
import trimesh
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from core.constants import NEUTRAL_COLORS
from core.mesh_ops import create_mesh, boolean_safe, validate_and_place_mesh, _ensure_volume
from core.thread import _generate_thread_on_shape

# === UNDO MANAGER ===
class _UndoManager:
    """Gestisce stack undo/redo per Scene."""
    def __init__(self, scene: 'Scene') -> None:
        self.scene = scene
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []

    def push(self) -> None:
        try:
            obj_copy = []
            for idx, obj in enumerate(self.scene.objects):
                try:
                    if hasattr(obj, 'copy'):
                        obj_copy.append(obj.copy())
                except Exception as e:
                    print(f"ERRORE undo: oggetto {idx} non copiabile: {e}")
                    obj_copy.append(obj)
            selected_idx = [i for i, obj in enumerate(self.scene.objects) if obj in self.scene.selected_objects]
            self.undo_stack.append({"obj": obj_copy, "selected_idx": selected_idx})
            if len(self.undo_stack) > 50:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
        except Exception as e:
            print(f"Errore inserimento stack undo: {e}")

    def start(self) -> None:
        self.push()

    def end(self) -> None:
        pass

    def cancel(self) -> None:
        pass

    def undo(self) -> bool:
        if self.undo_stack:
            state = self.undo_stack.pop()
            redo_state = {
                "obj": [],
                "selected_idx": [i for i, obj in enumerate(self.scene.objects) if obj in self.scene.selected_objects]
            }
            for obj in self.scene.objects:
                try:
                    if hasattr(obj, 'copy'):
                        redo_state["obj"].append(obj.copy())
                except Exception:
                    print("ERRORE: impossibile copiare oggetto per undo_stack (redo_state)")
                    continue
            if redo_state["obj"]:
                self.redo_stack.append(redo_state)
            self.scene.objects = state["obj"]
            self.scene.selected_objects = [self.scene.objects[i] for i in state.get("selected_idx", []) if i < len(self.scene.objects)]
            self.scene._needs_spatial_rebuild = True
            self.scene._notify(f"Annullato (oggetti: {len(self.scene.objects)}, selezionati: {len(self.scene.selected_objects)})")
            return True
        return False

    def redo(self) -> bool:
        if self.redo_stack:
            state = self.redo_stack.pop()
            undo_state = {
                "obj": [],
                "selected_idx": [i for i, obj in enumerate(self.scene.objects) if obj in self.scene.selected_objects]
            }
            for obj in self.scene.objects:
                try:
                    if hasattr(obj, 'copy'):
                        undo_state["obj"].append(obj.copy())
                except Exception:
                    print("ERRORE: impossibile copiare oggetto per undo_state (redo)")
                    continue
            if undo_state["obj"]:
                self.undo_stack.append(undo_state)
            self.scene.objects = state["obj"]
            self.scene.selected_objects = [self.scene.objects[i] for i in state.get("selected_idx", []) if i < len(self.scene.objects)]
            self.scene._needs_spatial_rebuild = True
            self.scene._notify(f"Ripristinato (oggetti: {len(self.scene.objects)}, selezionati: {len(self.scene.selected_objects)})")
            return True
        return False

# === CLASSE SCENE ===
class Scene:
    def __init__(self) -> None:
        self.objects: List[trimesh.Trimesh] = []
        self.selected_objects: List[trimesh.Trimesh] = []
        self.undo_mgr = _UndoManager(self)
        self.color_idx: int = 0
        self.sketch_entities: List[Dict[str, Any]] = []
        self.dimensions = []
        self.angle_dims = []
        self.snap_grid: bool = True
        self.scale_mode: str = "Disattivato"
        self.magnetic_snap: bool = True
        self.layers: Dict[str, Dict[str, Any]] = {"Default": {"visible": True, "locked": False, "color": [0.6, 0.75, 0.9, 1.0]}}
        self.active_layer: str = "Default"
        self.assemblies: Dict[str, Dict[str, Any]] = {}
        self.operation_in_progress = False
        self._callback_notify = None
        self._spatial_index = None
        self._needs_spatial_rebuild = True
        self.measurement_mode = None
        self.measurement_points = []
        self.active_tool = "selection"
        self.mirror_axis = "x"
        self.fillet_radius = 1.0
        self.offset_distance = 1.0
        self.revolve_angle = 360.0
        self.pattern_count = 3
        self.pattern_distance = 10.0
        self.pattern_direction = "x"
        self.smooth_iterations = 1
        self.subdivide_iterations = 1
        self.decimate_target = 1000
        self.hole_diameter = 5.0
        self.hole_depth = 10.0
        self.cut_axis = "z"
        self.cut_position = 0.0
        self.deformation_type = "bend"
        self.deformation_intensity = 0.5
        self.tool_diameter = 3.0
        self.stepover = 0.5
        self.feed_rate = 1000.0
        self.plunge_rate = 500.0
        self.depth_per_pass = 2.0
        self.toolpath_strategy = "adaptive"
        self.toolpath_direction = "climb"
        self.toolpath_depth = 0.0
        self.toolpath_offset = 0.0
        self.toolpath_feedrate = 1000.0
        self.toolpath_plunge_feedrate = 500.0
        self.toolpath_spindle_speed = 12000
        self.toolpath_coolant = "flood"
        self.toolpath_tool_number = 1
        self.toolpath_tool_diameter = 3.0
        self.toolpath_tool_length = 50.0
        self.toolpath_tool_flutes = 2
        self.toolpath_tool_material = "carbide"
        self.toolpath_tool_coating = "tialn"
        self.toolpath_tool_cutting_diameter = 3.0
        self.toolpath_tool_cutting_length = 20.0
        self.toolpath_tool_shank_diameter = 6.0
        self.toolpath_tool_shank_length = 30.0
        self.toolpath_tool_corner_radius = 0.0
        self.toolpath_tool_tip_angle = 0.0
        self.toolpath_tool_tip_diameter = 0.0
        self.toolpath_tool_tip_length = 0.0
        self.toolpath_tool_tip_radius = 0.0
        self.gcode_paths = []
        self.clipboard_objects = []

    @property
    def grid_step(self) -> float:
        return 0.0 if self.scale_mode == "Disattivato" else float(self.scale_mode.replace(" mm", ""))
    
    @property
    def has_selection(self) -> bool:
        return len(self.selected_objects) > 0
    
    @property
    def single_selection(self) -> Optional[trimesh.Trimesh]:
        return self.selected_objects[0] if self.selected_objects else None
    
    def clear_selection(self) -> None:
        self.selected_objects = []
    
    def add_to_selection(self, obj: trimesh.Trimesh) -> None:
        if obj.metadata.get("locked", False):
            return
        if obj not in self.selected_objects:
            self.selected_objects.append(obj)
            self._needs_spatial_rebuild = True
    
    def remove_from_selection(self, obj: trimesh.Trimesh) -> None:
        if obj in self.selected_objects:
            self.selected_objects.remove(obj)
    
    def toggle_selection(self, obj: trimesh.Trimesh) -> None:
        if obj in self.selected_objects:
            self.remove_from_selection(obj)
        else:
            self.add_to_selection(obj)
    
    def add_shape(self, shape_type: str, params: Dict[str, Any], name: Optional[str] = None) -> trimesh.Trimesh:
        mesh = create_mesh(shape_type, params)
        color = NEUTRAL_COLORS[self.color_idx % len(NEUTRAL_COLORS)]
        self.color_idx += 1
        
        mesh.metadata.update({
            "layer": self.active_layer,
            "color": color,
            "name": name or f"{shape_type}_{self.color_idx}",
            "params": params.copy(),
            "shape_type": shape_type,
            "assembly": None,
            "visible": True,
            "locked": False
        })
        
        self._undo_push()
        self.objects.append(mesh)
        self._needs_spatial_rebuild = True
        return mesh
    
    def _rebuild_spatial_index(self):
        try:
            if len(self.objects) <= 100:
                self._spatial_index = None
                return
            
            from scipy.spatial import cKDTree
            
            centers = []
            for obj in self.objects:
                if hasattr(obj, 'bounds') and obj.bounds is not None and len(obj.bounds) == 2:
                    center = (obj.bounds[0] + obj.bounds[1]) / 2
                    centers.append(center)
                else:
                    if hasattr(obj, 'vertices') and len(obj.vertices) > 0:
                        center = np.mean(obj.vertices, axis=0)
                        centers.append(center)
                    else:
                        centers.append([0, 0, 0])
            
            self._spatial_index = cKDTree(centers)
        except ImportError:
            # Intenzionale: scipy opzionale -> indice spaziale disattivato (fallback su scansione lineare)
            self._spatial_index = None
        except Exception as e:
            print(f"Errore nella creazione dell'octree: {e}")
            self._spatial_index = None
    
    def _get_nearby_objects(self, point, radius=10.0):
        if self._spatial_index is None or len(self.objects) == 0:
            return self.objects
        
        indices = self._spatial_index.query_ball_point(point, radius)
        return [self.objects[i] for i in indices]
    
    def _undo_push(self) -> None:
        self.undo_mgr.push()

    def start_operation(self) -> None:
        self.operation_in_progress = True
        self.undo_mgr.start()

    def end_operation(self) -> None:
        # Guardia idempotente: una seconda finalizzazione (es. end + cancel
        # dalla stessa operazione) non deve toccare lo stato undo.
        if not self.operation_in_progress:
            return
        self.operation_in_progress = False
        self.undo_mgr.end()

    def cancel_operation(self) -> None:
        # Guardia idempotente: se l'operazione e' gia' stata finalizzata
        # (end_operation), il cancel successivo e' un no-op.
        if not self.operation_in_progress:
            return
        self.operation_in_progress = False
        self.undo_mgr.cancel()

    def undo(self) -> bool:
        return self.undo_mgr.undo()

    def redo(self) -> bool:
        return self.undo_mgr.redo()

    def delete(self) -> bool:
        if not self.selected_objects:
            return False
        
        self.start_operation()
        try:
            deleted = len(self.selected_objects)
            names = [o.metadata.get("name", "?") for o in self.selected_objects]
            for obj in self.selected_objects[:]:
                if obj in self.objects:
                    self.objects.remove(obj)
            
            self.selected_objects = []
            self._needs_spatial_rebuild = True
            print(f"[TriviumCAD] Eliminati: {', '.join(names)}")
            self._notify(f"Eliminati {deleted} oggetti")
            return True
        finally:
            self.end_operation()
    
    def duplicate(self) -> None:
        if not self.selected_objects:
            self._notify("Nessun oggetto selezionato")
            return
        
        self.start_operation()
        try:
            names = []
            for obj in self.selected_objects[:]:
                copy_obj = obj.copy()
                copy_obj.apply_translation([20, 0, 0])
                name = copy_obj.metadata.get("name", "Object") + "_copy"
                copy_obj.metadata["name"] = name
                names.append(name)
                
                self.objects.append(copy_obj)
                self.selected_objects.append(copy_obj)
            
            self._needs_spatial_rebuild = True
            print(f"[TriviumCAD] Duplicati: {', '.join(names)}")
            self._notify(f"Duplicati {len(self.selected_objects)} oggetti")
        except Exception as e:
            print(f"[TriviumCAD] Errore duplicazione: {e}")
            self._notify("Errore nella duplicazione")
        finally:
            self.end_operation()
    
    def align_z(self) -> bool:
        if not self.selected_objects:
            self._notify("Nessun oggetto selezionato")
            return False
        
        self.start_operation()
        try:
            for obj in self.selected_objects:
                if hasattr(obj, 'bounds') and obj.bounds is not None and len(obj.bounds) == 2:
                    z_min = obj.bounds[0][2]
                    if abs(z_min) > 1e-3:
                        obj.apply_translation([0, 0, -z_min])
            
            self._notify(f"Allineati {len(self.selected_objects)} oggetti a Z=0")
            return True
        except Exception as e:
            print(f"Errore allineamento asse Z: {e}")
            return False
        finally:
            self.end_operation()
    
    def ungroup_object(self) -> None:
        if not self.selected_objects:
            return
        
        self.start_operation()
        try:
            for obj in self.selected_objects:
                if obj.metadata.get("assembly"):
                    obj.metadata["assembly"] = None
            
            self._notify(f"Separati {len(self.selected_objects)} oggetti")
        finally:
            self.end_operation()
    
    def group_selected(self) -> Optional[str]:
        if len(self.selected_objects) < 2:
            self._notify("Servono almeno 2 oggetti per creare un assembly")
            return None
        
        self.start_operation()
        
        try:
            assembly_id = f"asm_{int(time.time())}"
            
            for obj in self.selected_objects:
                obj.metadata["assembly"] = assembly_id
            
            self.assemblies[assembly_id] = {
                "objects": self.selected_objects.copy(),
                "name": f"Assembly {len(self.assemblies) + 1}"
            }
            
            self._notify(f"Creato assembly con {len(self.selected_objects)} oggetti")
            return assembly_id
        finally:
            self.end_operation()
    
    def explode_assembly(self, assembly_name: str) -> None:
        if assembly_name not in self.assemblies:
            return
        
        self.start_operation()
        try:
            for obj in self.assemblies[assembly_name]["objects"]:
                obj.metadata["assembly"] = None
            
            del self.assemblies[assembly_name]
            
            self._notify("Assembly esploso")
        finally:
            self.end_operation()
    
    def import_file(self, file_path: str) -> Optional[trimesh.Trimesh]:
        try:
            mesh = trimesh.load(file_path, force='mesh')
            if isinstance(mesh, trimesh.Scene):
                mesh = mesh.dump(concatenate=True)
                if not isinstance(mesh, trimesh.Trimesh):
                    for m in mesh:
                        if isinstance(m, trimesh.Trimesh):
                            mesh = m
                            break
            
            if hasattr(mesh, 'extents') and np.any(np.array(mesh.extents) < 1):
                mesh.apply_scale(1000.0)
            
            mesh = validate_and_place_mesh(mesh)
            mesh.metadata.update({
                "layer": self.active_layer,
                "color": NEUTRAL_COLORS[self.color_idx % len(NEUTRAL_COLORS)],
                "name": Path(file_path).stem,
                "shape_type": "imported",
                "params": {},
                "assembly": None
            })
            
            self.color_idx += 1
            self._undo_push()
            self.objects.append(mesh)
            self._needs_spatial_rebuild = True
            self._notify(f"Importato: {Path(file_path).name}")
            return mesh
        except Exception as e:
            self._notify(f"Errore importazione: {e}")
            return None
    
    def export_multi(self, file_path: str, format: str) -> Tuple[bool, str]:
        try:
            visible_objects = [
                obj for obj in self.objects 
                if self.layers.get(obj.metadata.get("layer", "Default"), {}).get("visible", True)
            ]
            
            if not visible_objects:
                return False, "Nessun oggetto visibile da esportare"
            
            scene = trimesh.Scene(visible_objects)
            
            try:
                scene.export(file_path, file_type=format.lower())
                self._notify(f"Esportato in formato {format}")
                return True, f"Esportazione {format} completata"
            except Exception as e:
                return False, f"Errore esportazione: {str(e)}"
        except Exception as e:
            print(f"Errore esportazione: {e}")
            return False, f"Errore esportazione: {str(e)}"
    
    def boolean_op(self, operation: str) -> bool:
        if len(self.selected_objects) < 2:
            self._notify("Necessari almeno due oggetti selezionati per l'operazione booleana")
            return False
        
        self.start_operation()
        try:
            result = boolean_safe(self.selected_objects, operation)
            
            if result is None or result.is_empty:
                self._notify("Risultato dell'operazione vuoto")
                return False
                
            first_obj = self.selected_objects[0]
            # Pulisci facce degeneri
            result.update_faces(result.nondegenerate_faces(height=1e-4))
            result.remove_unreferenced_vertices()
            result.fix_normals()
            result.metadata.update(first_obj.metadata.copy())
            result.metadata.pop("_gl_verts", None)
            result.metadata.pop("_gl_normals", None)
            result.metadata["name"] = f"{first_obj.metadata.get('name', 'Object')}_{operation}"
            
            for obj in self.selected_objects:
                if obj in self.objects:
                    self.objects.remove(obj)
            
            self.objects.append(result)
            self.selected_objects = [result]
            self._needs_spatial_rebuild = True

            self._notify(f"Operazione {operation} eseguita su {len(self.selected_objects)} oggetti")
            return True
        except Exception as e:
            self._notify(f"Fallimento operazione booleana: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def boolean_union(self) -> bool:
        return self.boolean_op("unione")
    
    def boolean_difference(self) -> bool:
        return self.boolean_op("sottrazione")
    
    def boolean_intersection(self) -> bool:
        return self.boolean_op("intersezione")
    
    def _shell_single(self, obj, wall, base_z) -> trimesh.Trimesh:
        st = obj.metadata.get("shape_type", "")
        center = (obj.bounds[0] + obj.bounds[1]) / 2 if obj.bounds is not None else np.zeros(3)
        half = (obj.bounds[1] - obj.bounds[0]) / 2 if obj.bounds is not None else np.ones(3)

        if st in ("box", "hollow_box"):
            inner = trimesh.creation.box(extents=[
                max(0.1, half[0] * 2 - wall * 2),
                max(0.1, half[1] * 2 - wall * 2),
                max(0.1, half[2] * 2 - wall * 2)])
            inner.apply_translation(center)
        elif st == "cylinder":
            inner = trimesh.creation.cylinder(
                radius=max(0.1, half[0] - wall),
                height=max(0.1, half[2] * 2 - wall * 2),
                sections=64)
            inner.apply_translation(center)
        elif st == "sphere":
            inner = trimesh.creation.icosphere(
                subdivisions=3, radius=max(0.1, half[0] - wall))
            inner.apply_translation(center)
        else:
            obj = _ensure_volume(obj)
            if obj is None or obj.is_empty or not obj.is_watertight:
                return None
            verts = np.asarray(obj.vertices, dtype=np.float64)
            faces = np.asarray(obj.faces, dtype=np.uint32)
            vn = np.asarray(obj.vertex_normals, dtype=np.float64)
            inner_verts = verts - vn * wall
            inner = trimesh.Trimesh(vertices=inner_verts, faces=faces.copy(), process=False)
            inner.remove_unreferenced_vertices()
            inner.update_faces(inner.nondegenerate_faces())
            inner = _ensure_volume(inner)
            if inner is None or inner.is_empty or not inner.is_watertight:
                return None

        result = boolean_safe([obj, inner], "difference")
        if result is None or result.is_empty:
            return None

        cut_z = base_z + wall + 0.5
        sliced = trimesh.intersections.slice_mesh_plane(
            result, [0, 0, 1], [0, 0, cut_z], cap=True)
        if sliced is not None and not sliced.is_empty:
            result = sliced
        result.fix_normals()

        if st in ("box", "hollow_box", "cylinder"):
            verts = result.vertices
            faces = result.faces
            at_cut = np.all(np.abs(verts[faces][:, :, 2] - cut_z) < 0.01, axis=1)
            if at_cut.any() and np.any(at_cut):
                centroids = verts[faces[at_cut]].mean(axis=1)
                if st in ("box", "hollow_box"):
                    ix = max(0.1, half[0] - wall)
                    iy = max(0.1, half[1] - wall)
                    is_cavity = (np.abs(centroids[:, 0] - center[0]) <= ix) & (np.abs(centroids[:, 1] - center[1]) <= iy)
                else:
                    ir = max(0.1, half[0] - wall)
                    d2 = (centroids[:, 0] - center[0])**2 + (centroids[:, 1] - center[1])**2
                    is_cavity = d2 <= ir * ir
                keep = np.ones(len(faces), dtype=bool)
                keep[at_cut] = ~is_cavity
                result.update_faces(keep)
                result.remove_unreferenced_vertices()
                if result.is_empty:
                    return None

        result.merge_vertices()
        return result

    def shell(self) -> bool:
        if len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per creare il guscio")
            return False
        
        self.start_operation()
        try:
            obj = self.selected_objects[0]
            wall = 2.0
            base_z = obj.bounds[0][2]
            
            components = trimesh.graph.split(obj, only_watertight=False)
            if len(components) == 0:
                self._notify("Nessun componente valido")
                return False
            
            results = []
            for comp in components:
                comp.metadata.update(obj.metadata)
                r = self._shell_single(comp, wall, base_z)
                if r is not None and not r.is_empty:
                    results.append(r)
            
            if not results:
                self._notify("Risultato dell'operazione vuoto")
                return False
            
            result = trimesh.util.concatenate(results) if len(results) > 1 else results[0]
            
            result.metadata.update(obj.metadata.copy())
            result.metadata.pop("_gl_verts", None)
            result.metadata.pop("_gl_normals", None)
            result.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_shell"
            
            if obj in self.objects:
                self.objects.remove(obj)
            
            self.objects.append(result)
            self.selected_objects = [result]
            self._needs_spatial_rebuild = True

            self._notify("Guscio creato con successo")
            return True
        except Exception as e:
            self._notify(f"Errore nella creazione del guscio: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def mirror(self, axis: str = "x") -> bool:
        if not self.selected_objects:
            self._notify("Nessun oggetto selezionato")
            return False
        
        self.start_operation()
        try:
            for obj in self.selected_objects:
                mirror_obj = obj.copy()
                
                if axis.lower() == "x":
                    mirror_matrix = np.array([[-1, 0, 0, 0],
                                              [0, 1, 0, 0],
                                              [0, 0, 1, 0],
                                              [0, 0, 0, 1]])
                elif axis.lower() == "y":
                    mirror_matrix = np.array([[1, 0, 0, 0],
                                              [0, -1, 0, 0],
                                              [0, 0, 1, 0],
                                              [0, 0, 0, 1]])
                elif axis.lower() == "z":
                    mirror_matrix = np.array([[1, 0, 0, 0],
                                              [0, 1, 0, 0],
                                              [0, 0, -1, 0],
                                              [0, 0, 0, 1]])
                else:
                    self._notify("Asse non valido per la simmetria")
                    return False
                
                mirror_obj.apply_transform(mirror_matrix)
                
                mirror_obj.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_mirror_{axis}"
                self.objects.append(mirror_obj)

            self._notify(f"Simmetria creata rispetto all'asse {axis.upper()}")
            return True
        except Exception as e:
            self._notify(f"Errore nella simmetria: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def fillet(self, radius: float = 1.0) -> bool:
        return self.fillet_selected(radius)

    def chamfer(self, distance: float = 1.0) -> bool:
        if not self.selected_objects:
            return False
        self.start_operation()
        try:
            new_selection = []
            for i, obj in enumerate(self.selected_objects):
                mesh = obj.copy()
                subdivs = min(3, max(1, int(np.ceil(distance))))
                for _ in range(subdivs):
                    try:
                        mesh = mesh.subdivide()
                    except Exception:
                        break
                if len(mesh.vertices) < 3:
                    new_selection.append(obj)
                    continue
                angle_threshold = np.radians(max(15, 55 - distance * 5))
                sharp = mesh.face_adjacency_angles > angle_threshold
                if not sharp.any():
                    new_selection.append(obj)
                    continue
                edge_verts = np.unique(mesh.face_adjacency_edges[sharp].flatten())
                verts = np.array(mesh.vertices, dtype=np.float64)
                norms = trimesh.geometry.mean_vertex_normals(len(verts), mesh.faces, mesh.face_normals)
                norms = norms / (np.linalg.norm(norms, axis=1, keepdims=True) + 1e-8)
                displacement = np.zeros_like(verts)
                displacement[edge_verts] = norms[edge_verts] * distance
                mesh.vertices[:] = verts - displacement
                mesh.metadata.update(obj.metadata.copy())
                for key in ["_gl_verts", "_gl_normals", "_gl_vbo_verts", "_gl_vbo_normals"]:
                    mesh.metadata.pop(key, None)
                mesh.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_cimatura"
                mesh.fix_normals()
                idx = self.objects.index(obj)
                self.objects[idx] = mesh
                new_selection.append(mesh)
            self.selected_objects = new_selection
            self._notify(f"Cimatura applicata con distanza {distance}mm")
            return True
        except Exception as e:
            self._notify(f"Errore cimatura: {e}")
            return False
        finally:
            self.cancel_operation()

    def offset(self, distance: float = 1.0) -> bool:
        if not self.selected_objects:
            return False
        self.start_operation()
        try:
            for obj in self.selected_objects:
                verts = np.array(obj.vertices, dtype=np.float64)
                norms = trimesh.geometry.mean_vertex_normals(len(verts), obj.faces, obj.face_normals)
                norms = norms / (np.linalg.norm(norms, axis=1, keepdims=True) + 1e-8)
                obj.vertices[:] = verts + norms * distance
            self._notify(f"Offset applicato con distanza {distance}mm")
            return True
        except Exception as e:
            self._notify(f"Errore offset: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def _profile_from_selection(self) -> Optional[np.ndarray]:
        if self.sketch_entities:
            for e in self.sketch_entities:
                if 'polygon' in e:
                    poly = e['polygon']
                    if hasattr(poly, 'exterior'):
                        pts = np.array(poly.exterior.coords)[:-1]
                        return pts
            return None
        if self.selected_objects:
            obj = self.selected_objects[0]
            verts_2d = np.array(obj.vertices)[:, :2]
            from scipy.spatial import ConvexHull
            hull = ConvexHull(verts_2d)
            return verts_2d[hull.vertices]
        return None

    def revolve(self, angle: float = 360.0) -> bool:
        self.start_operation()
        try:
            profile = self._profile_from_selection()
            if profile is None:
                profile = np.array([
                    [2, 0], [2, 5], [6, 5], [6, 8], [3, 8], [3, 12],
                    [7, 12], [7, 15], [0, 15], [0, 12], [2, 12], [2, 8],
                    [0, 8], [0, 5], [2, 5]
                ], dtype=np.float32)
            angle_rad = math.radians(angle)
            n_sections = max(8, int(abs(angle) / 5))
            mesh = trimesh.creation.revolve(profile, angle=angle_rad, sections=n_sections)
            mesh.fix_normals()
            mesh.metadata.update({
                "layer": self.active_layer,
                "color": NEUTRAL_COLORS[self.color_idx % len(NEUTRAL_COLORS)],
                "name": f"rivoluzione_{self.color_idx}",
                "shape_type": "revolved",
                "params": {"angolo": angle},
                "assembly": None
            })
            self.color_idx += 1
            self.objects.append(mesh)
            self.sketch_entities = []
            self._needs_spatial_rebuild = True
            self._notify(f"Rivoluzione creata con angolo {angle}°")
            return True
        except Exception as e:
            self._notify(f"Errore nella rivoluzione: {e}")
            return False
        finally:
            self.end_operation()
    
    def _sample_polygon(self, poly, n_pts: int = 64) -> np.ndarray:
        if hasattr(poly, 'exterior'):
            coords = np.array(poly.exterior.coords)[:-1]
        else:
            coords = np.array(poly)
        if len(coords) < 3:
            return np.zeros((n_pts, 2))
        closed = np.vstack([coords, coords[0:1]])
        lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
        total = lengths.sum()
        if total < 1e-8:
            return np.zeros((n_pts, 2))
        cumlen = np.insert(np.cumsum(lengths), 0, 0)
        samples = np.linspace(0, total, n_pts, endpoint=False)
        result = np.zeros((n_pts, 2))
        j = 0
        for i, s in enumerate(samples):
            while j < len(closed) - 2 and cumlen[j + 1] < s:
                j += 1
            t = (s - cumlen[j]) / (cumlen[j + 1] - cumlen[j] + 1e-10)
            result[i] = closed[j] + t * (closed[j + 1] - closed[j])
        return result

    def _profiles_2d(self) -> List[np.ndarray]:
        profili = []
        for e in self.sketch_entities:
            if 'polygon' in e:
                profili.append(self._sample_polygon(e['polygon']))
        if len(profili) >= 2:
            return profili[:2]
        if len(self.selected_objects) >= 2:
            objs = self.selected_objects[:2]
            verts1 = np.array(objs[0].vertices)[:, :2]
            verts2 = np.array(objs[1].vertices)[:, :2]
            from scipy.spatial import ConvexHull
            h1 = ConvexHull(verts1)
            h2 = ConvexHull(verts2)
            return [verts1[h1.vertices], verts2[h2.vertices]]
        return []

    def loft(self) -> bool:
        self.start_operation()
        try:
            profili = self._profiles_2d()
            if len(profili) < 2:
                profili = [
                    self._sample_polygon(np.array([[0,0],[5,0],[5,1],[0,1]])),
                    self._sample_polygon(np.array([[0,10],[8,10],[8,12],[0,12]])),
                ]
            n_pts = min(len(profili[0]), len(profili[1]))
            p1 = profili[0][:n_pts]
            p2 = profili[1][:n_pts]
            if p1.shape[1] == 2:
                p1 = np.column_stack([p1, np.zeros(n_pts)])
            if p2.shape[1] == 2:
                p2 = np.column_stack([p2, np.full(n_pts, 10.0)])
            n_slices = 20
            all_verts = []
            for i in range(n_slices):
                t = i / (n_slices - 1)
                v = p1 * (1 - t) + p2 * t
                all_verts.append(v)
            combined_verts = np.vstack(all_verts)
            faces = []
            for i in range(n_slices - 1):
                for j in range(n_pts):
                    jn = (j + 1) % n_pts
                    a = i * n_pts + j
                    b = i * n_pts + jn
                    c = (i + 1) * n_pts + j
                    d = (i + 1) * n_pts + jn
                    faces.append([a, c, b])
                    faces.append([b, c, d])
            mesh = trimesh.Trimesh(vertices=combined_verts, faces=np.array(faces))
            mesh.fix_normals()
            mesh.metadata.update({
                "layer": self.active_layer,
                "color": NEUTRAL_COLORS[self.color_idx % len(NEUTRAL_COLORS)],
                "name": f"loft_{self.color_idx}",
                "shape_type": "lofted",
                "params": {},
                "assembly": None
            })
            self.color_idx += 1
            self.objects.append(mesh)
            self.sketch_entities = []
            self._needs_spatial_rebuild = True
            self._notify(f"Loft creato con 2 profili")
            return True
        except Exception as e:
            self._notify(f"Errore nel loft: {e}")
            return False
        finally:
            self.end_operation()
    
    def _get_sweep_profile(self):
        from shapely.geometry import Polygon
        for e in self.sketch_entities:
            if 'polygon' in e:
                return e['polygon']
        if self.selected_objects:
            obj = self.selected_objects[0]
            verts_2d = np.array(obj.vertices)[:, :2]
            from scipy.spatial import ConvexHull
            hull = ConvexHull(verts_2d)
            hull_pts = verts_2d[hull.vertices]
            from shapely.geometry import Polygon
            return Polygon(hull_pts)
        return None

    def _get_sweep_path(self) -> Optional[np.ndarray]:
        for e in self.sketch_entities:
            if 'path' in e:
                return np.array(e['path'])
        return None

    def sweep(self) -> bool:
        self.start_operation()
        try:
            poly = self._get_sweep_profile()
            if poly is None:
                from shapely.geometry import Polygon as SPolygon
                poly = SPolygon([(-2,-2),(2,-2),(2,2),(-2,2),(-2,-2)])
            path = self._get_sweep_path()
            if path is None or len(path) < 2:
                n_pts = 64
                t_vals = np.linspace(0, 1, n_pts)
                path = np.zeros((n_pts, 3))
                for i, t in enumerate(t_vals):
                    theta = t * 4 * np.pi
                    path[i] = [15 * math.cos(theta), 15 * math.sin(theta), t * 20]
            mesh = trimesh.creation.sweep_polygon(poly, path, cap=True)
            mesh.fix_normals()
            mesh.metadata.update({
                "layer": self.active_layer,
                "color": NEUTRAL_COLORS[self.color_idx % len(NEUTRAL_COLORS)],
                "name": f"sweep_{self.color_idx}",
                "shape_type": "swept",
                "params": {},
                "assembly": None
            })
            self.color_idx += 1
            self.objects.append(mesh)
            self.sketch_entities = []
            self._needs_spatial_rebuild = True
            self._notify("Sweep creato con profilo e tracciato")
            return True
        except Exception as e:
            self._notify(f"Errore nello sweep: {e}")
            return False
        finally:
            self.end_operation()
    
    def linear_pattern(self, count: int = 3, distance: float = 10.0, direction: str = 'x') -> bool:
        if not self.selected_objects:
            self._notify("Seleziona almeno un oggetto per il pattern")
            return False
        
        self.start_operation()
        try:
            direction_vec = {
                'x': [distance, 0, 0],
                'y': [0, distance, 0],
                'z': [0, 0, distance]
            }.get(direction, [distance, 0, 0])
            
            for i in range(1, count):
                for obj in self.selected_objects:
                    copy_obj = obj.copy()
                    copy_obj.apply_translation([d * i for d in direction_vec])
                    copy_obj.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_pattern_{i}"
                    self.objects.append(copy_obj)

            self._notify(f"Pattern lineare creato ({count} elementi)")
            return True
        except Exception as e:
            self._notify(f"Errore nel pattern lineare: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def circular_pattern(self, count: int = 3, radius: float = 10.0, axis: str = 'z') -> bool:
        if not self.selected_objects:
            self._notify("Seleziona almeno un oggetto per il pattern")
            return False
        
        self.start_operation()
        try:
            axis_vec = {
                'x': [1, 0, 0],
                'y': [0, 1, 0],
                'z': [0, 0, 1]
            }.get(axis, [0, 0, 1])
            
            for i in range(1, count):
                angle = 2 * math.pi * i / count
                for obj in self.selected_objects:
                    copy_obj = obj.copy()
                    
                    all_vertices = np.asarray(obj.vertices)
                    center = (all_vertices.min(0) + all_vertices.max(0)) / 2
                    
                    copy_obj.apply_translation(-center)
                    copy_obj.apply_transform(trimesh.transformations.rotation_matrix(angle, axis_vec))
                    copy_obj.apply_translation(center)
                    
                    if axis == 'x':
                        copy_obj.apply_translation([0, radius * math.sin(angle), radius * math.cos(angle)])
                    elif axis == 'y':
                        copy_obj.apply_translation([radius * math.sin(angle), 0, radius * math.cos(angle)])
                    else:
                        copy_obj.apply_translation([radius * math.cos(angle), radius * math.sin(angle), 0])
                    
                    copy_obj.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_pattern_{i}"
                    self.objects.append(copy_obj)

            self._notify(f"Pattern circolare creato ({count} elementi)")
            return True
        except Exception as e:
            self._notify(f"Errore nel pattern circolare: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def _mesh_valida(self, mesh) -> bool:
        """True se la mesh ha vertici/facce presenti e bounds finiti."""
        try:
            if not hasattr(mesh, 'vertices') or not hasattr(mesh, 'faces'):
                return False
            verts = np.asarray(mesh.vertices)
            faces = np.asarray(mesh.faces)
            if verts.size == 0 or faces.size == 0 or len(verts) < 3 or len(faces) < 1:
                return False
            b = mesh.bounds
            if b is None or not np.all(np.isfinite(b)):
                return False
            return True
        except Exception:
            return False

    def smooth(self, iterations: int = 1) -> bool:
        if len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per lo smoothing")
            return False

        obj = self.selected_objects[0]
        if not self._mesh_valida(obj):
            self._notify("Smoothing non applicabile: mesh non valida o senza vertici")
            return False
        if obj not in self.objects:
            self._notify("Smoothing non applicabile: oggetto non più presente nella scena")
            return False

        self.start_operation()
        try:
            original = obj
            processed = original.copy()
            for _ in range(iterations):
                trimesh.smoothing.filter_laplacian(
                    processed, lamb=0.1, iterations=1,
                    implicit_time_integration=True, volume_constraint=True)

            if not np.all(np.isfinite(processed.vertices)):
                raise ValueError("vertici non finiti dopo il filtraggio")
            if float(np.max(np.abs(processed.vertices))) > 1000.0:
                raise ValueError("vertici esplosi dopo il filtraggio")
            if not self._mesh_valida(processed):
                raise ValueError("mesh non valida dopo il filtraggio")

            index = self.objects.index(original)
            self.objects[index] = processed
            self.selected_objects = [processed]

            self._notify(f"Smoothing applicato ({iterations} iterazioni)")
            return True
        except ValueError:
            self._notify("Smooth non applicabile a questa geometria")
            return False
        except Exception as e:
            self._notify(f"Errore nello smoothing: {e}")
            return False
        finally:
            self.cancel_operation()

    def subdivide(self, iterations: int = 1) -> bool:
        if len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per la suddivisione")
            return False

        obj = self.selected_objects[0]
        if not self._mesh_valida(obj):
            self._notify("Suddivisione non applicabile: mesh non valida o senza vertici")
            return False
        if obj not in self.objects:
            self._notify("Suddivisione non applicabile: oggetto non più presente nella scena")
            return False

        self.start_operation()
        try:
            original = obj
            processed = original
            for _ in range(iterations):
                processed = processed.subdivide()

            index = self.objects.index(original)
            self.objects[index] = processed
            self.selected_objects = [processed]

            self._notify(f"Suddivisione applicata ({iterations} iterazioni)")
            return True
        except Exception as e:
            self._notify(f"Errore nella suddivisione: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def decimate(self, target_faces: int = 1000) -> bool:
        if len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per la decimazione")
            return False
        
        self.start_operation()
        try:
            original = self.selected_objects[0]
            obj = original

            n_faces = len(obj.faces)
            if target_faces >= n_faces:
                self._notify(f"Decimazione non necessaria: la mesh ha già {n_faces} facce (target {target_faces})")
                return True

            if not obj.vertices.flags.writeable:
                obj = trimesh.Trimesh(
                    vertices=np.array(obj.vertices),
                    faces=np.array(obj.faces),
                    metadata=obj.metadata.copy()
                )
            
            obj = obj.simplify_quadric_decimation(face_count=target_faces)

            index = self.objects.index(original)
            self.objects[index] = obj
            self.selected_objects = [obj]

            self._notify(f"Decimazione applicata (target: {target_faces} facce)")
            return True
        except Exception as e:
            self._notify(f"Errore nella decimazione: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def create_hole(self, diameter: float = 5.0, depth: float = 10.0) -> bool:
        if len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per creare un foro")
            return False
        
        self.start_operation()
        try:
            obj = self.selected_objects[0]
            hole = trimesh.creation.cylinder(radius=diameter/2, height=depth)
            
            bounds = obj.bounds
            center = (bounds[0] + bounds[1]) / 2
            hole.apply_translation([center[0], center[1], center[2] - depth/2])
            
            result = boolean_safe([obj, hole], "difference")

            if result is None or result.is_empty:
                self._notify("Impossibile creare il foro")
                return False

            index = self.objects.index(obj)
            self.objects[index] = result
            result.metadata = obj.metadata.copy()
            result.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_with_hole"

            self.selected_objects = [result]

            self._notify(f"Foro creato (diametro: {diameter}mm, profondità: {depth}mm)")
            return True
        except Exception as e:
            self._notify(f"Errore nella creazione del foro: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def cut_with_plane(self, axis: str = 'z', position: float = 0.0) -> bool:
        if len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per il taglio")
            return False
        
        self.start_operation()
        try:
            obj = self.selected_objects[0]
            bounds = obj.bounds
            if bounds is None:
                return False
            
            ax_map = {'x': 0, 'y': 1, 'z': 2}
            ax_idx = ax_map.get(axis.lower(), 2)
            origin = [0, 0, 0]
            origin[ax_idx] = bounds[0][ax_idx] + position
            normal = [0, 0, 0]
            normal[ax_idx] = 1.0
            
            sliced = trimesh.intersections.slice_mesh_plane(
                obj, plane_origin=origin, plane_normal=normal, cap=True
            )
            if sliced is None or len(sliced.vertices) < 3:
                self._notify("Taglio con piano: nessuna mesh risultante")
                return False
            
            sliced.metadata.update(obj.metadata.copy())
            sliced.metadata.pop("_gl_verts", None)
            sliced.metadata.pop("_gl_normals", None)
            sliced.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_tagliato"
            sliced.fix_normals()
            
            idx = self.objects.index(obj)
            self.objects[idx] = sliced
            self.selected_objects = [sliced]
            self._needs_spatial_rebuild = True
            
            self._notify(f"Taglio eseguito con piano {axis}={position}")
            return True
        except Exception as e:
            self._notify(f"Errore nel taglio con piano: {e}")
            return False
        finally:
            self.end_operation()
    
    def deform(self, deformation_type: str = "bend", intensity: float = 0.5) -> bool:
        if len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per la deformazione")
            return False
        
        self.start_operation()
        try:
            obj = self.selected_objects[0]
            verts = obj.vertices.copy()
            bounds = obj.bounds
            if bounds is None:
                return False
            center = (bounds[0] + bounds[1]) / 2
            size = bounds[1] - bounds[0]
            local = verts - center
            
            if deformation_type == "bend":
                radius = max(size[0], size[1]) / max(intensity * 5, 0.1)
                angle_per_unit = 1.0 / max(radius, 0.1)
                for i in range(len(local)):
                    x, y, z = local[i]
                    theta = x * angle_per_unit
                    local[i] = [
                        (radius + z) * math.sin(theta),
                        y,
                        (radius + z) * math.cos(theta) - radius
                    ]
                self._notify(f"Deformazione di curvatura applicata (intensità: {intensity})")
                
            elif deformation_type == "twist":
                angle = intensity * math.pi
                for i in range(len(local)):
                    x, y, z = local[i]
                    t = (z + size[2]/2) / max(size[2], 0.001)
                    theta = t * angle
                    c, s = math.cos(theta), math.sin(theta)
                    local[i] = [x * c - y * s, x * s + y * c, z]
                self._notify(f"Deformazione di torsione applicata (intensità: {intensity})")
                
            elif deformation_type == "taper":
                for i in range(len(local)):
                    x, y, z = local[i]
                    t = (z + size[2]/2) / max(size[2], 0.001)
                    scale = 1.0 + intensity * t * 0.5
                    local[i] = [x * scale, y * scale, z]
                self._notify(f"Deformazione di affusolatura applicata (intensità: {intensity})")
            
            obj.vertices = local + center
            obj.remove_unreferenced_vertices()
            obj.fix_normals()
            obj.metadata.pop("_gl_verts", None)
            
            return True
        except Exception as e:
            self._notify(f"Errore nella deformazione: {e}")
            return False
        finally:
            self.end_operation()
    
    def project_to_surface(self) -> bool:
        if len(self.selected_objects) < 2:
            self._notify("Seleziona una forma 2D e una superficie 3D")
            return False
        
        self.start_operation()
        try:
            obj_2d = None
            obj_surf = None
            for obj in self.selected_objects:
                if obj_2d is None:
                    obj_2d = obj
                else:
                    obj_surf = obj
                    break
            if obj_surf is None and len(self.selected_objects) >= 2:
                obj_2d, obj_surf = self.selected_objects[0], self.selected_objects[1]
            
            if obj_surf is None:
                return False
            
            verts = obj_2d.vertices.copy()
            bounds_2d = obj_2d.bounds
            if bounds_2d is None:
                return False
            center_2d = (bounds_2d[0] + bounds_2d[1]) / 2
            
            ray_origins = verts + np.array([0, 0, 100])
            ray_dirs = np.tile([0, 0, -1], (len(verts), 1))
            
            locations, ray_idx, _ = obj_surf.ray.intersects_location(
                ray_origins, ray_dirs, multiple_hits=False
            )
            
            if len(locations) > 0:
                projected = verts.copy()
                for i, loc in zip(ray_idx, locations):
                    if i < len(projected):
                        projected[i, 0] = loc[0]
                        projected[i, 1] = loc[1]
                        projected[i, 2] = loc[2] + 0.5
                projected_mesh = trimesh.Trimesh(
                    vertices=projected,
                    faces=obj_2d.faces.copy()
                )
                projected_mesh.fix_normals()
                projected_mesh.remove_unreferenced_vertices()
                projected_mesh.metadata.update(obj_2d.metadata.copy())
                projected_mesh.metadata.pop("_gl_verts", None)
                projected_mesh.metadata["name"] = f"{obj_2d.metadata.get('name', 'Object')}_proiettato"
                
                self.objects.append(projected_mesh)
                self._needs_spatial_rebuild = True
                self._notify(f"Proiezione eseguita sulla superficie ({len(locations)} vertici proiettati)")
            else:
                self._notify("Nessuna superficie raggiunta per la proiezione")
            
            return True
        except Exception as e:
            self._notify(f"Errore nella proiezione: {e}")
            return False
        finally:
            self.end_operation()
    
    def merge_vertices(self, distance: float = 0.01) -> bool:
        if len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per unire i vertici")
            return False
        
        self.start_operation()
        try:
            obj = self.selected_objects[0]
            obj.merge_vertices(seam_threshold=distance)
            
            index = self.objects.index(obj)
            self.objects[index] = obj

            self._notify(f"Vertici uniti (distanza massima: {distance})")
            return True
        except Exception as e:
            self._notify(f"Errore nell'unire i vertici: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def measure_distance(self) -> bool:
        if not self.selected_objects:
            self._notify("Seleziona almeno un oggetto per misurare")
            return False
        
        try:
            self.measurement_mode = "distance"
            self.measurement_points = []
            self._notify("Clicca su due punti per misurare la distanza")
            return True
        except Exception as e:
            self._notify(f"Errore nella misurazione: {e}")
            return False
    
    def measure_angle(self) -> bool:
        if not self.selected_objects:
            self._notify("Seleziona almeno un oggetto per misurare")
            return False
        
        try:
            self.measurement_mode = "angle"
            self.measurement_points = []
            self._notify("Clicca su tre punti per misurare l'angolo")
            return True
        except Exception as e:
            self._notify(f"Errore nella misurazione: {e}")
            return False
    
    def move_selection(self, dx: float, dy: float, dz: float) -> None:
        if not self.selected_objects:
            return
        
        for obj in self.selected_objects:
            if hasattr(obj, 'apply_translation'):
                obj.apply_translation([dx, dy, dz])
                obj.metadata.pop("_gl_verts", None)
    
    def scale_selection(self, sx: float, sy: float, sz: float) -> None:
        if not self.selected_objects:
            return
        
        all_vertices = []
        for obj in self.selected_objects:
            all_vertices.extend(obj.vertices)
        
        if not all_vertices:
            return
        
        all_vertices = np.array(all_vertices)
        center = np.mean(all_vertices, axis=0)
        
        z_only = abs(sx - 1) < 0.001 and abs(sy - 1) < 0.001 and abs(sz - 1) > 0.001
        
        for obj in self.selected_objects:
            if hasattr(obj, 'apply_translation') and hasattr(obj, 'apply_scale'):
                base_z = obj.bounds[0][2] if hasattr(obj, 'bounds') and obj.bounds is not None else None
                if z_only:
                    if base_z is not None:
                        obj.apply_translation([0, 0, -base_z])
                        obj.apply_scale([sx, sy, sz])
                        obj.apply_translation([0, 0, base_z])
                    else:
                        obj.apply_scale([sx, sy, sz])
                else:
                    if base_z is not None and base_z < 0.001:
                        adj_center = np.array([center[0], center[1], 0.0])
                    else:
                        adj_center = center.copy()
                    obj.apply_translation(-adj_center)
                    obj.apply_scale([sx, sy, sz])
                    obj.apply_translation(adj_center)
                obj.metadata.pop("_gl_verts", None)
            else:
                print(f"Warning: L'oggetto {obj.metadata.get('name', 'unknown')} non supporta apply_scale")
    
    def rotate_selection(self, angle: float, axis: np.ndarray) -> None:
        if not self.selected_objects:
            return
        
        all_vertices = []
        for obj in self.selected_objects:
            all_vertices.extend(obj.vertices)
        
        if not all_vertices:
            return
            
        all_vertices = np.array(all_vertices)
        center = np.mean(all_vertices, axis=0)
        
        for obj in self.selected_objects:
            if hasattr(obj, 'apply_translation') and hasattr(obj, 'apply_transform'):
                obj.apply_translation(-center)
                obj.apply_transform(trimesh.transformations.rotation_matrix(angle, axis))
                obj.apply_translation(center)
                obj.metadata.pop("_gl_verts", None)
    
    def scale_selection_uniform(self, factor: float) -> bool:
        """Scala uniforme della selezione attorno al centroide di ciascun oggetto.

        Non usa scale_selection (sx,sy,sz separati, centro globale della selezione):
        qui un singolo fattore, centro = obj.centroid, vertici (v-c)*s+c.
        Annullabile con l'undo (push dello stato prima della mutazione).
        """
        if not self.selected_objects:
            self._notify("Nessun oggetto selezionato per la scala")
            return False
        if not np.isfinite(factor) or factor <= 0.0:
            self._notify(f"Fattore di scala non valido: {factor}")
            return False
        self.start_operation()
        try:
            cache_keys = ("_gl_verts", "_gl_normals", "_gl_vbo_verts", "_gl_vbo_normals")
            scaled = 0
            for obj in self.selected_objects:
                if not hasattr(obj, "vertices") or len(obj.vertices) == 0:
                    continue
                try:
                    c = np.asarray(obj.centroid, dtype=np.float64).reshape(3)
                except Exception:
                    c = np.asarray(obj.vertices, dtype=np.float64).mean(axis=0)
                verts = np.asarray(obj.vertices, dtype=np.float64)
                obj.vertices = (verts - c) * factor + c
                for key in cache_keys:
                    obj.metadata.pop(key, None)
                scaled += 1
            if scaled == 0:
                self._notify("Nessun oggetto scalabile tra i selezionati")
                return False
            self.end_operation()
            self._notify(f"Scala uniforme applicata a {scaled} oggetto/i (fattore {factor:.6f})")
            return True
        except Exception as e:
            print(f"Errore nella scala uniforme: {e}")
            return False
        finally:
            self.cancel_operation()
    
    def _notify(self, message: str) -> None:
        print(f"NOTIFICA: {message}")
        if self._callback_notify is not None:
            try:
                self._callback_notify(message)
            except Exception as e:
                print(f"[TriviumCAD] Errore nel callback di notifica: {e}")

    def slice_objects(self, axis: str = "z", offset: float = 0.0, pieces: int = 2) -> bool:
        if not self.selected_objects:
            return False
        self.start_operation()
        try:
            eps = 1e-6
            ax_idx = {'x': 0, 'y': 1, 'z': 2}.get(axis.lower(), 2)
            all_new = []
            for obj in self.selected_objects:
                if not hasattr(obj, 'vertices') or len(obj.vertices) < 3:
                    continue
                if not hasattr(obj, 'centroid'):
                    continue
                b = obj.bounds
                if b is None:
                    continue
                lo, hi = b[0][ax_idx], b[1][ax_idx]
                if hi - lo < eps:
                    continue
                centro = float(obj.centroid[ax_idx])
                if pieces <= 2:
                    cut_positions = [centro + offset]
                else:
                    step = (hi - lo) / pieces
                    n_cuts = pieces - 1
                    start = (lo + hi) / 2.0 - (hi - lo) / 2.0 + step + offset
                    cut_positions = [start + i * step for i in range(n_cuts)]
                
                current_pieces = [obj]
                for cp in cut_positions:
                    next_pieces = []
                    for piece in current_pieces:
                        if not hasattr(piece, 'vertices') or len(piece.vertices) < 3:
                            next_pieces.append(piece)
                            continue
                        bp = piece.bounds
                        if bp is None or bp[1][ax_idx] - bp[0][ax_idx] < eps:
                            next_pieces.append(piece)
                            continue
                        if axis.lower() == "z":
                            oa, nb = [0, 0, cp + eps], [0, 0, 1]
                            ob = [0, 0, cp - eps]
                        elif axis.lower() == "y":
                            oa, nb = [0, cp + eps, 0], [0, 1, 0]
                            ob = [0, cp - eps, 0]
                        else:
                            oa, nb = [cp + eps, 0, 0], [1, 0, 0]
                            ob = [cp - eps, 0, 0]
                        sa = trimesh.intersections.slice_mesh_plane(piece, plane_origin=oa, plane_normal=nb, cap=True)
                        sb = trimesh.intersections.slice_mesh_plane(piece, plane_origin=ob, plane_normal=[-x for x in nb], cap=True)
                        has_a = sa is not None and len(sa.vertices) >= 3
                        has_b = sb is not None and len(sb.vertices) >= 3
                        if has_a and has_b:
                            for m in (sa, sb):
                                m.metadata.update(piece.metadata.copy())
                                for k in ('_gl_verts','_gl_normals','_gl_vbo_verts','_gl_vbo_normals'):
                                    m.metadata.pop(k, None)
                                m.fix_normals()
                                next_pieces.append(m)
                        elif has_a:
                            next_pieces.append(sa)
                        elif has_b:
                            next_pieces.append(sb)
                        else:
                            next_pieces.append(piece)
                    current_pieces = next_pieces
                all_new.extend(current_pieces)
            
            if not all_new:
                return False
            for obj in self.selected_objects[:]:
                if obj in self.objects:
                    self.objects.remove(obj)
            for idx, no in enumerate(all_new):
                self.objects.append(no)
                no.metadata['name'] = f"{no.metadata.get('name','Obj')}_{idx}"
            self.selected_objects = all_new[:]
            self._needs_spatial_rebuild = True
            return True
        except Exception as e:
            print(f"Errore affettatura: {e}")
            return False
        finally:
            self.cancel_operation()

    def fillet_selected(self, radius: float = 25.0) -> bool:
        if not self.selected_objects:
            return False
        self.start_operation()
        new_selection = []
        try:
            for obj in self.selected_objects:
                try:
                    mesh = obj.copy()
                    if len(mesh.vertices) < 3:
                        continue
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
                    with np.errstate(divide='ignore', invalid='ignore'):
                        for _ in range(subdivs):
                            try:
                                mesh = mesh.subdivide()
                            except Exception:
                                break
                    if len(mesh.vertices) < 3:
                        new_selection.append(obj)
                        continue
                    if n_faces < 50:
                        strength = min(0.35, 0.06 + radius * 0.04)
                        smooth_iter = max(5, min(15, int(radius * 2.5)))
                    else:
                        strength = min(0.45, 0.1 + radius * 0.06)
                        smooth_iter = max(10, min(40, int(radius * 5.0)))
                    with np.errstate(divide='ignore', invalid='ignore'):
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
                    idx = self.objects.index(obj)
                    self.objects[idx] = mesh
                    new_selection.append(mesh)
                except Exception:
                    print("ERRORE: fillet_selected fallito per un oggetto nel loop")
            if new_selection:
                self.selected_objects = new_selection
            return bool(new_selection)
        except Exception as e:
            print(f"Errore arrotondamento: {e}")
            return False
        finally:
            self.cancel_operation()

    def thread_selected(self, turns: int = 8, thread_radius: float = 1.5) -> bool:
        if not self.selected_objects or len(self.selected_objects) != 1:
            self._notify("Seleziona un singolo oggetto per la filettatura")
            return False
        self.start_operation()
        try:
            obj = self.selected_objects[0]
            thread = _generate_thread_on_shape(obj, turns=turns, thread_radius=thread_radius)
            if thread and len(thread.vertices) >= 3:
                thread.metadata.update(obj.metadata.copy())
                thread.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_filettato"
                thread.metadata.pop("_gl_verts", None)
                thread.metadata.pop("_gl_normals", None)
                thread.metadata.pop("_gl_vbo_verts", None)
                thread.metadata.pop("_gl_vbo_normals", None)
                self.objects.append(thread)
                self.selected_objects = [thread]
                self._needs_spatial_rebuild = True
                self._notify(f"Filettatura generata: {len(thread.vertices)} vertici")
                return True
            return False
        except Exception as e:
            print(f"Errore filettatura: {e}")
            self._notify(f"Errore filettatura: {e}")
            return False
        finally:
            self.cancel_operation()

    def generate_adaptive_path(self, tool_diameter: float, stepover: float, 
                             clearance: float, feed_rate: float) -> bool:
        """Genera un percorso CAM adattivo per la fresatura"""
        if not self.selected_objects or len(self.selected_objects) > 1:
            return False
        
        self.start_operation()
        try:
            mesh = self.selected_objects[0]
            
            if not hasattr(mesh, 'bounds') or mesh.bounds is None:
                return False
            
            min_bounds, max_bounds = mesh.bounds
            safe_z = max_bounds[2] + clearance
            y_current = min_bounds[1]
            direction_x = 1
            self.gcode_paths = []
            
            while y_current <= max_bounds[1]:
                x_points = np.arange(min_bounds[0], max_bounds[0] + stepover, stepover)
                if direction_x == -1:
                    x_points = x_points[::-1]
                
                origins = np.array([[x, y_current, safe_z] for x in x_points])
                vectors = np.tile([0, 0, -1], (len(x_points), 1))
                
                if not hasattr(mesh, 'ray') or not hasattr(mesh.ray, 'intersects_location'):
                    return False
                
                locations, indices, _ = mesh.ray.intersects_location(
                    origins, vectors, multiple_hits=False)
                
                path, previous_z = [], safe_z
                for i, x in enumerate(x_points):
                    hits = locations[indices == i]
                    target = hits[0][2] + tool_diameter / 2 if len(hits) > 0 else previous_z
                    path.append([x, y_current, target])
                
                if len(path) > 1:
                    self.gcode_paths.append({
                        "type": "ext",
                        "pts": path,
                        "s": feed_rate
                    })
                
                y_current += stepover
                direction_x *= -1

            return len(self.gcode_paths) > 0
        except Exception as e:
            print(f"Errore generazione percorso adattivo: {e}")
            return False
        finally:
            self.cancel_operation()

# === SCANNER MODULE ===
class ScannerModule:
    def __init__(self) -> None:
        pass
        
    def load_scan(self, file_path: str) -> Optional[trimesh.Trimesh]:
        try:
            mesh = trimesh.load(file_path, force='mesh')
            if isinstance(mesh, trimesh.Scene):
                mesh = mesh.dump(concatenate=True)
                if not isinstance(mesh, trimesh.Trimesh):
                    for m in mesh:
                        if isinstance(m, trimesh.Trimesh):
                            mesh = m
                            break
            
            mesh = validate_and_place_mesh(mesh)
            mesh.metadata.update({
                "layer": "Default",
                "color": NEUTRAL_COLORS[1],
                "name": Path(file_path).stem + "_scan",
                "shape_type": "scanned",
                "params": {},
                "assembly": None
            })
            
            return mesh
        except Exception as e:
            print(f"Errore caricamento scan: {e}")
            return None