"""TriviumCAD core - costanti globali (estratte da triviumcad.py, v1.2.0)."""
from typing import List, Dict, Any

APP_NAME = "TriviumCAD"
VERSION = "1.2.0"

# Colori per il tema azzurro pastello
BACKGROUND_COLOR = "#AEC8E0"
TEXT_COLOR = "#0C1E36"
BORDER_COLOR = "#2C5F8A"
BUTTON_COLOR = "#C8DCF0"
BUTTON_HOVER = "#CFFAFE"
BUTTON_PRESSED = "#94E6F2"

# Colori neutri per le forme
NEUTRAL_COLORS: List[List[float]] = [
    [0.7, 0.7, 0.7, 1.0],
    [0.4, 0.6, 0.8, 1.0],
    [0.8, 0.5, 0.5, 1.0],
    [0.5, 0.8, 0.5, 1.0],
    [0.8, 0.8, 0.4, 1.0],
    [0.6, 0.5, 0.8, 1.0],
    [0.5, 0.8, 0.8, 1.0],
    [0.8, 0.6, 0.4, 1.0],
    [0.7, 0.4, 0.7, 1.0],
    [0.4, 0.7, 0.6, 1.0],
    [0.9, 0.6, 0.6, 1.0],
    [0.6, 0.6, 0.9, 1.0]
]

SHAPE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "Cubo": {"type": "box", "params": {"larghezza": 20.0, "altezza": 20.0, "profondità": 20.0}},
    "Cilindro": {"type": "cylinder", "params": {"raggio": 10.0, "altezza": 30.0, "sezioni": 64}},
    "Sfera": {"type": "sphere", "params": {"raggio": 15.0, "suddivisioni": 4}},
    "Cono": {"type": "cone", "params": {"raggio_base": 12.0, "altezza": 30.0, "sezioni": 64}},
    "collare": {"type": "collare", "params": {"raggio_esterno": 20.0, "raggio_interno": 12.0, "altezza": 8.0}},
    "Esagono": {"type": "hexagon", "params": {"raggio": 10.0, "altezza": 30.0}},
    "Spirale": {"type": "spiral", "params": {"raggio": 15.0, "altezza": 30.0, "giri": 4, "spessore": 3.0}},
    "Arco": {"type": "arc", "params": {"raggio_est": 20.0, "raggio_int": 16.0, "apertura": 90.0, "altezza": 8.0}},
    "Scatola vuota": {"type": "hollow_box", "params": {"larghezza": 30.0, "altezza": 20.0, "profondità": 20.0, "spessore_muro": 2.0}}
}

# =============================================================================
# PROFILI STAMPANTI 3D
# =============================================================================
PRINTER_PROFILES = {
    "Bambu Lab X1C": {
        "brand": "Bambu Lab", "model": "X1 Carbon",
        "build_volume": (256, 256, 256), "nozzle": [0.4, 0.6, 0.8],
        "max_temp": 300, "bed_temp": 100,
        "protocols": ["mqtt_ftps"],
        "default_layer": 0.16, "default_infill": 15
    },
    "Bambu Lab P1S": {
        "brand": "Bambu Lab", "model": "P1S",
        "build_volume": (256, 256, 256), "nozzle": [0.4, 0.6, 0.8],
        "max_temp": 300, "bed_temp": 100,
        "protocols": ["mqtt_ftps"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Bambu Lab A1": {
        "brand": "Bambu Lab", "model": "A1",
        "build_volume": (256, 256, 256), "nozzle": [0.4, 0.6, 0.8],
        "max_temp": 260, "bed_temp": 80,
        "protocols": ["mqtt_ftps"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Bambu Lab A1 Mini": {
        "brand": "Bambu Lab", "model": "A1 Mini",
        "build_volume": (180, 180, 180), "nozzle": [0.4],
        "max_temp": 260, "bed_temp": 80,
        "protocols": ["mqtt_ftps"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Anycubic Kobra 3": {
        "brand": "Anycubic", "model": "Kobra 3",
        "build_volume": (250, 250, 260), "nozzle": [0.4],
        "max_temp": 260, "bed_temp": 95,
        "protocols": ["ftp", "smb", "octoprint", "anycubic_cloud", "file"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Anycubic Kobra 2": {
        "brand": "Anycubic", "model": "Kobra 2",
        "build_volume": (220, 220, 250), "nozzle": [0.4],
        "max_temp": 260, "bed_temp": 95,
        "protocols": ["ftp", "smb", "octoprint", "file"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Anycubic Vyper": {
        "brand": "Anycubic", "model": "Vyper",
        "build_volume": (245, 245, 260), "nozzle": [0.4],
        "max_temp": 260, "bed_temp": 95,
        "protocols": ["ftp", "smb", "octoprint", "file"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Creality K1 Max": {
        "brand": "Creality", "model": "K1 Max",
        "build_volume": (300, 300, 300), "nozzle": [0.4],
        "max_temp": 300, "bed_temp": 100,
        "protocols": ["creality_http", "ftp", "octoprint", "file"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Creality K1": {
        "brand": "Creality", "model": "K1",
        "build_volume": (220, 220, 250), "nozzle": [0.4],
        "max_temp": 300, "bed_temp": 100,
        "protocols": ["creality_http", "ftp", "octoprint", "file"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Creality Ender 3 V3": {
        "brand": "Creality", "model": "Ender 3 V3",
        "build_volume": (220, 220, 250), "nozzle": [0.4],
        "max_temp": 260, "bed_temp": 100,
        "protocols": ["ftp", "smb", "octoprint", "file"],
        "default_layer": 0.20, "default_infill": 15
    },
    "Prusa i3 MK3S+": {
        "brand": "Prusa", "model": "i3 MK3S+",
        "build_volume": (250, 210, 210), "nozzle": [0.25, 0.4, 0.6],
        "max_temp": 280, "bed_temp": 100,
        "protocols": ["prusalink", "ftp", "octoprint", "file"],
        "default_layer": 0.15, "default_infill": 15
    },
    "Prusa XL": {
        "brand": "Prusa", "model": "XL",
        "build_volume": (360, 360, 360), "nozzle": [0.4, 0.6],
        "max_temp": 290, "bed_temp": 110,
        "protocols": ["prusalink", "ftp", "octoprint", "file"],
        "default_layer": 0.20, "default_infill": 15
    }
}