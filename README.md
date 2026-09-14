# TriviumCAD — CAD 3D open source per la stampa 3D (by N47Lab)

Dall'idea all'oggetto stampato senza cambiare programma.

[![Licenza: MIT](https://img.shields.io/badge/licenza-MIT-brightgreen?style=flat-square)](LICENSE)
[![Versione](https://img.shields.io/badge/versione-1.2.0-f0b429?style=flat-square)](https://github.com/Strugiss/TriviumCAD/releases)
[![Piattaforma](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=flat-square&logo=windows&logoColor=white)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)]()
[![Test](https://img.shields.io/badge/test-10%20inclusi-brightgreen?style=flat-square)](Test/)

![TriviumCAD v1.2.0 — screenshot dell'interfaccia](https://n47lab.altervista.org/triviumcad/immagini/TriviumCAD_v1.2.0_screenshot.png)

## Il problema, la soluzione

Chi progetta per la stampa 3D oggi passa da un CAD, poi uno slicer, poi un programma per l'invio: tre strumenti, tre formati, tre occasioni di errore. **TriviumCAD** unisce tutto in un unico ambiente: modelli con 9 forme parametriche, combini con booleane, filetti, misuri, generi i percorsi CAM e invii direttamente a 12 profili stampante — dalla stessa finestra, con una GUI in italiano. È scritto in Python (PyQt5 + OpenGL + trimesh), è gratuito, open source (MIT) ed è pensato per la stampa FDM reale, non per le demo.

## Funzionalità

| Funzionalità | Dettagli |
|---|---|
| ⭐ **Filettatura analitica** | Filetti esterni e interni con 3 profili (ISO 60°, trapezio, arrotondato) e 5 modalità (Auto, Metrico, UNF, UNC, Gas). Su 9 forme native la filettatura segue il profilo reale della superficie, non il bounding box |
| ⭐ **Invio diretto alla stampante** | 7 protocolli (Bambu Lab MQTT+FTP, Creality HTTP, PrusaLink, OctoPrint, FTP, SMB, Anycubic Cloud) + esportazione. 12 profili precaricati (Bambu Lab X1C/P1S/A1/A1 Mini, Anycubic Kobra 3/2/Vyper, Creality K1 Max/K1/Ender 3 V3, Prusa i3 MK3S+/XL) |
| ⭐ **Import 2D → 3D con buchi** | SVG, DXF e immagini (anche silhouette da foto): l'esterno diventa un solido estruso, i contorni interni diventano buchi automaticamente (fino a 400 punti per contorno) |
| **9 forme parametriche** | Cubo, Cilindro, Sfera, Cono, Collare, Esagono, Spirale, Arco, Scatola vuota — parametri aggiornati in tempo reale |
| **Booleane** | Unione, sottrazione, intersezione con 6 livelli di fallback per mesh difficili |
| **Testo 3D** | Creazione testo, adattamento alla superficie e bassorilievo |
| **GIZMO 3D** | Sposta, scala e ruota con goniometro a tacche (15°/45°); trascina le facce per allungare la forma |
| **CAM** | Percorsi utensile adattivi zig-zag: diametro utensile, passo laterale, quota di sicurezza, avanzamento |
| **Slice multi-pezzo** | Taglio a fette lungo X/Y/Z con offset e numero di pezzi per stampe grandi |
| **Misura e modifica** | Misura distanza (Ctrl+M) e angolo (Ctrl+Shift+M), chamfer, fillet, guscio, pattern lineare/circolare, mirror, smooth, subdivide, decimate, riparazione mesh |
| **Undo/Redo** | Fino a 50 passi (Ctrl+Z / Ctrl+Y) |
| **Export** | STL, OBJ, PLY, 3MF, GLB |
| **Console Python** | Integrata, con accesso diretto a scena e oggetti selezionati |
| **Tutorial** | Wizard di 11 pagine all'avvio, richiamabile da Opzioni/Aiuto |
| **Test** | 10 test inclusi (profili di filettatura e mesh) nella cartella `Test/` |

## Installazione

### Windows (installer pronto)

1. Scarica **TriviumCAD_Setup_1.2.0.exe**: [download diretto](https://n47lab.altervista.org/triviumcad/file/TriviumCAD_Setup_1.2.0.exe) (anche dalla [pagina del sito](https://n47lab.altervista.org/triviumcad/))
2. Esegui l'installer: crea le scorciatoie e associa l'estensione `.n47` (doppio clic per aprire una scena)
3. Avvia **TriviumCAD** dal menu Start

### Da sorgente (Windows, macOS, Linux)

Richiede **Python 3.10+**.

```bash
pip install trimesh numpy shapely PyQt5 PyOpenGL scipy pillow scikit-image requests paho-mqtt
python triviumcad.py
```

Dipendenze opzionali: `pillow` + `scikit-image` (import immagini → 3D), `requests` (invio HTTP), `paho-mqtt` (Bambu Lab), `scipy` (fallback di robustezza).

## Quick Start

1. **Apri il wizard** (11 pagine all'avvio) e crea la prima forma da *Crea → Primitive*: il viewport si naviga con orbit, pan e zoom
2. **Modella**: combina le forme con le booleane, aggiungi la filettatura (3 profili, 5 modalità) e misura con Ctrl+M
3. **Stampa**: scegli uno dei 12 profili e invia direttamente, oppure esporta STL/3MF per il tuo slicer

## Struttura del repository

```
TriviumCAD/
├── triviumcad.py         # applicazione completa: UI PyQt5, viewport OpenGL, logica
├── core/                 # motore senza dipendenze Qt
│   ├── constants.py      # costanti, libreria forme, profili stampante
│   ├── primitives.py     # primitive parametriche e testo 3D
│   ├── mesh_ops.py       # booleane, fillet, riparazione mesh
│   ├── thread.py         # filettatura: profili, mesh, sottrazione
│   ├── cam.py            # percorsi utensile adattivi zig-zag
│   └── scene.py          # scena, undo/redo, operazioni
├── Test/                 # 10 test + file di prova per import (SVG/DXF)
├── Documenti/            # documentazione di progetto
├── TriviumCAD.spec       # build PyInstaller
└── TriviumCAD_setup.iss  # installer Windows (Inno Setup)
```

## Link

- **Sito N47Lab**: https://n47lab.altervista.org/
- **TriviumCAD — sito dedicato**: https://n47lab.altervista.org/triviumcad/
- **Download**: https://n47lab.altervista.org/triviumcad/file/TriviumCAD_Setup_1.2.0.exe
- **Guide e tutorial**: [TUTORIAL.md](TUTORIAL.md) · [CHANGELOG.md](CHANGELOG.md)

## Licenza

MIT — vedi [LICENSE](LICENSE). © 2026 N47Lab (Alessandro Tulli).

## Contatti

**N47Lab** — laboratorio di ricerca e sviluppo software.
Sito: https://n47lab.altervista.org/ · GitHub: [@Strugiss](https://github.com/Strugiss)
