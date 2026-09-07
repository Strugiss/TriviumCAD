#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TriviumCAD v1.2.0
Versione completa con funzionalità CAD e CAM.
Copyright (c) 2026 N47Lab Team - Tutti i diritti riservati.
"""

import sys
import os
import math
import json
import time
import numpy as np
import trimesh
import trimesh.boolean
import trimesh.smoothing
import trimesh.repair
import shapely.geometry as sgeom
from shapely.geometry import Polygon as ShapelyPolygon
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set

# Importazioni PyQt5 - DEVE ESSERE PRIMA DELLE DEFINIZIONI DI CLASSI
from PyQt5.QtCore import Qt, QTimer, QEvent, QSize, QPoint, QPointF, QRect, QRectF, QObject, pyqtSignal, QSettings
from PyQt5.QtGui import QFont, QFontMetrics, QSurfaceFormat, QPainter, QPainterPath, QColor, QPen, QKeySequence, QTextCharFormat, QTextCursor, QIcon, QPixmap, QPalette
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSplitter, QGroupBox, QFormLayout,
    QFileDialog, QMessageBox, QInputDialog, QToolBar, QStatusBar,
    QShortcut, QListWidget, QListWidgetItem, QScrollArea, QOpenGLWidget, 
     QSpinBox, QDoubleSpinBox, QTreeWidget, QTreeWidgetItem, QSizePolicy, QAction,
    QTextEdit, QLineEdit, QTabWidget, QStackedWidget, QDialog, QDialogButtonBox, QFrame,
    QMenu, QToolButton, QButtonGroup, QSlider, QCheckBox, QComboBox,
    QPlainTextEdit, QDockWidget
)
from OpenGL.GL import *
from OpenGL.GLU import *

# =============================================================================
# COSTANTI GLOBALI
# =============================================================================
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

# --- CORE ESTRATTO (package core/) ---
from core.constants import (
    APP_NAME,
    BACKGROUND_COLOR, TEXT_COLOR, BORDER_COLOR, BUTTON_COLOR,
    BUTTON_HOVER, BUTTON_PRESSED,
    NEUTRAL_COLORS, SHAPE_LIBRARY, PRINTER_PROFILES,
)
from core import __version__ as VERSION
from core.utils import NumpyEncoder
from core.primitives import _generate_text_mesh
from core.mesh_ops import create_mesh, validate_and_place_mesh, boolean_safe, _ensure_volume, _ray_first_hits
from core.thread import _compute_thread_mesh, _compute_subtraction_volume
from core.cam import _compute_adaptive_path
from core.scene import Scene, _UndoManager, ScannerModule
# =============================================================================
# WORKER THREAD PER OPERAZIONI BLOCCANTI
# =============================================================================

class _GenericWorker(QObject):
    finished = pyqtSignal(object)
    def __init__(self, fn, args=None, kwargs=None):
        super().__init__()
        self.fn = fn
        self.args = args or ()
        self.kwargs = kwargs or {}
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(e)

# =============================================================================
# GIZMO RENDERER (estrae logica gizmo da GLWidget)
# =============================================================================
# === GIZMO RENDERER ===
class GizmoRenderer:
    def __init__(self):
        self.points_3d = {}
        self.points_2d = {}
        self.hover = None
        self.active_handle = None
        self.rotate_angle_during_drag = None
        self.angle_labels_2d = []
        self._ring_dl_x = None
        self._ring_dl_y = None
        self._ring_dl_z = None
        self._ring_dl_radius = -1.0
        self._ring_dl_center = None

    def _ensure_ring_dl(self, axis_name, center, radius):
        if (abs(self._ring_dl_radius - radius) < 0.001 and
            self._ring_dl_center is not None and
            np.linalg.norm(np.array(self._ring_dl_center) - np.array(center)) < 0.01 and
            ((axis_name == 'x' and self._ring_dl_x is not None) or
             (axis_name == 'y' and self._ring_dl_y is not None) or
             (axis_name == 'z' and self._ring_dl_z is not None))):
            return self._ring_dl_x if axis_name == 'x' else self._ring_dl_y if axis_name == 'y' else self._ring_dl_z
        # Rebuild all three axis display lists
        for old_dl in [self._ring_dl_x, self._ring_dl_y, self._ring_dl_z]:
            if old_dl is not None:
                try:
                    glDeleteLists(old_dl, 1)
                except Exception as e:
                    print(f"[TriviumCAD] gizmo._ensure_ring_dl (glDeleteLists): {e}")
        def _dl_for_ax(ax_name):
            dl = glGenLists(1)
            glNewList(dl, GL_COMPILE)
            segs = 96
            glBegin(GL_LINE_LOOP)
            glColor4f(1.0, 0.95, 0.3, 0.7)
            for i in range(segs):
                a = 2 * math.pi * i / segs
                if ax_name == 'x':
                    pt = np.array([0, radius * math.cos(a), radius * math.sin(a)])
                elif ax_name == 'y':
                    pt = np.array([radius * math.cos(a), 0, radius * math.sin(a)])
                else:
                    pt = np.array([radius * math.cos(a), radius * math.sin(a), 0])
                glVertex3fv(pt)
            glEnd()
            glBegin(GL_LINES)
            glColor4f(1.0, 0.9, 0.2, 0.7)
            for deg in range(0, 360, 15):
                a = math.radians(deg)
                tick_len = radius * 0.1 if deg % 45 == 0 else radius * 0.05
                if ax_name == 'x':
                    inner = np.array([0, radius * math.cos(a), radius * math.sin(a)])
                    outer = np.array([0, (radius + tick_len) * math.cos(a), (radius + tick_len) * math.sin(a)])
                elif ax_name == 'y':
                    inner = np.array([radius * math.cos(a), 0, radius * math.sin(a)])
                    outer = np.array([(radius + tick_len) * math.cos(a), 0, (radius + tick_len) * math.sin(a)])
                else:
                    inner = np.array([radius * math.cos(a), radius * math.sin(a), 0])
                    outer = np.array([(radius + tick_len) * math.cos(a), (radius + tick_len) * math.sin(a), 0])
                glVertex3fv(inner)
                glVertex3fv(outer)
            glEnd()
            glPointSize(5.0)
            glBegin(GL_POINTS)
            glColor4f(1.0, 0.85, 0.0, 0.9)
            for deg in range(0, 360, 45):
                a = math.radians(deg)
                num_r = radius * 1.08
                if ax_name == 'x':
                    pt = np.array([0, num_r * math.cos(a), num_r * math.sin(a)])
                elif ax_name == 'y':
                    pt = np.array([num_r * math.cos(a), 0, num_r * math.sin(a)])
                else:
                    pt = np.array([num_r * math.cos(a), num_r * math.sin(a), 0])
                glVertex3fv(pt)
            glEnd()
            glEndList()
            return dl
        self._ring_dl_x = _dl_for_ax('x')
        self._ring_dl_y = _dl_for_ax('y')
        self._ring_dl_z = _dl_for_ax('z')
        self._ring_dl_radius = radius
        self._ring_dl_center = list(center)
        return self._ring_dl_x if axis_name == 'x' else self._ring_dl_y if axis_name == 'y' else self._ring_dl_z

    def render(self, modelview, projection, viewport, scene, distance):
        self.angle_labels_2d = []
        if modelview is None or projection is None or viewport is None:
            return
        try:
            all_vertices = []
            for obj in scene.selected_objects:
                all_vertices.extend(obj.vertices)
            if not all_vertices:
                return
            all_vertices = np.array(all_vertices)
            bounds = [np.min(all_vertices, axis=0), np.max(all_vertices, axis=0)]
            center = (bounds[0] + bounds[1]) / 2
            extents = bounds[1] - bounds[0]
            max_extent = max(extents)
            scale = max(1.0, max_extent * 0.1)
            scale *= (distance / 200)
            self.points_3d = {}
            self.points_2d = {}
            size = 0.5 * scale
            all_text = all(obj.metadata.get("shape_type") == "text" for obj in scene.selected_objects)
            if all_text:
                ring_radius = min(max_extent * 0.7, size * 5)
                max_handle = size * 4
            else:
                ring_radius = max_extent * 0.7
                max_handle = float('inf')
            handle_len_x = min(max(extents[0], max_extent * 0.2) * 0.65, max_handle)
            handle_len_y = min(max(extents[1], max_extent * 0.2) * 0.65, max_handle)
            handle_len_z = min(max(extents[2], max_extent * 0.2) * 0.65, max_handle)
            axes = [
                ('x', [1, 0, 0], [0.8, 0.3, 0.3, 0.95], handle_len_x),
                ('y', [0, -1, 0], [0.3, 0.8, 0.3, 0.95], handle_len_y),
                ('z', [0, 0, 1], [0.3, 0.3, 0.8, 0.95], handle_len_z)
            ]
            for axis_name, axis_dir, color, handle_len in axes:
                is_hovered = (self.hover == axis_name or self.active_handle == axis_name or
                              self.hover == 'rot_' + axis_name or self.active_handle == 'rot_' + axis_name)
                self.draw_axis(center, axis_dir, color, handle_len, line_width=2.0, is_hovered=is_hovered)
            for axis_name, axis_dir, color, _ in axes:
                is_rot_active = (self.hover == 'rot_' + axis_name or self.active_handle == 'rot_' + axis_name)
                if is_rot_active:
                    glDisable(GL_LIGHTING)
                    glEnable(GL_LINE_SMOOTH)
                    glLineWidth(1.5)
                    glPushMatrix()
                    glTranslatef(*center)
                    glCallList(self._ensure_ring_dl(axis_name, center, ring_radius))
                    glPopMatrix()
                    glEnable(GL_LIGHTING)
                    label_r = ring_radius * 1.25
                    for deg in range(0, 360, 45):
                        a = math.radians(deg)
                        if axis_name == 'x':
                            lp = center + np.array([0, label_r * math.cos(a), label_r * math.sin(a)])
                        elif axis_name == 'y':
                            lp = center + np.array([label_r * math.cos(a), 0, label_r * math.sin(a)])
                        else:
                            lp = center + np.array([label_r * math.cos(a), label_r * math.sin(a), 0])
                        try:
                            sx, sy, _ = gluProject(lp[0], lp[1], lp[2],
                                modelview, projection, viewport)
                            self.angle_labels_2d.append((sx, viewport[3] - sy, f"{deg}°"))
                        except Exception as e:
                            print(f"[TriviumCAD] gizmo.render (etichetta angolo): {e}")
                for j in range(4):
                    base_a = math.radians(45 + j * 90)
                    if self.active_handle == 'rot_' + axis_name and self.rotate_angle_during_drag is not None and j == 0:
                        a = self.rotate_angle_during_drag
                    else:
                        a = base_a
                    if axis_name == 'x':
                        pos = center + np.array([0, ring_radius * math.cos(a), ring_radius * math.sin(a)])
                    elif axis_name == 'y':
                        pos = center + np.array([ring_radius * math.cos(a), 0, ring_radius * math.sin(a)])
                    else:
                        pos = center + np.array([ring_radius * math.cos(a), ring_radius * math.sin(a), 0])
                    key = f'rh{axis_name}{j}'
                    self.points_3d[key] = pos
                    try:
                        sx, sy, _ = gluProject(pos[0], pos[1], pos[2],
                            modelview, projection, viewport)
                        self.points_2d[key] = np.array([sx, viewport[3] - sy])
                    except Exception as e:
                        print(f"[TriviumCAD] gizmo.render (rot handle 2D): {e}")
                    is_rot_h = (self.hover == key)
                    self.draw_rot_handle(pos, size * 0.65, is_rot_h)
            for axis_name, axis_dir, color, handle_len in axes:
                handle_pos = center + np.array(axis_dir) * handle_len
                self.points_3d[axis_name] = handle_pos
                try:
                    screen_x, screen_y, _ = gluProject(
                        handle_pos[0], handle_pos[1], handle_pos[2],
                        modelview, projection, viewport)
                    self.points_2d[axis_name] = np.array([screen_x, viewport[3] - screen_y])
                except Exception as e:
                    print(f"[TriviumCAD] gizmo.render (handle asse 2D): {e}")
                    continue
                is_hovered = (self.hover == axis_name)
                self.draw_handle(handle_pos, axis_name, size, is_hovered)
            try:
                self.points_3d["center"] = center
                try:
                    screen_x, screen_y, _ = gluProject(
                        center[0], center[1], center[2],
                        modelview, projection, viewport)
                    self.points_2d["center"] = np.array([screen_x, viewport[3] - screen_y])
                except Exception as e:
                    print(f"[TriviumCAD] gizmo.render (centro 2D): {e}")
                is_hovered = (self.hover == "center")
                self.draw_handle(center, "center", size * 0.7, is_hovered)
            except Exception as e:
                print(f"[TriviumCAD] gizmo.render (blocco centro): {e}")
            uniform_scale_pos = center + np.array([max_extent * 0.5, max_extent * 0.5, 0])
            self.points_3d["uniform"] = uniform_scale_pos
            try:
                screen_x, screen_y, _ = gluProject(
                    uniform_scale_pos[0], uniform_scale_pos[1], uniform_scale_pos[2],
                    modelview, projection, viewport)
                self.points_2d["uniform"] = np.array([screen_x, viewport[3] - screen_y])
                is_hovered = (self.hover == "uniform")
                self.draw_uniform_scale_handle(uniform_scale_pos, is_hovered)
            except Exception as e:
                print(f"[TriviumCAD] gizmo.render (uniform handle): {e}")
            vertical_handle_pos = center + np.array([0, 0, max_extent * 0.9])
            self.points_3d["vertical"] = vertical_handle_pos
            try:
                screen_x, screen_y, _ = gluProject(
                    vertical_handle_pos[0], vertical_handle_pos[1], vertical_handle_pos[2],
                    modelview, projection, viewport)
                self.points_2d["vertical"] = np.array([screen_x, viewport[3] - screen_y])
                is_hovered = (self.hover == "vertical")
                self.draw_vertical_handle(vertical_handle_pos, is_hovered)
            except Exception as e:
                print(f"[TriviumCAD] gizmo.render (vertical handle): {e}")
            # --- Face handles (6 facce del bounding box) ---
            bmin, bmax = bounds[0], bounds[1]
            face_data = [
                ('face_x+', 'x', [bmax[0], (bmin[1]+bmax[1])/2, (bmin[2]+bmax[2])/2]),
                ('face_x-', 'x', [bmin[0], (bmin[1]+bmax[1])/2, (bmin[2]+bmax[2])/2]),
                ('face_y+', 'y', [(bmin[0]+bmax[0])/2, bmax[1], (bmin[2]+bmax[2])/2]),
                ('face_y-', 'y', [(bmin[0]+bmax[0])/2, bmin[1], (bmin[2]+bmax[2])/2]),
                ('face_z+', 'z', [(bmin[0]+bmax[0])/2, (bmin[1]+bmax[1])/2, bmax[2]]),
                ('face_z-', 'z', [(bmin[0]+bmax[0])/2, (bmin[1]+bmax[1])/2, bmin[2]]),
            ]
            for key, ax, pos in face_data:
                try:
                    off_dir = 1.0 if key.endswith('+') else -1.0
                    ax_idx = 0 if ax == 'x' else 1 if ax == 'y' else 2
                    outer_off = max(max_extent * 0.3, size * 3.0)
                    off_pos = list(pos)
                    off_pos[ax_idx] += off_dir * outer_off
                    self.points_3d[key] = np.array(off_pos)
                    sx, sy, _ = gluProject(off_pos[0], off_pos[1], off_pos[2],
                        modelview, projection, viewport)
                    self.points_2d[key] = np.array([sx, viewport[3] - sy])
                    ih = (self.hover == key)
                    self.draw_face_handle(np.array(off_pos), ax, size, key, ih)
                except Exception as e:
                    print(f"[TriviumCAD] gizmo.render (face handle): {e}")
        except Exception as e:
            print(f"Errore in gizmo render: {e}")

    def pick_handle(self, position, device_pixel_ratio):
        try:
            if not self.points_2d:
                return None
            mouse_x = position.x() * device_pixel_ratio
            mouse_y = position.y() * device_pixel_ratio
            tolerance = 30
            best_key = None
            best_dist = tolerance
            for key, (screen_x, screen_y) in self.points_2d.items():
                dist = math.hypot(mouse_x - screen_x, mouse_y - screen_y)
                if dist < best_dist:
                    best_dist = dist
                    best_key = key
            if best_key:
                self.hover = best_key
                if best_key.startswith('rot_') and len(best_key) > 5:
                    rot_base = best_key[:5]
                    self.hover = rot_base
                    return rot_base
                if best_key.startswith('rh') and len(best_key) >= 4:
                    rot_base = 'rot_' + best_key[2]
                    self.hover = rot_base
                    return rot_base
                return best_key
            self.hover = None
            return None
        except Exception as e:
            print(f"Errore in gizmo pick_handle: {e}")
            return None

    def get_rotation_angle(self, pos, device_pixel_ratio, modelview, projection, viewport, scene):
        try:
            if not scene.has_selection:
                return None
            sel = scene.selected_objects
            centroid = np.mean([o.centroid for o in sel], axis=0)
            sx, sy, _ = gluProject(centroid[0], centroid[1], centroid[2],
                modelview, projection, viewport)
            sc = np.array([sx, viewport[3] - sy])
            dx = pos.x() * device_pixel_ratio - sc[0]
            dy = pos.y() * device_pixel_ratio - sc[1]
            return math.atan2(dy, dx)
        except Exception as e:
            print(f"[TriviumCAD] gizmo.get_rotation_angle: {e}")
            return None

    def get_rotation_speed(self, modelview, projection, viewport, scene):
        try:
            if not scene.has_selection:
                return 0.01
            sel = scene.selected_objects
            centroid = np.mean([o.centroid for o in sel], axis=0)
            sx, sy, _ = gluProject(centroid[0], centroid[1], centroid[2],
                modelview, projection, viewport)
            ring_world = centroid + np.array([1.0, 0, 0])
            sx2, _, _ = gluProject(ring_world[0], ring_world[1], ring_world[2],
                modelview, projection, viewport)
            px_per_unit = max(1.0, abs(sx2 - sx))
            bounds = [np.min([o.centroid for o in sel], axis=0),
                      np.max([o.centroid for o in sel], axis=0)]
            max_extent = max(bounds[1] - bounds[0])
            ring_r = max_extent * 1.0
            screen_radius = ring_r * px_per_unit
            return 1.0 / max(10.0, screen_radius)
        except Exception as e:
            print(f"[TriviumCAD] gizmo.get_rotation_speed: {e}")
            return 0.01

    @staticmethod
    def draw_handle(position, axis, size, is_hovered=False):
        try:
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT)
            glDisable(GL_LIGHTING)
            if axis == 'x':
                base_color = [0.8, 0.3, 0.3, 0.95]
            elif axis == 'y':
                base_color = [0.3, 0.8, 0.3, 0.95]
            elif axis == 'z':
                base_color = [0.3, 0.3, 0.8, 0.95]
            elif axis == 'uniform':
                base_color = [0.8, 0.8, 0.3, 0.95]
            else:
                base_color = [0.6, 0.6, 0.6, 0.95]
            if is_hovered:
                color = [min(c * 1.2, 1.0) for c in base_color]
            else:
                color = base_color
            glColor4f(*color)
            glPushMatrix()
            glTranslatef(position[0], position[1], position[2])
            s = size * 1.5
            glBegin(GL_QUADS)
            for vx, vy, vz in [(-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s),
                             (-s, -s, -s), (-s, s, -s), (s, s, -s), (s, -s, -s)]:
                glVertex3f(vx, vy, vz)
            glEnd()
            if is_hovered:
                glLineWidth(3.0)
                glColor4f(1.0, 1.0, 1.0, 1.0)
                glBegin(GL_LINE_LOOP)
                glVertex3f(-s, -s, s); glVertex3f(s, -s, s); glVertex3f(s, s, s); glVertex3f(-s, s, s)
                glEnd()
                glBegin(GL_LINE_LOOP)
                glVertex3f(-s, -s, -s); glVertex3f(-s, s, -s); glVertex3f(s, s, -s); glVertex3f(s, -s, -s)
                glEnd()
                glBegin(GL_LINES)
                glVertex3f(-s, -s, s); glVertex3f(-s, -s, -s)
                glVertex3f(s, -s, s); glVertex3f(s, -s, -s)
                glVertex3f(s, s, s); glVertex3f(s, s, -s)
                glVertex3f(-s, s, s); glVertex3f(-s, s, -s)
                glEnd()
            glPopMatrix()
            glPopAttrib()
        except Exception as e:
            print(f"Errore in draw_handle: {e}")

    @staticmethod
    def draw_face_handle(position, axis, size, key, is_hovered=False):
        try:
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT)
            glDisable(GL_LIGHTING)
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            s = size * 2.0
            arrow_len = s * 0.8
            ax_idx = 0 if axis == 'x' else 1 if axis == 'y' else 2
            if axis == 'x':
                col = [0.95, 0.3, 0.3]
            elif axis == 'y':
                col = [0.3, 0.95, 0.3]
            else:
                col = [0.3, 0.3, 0.95]
            if is_hovered:
                col = [min(c*1.3, 1.0) for c in col]
            glPushMatrix()
            glTranslatef(position[0], position[1], position[2])
            i = (ax_idx + 1) % 3
            j = (ax_idx + 2) % 3
            off_dir = 1.0 if key.endswith('+') else -1.0

            # Square outline
            glLineWidth(3.0)
            glColor4f(col[0], col[1], col[2], 0.9)
            glBegin(GL_LINE_LOOP)
            for du, dv in [(-1,-1), (1,-1), (1,1), (-1,1)]:
                pt = [0.0, 0.0, 0.0]; pt[i] = du*s; pt[j] = dv*s
                glVertex3f(*pt)
            glEnd()

            # Filled square
            glColor4f(col[0], col[1], col[2], 0.15)
            glBegin(GL_QUADS)
            for du, dv in [(-1,-1), (1,-1), (1,1), (-1,1)]:
                pt = [0.0, 0.0, 0.0]; pt[i] = du*s; pt[j] = dv*s
                glVertex3f(*pt)
            glEnd()

            # Arrow shaft
            glLineWidth(2.5)
            glColor4f(col[0], col[1], col[2], 1.0)
            glBegin(GL_LINES)
            tip = [0.0, 0.0, 0.0]; tip[ax_idx] = off_dir * arrow_len
            glVertex3f(0, 0, 0)
            glVertex3f(*tip)
            glEnd()

            # Arrowhead (pyramid a 4 lati)
            aw = s * 0.3
            glColor4f(col[0], col[1], col[2], 1.0)
            base_ax = off_dir * arrow_len * 0.7
            tip_ax = off_dir * arrow_len
            base_pts = [(aw, aw), (-aw, aw), (-aw, -aw), (aw, -aw)]
            glBegin(GL_TRIANGLE_FAN)
            glVertex3f(0, 0, tip_ax)
            for du, dv in base_pts:
                pt = [0.0, 0.0, 0.0]; pt[i]=du; pt[j]=dv; pt[ax_idx]=base_ax
                glVertex3f(*pt)
            glVertex3f(aw, aw, base_ax)
            glEnd()

            glPopMatrix()
            glPopAttrib()
        except Exception as e:
            print(f"Errore in draw_face_handle: {e}")

    @staticmethod
    def draw_scale_handle(position, axis, size, is_hovered=False):
        try:
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT)
            glDisable(GL_LIGHTING)
            glDisable(GL_CULL_FACE)
            if axis == 'x':
                base_color = [0.9, 0.5, 0.5, 0.95]
            elif axis == 'y':
                base_color = [0.5, 0.9, 0.5, 0.95]
            else:
                base_color = [0.5, 0.5, 0.9, 0.95]
            if is_hovered:
                color = [min(c * 1.2, 1.0) for c in base_color]
            else:
                color = base_color
            glColor4f(*color)
            glPushMatrix()
            glTranslatef(position[0], position[1], position[2])
            s = size * 0.6
            for apex, base in [((0,s,0), [(s,0,-s),(s,0,s),(-s,0,s),(-s,0,-s)])]:
                for i in range(4):
                    glBegin(GL_TRIANGLES)
                    glVertex3f(*apex)
                    glVertex3f(*base[i])
                    glVertex3f(*base[(i+1)%4])
                    glEnd()
            for apex, base in [((0,-s,0), [(s,0,s),(s,0,-s),(-s,0,-s),(-s,0,s)])]:
                for i in range(4):
                    glBegin(GL_TRIANGLES)
                    glVertex3f(*apex)
                    glVertex3f(*base[i])
                    glVertex3f(*base[(i+1)%4])
                    glEnd()
            if is_hovered:
                glLineWidth(2.0)
                glColor4f(1,1,1,1)
                glBegin(GL_LINE_LOOP)
                for v in [(s,0,-s),(s,0,s),(-s,0,s),(-s,0,-s)]:
                    glVertex3f(*v)
                glEnd()
            glPopMatrix()
            glPopAttrib()
        except Exception as e:
            print(f"Errore in draw_scale_handle: {e}")

    @staticmethod
    def draw_rot_handle(position, size, is_hovered=False):
        try:
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT)
            glDisable(GL_LIGHTING)
            base_color = [0.55, 0.55, 0.6, 0.95] if not is_hovered else [0.75, 0.75, 0.8, 1.0]
            glColor4f(*base_color)
            glPushMatrix()
            glTranslatef(position[0], position[1], position[2])
            sphere = gluNewQuadric()
            gluSphere(sphere, size, 16, 12)
            gluDeleteQuadric(sphere)
            glPopMatrix()
            if is_hovered:
                glLineWidth(2.0)
                glColor4f(1,1,1,1)
                glBegin(GL_LINE_LOOP)
                s = size * 1.1
                for i in range(24):
                    a = 2 * math.pi * i / 24
                    glVertex3f(s*math.cos(a), s*math.sin(a), 0)
                glEnd()
                glBegin(GL_LINE_LOOP)
                for i in range(24):
                    a = 2 * math.pi * i / 24
                    glVertex3f(s*math.cos(a), 0, s*math.sin(a))
                glEnd()
            glPopAttrib()
        except Exception as e:
            print(f"Errore in draw_rot_handle: {e}")

    @staticmethod
    def draw_vertical_handle(position, is_hovered=False):
        try:
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_LIGHTING_BIT | GL_POLYGON_BIT)
            glEnable(GL_LIGHTING)
            glEnable(GL_NORMALIZE)
            base_color = [0.3, 0.8, 0.3, 0.95]
            if is_hovered:
                color = [min(c * 1.2, 1.0) for c in base_color]
            else:
                color = base_color
            glColor4f(*color)
            glPushMatrix()
            glTranslatef(position[0], position[1], position[2])
            stem_radius = 0.6
            stem_half = 1.8
            tip_radius = 1.0
            tip_height = 0.8
            quadric = gluNewQuadric()
            gluCylinder(quadric, stem_radius, stem_radius, stem_half * 2, 32, 1)
            gluDisk(quadric, 0, stem_radius, 32, 1)
            glTranslatef(0, 0, stem_half * 2)
            gluCylinder(quadric, 0, tip_radius, tip_height, 32, 1)
            glTranslatef(0, 0, -stem_half * 2 - tip_height)
            glRotatef(180, 1, 0, 0)
            gluCylinder(quadric, 0, tip_radius, tip_height, 32, 1)
            glRotatef(-180, 1, 0, 0)
            glTranslatef(0, 0, tip_height)
            gluDisk(quadric, 0, stem_radius, 32, 1)
            if is_hovered:
                glDisable(GL_LIGHTING)
                glLineWidth(2.0)
                glColor4f(1.0, 1.0, 1.0, 1.0)
                glBegin(GL_LINE_LOOP)
                for i in range(32):
                    angle = 2 * math.pi * i / 32
                    dx = stem_radius * math.cos(angle)
                    dy = stem_radius * math.sin(angle)
                    glVertex3f(dx, dy, 0)
                glEnd()
                glBegin(GL_LINE_LOOP)
                for i in range(32):
                    angle = 2 * math.pi * i / 32
                    dx = stem_radius * math.cos(angle)
                    dy = stem_radius * math.sin(angle)
                    glVertex3f(dx, dy, stem_half * 2)
                glEnd()
            glPopMatrix()
            glPopAttrib()
        except Exception as e:
            print(f"Errore in draw_vertical_handle: {e}")

    @staticmethod
    def draw_uniform_scale_handle(position, is_hovered=False):
        if not is_hovered:
            return
        try:
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_LIGHTING_BIT | GL_POLYGON_BIT)
            glEnable(GL_LIGHTING)
            glEnable(GL_NORMALIZE)
            color = [0.95, 0.95, 0.4, 1.0]
            glColor4f(*color)
            glPushMatrix()
            glTranslatef(position[0], position[1], position[2])
            sphere = gluNewQuadric()
            gluSphere(sphere, 0.8, 32, 32)
            if is_hovered:
                glDisable(GL_LIGHTING)
                glLineWidth(2.0)
                glColor4f(1.0, 1.0, 1.0, 1.0)
                glBegin(GL_LINE_LOOP)
                for i in range(32):
                    angle = 2 * math.pi * i / 32
                    x = 0.8 * math.cos(angle)
                    y = 0.8 * math.sin(angle)
                    glVertex3f(x, y, 0)
                glEnd()
                glBegin(GL_LINE_LOOP)
                for i in range(32):
                    angle = 2 * math.pi * i / 32
                    x = 0.8 * math.cos(angle)
                    z = 0.8 * math.sin(angle)
                    glVertex3f(x, 0, z)
                glEnd()
                glBegin(GL_LINE_LOOP)
                for i in range(32):
                    angle = 2 * math.pi * i / 32
                    y = 0.8 * math.cos(angle)
                    z = 0.8 * math.sin(angle)
                    glVertex3f(0, y, z)
                glEnd()
            glPopMatrix()
            glPopAttrib()
        except Exception as e:
            print(f"Errore in draw_uniform_scale_handle: {e}")

    @staticmethod
    def draw_axis(start, direction, color, length, line_width=1.5, is_hovered=False):
        try:
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT)
            glDisable(GL_LIGHTING)
            if is_hovered:
                color = [min(c * 1.2, 1.0) for c in color]
            glColor4f(*color)
            glLineWidth(line_width)
            glBegin(GL_LINES)
            glVertex3f(start[0], start[1], start[2])
            glVertex3f(
                start[0] + direction[0] * length,
                start[1] + direction[1] * length,
                start[2] + direction[2] * length)
            glEnd()
            if is_hovered:
                arrow_size = length * 0.15
                end_pos = [
                    start[0] + direction[0] * length,
                    start[1] + direction[1] * length,
                    start[2] + direction[2] * length]
                glLineWidth(1.0)
                glBegin(GL_LINES)
                glVertex3f(end_pos[0], end_pos[1], end_pos[2])
                glVertex3f(
                    end_pos[0] - direction[0] * arrow_size + direction[1] * arrow_size,
                    end_pos[1] - direction[1] * arrow_size + direction[2] * arrow_size,
                    end_pos[2] - direction[2] * arrow_size + direction[0] * arrow_size)
                glVertex3f(end_pos[0], end_pos[1], end_pos[2])
                glVertex3f(
                    end_pos[0] - direction[0] * arrow_size - direction[1] * arrow_size,
                    end_pos[1] - direction[1] * arrow_size - direction[2] * arrow_size,
                    end_pos[2] - direction[2] * arrow_size - direction[0] * arrow_size)
                glEnd()
            glPopAttrib()
        except Exception as e:
            print(f"Errore in draw_axis: {e}")

# =============================================================================
# BLOCCO 2: OPENGL WIDGET (CON TUTTE LE CORREZIONI RICHIESTE)
# =============================================================================
# === OPENGL WIDGET ===
class GLWidget(QOpenGLWidget):
    def __init__(self, scene, window):
        super().__init__()
        self.scene = scene
        self.window = window
        self.rotation = [-35, -45]
        self.rotation_z = 0.0
        self.distance = 150.0
        self.pan = [0, 0, 0]
        self.interaction_mode = 'NONE'
        self.last_position = None
        self.drag_start_mouse = np.array([0, 0])
        self.drag_offset = None
        self.rotate_start_angle = 0.0
        self.rotation_drag_speed = 0.005
        self.drag_speed = 0.25
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.sketch_mode = False
        self.sketch_tool = "line"
        self.sketch_points = []
        self.cam_mode = False
        self.angle_points = []
        self.device_pixel_ratio = 1.0
        self.physical_width = 1000
        self.physical_height = 800
        self.gizmo = GizmoRenderer()
        self._gl_ready = False
        self.frames = 0
        self._modelview_matrix = None
        self._projection_matrix = None
        self._viewport = None
        self._drag_modelview = None
        self._drag_projection = None
        self._drag_viewport = None
        self._drag_target = None
        self._grid_display_list = None
        self.selection_box_start = None
        self.selection_box_end = None
        self.selection_mode = False
        self.drag_threshold = 3
        self.click_handled = False
        self.dragging = False
        self.mouse_pressed = False
        self.mouse_button = Qt.NoButton
        self._rotz_pivot = None
        self.uniform_scale_start_pos = None
        self.uniform_scale_start_extents = None
        self.drag_face_axis = None
        self.drag_face_sign = None
        self.drag_face_orig_verts = None
        self.drag_face_accum_delta = 0.0
    
    def initializeGL(self):
        try:
            glClearColor(0.06, 0.06, 0.08, 1.0)
            glClearDepth(1.0)
            
            glEnable(GL_DEPTH_TEST)
            glDepthFunc(GL_LEQUAL)
            glDepthMask(GL_TRUE)
            
            glEnable(GL_CULL_FACE)
            glCullFace(GL_BACK)
            glFrontFace(GL_CCW)
            
            glDisable(GL_BLEND)
            glShadeModel(GL_SMOOTH)
            glHint(GL_PERSPECTIVE_CORRECTION_HINT, GL_NICEST)
            
            glEnable(GL_MULTISAMPLE)
            
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glEnable(GL_LIGHT1)
            glEnable(GL_COLOR_MATERIAL)
            glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.3, 0.3, 0.3, 1.0])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
            
            glLightfv(GL_LIGHT0, GL_AMBIENT, [0.5, 0.5, 0.5, 1.0])
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1.0])
            glLightfv(GL_LIGHT0, GL_SPECULAR, [0.3, 0.3, 0.3, 1.0])
            glLightfv(GL_LIGHT0, GL_POSITION, [300.0, 300.0, 400.0, 0.0])
            
            glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.3, 0.3, 0.4, 1.0])
            glLightfv(GL_LIGHT1, GL_POSITION, [-200.0, -150.0, 200.0, 0.0])
            
            glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
            
            glEnable(GL_NORMALIZE)
            
            glDisable(GL_POLYGON_OFFSET_LINE)
            glDisable(GL_POLYGON_OFFSET_FILL)
            
            self._grid_display_list = None
            self._gl_ready = True
            self.update()
        except Exception as e:
            print(f"Errore critico in initializeGL: {e}")
            self._gl_ready = False
    
    def resizeGL(self, width, height):
        try:
            self.device_pixel_ratio = self.devicePixelRatioF()
            if self.device_pixel_ratio <= 0:
                self.device_pixel_ratio = 1.0
            
            if width <= 0 or height <= 0:
                return
            
            physical_width = int(width * self.device_pixel_ratio)
            physical_height = int(height * self.device_pixel_ratio)
            
            if physical_width <= 0 or physical_height <= 0:
                return
            
            self.physical_width = physical_width
            self.physical_height = physical_height
            
            glViewport(0, 0, physical_width, physical_height)
        except Exception as e:
            print(f"Errore in resizeGL: {e}")
    
    def paintGL(self):
        if not self._gl_ready or not self.isValid():
            return
        
        try:
            width = self.width()
            height = self.height()
            if width <= 0 or height <= 0:
                return
            
            self.device_pixel_ratio = self.devicePixelRatioF()
            if self.device_pixel_ratio <= 0:
                self.device_pixel_ratio = 1.0
            
            physical_width = int(width * self.device_pixel_ratio)
            physical_height = int(height * self.device_pixel_ratio)
            self.physical_width = physical_width
            self.physical_height = physical_height
            
            glViewport(0, 0, physical_width, physical_height)
            
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            
            glDisable(GL_BLEND)
            glDepthMask(GL_TRUE)
            glEnable(GL_DEPTH_TEST)
            glDepthFunc(GL_LEQUAL)
            
            if not self.mouse_pressed or self.interaction_mode not in ('DRAG_HANDLE', 'DRAG_VERTICAL', 'DRAG_UNIFORM_SCALE', 'DRAG_ROTATE', 'DRAG_FACE'):
                self._drag_target = None
            
            self._sync_camera(width, height)
            
            self._grid()
            
            selected_set = set(self.scene.selected_objects)
            for obj in self.scene.objects:
                layer = obj.metadata.get("layer", "Default")
                if not self.scene.layers.get(layer, {}).get("visible", True):
                    continue
                if not obj.metadata.get("visible", True):
                    continue
                if obj in selected_set:
                    self._draw_shadow(obj)
                    self._draw_mesh(obj, True)
                else:
                    self._draw_mesh(obj, False)
            
            if self.scene.has_selection and not self.sketch_mode:
                self.gizmo.render(self._modelview_matrix, self._projection_matrix, self._viewport, self.scene, self.distance)
            
            self._draw_rulers_qt()
            self._draw_goniometer_labels()
            self._draw_measurement_overlay()
            
            if self.selection_mode and self.selection_box_start and self.selection_box_end:
                self._draw_selection_box()
            
            self._draw_toolpaths()
            
            self.frames += 1
        except Exception as e:
            print(f"Errore in paintGL: {e}")
    
    def _draw_shadow(self, mesh):
        try:
            if not hasattr(mesh, 'vertices') or len(mesh.vertices) == 0:
                return
            verts = mesh.vertices.astype(np.float32)
            faces = mesh.faces.astype(np.uint32) if hasattr(mesh, 'faces') else None
            min_z = float(np.min(verts[:, 2]))
            max_z = float(np.max(verts[:, 2]))
            below = min_z < -0.01
            if max_z < -0.01:
                return
            
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_DEPTH_BUFFER_BIT | GL_LINE_BIT)
            glDisable(GL_LIGHTING)
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_LINE_SMOOTH)
            
            # -- Contact contour (intersection mesh-plane Z=0) --
            if faces is not None and len(faces) > 0:
                contour_pts = []
                for tri in faces:
                    v = verts[tri]
                    z = v[:, 2]
                    # edges that cross Z=0
                    pts = []
                    for e in [(0,1),(1,2),(2,0)]:
                        a, b = v[e[0]], v[e[1]]
                        if (a[2] <= 0 and b[2] > 0) or (a[2] > 0 and b[2] <= 0):
                            t = -a[2] / (b[2] - a[2]) if b[2] != a[2] else 0.5
                            pts.append(a + t * (b - a))
                    if len(pts) == 2:
                        contour_pts.append(pts[0])
                        contour_pts.append(pts[1])
                
                if contour_pts:
                    contour_arr = np.array(contour_pts, dtype=np.float32)
                    # Draw the filled contact area (semi-transparent)
                    glColor4f(0.0, 1.0, 0.3, 0.15) if not below else glColor4f(1.0, 0.0, 0.0, 0.15)
                    glBegin(GL_TRIANGLES)
                    for i in range(0, len(contour_arr) - 1, 2):
                        if i + 2 < len(contour_arr):
                            c0, c1, c2 = contour_arr[i], contour_arr[i+1], contour_arr[(i+2) % len(contour_arr)]
                            c0[2] = c1[2] = c2[2] = 0
                            glVertex3fv(c0); glVertex3fv(c1); glVertex3fv(c2)
                    glEnd()
                    # Draw the contour line (thick, bright)
                    line_color = [1.0, 0.0, 0.0, 0.9] if below else [0.0, 1.0, 0.3, 0.9]
                    glColor4f(*line_color)
                    glLineWidth(3.0)
                    # Connect consecutive segment endpoints
                    glBegin(GL_LINE_LOOP)
                    for pt in contour_pts:
                        glVertex3f(pt[0], pt[1], 0)
                    glEnd()
            
            # -- Contact point marker (lowest vertex projected) --
            idx = np.argmin(verts[:, 2])
            contact = verts[idx].copy()
            contact[2] = 0.0
            marker_color = [1.0, 0.0, 0.0, 0.95] if below else [0.0, 1.0, 0.3, 0.95]
            r = max(2.0, abs(min_z) * 0.5 + 3.0) if below else 4.0
            
            # Filled circle at contact point
            glColor4f(marker_color[0], marker_color[1], marker_color[2], 0.3)
            glBegin(GL_TRIANGLE_FAN)
            glVertex3fv(contact)
            for i in range(25):
                a = 2 * math.pi * i / 24
                glVertex3f(contact[0] + r * math.cos(a), contact[1] + r * math.sin(a), 0)
            glEnd()
            
            # Outer ring
            glColor4f(*marker_color)
            glLineWidth(2.5)
            glBegin(GL_LINE_LOOP)
            for i in range(24):
                a = 2 * math.pi * i / 24
                glVertex3f(contact[0] + r * math.cos(a), contact[1] + r * math.sin(a), 0)
            glEnd()
            
            # Crosshair
            glColor4f(*marker_color)
            glLineWidth(1.5)
            glBegin(GL_LINES)
            glVertex3f(contact[0] - r*2.5, contact[1], 0)
            glVertex3f(contact[0] + r*2.5, contact[1], 0)
            glVertex3f(contact[0], contact[1] - r*2.5, 0)
            glVertex3f(contact[0], contact[1] + r*2.5, 0)
            glEnd()
            
            # Center dot
            glPointSize(6.0)
            glColor4f(marker_color[0], marker_color[1], marker_color[2], 1.0)
            glBegin(GL_POINTS)
            glVertex3fv(contact)
            glEnd()
            
            if below:
                # Depth line from contact to actual lowest point
                glColor4f(1.0, 0.0, 0.0, 0.5)
                glLineWidth(1.5)
                glBegin(GL_LINES)
                glVertex3f(contact[0], contact[1], 0)
                glVertex3f(contact[0], contact[1], min_z)
                glEnd()
                
                # Depth marker ticks
                glColor4f(1.0, 0.0, 0.0, 0.7)
                glLineWidth(1.0)
                depth = abs(min_z)
                tick_size = r * 0.5
                for dz in np.arange(0, depth + 0.1, 1.0):
                    if dz > 0 and dz <= depth:
                        z_pos = -dz
                        glBegin(GL_LINES)
                        glVertex3f(contact[0] - tick_size, contact[1], z_pos)
                        glVertex3f(contact[0] + tick_size, contact[1], z_pos)
                        glEnd()
            
            glPopAttrib()
        except Exception as e:
            print(f"[TriviumCAD] _draw_shadow: {e}")
    
    def _draw_selection_box(self):
        try:
            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()
            gluOrtho2D(0, self.width(), self.height(), 0)
            
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            glLoadIdentity()
            
            glDisable(GL_DEPTH_TEST)
            
            glColor4f(0.3, 0.6, 1.0, 0.2)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            
            x1, y1 = self.selection_box_start
            x2, y2 = self.selection_box_end
            
            glBegin(GL_QUADS)
            glVertex2f(x1, y1)
            glVertex2f(x2, y1)
            glVertex2f(x2, y2)
            glVertex2f(x1, y2)
            glEnd()
            
            glColor4f(0.3, 0.6, 1.0, 0.8)
            glLineWidth(1.5)
            glBegin(GL_LINE_LOOP)
            glVertex2f(x1, y1)
            glVertex2f(x2, y1)
            glVertex2f(x2, y2)
            glVertex2f(x1, y2)
            glEnd()
            
            glDisable(GL_BLEND)
            glEnable(GL_DEPTH_TEST)
            
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopMatrix()
        except Exception as e:
            print(f"Errore nel disegnare la box di selezione: {e}")
    
    def _sync_camera(self, width, height):
        try:
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            
            if self.sketch_mode:
                glOrtho(-width / 2, width / 2, -height / 2, height / 2, -5000, 5000)
            else:
                aspect_ratio = self.physical_width / self.physical_height if self.physical_height > 0 else 1
                far_plane = max(1000.0, self.distance * 5)
                gluPerspective(45.0, aspect_ratio, 0.5, far_plane)
            
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            
            if not self.sketch_mode:
                gluLookAt(0, 0, self.distance, 0, 0, 0, 0, 1, 0)
                glTranslatef(*self.pan)
                glRotatef(self.rotation[0], 1, 0, 0)
                glRotatef(self.rotation[1], 0, 1, 0)
                # Z rotation: centra sulla selezione solo durante ROT_Z attivo
                if self.interaction_mode == 'ROT_Z' and self.scene.has_selection:
                    centers = [o.centroid for o in self.scene.selected_objects if hasattr(o, 'centroid')]
                    target = np.mean(centers, axis=0) if centers else np.zeros(3)
                    self._rotz_pivot = target.copy()
                else:
                    target = self._rotz_pivot if self._rotz_pivot is not None else np.zeros(3)
                if np.linalg.norm(target) > 1e-8:
                    glTranslatef(target[0], target[1], target[2])
                    glRotatef(self.rotation_z, 0, 0, 1)
                    glTranslatef(-target[0], -target[1], -target[2])
                else:
                    glRotatef(self.rotation_z, 0, 0, 1)
            
            self._modelview_matrix = glGetDoublev(GL_MODELVIEW_MATRIX)
            self._projection_matrix = glGetDoublev(GL_PROJECTION_MATRIX)
            self._viewport = glGetIntegerv(GL_VIEWPORT)
        except Exception as e:
            print(f"Errore in _sync_camera: {e}")
    
    def _invalidate_all_vbos(self):
        for obj in self.scene.objects:
            obj.metadata.pop('_gl_verts', None)
            obj.metadata.pop('_gl_normals', None)

    def _draw_mesh(self, mesh, is_selected):
        try:
            if not hasattr(mesh, 'vertices') or len(mesh.vertices) == 0:
                return
            
            if "_gl_verts" not in mesh.metadata:
                # Clean up stale VBOs
                if "_gl_vbo_verts" in mesh.metadata:
                    glDeleteBuffers(2, [mesh.metadata.pop("_gl_vbo_verts"), mesh.metadata.pop("_gl_vbo_normals")])
                    del mesh.metadata["_gl_vbo_count"]
                
                verts = mesh.vertices.astype(np.float32)
                faces = mesh.faces.astype(np.uint32)
                expanded_verts = np.ascontiguousarray(verts[faces.ravel()])
                mesh.metadata["_gl_verts"] = expanded_verts
                mesh.metadata["_gl_vbo_count"] = len(expanded_verts)
                
                # Vertex normals (smooth) if available, fallback to face normals
                if hasattr(mesh, 'vertex_normals') and mesh.vertex_normals is not None and len(mesh.vertex_normals) == len(mesh.vertices):
                    vert_normals = mesh.vertex_normals.astype(np.float32)
                else:
                    vert_normals = np.repeat(mesh.face_normals.astype(np.float32), 3, axis=0)
                expanded_normals = np.ascontiguousarray(vert_normals[faces.ravel()])
                mesh.metadata["_gl_normals"] = expanded_normals
                
                # Create VBOs
                vbo_verts = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, vbo_verts)
                glBufferData(GL_ARRAY_BUFFER, expanded_verts.nbytes, expanded_verts, GL_STATIC_DRAW)
                vbo_normals = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, vbo_normals)
                glBufferData(GL_ARRAY_BUFFER, expanded_normals.nbytes, expanded_normals, GL_STATIC_DRAW)
                glBindBuffer(GL_ARRAY_BUFFER, 0)
                mesh.metadata["_gl_vbo_verts"] = vbo_verts
                mesh.metadata["_gl_vbo_normals"] = vbo_normals
            
            num_verts = mesh.metadata["_gl_vbo_count"]
            
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)
            
            glBindBuffer(GL_ARRAY_BUFFER, mesh.metadata["_gl_vbo_verts"])
            glVertexPointer(3, GL_FLOAT, 0, None)
            glBindBuffer(GL_ARRAY_BUFFER, mesh.metadata["_gl_vbo_normals"])
            glNormalPointer(GL_FLOAT, 0, None)
            
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_POLYGON_BIT | GL_LIGHTING_BIT | GL_DEPTH_BUFFER_BIT)
            try:
                glDisable(GL_BLEND)
                glDepthMask(GL_TRUE)
                glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
                glEnable(GL_CULL_FACE)
                glCullFace(GL_BACK)
                glFrontFace(GL_CCW)
                
                glEnable(GL_LIGHTING)
                glShadeModel(GL_SMOOTH)
                
                color = mesh.metadata.get("color", NEUTRAL_COLORS[0])
                if len(color) == 3:
                    color = [*color, 1.0]
                if is_selected:
                    color = [0.3, 0.6, 1.0, 1.0]
                glColor4f(color[0], color[1], color[2], color[3] if len(color)>3 else 1.0)
                
                glDrawArrays(GL_TRIANGLES, 0, num_verts)
            finally:
                glPopAttrib()
            
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)
        except Exception as e:
            print(f"Errore in _draw_mesh: {e}")
    
    def _draw_toolpaths(self):
        if not self.scene.gcode_paths:
            return
        
        glDisable(GL_LIGHTING)
        glLineWidth(2.0)
        
        for path in self.scene.gcode_paths:
            if path["type"] == "ext":
                glColor3f(0.2, 0.8, 0.2)
                glBegin(GL_LINE_STRIP)
                for x, y, z in path["pts"]:
                    glVertex3f(x, y, z)
                glEnd()
        
        glEnable(GL_LIGHTING)
    
    def _grid(self):
        try:
            if self._grid_display_list is None:
                self._grid_display_list = glGenLists(1)
                glNewList(self._grid_display_list, GL_COMPILE)
                extent = 500
                glBegin(GL_LINES)
                for i in range(-extent, extent + 1, 1):
                    if i == 0:
                        color = [0.45, 0.45, 0.55]
                    elif i % 100 == 0:
                        color = [0.30, 0.30, 0.40]
                    elif i % 10 == 0:
                        color = [0.22, 0.22, 0.30]
                    else:
                        color = [0.14, 0.14, 0.20]
                    glColor3f(*color)
                    glVertex3f(i, -extent, 0)
                    glVertex3f(i, extent, 0)
                    glVertex3f(-extent, i, 0)
                    glVertex3f(extent, i, 0)
                glEnd()
                glLineWidth(2.0)
                glBegin(GL_LINES)
                glColor3f(0.50, 0.50, 0.55)
                glVertex3f(-extent, 0, 0)
                glVertex3f(extent, 0, 0)
                glColor3f(0.50, 0.50, 0.55)
                glVertex3f(0, -extent, 0)
                glVertex3f(0, extent, 0)
                glColor3f(0.50, 0.50, 0.55)
                glVertex3f(0, 0, -extent)
                glVertex3f(0, 0, extent)
                glEnd()
                glLineWidth(2.0)
                glBegin(GL_LINES)
                glColor3f(0.30, 0.40, 0.55)
                glVertex3f(-extent, -extent, 0)
                glVertex3f(extent, -extent, 0)
                glVertex3f(extent, -extent, 0)
                glVertex3f(extent, extent, 0)
                glVertex3f(extent, extent, 0)
                glVertex3f(-extent, extent, 0)
                glVertex3f(-extent, extent, 0)
                glVertex3f(-extent, -extent, 0)
                glEnd()
                glEndList()
            
            glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_LINE_BIT | GL_DEPTH_BUFFER_BIT)
            glDisable(GL_LIGHTING)
            glDisable(GL_DEPTH_TEST)
            glLineWidth(1.0)
            glCallList(self._grid_display_list)
            glPopAttrib()
        except Exception as e:
            print(f"Errore in _grid: {e}")
    
    def _draw_rulers_qt(self):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w = self.width()
            h = self.height()
            ruler_sz = 18
            p.fillRect(0, 0, w, ruler_sz, QColor(35, 35, 45, 200))
            p.fillRect(0, ruler_sz, ruler_sz, h - ruler_sz, QColor(35, 35, 45, 200))
            p.setPen(QPen(QColor(160, 160, 180), 1))
            step = 50
            for x in range(step, w, step):
                p.drawLine(x, 0, x, ruler_sz // 2)
            for y in range(ruler_sz + step, h, step):
                p.drawLine(0, y, ruler_sz // 2, y)
            p.setPen(QPen(QColor(200, 200, 220), 1))
            f = QFont("Segoe UI", 7)
            p.setFont(f)
            for x in range(step, w, step):
                p.drawText(x - 10, ruler_sz - 2, 20, 10, 0x0080, str(x))
            for y in range(ruler_sz + step, h, step):
                p.drawText(1, y - 5, ruler_sz - 2, 10, 0x0084, str(y))
            p.end()
        except Exception as e:
            print(f"Errore in _draw_rulers_qt: {e}")
    
    def _draw_goniometer_labels(self):
        try:
            labels = self.gizmo.angle_labels_2d if hasattr(self, 'gizmo') else []
            if not labels:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            f = QFont("Segoe UI", 8, QFont.Bold)
            p.setFont(f)
            p.setPen(QPen(QColor(200, 200, 220, 220), 1))
            for sx, sy, text in labels:
                p.drawText(int(sx) - 12, int(sy) - 10, 24, 20, 0x0084, text)
            p.end()
        except Exception as e:
            print(f"Errore in _draw_goniometer_labels: {e}")
    
    def _screen_to_ray(self, x, y):
        try:
            if self._modelview_matrix is None or self._projection_matrix is None or self._viewport is None:
                return None, None
            mv = self._modelview_matrix
            pr = self._projection_matrix
            vp = self._viewport
            mx = x * self.device_pixel_ratio
            my = (self.height() - y) * self.device_pixel_ratio
            near = gluUnProject(mx, my, 0.0, mv, pr, vp)
            far = gluUnProject(mx, my, 1.0, mv, pr, vp)
            if near is None or far is None:
                return None, None
            origin = np.array([near[0], near[1], near[2]])
            direction = np.array([far[0] - near[0], far[1] - near[1], far[2] - near[2]])
            norm = np.linalg.norm(direction)
            if norm > 1e-8:
                direction /= norm
            return origin, direction
        except Exception as e:
            print(f"Errore in _screen_to_ray: {e}")
            return None, None
    
    def _pick_object(self, position):
        try:
            if self.scene._needs_spatial_rebuild:
                self.scene._rebuild_spatial_index()
            ray_origin, ray_direction = self._screen_to_ray(position.x(), position.y())
            if ray_origin is None or ray_direction is None:
                return None
            if self.scene._spatial_index is not None:
                nearby = self.scene._get_nearby_objects(ray_origin, radius=500.0)
            else:
                nearby = self.scene.objects[:]
            best_obj = None
            best_dist = float('inf')
            for obj in nearby:
                layer = obj.metadata.get("layer", "Default")
                if not self.scene.layers.get(layer, {}).get("visible", True):
                    continue
                if obj.ray.intersects_any([ray_origin], [ray_direction]):
                    locations, _, _ = obj.ray.intersects_location([ray_origin], [ray_direction])
                    if locations is not None and len(locations) > 0:
                        dists = np.linalg.norm(locations - ray_origin, axis=1)
                        min_idx = np.argmin(dists)
                        if dists[min_idx] < best_dist:
                            best_dist = dists[min_idx]
                            best_obj = obj
            return best_obj
        except Exception as e:
            print(f"Errore in _pick_object: {e}")
            return None
    
    def _intersect_ray_plane(self, ray_origin, ray_direction, z):
        try:
            if abs(ray_direction[2]) > 1e-6:
                t = (z - ray_origin[2]) / ray_direction[2]
                if t >= 0:
                    return ray_origin + t * ray_direction
            return None
        except Exception as e:
            print(f"Errore in _intersect_ray_plane: {e}")
            return None
    
    def _get_sketch_coords(self, position):
        try:
            ray_origin, ray_direction = self._screen_to_ray(position.x(), position.y())
            if ray_origin is not None and ray_direction is not None and abs(ray_direction[2]) > 1e-6:
                t = (0.0 - ray_origin[2]) / ray_direction[2]
                point = ray_origin + t * ray_direction
                return point[0], point[1]
            return 0.0, 0.0
        except Exception as e:
            print(f"Errore in _get_sketch_coords: {e}")
            return 0.0, 0.0
    
    def _measure_click(self, position):
        try:
            if self.scene.measurement_mode is None:
                return
            px, py = self._get_sketch_coords(position)
            self.scene.measurement_points.append([px, py, 0.0])
            self.update()
            mode = self.scene.measurement_mode
            need = 2 if mode == "distance" else 3
            if len(self.scene.measurement_points) < need:
                remaining = need - len(self.scene.measurement_points)
                self.window.status_bar.showMessage(f"Misura: clicca altri {remaining} punto/i", 2000)
                return
            pts = self.scene.measurement_points
            if mode == "distance":
                d = math.dist(pts[0][:2], pts[1][:2])
                if d > 1e-9 and self.scene.selected_objects:
                    nuovo, ok = QInputDialog.getDouble(
                        self.window,
                        "Misura — Scala forma",
                        f"Distanza misurata: {d:.3f} mm\n"
                        "Inserisci il nuovo valore (la forma selezionata verrà scalata in modo uniforme):",
                        d, 0.001, 100000.0, 3
                    )
                    if ok and abs(nuovo - d) > 1e-9:
                        s = nuovo / d
                        if self.scene.scale_selection_uniform(s):
                            self.window.status_bar.showMessage(
                                f"Scala applicata: {d:.3f} → {nuovo:.3f} mm (fattore {s:.4f})", 5000
                            )
                            self.window.update_ui()
                            self.update()
                        else:
                            self.window.status_bar.showMessage(f"Distanza: {d:.3f} mm", 5000)
                    else:
                        self.window.status_bar.showMessage(f"Distanza: {d:.3f} mm", 5000)
                else:
                    self.window.status_bar.showMessage(f"Distanza: {d:.3f} mm", 5000)
            else:
                a = math.degrees(self._angle_between(pts[0], pts[1], pts[2]))
                self.window.status_bar.showMessage(f"Angolo: {a:.2f}°", 5000)
            self.scene.measurement_mode = None
            self.scene.measurement_points = []
            self.update()
        except Exception as e:
            print(f"Errore in _measure_click: {e}")
    
    @staticmethod
    def _angle_between(p1, p2, p3):
        u = np.array(p1[:2], dtype=np.float64) - np.array(p2[:2], dtype=np.float64)
        v = np.array(p3[:2], dtype=np.float64) - np.array(p2[:2], dtype=np.float64)
        nu = np.linalg.norm(u)
        nv = np.linalg.norm(v)
        if nu < 1e-12 or nv < 1e-12:
            return 0.0
        cosv = float(np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0))
        return math.acos(cosv)
    
    def _world_to_screen(self, point):
        try:
            if self._modelview_matrix is None or self._projection_matrix is None or self._viewport is None:
                return None
            w = gluProject(point[0], point[1], point[2],
                           self._modelview_matrix, self._projection_matrix, self._viewport)
            if w is None:
                return None
            dpr = self.device_pixel_ratio if self.device_pixel_ratio > 0 else 1.0
            return (w[0] / dpr, self.height() - w[1] / dpr)
        except Exception as e:
            print(f"Errore in _world_to_screen: {e}")
            return None
    
    def _snap_selection_xy(self):
        try:
            if not self.scene.snap_grid:
                return
            step = self.scene.grid_step
            if step is None or step <= 0:
                return
            for obj in self.scene.selected_objects:
                try:
                    c = obj.centroid
                except Exception:
                    continue
                tx = round(c[0] / step) * step
                ty = round(c[1] / step) * step
                dx = tx - c[0]
                dy = ty - c[1]
                if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                    obj.apply_translation([dx, dy, 0.0])
                    obj.metadata.pop("_gl_verts", None)
        except Exception as e:
            print(f"Errore in _snap_selection_xy: {e}")
    
    def _draw_measurement_overlay(self):
        try:
            if self.scene.measurement_mode is None or not self.scene.measurement_points:
                return
            pts = self.scene.measurement_points
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            scr = []
            for pt in pts:
                s = self._world_to_screen(np.array(pt, dtype=np.float64))
                if s is None:
                    continue
                scr.append(s)
                p.setBrush(QColor(255, 220, 80, 230))
                p.setPen(QPen(QColor(255, 255, 255), 1))
                p.drawEllipse(int(s[0]) - 4, int(s[1]) - 4, 8, 8)
            if len(scr) >= 2:
                p.setPen(QPen(QColor(255, 200, 60), 1))
                for i in range(len(scr) - 1):
                    p.drawLine(int(scr[i][0]), int(scr[i][1]), int(scr[i + 1][0]), int(scr[i + 1][1]))
            p.end()
        except Exception as e:
            print(f"Errore in _draw_measurement_overlay: {e}")
    
    def _select_objects_in_box(self, start, end):
        try:
            x1, y1 = start.x(), start.y()
            x2, y2 = end.x(), end.y()
            
            left = min(x1, x2)
            right = max(x1, x2)
            bottom = min(y1, y2)
            top = max(y1, y2)
            
            if not (QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                self.scene.clear_selection()
            
            objects_to_test = self.scene.objects
            
            for obj in objects_to_test:
                if hasattr(obj, 'bounds') and obj.bounds is not None and len(obj.bounds) == 2:
                    min_bound = obj.bounds[0]
                    max_bound = obj.bounds[1]
                    
                    screen_points = []
                    for x in [min_bound[0], max_bound[0]]:
                        for y in [min_bound[1], max_bound[1]]:
                            for z in [min_bound[2], max_bound[2]]:
                                try:
                                    screen_x, screen_y, _ = gluProject(
                                        x, y, z,
                                        self._modelview_matrix,
                                        self._projection_matrix,
                                        self._viewport
                                    )
                                    screen_points.append((screen_x, self._viewport[3] - screen_y))
                                except Exception as e:
                                    print(f"[TriviumCAD] selezione multipla (gluProject): {e}")
                    
                    for sx, sy in screen_points:
                        if left <= sx <= right and bottom <= sy <= top:
                            self.scene.add_to_selection(obj)
                            break
            
            self.window.update_ui()
            self.update()
        except Exception as e:
            print(f"Errore nella selezione multipla: {e}")
    
    def _screen_to_world(self, x, y):
        try:
            ray_origin, ray_direction = self._screen_to_ray(x, y)
            if ray_origin is None or ray_direction is None:
                return np.array([0, 0, 0])
            
            if abs(ray_direction[2]) > 1e-6:
                t = -ray_origin[2] / ray_direction[2]
                return ray_origin + t * ray_direction
            
            return ray_origin
        except Exception as e:
            print(f"Errore in _screen_to_world: {e}")
            return np.array([0, 0, 0])
    
    def mousePressEvent(self, event):
        try:
            self.mouse_pressed = True
            self.mouse_button = event.button()
            self._drag_target = None
            
            self.last_position = event.pos()
            self.drag_start_mouse = np.array([event.x(), event.y()])
            self.selection_box_start = (event.x(), event.y())
            self.selection_box_end = (event.x(), event.y())
            self.dragging = False
            
            self.click_handled = False
            
            if self.scene.measurement_mode is not None and event.button() == Qt.LeftButton:
                self._measure_click(event.pos())
                self.click_handled = True
                return
            
            if event.button() == Qt.RightButton:
                if self.scene.has_selection:
                    self.interaction_mode = 'CONTEXT_MENU'
                    self.click_handled = True
                return
            
            if event.modifiers() & Qt.ControlModifier and event.button() == Qt.LeftButton:
                self.interaction_mode = 'ORBIT'
                self.click_handled = True
                return
            
            if event.modifiers() & Qt.ControlModifier and event.button() == Qt.MiddleButton:
                self.interaction_mode = 'ROT_Z'
                self.click_handled = True
                return
            
            if event.button() == Qt.MiddleButton:
                self.interaction_mode = 'PAN'
                self.click_handled = True
                return
            
            if self.scene.has_selection and event.button() == Qt.LeftButton:
                handle = self.gizmo.pick_handle(event.pos(), self.device_pixel_ratio)
                if handle:
                    if handle == "vertical":
                        self.interaction_mode = 'DRAG_VERTICAL'
                    elif handle == "uniform":
                        self.interaction_mode = 'DRAG_UNIFORM_SCALE'
                    elif handle.startswith('rot_'):
                        self.interaction_mode = 'DRAG_ROTATE'
                        self.gizmo.active_handle = handle
                        self.rotate_start_angle = self.gizmo.get_rotation_angle(event.pos(), self.device_pixel_ratio, self._modelview_matrix, self._projection_matrix, self._viewport, self.scene)
                    elif handle.startswith('face_'):
                        self.interaction_mode = 'DRAG_FACE'
                        self.gizmo.active_handle = handle
                        self.drag_face_axis = handle[5]
                        self.drag_face_sign = handle[6]
                        self.drag_face_orig_verts = {}
                        ax_idx = {'x': 0, 'y': 1, 'z': 2}[self.drag_face_axis]
                        for o in self.scene.selected_objects:
                            ctr = o.centroid
                            local = o.vertices - ctr
                            half_extent = np.max(local[:, ax_idx]) if self.drag_face_sign == '+' else np.min(local[:, ax_idx])
                            if abs(half_extent) < 1e-10:
                                continue
                            weight = np.maximum(0, local[:, ax_idx] / half_extent)
                            self.drag_face_orig_verts[id(o)] = (o.vertices.copy(), weight, ctr)
                        self.drag_face_accum_delta = 0.0
                    else:
                        self.interaction_mode = 'DRAG_HANDLE'
                    
                    self.gizmo.active_handle = handle
                    ray_origin, ray_direction = self._screen_to_ray(event.x(), event.y())
                    if handle == "vertical":
                        self.drag_offset = np.array([0, 0, self.scene.single_selection.centroid[2]])
                    elif handle.startswith('rot_'):
                        pass
                    else:
                        self.drag_offset = self._intersect_ray_plane(ray_origin, ray_direction, 0.0)
                    self._drag_modelview = self._modelview_matrix.copy() if self._modelview_matrix is not None else None
                    self._drag_projection = self._projection_matrix.copy() if self._projection_matrix is not None else None
                    self._drag_viewport = self._viewport[:] if self._viewport is not None else None
                    centers = [o.centroid for o in self.scene.selected_objects if hasattr(o, 'centroid')]
                    self._drag_target = np.mean(centers, axis=0) if centers else np.array([0.0, 0.0, 0.0])
                    self.scene.start_operation()
                    self.window.update_ui()
                    self.click_handled = True
                    return
            
            if event.button() == Qt.LeftButton and not self.sketch_mode:
                hit = self._pick_object(event.pos())
                if hit:
                    if event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
                        self.scene.toggle_selection(hit)
                    elif hit not in self.scene.selected_objects:
                        self.scene.clear_selection()
                        self.scene.add_to_selection(hit)
                    self.window.update_ui()
                    self.update()
                    
                    self.interaction_mode = 'DRAG_OBJECT'
                    ray_origin, ray_direction = self._screen_to_ray(event.x(), event.y())
                    self.drag_offset = self._intersect_ray_plane(ray_origin, ray_direction, 0.0)
                    self._drag_modelview = self._modelview_matrix.copy() if self._modelview_matrix is not None else None
                    self._drag_projection = self._projection_matrix.copy() if self._projection_matrix is not None else None
                    self._drag_viewport = self._viewport[:] if self._viewport is not None else None
                    self.scene.start_operation()
                    self.click_handled = True
                    return
            
            if event.button() == Qt.LeftButton:
                self.interaction_mode = 'NONE'
                self.click_handled = False
                return
            
        except Exception as e:
            print(f"Errore in mousePressEvent: {e}")
    
    def mouseMoveEvent(self, event):
        try:
            # Stato residuo: il mouseReleaseEvent puo' non arrivare (rilascio fuori finestra).
            # Se il flag mouse_pressed e' vero ma FISICAMENTE nessun pulsante e' premuto,
            # lo stato e' sporco: reset senza applicare alcun delta (evita lo scatto camera).
            if self.mouse_pressed and not (event.buttons() & (Qt.LeftButton | Qt.MiddleButton | Qt.RightButton)):
                self.mouse_pressed = False
                self.dragging = False
                self.interaction_mode = 'NONE'
                self.last_position = None
                return
            
            self.gizmo.pick_handle(event.pos(), self.device_pixel_ratio)
            self.update()
            
            if self.last_position is None:
                return
            
            dx = event.x() - self.last_position.x()
            dy = event.y() - self.last_position.y()
            
            drag_distance = math.hypot(
                event.x() - self.drag_start_mouse[0],
                event.y() - self.drag_start_mouse[1]
            )
            
            if drag_distance > self.drag_threshold:
                self.dragging = True
                
                if self.interaction_mode == 'NONE':
                    if event.modifiers() & Qt.ControlModifier and self.mouse_button == Qt.LeftButton:
                        self.interaction_mode = 'ORBIT'
                    elif event.modifiers() & Qt.ControlModifier and self.mouse_button == Qt.MiddleButton:
                        self.interaction_mode = 'ROT_Z'
                    elif self.mouse_button == Qt.MiddleButton:
                        self.interaction_mode = 'PAN'
                    elif self.mouse_button == Qt.LeftButton:
                        self.interaction_mode = 'BOX_SELECT'
                        self.selection_mode = True
            
            if self.interaction_mode == 'ROT_Z' and self.dragging:
                self.rotation_z += dx * 0.5
            elif self.interaction_mode == 'PAN' and self.dragging:
                pan_scale = self.distance / 200.0
                self.pan[0] += dx * 0.5 * pan_scale
                self.pan[1] -= dy * 0.5 * pan_scale
            elif self.interaction_mode == 'DRAG_HANDLE' and self.scene.has_selection and self.dragging:
                if self.gizmo.active_handle == "center":
                    ray_origin, ray_direction = self._screen_to_ray(event.pos().x(), event.pos().y())
                    target = self._intersect_ray_plane(ray_origin, ray_direction, 0.0)
                    if target is not None and self.drag_offset is not None:
                        delta = target - self.drag_offset
                        self.scene.move_selection(delta[0], delta[1], 0.0)
                        self.drag_offset = target
                        self._snap_selection_xy()
                else:
                    factor = 1.0
                    if self.gizmo.active_handle == 'z':
                        factor = 1.0 + dy * 0.01
                        factor = 2.0 - factor
                    else:
                        factor = 1.0 + dx * 0.01
                    factor = max(0.1, min(10, factor))
                    axis_vec = {'x': [1,0,0], 'y': [0,1,0], 'z': [0,0,1]}.get(self.gizmo.active_handle, [1,1,1])
                    sv = [1,1,1]
                    if axis_vec[0] > 0: sv[0] = factor
                    if axis_vec[1] > 0: sv[1] = factor
                    if axis_vec[2] > 0: sv[2] = factor
                    self.scene.scale_selection(*sv)
                
                self.window.update_ui()
            elif self.interaction_mode == 'DRAG_UNIFORM_SCALE' and self.scene.has_selection and self.dragging:
                factor = 1.0 + dx * 0.01
                factor = max(0.1, min(10, factor))
                
                self.scene.scale_selection(factor, factor, factor)
                
                self.window.update_ui()
            elif self.interaction_mode == 'DRAG_OBJECT' and self.scene.has_selection and self.dragging:
                ray_origin, ray_direction = self._screen_to_ray(event.pos().x(), event.pos().y())
                target = self._intersect_ray_plane(ray_origin, ray_direction, 0.0)
                if target is not None and self.drag_offset is not None:
                    delta = (target - self.drag_offset) * self.drag_speed
                    self.scene.move_selection(delta[0], delta[1], 0.0)
                    self.drag_offset = target
                    self._snap_selection_xy()
                
                self.window.update_ui()
            elif self.interaction_mode == 'DRAG_VERTICAL' and self.scene.has_selection and self.dragging:
                if self.drag_offset is not None:
                    scale = self.distance / 500.0
                    delta_z = -(event.y() - self.last_position.y()) * scale * 0.5
                    self.scene.move_selection(0, 0, delta_z)
                
                self.window.update_ui()
            elif self.interaction_mode == 'DRAG_FACE' and self.scene.has_selection and self.dragging:
                if self.drag_face_orig_verts:
                    axis_idx = {'x': 0, 'y': 1, 'z': 2}[self.drag_face_axis]
                    dist_scale = self.distance / 500.0
                    if self.drag_face_axis == 'z':
                        inc_delta = -dy * dist_scale * 0.5
                    else:
                        inc_delta = dx * dist_scale * 0.5
                    self.drag_face_accum_delta += inc_delta
                    for obj in self.scene.selected_objects:
                        oid = id(obj)
                        entry = self.drag_face_orig_verts.get(oid)
                        if entry is not None:
                            orig, weight, ctr = entry
                            new_verts = orig.copy()
                            new_verts[:, axis_idx] = orig[:, axis_idx] + weight * self.drag_face_accum_delta
                            obj.vertices = new_verts
                            obj.metadata.pop("_gl_verts", None)
                self.window.update_ui()
            elif self.interaction_mode == 'DRAG_ROTATE' and self.scene.has_selection:
                axis = self.gizmo.active_handle[4]
                if axis == 'z':
                    cur = self.gizmo.get_rotation_angle(event.pos(), self.device_pixel_ratio, self._modelview_matrix, self._projection_matrix, self._viewport, self.scene)
                    if cur is not None:
                        self.gizmo.rotate_angle_during_drag = cur
                        delta = cur - self.rotate_start_angle
                        self.scene.rotate_selection(delta, [0, 0, 1])
                        self.rotate_start_angle = cur
                elif axis == 'x':
                    delta = -(event.y() - self.last_position.y()) * self.rotation_drag_speed
                    self.scene.rotate_selection(delta, [1, 0, 0])
                else:
                    delta = (event.x() - self.last_position.x()) * self.rotation_drag_speed
                    self.scene.rotate_selection(delta, [0, 1, 0])
                self.window.update_ui()
            elif self.interaction_mode == 'ORBIT' and self.dragging:
                self.rotation[1] += dx * 0.5
                self.rotation[0] += dy * 0.5
                self.rotation[0] = max(-89, min(89, self.rotation[0]))
            elif self.interaction_mode == 'BOX_SELECT':
                self.selection_box_end = (event.x(), event.y())
            
            self.last_position = event.pos()
        except Exception as e:
            print(f"Errore in mouseMoveEvent: {e}")
            # Un'eccezione non deve lasciare last_position vecchio: il move successivo
            # partirebbe con un delta enorme (scatto camera/oggetto).
            self.last_position = event.pos()
    
    def mouseReleaseEvent(self, event):
        try:
            self.mouse_pressed = False
            self._drag_target = None
            
            if self.dragging:
                if self.interaction_mode == 'BOX_SELECT':
                    start = QPoint(self.selection_box_start[0], self.selection_box_start[1])
                    end = QPoint(self.selection_box_end[0], self.selection_box_end[1])
                    self._select_objects_in_box(start, end)
                
                elif self.interaction_mode == 'ORBIT' or self.interaction_mode == 'PAN' or self.interaction_mode == 'ROT_Z' or self.interaction_mode == 'DRAG_ROTATE':
                    self.interaction_mode = self.interaction_mode
            elif not self.click_handled:
                hit = self._pick_object(QPoint(self.drag_start_mouse[0], self.drag_start_mouse[1]))
                if hit:
                    if event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
                        self.scene.toggle_selection(hit)
                    else:
                        self.scene.clear_selection()
                        self.scene.add_to_selection(hit)
                    self.window.update_ui()
                    self.update()
                else:
                    if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                        self.scene.clear_selection()
                        self.window.update_ui()
                        self.update()
            
            self.dragging = False
            self.selection_mode = False
            self.selection_box_start = None
            self.selection_box_end = None
            self._drag_modelview = None
            self._drag_projection = None
            self._drag_viewport = None
            
            if self.scene.operation_in_progress:
                self.scene.end_operation()
            
            self.interaction_mode = 'NONE'
            self.last_position = None
            self.gizmo.rotate_angle_during_drag = None
            self.drag_face_axis = None
            self.drag_face_sign = None
            self.drag_face_orig_verts = None
            self.drag_face_accum_delta = 0.0
            self.click_handled = False
        except Exception as e:
            print(f"Errore in mouseReleaseEvent: {e}")
            # Su eccezione lo stato non deve restare sporco (mode/dragging residui
            # farebbero scattare la camera al primo move successivo).
            self.mouse_pressed = False
            self.dragging = False
            self.interaction_mode = 'NONE'
            self.last_position = None
    
    def contextMenuEvent(self, event):
        if self.scene.has_selection:
            menu = QMenu(self)
            
            duplicate_action = menu.addAction("Duplica")
            delete_action = menu.addAction("Elimina")
            group_action = menu.addAction("Raggruppa")
            ungroup_action = menu.addAction("Separati")
            align_z_action = menu.addAction("Allinea a Z=0")
            
            action = menu.exec_(self.mapToGlobal(event.pos()))
            if action == duplicate_action:
                self.scene.duplicate()
                self.window.update_ui()
                self.update()
            elif action == delete_action:
                self.scene.delete()
                self.window.update_ui()
                self.update()
            elif action == group_action and len(self.scene.selected_objects) >= 2:
                self.scene.group_selected()
                self.window.status_bar.showMessage(f"Raggruppati {len(self.scene.selected_objects)} oggetti", 3000)
            elif action == ungroup_action:
                self.scene.ungroup_object()
                self.window.status_bar.showMessage(f"Separati {len(self.scene.selected_objects)} oggetti", 3000)
            elif action == align_z_action:
                self.scene.align_z()
                self.window.update_ui()
                self.update()
    
    def wheelEvent(self, event):
        try:
            factor = 1.0 - event.angleDelta().y() * 0.0015
            # Protezione fattore negativo: un delta cumulato > 666 invertirebbe lo zoom
            # (distance *= negativo -> salto). Clamp del fattore a [0.1, 2.0].
            factor = max(0.1, min(2.0, factor))
            self.distance *= factor
            self.distance = max(10, min(5000, self.distance))
            self.update()
        except Exception as e:
            print(f"Errore in wheelEvent: {e}")
    
    def keyPressEvent(self, event):
        try:
            key = event.key()
            mod = event.modifiers()
            if key == Qt.Key_Escape:
                if self.scene.measurement_mode is not None:
                    self.scene.measurement_mode = None
                    self.scene.measurement_points = []
                    self.window.status_bar.showMessage("Misurazione annullata", 2000)
                    self.update()
                elif self.sketch_mode:
                    pass
                elif self.scene.has_selection:
                    self.scene.clear_selection()
                    self.window.update_ui()
                    self.update()
            elif key == Qt.Key_Delete and self.scene.has_selection:
                self.scene.delete()
                self.window.update_ui()
                self.update()
            elif key == Qt.Key_A and mod & Qt.ControlModifier:
                self.scene.selected_objects = self.scene.objects.copy()
                self.window.update_ui()
                self.update()
            elif key == Qt.Key_D and mod & Qt.ControlModifier:
                self.scene.clear_selection()
                self.window.update_ui()
                self.update()
            elif key == Qt.Key_M and mod & Qt.ControlModifier:
                if mod & Qt.ShiftModifier:
                    if self.scene.measure_angle():
                        self.update()
                else:
                    if self.scene.measure_distance():
                        self.update()
            elif key == Qt.Key_Z and not (mod & Qt.ControlModifier):
                if self.scene.undo():
                    self.window.update_ui()
                    self.update()
            elif key == Qt.Key_Z and (mod & Qt.ControlModifier):
                if mod & Qt.ShiftModifier:
                    if self.scene.redo():
                        self.window.update_ui()
                        self.update()
                else:
                    if self.scene.undo():
                        self.window.update_ui()
                        self.update()
            elif key == Qt.Key_Y and not (mod & Qt.ControlModifier):
                if self.scene.redo():
                    self.window.update_ui()
                    self.update()
            elif key == Qt.Key_X and not (mod & Qt.ControlModifier):
                self._cut_selected()
            elif key == Qt.Key_C and not (mod & Qt.ControlModifier):
                self._copy_selected()
            elif key == Qt.Key_V and not (mod & Qt.ControlModifier):
                self._paste_clipboard()
            elif key == Qt.Key_Space:
                self.scene.align_z()
                self.window.update_ui()
                self.update()
        except Exception as e:
            print(f"Errore in keyPressEvent: {e}")

    def _cut_selected(self):
        self._copy_selected()
        self.scene.delete()
        self.window.update_ui()
        self.update()

    def _copy_selected(self):
        self.scene.clipboard_objects = []
        for obj in self.scene.selected_objects:
            try:
                self.scene.clipboard_objects.append(obj.copy())
            except Exception:
                print("ERRORE: _copy_selected fallito per un oggetto")
                pass

    def _paste_clipboard(self):
        if not self.scene.clipboard_objects:
            return
        self.scene.start_operation()
        for obj in self.scene.clipboard_objects:
            try:
                new_obj = obj.copy()
                new_obj.apply_translation([10, 10, 0])
                new_obj.metadata["name"] = new_obj.metadata.get("name", "Object") + "_paste"
                self.scene.objects.append(new_obj)
            except Exception:
                print("ERRORE: _paste_clipboard fallito per un oggetto")
                pass
        self.scene.end_operation()
        self.window.update_ui()
        self.update()

# =============================================================================
# BLOCCO 3: UI COMPONENTS
# =============================================================================
# === TUTORIAL DIALOG ===
class TutorialDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📖 Tutorial TriviumCAD")
        self.setMinimumSize(680, 540)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BACKGROUND_COLOR};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 6px;
            }}
            QTextEdit {{
                background: #F2F6FB;
                color: {TEXT_COLOR};
                border: 1px solid #B0C8DF;
                border-radius: 3px;
                padding: 8px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }}
            QPushButton {{
                background-color: {BUTTON_COLOR};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 3px;
                padding: 6px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #B8D4EC;
            }}
            QPushButton:disabled {{
                background-color: #A0B8D0;
                color: #6080A0;
            }}
            QCheckBox {{
                color: {TEXT_COLOR};
            }}
        """)

        layout = QVBoxLayout(self)

        # Stacked widget per le pagine
        self.stack = QStackedWidget()

        # Contenuti: lista di (titolo, html) per preservare l'ordine
        self.pages = [
            ("🚀 Introduzione", f"<h2 style='color:#0C1E36;'>Benvenuto in {APP_NAME} v{VERSION}</h2>"
                               "<p>TriviumCAD è un ambiente integrato per modellazione 3D, progettazione meccanica,<br>"
                               "generazione CAM (percorsi utensile) e invio diretto a stampanti 3D.</p>"
                               "<h3>Convenzione spaziale:</h3>"
                               "<p>• <b style='color:#CC3333;'>● Rosso = Destra</b> (Asse X, larghezza)<br>"
                               "• <b style='color:#33CC33;'>● Verde = Dietro</b> (Asse Y, profondità, fronte utente = -Y)<br>"
                               "• <b style='color:#3333CC;'>● Blu = Sopra</b> (Asse Z, altezza)</p>"
                               "<h3>Pannelli:</h3>"
                               "<p>• <b>Sinistro:</b> Forme Primitive, Meccanica (Filettatura/Affetta/Arrotonda), CAM<br>"
                               "• <b>Destro:</b> Testo 3D, Parametri (posizione/rotazione), Analisi<br>"
                               "• <b>Proprietà:</b> (seleziona un oggetto) mostra volume, coordinate, dimensioni, stato mesh<br>"
                               "• <b>Toolbar:</b> Da2 a 3D, Nuovo/Apri/Salva, Booleane, Guscio, Snap, Magneti</p>"
                               "<p><b>N.B.</b> Ogni operazione è annullabile con Ctrl+Z.</p>"),

            ("🟦 Forme", "<h2>Libreria Forme (pannello sinistro)</h2>"
                         "<p>Clicca un pulsante per creare la forma all'origine. Poi spostala col GIZMO o coi parametri.</p>"
                         "<p>• <b>Cubo</b> — larghezza, altezza, profondità<br>"
                         "• <b>Cilindro</b> — raggio, altezza, sezioni (circonferenza)<br>"
                         "• <b>Sfera</b> — raggio, suddivisioni (più suddivisioni = più liscia)<br>"
                         "• <b>Cono</b> — raggio base, altezza, sezioni<br>"
                         "• <b>collare</b> — raggio esterno, raggio interno, altezza (rondella)<br>"
                         "• <b>Esagono</b> — raggio, altezza (prisma esagonale)<br>"
                         "• <b>Spirale</b> — raggio, altezza, giri, spessore (elica 3D)<br>"
                         "• <b>Arco</b> — raggio esterno, raggio interno, apertura (°), altezza (parete curva)<br>"
                         "• <b>Scatola vuota</b> — larghezza, altezza, profondità, spessore muro (senza parete superiore)</p>"
                         "<p><b>Nota:</b> Altezza = Z (Blu).</p>"),

            ("👁️ Vista e Selezione", "<h2>Controlli Vista</h2>"
                                      "<p>• <b>Rotella:</b> Zoom dinamico (da 10 a 5000 unità)<br>"
                                      "• <b>Ctrl + SX + Drag:</b> Rotazione 360° (orbita)<br>"
                                      "• <b>Centrale + Drag:</b> Pan (traslazione vista)<br>"
                                      "• <b>Ctrl + Centrale + Drag:</b> Rotazione asse Z</p>"
                                      "<h3>Selezione Oggetti</h3>"
                                      "<p>• <b>Click</b> su oggetto: seleziona (deseleziona gli altri)<br>"
                                      "• <b>Shift+Click</b> o <b>Ctrl+Click</b>: aggiungi/togli dalla selezione<br>"
                                      "• <b>SX + Drag</b> su sfondo: selezione rettangolare (box select)<br>"
                                      "• <b>Shift + box select:</b> aggiunge alla selezione<br>"
                                      "• <b>Click vuoto:</b> deseleziona tutto<br>"
                                      "• <b>Tasto DX:</b> menu contestuale (Duplica, Elimina, Raggruppa, Allinea a Z=0)<br>"
                                      "• <b>Ctrl+A:</b> seleziona tutti &nbsp;•&nbsp; <b>Ctrl+D:</b> deseleziona tutti<br>"
                                      "• <b>Del:</b> elimina selezionati</p>"
                                      "<h3>Misurazioni:</h3>"
                                      "<p>• <b>Ctrl+M:</b> misura distanza tra 2 punti (clicca 2 punti sulla scena)<br>"
                                      "• <b>Ctrl+Shift+M:</b> misura angolo tra 3 punti (clicca 3 punti)</p>"),

            ("🎨 GIZMO", "<h2>Maniglie di Trasformazione</h2>"
                         "<p>Il GIZMO appare quando selezioni uno o più oggetti.</p>"
                         "<p><b style='color:#CC3333;'>● Rosso — Asse X:</b> Larghezza (destra/sinistra)<br>"
                         "<b style='color:#33CC33;'>● Verde — Asse Y:</b> Profondità (davanti = -Y, dietro = +Y)<br>"
                         "<b style='color:#3333CC;'>● Blu — Asse Z:</b> Altezza (sopra = +Z, sotto = -Z)</p>"
                         "<p>• <b>◉ Bianco (centro):</b> Sposta su piano XY (segue il mouse 1:1)<br>"
                         "• <b>⇅ Grigia (verticale):</b> Sposta su Z (trascina su/giù)<br>"
                         "• <b>◆ Gialla (diagonale):</b> Scala uniforme (trascina orizzontalmente)<br>"
                         "• <b>Assi colorati:</b> Trascina per scalare SOLO lungo quell'asse<br>"
                         "• <b style='color:#FFDD00;'>● Cerchi gialli (goniometro):</b> Appaiono passando il mouse sugli assi<br>"
                         "&nbsp;&nbsp;• Trascina per ruotare attorno all'asse<br>"
                         "&nbsp;&nbsp;• Tacche ogni 15° (piccole), ogni 45° (grandi con punti)<br>"
                         "• <b>Maniglia evidenziata:</b> Pronta al trascinamento (cambia colore al passaggio del mouse)</p>"
                         "<h3>🧩 Sposta Faccia</h3>"
                         "<p>• Trascina per <b>allungare/accorciare l'intera metà della forma</b> dal centro geometrico<br>"
                         "• Deformazione uniforme lungo l'asse: la sezione perpendicolare resta invariata<br>"
                         "• Il peso è massimo (1.0) alla faccia e zero al centro — transizione lineare<br>"
                         "• Ogni lato ha la sua maniglia: <b style='color:#CC3333;'>■ X+ / X-</b> (rosso), "
                         "<b style='color:#33CC33;'>■ Y+ / Y-</b> (verde), <b style='color:#3333CC;'>■ Z+ / Z-</b> (blu)<br>"
                         "• Ideale per stirare un lato come gomma: un tubo tirato si allunga e resta tondo</p>"),

            ("🔧 Manipolazioni", "<h2>1. Spostamento</h2>"
                                 "<p>• Trascina direttamente l'oggetto con SX<br>"
                                 "• Usa GIZMO: Bianco centro (XY) o Grigio verticale (Z)<br>"
                                 "• Modifica X, Y, Z nel pannello Parametri (destra)</p>"
                                 "<h2>2. Rotazione</h2>"
                                 "<p>• GIZMO: cerchi gialli (goniometro) su hover degli assi<br>"
                                 "• Modifica Rot X/Y/Z nel pannello Parametri</p>"
                                 "<h2>3. Scalatura</h2>"
                                 "<p>• Assi singoli: maniglie colorate<br>"
                                 "• Uniforme: maniglia gialla diagonale</p>"
                                 "<h2>4. Operazioni Booleane</h2>"
                                 "<p>• Seleziona 2+ oggetti: <b>Unione</b> (fonde), <b>Sottrazione</b> (primo - secondo), <b>Intersezione</b></p>"
                                 "<h2>5. Allineamento a Z=0</h2>"
                                 "<p>• Tasto <b>Spazio</b> o DX › Allinea a Z=0</p>"
                                 "<h2>6. Pattern (Serie)</h2>"
                                 "<p>• Lineare: menu Modifica › Pattern lineare — copia N volte con distanza lungo X/Y/Z<br>"
                                 "• Circolare: menu Modifica › Pattern circolare — copia N volte in cerchio attorno a un asse</p>"
                                 "<h2>7. Mirror (Specchio)</h2>"
                                 "<p>• Crea copia specchiata lungo X, Y o Z</p>"
                                 "<h2>8. Deformazioni Mesh</h2>"
                                 "<p>• <b>Smooth:</b> arrotonda la mesh (Laplaciano)<br>"
                                 "• <b>Subdivide:</b> aumenta la risoluzione<br>"
                                 "• <b>Decimate:</b> riduce il numero di facce<br>"
                                 "• <b>Merge Vertici:</b> fonde vertici vicini</p>"
                                 "<h2>9. Guscio (Shell)</h2>"
                                 "<p>• Trasforma solido pieno in involucro cavo con parete inferiore</p>"
                                  "<h2>10. Da2 a 3D — Importa 2D e converti in 3D</h2>"
                                  "<p>• <b>SVG / DXF:</b> import vettoriale — carica i poligoni, li estrude in mesh watertight<br>"
                                  "• <b>Immagini (JPG, PNG, ...):</b> binarizzazione → contour detection → poligono con buchi → estrude<br>"
                                  "• <b>Silhouette-mode:</b> contorno esterno + buchi interni (finestrini, dettagli) rilevati automaticamente<br>"
                                  "• Le mesh vengono normalizzate a max 30 unità e centrate sul piano di lavoro</p>"
                                  "<h2>11. Rivoluzione / Loft / Sweep</h2>"
                                  "<p>• <b>Rivoluzione:</b> seleziona un oggetto → dal menu DX scegli Rivoluzione → ruota il profilo attorno a Z<br>"
                                  "• <b>Loft:</b> seleziona 2 oggetti → menu DX → Loft → interpola i profili in una mesh continua<br>"
                                  "• <b>Sweep:</b> seleziona un oggetto → menu DX → Sweep → estrusione lungo percorso elicoidale</p>"
                                  "<h2>12. Gruppi / Layer</h2>"
                                  "<p>• <b>Raggruppa:</b> unisce oggetti in gruppo<br>"
                                  "• <b>Separati:</b> scioglie il gruppo<br>"
                                  "• <b>Layer:</b> organizza oggetti su livelli diversi</p>"
                                  "<h2>13. Taglia/Copia/Incolla</h2>"
                                 "<p>• <b>Ctrl+X:</b> Taglia &nbsp;•&nbsp; <b>Ctrl+C:</b> Copia &nbsp;•&nbsp; <b>Ctrl+V:</b> Incolla<br>"
                                 "• <b>Ctrl+Z:</b> Annulla &nbsp;•&nbsp; <b>Ctrl+Y:</b> Ripristina (fino a 50 step)</p>"),

            ("📝 Testo 3D", "<h2>Pannello Testo (destra)</h2>"
                            "<h3>1. Crea</h3>"
                            "<p>• Scrivi il testo, scegli font, dimensione, spessore, spaziatura<br>"
                            "• Clicca 'Crea' → il testo viene generato come mesh 3D verticale<br>"
                            "• Posizionato di fronte all'oggetto selezionato o all'origine<br>"
                            "• Dopo la creazione, usa GIZMO per posizionarlo</p>"
                            "<h3>2. Adatta</h3>"
                            "<p>• Seleziona una forma, scrivi il testo, clicca 'Adatta'<br>"
                            "• Il testo viene posizionato sulla faccia anteriore (-Y) e unito con booleana</p>"
                            "<h3>3. Bassorilievo</h3>"
                            "<p>• Crea prima il testo con 'Crea'<br>"
                            "• Posizionalo davanti alla forma con GIZMO<br>"
                            "• Seleziona <b>sia il testo che la forma</b><br>"
                            "• Clicca 'Bassorilievo' → il testo viene inciso sulla faccia anteriore</p>"),

            ("⚙️ Meccanica", "<h2>Pannello Meccanica (sinistra)</h2>"
                             "<h3>Filettatura:</h3>"
                             "<p>• <b>Tipo:</b> Interna (incisa) / Esterna (volume separato)<br>"
                             "• <b>Modalità:</b> Auto (profilo), Metrico, UNF / UNC, Gas<br>"
                             "• <b>Profilo:</b> Filo (ISO 60°), Trapezio (piatto), Arrotondato (cosinusoidale)<br>"
                             "• <b>Passo:</b> distanza tra creste in mm (o TPI per UNF/UNC)<br>"
                             "• <b>Esterna:</b> volume separato — <b>Shift+Click</b> su forma + filetto → toolbar <b>Booleane › Unione</b><br>"
                             "• <b>Interna:</b> incisa nella parete con booleana DIFFERENZA (automatico)<br>"
                             "• La filettatura segue il <b>profilo reale</b> della forma (non bounding box)<br>"
                             "• Supporta: cilindro, sfera, cono, esagono, box, scatola vuota, collare, arco, donut, forme importate</p>"
                             "<h3>Affetta:</h3>"
                             "<p>• Taglia l'oggetto con un piano lungo X, Y o Z<br>"
                             "• Crea due mesh separate (sopra/sotto il piano)</p>"
                             "<h3>Arrotondamento (Raccordo):</h3>"
                             "<p>• Raggio 0.5-50 — subdivide e applica smoothing Taubin</p>"
                             "<h3>CAM (Percorsi Utensile):</h3>"
                             "<p>• Seleziona un singolo oggetto, imposta diametro utensile e stepover<br>"
                             "• Genera percorsi adattivi 3D per fresatura</p>"),

            ("⌨️ Scorciatoie", "<h2>Generali</h2>"
                               "<p>• <b>Ctrl+Z:</b> Annulla &nbsp;|&nbsp; <b>Ctrl+Y:</b> Ripristina<br>"
                               "• <b>Ctrl+X:</b> Taglia &nbsp;|&nbsp; <b>Ctrl+C:</b> Copia &nbsp;|&nbsp; <b>Ctrl+V:</b> Incolla<br>"
                               "• <b>Del:</b> Elimina &nbsp;|&nbsp; <b>Ctrl+D:</b> Deseleziona &nbsp;|&nbsp; <b>Ctrl+A:</b> Seleziona tutti<br>"
                               "• <b>Esc:</b> Deseleziona tutto / esci da sketch mode<br>"
                               "• <b>Spazio:</b> Allinea selezione a Z=0</p>"
                               "<h2>Vista</h2>"
                               "<p>• <b>Rotella:</b> Zoom<br>"
                               "• <b>Ctrl+SX+Drag:</b> Orbita<br>"
                               "• <b>Centrale+Drag:</b> Pan<br>"
                               "• <b>Ctrl+Centrale+Drag:</b> Rotazione asse Z</p>"
                               "<h2>Selezione</h2>"
                               "<p>• <b>Shift+Click / Ctrl+Click:</b> Aggiungi/Togli selezione<br>"
                               "• <b>SX+Drag (sfondo):</b> Box select<br>"
                               "• <b>Tasto DX:</b> Menu contestuale</p>"
                               "<h2>Misurazioni</h2>"
                               "<p>• <b>Ctrl+M:</b> Misura distanza<br>"
                               "• <b>Ctrl+Shift+M:</b> Misura angolo</p>"),

            ("💡 Tips & Tricks", "<p>• <b>Salva spesso</b> con versioni multiple (File › Salva come .n47)<br>"
                                "• <b>File › Esporta:</b> STL, OBJ, PLY, 3MF, GLB<br>"
                                "• <b>File › Importa:</b> STL, OBJ, PLY, 3MF<br>"
                                "• <b>Da2 a 3D:</b> importa immagini, SVG, DXF → mesh 3D<br>"
                                "• <b>Watertight:</b> verifica che la mesh sia chiusa (essenziale per stampa 3D)<br>"
                                "• <b>Layer:</b> usa layer diversi per parti separate<br>"
                                "• <b>Snap Griglia:</b> attiva dalla toolbar per posizionamento preciso<br>"
                                "• <b>Magneti:</b> attacca gli oggetti tra loro quando sono vicini<br>"
                                "• <b>Filettatura su sfera/cono/esagono:</b> segue il profilo reale, non il bbox<br>"
                                "• <b>Filettatura interna:</b> incisa automaticamente con booleana DIFFERENZA<br>"
                                "• <b>Arrotondamento:</b> Raggio 1-2 per smussatura leggera, 3+ per marcata<br>"
                                "• <b>Booleane:</b> ora con Undo funzionante e multi-selezione stabile<br>"
                                "• <b>Testo 3D:</b> 'Crea' → posiziona con GIZMO → seleziona entrambi → 'Bassorilievo'<br>"
                                "• <b>Undo/Redo:</b> 50 step massimi, non dimenticare Ctrl+Z<br>"
                                "• <b>Guscio:</b> lascia la base inferiore piena (ideale per contenitori)<br>"
                                "• <b>Collare:</b> ideale per flange e distanziali</p>"),

            ("🖨️ Stampa 3D", "<h2>Invio diretto a stampante</h2>"
                              "<p>File › 'Invia alla stampante…' apre la finestra di connessione.</p>"
                              "<h3>Profili integrati (13):</h3>"
                              "<p>• <b>Bambu Lab:</b> X1C, P1S, A1, A1 Mini — MQTT+FTP<br>"
                              "• <b>Anycubic:</b> Kobra 3, Kobra 2, Vyper — FTP, SMB, OctoPrint, Cloud<br>"
                              "• <b>Creality:</b> K1 Max, K1, Ender 3 V3 — HTTP WiFi, FTP, OctoPrint<br>"
                              "• <b>Prusa:</b> i3 MK3S+, XL — PrusaLink, FTP, OctoPrint</p>"
                              "<h3>Protocolli di connessione:</h3>"
                              "<p>• <b>mqtt_ftps:</b> Bambu Lab (MQTT + FTP over TLS)<br>"
                              "• <b>creality_http:</b> Creality WiFi (HTTP POST)<br>"
                              "• <b>prusalink:</b> Prusa REST API<br>"
                              "• <b>octoprint:</b> Universale (API key)<br>"
                              "• <b>ftp / smb:</b> Condivisione rete locale<br>"
                              "• <b>anycubic_cloud:</b> Anycubic Cloud<br>"
                              "• <b>file:</b> Esporta solo GCODE</p>"),

            ("📊 Analisi", "<h2>Pannello Analisi (destra)</h2>"
                           "<p>Seleziona uno o più oggetti e clicca:</p>"
                           "<p>• <b>Volume:</b> calcola il volume in mm³<br>"
                           "• <b>Superficie:</b> area totale della mesh in mm²<br>"
                           "• <b>Centro Massa:</b> coordinate del baricentro (COM)<br>"
                           "• <b>Bounding Box:</b> dimensioni X, Y, Z min/max e centro<br>"
                           "• <b>Tenuta Stagna:</b> verifica se la mesh è watertight (chiusa, senza buchi)</p>"
                           "<h3>Pannello Proprietà (automatico alla selezione):</h3>"
                           "<p>• Scheda 'Selezione': conteggio, volume totale, area totale<br>"
                           "• Scheda 'Coordinate & Dimensioni': centro (X,Y,Z), dimensioni (L,H,P)<br>"
                           "• Scheda 'Stato': Volume, Area, Watertight (singolo oggetto)<br>"
                           "• Parametri dinamici modificabili (raggio, altezza, ecc.)</p>"),
        ]

        # Crea le pagine nello stack
        for title, html_text in self.pages:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(4, 4, 4, 4)

            editor = QTextEdit()
            editor.setReadOnly(True)
            editor.setHtml(html_text)
            page_layout.addWidget(editor)

            self.stack.addWidget(page)

        layout.addWidget(self.stack)

        # Navigazione
        nav_layout = QHBoxLayout()

        self.back_btn = QPushButton("← Indietro")
        self.back_btn.clicked.connect(self._prev)

        self.page_counter = QLabel("1 / {}".format(len(self.pages)))
        self.page_counter.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: bold; padding: 0 8px;")

        self.next_btn = QPushButton("Avanti →")
        self.next_btn.clicked.connect(self._next)

        # Menu a tendina per saltare alle pagine
        self.page_combo = QComboBox()
        self.page_combo.setMinimumWidth(180)
        self.page_combo.setStyleSheet("""
            QComboBox {
                background: #F2F6FB; color: #0C1E36;
                border: 1px solid #B0C8DF; border-radius: 3px;
                padding: 4px 8px; font-size: 12px;
            }
            QComboBox:hover { background: #E0EDF5; }
            QComboBox::drop-down { border: none; }
        """)
        for title, _ in self.pages:
            clean = title.replace("🚀", "").replace("🟦", "").replace("👁️", "").replace("🎨", "")
            clean = clean.replace("🔧", "").replace("📝", "").replace("⚙️", "").replace("⌨️", "")
            clean = clean.replace("💡", "").replace("🖨️", "").replace("📊", "").strip()
            self.page_combo.addItem(clean)
        self.page_combo.currentIndexChanged.connect(self._on_combo_changed)

        # Nascondi all'avvio
        self.hide_cb = QCheckBox("Nascondi all'avvio")
        self._combo_updating = False
        settings = QSettings("TriviumCAD", "TriviumCAD")
        self.hide_cb.setChecked(settings.value("tutorial/hide_on_startup", False, type=bool))
        self.hide_cb.toggled.connect(self._on_hide_toggled)

        # Chiudi
        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(self.accept)

        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self.page_counter)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_btn)
        nav_layout.addWidget(self.page_combo)
        nav_layout.addWidget(self.hide_cb)
        nav_layout.addStretch()
        nav_layout.addWidget(close_btn)

        layout.addLayout(nav_layout)

        self._update_nav()

    def _on_combo_changed(self, idx):
        if not self._combo_updating:
            self.stack.setCurrentIndex(idx)
            self._update_nav()

    def _update_nav(self):
        idx = self.stack.currentIndex()
        total = len(self.pages)
        self.back_btn.setEnabled(idx > 0)
        self.next_btn.setEnabled(idx < total - 1)
        self.page_counter.setText(f"{idx + 1} / {total}")
        self._combo_updating = True
        self.page_combo.setCurrentIndex(idx)
        self._combo_updating = False

    def _prev(self):
        self.stack.setCurrentIndex(self.stack.currentIndex() - 1)
        self._update_nav()

    def _next(self):
        self.stack.setCurrentIndex(self.stack.currentIndex() + 1)
        self._update_nav()

    def _on_hide_toggled(self, checked):
        settings = QSettings("TriviumCAD", "TriviumCAD")
        settings.setValue("tutorial/hide_on_startup", checked)

# =============================================================================
# DIALOG CONNESSIONE STAMPANTE 3D
# =============================================================================
# === STAMPA 3D ===
class PrinterConnectDialog(QDialog):
    PROTOCOL_LABELS = {
        "mqtt_ftps": "Bambu Lab MQTT+FTP (diretto)",
        "creality_http": "Creality HTTP API (Wi-Fi)",
        "prusalink": "PrusaLink REST API (rete locale)",
        "octoprint": "OctoPrint API (universale)",
        "ftp": "FTP generico",
        "smb": "Cartella di rete SMB",
        "anycubic_cloud": "Anycubic Cloud (Wi-Fi)",
        "file": "Solo esporta (manuale)"
    }
    PROTOCOL_HELP = {
        "mqtt_ftps": "<small>Richiede IP + Access Code dalla stampante. Carica file via FTP e avvia stampa via MQTT.</small>",
        "creality_http": "<small>Richiede IP. Collega via HTTP all'interfaccia web della stampante Creality (K1/K1 Max).</small>",
        "prusalink": "<small>Richiede IP + API key (da PrusaLink/Prusa Connect). Invia file via REST API.</small>",
        "octoprint": "<small>Richiede IP + API key (da OctoPrint > Impostazioni > API). Universal: funziona con qualsiasi stampante via Raspberry Pi.</small>",
        "ftp": "<small>Richiede IP + credenziali FTP. Carica il file sulla stampante o server FTP.</small>",
        "smb": "<small>Richiede percorso di rete (es. //192.168.1.100/share). Copia il file su cartella condivisa.</small>",
        "anycubic_cloud": "<small>Richiede IP + credenziali Anycubic Cloud. Invia alla stampante via cloud.</small>",
        "file": "<small>Esporta il file con le impostazioni del profilo, senza inviare.</small>"
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connessione Stampante 3D")
        self.setMinimumSize(560, 520)
        self.setStyleSheet(f"""
            background-color: {BACKGROUND_COLOR}; color: {TEXT_COLOR};
            border: 1px solid {BORDER_COLOR}; border-radius: 4px;
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        
        lbl = QLabel("<b>Seleziona stampante e metodo di connessione</b>")
        lbl.setStyleSheet(f"color: {TEXT_COLOR}; padding: 4px;")
        layout.addWidget(lbl)
        
        self.profile_combo = QComboBox()
        for name in PRINTER_PROFILES:
            self.profile_combo.addItem(name)
        self.profile_combo.currentTextChanged.connect(self._on_profile_change)
        layout.addWidget(QLabel("Modello stampante:"))
        layout.addWidget(self.profile_combo)
        
        h_proto = QHBoxLayout()
        h_proto.addWidget(QLabel("Protocollo:"))
        self.protocol_combo = QComboBox()
        self.protocol_combo.currentTextChanged.connect(self._on_protocol_change)
        h_proto.addWidget(self.protocol_combo, 1)
        layout.addLayout(h_proto)
        
        self.proto_help = QLabel("")
        self.proto_help.setWordWrap(True)
        self.proto_help.setStyleSheet(f"color: #3060A0; padding: 2px 6px;")
        layout.addWidget(self.proto_help)
        
        info = QGroupBox("Specifiche stampante")
        il = QVBoxLayout(info)
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        il.addWidget(self.info_label)
        layout.addWidget(info)
        
        conn = QGroupBox("Connessione")
        cl = QVBoxLayout(conn)
        cl.setSpacing(4)
        
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Indirizzo IP / Host:"))
        self.ip_entry = QLineEdit()
        self.ip_entry.setPlaceholderText("es. 192.168.1.100")
        h1.addWidget(self.ip_entry)
        cl.addLayout(h1)
        
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Password / API key:"))
        self.code_entry = QLineEdit()
        self.code_entry.setPlaceholderText("(opzionale) chiave o password")
        self.code_entry.setEchoMode(QLineEdit.Password)
        h2.addWidget(self.code_entry)
        cl.addLayout(h2)
        
        h2b = QHBoxLayout()
        h2b.addWidget(QLabel("Utente (opz):"))
        self.user_entry = QLineEdit()
        self.user_entry.setPlaceholderText("(opzionale per FTP/SMB)")
        h2b.addWidget(self.user_entry)
        cl.addLayout(h2b)
        
        layout.addWidget(conn)
        
        opts = QGroupBox("Opzioni di stampa")
        ol = QVBoxLayout(opts)
        ol.setSpacing(4)
        
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Qualità layer (mm):"))
        self.layer_spin = QDoubleSpinBox()
        self.layer_spin.setRange(0.04, 0.4)
        self.layer_spin.setSingleStep(0.02)
        self.layer_spin.setDecimals(2)
        h3.addWidget(self.layer_spin)
        ol.addLayout(h3)
        
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("Infill %:"))
        self.infill_spin = QSpinBox()
        self.infill_spin.setRange(0, 100)
        h4.addWidget(self.infill_spin)
        ol.addLayout(h4)
        
        h5 = QHBoxLayout()
        h5.addWidget(QLabel("Supporti:"))
        self.supports_cb = QCheckBox("Genera supporti")
        h5.addWidget(self.supports_cb)
        h5.addStretch()
        self.bed_adh_cb = QCheckBox("Brim/Adesione")
        h5.addWidget(self.bed_adh_cb)
        ol.addLayout(h5)
        
        layout.addWidget(opts)
        
        btn_row = QHBoxLayout()
        self.send_btn = QPushButton("Invia alla stampante")
        self.send_btn.setStyleSheet(f"background-color: #4CAF50; color: white; padding: 8px 20px;")
        self.send_btn.clicked.connect(self._send_to_printer)
        self.export_btn = QPushButton("Solo esporta")
        self.export_btn.clicked.connect(self._export_profile)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.send_btn)
        layout.addLayout(btn_row)
        
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {TEXT_COLOR}; padding: 4px;")
        layout.addWidget(self.status)
        
        self._on_profile_change(self.profile_combo.currentText())
    
    def _on_profile_change(self, name):
        p = PRINTER_PROFILES.get(name, {})
        bv = p.get("build_volume", (0,0,0))
        nozz = ", ".join(f"{n}mm" for n in p.get("nozzle", [0.4]))
        self.info_label.setText(
            f"Volume: {bv[0]}×{bv[1]}×{bv[2]} mm &nbsp;|&nbsp; Ugelli: {nozz}<br>"
            f"T max: {p.get('max_temp', 0)}°C &nbsp;|&nbsp; Letto: {p.get('bed_temp', 0)}°C &nbsp;|&nbsp; "
            f"Layer default: {p.get('default_layer', 0.2)}mm &nbsp;|&nbsp; Infill: {p.get('default_infill', 15)}%"
        )
        self.layer_spin.setValue(p.get("default_layer", 0.2))
        self.infill_spin.setValue(p.get("default_infill", 15))
        
        self.protocol_combo.blockSignals(True)
        self.protocol_combo.clear()
        for proto in p.get("protocols", ["file"]):
            label = self.PROTOCOL_LABELS.get(proto, proto)
            self.protocol_combo.addItem(label, proto)
        self.protocol_combo.blockSignals(False)
        self._on_protocol_change(self.protocol_combo.currentData())
    
    def _on_protocol_change(self, proto):
        help_text = self.PROTOCOL_HELP.get(proto, "")
        self.proto_help.setText(help_text)
        needs_auth = proto in ("ftp", "mqtt_ftps", "prusalink", "octoprint", "anycubic_cloud")
        self.code_entry.setEnabled(needs_auth or proto == "smb")
        self.user_entry.setEnabled(proto in ("ftp", "smb"))
    
    def _send_to_printer(self):
        profile = PRINTER_PROFILES.get(self.profile_combo.currentText())
        if not profile:
            return
        proto = self.protocol_combo.currentData()
        ip = self.ip_entry.text().strip()
        
        parent = self.parent() or self.parentWidget()
        while parent and not hasattr(parent, 'scene'):
            parent = parent.parent() if parent else None
        if not parent or not hasattr(parent, 'scene'):
            self.status.setText("<span style='color:red;'>Errore: contesto applicazione non trovato</span>")
            return
        
        scene = parent.scene
        visible = [o for o in scene.objects if scene.layers.get(o.metadata.get("layer", "Default"), {}).get("visible", True)]
        if not visible:
            self.status.setText("<span style='color:red;'>Nessun oggetto visibile da stampare</span>")
            return
        
        if proto != "file" and not ip:
            self.status.setText("<span style='color:red;'>Inserisci l'indirizzo IP della stampante</span>")
            return
        
        layer = self.layer_spin.value()
        infill = self.infill_spin.value()
        supports = self.supports_cb.isChecked()
        brim = self.bed_adh_cb.isChecked()
        
        try:
            self.status.setText("Preparazione file...")
            QApplication.processEvents()
            
            import tempfile, os
            tmp_path = os.path.join(tempfile.gettempdir(), f"triviumcad_print_{int(time.time())}.3mf")
            mesh_scene = trimesh.Scene(visible)
            mesh_scene.export(tmp_path, file_type="3mf")
            
            handlers = {
                "mqtt_ftps": self._send_bambulab,
                "creality_http": self._send_creality_http,
                "prusalink": self._send_prusalink,
                "octoprint": self._send_octoprint,
                "ftp": self._send_ftp,
                "smb": self._send_smb,
                "anycubic_cloud": self._send_anycubic_cloud,
                "file": self._send_fileonly
            }
            handler = handlers.get(proto, self._send_fileonly)
            handler(tmp_path, profile, ip, layer, infill, supports, brim)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status.setText(f"<span style='color:red;'>Errore: {str(e)}</span>")
    
    def _prepare_print_attrs(self, profile, layer, infill, supports, brim):
        return {
            "layer_height": layer,
            "infill": infill,
            "support": int(supports),
            "brim": int(brim),
            "bed_temp": profile.get("bed_temp", 60),
            "nozzle_temp": profile.get("max_temp", 220)
        }
    
    def _send_bambulab(self, file_path, profile, ip, layer, infill, supports, brim):
        code = self.code_entry.text().strip()
        if not code:
            self.status.setText("<span style='color:red;'>Inserisci l'Access Code della stampante Bambu Lab</span>")
            return
        try:
            self.status.setText("Caricamento file via FTP...")
            QApplication.processEvents()
            import ftplib, os
            ftp = ftplib.FTP_TLS()
            ftp.connect(ip, 990)
            ftp.login("bblp", code)
            ftp.prot_p()
            remote_name = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_name}", f)
            ftp.quit()
            
            self.status.setText("File caricato. Invio comando di stampa via MQTT...")
            QApplication.processEvents()
            
            import paho.mqtt.client as mqtt, json, uuid
            client = mqtt.Client(client_id="triviumcad_print")
            client.tls_set()
            client.username_pw_set("bblp", code)
            client.connect(ip, 8883, 10)
            client.loop_start()
            
            attrs = self._prepare_print_attrs(profile, layer, infill, supports, brim)
            cmd = json.dumps({
                "print": {
                    "sequence_id": "0", "command": "project_file",
                    "param": f"/sdcard/{remote_name}",
                    "subtask_id": str(uuid.uuid4()),
                    "timelapse": False,
                    "bed_temp": attrs["bed_temp"], "nozzle_temp": attrs["nozzle_temp"],
                    "layer_height": attrs["layer_height"], "infill": attrs["infill"],
                    "support": attrs["support"]
                }
            })
            client.publish(f"device/{ip}/request", cmd)
            time.sleep(1)
            client.disconnect()
            client.loop_stop()
            self.status.setText(f"<span style='color:green;'>✅ Comando inviato a {profile['brand']} {profile['model']} ({ip})</span>")
        except Exception as e:
            self.status.setText(f"<span style='color:red;'>Errore Bambu Lab: {str(e)}</span>")
    
    def _send_creality_http(self, file_path, profile, ip, layer, infill, supports, brim):
        try:
            import requests
            attrs = self._prepare_print_attrs(profile, layer, infill, supports, brim)
            url = f"http://{ip}/upload"
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "model/3mf")}
                data = {"print": "true", **{k: str(v) for k, v in attrs.items()}}
                r = requests.post(url, files=files, data=data, timeout=30)
            if r.status_code in (200, 201):
                self.status.setText(f"<span style='color:green;'>✅ File inviato a Creality {profile['model']} ({ip})</span>")
            else:
                self.status.setText(f"<span style='color:orange;'>⚠️ Risposta HTTP {r.status_code}: {r.text[:200]}</span>")
        except ImportError:
            self.status.setText("Installa: pip install requests")
        except Exception as e:
            self.status.setText(f"<span style='color:red;'>Errore Creality HTTP: {str(e)}</span>")
    
    def _send_prusalink(self, file_path, profile, ip, layer, infill, supports, brim):
        api_key = self.code_entry.text().strip()
        try:
            import requests
            headers = {"X-Api-Key": api_key} if api_key else {}
            url = f"http://{ip}/api/v1/files"
            with open(file_path, "rb") as f:
                r = requests.post(url, headers=headers, files={"file": f}, timeout=30)
            if r.status_code in (200, 201):
                self.status.setText(f"<span style='color:green;'>✅ File inviato a Prusa {profile['model']} ({ip}) via PrusaLink</span>")
            else:
                self.status.setText(f"<span style='color:orange;'>⚠️ Risposta HTTP {r.status_code}</span>")
        except ImportError:
            self.status.setText("Installa: pip install requests")
        except Exception as e:
            self.status.setText(f"<span style='color:red;'>Errore PrusaLink: {str(e)}</span>")
    
    def _send_octoprint(self, file_path, profile, ip, layer, infill, supports, brim):
        api_key = self.code_entry.text().strip()
        try:
            import requests
            headers = {"X-Api-Key": api_key} if api_key else {}
            url = f"http://{ip}/api/files/local"
            with open(file_path, "rb") as f:
                r = requests.post(url, headers=headers,
                    files={"file": (os.path.basename(file_path), f, "model/3mf")},
                    data={"select": "true", "print": "true"}, timeout=60)
            if r.status_code in (200, 201):
                self.status.setText(f"<span style='color:green;'>✅ File inviato a OctoPrint ({ip}) — stampa avviata</span>")
            else:
                self.status.setText(f"<span style='color:orange;'>⚠️ Risposta HTTP {r.status_code}: {r.text[:200]}</span>")
        except ImportError:
            self.status.setText("Installa: pip install requests")
        except Exception as e:
            self.status.setText(f"<span style='color:red;'>Errore OctoPrint: {str(e)}</span>")
    
    def _send_ftp(self, file_path, profile, ip, layer, infill, supports, brim):
        user = self.user_entry.text().strip() or "anonymous"
        pw = self.code_entry.text().strip() or ""
        try:
            import ftplib, os
            ftp = ftplib.FTP()
            ftp.connect(ip, 21)
            ftp.login(user, pw)
            remote_name = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_name}", f)
            ftp.quit()
            self.status.setText(f"<span style='color:green;'>✅ File caricato via FTP su {ip}</span>")
        except Exception as e:
            self.status.setText(f"<span style='color:red;'>Errore FTP: {str(e)}</span>")
    
    def _send_smb(self, file_path, profile, ip, layer, infill, supports, brim):
        user = self.user_entry.text().strip()
        pw = self.code_entry.text().strip()
        share_path = self.ip_entry.text().strip()
        try:
            import shutil, os
            if not share_path.startswith("//") and not share_path.startswith("\\\\"):
                share_path = f"//{share_path}/share"
            out_path = os.path.join(share_path, os.path.basename(file_path))
            shutil.copy2(file_path, out_path)
            self.status.setText(f"<span style='color:green;'>✅ File copiato su {share_path}</span>")
        except Exception as e:
            self.status.setText(f"<span style='color:red;'>Errore copia SMB: {str(e)}</span>")
    
    def _send_anycubic_cloud(self, file_path, profile, ip, layer, infill, supports, brim):
        email = self.user_entry.text().strip()
        pw = self.code_entry.text().strip()
        if not email or not pw:
            self.status.setText("<span style='color:red;'>Inserisci email e password Anycubic Cloud</span>")
            return
        try:
            import requests, json
            session = requests.Session()
            login = session.post("https://cloud.anycubic.com/api/v1/login",
                json={"email": email, "password": pw}, timeout=15)
            if login.status_code != 200:
                self.status.setText(f"<span style='color:red;'>Login Anycubic fallito: {login.status_code}</span>")
                return
            token = login.json().get("data", {}).get("token", "")
            if not token:
                self.status.setText("<span style='color:red;'>Token Anycubic non ricevuto</span>")
                return
            
            with open(file_path, "rb") as f:
                upload = session.post("https://cloud.anycubic.com/api/v1/file/upload",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": f}, timeout=60)
            if upload.status_code == 200:
                self.status.setText(f"<span style='color:green;'>✅ File caricato su Anycubic Cloud. Avvia la stampa dall'app Anycubic.</span>")
            else:
                self.status.setText(f"<span style='color:orange;'>⚠️ Upload su Anycubic: {upload.status_code} {upload.text[:200]}</span>")
        except ImportError:
            self.status.setText("Installa: pip install requests")
        except Exception as e:
            self.status.setText(f"<span style='color:red;'>Errore Anycubic Cloud: {str(e)}</span>")
    
    def _send_fileonly(self, file_path, profile, ip, layer, infill, supports, brim):
        out_dir = os.path.expanduser("~/Desktop")
        try:
            import shutil, os
            out_path = os.path.join(out_dir, os.path.basename(file_path))
            shutil.copy2(file_path, out_path)
        except Exception as e:
            print(f"ERRORE: _send_fileonly fallito: {e}")
            pass
        self.status.setText(
            f"<span style='color:green;'>✅ File pronto per {profile['brand']} {profile['model']}</span>"
            f"<br>Layer: {layer}mm | Infill: {infill}% | Supporti: {'Sì' if supports else 'No'}"
            f"<br>Usa File → Esporta per salvare con nome personalizzato"
        )
    
    def _export_profile(self):
        profile = PRINTER_PROFILES.get(self.profile_combo.currentText())
        if not profile:
            return
        parent = self.parent() or self.parentWidget()
        while parent and not hasattr(parent, 'scene'):
            parent = parent.parent() if parent else None
        if not parent:
            return
        scene = parent.scene
        visible = [o for o in scene.objects if scene.layers.get(o.metadata.get("layer", "Default"), {}).get("visible", True)]
        if not visible:
            return
        
        layer = self.layer_spin.value()
        infill = self.infill_spin.value()
        supports = self.supports_cb.isChecked()
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta con profilo stampante",
            f"{profile['brand']}_{profile['model']}.3mf",
            "File 3MF (*.3mf);;File STL (*.stl)"
        )
        if path:
            try:
                scene_obj = trimesh.Scene(visible)
                scene_obj.export(path)
                self.status.setText(
                    f"<span style='color:green;'>✅ Esportato: {path}</span>"
                    f"<br>Profilo: {profile['brand']} {profile['model']}"
                    f"<br>Layer: {layer}mm | Infill: {infill}% | Supporti: {'Sì' if supports else 'No'}"
                )
            except Exception as e:
                self.status.setText(f"<span style='color:red;'>Errore: {str(e)}</span>")

# === PROPERTIES PANEL ===
class PropertiesPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.old_widgets = []
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        main_layout.setContentsMargins(6, 6, 6, 6)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        main_layout.addWidget(scroll)
        
        container = QWidget()
        container_layout = QVBoxLayout()
        container.setLayout(container_layout)
        container_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
        
        self.placeholder = QLabel("🖱️ Seleziona un oggetto")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet(f"padding:15px;color:#2C4A6E;font-style:italic;font-size:10px;background-color: {BACKGROUND_COLOR};")
        container_layout.addWidget(self.placeholder)
        container_layout.addStretch()
        
        self.selection_group = QGroupBox("🔍 Selezione")
        self.selection_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                margin-top: 1ex;
                font-weight: bold;
                color: {BORDER_COLOR};
                background-color: {BACKGROUND_COLOR};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 7px;
                padding: 0 3px 0 3px;
                color: {BORDER_COLOR};
            }}
        """)
        selection_layout = QFormLayout()
        self.selection_group.setLayout(selection_layout)
        self.selection_group.hide()
        container_layout.addWidget(self.selection_group)
        
        self.selection_count = QLabel("0")
        self.selection_volume = QLabel("0")
        self.selection_area = QLabel("0")
        
        selection_layout.addRow("Oggetti:", self.selection_count)
        selection_layout.addRow("Vol. Tot:", self.selection_volume)
        selection_layout.addRow("Area Tot:", self.selection_area)
        
        self.coordinates_group = QGroupBox("📍 Coordinate & Dimensioni")
        self.coordinates_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                margin-top: 1ex;
                font-weight: bold;
                color: {BORDER_COLOR};
                background-color: {BACKGROUND_COLOR};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 7px;
                padding: 0 3px 0 3px;
                color: {BORDER_COLOR};
            }}
        """)
        form_layout = QFormLayout()
        self.coordinates_group.setLayout(form_layout)
        self.coordinates_group.hide()
        container_layout.addWidget(self.coordinates_group)
        
        self.x_label = QLabel("X:0.00")
        self.y_label = QLabel("Y:0.00")
        self.z_label = QLabel("Z:0.00")
        self.width_label = QLabel("L:0.00")
        self.height_label = QLabel("H:0.00")
        self.depth_label = QLabel("P:0.00")
        
        for label, style in [
            (self.x_label, f"color:#0FF;font:11px mono;background-color: {BACKGROUND_COLOR};"),
            (self.y_label, f"color:#0FF;font:11px mono;background-color: {BACKGROUND_COLOR};"),
            (self.z_label, f"color:#0FF;font:11px mono;background-color: {BACKGROUND_COLOR};"),
            (self.width_label, f"color:#FFD700;font:11px mono;background-color: {BACKGROUND_COLOR};"),
            (self.height_label, f"color:#FFD700;font:11px mono;background-color: {BACKGROUND_COLOR};"),
            (self.depth_label, f"color:#FFD700;font:11px mono;background-color: {BACKGROUND_COLOR};")
        ]:
            label.setStyleSheet(style)
        
        form_layout.addRow("🎯 X:", self.x_label)
        form_layout.addRow("🎯 Y:", self.y_label)
        form_layout.addRow("🎯 Z:", self.z_label)
        form_layout.addRow("📏 L:", self.width_label)
        form_layout.addRow("📏 H:", self.height_label)
        form_layout.addRow("📏 P:", self.depth_label)
        
        self.status_group = QGroupBox("📊 Stato")
        self.status_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                margin-top: 1ex;
                font-weight: bold;
                color: {BORDER_COLOR};
                background-color: {BACKGROUND_COLOR};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 7px;
                padding: 0 3px 0 3px;
                color: {BORDER_COLOR};
            }}
        """)
        status_layout = QFormLayout()
        self.status_group.setLayout(status_layout)
        self.status_group.hide()
        container_layout.addWidget(self.status_group)
        
        self.volume_label = QLabel("0")
        self.area_label = QLabel("0")
        self.watertight_label = QLabel("-")
        
        status_layout.addRow("Vol:", self.volume_label)
        status_layout.addRow("Area:", self.area_label)
        status_layout.addRow("WT:", self.watertight_label)
        
        self.params_layout = QFormLayout()
        container_layout.addLayout(self.params_layout)
        self.spinboxes = {}

    def update_ui(self, selected_objects):
        try:
            for widget in self.old_widgets:
                if widget:
                    widget.deleteLater()
            self.old_widgets.clear()
            self.spinboxes.clear()
            
            while self.params_layout.count():
                item = self.params_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            if not selected_objects:
                self.placeholder.show()
                self.selection_group.hide()
                self.coordinates_group.hide()
                self.status_group.hide()
                return
            
            self.placeholder.hide()
            self.selection_group.show()
            
            self.selection_count.setText(str(len(selected_objects)))
            
            total_volume = sum(obj.volume for obj in selected_objects if hasattr(obj, 'volume'))
            self.selection_volume.setText(f"{total_volume:.1f} mm³")
            
            total_area = sum(obj.area for obj in selected_objects if hasattr(obj, 'area'))
            self.selection_area.setText(f"{total_area:.1f} mm²")
            
            if len(selected_objects) == 1:
                obj = selected_objects[0]
                
                self.coordinates_group.show()
                self.status_group.show()
                
                vertices = np.asarray(obj.vertices)
                center = (vertices.min(0) + vertices.max(0)) / 2
                extents = vertices.max(0) - vertices.min(0)
                
                self.x_label.setText(f"X:{center[0]:.2f}")
                self.y_label.setText(f"Y:{center[1]:.2f}")
                self.z_label.setText(f"Z:{center[2]:.2f}")
                self.width_label.setText(f"L:{extents[0]:.2f}")
                self.height_label.setText(f"H:{extents[2]:.2f}")
                self.depth_label.setText(f"P:{extents[1]:.2f}")
                self.volume_label.setText(f"{obj.volume:.1f} mm³")
                self.area_label.setText(f"{obj.area:.1f} mm²")
                self.watertight_label.setText("✅ Si" if hasattr(obj, 'is_watertight') and obj.is_watertight else "⚠️ No")
                
                if obj.metadata.get("shape_type") in [s["type"] for s in SHAPE_LIBRARY.values()]:
                    for key, value in obj.metadata.get("params", {}).items():
                        if key in ("tipo", "spessore"):
                            continue
                        
                        spinbox = QDoubleSpinBox()
                        spinbox.setRange(0, 9999)
                        spinbox.setValue(float(value) if isinstance(value, (int, float)) else 0)
                        spinbox.valueChanged.connect(lambda v, k=key: self._on_param_changed(k, v))
                        
                        self.params_layout.addRow(key.replace("_", " ").title(), spinbox)
                        self.spinboxes[key] = spinbox
                        self.old_widgets.append(spinbox)
            else:
                self.coordinates_group.hide()
                self.status_group.hide()
        except Exception as e:
            print(f"Errore update_ui: {e}")

    def _on_param_changed(self, key, value):
        if self.window and self.window.scene.has_selection:
            self.window.scene.start_operation()
            obj = self.window.scene.selected_objects[0]
            
            obj.metadata["params"][key] = value
            
            try:
                new_mesh = create_mesh(obj.metadata["shape_type"], obj.metadata["params"])
                new_mesh.metadata = obj.metadata.copy()
                for k in ["_gl_verts", "_gl_normals", "_gl_vbo_verts", "_gl_vbo_normals"]:
                    new_mesh.metadata.pop(k, None)
                index = self.window.scene.objects.index(obj)
                self.window.scene.objects[index] = new_mesh
                self.window.scene.selected_objects[0] = new_mesh
                self.window.scene.end_operation()
                self.window.gl_widget.update()
            except Exception as e:
                self.window.scene.cancel_operation()
                print(f"Errore nella rigenerazione della mesh: {e}")

# =============================================================================
# BLOCCO 4: MAIN APPLICATION
# =============================================================================
# === UTILITY ICONE ===
def _make_icon(text, color, size=24):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(*color))
    p.setPen(QPen(QColor(*color).darker(150), 1))
    r = size // 2 - 2
    p.drawEllipse(QPoint(size//2, size//2), r, r)
    p.setPen(QColor(255, 255, 255))
    f = QFont("Segoe UI", size // 3, QFont.Bold)
    p.setFont(f)
    p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, text[:2])
    p.end()
    return QIcon(pm)

def _make_eye_icon(visible=True, size=14):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    cx, cy = size // 2, size // 2
    ew, eh = size - 4, size // 2 - 1
    if visible:
        p.setPen(QPen(QColor("#2C5F8A"), 1.2))
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawEllipse(int(cx - ew/2), int(cy - eh/2), ew, eh)
        p.setBrush(QColor("#2C5F8A"))
        p.drawEllipse(int(cx - 2), int(cy - 2), 4, 4)
    else:
        p.setPen(QPen(QColor("#aaa"), 1.2))
        p.setBrush(QColor(240, 240, 240, 200))
        p.drawEllipse(int(cx - ew/2), int(cy - eh/2), ew, eh)
        p.setPen(QPen(QColor("#cc4444"), 1.5))
        p.drawLine(2, 2, size - 2, size - 2)
    p.end()
    return QIcon(pm)

def _make_lock_icon(locked=True, size=14):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    bw, bh = size - 4, size // 2
    bx = (size - bw) // 2
    by = size - bh - 2
    if locked:
        p.setPen(QPen(QColor("#b8960a"), 1.2))
        p.setBrush(QColor("#e8c840"))
        p.drawRoundedRect(bx, by, bw, bh, 2, 2)
        p.setPen(QPen(QColor("#b8960a"), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawArc(bx + 1, by - 3, bw - 2, bw - 2, 180 * 16, 180 * 16)
    else:
        p.setPen(QPen(QColor("#999"), 1.2))
        p.setBrush(QColor(200, 200, 200))
        p.drawRoundedRect(bx, by, bw, bh, 2, 2)
        p.setPen(QPen(QColor("#999"), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawArc(bx + 1, by - 3, bw - 2, bw - 2, 180 * 16, 160 * 16)
    p.end()
    return QIcon(pm)

# === CONSOLE ===
class _CaptureStream:
    def __init__(self, callback, original):
        self.callback = callback
        self.original = original
    def write(self, text):
        if self.original:
            try:
                self.original.write(text)
            except UnicodeEncodeError:
                try:
                    self.original.write(text.encode('utf-8', errors='replace').decode('utf-8'))
                except Exception as e:
                    print(f"[TriviumCAD] _CaptureStream.write (fallback utf-8): {e}")
            except Exception as e:
                print(f"[TriviumCAD] _CaptureStream.write: {e}")
        if text:
            self.callback(text)
    def flush(self):
        if self.original:
            try:
                self.original.flush()
            except Exception as e:
                print(f"[TriviumCAD] _CaptureStream.flush: {e}")

class ConsoleDialog(QDialog):
    def __init__(self, scene, gl_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Console Python — TriviumCAD")
        self.resize(520, 360)
        self.scene = scene
        self.gl_widget = gl_widget
        self.history = []
        self.history_idx = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e; color: #d4d4d4;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #333; border-radius: 3px;
                padding: 4px;
            }
        """)
        layout.addWidget(self.output)

        self.input = QLineEdit()
        self.input.setStyleSheet("""
            QLineEdit {
                background: #252526; color: #d4d4d4;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #333; border-radius: 3px;
                padding: 4px 6px;
            }
        """)
        self.input.returnPressed.connect(self._execute)
        layout.addWidget(self.input)

        self._print_banner()
        self.input.setFocus()

        import sys as _sys, queue
        self._capture_queue = queue.Queue()
        self._capture_timer = QTimer(self)
        self._capture_timer.timeout.connect(self._drain_capture_queue)
        self._capture_timer.start(50)
        self._orig_stdout = _sys.stdout
        self._orig_stderr = _sys.stderr
        _sys.stdout = _CaptureStream(self._capture_queue.put, self._orig_stdout)
        _sys.stderr = _CaptureStream(self._capture_queue.put, self._orig_stderr)
        _sys.stdout.write("Console attiva — stdout/stderr catturati\n")

    def _drain_capture_queue(self):
        import sys as _sys
        while True:
            try:
                text = self._capture_queue.get_nowait()
            except _sys.modules['queue'].Empty:
                break
            text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')
            cur = self.output.textCursor()
            cur.movePosition(QTextCursor.End)
            cur.insertHtml(f'<span style="color:#d4d4d4;">{text}</span>')
            self.output.setTextCursor(cur)
            scroll = self.output.verticalScrollBar()
            scroll.setValue(scroll.maximum())

    def closeEvent(self, event):
        import sys as _sys
        _sys.stdout = self._orig_stdout
        _sys.stderr = self._orig_stderr
        super().closeEvent(event)

    def _print_banner(self):
        self.output.append(
            '<span style="color:#569cd6;">╔══════════════════════════════════════╗</span><br>'
            '<span style="color:#569cd6;">║  TriviumCAD Python Console              ║</span><br>'
            '<span style="color:#569cd6;">╚══════════════════════════════════════╝</span><br>'
            '<span style="color:#888;">Digita codice Python e premi Invio.</span><br>'
            '<span style="color:#888;">↑↓ cronologia. Variabili disponibili:</span><br>'
            '<span style="color:#6a9955;">  scene</span><span style="color:#888;"> — scena corrente</span><br>'
            '<span style="color:#6a9955;">  gl</span><span style="color:#888;"> — widget 3D</span><br>'
            '<span style="color:#6a9955;">  selected</span><span style="color:#888;"> — oggetti selezionati</span><br>'
            '<span style="color:#6a9955;">  obj</span><span style="color:#888;"> — primo selezionato</span><br>'
            '<span style="color:#6a9955;">  np, trimesh</span><span style="color:#888;"> — librerie</span><br>'
            '<span style="color:#888;">Tutto stdout/stderr dell\'app appare qui.</span><br>'
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            if self.history and self.history_idx > 0:
                self.history_idx -= 1
                self.input.setText(self.history[self.history_idx])
        elif event.key() == Qt.Key_Down:
            if self.history and self.history_idx < len(self.history) - 1:
                self.history_idx += 1
                self.input.setText(self.history[self.history_idx])
            else:
                self.history_idx = len(self.history)
                self.input.clear()
        super().keyPressEvent(event)

    def _execute(self):
        code = self.input.text().strip()
        if not code:
            return
        self.history.append(code)
        self.history_idx = len(self.history)
        self.input.clear()
        self.output.append(f'<span style="color:#569cd6;">&gt;&gt;&gt;</span> {code}')
        import io, contextlib, traceback
        env = {
            "scene": self.scene,
            "gl": self.gl_widget,
            "selected": self.scene.selected_objects,
            "obj": self.scene.single_selection,
            "np": np,
            "trimesh": trimesh,
        }
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                result = eval(code, env)
            out = buf.getvalue()
            if out:
                self.output.append(f'<span style="color:#d4d4d4;">{out}</span>')
            if result is not None:
                self.output.append(f'<span style="color:#ce9178;">{result!r}</span>')
        except SyntaxError:
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    exec(code, env)
                out = buf.getvalue()
                if out:
                    self.output.append(f'<span style="color:#d4d4d4;">{out}</span>')
            except Exception as e:
                self.output.append(f'<span style="color:#f44747;">{traceback.format_exc()}</span>')
        except Exception as e:
            self.output.append(f'<span style="color:#f44747;">{traceback.format_exc()}</span>')
        self.gl_widget.update()
        scroll = self.output.verticalScrollBar()
        scroll.setValue(scroll.maximum())

# === CADWindow (MAIN WINDOW) ===
class CADWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1280, 720)
        self.setMinimumSize(960, 540)
        
        self.scene = Scene()
        self.gl_widget = GLWidget(self.scene, self)
        self.right_panel = None
        self.console_dialog = None
        
        self._setup_ui()
        
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._update_stats)
        self.fps_timer.start(500)
        self.frames = 0
        self.last_time = time.time()
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Pronto")
        self.scene._callback_notify = self._show_notify

    def _show_notify(self, message: str) -> None:
        try:
            self.status_bar.showMessage(message, 3000)
        except Exception as e:
            print(f"[TriviumCAD] Errore nell'aggiornamento della status bar: {e}")
    
    def _setup_ui(self):
        self._setup_menu()
        self._setup_toolbar()
        self._setup_layout()
        self._setup_outliner()
    
    def _run_blocking(self, title, worker_fn, callback_fn):
        from PyQt5.QtWidgets import QApplication, QMessageBox as _QMsgBox
        try:
            QApplication.processEvents()
            result = worker_fn()
            if isinstance(result, Exception):
                print(f"[TriviumCAD] ERRORE: {result}")
                _QMsgBox.warning(self, "Errore", f"Operazione fallita:\n{result}")
            else:
                callback_fn(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[TriviumCAD] ERRORE in _run_blocking: {e}")
    
    def _undo_action(self):
        if self.scene.undo():
            self.gl_widget._invalidate_all_vbos()
            self.update_ui()
            self.gl_widget.update()
    
    def _redo_action(self):
        if self.scene.redo():
            self.gl_widget._invalidate_all_vbos()
            self.update_ui()
            self.gl_widget.update()
    
    # --- MENU ---
    def _setup_menu(self):
        menu_bar = self.menuBar()
        
        file_menu = menu_bar.addMenu("File")
        file_menu.addAction("Nuovo", self._new)
        file_menu.addAction("Apri", self._open)
        file_menu.addAction("Salva", self._save)
        file_menu.addSeparator()
        file_menu.addAction("Importa", self._import)
        file_menu.addAction("Esporta", self._export)
        file_menu.addAction("Invia alla stampante...", self._show_printer_dialog)
        file_menu.addSeparator()
        file_menu.addAction("Esci", self.close)
        
        edit_menu = menu_bar.addMenu("Modifica")
        edit_menu.addAction("Annulla", self._undo_action).setShortcut("Ctrl+Z")
        edit_menu.addAction("Ripristina", self._redo_action).setShortcut("Ctrl+Y")
        edit_menu.addSeparator()
        edit_menu.addAction("Duplica", self.scene.duplicate).setShortcut("Ctrl+D")
        edit_menu.addAction("Elimina", self.scene.delete).setShortcut("Del")
        edit_menu.addSeparator()
        edit_menu.addAction("Chamfer...", self._cad_chamfer)
        edit_menu.addAction("Pattern lineare...", self._cad_pattern_linear)
        edit_menu.addAction("Pattern circolare...", self._cad_pattern_circular)
        edit_menu.addSeparator()
        edit_menu.addAction("Specchia (Mirror X)", lambda: self._cad_mirror("x"))
        edit_menu.addAction("Specchia (Mirror Y)", lambda: self._cad_mirror("y"))
        edit_menu.addAction("Specchia (Mirror Z)", lambda: self._cad_mirror("z"))
        
        mesh_menu = menu_bar.addMenu("Mesh")
        mesh_menu.addAction("Smooth...", self._cad_smooth)
        mesh_menu.addAction("Subdivide...", self._cad_subdivide)
        mesh_menu.addAction("Decimate...", self._cad_decimate)
        mesh_menu.addSeparator()
        mesh_menu.addAction("Ripara", self._cad_repair)
        
        opts_menu = menu_bar.addMenu("Opzioni")
        self._snap_act = QAction("Snap Griglia", self)
        self._snap_act.setCheckable(True)
        self._snap_act.setChecked(self.scene.snap_grid)
        self._snap_act.triggered.connect(self._toggle_snap)
        opts_menu.addAction(self._snap_act)
        self._magnet_act = QAction("Magneti", self)
        self._magnet_act.setCheckable(True)
        self._magnet_act.setChecked(self.scene.magnetic_snap)
        self._magnet_act.triggered.connect(self._toggle_magnetic)
        opts_menu.addAction(self._magnet_act)
        opts_menu.addSeparator()
        opts_menu.addAction("Scala Griglia...", self._set_grid_scale)
        opts_menu.addSeparator()
        self._console_act = QAction("Console Python", self)
        self._console_act.setCheckable(True)
        self._console_act.setChecked(False)
        self._console_act.triggered.connect(self._toggle_console)
        opts_menu.addAction(self._console_act)
        opts_menu.addSeparator()
        opts_menu.addAction("Mostra Tutorial...", self._show_tutorial)
        
        help_menu = menu_bar.addMenu("Aiuto")
        help_menu.addAction("Tutorial", self._show_tutorial)
        help_menu.addAction("Informazioni", self._show_about)
    
    # --- TOOLBAR ---
    def _setup_toolbar(self):
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        tb_container = QWidget()
        tb_layout = QHBoxLayout(tb_container)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(2)

        def sep():
            s = QFrame()
            s.setFrameShape(QFrame.VLine)
            s.setFrameShadow(QFrame.Sunken)
            return s

        def mkbtn(text, cb, icon_color=(100,150,200)):
            b = QPushButton(_make_icon(text.split()[-1][:2], icon_color, 20), text)
            b.setIconSize(QSize(20, 20))
            b.setFlat(True)
            b.setStyleSheet("""
                QPushButton {
                    color: #0C1E36;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 5px 10px;
                    border: 2px solid #2C5F8A;
                    border-radius: 14px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(200,220,240,0.5), stop:1 rgba(200,220,240,0.2));
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(207,250,254,0.6), stop:1 rgba(207,250,254,0.3));
                    border-color: #3A7FAA;
                }
            """)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(cb)
            return b

        tb_layout.addStretch()
        tb_layout.addWidget(mkbtn("Da2 a 3D", self._import_2d_to_3d, (180,100,80)))
        tb_layout.addWidget(sep())
        tb_layout.addWidget(mkbtn("Nuovo", self._new, (100,180,100)))
        tb_layout.addWidget(mkbtn("Apri", self._open, (120,140,200)))
        tb_layout.addWidget(mkbtn("Salva", self._save, (140,120,80)))
        tb_layout.addWidget(sep())
        bool_btn = QPushButton(_make_icon("B", (80,120,160), 20), "Booleane")
        bool_btn.setIconSize(QSize(20, 20))
        bool_btn.setFlat(True)
        bool_btn.setStyleSheet("""
            QPushButton {
                color: #0C1E36;
                font-size: 12px;
                font-weight: bold;
                padding: 5px 10px;
                border: 2px solid #2C5F8A;
                border-radius: 14px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(200,220,240,0.5), stop:1 rgba(200,220,240,0.2));
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(207,250,254,0.6), stop:1 rgba(207,250,254,0.3));
                border-color: #3A7FAA;
            }
        """)
        bool_btn.setCursor(Qt.PointingHandCursor)
        bool_menu = QMenu(self)
        bool_menu.addAction("Unione", lambda: self._run_boolean("unione"))
        bool_menu.addAction("Sottrazione", lambda: self._run_boolean("sottrazione"))
        bool_menu.addAction("Intersezione", lambda: self._run_boolean("intersezione"))
        bool_btn.setMenu(bool_menu)
        tb_layout.addWidget(bool_btn)
        tb_layout.addWidget(sep())
        tb_layout.addWidget(mkbtn("Guscio", self._shell, (160,140,80)))
        tb_layout.addWidget(sep())
        snap_btn = mkbtn("Snap", self._toggle_snap, (100,160,180))
        snap_btn.setCheckable(True)
        snap_btn.setChecked(self.scene.snap_grid)
        tb_layout.addWidget(snap_btn)
        magnet_btn = mkbtn("Magneti", self._toggle_magnetic, (140,100,160))
        magnet_btn.setCheckable(True)
        magnet_btn.setChecked(self.scene.magnetic_snap)
        tb_layout.addWidget(magnet_btn)
        tb_layout.addStretch()
        tb_layout.addSpacing(8)
        
        donate_btn = QPushButton("❤️  Sostieni")
        donate_btn.setFlat(True)
        donate_btn.setMinimumHeight(34)
        donate_btn.setStyleSheet("""
            QPushButton {
                color: #0C1E36;
                font-size: 12px;
                font-weight: bold;
                padding: 5px 10px;
                border: 2px solid #f5a623;
                border-radius: 14px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(245,166,35,0.12), stop:1 rgba(245,166,35,0.04));
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(245,166,35,0.25), stop:1 rgba(245,166,35,0.12));
                border-color: #ffc107;
                color: #0C1E36;
            }
        """)
        donate_btn.setCursor(Qt.PointingHandCursor)
        donate_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.paypal.com/donate/?hosted_button_id=BC8Q8DEFUE9LJ")))
        tb_layout.addWidget(donate_btn)
        
        tb_layout.addSpacing(6)
        
        sito_btn = QPushButton("Sito")
        sito_btn.setFlat(True)
        sito_btn.setMinimumHeight(34)
        sito_btn.setStyleSheet("""
            QPushButton {
                color: #0C1E36;
                font-size: 12px;
                font-weight: bold;
                padding: 5px 10px;
                border: 2px solid #5a9fd4;
                border-radius: 14px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(90,159,212,0.12), stop:1 rgba(90,159,212,0.04));
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(90,159,212,0.25), stop:1 rgba(90,159,212,0.12));
                border-color: #7eb8e0;
                color: #0C1E36;
            }
        """)
        sito_btn.setCursor(Qt.PointingHandCursor)
        sito_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://n47lab.altervista.org")))
        tb_layout.addWidget(sito_btn)
        
        tb_layout.addSpacing(4)
        toolbar.addWidget(tb_container)
    
    # --- LAYOUT ---
    def _setup_layout(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        left_panel = self._create_left_panel()
        left_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        main_layout.addWidget(left_panel, 1)
        
        self.gl_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.gl_widget, 5)
        
        self.right_panel = self._create_right_panel()
        self.right_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        main_layout.addWidget(self.right_panel, 1)
        
        self.setCentralWidget(main_widget)
    
    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        shape_icons = {
            "Cubo": (100,160,220), "Cilindro": (140,200,120), "Sfera": (220,140,120),
            "Cono": (200,180,100), "collare": (180,120,160), "Esagono": (120,180,160),
            "Spirale": (160,140,200), "Arco": (200,160,140), "Scatola vuota": (140,160,180)
        }
        
        shapes_group = QGroupBox("Forme Primitive")
        shapes_layout = QGridLayout(shapes_group)
        shapes_layout.setSpacing(2)
        bm = self.fontMetrics()
        bmin_h = max(bm.height() + 10, 28)
        for i, (name, shape) in enumerate(SHAPE_LIBRARY.items()):
            c = shape_icons.get(name, (150,150,150))
            btn = QPushButton(_make_icon(name[:2], c, 20), name)
            btn.setIconSize(QSize(20, 20))
            btn.setMinimumHeight(bmin_h)
            btn.clicked.connect(lambda checked=False, s=shape["type"], p=shape["params"]: self._add_shape(s, p))
            shapes_layout.addWidget(btn, i // 3, i % 3)
        layout.addWidget(shapes_group)
        mech_group = QGroupBox("Meccanica")
        layout.addWidget(mech_group)
        mech_layout = QVBoxLayout(mech_group)
        mech_layout.setSpacing(6)
        fm = self.fontMetrics()
        combo_h = max(fm.height() + 10, 28)
        btn_h = max(fm.height() + 12, 32)
        thr_sub = QGroupBox("Filettatura")
        thr_l = QVBoxLayout(thr_sub)
        thr_l.setSpacing(6)
        thr_l.addWidget(QLabel("Tipo:"))
        self.thread_type = QComboBox()
        self.thread_type.addItems(["Interna", "Esterna"])
        self.thread_type.setCurrentText("Esterna")
        self.thread_type.setMinimumWidth(120)
        self.thread_type.setMinimumHeight(combo_h)
        thr_l.addWidget(self.thread_type)
        thr_l.addWidget(QLabel("Modalità:"))
        self.thread_mode = QComboBox()
        self.thread_mode.addItems(["Auto (profilo)", "Metrico", "UNF", "UNC", "Gas"])
        self.thread_mode.setMinimumWidth(120)
        self.thread_mode.setMinimumHeight(combo_h)
        thr_l.addWidget(self.thread_mode)
        thr_l.addWidget(QLabel("Profilo:"))
        self.thread_profile = QComboBox()
        self.thread_profile.addItems(["Trapezio", "Filo", "Arrotondato"])
        self.thread_profile.setCurrentText("Filo")
        self.thread_profile.setMinimumWidth(120)
        self.thread_profile.setMinimumHeight(combo_h)
        thr_l.addWidget(self.thread_profile)
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Passo:"))
        self.thread_pitch = QDoubleSpinBox()
        self.thread_pitch.setRange(0.1, 10)
        self.thread_pitch.setValue(1.5)
        self.thread_pitch.setMinimumWidth(80)
        self.thread_pitch.setMinimumHeight(combo_h)
        pr.addWidget(self.thread_pitch)
        thr_l.addLayout(pr)
        pd = QHBoxLayout()
        pd.addWidget(QLabel("Profondità:"))
        self.thread_depth = QDoubleSpinBox()
        self.thread_depth.setRange(0.01, 50)
        self.thread_depth.setValue(1.0)
        self.thread_depth.setDecimals(2)
        self.thread_depth.setSingleStep(0.1)
        self.thread_depth.setMinimumWidth(80)
        self.thread_depth.setMinimumHeight(combo_h)
        pd.addWidget(self.thread_depth)
        thr_l.addLayout(pd)
        app_btn = QPushButton("Applica Filettatura", clicked=self._apply_threading)
        app_btn.setMinimumHeight(btn_h)
        thr_l.addWidget(app_btn)
        mech_layout.addWidget(thr_sub)
        sl_sub = QGroupBox("Affetta")
        sl_l = QVBoxLayout(sl_sub)
        sl_l.setSpacing(4)
        ar = QHBoxLayout()
        ar.addWidget(QLabel("Asse:"))
        self.slice_axis = QComboBox()
        self.slice_axis.addItems(["Z", "Y", "X"])
        self.slice_axis.setMinimumHeight(combo_h)
        ar.addWidget(self.slice_axis)
        sl_l.addLayout(ar)
        pr2 = QHBoxLayout()
        pr2.addWidget(QLabel("Offset:"))
        self.slice_pos = QDoubleSpinBox()
        self.slice_pos.setRange(-500, 500)
        self.slice_pos.setMinimumHeight(combo_h)
        pr2.addWidget(self.slice_pos)
        pr2.addWidget(QLabel("Pezzi:"))
        self.slice_count = QSpinBox()
        self.slice_count.setRange(2, 100)
        self.slice_count.setValue(2)
        self.slice_count.setMinimumHeight(combo_h)
        self.slice_count.setMinimumWidth(50)
        pr2.addWidget(self.slice_count)
        sl_l.addLayout(pr2)
        sl_btn = QPushButton("Affetta Selezione", clicked=self._slice_selection)
        sl_btn.setMinimumHeight(btn_h)
        sl_l.addWidget(sl_btn)
        mech_layout.addWidget(sl_sub)
        fi_sub = QGroupBox("Arrotonda")
        fi_l = QVBoxLayout(fi_sub)
        fi_l.setSpacing(4)
        fr2 = QHBoxLayout()
        fr2.addWidget(QLabel("Raggio:"))
        self.fillet_radius_spin = QDoubleSpinBox()
        self.fillet_radius_spin.setRange(0.1, 100)
        self.fillet_radius_spin.setValue(25.0)
        self.fillet_radius_spin.setSingleStep(1.0)
        self.fillet_radius_spin.setMinimumHeight(combo_h)
        fr2.addWidget(self.fillet_radius_spin)
        fi_l.addLayout(fr2)
        fi_btn = QPushButton("Applica Arrotondamento", clicked=self._apply_fillet)
        fi_btn.setMinimumHeight(btn_h)
        fi_l.addWidget(fi_btn)
        mech_layout.addWidget(fi_sub)
        layout.addWidget(mech_group)
        
        cam_group = QGroupBox("CAM")
        cam_layout = QVBoxLayout(cam_group)
        cam_layout.setSpacing(4)
        td = QDoubleSpinBox()
        td.setRange(0.5, 10); td.setValue(3.0); td.setSuffix(" mm")
        td.setMinimumHeight(combo_h)
        td.valueChanged.connect(lambda v: setattr(self.scene, "tool_diameter", v))
        so = QDoubleSpinBox()
        so.setRange(0.1, 5); so.setValue(0.5); so.setSuffix(" mm")
        so.setMinimumHeight(combo_h)
        so.valueChanged.connect(lambda v: setattr(self.scene, "stepover", v))
        cam_layout.addWidget(QLabel("Diametro utensile:"))
        cam_layout.addWidget(td)
        cam_layout.addWidget(QLabel("Stepover:"))
        cam_layout.addWidget(so)
        cam_layout.addWidget(QPushButton("Genera Toolpath", clicked=self._generate_toolpath))
        layout.addWidget(cam_group)
        layout.addStretch(1)
        return panel

    # --- PANNELLO DESTRO ---
    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        text_group = QGroupBox("Testo 3D")
        text_layout = QVBoxLayout(text_group)
        text_layout.setSpacing(2)
        self.text_entry = QPlainTextEdit()
        self.text_entry.setPlaceholderText("Inserisci testo...")
        self.text_entry.setMaximumHeight(50)
        text_layout.addWidget(self.text_entry)
        fr = QHBoxLayout()
        fr.addWidget(QLabel("<small>Font:</small>"))
        self.font_combo = QComboBox()
        from PyQt5.QtGui import QFontDatabase
        for f in QFontDatabase().families():
            self.font_combo.addItem(f)
        self.font_combo.setCurrentText("Arial")
        fr.addWidget(self.font_combo)
        text_layout.addLayout(fr)
        sr = QHBoxLayout()
        sr.addWidget(QLabel("<small>Dim:</small>"))
        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(1, 200)
        self.font_size_spin.setValue(5)
        sr.addWidget(self.font_size_spin)
        sr.addWidget(QLabel("<small>Spess:</small>"))
        self.thickness_spin = QDoubleSpinBox()
        self.thickness_spin.setRange(0.1, 50)
        self.thickness_spin.setValue(1)
        sr.addWidget(self.thickness_spin)
        text_layout.addLayout(sr)
        spr = QHBoxLayout()
        spr.addWidget(QLabel("<small>Spaz:</small>"))
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(-50, 100)
        self.spacing_spin.setValue(0)
        spr.addWidget(self.spacing_spin)
        text_layout.addLayout(spr)
        btn_row = QHBoxLayout()
        btn_row.addWidget(QPushButton(_make_icon("Cr", (100,180,120), 16), "Crea", clicked=self._add_text_mesh))
        btn_row.addWidget(QPushButton(_make_icon("Ad", (180,140,100), 16), "Adatta", clicked=self._adapt_text_to_shape))
        text_layout.addLayout(btn_row)
        text_layout.addWidget(QPushButton(_make_icon("Ba", (160,100,80), 16), "Bassorilievo", clicked=self._bassorilievo))
        layout.addWidget(text_group)

        par_group = QGroupBox("Parametri")
        par_layout = QFormLayout(par_group)
        self.par_x = QDoubleSpinBox(); self.par_x.setRange(-999, 999); self.par_x.valueChanged.connect(lambda v: self._apply_param("pos_x", v))
        self.par_y = QDoubleSpinBox(); self.par_y.setRange(-999, 999); self.par_y.valueChanged.connect(lambda v: self._apply_param("pos_y", v))
        self.par_z = QDoubleSpinBox(); self.par_z.setRange(-999, 999); self.par_z.valueChanged.connect(lambda v: self._apply_param("pos_z", v))
        self.par_rx = QDoubleSpinBox(); self.par_rx.setRange(-360, 360); self.par_rx.valueChanged.connect(lambda v: self._apply_param("rot_x", v))
        self.par_ry = QDoubleSpinBox(); self.par_ry.setRange(-360, 360); self.par_ry.valueChanged.connect(lambda v: self._apply_param("rot_y", v))
        self.par_rz = QDoubleSpinBox(); self.par_rz.setRange(-360, 360); self.par_rz.valueChanged.connect(lambda v: self._apply_param("rot_z", v))
        par_layout.addRow("X:", self.par_x); par_layout.addRow("Y:", self.par_y); par_layout.addRow("Z:", self.par_z)
        par_layout.addRow("Rot X:", self.par_rx); par_layout.addRow("Rot Y:", self.par_ry); par_layout.addRow("Rot Z:", self.par_rz)
        for _sp in (self.font_size_spin, self.thickness_spin, self.spacing_spin,
                    self.par_x, self.par_y, self.par_z,
                    self.par_rx, self.par_ry, self.par_rz):
            _sp.setMinimumHeight(28)
        layout.addWidget(par_group)

        an_group = QGroupBox("Analisi")
        an_layout = QVBoxLayout(an_group)
        an_layout.setSpacing(2)
        an_layout.addWidget(QPushButton("Volume", clicked=lambda: self._analyze("volume")))
        an_layout.addWidget(QPushButton("Superficie", clicked=lambda: self._analyze("area")))
        an_layout.addWidget(QPushButton("Centro Massa", clicked=lambda: self._analyze("com")))
        an_layout.addWidget(QPushButton("Bounding Box", clicked=lambda: self._analyze("bbox")))
        an_layout.addWidget(QPushButton("Tenuta Stagna", clicked=lambda: self._analyze("watertight")))
        layout.addWidget(an_group)

        layout.addStretch()
        return panel

    # --- PARAMETRI FORMA ---
    def _apply_param(self, param, value):
        if not self.scene.single_selection:
            return
        obj = self.scene.single_selection
        if param.startswith("pos_"):
            axis = {"pos_x": 0, "pos_y": 1, "pos_z": 2}[param]
            centroid = obj.centroid if hasattr(obj, 'centroid') else obj.vertices.mean(axis=0)
            delta = value - centroid[axis]
            obj.apply_translation([delta if axis==0 else 0, delta if axis==1 else 0, delta if axis==2 else 0])
        elif param.startswith("rot_"):
            axis = {"rot_x": 0, "rot_y": 1, "rot_z": 2}[param]
            prev = obj.metadata.get(param, 0.0)
            delta = value - prev
            if abs(delta) > 0.01:
                direction = [0, 0, 0]
                direction[axis] = 1
                self.scene.rotate_selection(math.radians(delta), direction)
                obj.metadata[param] = value
                obj.metadata.pop("_gl_normals", None)
        self.gl_widget.update()

    # --- ADATTAMENTO TESTO A SUPERFICIE ---
    def _adapt_text_to_shape(self):
        txt_obj = None
        shape_obj = None
        for obj in self.scene.selected_objects:
            if obj.metadata.get("shape_type") == "text":
                txt_obj = obj
            else:
                shape_obj = obj
        if txt_obj is None:
            QMessageBox.information(self, "Info", "Crea prima il testo con 'Crea', poi seleziona sia il testo che la forma")
            return
        if shape_obj is None:
            QMessageBox.warning(self, "Attenzione", "Seleziona anche una forma a cui adattare il testo")
            return
        try:
            import numpy as np
            text_mesh = txt_obj.copy()
            obj = shape_obj
            bounds = obj.bounds
            if bounds is None:
                return
            t_bounds = text_mesh.bounds
            t_size = t_bounds[1] - t_bounds[0]
            face_size = bounds[1] - bounds[0]
            if t_size[0] > 0 and t_size[2] > 0:
                scale = min(face_size[0] / t_size[0], face_size[2] / t_size[2]) * 0.7
                text_mesh.apply_scale([scale, 1.0, scale])
            shape_center = np.mean([bounds[0], bounds[1]], axis=0)
            self.gl_widget.repaint()
            mv = self.gl_widget._modelview_matrix
            if mv is None or not np.all(np.isfinite(mv)):
                QMessageBox.warning(self, "Attenzione", "Nessuna vista camera disponibile. Ruota la vista e riprova.")
                return
            cam_pos = np.linalg.inv(mv)[:3, 3]
            d = shape_center - cam_pos
            nd = np.linalg.norm(d)
            if nd < 1e-8:
                QMessageBox.warning(self, "Attenzione", "Camera troppo vicina alla forma. Allontana la vista.")
                return
            d_dir = d / nd
            locs, _, tris = obj.ray.intersects_location([cam_pos], [d_dir])
            if len(locs) == 0:
                QMessageBox.warning(self, "Attenzione", "Nessuna superficie raggiunta dalla camera. Ruota la vista e riprova.")
                return
            hit_idx = int(np.argmin(np.sum((locs - cam_pos) ** 2, axis=1)))
            anchor = locs[hit_idx]
            fn = obj.face_normals[tris[hit_idx]]
            if np.dot(fn, anchor - shape_center) < 0:
                fn = -fn
            # 1) Centra il testo sull'ancora (superficie esterna)
            text_mesh.vertices = text_mesh.vertices - text_mesh.centroid + anchor
            # 2) Salva offset Y originale di ogni vertice (spessore del testo)
            y_offsets = text_mesh.vertices[:, 1] - anchor[1]
            # 3) Proietta ogni vertice sulla superficie lungo la normale della faccia (non radiale)
            n_verts = len(text_mesh.vertices)
            proj_hits = np.zeros((n_verts, 3))
            proj_ok = np.zeros(n_verts, dtype=bool)
            locs_p_all, ray_idx_p_all, _ = obj.ray.intersects_location(text_mesh.vertices, np.tile(fn, (n_verts, 1)))
            locs_p, ray_idx_p = _ray_first_hits(locs_p_all, ray_idx_p_all, text_mesh.vertices)
            if len(locs_p) > 0:
                proj_hits[ray_idx_p] = locs_p
                proj_ok[ray_idx_p] = True
            rest = np.where(~proj_ok)[0]
            if len(rest) > 0:
                locs_n_all, ray_idx_n_all, _ = obj.ray.intersects_location(text_mesh.vertices[rest], np.tile(-fn, (len(rest), 1)))
                locs_n, ray_idx_n = _ray_first_hits(locs_n_all, ray_idx_n_all, text_mesh.vertices[rest])
                if len(locs_n) > 0:
                    proj_hits[rest[ray_idx_n]] = locs_n
                    proj_ok[rest[ray_idx_n]] = True
            new_verts = text_mesh.vertices.copy()
            if proj_ok.any():
                new_verts[proj_ok] = proj_hits[proj_ok] + fn * y_offsets[proj_ok, np.newaxis]
            text_mesh.vertices = new_verts
            text_mesh.fix_normals()
            text_mesh.merge_vertices()
            if not text_mesh.is_watertight:
                text_mesh = _ensure_volume(text_mesh)
            text_mesh.metadata = txt_obj.metadata.copy()
            text_mesh.metadata["name"] = f"{txt_obj.metadata.get('name', 'Testo')}_adattato"
            self.scene.start_operation()
            if txt_obj in self.scene.objects:
                self.scene.objects.remove(txt_obj)
            self.scene.objects.append(text_mesh)
            self.scene.selected_objects = [shape_obj, text_mesh]
            self.scene._needs_spatial_rebuild = True
            self.scene.end_operation()
            self._refresh_view()
            self.status_bar.showMessage("Testo adattato alla superficie", 3000)
        except Exception as e:
            print(f"Errore adattamento testo: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Errore", f"Adattamento fallito: {str(e)}")

    def _shell(self):
        obj = self.scene.single_selection
        if not obj:
            QMessageBox.warning(self, "Attenzione", "Seleziona un singolo oggetto")
            return
        if self.scene.shell():
            self._refresh_view()
            self.status_bar.showMessage("Guscio applicato", 3000)

    def _bassorilievo(self):
        txt_obj = None
        shape_obj = None
        for obj in self.scene.selected_objects:
            if obj.metadata.get("shape_type") == "text":
                txt_obj = obj
            else:
                shape_obj = obj
        if txt_obj is None:
            QMessageBox.information(self, "Info", "Seleziona un testo e una forma")
            return
        if shape_obj is None:
            QMessageBox.warning(self, "Attenzione", "Seleziona anche una forma")
            return
        try:
            import numpy as np
            text_mesh = txt_obj.copy()
            obj = shape_obj
            bounds = obj.bounds
            if bounds is None:
                return
            t_bounds = text_mesh.bounds
            t_size = t_bounds[1] - t_bounds[0]
            face_size = bounds[1] - bounds[0]
            if t_size[0] > 0 and t_size[2] > 0:
                scale = min(face_size[0] / t_size[0], face_size[2] / t_size[2]) * 0.7
                text_mesh.apply_scale([scale, 1.0, scale])
            shape_center = np.mean([bounds[0], bounds[1]], axis=0)
            d = np.array([0, 0, 1])
            locs, _, tris = obj.ray.intersects_location([shape_center], [d])
            if len(locs) == 0:
                d = np.array([0, 0, -1])
                locs, _, tris = obj.ray.intersects_location([shape_center], [d])
            if len(locs) == 0:
                QMessageBox.warning(self, "Attenzione", "Nessuna superficie raggiunta dall'alto/basso")
                return
            hit = locs[0]
            fn = obj.face_normals[tris[0]]
            if np.dot(fn, d) < 0:
                fn = -fn
            normal_testo = np.array([0, 1, 0])
            zs_pre = text_mesh.vertices[:, 2]
            top_pre = text_mesh.vertices[np.abs(zs_pre - zs_pre.max()) < 1e-9].mean(axis=0)
            axis_r = np.cross(normal_testo, fn)
            if np.linalg.norm(axis_r) > 1e-8:
                axis_r = axis_r / np.linalg.norm(axis_r)
                angle_r = math.acos(max(-1, min(1, np.dot(normal_testo, fn))))
                R = trimesh.transformations.rotation_matrix(angle_r, axis_r, point=text_mesh.centroid)
                text_mesh.apply_transform(R)
            else:
                if np.dot(normal_testo, fn) < 0:
                    R = trimesh.transformations.rotation_matrix(math.pi, [0, 1, 0], point=text_mesh.centroid)
                    text_mesh.apply_transform(R)
            top_after = R[:3, :3] @ (top_pre - text_mesh.centroid) + text_mesh.centroid
            if np.dot(top_after - text_mesh.centroid, fn) < 0:
                R = trimesh.transformations.rotation_matrix(math.pi, fn, point=text_mesh.centroid)
                text_mesh.apply_transform(R)
            ext = text_mesh.bounds[1] - text_mesh.bounds[0]
            spessore = abs(float(np.dot(ext, fn)))
            top_off = float(np.max(np.dot(text_mesh.vertices - text_mesh.centroid, fn)))
            text_mesh.vertices = text_mesh.vertices - text_mesh.centroid + hit - fn * (top_off + 0.01)
            closest, _, tri_idx = obj.nearest.on_surface(text_mesh.vertices)
            norms = obj.face_normals[tri_idx]
            delta = text_mesh.vertices - closest
            signed = np.einsum('ij,ij->i', delta, norms)
            text_mesh.vertices = closest + norms * signed[:, None]
            text_mesh.fix_normals()
            text_mesh.merge_vertices()
            if not text_mesh.is_watertight:
                text_mesh = _ensure_volume(text_mesh)
            result = boolean_safe([obj, text_mesh], "sottrazione")
            if result is None or result.is_empty:
                raise RuntimeError("Risultato booleana vuoto")
            result.merge_vertices()
            result.metadata = obj.metadata.copy()
            result.metadata.pop("_gl_verts", None)
            result.metadata.pop("_gl_normals", None)
            result.metadata["name"] = f"{obj.metadata.get('name', 'Object')}_inciso"
            self.scene.start_operation()
            for o in [obj, txt_obj]:
                if o in self.scene.objects:
                    self.scene.objects.remove(o)
            self.scene.objects.append(result)
            self.scene.selected_objects = [result]
            self.scene._needs_spatial_rebuild = True
            self.scene.end_operation()
            self._refresh_view()
            self.status_bar.showMessage(f"Bassorilievo applicato: testo inciso (profondita ~ {spessore:.2f} mm)", 3000)
        except Exception as e:
            print(f"Errore bassorilievo: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Errore", f"Bassorilievo fallito: {str(e)}")

    def _normalize_polygon(self, poly, target_max=30.0):
        from shapely import affinity
        bounds = poly.bounds
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        current_max = max(w, h)
        if current_max > target_max:
            sf = target_max / current_max
            cx = (bounds[0] + bounds[2]) * 0.5
            cy = (bounds[1] + bounds[3]) * 0.5
            poly = affinity.scale(poly, xfact=sf, yfact=sf, origin=(cx, cy))
            bounds = poly.bounds
        cx = (bounds[0] + bounds[2]) * 0.5
        cy = (bounds[1] + bounds[3]) * 0.5
        if abs(cx) > 0.01 or abs(cy) > 0.01:
            poly = affinity.translate(poly, -cx, -cy)
        return poly

    def _import_vector_to_3d(self, path: str) -> trimesh.Trimesh:
        path2d = trimesh.load_path(path)
        if hasattr(path2d, 'polygons_full') and path2d.polygons_full:
            meshes = [trimesh.creation.extrude_polygon(self._normalize_polygon(poly), height=5) for poly in path2d.polygons_full]
            if len(meshes) == 1:
                return meshes[0]
            merged = trimesh.util.concatenate(meshes)
            merged.remove_unreferenced_vertices()
            return merged
        if hasattr(path2d, 'entities') and len(path2d.entities) > 0:
            lines = []
            for e in path2d.entities:
                pts = path2d.vertices[e.points]
                lines.append(pts)
            if lines:
                all_pts = np.vstack(lines)
                from shapely.geometry import MultiPoint
                hull = MultiPoint(all_pts[:, :2]).convex_hull
                if not hull.is_empty:
                    hull = self._normalize_polygon(hull)
                    return trimesh.creation.extrude_polygon(hull, height=5)
        mesh = trimesh.load(path, force='mesh')
        if isinstance(mesh, trimesh.Scene):
            mesh = mesh.dump(concatenate=True)
        return mesh

    def _simplify_contour(self, contour, max_pts=400):
        step = max(1, len(contour) // max_pts)
        return contour[::step]

    def _import_image_to_3d(self, path: str) -> trimesh.Trimesh:
        from PIL import Image
        img = Image.open(path).convert('L')
        arr = np.array(img)
        from skimage.measure import find_contours
        from shapely.geometry import Polygon
        binary_level = arr.max() * 0.4
        binary = (arr > binary_level).astype(np.uint8) * 255
        contours = find_contours(binary, level=127)
        if not contours:
            from scipy.ndimage import sobel
            edges_x = sobel(arr, axis=1)
            edges_y = sobel(arr, axis=0)
            edges = np.hypot(edges_x, edges_y)
            pts = np.column_stack(np.where(edges > edges.max() * 0.3))
            if len(pts) < 10:
                raise ValueError("Pochi contorni rilevati")
            from shapely.geometry import MultiPoint
            hull = MultiPoint([(float(p[1]), float(-p[0])) for p in pts]).convex_hull
            if hull.is_empty:
                raise ValueError("Contorno vuoto")
            return trimesh.creation.extrude_polygon(self._normalize_polygon(hull), height=5)
        raw_polys = []
        for c in contours:
            c = self._simplify_contour(c)
            c_xy = np.column_stack([c[:, 1], -c[:, 0]])
            if len(c_xy) >= 4:
                try:
                    p = Polygon(c_xy)
                    if p.is_valid and p.area > 10:
                        raw_polys.append(p)
                except Exception:
                    continue
        if not raw_polys:
            raise ValueError("Nessun poligono valido dai contorni")
        if len(raw_polys) <= 2:
            polys = [self._normalize_polygon(p) for p in raw_polys]
            if len(polys) == 1:
                return trimesh.creation.extrude_polygon(polys[0], height=5)
            meshes = [trimesh.creation.extrude_polygon(p, height=5) for p in polys]
            merged = trimesh.util.concatenate(meshes)
            merged.remove_unreferenced_vertices()
            return merged
        raw_polys.sort(key=lambda p: p.area, reverse=True)
        exterior = raw_polys[0]
        min_hole_area = max(1000, exterior.area * 0.01)
        holes = []
        separate = []
        for p in raw_polys[1:]:
            if p.area < min_hole_area:
                break
            if exterior.contains(p):
                holes.append(p)
            else:
                separate.append(p)
        if holes:
            from shapely.ops import unary_union
            try:
                holes_union = unary_union(holes)
                combined = exterior.difference(holes_union)
                if not combined.is_empty and combined.is_valid:
                    combined = self._normalize_polygon(combined)
                    to_extrude = [combined] + [self._normalize_polygon(p) for p in separate]
                    meshes = [trimesh.creation.extrude_polygon(p, height=5) for p in to_extrude]
                    merged = trimesh.util.concatenate(meshes)
                    merged.remove_unreferenced_vertices()
                    return merged
            except Exception as e:
                # Fallback intenzionale: se la booleana con fori fallisce, si prosegue
                # con l'estrusione semplice (senza fori) senza interrompere l'import.
                print(f"[TriviumCAD] _import_vector_to_3d (fallback senza fori): {e}")
        polys = [self._normalize_polygon(p) for p in [exterior] + separate]
        meshes = [trimesh.creation.extrude_polygon(p, height=5) for p in polys]
        merged = trimesh.util.concatenate(meshes)
        merged.remove_unreferenced_vertices()
        return merged

    def _import_2d_to_3d(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importa 2D in 3D", "",
            "Tutti i formati (*.svg *.dxf *.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp);;"
            "SVG (*.svg);;DXF (*.dxf);;Immagini (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp)"
        )
        if not path:
            return
        ext = Path(path).suffix.lower()
        try:
            if ext in (".svg", ".dxf"):
                mesh = self._import_vector_to_3d(path)
            else:
                mesh = self._import_image_to_3d(path)
            if mesh and len(mesh.vertices) > 0:
                mesh = validate_and_place_mesh(mesh)
                mesh.metadata.update({
                    "layer": self.scene.active_layer,
                    "color": NEUTRAL_COLORS[self.scene.color_idx % len(NEUTRAL_COLORS)],
                    "name": Path(path).stem,
                    "shape_type": "imported_2d",
                    "params": {},
                    "assembly": None
                })
                self.scene.color_idx += 1
                self.scene.objects.append(mesh)
                self._refresh_view()
                self.status_bar.showMessage(f"Importato: {Path(path).name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Importazione 2D fallita: {str(e)}")

    # --- ANALISI MESH ---
    def _analyze(self, mode: str):
        obj = self.scene.single_selection
        if not obj:
            QMessageBox.warning(self, "Attenzione", "Seleziona un singolo oggetto")
            return
        if mode == "volume":
            v = obj.volume if hasattr(obj, 'volume') else 0
            QMessageBox.information(self, "Volume", f"Volume: {v:.2f}")
        elif mode == "area":
            a = obj.area if hasattr(obj, 'area') else 0
            QMessageBox.information(self, "Superficie", f"Area: {a:.2f}")
        elif mode == "com":
            c = obj.center_mass if hasattr(obj, 'center_mass') else np.mean(obj.vertices, axis=0)
            QMessageBox.information(self, "Centro Massa", f"({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})")
        elif mode == "bbox":
            b = obj.bounds
            if b is not None:
                dims = b[1] - b[0]
                QMessageBox.information(self, "Bounding Box", f"({dims[0]:.2f}, {dims[1]:.2f}, {dims[2]:.2f})")
        elif mode == "watertight":
            wt = hasattr(obj, 'is_watertight') and obj.is_watertight
            QMessageBox.information(self, "Tenuta Stagna", "✅ Watertight" if wt else "❌ Non watertight")
    
    # --- CREAZIONE FORME (UI) ---
    def _add_shape(self, shape_type: str, params: Dict[str, Any]):
        mesh = self.scene.add_shape(shape_type, params)
        print(f"[TriviumCAD] Creata forma: {mesh.metadata.get('name', shape_type)}")
        self.gl_widget.update()
        self.update_ui()
    
    # --- BOOLEANE (UI) ---
    def _run_boolean(self, operation):
        if len(self.scene.selected_objects) < 2:
            print("[TriviumCAD] Booleana: servono almeno 2 oggetti selezionati")
            QMessageBox.warning(self, "Attenzione", "Servono almeno 2 oggetti selezionati")
            return
        meshes = self.scene.selected_objects[:]
        self.scene.start_operation()
        try:
            result = boolean_safe(meshes, operation)
            if result is None or result.is_empty:
                print(f"[TriviumCAD] Booleana {operation}: risultato vuoto")
                QMessageBox.warning(self, "Errore", "Risultato vuoto")
                self.scene.end_operation()
                return
            result.update_faces(result.nondegenerate_faces(height=1e-4))
            result.remove_unreferenced_vertices()
            result.fix_normals()
            # Copia selettiva: solo campi essenziali, reset flag critici
            result.metadata["name"] = f"{meshes[0].metadata.get('name', 'Object')}_{operation}"
            result.metadata["color"] = meshes[0].metadata.get("color", [0.7, 0.7, 0.7, 1.0])
            result.metadata["layer"] = meshes[0].metadata.get("layer", "Default")
            result.metadata["locked"] = False
            result.metadata["visible"] = True
            result.metadata["shape_type"] = "boolean"
            result.metadata["params"] = {}
            result.metadata.pop("assembly", None)
            for key in ["_gl_verts", "_gl_normals", "_gl_vbo_verts", "_gl_vbo_normals"]:
                result.metadata.pop(key, None)
            for obj in meshes:
                if obj in self.scene.objects:
                    self.scene.objects.remove(obj)
            self.scene.objects.append(result)
            self.scene.selected_objects = [result]
            self.scene._needs_spatial_rebuild = True
            print(f"[TriviumCAD] Booleana {operation}: {result.metadata['name']}")
            self.scene.end_operation()
            self.gl_widget._invalidate_all_vbos()
            self._refresh_outliner()
            self._refresh_view()
            self.status_bar.showMessage(f"Operazione {operation} completata", 3000)
        except Exception as e:
            self.scene.cancel_operation()
            print(f"[TriviumCAD] Booleana {operation}: {e}")
            QMessageBox.warning(self, "Errore", f"Operazione booleana fallita:\n{e}")
    
    # --- CAM (UI) ---
    def _run_toolpath(self):
        if not self.scene.selected_objects:
            QMessageBox.warning(self, "Attenzione", "Seleziona un oggetto")
            return
        mesh = self.scene.selected_objects[0]
        td = self.scene.tool_diameter
        so = self.scene.stepover
        fr = self.scene.feed_rate
        def worker():
            return _compute_adaptive_path(mesh, td, so, 5.0, fr)
        def callback(gcode_paths):
            if gcode_paths:
                self.scene.gcode_paths = gcode_paths
                n_paths = len(gcode_paths)
                n_pts = sum(len(p.get("pts", [])) for p in gcode_paths)
                print(f"[TriviumCAD] CAM: {n_pts} punti percorso generati")
                self._refresh_view()
                self.status_bar.showMessage("Percorso CAM generato", 3000)
            else:
                print(f"[TriviumCAD] CAM: errore generazione")
                self.status_bar.showMessage("Errore generazione percorso CAM", 3000)
        self._run_blocking("Generazione percorso CAM", worker, callback)
    
    # --- FILETTO/THREAD (UI) ---
    def _run_fillet(self):
        if not self.scene.selected_objects:
            QMessageBox.warning(self, "Attenzione", "Seleziona uno o piu oggetti")
            return
        radius = self.fillet_radius_spin.value()
        if self.scene.fillet_selected(radius):
            self.gl_widget._invalidate_all_vbos()
            self._refresh_view()
            self.status_bar.showMessage(f"Arrotondamento applicato (raggio: {radius})", 3000)
        else:
            print(f"[TriviumCAD] Arrotondamento: errore")
            QMessageBox.warning(self, "Errore", "Arrotondamento fallito: nessuno spigolo vivo rilevato")
            self.status_bar.showMessage("Errore arrotondamento", 3000)
    
    # --- MESH OPERATIONS (UI) ---
    def _cad_require_selection(self):
        if not self.scene.has_selection:
            self.status_bar.showMessage("Nessun oggetto selezionato", 3000)
            return False
        return True

    def _cad_post_apply(self, msg):
        self.gl_widget._invalidate_all_vbos()
        self._refresh_view()
        self.status_bar.showMessage(msg, 3000)

    def _cad_chamfer(self):
        if not self._cad_require_selection():
            return
        distance, ok = QInputDialog.getDouble(self, "Chamfer", "Distanza cimatura (mm):", 1.0, 0.1, 100.0, 2)
        if not ok:
            return
        if self.scene.chamfer(distance):
            self._cad_post_apply(f"Chamfer applicato (distanza {distance} mm)")
        else:
            self.status_bar.showMessage("Chamfer non applicato", 3000)

    def _cad_pattern_linear(self):
        if not self._cad_require_selection():
            return
        count, ok = QInputDialog.getInt(self, "Pattern lineare", "Numero di elementi:", 3, 2, 100)
        if not ok:
            return
        distance, ok2 = QInputDialog.getDouble(self, "Pattern lineare", "Distanza tra elementi (mm):", 10.0, 0.1, 1000.0, 2)
        if not ok2:
            return
        direction, ok3 = QInputDialog.getItem(self, "Pattern lineare", "Direzione:", ["x", "y", "z"], 0, False)
        if not ok3:
            return
        if self.scene.linear_pattern(count, distance, direction):
            self._cad_post_apply(f"Pattern lineare creato ({count} elementi)")
        else:
            self.status_bar.showMessage("Pattern lineare non creato", 3000)

    def _cad_pattern_circular(self):
        if not self._cad_require_selection():
            return
        count, ok = QInputDialog.getInt(self, "Pattern circolare", "Numero di elementi:", 3, 2, 100)
        if not ok:
            return
        radius, ok2 = QInputDialog.getDouble(self, "Pattern circolare", "Raggio (mm):", 10.0, 0.1, 1000.0, 2)
        if not ok2:
            return
        axis, ok3 = QInputDialog.getItem(self, "Pattern circolare", "Asse:", ["z", "x", "y"], 0, False)
        if not ok3:
            return
        if self.scene.circular_pattern(count, radius, axis):
            self._cad_post_apply(f"Pattern circolare creato ({count} elementi)")
        else:
            self.status_bar.showMessage("Pattern circolare non creato", 3000)

    def _cad_mirror(self, axis):
        if not self._cad_require_selection():
            return
        if self.scene.mirror(axis):
            self._cad_post_apply(f"Simmetria creata rispetto all'asse {axis.upper()}")
        else:
            self.status_bar.showMessage("Simmetria non creata", 3000)

    def _cad_smooth(self):
        if not self._cad_require_selection():
            return
        iterations, ok = QInputDialog.getInt(self, "Smooth", "Iterazioni:", 1, 1, 20)
        if not ok:
            return
        if self.scene.smooth(iterations):
            self._cad_post_apply(f"Smoothing applicato ({iterations} iterazioni)")
        else:
            self.status_bar.showMessage("Smoothing non applicato", 3000)

    def _cad_subdivide(self):
        if not self._cad_require_selection():
            return
        iterations, ok = QInputDialog.getInt(self, "Subdivide", "Iterazioni:", 1, 1, 5)
        if not ok:
            return
        if self.scene.subdivide(iterations):
            self._cad_post_apply(f"Suddivisione applicata ({iterations} iterazioni)")
        else:
            self.status_bar.showMessage("Suddivisione non applicata", 3000)

    def _cad_decimate(self):
        if not self._cad_require_selection():
            return
        target_faces, ok = QInputDialog.getInt(self, "Decimate", "Numero di facce target:", 1000, 4, 100000)
        if not ok:
            return
        if self.scene.decimate(target_faces):
            self._cad_post_apply(f"Decimazione applicata (target: {target_faces} facce)")
        else:
            self.status_bar.showMessage("Decimazione non applicata", 3000)

    def _cad_repair(self):
        if not self._cad_require_selection():
            return
        self.scene.start_operation()
        try:
            msgs = []
            for obj in self.scene.selected_objects:
                before_v = len(obj.vertices)
                before_w = bool(obj.is_watertight) if hasattr(obj, "is_watertight") else False
                name = obj.metadata.get("name", "Oggetto")
                if before_w:
                    msgs.append(f"{name}: gia' watertight ({before_v} vertici)")
                    continue
                try:
                    trimesh.repair.fill_holes(obj)
                    trimesh.repair.fix_winding(obj)
                    trimesh.repair.fix_normals(obj)
                except Exception as e:
                    self.status_bar.showMessage(f"Riparazione fallita: {e}", 3000)
                    continue
                after_v = len(obj.vertices)
                after_w = bool(obj.is_watertight) if hasattr(obj, "is_watertight") else False
                obj.metadata.pop("_gl_verts", None)
                obj.metadata.pop("_gl_normals", None)
                msgs.append(f"{name}: {before_v}->{after_v} vertici, watertight: {before_w}->{after_w}")
            self.scene._needs_spatial_rebuild = True
            self.scene.end_operation()
            self.gl_widget._invalidate_all_vbos()
            self._refresh_view()
            if not msgs:
                self.status_bar.showMessage("Nessun oggetto riparato", 3000)
            else:
                msg = "; ".join(msgs)
                print(f"[TriviumCAD] Ripara: {msg}")
                self.status_bar.showMessage(f"Ripara: {msg}", 6000)
        except Exception as e:
            self.scene.cancel_operation()
            self.status_bar.showMessage(f"Errore riparazione: {e}", 3000)
    
    def _run_threading(self):
        if not self.scene.single_selection:
            QMessageBox.warning(self, "Attenzione", "Seleziona un singolo oggetto cilindrico")
            return
        obj = self.scene.single_selection
        thr_type = self.thread_type.currentText()
        mode = self.thread_mode.currentText()
        pitch = self.thread_pitch.value()
        profile = self.thread_profile.currentText()
        bounds = obj.bounds
        if bounds is None:
            return
        if mode == "Metrico":
            pitch = max(0.5, pitch)
        elif mode in ("UNF", "UNC"):
            pitch = 25.4 / max(16, int(25.4 / pitch))
        elif mode == "Gas":
            pitch = max(0.5, pitch)
        turns = max(2, int((bounds[1][2] - bounds[0][2]) / pitch))
        if profile == "Filo": h_thread = 0.6134 * pitch
        elif profile == "Trapezio": h_thread = 0.5 * pitch
        else: h_thread = 0.4 * pitch

        if thr_type == "Esterna":
            try:
                thread_mesh = _compute_thread_mesh(obj, thr_type, pitch, turns, profile, depth=self.thread_depth.value())
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[TriviumCAD] Filettatura: eccezione {e}")
                self.status_bar.showMessage("Filettatura fallita", 3000)
                return
            if thread_mesh is None or len(thread_mesh.vertices) < 3:
                print(f"[TriviumCAD] Filettatura {thr_type}: fallita")
                self.status_bar.showMessage("Filettatura fallita", 3000)
                return
            self.scene.start_operation()
            idx = self.scene.objects.index(obj)
            self.scene.objects[idx] = thread_mesh
            self.scene.selected_objects = [thread_mesh]
            self.scene._needs_spatial_rebuild = True
            self.scene.end_operation()
            print(f"[TriviumCAD] Filettatura {thr_type} ({mode}, passo {pitch}) incisa sull'oggetto")
            self._refresh_view()
            self.status_bar.showMessage(f"Filettatura {thr_type} incisa ({mode})", 3000)
        else:
            try:
                sub_vol = _compute_subtraction_volume(obj, pitch, turns, profile, h_thread)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[TriviumCAD] Filettatura interna: eccezione {e}")
                self.status_bar.showMessage("Filettatura interna fallita", 3000)
                return
            if sub_vol is None or len(sub_vol.vertices) < 3:
                print(f"[TriviumCAD] Filettatura interna: volume sottrazione vuoto")
                self.status_bar.showMessage("Filettatura interna fallita", 3000)
                return
            try:
                result_mesh = boolean_safe([obj, sub_vol], "difference")
            except Exception as e:
                print(f"[TriviumCAD] Filettatura interna: booleana fallita ({e})")
                self.status_bar.showMessage("Filettatura interna: booleana fallita", 3000)
                return
            if result_mesh is None or len(result_mesh.vertices) < 3:
                print(f"[TriviumCAD] Filettatura interna: risultato booleana vuoto")
                self.status_bar.showMessage("Filettatura interna fallita", 3000)
                return
            self.scene.start_operation()
            idx = self.scene.objects.index(obj)
            self.scene.objects[idx] = result_mesh
            self.scene.selected_objects = [result_mesh]
            self.scene._needs_spatial_rebuild = True
            self.scene.end_operation()
            print(f"[TriviumCAD] Filettatura interna ({mode}, passo {pitch}) incisa")
            self._refresh_view()
            self.status_bar.showMessage(f"Filettatura interna incisa ({mode})", 3000)
    
    def _generate_toolpath(self):
        self._run_toolpath()
    
    # --- FILE OPERATIONS ---
    def _new(self):
        self.scene = Scene()
        self.scene._callback_notify = self._show_notify
        self.gl_widget.scene = self.scene
        self.gl_widget.update()
        self.update_ui()
        print("[TriviumCAD] Nuova scena creata")
        self.statusBar().showMessage("Nuova scena creata")
    
    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Apri", "", "File 3D (*.stl *.obj *.ply *.3mf);;Scena TriviumCAD (*.n47)"
        )
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext == ".n47":
            self._load_n47(path)
            return
        try:
            mesh = trimesh.load(path, force='mesh')
            if isinstance(mesh, trimesh.Scene):
                mesh = mesh.dump(concatenate=True)
            
            if hasattr(mesh, 'extents') and np.any(np.array(mesh.extents) < 1):
                mesh.apply_scale(1000.0)
            
            mesh = validate_and_place_mesh(mesh)
            mesh.metadata.update({
                "layer": "Default",
                "color": NEUTRAL_COLORS[0],
                "name": Path(path).stem,
                "shape_type": "imported",
                "params": {},
                "assembly": None
            })
            
            self.scene.objects.append(mesh)
            print(f"[TriviumCAD] Importato: {Path(path).name}")
            self.gl_widget.update()
            self.update_ui()
            self.statusBar().showMessage(f"File aperto: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile aprire il file: {str(e)}")
    
    def _load_n47(self, path):
        try:
            import zipfile, io
            with zipfile.ZipFile(path, 'r') as zf:
                names = zf.namelist()
                if "version.txt" not in names:
                    raise ValueError("File .n47 non valido: manca version.txt")
                if "scene.json" not in names:
                    raise ValueError("File .n47 non valido: manca scene.json")
                version = zf.read("version.txt").decode().strip()
                if version != "1.0":
                    print(f"AVVISO: versione .n47 sconosciuta: {version}")
                scene_state = json.loads(zf.read("scene.json"))
                if not isinstance(scene_state, dict):
                    raise ValueError("scene.json non è un dizionario valido")
                self.scene.color_idx = scene_state.get("color_idx", 0)
                self.scene.active_layer = scene_state.get("active_layer", "Default")
                self.scene.snap_grid = scene_state.get("snap_grid", True)
                self.scene.magnetic_snap = scene_state.get("magnetic_snap", True)
                self.scene.scale_mode = scene_state.get("scale_mode", "Disattivato")
                self.scene.layers = scene_state.get("layers", {"Default": {"visible": True, "locked": False, "color": [0.6, 0.75, 0.9, 1.0]}})
                self.scene.objects = []
                self.scene.selected_objects = []
                self.scene.undo_stack = []
                self.scene.redo_stack = []
                mesh_names = sorted([n for n in names if n.startswith("mesh_") and n.endswith(".npz")])
                for name in mesh_names:
                    idx = name.split("_")[1].split(".")[0]
                    meta_name = f"mesh_{idx}_meta.json"
                    if meta_name not in names:
                        print(f"AVVISO: mesh_{idx} senza metadata, salto")
                        continue
                    data = np.load(io.BytesIO(zf.read(name)))
                    if "vertices" not in data or "faces" not in data:
                        print(f"AVVISO: mesh_{idx} dati mancanti, salto")
                        continue
                    meta = json.loads(zf.read(meta_name))
                    if not isinstance(meta, dict):
                        meta = {}
                    mesh = trimesh.Trimesh(vertices=data["vertices"], faces=data["faces"], metadata=meta, process=False)
                    self.scene.objects.append(mesh)
            self.gl_widget.update()
            self.update_ui()
            self.statusBar().showMessage(f"Scena caricata: {Path(path).name} ({len(self.scene.objects)} oggetti)", 3000)
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Errore", f"Caricamento scena fallito: {str(e)}")
    
    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva", "", "File TriviumCAD (*.n47)"
        )
        if not path:
            return
        try:
            import zipfile, io, tempfile, os
            from pathlib import Path
            scene_state = {
                "color_idx": self.scene.color_idx,
                "active_layer": self.scene.active_layer,
                "snap_grid": self.scene.snap_grid,
                "magnetic_snap": self.scene.magnetic_snap,
                "scale_mode": self.scene.scale_mode,
                "layers": self.scene.layers,
            }
            obj_list = []
            for i, obj in enumerate(self.scene.objects):
                meta = {k: v for k, v in obj.metadata.items() if not k.startswith("_gl_")}
                obj_list.append({
                    "index": i,
                    "vertices": obj.vertices,
                    "faces": obj.faces,
                    "metadata": meta,
                })
            fd, tmp_path = tempfile.mkstemp(suffix=".n47", dir=os.path.dirname(path) or ".")
            os.close(fd)
            try:
                with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("version.txt", "1.0")
                    zf.writestr("scene.json", json.dumps(scene_state, ensure_ascii=False, cls=NumpyEncoder))
                    for o in obj_list:
                        buf = io.BytesIO()
                        np.savez_compressed(buf, vertices=o["vertices"], faces=o["faces"])
                        zf.writestr(f"mesh_{o['index']}.npz", buf.getvalue())
                        zf.writestr(f"mesh_{o['index']}_meta.json", json.dumps(o["metadata"], ensure_ascii=False, cls=NumpyEncoder))
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except Exception:
                    print("ERRORE: impossibile rimuovere tmp_path dopo errore save")
                    pass
                raise
            self.statusBar().showMessage(f"Scena salvata: {Path(path).name} ({len(obj_list)} oggetti)", 3000)
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Errore", f"Salvataggio fallito: {str(e)}")
    
    def _import(self):
        self._open()
    
    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta", "", "File STL (*.stl);;File OBJ (*.obj);;File PLY (*.ply);;File 3MF (*.3mf);;File GLB (*.glb)"
        )
        if path:
            try:
                ext = Path(path).suffix.lower().lstrip(".")
                visible_objects = [
                    obj for obj in self.scene.objects 
                    if self.scene.layers.get(obj.metadata.get("layer", "Default"), {}).get("visible", True)
                ]
                
                if not visible_objects:
                    QMessageBox.warning(self, "Esportazione", "Nessun oggetto visibile da esportare")
                    return
                
                scene = trimesh.Scene(visible_objects)
                scene.export(path, file_type=ext)
                self.statusBar().showMessage(f"Esportato in: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Impossibile esportare: {str(e)}")
    
    def _show_printer_dialog(self):
        dlg = PrinterConnectDialog(self)
        dlg.exec_()
    
    # --- SNAP/GRID ---
    def _toggle_snap(self, checked=None):
        if isinstance(checked, bool):
            self.scene.snap_grid = checked
        else:
            self.scene.snap_grid = not self.scene.snap_grid
        self.status_bar.showMessage(f"Snap griglia: {'ON' if self.scene.snap_grid else 'OFF'}", 2000)

    def _toggle_magnetic(self, checked=None):
        if isinstance(checked, bool):
            self.scene.magnetic_snap = checked
        else:
            self.scene.magnetic_snap = not self.scene.magnetic_snap
        self.status_bar.showMessage(f"Magneti: {'ON' if self.scene.magnetic_snap else 'OFF'}", 2000)

    def _set_grid_scale(self):
        modes = ["Disattivato", "0.5 mm", "1 mm", "2 mm", "5 mm", "10 mm"]
        current = self.scene.scale_mode
        idx = modes.index(current) if current in modes else 0
        val, ok = QInputDialog.getItem(self, "Scala Griglia", "Modalita:", modes, idx, False)
        if ok:
            self.scene.scale_mode = val
            self.status_bar.showMessage(f"Scala griglia: {val}", 2000)

    def _toggle_console(self, checked):
        try:
            if checked:
                self.console_dialog = ConsoleDialog(self.scene, self.gl_widget, self)
                self.console_dialog.finished.connect(self._console_closed)
                self.console_dialog.show()
            else:
                if self.console_dialog is not None:
                    self.console_dialog.close()
                    self.console_dialog = None
        except Exception as e:
            QMessageBox.warning(self, "Console", f"Impossibile aprire la console:\n{e}")
            self._console_act.blockSignals(True)
            self._console_act.setChecked(False)
            self._console_act.blockSignals(False)

    def _console_closed(self):
        self._console_act.blockSignals(True)
        self._console_act.setChecked(False)
        self._console_act.blockSignals(False)
        self.console_dialog = None

    # --- INFO/HELP ---
    def _show_tutorial(self):
        TutorialDialog(self).exec_()

    def _show_about(self):
        QMessageBox.about(self, "Informazioni",
            f"<h2>{APP_NAME} v{VERSION}</h2><p>Applicazione CAD/CAM 3D.<br>Copyright (c) 2026 N47Lab Team</p>")

    def _apply_threading(self):
        self._run_threading()

    def _slice_selection(self):
        if not self.scene.has_selection:
            QMessageBox.warning(self, "Attenzione", "Seleziona uno o piu oggetti da affettare")
            return
        axis = self.slice_axis.currentText().lower()
        offset = self.slice_pos.value()
        pieces = self.slice_count.value()
        if self.scene.slice_objects(axis, offset, pieces):
            self._refresh_view()
            self.status_bar.showMessage(f"Affettatura completata: {pieces} pezzi", 3000)
        else:
            QMessageBox.warning(self, "Errore", "Impossibile affettare gli oggetti selezionati")

    def _apply_fillet(self):
        self._run_fillet()

    def _refresh_view(self):
        self.gl_widget.update()
        self.update_ui()

    # --- TESTO (UI) ---
    def _add_text_mesh(self):
        text = self.text_entry.toPlainText()
        if not text:
            return
        font_name = self.font_combo.currentText()
        font_size = self.font_size_spin.value()
        thickness = self.thickness_spin.value()
        spacing = self.spacing_spin.value()
        mesh = _generate_text_mesh(text, font_name, font_size, thickness, spacing)
        if mesh and len(mesh.vertices) > 0:
            import trimesh.transformations as tf
            R = tf.rotation_matrix(math.radians(90), [1, 0, 0])
            mesh.apply_transform(R)
            mesh.fix_normals()
            mesh.apply_translation(-mesh.centroid)
            mesh.metadata.update({
                "layer": self.scene.active_layer,
                "color": NEUTRAL_COLORS[self.scene.color_idx % len(NEUTRAL_COLORS)],
                "name": f"Testo_{text[:10]}",
                "shape_type": "text",
                "params": {},
                "assembly": None
            })
            self.scene.color_idx += 1
            self.scene._undo_push()
            self.scene.objects.append(mesh)
            self.scene._needs_spatial_rebuild = True
            self._refresh_view()

    # --- UI REFRESH ---
    def update_ui(self):
        if hasattr(self, 'right_panel') and self.right_panel is not None:
            if hasattr(self.right_panel, 'update_ui'):
                self.right_panel.update_ui(self.scene.selected_objects)
        if hasattr(self, 'outliner_list'):
            self._sync_outliner_selection()
    
    # --- OUTLINER ---
    def _setup_outliner(self):
        self.outliner_dock = QDockWidget("Outliner", self)
        self.outliner_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.outliner_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.outliner_dock.setMinimumWidth(30)
        self.outliner_dock.setMaximumWidth(200)
        
        self.outliner_list = QListWidget()
        self.outliner_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.outliner_list.itemSelectionChanged.connect(self._on_outliner_sel_changed)
        self.outliner_list.setAlternatingRowColors(True)
        self.outliner_list.setSpacing(0)
        self.outliner_list.setStyleSheet("QListWidget::item { padding: 0px; }")
        
        self.outliner_dock.setWidget(self.outliner_list)
        self.addDockWidget(Qt.RightDockWidgetArea, self.outliner_dock)
        self._refresh_outliner()
    
    def _refresh_outliner(self):
        if not hasattr(self, 'outliner_list'):
            return
        self.outliner_list.blockSignals(True)
        self.outliner_list.clear()
        sel_set = set(id(o) for o in self.scene.selected_objects)
        for idx, obj in enumerate(self.scene.objects):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, idx)
            w = QWidget()
            layout = QHBoxLayout(w)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            color = obj.metadata.get("color", [0.5, 0.5, 0.5, 1.0])
            pix = QPixmap(14, 14)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor(int(color[0]*255), int(color[1]*255), int(color[2]*255)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, 14, 14)
            p.end()
            color_label = QLabel()
            color_label.setPixmap(pix)
            color_label.setFixedSize(16, 16)
            layout.addWidget(color_label)
            name_label = QLabel(obj.metadata.get("name", "?"))
            name_label.setStyleSheet("color: #0C1E36; font-size: 12px; padding: 1px 2px;")
            layout.addWidget(name_label, 1)
            vis = obj.metadata.get("visible", True)
            vis_btn = QPushButton()
            vis_btn.setIcon(_make_eye_icon(vis, 18))
            vis_btn.setFixedSize(20, 20)
            vis_btn.setStyleSheet("QPushButton { border: none; background: transparent; padding: 0px; margin: 0px; } QPushButton:hover { background: #e0e0e0; border-radius: 2px; }")
            vis_btn.setToolTip("Mostra/Nascondi")
            vis_btn.clicked.connect(lambda checked, o=obj: self._toggle_outliner_vis(o))
            layout.addWidget(vis_btn)
            locked = obj.metadata.get("locked", False)
            lock_btn = QPushButton()
            lock_btn.setIcon(_make_lock_icon(locked, 18))
            lock_btn.setFixedSize(20, 20)
            lock_btn.setStyleSheet("QPushButton { border: none; background: transparent; padding: 0px; margin: 0px; } QPushButton:hover { background: #e0e0e0; border-radius: 2px; }")
            lock_btn.setToolTip("Blocca/Sblocca")
            lock_btn.clicked.connect(lambda checked, o=obj: self._toggle_outliner_lock(o))
            layout.addWidget(lock_btn)
            self.outliner_list.addItem(item)
            self.outliner_list.setItemWidget(item, w)
            if id(obj) in sel_set:
                item.setSelected(True)
        self.outliner_list.blockSignals(False)
    
    def _on_outliner_sel_changed(self):
        new_sel = []
        for i in range(self.outliner_list.count()):
            item = self.outliner_list.item(i)
            if item.isSelected():
                idx = item.data(Qt.UserRole)
                if idx is not None and 0 <= idx < len(self.scene.objects):
                    obj = self.scene.objects[idx]
                    if not obj.metadata.get("locked", False):
                        new_sel.append(obj)
        self.scene.selected_objects = new_sel
        self.scene._needs_spatial_rebuild = True
        self.gl_widget.update()
        self.update_ui()
    
    def _sync_outliner_selection(self):
        if not hasattr(self, 'outliner_list'):
            return
        if self.outliner_list.count() != len(self.scene.objects):
            self._refresh_outliner()
            return
        sel_set = set(id(o) for o in self.scene.selected_objects)
        self.outliner_list.blockSignals(True)
        for i in range(self.outliner_list.count()):
            item = self.outliner_list.item(i)
            if item is None:
                continue
            idx = item.data(Qt.UserRole)
            if idx is not None and 0 <= idx < len(self.scene.objects):
                item.setSelected(id(self.scene.objects[idx]) in sel_set)
        self.outliner_list.blockSignals(False)
    
    def _toggle_outliner_vis(self, obj):
        visible = obj.metadata.get("visible", True)
        obj.metadata["visible"] = not visible
        self.gl_widget.update()
        self._refresh_outliner()
    
    def _toggle_outliner_lock(self, obj):
        locked = obj.metadata.get("locked", False)
        obj.metadata["locked"] = not locked
        self._refresh_outliner()
    
    def _update_stats(self):
        now = time.time()
        elapsed = now - self.last_time
        fps = self.frames / elapsed if elapsed > 0 else 0
        
        cur = self.statusBar().currentMessage()
        if not cur or cur.startswith("FPS:"):
            self.statusBar().showMessage(
                f"FPS: {fps:.1f} | Oggetti: {len(self.scene.objects)} | Selezionati: {len(self.scene.selected_objects)}"
            )
        
        self.frames = 0
        self.last_time = now

# =============================================================================
# BLOCCO 5: SPLASH SCREEN & ENTRY POINT
# =============================================================================
class SplashScreen(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        scr_w = QApplication.primaryScreen().availableGeometry().width()
        self.setFixedSize(min(1280, scr_w), 680)
        self.show()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        margin = 48
        p.setPen(QPen(QColor(200, 200, 210), 6))
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawRoundedRect(margin, margin, w - margin * 2, h - margin * 2, 24, 24)

        text = "TriviumCAD"
        colors = [
            QColor(*[int(c * 255) for c in NEUTRAL_COLORS[i % len(NEUTRAL_COLORS)][:3]])
            for i in range(len(text))
        ]
        font_size = min(120, max(60, int((w - 260) / (len(text) * 0.71))))
        font = QFont("Segoe UI", font_size, QFont.Bold)
        spacing = int(font_size * 0.92)

        cx, cy = w // 2, h // 2 - 20
        stagger_x = [-16, 20, -10, 24, -20, 12]
        stagger_y = [-24, 16, -30, 12, -36, 20]
        rot = [-4, 3, -6, 5, -3, 7]

        for i, ch in enumerate(text):
            p.save()
            p.setFont(font)
            c = colors[i]
            p.setPen(QPen(c.darker(130), 4))
            p.setBrush(c)
            bordo = i < 2 or i >= len(text) - 2
            sx = 0 if bordo else (stagger_x[i] if i < len(stagger_x) else 0)
            sy = 0 if bordo else (stagger_y[i] if i < len(stagger_y) else 0)
            rr = 0 if bordo else (rot[i] if i < len(rot) else 0)
            x = cx + (i - len(text) / 2) * spacing + sx
            y = cy + sy
            p.translate(x, y)
            p.rotate(rr)
            r = QFontMetrics(font).boundingRect(ch)
            p.drawText(-r.width() // 2, -r.height() // 2, r.width(), r.height(), Qt.AlignCenter, ch)
            p.restore()

        font2 = QFont("Segoe UI", 18)
        p.setFont(font2)
        p.setPen(QColor(180, 190, 200))
        p.drawText(QRect(0, h - 50, w, 30), Qt.AlignCenter, "Caricamento in corso...")

        # --- CAD 2D con forme primitive ---
        def _build_arc(cx, cy, r, start_deg, end_deg, segs=16):
            pts = []
            for i in range(segs + 1):
                a = math.radians(start_deg + (end_deg - start_deg) * i / segs)
                pts.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
            return pts

        cad_cx = w // 2
        cad_cy = cy + 145
        letter_w = 56
        letter_h = 72
        gap = 18
        stroke_w = 12
        total_w = letter_w * 3 + gap * 2
        start_x = cad_cx - total_w // 2
        cad_colors = [
            QColor(*[int(c * 255) for c in NEUTRAL_COLORS[0][:3]]),
            QColor(*[int(c * 255) for c in NEUTRAL_COLORS[1][:3]]),
            QColor(*[int(c * 255) for c in NEUTRAL_COLORS[2][:3]]),
        ]
        segs = 18

        for li, (lx, lc) in enumerate(zip(
            [start_x, start_x + letter_w + gap, start_x + (letter_w + gap) * 2],
            cad_colors
        )):
            shadow = lc.darker(160)
            for offset_x, offset_y, fill in [(4, 4, shadow), (0, 0, lc)]:
                path = QPainterPath()
                if li == 0:  # C = arco sinistro (apre a destra)
                    r_outer = letter_h / 2
                    r_inner = r_outer - stroke_w
                    lcy = cad_cy + letter_h / 2
                    outer = _build_arc(lx + r_outer, lcy, r_outer, 315, 45, segs)
                    inner = _build_arc(lx + r_outer, lcy, r_inner, 45, 315, segs)
                    poly = outer + inner
                    path.moveTo(poly[0])
                    for pt in poly[1:]:
                        path.lineTo(pt)
                    path.closeSubpath()
                elif li == 1:  # A = cono + barra
                    top = cad_cy + 4
                    bot = cad_cy + letter_h
                    mx = lx + letter_w / 2
                    lx2 = lx + 2
                    rx = lx + letter_w - 2
                    bar_y = cad_cy + letter_h * 0.55
                    sb2 = stroke_w * 0.6
                    poly = [
                        QPointF(lx2, bot),
                        QPointF(mx, top),
                        QPointF(rx, bot),
                        QPointF(rx - sb2, bot),
                        QPointF(mx + 3, top + stroke_w * 0.5),
                        QPointF(lx2 + sb2, bot),
                    ]
                    path.moveTo(poly[0])
                    for pt in poly[1:]:
                        path.lineTo(pt)
                    path.closeSubpath()
                    bar_path = QPainterPath()
                    bw = stroke_w + 4
                    bar_path.addRect(QRectF(mx - bw // 2, bar_y - stroke_w // 2, bw, stroke_w))
                    path = path.united(bar_path)
                else:  # D = retta verticale + arco destro (specchiato C)
                    r_outer = letter_h / 2
                    r_inner = r_outer - stroke_w
                    lcy = cad_cy + letter_h / 2
                    arc_cx = lx + letter_w - r_outer
                    path.addRect(QRectF(lx + 2, cad_cy + 2, stroke_w, letter_h - 4))
                    outer = _build_arc(arc_cx, lcy, r_outer, 225, 495, segs)
                    inner = _build_arc(arc_cx, lcy, r_inner, 135, -135, segs)
                    arc_path = QPainterPath()
                    poly = outer + inner
                    arc_path.moveTo(poly[0])
                    for pt in poly[1:]:
                        arc_path.lineTo(pt)
                    arc_path.closeSubpath()
                    path.addPath(arc_path)

                path.translate(offset_x, offset_y)
                p.fillPath(path, fill)
                p.setPen(QPen(fill.darker(120), 1))
                p.drawPath(path)

        p.end()

    def mousePressEvent(self, event):
        self.close()

# === MAIN ===
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(f"""
        QMainWindow, QDialog {{
            background-color: {BACKGROUND_COLOR};
            color: {TEXT_COLOR};
        }}
        CADWindow {{
            background-color: {BACKGROUND_COLOR};
        }}
        QGroupBox {{
            font-weight: bold;
            color: {TEXT_COLOR};
            border: 1px solid {BORDER_COLOR};
            border-radius: 4px;
            margin-top: 1ex;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 7px;
            padding: 0 3px 0 3px;
        }}
        QPushButton {{
            background-color: {BUTTON_COLOR};
            color: {TEXT_COLOR};
            border: 1px solid {BORDER_COLOR};
            border-radius: 3px;
            padding: 4px 10px;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: #B8D4EC;
        }}
        QPushButton:pressed {{
            background-color: #8CB4D4;
        }}
        QComboBox, QDoubleSpinBox {{
            background-color: #C4D8EC;
            color: {TEXT_COLOR};
            border: 1px solid {BORDER_COLOR};
            border-radius: 3px;
            padding: 2px 4px;
        }}
        QLabel {{
            color: {TEXT_COLOR};
        }}
        QToolBar {{
            background-color: {BACKGROUND_COLOR};
            border: none;
            spacing: 2px;
        }}
        QMenuBar {{
            background-color: #9CBDDB;
            color: {TEXT_COLOR};
            padding: 4px;
        }}
        QMenuBar::item:selected {{
            background-color: {BUTTON_COLOR};
        }}
        QMenu {{
            background-color: #C4D8EC;
            color: {TEXT_COLOR};
            border: 1px solid {BORDER_COLOR};
        }}
        QMenu::item:selected {{
            background-color: {BUTTON_COLOR};
        }}
        QStatusBar {{
            background-color: #9CBDDB;
            color: {TEXT_COLOR};
            padding: 4px;
        }}
    """)
    
    splash = SplashScreen()
    splash.show()
    app.processEvents()
    
    format = QSurfaceFormat()
    format.setVersion(3, 3)
    format.setProfile(QSurfaceFormat.CompatibilityProfile)
    format.setDepthBufferSize(24)
    format.setStencilBufferSize(8)
    format.setSamples(4)
    format.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(format)
    
    import time
    time.sleep(0.5)
    app.processEvents()
    
    window = CADWindow()
    splash.close()
    window.show()
    
    # Mostra tutorial all'avvio (se non nascosto)
    settings = QSettings("TriviumCAD", "TriviumCAD")
    if not settings.value("tutorial/hide_on_startup", False, type=bool):
        window._show_tutorial()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()