# Covert Hinge — Bitcoin Seed Vault

A concealed two-part hinged box that holds a standard bitcoin seed phrase
card (85 × 54 mm) or stamped metal plate. From the outside it looks like
an unremarkable rectangular block.

---

## Dimensions

| Feature            | Value                     |
|--------------------|---------------------------|
| Outer envelope     | 105 × 62 × 24 mm          |
| Body height        | 14.4 mm                   |
| Lid height         | 9.6 mm                    |
| Main cavity        | 98 × 55 × 11.4 mm (body)  |
| Decoy tray depth   | 8 mm (false back enabled) |
| Hinge barrels      | 3 × ø5 mm                 |
| Hinge pin          | ø2.4 mm (M2.4 steel rod)  |

---

## How to Generate the 3D Model

1. Install [FreeCAD 0.21+](https://www.freecad.org/downloads.php)
2. Open FreeCAD → **Macro ▸ Macros…**
3. Click **Create**, paste / open `covert_hinge.py`, click **Execute**
4. The document `CovertHinge_BitcoinSeedVault` opens with three parts:
   - **Body** — lower half with cavity and hinge knuckles
   - **Lid** — upper half with recess and hinge sockets
   - **HingePin_1/2/3** — barrel pins (or replace with M2.4 × 18 mm steel pins)
5. Export each part: **File ▸ Export → STL Mesh**

---

## Print Settings

| Setting        | Value                              |
|----------------|------------------------------------|
| Material       | PETG or ABS (avoid PLA — warps)    |
| Layer height   | 0.15 mm                            |
| Infill         | 40 % gyroid                        |
| Wall loops     | 4                                  |
| Supports       | None required                      |
| Orientation    | Body flat-side down; Lid cavity up |

---

## Assembly

```
Parts needed
  • Body (printed)
  • Lid  (printed)
  • 3 × M2.4 × 18 mm stainless steel pin  — or print HingePin parts

Steps
  1. Test-fit body and lid dry — lip should press together firmly.
     Tune LIP_T in covert_hinge.py if fit is too tight or loose.

  2. Align the three hinge barrels (on the body) with the three
     sockets (on the lid spine).

  3. Press or slide the M2.4 steel pins through the aligned barrels.
     A drop of thread-locker on each pin end prevents removal.

  4. Verify the lid opens ~130° and snaps shut with the friction lip.

  5. (Optional) Sand exterior with 220 → 400 grit, apply matte black
     spray paint to eliminate layer lines and finger-print texture.
```

---

## Security Usage

### Placing Seed Phrases
- Write / stamp seed phrase on a metal plate no larger than 85 × 54 × 1 mm
- Place plate inside the **real cavity** (behind the false back wall)
- Fill the **decoy tray** with an innocuous item (business card, coin)

### Concealment Tips
| Location           | Disguise idea                              |
|--------------------|--------------------------------------------|
| Workshop           | Mixed in a hardware parts drawer           |
| Kitchen            | In a utensil junk drawer                  |
| Home office        | Among pens / cable ties in a desk drawer   |
| Storage unit       | Inside a labelled electrical junction box  |

### What to Avoid
- Do **not** mark, label, or brand the exterior
- Do **not** store near other crypto hardware (Ledger, Trezor)
- Do **not** use a shiny or obviously "premium" filament colour
- Do **not** mention this device in a will or digital document by name —
  use a physical letter stored with a trusted attorney

---

## Configuration Reference (`covert_hinge.py`)

| Variable          | Default | Effect                                    |
|-------------------|---------|-------------------------------------------|
| `OUTER_W`         | 105 mm  | Total width                               |
| `OUTER_D`         | 62 mm   | Total depth                               |
| `OUTER_H`         | 24 mm   | Total height (body + lid)                 |
| `WALL_T`          | 3.5 mm  | Wall / floor thickness                    |
| `LID_FRAC`        | 0.40    | Lid fraction of total height              |
| `FALSE_BACK`      | True    | Enable decoy tray                         |
| `FALSE_BACK_DEPTH`| 8 mm    | Depth of visible decoy tray               |
| `LIP_T`           | 0.6 mm  | Friction-fit lip thickness (tune for fit) |
| `HINGE_COUNT`     | 3       | Number of hinge barrels                   |
| `HINGE_R`         | 2.5 mm  | Barrel radius                             |
| `HINGE_PIN`       | 1.2 mm  | Pin radius (use M2.4 steel rod)           |
