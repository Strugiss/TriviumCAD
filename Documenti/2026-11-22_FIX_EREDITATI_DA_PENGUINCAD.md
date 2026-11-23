# Fix ereditati da PenguinCAD — scaletta per TriviumCAD

**Data:** 22/11/2026
**Fonte:** PenguinCAD 1.3.1, sette fix validati (98/98 test su Windows e Linux).
**Destinazione:** TriviumCAD 1.3.0, commit `691c7c9`, branch `main`.
**Stato:** i fix **non** sono applicati a TriviumCAD. Questo documento li
registra per la ripresa, senza ricerche superflue.

## Contesto

I sette difetti sono nati in TriviumCAD 1.3.0 e sono stati corretti solo in
PenguinCAD, il port Linux. Le implementazioni di riferimento sono in
`10_PROGETTO_PenguinCAD\penguincad.py`, `core\scene.py` e `Test\`.

TriviumCAD usa OpenGL 3.3 Compatibility, tema scuro e toolbar con emoji.
PenguinCAD usa OpenGL 2.1, tema scuro e toolbar QPainter. **I fix sono
funzionali: non vanno copiati gli stili né il contesto OpenGL.**

## Ordine consigliato (dal più rapido)

1. picking oggetti nascosti;
2. console e cache GL;
3. valore nell'overlay misura;
4. rinomina dall'outliner;
5. scala ancorata a Z=0;
6. pannello Proprietà Layer/Shape;
7. misura 3D su Z≠0.

## Dettaglio dei sette interventi

### 1. Picking oggetti nascosti

- **Difetto:** `_pick_object` filtra solo il layer; `_select_objects_in_box`
  include i nascosti. Un oggetto `visible=False` è selezionabile.
- **Riferimento Trivium:** `triviumcad.py:1429-1457` e `1619-1662`.
- **Fix PenguinCAD:** in `_pick_object` e `_select_objects_in_box`, escludere
  `metadata.get("visible", True) is False`; l'oggetto resta in scena,
  nell'outliner e fuori dall'export.
- **Test PenguinCAD:** `Test\test_picking_e_console.py`.
- **PASS:** click sul nascosto → 0 selezioni; box select → solo visibile;
  export invariato.

### 2. Console e cache GL

- **Difetto:** dopo `exec`/`eval` la console chiama solo `gl_widget.update()`;
  le cache `_gl_verts`, `_gl_normals`, `_gl_vbo_*` restano e la geometria
  modificata non si vede.
- **Riferimento Trivium:** `ConsoleDialog` intorno a `triviumcad.py:3321-3465`.
- **Fix PenguinCAD:** lista unica `_GL_CACHE_KEYS`; `_invalida_cache_gl`;
  `_vbo_pendenti` cancellati nel `paintGL` con contesto corrente;
  `_invalidate_all_vbos` dopo `exec`/`eval`.
- **Test PenguinCAD:** `Test\test_picking_e_console.py`.
- **PASS:** `obj.apply_scale(0.5)` in console → volume 1000 mm³ al frame
  successivo, cache assenti.

### 3. Valore nell'overlay misura

- **Difetto:** l'overlay disegna marker e linea, non il valore; il valore è
  solo nella status bar e nel dialog.
- **Riferimento Trivium:** `_draw_measurement_overlay`,
  `_update_measure_overlay`.
- **Fix PenguinCAD:** `_testo_misura(mode, points)`; badge con distanza/angolo;
  `scene.measurement_done`; la misura completata resta in scena finché Esc o
  una nuova misura; status coerente.
- **Test PenguinCAD:** `Test\test_measure_overlay.py`.
- **PASS:** badge “10.00 mm” e “90.0°” persistenti, contrasto ≥ 7:1.

### 4. Rinomina dall'outliner

- **Difetto:** item non editabili, nessun menu contestuale, nessun
  `QInputDialog.getText`; il nome cambia solo con `update_ui`.
- **Riferimento Trivium:** `_setup_outliner` intorno a `triviumcad.py:5203-5236`.
- **Fix PenguinCAD:** label con doppio click, `itemDoubleClicked`, menu
  contestuale “Rinomina…”, `_rename_object` con `QInputDialog.getText`,
  `metadata["name"]` + refresh.
- **Test PenguinCAD:** `Test\test_ui_interazione.py`.
- **PASS:** doppio click → un solo dialog; nome aggiornato e persistente;
  Annulla/vuoto invariati; occhio/lucchetto e drag intatti.

### 5. Scala ancorata a Z=0

- **Difetto:** `scale_selection_uniform` scala attorno al centroide; un cubo
  a Z=0..20, scalato, scende a Z=-10.
- **Riferimento Trivium:** `core\scene.py:1478-1503`.
- **Fix PenguinCAD:** `scale_selection_uniform(factor, ancora_z=0.0)`;
  `Z' = (Z-ancora_z)*s + ancora_z`; X/Y attorno al centroide del singolo
  oggetto; undo invariato.
- **Test PenguinCAD:** `Test\test_scene_allineamento.py`.
- **PASS:** Z min 0.0; Z max 40 con scala 2; volume ×8; undo 8000.

### 6. Pannello Proprietà Layer/Shape

- **Difetto:** `PropertiesPanel` è dead code; il pannello destro non mostra
  layer/shape_type; il tutorial promette un pannello che non esiste.
- **Riferimento Trivium:** `PropertiesPanel` intorno a `triviumcad.py:3002`;
  `_create_right_panel` intorno a `3998-4076`; tutorial.
- **Fix PenguinCAD:** gruppo “Proprietà” con `prop_layer`/`prop_shape`,
  sincronizzato alla selezione (singola/multipla/assente); tutorial corretto.
- **Test PenguinCAD:** `Test\test_ui_interazione.py`.
- **PASS:** cubo `Default/box`, cilindro `Supporti/cylinder`, deselezione
  `—/—`, multi-selezione comune o `—`.

### 7. Misura 3D su Z≠0

- **Difetto:** la misura usa solo X/Y e proietta su Z=0; due punti a 10 mm
  sulla faccia Z=20 danno 13.025 mm.
- **Riferimento Trivium:** `_get_sketch_coords`, `_measure_click`,
  `_angle_between` intorno a `triviumcad.py:1482-1529`.
- **Fix PenguinCAD:** `_pick_surface_point` (ray-cast sulla mesh visibile),
  `_get_measure_point` con fallback Z=0 solo sul vuoto, punti `[x,y,z]`,
  distanza/angolo 3D, overlay proiettato.
- **Test PenguinCAD:** `Test\test_misura_3d.py`.
- **PASS:** faccia Z=20 → 10.00 mm; angolo 90°; scala/undo; fallback sul vuoto.

## Test e verifica

- Baseline TriviumCAD: **25/25** (`python -m pytest Test -q`).
- Per ogni fix: test mirato + regressione; `py_compile`.
- GUI reale: `python triviumcad.py`, con click reali.
- Criterio: nessun test declassato; i test nuovi restano permanenti.

## Note di adattamento

- Non copiare `penguincad.py` in blocco: Trivium ha OpenGL 3.3, tema e
  toolbar diversi.
- I nomi cambiano (`triviumcad.py` vs `penguincad.py`); i fix sono funzionali.
- `core\scene.py` di Trivium non ha `measurement_done` né `ancora_z`:
  vanno aggiunti.
- `_invalidate_all_vbos` esiste già in Trivium ma senza `_vbo_pendenti`:
  va completato.
- Non fare push: il repository ha un remoto GitHub, ma la privacy vieta push.

## Riferimenti

- Implementazioni: `10_PROGETTO_PenguinCAD\penguincad.py`,
  `core\scene.py`, `Test\test_picking_e_console.py`,
  `test_measure_overlay.py`, `test_misura_3d.py`,
  `test_ui_interazione.py`, `test_scene_allineamento.py`.
- Documento di allineamento PenguinCAD:
  `10_PROGETTO_PenguinCAD\Documenti\2026-11-22_ALLINEAMENTO_PENGUINCAD.md`.
- Backup PenguinCAD 1.3.1:
  `Backup\PENGUINCAD_20261122-2108_131_FINALE.zip`.

## Stato

- TriviumCAD: **7 fix applicati** il 23/11/2026 sul branch `fix/ereditati-1.3.1`, base `691c7c9`.
- Test: **30/30** (25 esistenti + 5 nuovi in `Test/test_fix_ereditati.py`).
- Commit unico finale; nessun push.
- Report di applicazione: `Documenti/2026-11-23_FIX_EREDITATI_APPLICATI.md`.
