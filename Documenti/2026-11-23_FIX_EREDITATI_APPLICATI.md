# Fix ereditati da PenguinCAD — applicazione su TriviumCAD

**Data:** 23/11/2026
**Branch:** `fix/ereditati-1.3.1`, base `691c7c9` (`main`)
**Stato:** 7/7 fix applicati, 30/30 test, GUI avviata senza errori; commit unico; nessun push.

## Riepilogo

| # | Fix | File | Esito |
|---:|---|---|---|
| 1 | Picking oggetti nascosti | `triviumcad.py` `_pick_object`, `_select_objects_in_box` | esclusi `visible=False` |
| 2 | Console e cache GL | `triviumcad.py` `_invalidate_all_vbos`, `_svuota_vbo_pendenti`, `paintGL`, `ConsoleDialog` | cache invalidata dopo `exec`/`eval`; VBO cancellati nel frame |
| 3 | Valore nell'overlay misura | `triviumcad.py` `_testo_misura`, `_draw_measurement_overlay`, `_measure_click`; `core/scene.py` | badge mm/° persistente, `measurement_done` |
| 4 | Rinomina dall'outliner | `triviumcad.py` `_OutlinerNameLabel`, `_rename_object`, menu contestuale | doppio click e “Rinomina…” |
| 5 | Scala ancorata a Z=0 | `core/scene.py` `scale_selection_uniform(factor, ancora_z=0.0)` | base ferma a Z=0 |
| 6 | Pannello Proprietà Layer/Shape | `triviumcad.py` `_create_right_panel`, `_sync_property_fields`; `TUTORIAL.md` | gruppo Proprietà sincronizzato |
| 7 | Misura 3D su Z≠0 | `triviumcad.py` `_pick_surface_point`, `_get_measure_point`, `_angle_between` | ray-cast 3D, fallback Z=0 |

## Dettaglio

### 1. Picking oggetti nascosti

- `_pick_object`: dopo il controllo del layer, salta gli oggetti con
  `metadata["visible"] is False`.
- `_select_objects_in_box`: la lista da testare esclude gli stessi oggetti.
- L’oggetto resta in scena, nell’outliner e fuori dall’export.

### 2. Console e cache GL

- `_invalidate_all_vbos` rimuove tutte le chiavi cache (`_gl_verts`,
  `_gl_normals`, `_gl_vbo_verts`, `_gl_vbo_normals`, `_gl_vbo_count`) e
  accumula gli id VBO in `_vbo_pendenti`.
- `_svuota_vbo_pendenti` cancella i VBO nel `paintGL`, con contesto corrente.
- `ConsoleDialog` invalida le cache dopo `exec`/`eval`, prima di `update()`.

### 3. Valore nell’overlay misura

- `_testo_misura`: distanza 3D in mm, angolo al vertice in gradi.
- Badge disegnato sopra il segmento o vicino al vertice, con sfondo scuro e
  bordo ambra.
- `measurement_done` impedisce click successivi; la misura resta finché Esc o
  una nuova misura. `measure_distance`/`measure_angle` resettano lo stato.

### 4. Rinomina dall’outliner

- `_OutlinerNameLabel` emette `doubleClicked` e accetta l’evento.
- `_rename_object` usa `QInputDialog.getText`; aggiorna solo `metadata["name"]`
  e l’outliner. Annulla o testo vuoto non cambiano nulla.
- Menu contestuale “Rinomina…” sull’item.

### 5. Scala ancorata a Z=0

- `scale_selection_uniform(factor, ancora_z=0.0)`.
- X/Y attorno al centroide dell’oggetto; Z attorno al piano di ancoraggio:
  `z' = (z - ancora_z) * s + ancora_z`.
- Validazione del piano; undo invariato.

### 6. Pannello Proprietà Layer/Shape

- Gruppo “Proprietà” tra Testo 3D e Parametri, con `prop_layer` e `prop_shape`.
- `_sync_property_fields`: nessuna selezione `—/—`; singola selezione
  layer/shape; multipla il valore comune o `—`.
- Tutorial aggiornato in `TUTORIAL.md` e nel tutorial integrato.

### 7. Misura 3D su Z≠0

- `_pick_surface_point`: ray-cast sulla mesh dell’oggetto visibile più vicino.
- `_get_measure_point`: superficie colpita, fallback al piano Z=0 solo sul vuoto.
- Punti `[x, y, z]`; distanza e angolo 3D; overlay proiettato con `gluProject`.

## Test

- Baseline pre-fix: **25/25**.
- Post-fix: **30/30** (`python -m pytest Test -q`, 1,67 s).
- Nuovi test permanenti in `Test/test_fix_ereditati.py`:
  - scala ancorata a Z=0 (Z min 0, Z max 40, volume ×8);
  - ancora esplicita a Z=20;
  - reset di `measurement_done` con `measure_distance`;
  - angolo 3D su piano Z=20 (90°);
  - testo overlay “10.00 mm” e “90.0°”.
- `py_compile` su `triviumcad.py` e `core/scene.py`: OK.
- GUI: `python triviumcad.py` avviata e chiusa; solo warning font non installati
  (`Bergstena Decorated`, `Hillside Calligraphy`), preesistenti.

## Collaudo GUI reale — 7/7 PASS

Harness: `Test/collaudi/2026-11-23_FIX_EREDITATI/harness_fix_ereditati.py`.
Avvia la vera `CADWindow`, mostra la finestra e pilota i widget con QTest.
Esiti: `esiti_fix_ereditati.json`.

| Test | Evidenza |
|---|---|
| 1. Picking nascosti | click sul nascosto: 0 selezioni; click sul visibile: 1; box-select: solo il visibile |
| 2. Console/cache GL | `obj.apply_scale(0.5)`: volume 8000 → 1000; cache `_gl_*` assenti subito dopo l’exec |
| 3. Overlay misura | badge “9.87 mm”, `measurement_done=True`, Esc azzera |
| 4. Rinomina outliner | doppio click, dialog pilotato, nome ed etichetta “Rinominato” |
| 5. Scala Z=0 | Z min **0.0**, Z max 39.619 con fattore 1.981, volume ×7.77 |
| 6. Pannello Proprietà | box `Default/box`, cilindro `Default/cylinder`, deselezione `—/—`, multi `Default/—` |
| 7. Misura 3D | punti a **Z=30.0**, distanza 9.94 mm, badge “9.94 mm” |

**Nota sulla precisione:** i click sono a pixel interi; distanze 9.87/9.94 mm e
fattore 1.981 invece di 2.000 sono l’errore di quantizzazione dello schermo,
entro la tolleranza dichiarata di 0.3 mm. La quota Z resta esatta (0.0 e 30.0)
e l’ancoraggio a Z=0 è esatto.

## Limiti

- L’harness copre i sette comportamenti con click reali; non sostituisce una
  sessione manuale esplorativa su casi limite (mesh importate, layer nascosti,
  misure su geometrie concave).

## Backup

- Pre-fix: `Backup/TRIVIUMCAD_20261123_PRE_FIX.zip` — 50 file, 275,5 MB,
  SHA256 `96BC5132015F98AF1213FE39BC7428446A26C5B059F583020BBD01081989388C`.

## Commit

Unico commit sul branch `fix/ereditati-1.3.1`; nessun push al remoto.
