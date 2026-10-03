# 2PenAxE — Icona custom + Mockup UX (report del 03/10/2026)

Progetto: TriviumCAD — funzione "2PenAxE" (sketch 2D multi-piano)
Zona di scrittura rispettata: `Immagini\` (icone) e `Documenti\` (mockup). Nessun file di codice toccato.

> Nota di conformità: la cartella `Report/` del laboratorio non esiste nel progetto TriviumCAD né nella root `Esperimento/`. Per non uscire dal perimetro concesso dall'incarico, questo report è depositato in `Documenti\` con nome datato.

---

## 1. File creati (verificati su disco)

| File | Dimensioni | Peso | Note |
|------|-----------|------|------|
| `Immagini\2penaxe_icon.svg` | viewBox 0 0 512 512 | 3.081 byte | vettoriale, scritto a mano |
| `Immagini\2penaxe_64.png` | 64×64 px | 1.833 byte | RGBA, trasparenza reale (alpha 0–255) |
| `Immagini\2penaxe_256.png` | 256×256 px | 5.071 byte | RGBA, trasparenza reale |
| `Immagini\2penaxe_512.png` | 512×512 px | 11.448 byte | RGBA, trasparenza reale |
| `Documenti\2penaxe_mockup.png` | 1600×900 px | 76.511 byte | RGB, mockup modale completo |
| `Documenti\2penaxe_anteprima_icone.png` | 660×250 px | 14.882 byte | tavola di leggibilità 128/64/32/28 px + su pulsante |

**Verifica tecnica PNG (PIL):** dimensioni e modalità riportate in tabella; canale alpha con minimo 0 e massimo 255 su tutti e tre i formati (trasparenza piena, non sfondo bianco). Bounding box del contenuto: 64→(9,8,56,59), 256→(37,35,219,234), 512→(74,70,438,468). Ispezione visiva effettuata: leggibile a 64 px e a 28–32 px.

**Render:** `QSvgRenderer` + `QPainter` (PyQt5, offscreen), antialiasing attivo, `Format_ARGB32` riempito di trasparente.

---

## 2. Icona — scelte di design

Rebus letterale deciso da N47:
- **foglio millimetrato** scuro con griglia tenue (griglia disegnata come linee esplicite, non pattern, per compatibilità piena col renderer SVG);
- **una penna al centro** = la lama: corpo bianco `#dde6f5` con feritoia ambra `#f0b429`, fondello in ottone, punta metallica `#9fb3cc`;
- **manico d'ascia** in ottone `#b87333`/`#d4944a` che attraversa il foglio in asse con la penna e **sporge sotto**, con ghiera e puntale: l'occhio ricompone l'ascia (lama-penna sopra, asta-manico sotto).

Colori da `STANDARD_VISIVO.md`: foglio `#10243F`, griglia `rgba(120,160,220,0.18)` / `0.32` per le linee principali, bordo foglio `rgba(120,160,220,0.55)`. Sfondo trasparente (adatta anche a pulsante scuro, verificato nell'anteprima).

Osservazione onesta: a colpo d'occhio la composizione può leggersi anche come "martello" (penna orizzontale + manico). È fedele al rebus richiesto; se N47 desidera una lettura "ascia" più esplicita, è pronta la variante con penna inclinata — da concordare, nessuna iniziativa presa.

---

## 3. Mockup UX — scelte di design

Modale 1600×900 su standard scuro, sfondo `#0C1E36` con due glow radiali tenui (ambra alto-destra, verde basso-sinistra) e ombra morbida. Zone, tutte etichettate con 10 richiami numerati:

1. **Titolo + icona** — header con icona 46 px, titolo ambra, bordo ottone, X di chiusura.
2. **Strumenti di disegno (8)** — linea, polilinea, rettangolo, cerchio, arco, selezione/sposta, gomma, misure; "Linea" attiva (fondo ambra 14%, bordo ambra).
3. **Viste standard** — Alto / Fronte / Lato / Isometrica (attiva).
4. **Selettore piano** — segmented XY | XZ | YZ, piano attivo in ambra.
5. **Vista orbitabile** — griglia millimetrata, assi colorati (X ambra, Y verde CRT, Z blu `#5ba3e6`), mini-cubo di orientamento in basso.
6. **Controlli vista 3D** — Rotazione 360°, Zoom, Pan, con icone a linee.
7. **Misure live** — quote 120.00 / 80.00 / R 25.00 (pannello A) e 96.40 / 45.0° (pannello B) in pillole scure, stile CAD.
8. **Ancore selezionabili** — checkbox: Endpoint, Midpoint, Centri, Intersezioni, Assi, Origine, Griglia (4 attive); barra riepilogo "4 / 7".
9. **OK · Annulla · Applica** — OK ambra con testo scuro, Applica a bordo ambra.
10. **Coordinate & snap** — status per pannello con coordinate cursore e LED "Snap ON".

I due pannelli (A: piano XY, B: piano XZ) mostrano contenuti diversi per far vedere il comportamento multi-piano. Tipografia: Segoe UI (titoli/testi), Consolas (dati/misure/coordinate) — coerente col carattere tecnico del laboratorio.

---

## 4. Vincoli rispettati

- Nessun file di codice o di altri progetti toccato; scritture solo in `Immagini\` e `Documenti\`.
- Tutto in italiano; nessun JSON/stack trace esposto; WYSIWYG.
- Rigore: ogni passaggio verificato su disco (render, dimensioni, modalità, bbox, ispezione visiva).

## 5. Prossimi passi (a cura di N47)

1. Ispezione visiva dei file (mockup e anteprima leggibilità).
2. Eventuali correzioni o varianti (es. lettura "ascia" più esplicita, doppia penna).
3. Backup solo dopo approvazione esplicita (Regola 7).

---

## 6. Revisione v2 — variante "ascia" (03/10/2026)

Su scelta di N47: penna **inclinata** = lama dell'ascia bipenne, manico ottone che sporge sotto. La v1 (penna dritta) **non è stata cancellata**: conservata come `2penaxe_icon_v1_penna-dritta.svg` (SHA256 `727C4E65…`), `2penaxe_512_v1_penna-dritta.png` (SHA256 `03ADE12C…`) e `2penaxe_anteprima_icone_v1_penna-dritta.png`.

### File ufficiali aggiornati (v2, verificati su disco)

| File | Dimensioni | Peso | Note |
|------|-----------|------|------|
| `Immagini\2penaxe_icon.svg` | viewBox 0 0 512 512 | 3.263 byte | penna ruotata −36° |
| `Immagini\2penaxe_64.png` | 64×64 px | 3.085 byte | RGBA, alpha 0–255 |
| `Immagini\2penaxe_256.png` | 256×256 px | 13.142 byte | RGBA, alpha 0–255 |
| `Immagini\2penaxe_512.png` | 512×512 px | 21.364 byte | RGBA, alpha 0–255, bbox (74,70,438,456) |
| `Documenti\2penaxe_anteprima_icone.png` | 660×250 px | 20.281 byte | 128/64/32/28 px + pulsante blu bordato ambra |

### Scelte di design v2

- Penna ruotata di −36°, punta metallica in basso a sinistra (il **filo** della scure), fondello ottone a **cuneo** (controlama → lettura bipenne), corpo più tozzo (46 px) con feritoia ambra.
- Manico più massiccio (36 px), innesto a ~70% della penna (lama lunga, corno corto), ghiera e puntale in basso.
- Foglio millimetrato, griglia, colori e sfondo trasparente invariati.

### Verifiche

- PIL: dimensioni, modalità RGBA, alpha 0–255, bbox su 64/256/512; ispezione visiva a 28–32 px (crop ×8): silhouette leggibile.
- Nota tecnica: durante l'aggiornamento l'anteprima v1 era aperta in `Photos.exe` (lock in scrittura); risolta rinominando il file (conservato come v1) e ricopiando il nuovo — nessun intervento sul processo dell'utente.

### Prossimi passi

1. Ispezione visiva della v2 e dell'anteprima aggiornata.
2. Eventuali correzioni; backup solo dopo approvazione esplicita (Regola 7).

---

## 7. Revisione v3 — "foglio landscape + penna verticale" (03/10/2026)

Su specifica esatta di N47: foglio millimetrato **in orizzontale** (lato lungo come base), **penna in verticale nel mezzo del foglio**, che **sporge dal lato lungo** creando l'illusione di un'ascia.

### Scelta di orientamento (e perché)

- **Punta in alto**, rivolta verso il bordo superiore del foglio ma **senza superarlo** (13 px di margine su 512): così la penna ha **una sola sporgenza, quella inferiore** → testa (foglio) in alto, manico (penna) in basso, come un'ascia reale.
- Scartata la punta in basso: la parte sporgente sarebbe stata la punta appuntita, che non legge come manico.
- La penna è disegnata **davanti** al foglio: resta riconoscibile (punta, sezione ambra, fusto, anelli, fondello ottone) e a 28–32 px la silhouette esterna è "rettangolo + asta" = ascia.

### Mockup ASCII

```
      ┌────────────────────────────────────────┐
      │┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ │  ← foglio millimetrato landscape
      │┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ╷ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ │     (384×192, lato lungo = base)
      │┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ▲ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ │
      │┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ▓ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ │  ← penna verticale al centro
      │┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ▓ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ ┼ │     (punta in alto, dentro il foglio)
      └─────────────────▓──────────────────────┘
                        ▓                        ← sporge sotto = MANICO d'ascia
                        ▓
                        ●                        ← fondello ottone (pomello)
```

### File ufficiali v3 (verificati su disco)

| File | Dimensioni | Peso | SHA256 (primi 16) |
|------|-----------|------|-------------------|
| `Immagini\2penaxe_icon.svg` | viewBox 0 0 512 512 | 3.664 byte | `2bb50e2aeac7800d` |
| `Immagini\2penaxe_64.png` | 64×64 px | 1.393 byte | `ce7773333822c876` |
| `Immagini\2penaxe_256.png` | 256×256 px | 4.724 byte | `e6e4d78dfa5b2610` |
| `Immagini\2penaxe_512.png` | 512×512 px | 9.868 byte | `e235ba69a463f2c3` |
| `Documenti\2penaxe_anteprima_icone.png` | 660×250 px | 20.886 byte | `7f1e0ec198544106` |

### Conservazione versioni

- v1 già conservata: `2penaxe_icon_v1_penna-dritta.svg`, `2penaxe_512_v1_penna-dritta.png`, `2penaxe_anteprima_icone_v1_penna-dritta.png`.
- v2 conservata in questa revisione: `2penaxe_icon_v2_ascia-inclinata.svg`, `2penaxe_64_v2_ascia-inclinata.png`, `2penaxe_256_v2_ascia-inclinata.png`, `2penaxe_512_v2_ascia-inclinata.png`, `2penaxe_anteprima_icone_v2_ascia-inclinata.png` (copie fedeli: pesi identici agli originali).

### Verifiche PIL

- `2penaxe_64.png`: 64×64 RGBA, alpha 0..255, bbox (7, 7, 57, 57).
- `2penaxe_256.png`: 256×256 RGBA, alpha 0..255, bbox (31, 31, 225, 226).
- `2penaxe_512.png`: 512×512 RGBA, alpha 0..255, bbox (62, 62, 450, 451): il contenuto non supera mai il bordo superiore del foglio → nessuna sporgenza sopra, la sporgenza è solo sotto (manico).
- Anteprima: 660×250 RGB (128/64/32/28 px + pulsante blu bordato ambra).
- Leggibilità a 28 px: crop ×8 ispezionato: testa rettangolare scura + manico chiaro/ottone → lettura "ascia" leggibile; a 128/64 px si distinguono punta, sezione ambra e anelli.

### Note tecniche

- Geometria: foglio 384×192 (2:1) centrato; penna con fusto 46 px, punta a 13 px dal bordo superiore; sporgenza sotto il lato lungo 194 px.
- Bordo foglio portato a `rgba(120,160,220,0.7)` (v2: 0.55) per mantenere leggibile la testa dell'ascia a 28 px su fondo scuro. Griglia `rgba(120,160,220,0.18)`/`0.32`, fondo `#10243F`, penna `#dde6f5`/`#f0b429`, ottone `#b87333`/`#d4944a`, sfondo trasparente: invariati da precetto.
- Nessun file di codice o di altri progetti toccato.

### Prossimi passi

1. Ispezione visiva della v3 e dell'anteprima aggiornata.
2. Eventuali correzioni; backup solo dopo approvazione esplicita (Regola 7).
