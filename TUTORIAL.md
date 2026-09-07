# Tutorial TriviumCAD

Guida all'uso di **TriviumCAD** — CAD 3D parametrico/mesh gratuito per stampa 3D (v1.2.0).

---

## 1. Avvio

1. Installa le dipendenze (vedi `README.md` → Installazione).
2. Avvia con:

   ```bash
   python triviumcad.py
   ```

3. All'avvio compare lo splash screen e poi il **tutorial** (11 pagine, navigabile
   con **← Indietro / Avanti →** e menu a tendina in alto). Puoi spuntare
   *"Nascondi all'avvio"*: lo ritrovi da **Opzioni → Tutorial** o **Aiuto**.
4. Se avvii l'eseguibile installato (`TriviumCAD.exe`), il doppio clic su un file
   **.n47** apre direttamente la scena salvata.

### Convenzione spaziale

- **Rosso = Destra** (asse X, larghezza)
- **Verde = Dietro** (asse Y, profondità; fronte utente = −Y)
- **Blu = Sopra** (asse Z, altezza)

## 2. Interfaccia

| Zona | Contenuto |
|---|---|
| **Toolbar (in alto)** | Da 2 a 3D, Nuovo/Apri/Salva, Booleane, Guscio, Snap, Magneti, donazioni, sito |
| **Pannello sinistro** | Forme primitive (griglia), Meccanica (Filettatura, Affetta, Arrotonda), CAM |
| **Pannello destro** | Testo 3D, Parametri (posizione/rotazione), Analisi mesh |
| **Outliner (destra)** | Elenco oggetti con layer; clic per selezionare, Ctrl+clic per multi-selezione |
| **Proprietà** | Con un oggetto selezionato: volume, coordinate, dimensioni, stato mesh |

Comandi di vista: **Rotella** = zoom · **Ctrl + SX + Drag** = orbita 360° ·
**Centrale + Drag** = pan · **Ctrl + Centrale + Drag** = rotazione asse Z.

## 3. Primi passi (flusso completo)

1. **Crea un cubo**: pannello sinistro → pulsante **Cubo**.
2. **Aggiungi un cilindro** e spostalo: trascinalo con il mouse, oppure usa il
   **GIZMO** (bianco = sposta su XY, grigio verticale = sposta su Z).
3. **Booleana**: seleziona i 2 oggetti (Shift+Click o box select) → toolbar
   **Sottrazione** (il primo toglie il secondo) o **Unione**.
4. **Filettatura**: seleziona un cilindro → pannello Meccanica → *Filettatura*:
   Tipo **Esterna**, Modalità **Metrico**, Passo 1.5 → **Applica**.
5. **Export**: menu **File → Esporta** → scegli **STL** (o OBJ/PLY/3MF/GLB).
6. **Invia alla stampante**: menu **File → Stampa 3D** (o pulsante dedicato) →
   scegli profilo stampante, protocollo, IP e credenziali → **Invia**.

## 4. Funzioni per sezione

### 4.1 Import 2D → 3D (con buchi)

Toolbar → **Da 2 a 3D**. Supporta:

- **SVG / DXF**: i poligoni vengono estrusi e uniti (watertight).
- **Immagini** (anche foto di silhouette): binarizzazione, rilevamento contorni,
  estrusione. I contorni interni diventano **buchi** automaticamente
  (finestrini, fori, dettagli interni). Se il disegno è molto complesso viene
  semplificato a ~400 punti per contorno.

### 4.2 Primitive (pannello sinistro)

| Forma | Parametri |
|---|---|
| Cubo | larghezza, altezza, profondità |
| Cilindro | raggio, altezza, sezioni |
| Sfera | raggio, suddivisioni |
| Cono | raggio base, altezza, sezioni |
| Collare | raggio esterno, raggio interno, altezza |
| Esagono | raggio, altezza |
| Spirale | raggio, altezza, giri, spessore |
| Arco | raggio esterno, raggio interno, apertura (°), altezza |
| Scatola vuota | larghezza, altezza, profondità, spessore muro |

### 4.3 Testo 3D (pannello destro)

- **Crea**: scrivi il testo e premi Crea → mesh 3D del testo.
- **Adatta**: proietta il testo sulla superficie esterna della forma selezionata
  (spessore preservato lungo la normale).
- **Bassorilievo**: testo inciso/rilevato sulla superficie.

### 4.4 Booleane

Seleziona 2+ oggetti e scegli in toolbar:

- **Unione** — fonde i solidi.
- **Sottrazione** — il primo oggetto meno i successivi.
- **Intersezione** — parte comune.

Per le mesh difficili la booleana usa fino a 6 livelli di fallback; ogni
operazione è annullabile con **Ctrl+Z**.

### 4.5 Guscio

Seleziona un oggetto → **Guscio** in toolbar: crea la versione cava con lo
spessore di parete richiesto (forme piene o già cave, con base opzionale).

### 4.6 Fillet (Arrotonda)

Pannello sinistro → Meccanica → **Arrotonda**: raggio e applica. Gli spigoli
vivi vengono arrotondati con smoothing Taubin pesato (volume quasi invariato,
facce piatte preservate). Applicabile più volte senza esplosione geometrica.

### 4.7 Filettatura

Pannello sinistro → Meccanica → **Filettatura**:

| Parametro | Opzioni |
|---|---|
| **Tipo** | Interna (incisa nel foro) · Esterna (volume aggiunto) |
| **Modalità** | Auto (profilo) · Metrico (passo in mm) · UNF / UNC (passo in TPI, convertito in mm) · Gas |
| **Profilo** | Filo (ISO 60°) · Trapezio · Arrotondato |
| **Passo** | distanza tra creste in mm (o TPI per UNF/UNC) |
| **Profondità** | profondità della valle del filetto |

Su **7 forme native** (cilindro, sfera, cono, box, esagono, arco e donut —
quest'ultimo non più esposto nell'interfaccia ma ancora gestito dal core) la
filettatura segue il **profilo reale della superficie** (raggio calcolato punto
per punto), non il bounding box; collare e scatola vuota hanno raggio reale
dedicato nella filettatura interna. Per le forme importate il filetto viene
inciso radialmente sulla mesh.

### 4.8 Slice (Affetta)

Pannello sinistro → **Affetta**: scegli asse, offset e numero di pezzi:
il modello viene tagliato in fette separate.

### 4.9 CAM

Pannello sinistro → **CAM**: genera percorsi utensile **adattivi zig-zag**
(diametro utensile, passo laterale, quota di sicurezza, avanzamento) sulla forma
selezionata.

### 4.10 Gizmo

Alla selezione compaiono le maniglie:

- **Bianco (centro)** — sposta su XY (segue il mouse 1:1)
- **Grigia verticale** — sposta su Z
- **Gialla diagonale** — scala uniforme
- **Assi colorati** — scala lungo l'asse singolo
- **Cerchi gialli (goniometro)** — al passaggio del mouse sugli assi: trascina
  per ruotare (tacche ogni 15°, grandi ogni 45°)
- **Maniglie facce (6)** — al centro di ogni faccia del bounding box: trascina
  per **allungare/accorciare metà forma** dal centro (es. stirare un tubo
  mantenendo la sezione tonda)

### 4.11 Selezione

- **Click** — seleziona un oggetto (deseleziona gli altri)
- **Shift+Click / Ctrl+Click** — aggiungi/togli dalla selezione
- **SX + Drag** sullo sfondo — **box select** (rettangolare); **Shift + box** aggiunge
- **Click vuoto** — deseleziona tutto
- **Tasto destro** — menu contestuale (Duplica, Elimina, Raggruppa, Allinea a Z=0)

### 4.12 Undo/Redo

Ogni operazione è annullabile: **Ctrl+Z** annulla, **Ctrl+Y** (o **Ctrl+Shift+Z**)
ripristina. Memoria fino a **50 passi**.

### 4.13 Console Python integrata

In basso a destra: console con **eval** su ambiente live:
`scene`, `gl`, `selected` (oggetti selezionati), `obj` (selezione singola),
`np`, `trimesh`. Esempio:

```python
obj.apply_translation([10, 0, 0])
selected[0].metadata["name"]
```

Le frecce **↑/↓** richiamano la cronologia dei comandi.

### 4.14 Profili stampante e protocolli

Menu **File → Stampa 3D**: scegli il modello (12 profili precaricati) e il
protocollo (8 voci: 7 protocolli diretti + *"solo esporta"*):

| Protocollo | Uso |
|---|---|
| Bambu Lab MQTT+FTP | IP + Access Code; upload FTP e avvio stampa via MQTT (TLS) |
| Creality HTTP | IP; API WiFi (K1, K1 Max) |
| PrusaLink | IP + API key; REST su rete locale |
| OctoPrint | IP + API key; universale via Raspberry Pi |
| FTP | IP + credenziali; copia file su server/stampante |
| SMB | Percorso di rete (es. `//192.168.1.100/share`) |
| Anycubic Cloud | Email + password; upload cloud |
| Solo esporta | Export con impostazioni del profilo, senza inviare |

Impostazioni di stampa: qualità layer (mm), infill %, supporti, adesione al piatto.

### 4.15 Misura e scala

- **Ctrl+M** — misura distanza: clicca **2 punti** sulla scena; si apre il popup
  **"Misura — Scala forma"** con il valore misurato. Inserendo un nuovo valore
  la forma selezionata viene scalata in **modo uniforme e centrato** (annullabile
  con Ctrl+Z).
- **Ctrl+Shift+M** — misura angolo: clicca **3 punti**; il valore appare nella
  status bar.
- **Esc** annulla una misurazione in corso.

### 4.16 Menu Modifica

Menu **Modifica** (barra dei menu):

| Voce | Funzione |
|---|---|
| **Chamfer…** | Smusso degli spigoli della forma selezionata. |
| **Pattern lineare…** | Copie lungo una direzione con distanza e numero di copie. |
| **Pattern circolare…** | Copie in cerchio attorno a un asse. |
| **Specchia (Mirror X/Y/Z)** | Riflessione della forma lungo l'asse scelto. |

### 4.17 Menu Mesh

Menu **Mesh** (barra dei menu):

| Voce | Funzione |
|---|---|
| **Smooth…** | Levigatura della mesh. |
| **Subdivide…** | Suddivisione delle facce (maggiore dettaglio). |
| **Decimate…** | Riduzione del numero di facce. |
| **Ripara** | Ricostruzione di mesh non watertight (riparazione mesh). |

## 5. Scorciatoie da tastiera

| Tasto | Azione |
|---|---|
| `Ctrl+Z` | Annulla |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Ripristina |
| `Ctrl+A` | Seleziona tutto |
| `Ctrl+D` | Deseleziona tutto |
| `X` / `C` / `V` | Taglia / Copia / Incolla (senza Ctrl) |
| `Canc` (Del) | Elimina selezionati |
| `Esc` | Deseleziona |
| `Spazio` | Allinea oggetti a Z = 0 |
| *(menu Modifica → Pattern lineare…)* | Pattern lineare (nessuna scorciatoia) |
| *(menu Modifica → Pattern circolare…)* | Pattern circolare (nessuna scorciatoia) |
| `Ctrl+M` | Misura distanza (2 clic) |
| `Ctrl+Shift+M` | Misura angolo (3 clic) |
| `Ctrl + SX + Drag` | Orbita camera |
| `Ctrl + Centrale + Drag` | Rotazione camera su Z |

## 6. Risoluzione problemi

### Il server stampante non è raggiungibile

1. Verifica che stampante e PC siano sulla **stessa rete** (ping dall'IP indicato).
2. Controlla IP, porta e **credenziali** (Access Code Bambu, API key PrusaLink/
   OctoPrint) nel dialogo di connessione.
3. Per Bambu: l'Access Code si legge dal menu *Impostazioni → Rete* della stampante.
4. Per OctoPrint: API key in *Impostazioni → API*; la stampa si avvia solo con
   server attivo.
5. Per SMB: il percorso deve essere raggiungibile (es. `//192.168.1.100/share`)
   e scrivibile dall'utente indicato (opzionale).
6. Se il problema resta: usa **"Solo esporta"** e trasferisci il file con
   l'app/scheda della stampante.

### La mesh non è watertight (booleane o export non riescono)

1. **Verifica**: pannello Analisi → stato mesh (watertight sì/no).
2. **Cause tipiche**: import SVG/DXF con curve aperte, immagini con contorni
   frammentati, booleane su mesh con fori.
3. **Rimedi**:
   - Rigenera la forma nativa (primitive sono sempre chiuse).
   - Usa *Decima/Subdividi* o *Smooth* per ripulire la geometria.
   - Per i buchi automatici usa immagini **binarizzate ad alto contrasto**:
     i contorni devono chiudersi.
   - La booleana ha 6 fallback: se fallisce anche l'ultimo, prova a ridurre
     il numero di oggetti nella selezione o a ruotarli leggermente.
4. Salva spesso il progetto in formato **.n47** (File → Salva come) prima di
   operazioni pesanti.