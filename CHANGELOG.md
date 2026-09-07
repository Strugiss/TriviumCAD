# Changelog TriviumCAD

Tutte le modifiche notevoli del progetto TriviumCAD sono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/);
versioning semantico: `MAJOR.MINOR.PATCH`.

## [1.2.0] - 2026-09-07

### Nome del prodotto

**Rinominato da N47Lab a TriviumCAD** (il nome N47Lab resta al laboratorio/autor: 'by N47Lab').

### Fix

**Camera — "scatto piano" risolto**

- Eliminato lo stato residuo della modalità "release" che faceva scattare la
  vista al click successivo.
- Perno di rotazione asse Z (ROT_Z) corretto durante l'orbita.
- Guardie anti-jitter su trascinamento e orbita.
- Clamp della rotella di zoom (limiti minimo/massimo rispettati).

**Testo 3D — 12 difetti corretti**

- "Adatta" poteva proiettare il testo sulla faccia sbagliata della forma.
- Profondità incisione errata nel bassorilievo.
- Testo multilinea mal gestito.
- Dimensioni frazionarie non rispettate.
- Font mancante sul sistema: fallback gestito.
- Mesh del testo non sempre watertight.
- Crash su import SVG con geometria non valida.
- Import dei componenti del testo (caratteri/parole) corretto.

**Critici corretti**

- Doppia finalizzazione operazioni: eliminata la chiamata duplicata
  (`end_operation` + `cancel_operation` nel `finally`).
- Smooth/Subdivide non crashano più sulle mesh sostituite: il riferimento
  originale viene salvato prima della sostituzione dell'oggetto.
- Rotazione dal pannello Proprietà: le spinbox `rot_x`/`rot_y`/`rot_z` ora
  ruotano effettivamente l'oggetto.
- `_notify()` collegato alla **status bar**: i feedback delle operazioni sono
  visibili all'utente (prima finivano solo su stdout).
- Status bar: il **timer FPS** non sovrascrive più i messaggi di misura e le
  notifiche delle operazioni.

### Aggiunto (funzioni attivate)

- **Misura distanza/angolo**: `Ctrl+M` (2 clic) e `Ctrl+Shift+M` (3 clic) con
  popup **"Misura — Scala forma"** (scala uniforme centrata, con undo).
- **Snap griglia** funzionante (Opzioni → Snap Griglia).
- **Chamfer** (Menu Modifica → Chamfer…).
- **Pattern lineare e circolare** (Menu Modifica → Pattern lineare… / Pattern
  circolare…).
- **Mirror / Specchia** lungo X, Y, Z (Menu Modifica → Specchia).
- **Smooth, Subdivide, Decimate** (Menu Mesh).
- **Ripara** (Menu Mesh → Ripara): riparazione di mesh non watertight.
- **Outliner con layer**: elenco oggetti con layer; clic per selezionare,
  Ctrl+clic per multi-selezione.

### Migliorie

- **Core modulare senza Qt**: la logica computazionale è stata estratta in
  `core/` (`constants`, `primitives`, `thread`, `mesh_ops`, `cam`, `scene`,
  `utils`), testabile e riutilizzabile senza caricare l'interfaccia.
- **Documentazione**: aggiunti README.md, TUTORIAL.md e questo CHANGELOG.md;
  i report di sviluppo sono stati raccolti in `Documenti/`.
- **Versione unica**: `VERSION` centralizzata in `core/constants.py`
  (1.2.0) e usata da UI e dialoghi.

## [1.1.0] - 2026-07-18

Riepilogo dello sviluppo 22/06 → 17/07 (da `report_modifiche.txt`).

### Aggiunto

- **Riconoscimento topologico "Sposta Faccia" v2**: selezione della faccia per
  componente connessa (normale allineata all'asse, soglia 40°) e allungamento
  uniforme dal centro senza assottigliare la sezione.
- **Face Handles Gizmo**: 6 maniglie al centro di ogni faccia del bounding box
  (X+/X−, Y+/Y−, Z+/Z−) con frecce 3D, offset proporzionale alla dimensione.
- **Splash screen** con logo "CAD" 3D (QPainterPath, ombra 3D).
- **Stampa 3D diretta**: 12 profili stampante (Bambu Lab X1C/P1S/A1/A1 Mini,
  Anycubic Kobra 3/Kobra 2/Vyper, Creality K1 Max/K1/Ender 3 V3,
  Prusa i3 MK3S+/XL) e protocolli MQTT+FTP, HTTP WiFi, PrusaLink, OctoPrint,
  FTP, SMB, Cloud.
- **Filettatura interna incisa**: booleana DIFFERENZA con volume watertight;
  raggio superficie reale su ogni forma nativa; fallback ray-casting per forme
  importate.
- **Filettatura esterna**: generazione diretta della mesh (N×M sezioni, vertici
  dei tappi condivisi → watertight, ~3600 vertici per cilindro standard);
  profili Filo ISO 60°, Trapezio, Arrotondato.
- **TutorialDialog**: wizard a schede (11 pagine) con navigazione, contatore
  pagina, "Nascondi all'avvio" (QSettings), mostrato dopo lo splash.
- **Adatta Testo**: proiezione radiale dal centro della forma con raycast
  batch, spessore preservato lungo la normale, normali corrette.
- **Sezione 2D→3D completamente riscritta**: SVG/DXF via
  `trimesh.load_path()` + `extrude_polygon()` (fallback `force='mesh'`);
  immagini via `skimage.find_contours()` (fallback ConvexHull);
  rivoluzione, loft e sweep con `trimesh.creation`.
- **Buchi automatici nella silhouette**: binarizzazione (soglia 0.4),
  `unary_union` dei contorni interni + `difference` dall'esterno,
  semplificazione a ~400 punti, normalizzazione poligoni.

### Corretto

- Bug "piano che scatta": `_drag_target` residuo nella `_sync_camera()`.
- Booleane senza Undo e metadata corrotto: `start_operation/end_operation`,
  metadata selettivo e `_refresh_outliner()`.
- Codice duplicato in Adatta Testo (NameError).

### Migliorato

- Performance: display list per il gizmo, `glPushAttrib` ristretto, operazioni
  pesanti (booleane, toolpath, filettatura, fillet) in QThread con progress
  dialog — UI non bloccante.
- Fillet: subdivisione adattiva (max 10 000 facce), edge detection sugli spigoli
  vivi, peso gaussiano + Taubin filter + blend (volume −0.65% ÷ −1.79%).
- Interfaccia: finestra dinamica (1280×720, min 960×540), griglia forme 3×3.

## [1.0.0] - 2026-06-22

Rilascio iniziale (storico non dettagliato; vedi `Documenti/` per i report di
sviluppo precedenti).