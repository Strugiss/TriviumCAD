# Changelog TriviumCAD

Tutte le modifiche notevoli del progetto TriviumCAD sono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/);
versioning semantico: `MAJOR.MINOR.PATCH`.

## [1.3.0] - 2026-10-04

### Corretto — round-trip file: metadata filettatura esterna, export solo visibili, testo 3D

- **Filettatura ESTERNA preserva i metadata** (`triviumcad.py`, `_run_threading`
  ramo Esterna): dopo `_compute_thread_mesh` il risultato copia i metadata
  dell'oggetto originale (nome `*_filettato`, layer, colore, visible, locked,
  shape_type) e rimuove le cache GL (`_gl_verts`, `_gl_normals`,
  `_gl_vbo_verts`, `_gl_vbo_normals`), come già faceva il ramo Interna.
  Smoke: Cilindro con layer `LayerTest` → Filettatura Esterna → Salva `.n47` →
  `mesh_0_meta.json` con name=`cilindro_meta_filettato`, layer, color, visible,
  locked, shape_type (7/7 check).
- **Export STL esclude gli oggetti con visibilità OFF** (`triviumcad.py`,
  `_export`): aggiunto il filtro `obj.metadata.get("visible", True) is not False`
  (None/True = visibile). Stessa coerenza applicata ai percorsi 3MF/scena intera
  "Invia alla stampante" (`_send_to_printer`) ed "Esporta con profilo stampante"
  (`_export_profile`), che esportano l'intera scena. Il salvataggio `.n47`
  continua a salvare TUTTO (nessun filtro). Smoke: 2 box 10/20 mm con uno
  `visible=False` → STL volume 1000.00 (solo il visibile; con l'hidden sarebbe
  9000.00); `.n47` con 2 mesh.
- **Testo 3D con metadata coerenti alle primitive** (`triviumcad.py`,
  `_add_text_mesh`): aggiunti `visible=True` e `locked=False` (layer già
  `scene.active_layer`, default `Default`). Smoke: Testo → Salva →
  `mesh_0_meta.json` con visible/locked.
- Verifica Windows: `python -m py_compile triviumcad.py` OK;
  `python -m pytest Test/ -q` → **25 passed**; smoke mirato 24/24 check.
  Backup preventivo: `Backup\PRE_2026-10-04_fix_file\triviumcad.py` e
  `CHANGELOG.md` (hash SHA256 identici agli originali).
  `10_PROGETTO_PenguinCAD` non toccato.

### Corretto — fix in tempo reale da mega-collaudo (snap, overlay misura, metadata, separati)

- **Magneti/Snap — stato allineato menu↔toolbar** (`triviumcad.py`): i pulsanti
  toolbar sono ora riferimenti persistenti (`self._snap_btn`, `self._magnet_btn`)
  e `_toggle_snap` / `_toggle_magnetic` sincronizzano il checked di voce menu e
  pulsante in entrambe le direzioni (helper `_sync_toggle_controls`, con
  `blockSignals` per evitare rientranze). Smoke: 5/5 casi OK (menu→toolbar,
  toolbar→menu, incrociato, Snap e Magneti).
- **Overlay misura visibile nella viewport 3D** (`triviumcad.py`, GLWidget):
  QPainter dentro `paintGL` di QOpenGLWidget non produceva output e il pattern
  `beginNativePainting` è risultato instabile (crash nativo su Windows);
  l'overlay è ora disegnato dal nuovo widget figlio trasparente e non
  interattivo `_MeasureOverlay`, gestito da `_update_measure_overlay` su click,
  Esc, resize e fine frame. Linea a coordinate half-pixel per nitidezza (prima
  sdoppiata al 50% dall'antialiasing). Smoke: dopo Ctrl+M + 2 click, pixel
  esatti `(255,200,60)` = 6, vicini (tol 8) = 209, sequenza orizzontale di
  208 px a y=444 tra i punti riproiettati; screenshot
  `%TEMP%\opencode\fix_rt_overlay_measure_win.png` e crop
  `%TEMP%\opencode\fix_rt_overlay_measure_fascia.png`.
- **Metadata preservati** (l'Outliner non mostra più `?`): `Scene.subdivide` e
  `Scene.decimate` (`core/scene.py`) copiano i metadata dell'originale (nome,
  colore, layer, shape_type, params) sul risultato e rimuovono le cache GL
  riferite alla vecchia geometria; Filettatura Interna (`triviumcad.py`, ramo
  booleana) fa lo stesso e rinomina `*_filettato`, come il ramo Esterna. Smoke:
  `box_1` mantenuto dopo Subdivide (cache GL assente) e Decimate (768→192
  facce); `cylinder_1` → `cylinder_1_filettato` mostrato in Outliner.
- **Separati ripulisce `scene.assemblies`** (`core/scene.py`): `ungroup_object`
  ora rimuove l'assembly (`del self.assemblies[...]`) oltre ad azzerare il
  metadata `assembly` degli oggetti selezionati, come `explode_assembly`.
  Smoke: Raggruppa→Separati → `len(assemblies)==0`; verificato anche il caso
  con un solo oggetto selezionato.
- Verifica Windows: `python -m py_compile` OK; `python -m pytest Test/ -q` →
  **25 passed**. Backup preventivo:
  `Backup\PRE_2026-10-04_fix_rt\triviumcad.py` e
  `Backup\PRE_2026-10-04_fix_rt\core\scene.py` (hash SHA256 identici agli
  originali). `10_PROGETTO_PenguinCAD` non toccato.

### Corretto — 2PenAxE: entità di tutti i piani visibili in prospettiva (viste Isometriche all'apertura)

- **Entità dei piani non attivi ben visibili** in entrambi i pannelli
  (`SketchCanvas._draw_entities`): azzurro chiaro `#83CBFF` (nuova costante
  `BLUE_ENTITY`) con alpha 230 e spessore 1.8, al posto del blu tenue
  `rgba(91,163,230,110)` spessore 1.4; il piano attivo resta bianco
  `TEXT_BODY` spessore 2.0 e la selezione verde `GREEN_CRT` 2.4 è invariata.
  La distinzione piano attivo / altri piani è mantenuta.
- **Viste di default oblique**: all'apertura del dialogo entrambi i pannelli
  partono dalla vista **Isometrica** `(-45°, 30°)` (`STANDARD_VIEWS`), così
  ogni piano è visibile in prospettiva in entrambi i pannelli (prima A=XY
  partiva da Alto e B=XZ da Fronte: i disegni degli altri piani restavano di
  taglio). I pulsanti Alto / Fronte / Lato / Isometrica e il comportamento
  del selettore piano restano invariati.
- **Proiezione WYSIWYG verificata**: ogni entità è proiettata con la camera
  del proprio pannello. Smoke GUI reale con linea+cerchio su A (XY) e linea
  su B (XZ): campioni proiettati su pixel del colore atteso 41/41, 65/65,
  41/41, 41/41, 41/41; pixel azzurri/bianchi canvas A **605/891**, canvas B
  **838/619**; viste default A e B `(-45°, 30°)`; i 4 pulsanti vista
  applicano le viste corrette. Screenshot:
  `%TEMP%\opencode\2penaxe_viste_01_dialog_iso.png`, `..._02_canvas_A.png`,
  `..._03_canvas_B.png`, `..._04_pulsante_alto.png`, `..._05_finale_iso.png`.
- Verifica Windows: `python -m py_compile sketch.py` OK;
  `python -m pytest Test/ -q` → **25 passed**. Backup preventivo:
  `Backup\PRE_2026-10-04_2penaxe_viste\sketch.py`.

### Aggiunto — 2PenAxE: sketch 2D multi-piano (modale, live, persistente)

- **Pulsante toolbar "2PenAxE"** (icona custom `Immagini/2penaxe_64.png` + testo,
  stesso stile unico della toolbar: sfondo `#132A47`, bordo ambra `#f0b429`,
  testo bianco) che apre una **finestra separata MODALE** (1600×900, min
  1200×700, standard scuro del precetto).
- **Nuovo modulo `sketch.py`** (autonomo, importato da `triviumcad.py`):
  modello entità JSON-safe, conversioni piano→3D, motore snap/ancore puro,
  `SketchCanvas` (vista 3D orbitabile a 360° con QPainter, proiezione
  ortografica) e `SketchDialog`.
- **Due pannelli affiancati** con selettore piano libero **XY / XZ / YZ**
  per ciascuno; vista orbitabile con rotazione (tasto destro o modalità
  dedicata), zoom (rotella o modalità), pan (tasto centrale o modalità);
  griglia millimetrata e assi colorati (X ambra, Y verde CRT, Z blu
  `#5ba3e6`); bussola di orientamento.
- **Strumenti**: linea, polilinea (doppio clic/Invio), rettangolo, cerchio,
  arco (centro-inizio-fine), selezione/sposta (drag), gomma, misure live
  (lunghezza, raggio, L×H, angolo); tooltip in italiano su ogni pulsante.
- **Ancore selezionabili (7)**: Endpoint, Midpoint, Centri, Intersezioni,
  Proiezioni assi, Origine, Griglia — checkbox + contatore "N / 7",
  evidenziazione al cursore (marcatore ambra con etichetta del tipo) e
  aggancio al click; priorità CAD: geometriche → assi → griglia (la griglia
  aggancia sempre quando attiva). Passo griglia reale in mm (1–50).
- **Viste standard**: Alto (XY), Fronte (XZ), Lato (YZ), Isometrica; si
  applicano al pannello con il focus (altrimenti a entrambi).
- **Live update scena 3D**: a ogni modifica il dialog aggiorna
  `scene.sketch_2d_entities` e ridisegna il `GLWidget`; il `GLWidget` disegna
  le linee dello sketch (overlay ambra) in `paintGL` via
  `sketch.entity_to_3d_paths`.
- **Persistenza `.n47`**: `scene.json` contiene `sketch_2d.entities` +
  `sketch_2d.state` (piani A/B, passo griglia, ancore, strumento); riaprendo
  il file lo sketch è **ri-editabile** e le linee ricompaiono in scena.
  Retrocompatibile: scene senza `sketch_2d` caricano vuoto.
- **WYSIWYG**: entità in mm reali sul piano (XY→`(u,v,0)`, XZ→`(u,0,v)`,
  YZ→`(0,u,v)`); quote live fedeli; riapertura identica.
- **Undo/Redo** (`Ctrl+Z` / `Ctrl+Y`, pulsanti ↶ ↷, fino a 100 passi) con
  snapshot delle entità; **Annulla/X** ripristina lo stato di apertura,
  **Applica** conferma senza chiudere, **OK** conferma e chiude.
- **Sweep di coerenza**: README (funzionalità + struttura progetto),
  TUTORIAL.md (sezione 4.18 + toolbar), `Documenti\FEATURE MANCANTI (top).txt`
  (sketch 2D → FATTO v1), `TriviumCAD.spec` (icona nei datas per PyInstaller).
- Verifica Windows: `python -m py_compile` OK; `python -m pytest Test/ -q` →
  **25 passed** (10 baseline + 15 nuovi in `Test/test_sketch.py`); smoke GUI
  reale (`%TEMP%\opencode\smoke_2penaxe.py`) con dialog modale via `exec_`:
  pannelli A=XY/B=XZ, viste Alto/Fronte; live 1→2→3→4 entità; snap Endpoint
  su `(-60.00, -40.00)` con aggancio `p1` esatto e marcatore visibile; snap
  Griglia su `(10.00, 10.00)`; misura 3-4-5 = `50.0 mm`; undo 4→3 e redo →4;
  vista Isometrica `(-45°, 30°)`, Alto `(0°, 0°)`; pixel ambra in scena 3D
  **2063** sia live sia dopo riapertura `.n47` (identica, WYSIWYG); rollback
  Annulla OK; click reale sul pulsante → status "2PenAxE: sketch con 4
  entità". Screenshot: `2penaxe_01_dialog.png`, `2penaxe_02_scena_live.png`,
  `2penaxe_03_dopo_riapertura.png`, `2penaxe_04_rieditabile.png`,
  `2penaxe_05_snap_marker.png`, `2penaxe_06_finestra_main.png`.
- Limiti dichiarati (v1): constraint solver **escluso** (richiesta N47);
  nessun trim/fillet 2D; le quote live non sono entità persistenti.

### Uniformato — Pulsanti toolbar: stile unico (blu + bordo ambra + testo bianco + emoji)

- **Stile unico `btn_qss`** in `_setup_toolbar` per TUTTI i 10 pulsanti della
  toolbar ("Da2 a 3D", "Nuovo", "Apri", "Salva", "Booleane", "Guscio", "Snap",
  "Magneti", "Sostieni", "Sito"): sfondo blu `#132A47` (`BG_CARD`), bordo ambra
  `#f0b429` (`AMBER`) spesso 2 px, testo bianco `#ffffff`, radius 12 px.
  Eliminati gli stili disomogenei ("Sostieni" ottone, "Sito" ambra piena) e le
  icone a cerchio `_make_icon` dai pulsanti della toolbar (invariate nei
  pannelli). Callback, menu "Booleane", separatori, ordine e layout invariati.
- **Emoji davanti al testo per tutti**: 🧊 Da2 a 3D, 🆕 Nuovo, 📂 Apri,
  💾 Salva, 🅱 Booleane, 🛡️ Guscio, 🎯 Snap, 🧲 Magneti, 💖 Sostieni, 🌐 Sito.
- **Fix fallback font Windows (collaudo N47)**: 🐚 (0 px colorati), ❤️ (resa
  bianca) e 📐 (16 px colorati) non erano rese a colori dal font di fallback.
  Sostituite con la prima candidata che passa la verifica empirica PIL su GUI
  reale (`w.grab()`, pixel con `max−min > 45` nella zona emoji, soglia > 50):
  🛡️ Guscio (🥅 fermo a 43 px, 🛡️ 88 px), 🎯 Snap (📏 fermo a 21 px, 🎯
  97 px), 💖 Sostieni (83 px). Le scelte passano anche con la metrica
  posizionale che esclude il bordo per costruzione (🛡️ 95, 🎯 104, 💖 117).
  Le altre 7 emoji restano invariate.
- **Stati coerenti**: hover blu `#173258` (`BG_ELEV`), pressed `#1d3b66`
  (`BUTTON_PRESSED`); checked/attivi (Snap/Magneti) con base blu `#173258` e
  bordo ambra più luminoso `#f7c948` (`AMBER_LIGHT`) — nessun ritorno all'ambra
  pieno.
- Verifica Windows: `python -m py_compile` OK; `python -m pytest Test/ -q` →
  10 passed; GUI reale con campionamento PIL di OGNI pulsante — sfondo
  `#132A47` 10/10, bordo `#f0b429` 10/10 (4 lati), testo bianco 10/10, emoji
  10/10; Snap/Magneti checked: sfondo `#173258`, bordo `#f7c948`. Screenshot:
  `%TEMP%\opencode\toolbar_base.png`, `toolbar_base_full.png`,
  `toolbar_checked.png`.
  Verifica finale fix emoji: 10/10 a colori anche con la metrica posizionale
  che esclude il bordo (x=8..34; 🛡️ 95, 🎯 104, 💖 117, 📂 121), sfondo/
  bordo/testo 10/10; screenshot `%TEMP%\opencode\toolbar_emoji_final.png`
  (+ `_full.png`).

### Restyling — Palette del precetto (STANDARD_VISIVO) su tutta l'interfaccia

- **Palette centralizzata** in `core/constants.py` (valori letti alla lettera da
  `STANDARD_VISIVO.md`): sfondi `#0C1E36` / `#10243F` / `#132A47` / `#173258`,
  bordi `rgba(120,160,220,0.18)`, ambra `#f0b429` / `#f7c948` / `#8a6118` /
  `#d9a23c` / `rgba(240,180,41,0.14)`, ottone `#b87333` / `#d4944a`, verde CRT
  `#33ff33` / `#1a9e1a` (solo accenti/valori brevi, mai testi lunghi), testi
  `#dde6f5` / `#9fb3cc`; alias legacy rimappati sulla palette scura.
- **QSS globale** (`_app_stylesheet()`, estratta da `main()` per riuso negli
  script di verifica — unica fonte, nessun drift): menu bar/menu, toolbar,
  gruppi, pulsanti, campi, combo, spinbox, checkbox, slider, scrollbar, status
  bar, dock/outliner, tooltip, tab. Radius 8–12 px, hover `#173258`.
- **Font da precetto** con fallback documentati (nessun download): Orbitron per
  titoli/brand/pulsanti, Inter per il testo, Share Tech Mono per dati/status/
  console.
- **Widget aggiornati**: TutorialDialog, PrinterConnectDialog (pulsante "Invia
  alla stampante" in ambra con testo `#101014`), PropertiesPanel (valori X/Y/Z
  verde CRT, L/H/P ambra, font mono), ConsoleDialog (messaggi in palette),
  icone occhio/lucchetto dell'Outliner, splash (brand Orbitron ambra, lettere
  CAD ottone), pulsanti toolbar ("Sostieni" ottone, "Sito" ambra), placeholder.
- **Viewport 3D**: sfondo `#0C1E36`, griglia in tinte blu tenui, assi centrali
  X/Y/Z nella convenzione standard 3D (rosso/verde/blu); righelli e etichette
  goniometro in palette.
- Verifica Windows: contrasto WCAG **AAA su 6 coppie campione** (≥7.28:1);
  screenshot PRIMA/DOPO e campionamento PIL in `%TEMP%\opencode\`; test
  `python -m pytest Test/ -q` → 10 passed.

### Fix — Outliner: nomi non aggiornati a parità di conteggio (collaudo D1)

- **`_sync_outliner_selection`**: aggiorna SEMPRE i testi (e le icone
  visibilità/lucchetto) degli item esistenti, anche quando
  `len(scene.objects)` non cambia — es. "Adatta": il testo sostituito
  (`*_adattato`) resta nella stessa posizione e l'item mostrava il vecchio
  nome. Riprodotto prima del fix (item `Testo_N47`, scena
  `Testo_N47_adattato`), verificato dopo (item allineato); stesso esito per la
  rinomina di un oggetto.

### Aggiunto — Pannelli laterali collassabili (Outliner sempre visibile)

- **Pannello sinistro** (Forme Primitive / Meccanica / CAM) e **pannello destro**
  (Testo 3D / Parametri / Analisi) collassabili: si richiudono verso il lato
  rispettivo e la vista 3D si espande a tutto campo.
- **Linguetta sul bordo** quando il pannello è chiuso (pulsante verticale con
  freccia: ▶ a sinistra, ◀ a destra) per riaprirlo; pulsante di chiusura in cima
  al pannello quando è aperto. Aperti di default, nessuna persistenza dello stato.
- **Outliner sempre visibile**: è un `QDockWidget` separato dal layout centrale,
  quindi il collasso del pannello destro non lo nasconde; rimosso il flag
  `DockWidgetClosable` così non può essere chiuso per errore.
- Pulsanti/linguette più visibili: larghezza 28 px (26/56 px di altezza),
  frecce a 16 px e palette da precetto (`STANDARD_VISIVO`): fondo ambra
  `#f0b429`, testo/freccia `#101014`, hover `#f7c948`, bordo `#8a6118`,
  pressed `#d9a23c`; tooltip "Chiudi/Apri pannello" su ogni pulsante.
  Nessuna modifica alle funzioni interne dei pannelli.

### Fix — porting fix universali da PenguinCAD (collaudo Linux)

- **`core/primitives.py` — arco (`_generate_blender_arc`)**: il settore rispetta
  l'`apertura` reale (prima il taglio a semipiano produceva sempre ~180°);
  360° = anello pieno.
- **`core/primitives.py` — scatola vuota (`_generate_blender_hollow_box`)**:
  `except` non più silenzioso (log su stdout, fallback al cubo pieno tracciato).
- **`core/scene.py` — undo/redo**: salvati anche gli stati con 0 oggetti
  (dopo un delete totale `redo()` ripristina la scena vuota).
- **Camera (`_adapt_text_to_shape`)**: posizione camera secondo la convenzione
  PyOpenGL (`-mv[:3,:3] @ mv[3,:3]`): eliminato il falso "Camera troppo vicina".
- **`_simplify_contour`**: campionamento a indici equidistanti (rispetta
  `max_pts`, es. 1000→400).
- **`_send_fileonly`**: rimosso l'`import os` locale che rompeva il fallback
  `~`; copia sul Desktop via `QStandardPaths`; status "File pronto" solo se la
  copia riesce, altrimenti status d'errore.
- **`PrinterConnectDialog`**: il cambio protocollo passa il codice
  (`currentData()`), non la label; campo Utente/Email abilitato anche per
  Anycubic Cloud (label "Email (Anycubic Cloud):", placeholder email).
- **`_run_blocking`**: le eccezioni del worker sono segnalate all'utente
  (warning), non solo nel traceback.
- **`_cad_repair`**: il messaggio d'errore non è più sovrascritto da
  "Nessun oggetto riparato"; log su stdout.
- **Menu Modifica**: voci Taglia/Copia/Incolla collegate a
  `GLWidget._cut_selected/_copy_selected/_paste_clipboard` con Ctrl+X/C/V.
- **`_open`**: per file SVG/DXF/immagine indirizza a "Da 2D a 3D" invece
  dell'errore di trimesh.
- **Gizmo (`pick_handle`)**: tolleranza dedicata di 15 px per i quadratini di
  rotazione (`rh*`): non intercettano più il drag del corpo (traslazione con
  snap).
- **Pannello Parametri**: X/Y/Z e Rot X/Y/Z sincronizzati con l'oggetto
  selezionato (`_sync_param_fields` in `update_ui`, `blockSignals`).
- **Pannello sinistro scrollabile**: avvolto in `QScrollArea`
  (`widgetResizable`), pattern del pannello destro.
- **Contrasti WCAG**: pulsante "Invia alla stampante" `#4CAF50`→`#2E7D32`;
  label info protocollo `#3060A0`→`#1F4E79`; placeholder "Inserisci testo..."
  `#6E6E6E`; rimossa la cornice ASCII dal titolo della console.
- **Scorciatoie**: Ctrl+D = Duplica; deselezione totale su Ctrl+Shift+D
  (`GLWidget.keyPressEvent`).
- **Tutorial interno**: "Profili integrati (13)"→12; titolo sezione
  "🖨️ Stampa 3D"→"🖨️ Invia alla stampante".
- **`requirements.txt`**: creato con le dipendenze reali e le opzionali.
- **Documentazione allineata**: `TUTORIAL.md` (Ctrl+D = Duplica / Ctrl+Shift+D =
  Deseleziona; menu "File → Invia alla stampante...") e `README.md`
  (`requirements.txt` citato nell'installazione).

### Fix — Testo 3D su Windows: multi-selezione e adattamento robusto

- **Scena — Ctrl+click = multi-selezione**: il Ctrl+click sinistro su un oggetto
  era intercettato come orbita camera e la selezione non arrivava mai a
  `selected_objects` (il testo o la forma restavano da soli). Ora Ctrl+click
  su un oggetto fa toggle di selezione (stesso percorso di Shift+click);
  l'orbita con Ctrl resta solo sullo spazio vuoto. Diagnosi: la selezione
  "testo+forma" non arrivava a `_adapt_text_to_shape`/`_bassorilievo`.
- **`_adapt_text_to_shape` — fallback rigido orientato**: la proiezione
  per-vertice poteva lasciare centinaia di vertici senza hit (testo
  compenetrato nella forma o oltre i bordi della faccia; il codice misurava
  lo spessore lungo l'asse Y globale mentre `fn` poteva essere X/Z),
  producendo una mesh con bordi aperti (`watertight=False`) e facendo fallire
  la booleana del Bassorilievo ("Not all meshes are volumes"). Se la mesh
  proiettata non è un volume, il testo viene ora riorientato (spessore Y→`fn`),
  centrato sull'ancora e appoggiato alla superficie **senza deformarlo**:
  `_adattato` è sempre watertight/volume.
- Verifica Windows: `python -m pytest Test/ -q` → 10 passed; smoke GUI
  (scena Ctrl+click e Outliner Ctrl+click → 2 oggetti selezionati;
  Adatta → `_adattato` volume valido; Bassorilievo → `_inciso` volume valido).

Nota: i fix "`_new` — conferma su scena non vuota + invalidazione VBO" e
"test con `CORE_DIR` relativo" erano già presenti (v1.2.1) e non sono stati
duplicati.

## [1.2.1] - 2026-09-17

### Fix

**Comando "Nuovo" — la causa del "non fa nulla"**

- **Conferma su scena non vuota**: se ci sono oggetti non salvati viene chiesto
  "Creare una nuova scena comunque?" con pulsanti **Annulla** (lascia tutto
  intatto) e **Crea**.
- **Feedback visibile**: "Nuova scena creata" mostra la conferma nella status
  bar; prima, a scena già vuota, il comando non produceva alcun segnale visibile.
- **Scorciatoia `Ctrl+N`** sull'azione di menu File → Nuovo.
- **Invalidazione dei VBO** della scena precedente prima della sostituzione.

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