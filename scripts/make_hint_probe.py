"""Build tiny fonts that move one rectangle by a known per-ppem shift, to test rasterizers.

Each font maps "A" to a 400 x 500-unit rectangle. The fonts differ only in how the
rectangle is moved at 10-20 ppem:

- HangyeolProbe-Up8: the Hangul shift of the real fonts (prep table, storage slot, fpgm
  function with SHPIX + SHZ, from ``add_ppem_shift_hints``), +1/8 px.
- HangyeolProbe-Up32: the same, +1/2 px.
- HangyeolProbe-Down8: the same, -1/8 px.
- HangyeolProbe-Direct8: every point touched (MDAP) and moved with SHPIX straight in the
  glyph program, with no storage, function or SHZ, +1/8 px.
- HangyeolProbe-None: no instructions.

``tools/render-windows`` renders them with DirectWrite and reports how far each one moved.

Usage: uv run python scripts/make_hint_probe.py [OUT_DIR]
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import ttProgram

from hangyeol_code.builder import add_ppem_shift_hints

PPEMS = range(10, 21)
BOX = (100, 100, 500, 600)
PROBES = {
    "Up8": 0.125,
    "Up32": 0.5,
    "Down8": -0.125,
    "Direct8": 0.125,
    "None": 0.0,
}


def build(name: str, shift: float) -> FontBuilder:
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "space", "box"])
    fb.setupCharacterMap({0x20: "space", 0x41: "box"})
    glyphs = {}
    for glyph_name in (".notdef", "space", "box"):
        pen = TTGlyphPen(None)
        if glyph_name == "box":
            x0, y0, x1, y1 = BOX
            pen.moveTo((x0, y0))
            pen.lineTo((x0, y1))
            pen.lineTo((x1, y1))
            pen.lineTo((x1, y0))
            pen.closePath()
        glyphs[glyph_name] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({".notdef": (600, 0), "space": (600, 0), "box": (600, BOX[0])})
    fb.setupHorizontalHeader(ascent=1020, descent=-300)
    family = f"Hangyeol Probe {name}"
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=1020, sTypoDescender=-300, usWinAscent=1020, usWinDescent=300)
    fb.setupPost(isFixedPitch=1)
    fb.setupMaxp()
    font = fb.font
    for tag in ("fpgm", "prep"):
        table = newTable(tag)
        table.program = ttProgram.Program()
        table.program.fromBytecode(b"")
        font[tag] = table
    gasp = newTable("gasp")
    gasp.gaspRange = {0xFFFF: 0x000F}
    font["gasp"] = gasp
    maxp = font["maxp"]
    maxp.maxZones, maxp.maxTwilightPoints, maxp.maxStorage = 2, 0, 0
    maxp.maxFunctionDefs, maxp.maxInstructionDefs, maxp.maxStackElements = 0, 0, 8
    maxp.maxSizeOfInstructions = 0

    if name == "Direct8":
        # Touch each point in y (backward-compatible rasterizers only move touched points with
        # SHPIX), then move all four by the shift, with no storage, function or SHZ.
        touch = [line for point in range(4) for line in (f"PUSH[ ] {point}", "MDAP[0]")]
        program = ttProgram.Program()
        program.fromAssembly(
            [
                "SVTCA[0]",
                *touch,
                f"PUSH[ ] 0 1 2 3 4 {round(shift * 64)}",
                "SWAP[ ]",
                "SLOOP[ ]",
                "SHPIX[ ]",
            ]
        )
        font["glyf"]["box"].program = program
        maxp.maxSizeOfInstructions = len(program.getBytecode())
    elif shift:
        add_ppem_shift_hints(font, ["box"], dict.fromkeys(PPEMS, shift))
    return fb


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "tools/render-windows/probe")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, shift in PROBES.items():
        path = out_dir / f"HangyeolProbe-{name}.ttf"
        build(name, shift).save(str(path))
        print(f"{path}  shift {shift:+.3f} px at {PPEMS.start}-{PPEMS.stop - 1} ppem")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
