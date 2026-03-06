"""
Covert Hinge - Bitcoin Seed Phrase Concealment Device
FreeCAD Python Macro

USAGE:
    1. Open FreeCAD
    2. Go to Macro > Macros...
    3. Click "Create" and paste this script, or open this file directly
    4. Run the macro with Macro > Run Macro (F6)
    5. The model will be generated in the active document
    6. Export STL via File > Export for 3D printing

DESIGN OVERVIEW:
    A concealed two-part box joined by a recessed barrel hinge. From the
    outside it appears as a solid rectangular block. Opened by pressing
    the spine firmly — the friction fit lid lifts off the body. The inner
    cavity holds a standard seed phrase storage card (85 x 54 mm) or a
    stamped steel plate.

PRINT SETTINGS (recommended):
    Material : PETG or ABS (heat/moisture resistant)
    Layer    : 0.15 mm
    Infill   : 40 % (gyroid)
    Walls    : 4 perimeters
    Supports : None required

SECURITY NOTES:
    - Print in a plain filament colour (black/grey) — avoid metallics
    - Sand exterior smooth and apply matte paint to disguise print lines
    - Store in an ordinary location: bookshelf, tool drawer, junk box
    - Never label, mark, or store near other crypto materials
    - Consider a decoy compartment (false_back = True) holding dummy content
"""

import FreeCAD as App
import FreeCADGui as Gui
import Part
from FreeCAD import Base

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION  — adjust these values before running
# ─────────────────────────────────────────────────────────────

# Outer envelope (mm)
OUTER_W  = 105.0   # width  (X) — slightly wider than a credit card
OUTER_D  =  62.0   # depth  (Y) — slightly deeper than a credit card
OUTER_H  =  24.0   # total height (Z) — body + lid combined

# Wall / floor / ceiling thickness (mm)
WALL_T   =   3.5   # side walls
FLOOR_T  =   3.0   # bottom floor and lid ceiling
HINGE_R  =   2.5   # barrel hinge radius
HINGE_PIN=   1.2   # hinge pin radius (print loose or drill for metal rod)

# Lid height as fraction of total height
LID_FRAC =   0.40  # lid takes 40 % → 9.6 mm; body takes 60 % → 14.4 mm

# False back: thin wall that hides the real cavity behind a shallow decoy
FALSE_BACK       = True
FALSE_BACK_DEPTH =  8.0  # depth (Y) of the visible decoy tray

# Friction-fit lip (press-fit ridge on body, groove on lid)
LIP_H    =  1.5    # height of press-fit lip
LIP_T    =  0.6    # radial thickness (tune for fit: +0.1 tighter, -0.1 looser)

# Hinge count along the spine (left edge, X = 0)
HINGE_COUNT = 3

# ─────────────────────────────────────────────────────────────
#  DERIVED DIMENSIONS
# ─────────────────────────────────────────────────────────────

LID_H    = OUTER_H * LID_FRAC
BODY_H   = OUTER_H - LID_H

INNER_W  = OUTER_W - 2 * WALL_T
INNER_D  = OUTER_D - 2 * WALL_T   # (hinge spine wall is also WALL_T)
INNER_H_BODY = BODY_H - FLOOR_T   # usable cavity depth in body
INNER_H_LID  = LID_H  - FLOOR_T   # usable recess in lid

# Hinge barrel sits in the spine (left wall), centred on the parting line
HINGE_CY = WALL_T / 2             # barrel Y centre (within the spine wall)
HINGE_CZ = BODY_H                 # barrel Z centre at parting line

# Spacing of hinge barrels along X
HINGE_SPACING = OUTER_W / (HINGE_COUNT + 1)

# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def box(w, d, h, x=0, y=0, z=0):
    """Return a solid box placed at (x, y, z)."""
    s = Part.makeBox(w, d, h)
    s.translate(Base.Vector(x, y, z))
    return s

def cylinder(r, h, x=0, y=0, z=0, axis='Z'):
    """Return a cylinder along the given axis, placed at (x, y, z)."""
    s = Part.makeCylinder(r, h)
    if axis == 'X':
        s.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 1, 0), 90)
        s.translate(Base.Vector(x, y, z))
    elif axis == 'Y':
        s.rotate(Base.Vector(0, 0, 0), Base.Vector(1, 0, 0), -90)
        s.translate(Base.Vector(x, y, z))
    else:
        s.translate(Base.Vector(x, y, z))
    return s

# ─────────────────────────────────────────────────────────────
#  BODY  (bottom half)
# ─────────────────────────────────────────────────────────────

def make_body():
    """
    Solid outer shell minus interior cavity.
    The spine (left wall, X = 0) contains the hinge knuckle sockets.
    """
    # Outer shell
    shell = box(OUTER_W, OUTER_D, BODY_H)

    # Main interior cavity
    cavity = box(
        INNER_W, INNER_D, INNER_H_BODY,
        x = WALL_T, y = WALL_T, z = FLOOR_T
    )

    body = shell.cut(cavity)

    # ── False back: subdivide cavity with a thin wall leaving a decoy tray ──
    if FALSE_BACK:
        real_cavity_y = WALL_T + FALSE_BACK_DEPTH + WALL_T
        # Remove real cavity (behind the false back wall)
        real_slot = box(
            INNER_W,
            INNER_D - FALSE_BACK_DEPTH - WALL_T,
            INNER_H_BODY,
            x = WALL_T,
            y = real_cavity_y,
            z = FLOOR_T
        )
        body = body.cut(real_slot)

    # ── Friction-fit lip: a raised ridge around the top rim ──
    # Outer ridge profile box — will be added to the top of the body walls
    lip_outer = box(OUTER_W, OUTER_D, LIP_H, z=BODY_H)
    lip_inner = box(
        OUTER_W - 2 * (WALL_T - LIP_T),
        OUTER_D - 2 * (WALL_T - LIP_T),
        LIP_H,
        x = WALL_T - LIP_T,
        y = WALL_T - LIP_T,
        z = BODY_H
    )
    lip = lip_outer.cut(lip_inner)
    body = body.fuse(lip)

    # ── Hinge knuckles (male barrels protruding from the left spine wall) ──
    for i in range(HINGE_COUNT):
        cx = HINGE_SPACING * (i + 1)
        # The barrel protrudes into the lid's spine recess when assembled
        barrel = cylinder(
            HINGE_R, WALL_T + HINGE_R,   # length: span the spine + small protrusion
            x = cx - HINGE_R,             # barrel along X centred on cx
            y = -HINGE_R,                 # sit flush with outer face of spine
            z = HINGE_CZ - HINGE_R,
            axis='X'
        )
        pin_hole = cylinder(
            HINGE_PIN, WALL_T + HINGE_R + 2,
            x = cx - HINGE_R - 1,
            y = -HINGE_R,
            z = HINGE_CZ - HINGE_PIN / 2,
            axis='X'
        )
        barrel = barrel.cut(pin_hole)
        body = body.fuse(barrel)

    return body

# ─────────────────────────────────────────────────────────────
#  LID  (top half)
# ─────────────────────────────────────────────────────────────

def make_lid():
    """
    Mirror image of body ceiling + hinge sockets to accept body knuckles.
    Shown in open position (rotated 180° around hinge axis = X axis at spine).
    """
    # Outer shell
    shell = box(OUTER_W, OUTER_D, LID_H)

    # Interior recess (faces down when closed, so cavity on -Z side)
    recess = box(
        OUTER_W - 2 * (WALL_T - LIP_T) - 0.2,   # 0.2 mm clearance for lip
        OUTER_D - 2 * (WALL_T - LIP_T) - 0.2,
        LIP_H + 0.5,                               # capture the lip + clearance
        x = WALL_T - LIP_T + 0.1,
        y = WALL_T - LIP_T + 0.1,
        z = 0
    )
    lid = shell.cut(recess)

    # Ceiling cavity (storage space inside lid)
    lid_cavity = box(
        INNER_W, INNER_D, INNER_H_LID,
        x = WALL_T, y = WALL_T, z = LIP_H + 0.5
    )
    lid = lid.cut(lid_cavity)

    # ── Hinge sockets (female) in the spine of the lid ──
    for i in range(HINGE_COUNT):
        cx = HINGE_SPACING * (i + 1)
        socket = cylinder(
            HINGE_R + 0.3,           # 0.3 mm clearance around barrel
            WALL_T + HINGE_R + 0.5,  # depth to accept full barrel length
            x = cx - HINGE_R - 0.15,
            y = -HINGE_R - 0.3,
            z = 0 - HINGE_R - 0.3,   # z=0 is the bottom of lid (parting plane)
            axis='X'
        )
        pin_slot = cylinder(
            HINGE_PIN + 0.2,
            WALL_T + HINGE_R + 2,
            x = cx - HINGE_R - 1,
            y = -HINGE_R - 0.3,
            z = 0 - HINGE_PIN / 2 - 0.1,
            axis='X'
        )
        socket = socket.fuse(pin_slot)
        lid = lid.cut(socket)

    return lid

# ─────────────────────────────────────────────────────────────
#  HINGE PIN  (steel rod or printed pin — print slightly undersized)
# ─────────────────────────────────────────────────────────────

def make_pin(index):
    """Single hinge pin for barrel i."""
    cx = HINGE_SPACING * (index + 1)
    pin = cylinder(
        HINGE_PIN - 0.1,             # 0.1 mm clearance for smooth rotation
        WALL_T + HINGE_R,
        x = cx - HINGE_R,
        y = -HINGE_R,
        z = HINGE_CZ - HINGE_PIN / 2,
        axis='X'
    )
    return pin

# ─────────────────────────────────────────────────────────────
#  ASSEMBLE AND ADD TO FREECAD DOCUMENT
# ─────────────────────────────────────────────────────────────

def main():
    doc_name = "CovertHinge_BitcoinSeedVault"

    # Create or reuse document
    if doc_name in [d.Name for d in App.listDocuments().values()]:
        doc = App.getDocument(doc_name)
        # Clear old objects
        for obj in doc.Objects:
            doc.removeObject(obj.Name)
    else:
        doc = App.newDocument(doc_name)

    print("Building body…")
    body_shape = make_body()
    body_obj = doc.addObject("Part::Feature", "Body")
    body_obj.Shape = body_shape
    body_obj.Label = "Body (bottom)"
    body_obj.ViewObject.ShapeColor = (0.25, 0.25, 0.25)   # dark grey

    print("Building lid…")
    lid_shape = make_lid()
    # Position lid above body for display (open position)
    lid_shape.translate(Base.Vector(0, 0, BODY_H + LID_H + 5))
    lid_obj = doc.addObject("Part::Feature", "Lid")
    lid_obj.Shape = lid_shape
    lid_obj.Label = "Lid (top)"
    lid_obj.ViewObject.ShapeColor = (0.30, 0.30, 0.30)

    print("Building hinge pins…")
    for i in range(HINGE_COUNT):
        pin_shape = make_pin(i)
        pin_obj = doc.addObject("Part::Feature", f"HingePin_{i+1}")
        pin_obj.Shape = pin_shape
        pin_obj.Label = f"Hinge Pin {i+1}"
        pin_obj.ViewObject.ShapeColor = (0.75, 0.75, 0.80)   # steel-ish

    doc.recompute()

    # Fit view
    try:
        Gui.activeDocument().activeView().fitAll()
        Gui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass  # headless mode — skip GUI calls

    # Print summary
    print("\n" + "="*56)
    print("  COVERT HINGE — BITCOIN SEED VAULT")
    print("="*56)
    print(f"  Outer envelope   : {OUTER_W} × {OUTER_D} × {OUTER_H} mm")
    print(f"  Body height      : {BODY_H:.1f} mm")
    print(f"  Lid height       : {LID_H:.1f} mm")
    print(f"  Cavity (body)    : {INNER_W:.1f} × {INNER_D:.1f} × {INNER_H_BODY:.1f} mm")
    print(f"  False back       : {'YES — decoy tray ' + str(FALSE_BACK_DEPTH) + ' mm deep' if FALSE_BACK else 'NO'}")
    print(f"  Hinge barrels    : {HINGE_COUNT} × ø{HINGE_R*2:.1f} mm")
    print(f"  Pin diameter     : ø{HINGE_PIN*2:.1f} mm (use M2.4 steel pin)")
    print("="*56)
    print("  Parts exported to document:", doc_name)
    print("  Export each Part as STL:")
    print("    File ▸ Export ▸ select Body / Lid / Pins → .stl")
    print("="*56)

    return doc


if __name__ == "__main__":
    main()
