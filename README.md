# TriviumCAD — CAD 3D per stampa 3D (by N47Lab)

**CAD 3D parametrico/mesh gratuito per stampa 3D — in italiano**

TriviumCAD è un ambiente integrato per la modellazione 3D, la progettazione meccanica,
la generazione di percorsi utensile (CAM) e l'invio diretto delle stampe alla
stampante 3D. Sviluppato in **Python** con **PyQt5 + OpenGL + trimesh**, è pensato
per chi vuole passare dall'idea al file stampabile senza cambiare programma.

- Versione: **1.2.0**
- Sviluppato da: **N47Lab Team (Alessandro Tulli)** — © 2026
- Licenza: **MIT** (vedi [LICENSE](LICENSE))

---

## Funzionalità chiave

| Funzionalità | Descrizione |
|---|---|
| ⭐ **Filettatura analitica** | Filettatura esterna e interna con 3 profili (Filo ISO 60°, Trapezio, Arrotondato) e 5 modalità (Auto, Metrico, UNF, UNC, Gas). Per 9 forme native la filettatura segue il profilo reale della superficie, non il bounding box. |
| ⭐ **Invio diretto alle stampanti** | 8 modalità di invio: 7 protocolli diretti (Bambu Lab MQTT+FTP, Creality HTTP, PrusaLink, OctoPrint, FTP, SMB, Anycubic Cloud) + esportazione con profilo stampante. 12 profili precaricati (Bambu Lab X1C/P1S/A1/A1 Mini, Anycubic Kobra 3/Kobra 2/Vyper, Creality K1 Max/K1/Ender 3 V3, Prusa i3 MK3S+/XL) con volume di stampa, ugelli e impostazioni di default. |
| ⭐ **Import 2D → 3D con buchi** | Importa SVG, DXF e immagini (anche foto di silhouette): l'esterno diventa un solido estruso e i contorni interni diventano buchi automaticamente (binarizzazione + rilevamento contorni, fino a 400 punti per contorno). |
| Primitive | 9 primitive parametriche: Cubo, Cilindro, Sfera, Cono, Collare, Esagono, Spirale, Arco, Scatola vuota. |
| Testo 3D | Creazione testo, adattamento alla superficie della forma e bassorilievo. |
| Booleane | Unione, sottrazione, intersezione con 6 livelli di fallback per mesh difficili. |
| Guscio e fillet | Guscio su forme cave/aperte e arrotondamento spigoli (Taubin pesato con edge detection). |
| Slicer | Taglio a fette lungo gli assi con offset e numero di pezzi. |
| CAM | Percorsi utensile adattivi zig-zag (diametro utensile, passo laterale, quota di sicurezza, avanzamento). |
| Gizmo | Sposta, scala e ruota con goniometro a tacche (15°/45°); trascina le facce per allungare la forma. |
| Selezione | Click ray-cast, box select, Ctrl/Shift+Click per multi-selezione. |
| Undo/Redo | Fino a 50 passi (Ctrl+Z / Ctrl+Y). |
| Export | STL, OBJ, PLY, 3MF, GLB. |
| Console | Console Python integrata con accesso diretto a scena e oggetti selezionati. |
| Tutorial | Wizard di 11 pagine all'avvio, richiamabile da Opzioni/Aiuto. |
| Misura distanza/angolo | Ctrl+M (2 clic) e Ctrl+Shift+M (3 clic); popup "Misura — Scala forma" con scala uniforme centrata e undo. |
| Snap griglia | Allineamento al reticolo (Opzioni → Snap Griglia). |
| Chamfer | Smussatura spigoli (Menu Modifica → Chamfer…). |
| Pattern lineare/circolare | Copie di oggetti su riga o in cerchio (Menu Modifica → Pattern lineare… / Pattern circolare…). |
| Mirror | Specchiatura lungo gli assi (Menu Modifica → Specchia). |
| Smooth/Subdivide/Decimate | Rifinitura della mesh (Menu Mesh). |
| Riparazione mesh | Ricostruzione di mesh non watertight (Menu Mesh → Ripara). |

---

## Installazione

Richiede **Python 3.10+** (Windows, macOS, Linux).

```bash
pip install trimesh numpy shapely PyQt5 PyOpenGL scipy pillow scikit-image requests paho-mqtt
```

Dipendenze **opzionali** (funzionano in fallback se assenti, ma attivano funzioni extra):

| Pacchetto | Necessario per |
|---|---|
| `pillow` + `scikit-image` | Import immagini → 3D (rilevamento contorni e buchi) |
| `requests` | Invio a stampanti via HTTP (Creality, PrusaLink, OctoPrint, Anycubic Cloud) |
| `paho-mqtt` | Invio a stampanti Bambu Lab (MQTT + FTP over TLS) |
| `scipy` | Ottimizzazioni e fallback di robustezza (indice spaziale, guscio convesso, sobel) |

## Avvio

```bash
python triviumcad.py
```

## Struttura del progetto

```
TestN47Lab/
├── triviumcad.py         # Applicazione completa: UI (PyQt5), rendering OpenGL, logica
├── core/                # Modulo core, senza dipendenze Qt
│   ├── constants.py     # Costanti, libreria forme, profili stampante
│   ├── primitives.py    # Generazione mesh primitive e testo 3D
│   ├── mesh_ops.py      # Booleane, fillet, validazione mesh
│   ├── thread.py        # Filettatura (profili, mesh, sottrazione)
│   ├── cam.py           # Percorsi utensile adattivi
│   ├── scene.py         # Scena, undo/redo, operazioni, scanner
│   └── utils.py         # Utility (es. NumpyEncoder)
├── TriviumCAD.spec       # Build PyInstaller
└── TriviumCAD_setup.iss  # Installer Inno Setup
```

Il modulo `core/` è stato estratto dalla UI in modo da poter essere testato e
riutilizzato senza caricare Qt.

## Build

### Eseguibile (PyInstaller)

```bash
pyinstaller TriviumCAD.spec
```

Output in `dist\TriviumCAD\` (collezione one-folder con `TriviumCAD.exe`, icona `favicon.ico`).

### Installer Windows (Inno Setup)

1. Compila prima con PyInstaller (sopra).
2. Apri `TriviumCAD_setup.iss` in Inno Setup 6 e compila.
   Output: `installer\TriviumCAD_Setup_1.2.0.exe` — installa, crea scorciatoie,
   associa l'estensione `.n47` alle scene TriviumCAD (doppio clic per aprire).

## Screenshot

*(Sezione riservata: le immagini verranno aggiunte qui.)*

## Changelog

Vedi [CHANGELOG.md](CHANGELOG.md) per lo storico delle versioni.

## Tutorial

Guida completa all'uso: [TUTORIAL.md](TUTORIAL.md).

## Licenza

MIT — vedi [LICENSE](LICENSE). © 2026 N47Lab Team.