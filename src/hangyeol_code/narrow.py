"""Hangyeol Code Narrow: the same font on 540/1080-unit cells instead of 600/1200.

Every glyph keeps its place relative to the centre of its cell (or cells, for ligatures
and combining marks drawn over the previous cell), except for the sideways shift in
step 2. Margins are measured on the rendered outline; in italics the 9° slant is removed
first so the slant itself does not count as overflow.

1. If the narrower cell still leaves at least ``min_margin`` on both sides, the glyph is
   only moved with its cell.
2. Otherwise it first moves sideways by up to ``max_shift``, at most until it is centred
   in its cell. Combining marks never shift, and an italic glyph shifts as far as its
   upright glyph.
3. If it still does not fit, it is squeezed horizontally about the cell centre until
   ``min_margin`` is left, by at most ``max_shrink``. Glyphs that already crossed their
   cell edges are not shifted and are squeezed by the full ``max_shrink``.
4. Symbols drawn in a square box (ink aspect within ``square_tolerance``) that get
   squeezed are scaled vertically by the same factor about their own vertical centre.

Box drawing, block elements, Powerline separators and progress-bar pieces are laid out on
the cell grid itself, so they are scaled by exactly the cell ratio to keep joining their
neighbours.

The TrueType hints of JetBrains Mono only move points vertically, and every point keeps
its index, so all glyph programs stay. For the shapes that are also scaled vertically
(○ ■ ⊕ ...), FreeType at 10-20 px shows the hinted edges following the new outline as
closely as they follow the original one (within 1 px).
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from fontTools.misc.transform import Identity, Offset, Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program

from hangyeol_code.builder import add_ppem_shift_hints

logger = logging.getLogger(__name__)

ITALIC_PIVOT_Y = 275  # JetBrains Mono italics are sheared about half the x-height

CELL_FILL_RANGES = (
    (0x2500, 0x259F),  # box drawing, block elements
    (0x239B, 0x23B3),  # bracket and integral pieces
    (0x23BA, 0x23BD),  # horizontal scan lines
    (0xE0B0, 0xE0D7),  # Powerline separators
    (0xEE00, 0xEE0B),  # progress bar pieces
)

# Symbols designed in a square: enclosed and circled characters, geometric shapes, card
# suits and stars, circled/squared operators, power symbols and Nerd Fonts icons.
SQUARE_SYMBOL_RANGES = (
    (0x203B, 0x203B),  # reference mark
    (0x2295, 0x22A1),  # circled and squared operators
    (0x2318, 0x2318),  # place of interest sign
    (0x238B, 0x238B),  # broken circle (escape)
    (0x23FB, 0x23FE),  # power symbols
    (0x2460, 0x24FF),  # enclosed alphanumerics
    (0x25A0, 0x25FF),  # geometric shapes
    (0x2600, 0x26FF),  # miscellaneous symbols
    (0x2776, 0x2793),  # dingbat circled digits
    (0x2B00, 0x2BFF),  # miscellaneous symbols and arrows
    (0x3200, 0x32FF),  # enclosed CJK letters and months
    (0xE000, 0xF8FF),  # private use (Nerd Fonts icons)
    (0x1F100, 0x1F1FF),  # enclosed alphanumeric supplement
    (0xF0000, 0x10FFFF),  # supplementary private use (Material Design icons)
)

# Hint groups, in the order their shift tables are added to the font.
HINT_GROUPS = ("hangul", "icons", "symbols")


@dataclass(frozen=True)
class NarrowSettings:
    """How far to narrow and how to treat glyphs that no longer fit."""

    ratio: float = 0.9
    min_margin: float = 7.5
    max_shrink: float = 0.10
    max_shift: float = 20.0  # 0 keeps every glyph centred
    square_tolerance: float = 1.25
    overflow_tolerance: float = 2.0  # crossings this small count as touching (rounding)


DEFAULT_SETTINGS = NarrowSettings()


@dataclass
class Plan:
    """What happens to one glyph."""

    name: str
    cps: list[int]
    kind: str
    advance: int
    new_advance: int
    sx: float = 1.0
    sy: float = 1.0
    slanted: bool = False
    before: tuple[float, float] | None = None  # margins in the old cell(s)
    after: tuple[float, float] | None = None  # margins in the new cell(s)
    matrix: Transform = field(default_factory=lambda: Identity)
    offset: float = 0.0  # header xMin - lsb (pp1)
    dx: float = 0.0  # sideways shift within the new cell(s), before squeezing


def is_cell_fill(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in CELL_FILL_RANGES)


def is_square_symbol(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in SQUARE_SYMBOL_RANGES)


def is_private_use(cp: int) -> bool:
    return 0xE000 <= cp <= 0xF8FF or cp >= 0xF0000


def fit_shift(x0: float, x1: float, box_left: float, box_right: float, limit: float) -> float:
    """Return the shift, up to ``limit``, that brings ink ``x0..x1`` between the margins.

    The ink never moves past the point where it is centred between them.
    """
    if x1 - x0 >= box_right - box_left:
        shift = (box_left + box_right) / 2 - (x0 + x1) / 2
    elif x0 < box_left:
        shift = box_left - x0
    elif x1 > box_right:
        shift = box_right - x1
    else:
        shift = 0.0
    return max(-limit, min(limit, shift))


def rendered_bounds(glyph_set: Any, name: str, shear: float, pivot: float) -> Any:
    pen = BoundsPen(glyph_set)
    target = TransformPen(pen, (1, 0, -shear, 1, shear * pivot, 0)) if shear else pen
    glyph_set[name].draw(target)
    return pen.bounds


def outline_signature(glyph_set: Any, name: str) -> str:
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    return repr(pen.value)


def plan_font(
    font: TTFont, upright: TTFont | None, settings: NarrowSettings = DEFAULT_SETTINGS
) -> dict[str, Plan]:
    """Decide the transform of every glyph. ``upright`` is the matching upright font for
    an italic, used to tell slanted glyphs from upright ones."""
    ratio = settings.ratio
    glyph_set = font.getGlyphSet()
    glyf = cast("Any", font["glyf"])
    hmtx = cast("Any", font["hmtx"])
    cps_of: dict[str, list[int]] = {}
    for cp, name in font.getBestCmap().items():
        cps_of.setdefault(name, []).append(cp)
    gdef = cast("Any", font["GDEF"]).table if "GDEF" in font else None
    classes = gdef.GlyphClassDef.classDefs if gdef and gdef.GlyphClassDef else {}

    shear = 0.0
    upright_set = None
    upright_shifts: dict[str, float] = {}
    if upright is not None:
        shear = math.tan(math.radians(-cast("Any", font["post"]).italicAngle))
        upright_set = upright.getGlyphSet()
        if settings.max_shift > 0:
            upright_shifts = {name: p.dx for name, p in plan_font(upright, None, settings).items()}

    plans: dict[str, Plan] = {}
    for name in font.getGlyphOrder():
        advance, lsb = hmtx[name]
        glyph = glyf[name]
        cps = sorted(cps_of.get(name, []))
        offset = (glyph.xMin - lsb) if glyph.numberOfContours != 0 else 0
        plan = Plan(name, cps, "empty", advance, round(advance * ratio), offset=offset)
        plans[name] = plan
        if advance == 0 or glyph.numberOfContours == 0:
            continue

        slanted = False
        if upright_set is not None and not any(is_cell_fill(cp) for cp in cps):
            slanted = name not in upright_set or outline_signature(
                glyph_set, name
            ) != outline_signature(upright_set, name)
        plan.slanted = slanted
        t = shear if slanted else 0.0
        x0, y0, x1, y1 = rendered_bounds(glyph_set, name, t, ITALIC_PIVOT_Y)

        # The cells this glyph is laid out on, in old units.
        if ".liga" in name:
            n = len(name.split(".")[0].split("_"))
            left, right = -advance * (n - 1), advance
            kind = "ligature"
        else:
            k = math.floor((x0 + x1) / 2 / advance)
            left, right = k * advance, (k + 1) * advance
            kind = "mark" if classes.get(name) == 3 or k < 0 else "glyph"
        mid, new_left, new_right = (left + right) / 2, left * ratio, right * ratio
        new_mid = mid * ratio
        plan.before = (x0 - left, right - x1)
        box_left, box_right = new_left + settings.min_margin, new_right - settings.min_margin
        # The ink once the glyph has moved with its cell centre, before any shift or squeeze.
        ink0, ink1 = x0 - mid + new_mid, x1 - mid + new_mid

        sx = sy = 1.0
        dx = 0.0
        if any(is_cell_fill(cp) for cp in cps):
            kind, sx = "cell-fill", ratio
        else:
            tolerance = settings.overflow_tolerance
            if x0 < left - tolerance or x1 > right + tolerance:
                kind, sx = f"{kind}-overflow", 1.0 - settings.max_shrink
            else:
                if settings.max_shift > 0 and kind != "mark":
                    dx = upright_shifts.get(
                        name, fit_shift(ink0, ink1, box_left, box_right, settings.max_shift)
                    )
                limits = [1.0]
                if ink0 + dx < new_mid:
                    limits.append((new_mid - box_left) / (new_mid - ink0 - dx))
                if ink1 + dx > new_mid:
                    limits.append((box_right - new_mid) / (ink1 + dx - new_mid))
                sx = max(1.0 - settings.max_shrink, min(limits))
                if sx < 1.0 - 1e-9:
                    kind = f"{kind}-squeezed"
                else:
                    sx = 1.0
                if abs(dx) > 1e-9:
                    kind = f"{kind}-shifted"
            width, height = x1 - x0, y1 - y0
            tol = settings.square_tolerance
            square = height > 0 and 1 / tol <= width / height <= tol
            if sx < 1.0 and square and any(is_square_symbol(cp) for cp in cps):
                sy = sx
                kind = f"{kind}-square"
        plan.kind, plan.sx, plan.sy, plan.dx = kind, sx, sy, dx
        offset_x = new_mid + sx * (dx - mid)
        plan.after = (offset_x + sx * x0 - new_left, new_right - (offset_x + sx * x1))

        yc = (y0 + y1) / 2
        scale = Transform(sx, 0, 0, sy, offset_x, yc - sy * yc)
        if t:
            deslant = Transform(1, 0, -t, 1, t * ITALIC_PIVOT_Y, 0)
            reslant = Transform(1, 0, t, 1, -t * ITALIC_PIVOT_Y, 0)
            plan.matrix = reslant.transform(scale).transform(deslant)
        else:
            plan.matrix = scale
    return plans


def _transform_anchor(anchor: Any, matrix: Transform) -> None:
    x, y = matrix.transformPoint((anchor.XCoordinate, anchor.YCoordinate))
    anchor.XCoordinate, anchor.YCoordinate = round(x), round(y)


def apply_plans(font: TTFont, plans: dict[str, Plan]) -> dict[str, int]:
    """Move outlines, components, metrics and mark anchors as planned."""
    glyf = cast("Any", font["glyf"])
    hmtx = cast("Any", font["hmtx"])
    stats = {"scaled_components": 0}

    def rendered_matrix(plan: Plan) -> Transform:
        return plan.matrix.transform(Offset(-plan.offset, 0))

    # Composite placement depends on the old geometry of its components, so compute it first.
    composite_updates: list[tuple[Any, Transform]] = []
    for name, plan in plans.items():
        glyph = glyf[name]
        if not glyph.isComposite():
            continue
        for comp in glyph.components:
            if getattr(comp, "firstPt", None) is not None:
                msg = f"{name}: point-matched components are not supported"
                raise ValueError(msg)
            (xx, xy), (yx, yy) = getattr(comp, "transform", ((1.0, 0.0), (0.0, 1.0)))
            placement = Transform(xx, xy, yx, yy, comp.x, comp.y)
            child = rendered_matrix(plans[comp.glyphName]).inverse()
            composite_updates.append(
                (comp, rendered_matrix(plan).transform(placement).transform(child))
            )

    for name, plan in plans.items():
        glyph = glyf[name]
        if glyph.numberOfContours > 0:
            m = rendered_matrix(plan)
            glyph.coordinates = GlyphCoordinates(
                [(round(x), round(y)) for x, y in m.transformPoints(glyph.coordinates)]
            )

    for comp, m in composite_updates:
        comp.x, comp.y = round(m.dx), round(m.dy)
        comp.flags &= ~0x0200  # USE_MY_METRICS: metrics are written explicitly below
        if all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(m[:4], (1, 0, 0, 1), strict=True)):
            if hasattr(comp, "transform"):
                del comp.transform
            comp.flags &= ~(0x0008 | 0x0040 | 0x0080)
        else:
            comp.transform = [[m.xx, m.xy], [m.yx, m.yy]]
            comp.flags = (comp.flags | 0x1000) & ~0x0800  # offsets are not scaled
            stats["scaled_components"] += 1

    for name, plan in plans.items():
        glyph = glyf[name]
        if glyph.numberOfContours != 0:
            glyph.recalcBounds(glyf)
            hmtx[name] = (plan.new_advance, glyph.xMin)
        else:
            hmtx[name] = (plan.new_advance, 0)

    if "GPOS" in font:
        for lookup in cast("Any", font["GPOS"]).table.LookupList.Lookup:
            for sub in lookup.SubTable:
                st = sub.ExtSubTable if lookup.LookupType == 9 else sub
                lt = st.LookupType if lookup.LookupType == 9 else lookup.LookupType
                if lt == 4:
                    marks = zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord, strict=True)
                    for g, rec in marks:
                        _transform_anchor(rec.MarkAnchor, plans[g].matrix)
                    bases = zip(st.BaseCoverage.glyphs, st.BaseArray.BaseRecord, strict=True)
                    for g, rec in bases:
                        for anchor in rec.BaseAnchor:
                            if anchor is not None:
                                _transform_anchor(anchor, plans[g].matrix)
                elif lt == 6:
                    marks = zip(st.Mark1Coverage.glyphs, st.Mark1Array.MarkRecord, strict=True)
                    for g, rec in marks:
                        _transform_anchor(rec.MarkAnchor, plans[g].matrix)
                    bases = zip(st.Mark2Coverage.glyphs, st.Mark2Array.Mark2Record, strict=True)
                    for g, rec in bases:
                        for anchor in rec.Mark2Anchor:
                            if anchor is not None:
                                _transform_anchor(anchor, plans[g].matrix)
                else:
                    msg = f"GPOS lookup type {lt} is not handled"
                    raise ValueError(msg)
    return stats


def hint_groups(plans: dict[str, Plan], added: set[str]) -> dict[str, list[str]]:
    """Split the glyphs that get a per-ppem shift into hint groups.

    hangul: glyphs taken from Pretendard/Noto Sans KR (``added``) that kept their height.
    icons: Nerd Fonts icons that were scaled (they carry no hints of their own).
    symbols: glyphs from ``added`` that were scaled vertically.
    """
    groups: dict[str, list[str]] = {group: [] for group in HINT_GROUPS}
    for name, plan in plans.items():
        if name in added and plan.sy < 1:
            groups["symbols"].append(name)
        elif name in added:
            groups["hangul"].append(name)
        elif (
            plan.kind != "cell-fill"
            and any(is_private_use(cp) for cp in plan.cps)
            and (plan.sx < 1 or plan.sy < 1)
        ):
            groups["icons"].append(name)
    return groups


def add_group_hints(
    font: TTFont, groups: dict[str, list[str]], tables: dict[str, dict[int, float] | None]
) -> dict[str, int]:
    """Add one per-ppem shift table per group, in ``HINT_GROUPS`` order."""
    glyf = cast("Any", font["glyf"])
    hinted = {}
    for group in HINT_GROUPS:
        shifts = tables.get(group)
        names = groups.get(group, [])
        if not shifts or not names:
            continue
        for name in names:
            glyf[name].program = Program()
            glyf[name].program.fromBytecode(b"")
        hinted[group] = add_ppem_shift_hints(font, names, shifts)
    return hinted


def narrow_font(
    font: TTFont, upright: TTFont | None, settings: NarrowSettings = DEFAULT_SETTINGS
) -> tuple[dict[str, Plan], dict[str, int]]:
    """Narrow ``font`` in place and return the per-glyph plans and a few counts."""
    plans = plan_font(font, upright, settings)
    stats = apply_plans(font, plans)
    os2 = cast("Any", font["OS/2"])
    os2.xAvgCharWidth = round(os2.xAvgCharWidth * settings.ratio)
    kinds: dict[str, int] = {}
    for plan in plans.values():
        kinds[plan.kind] = kinds.get(plan.kind, 0) + 1
    logger.info(
        "Narrowed to %d/%d: %s, scaled components=%d",
        round(600 * settings.ratio),
        round(1200 * settings.ratio),
        ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())),
        stats["scaled_components"],
    )
    return plans, stats


def write_report(path: Path, rows: list[tuple[str, Plan]]) -> None:
    """Write one TSV row per glyph and style describing what happened to it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(
            [
                "style",
                "glyph",
                "codepoints",
                "kind",
                "advance",
                "sx",
                "sy",
                "dx",
                "left_before",
                "right_before",
                "left_after",
                "right_after",
            ]
        )
        for style, plan in rows:
            writer.writerow(
                [
                    style,
                    plan.name,
                    " ".join(f"U+{cp:04X}" for cp in plan.cps),
                    plan.kind,
                    plan.advance,
                    f"{plan.sx:.4f}",
                    f"{plan.sy:.4f}",
                    f"{plan.dx:.1f}",
                    *(f"{v:.1f}" for v in (plan.before or ())),
                    *(f"{v:.1f}" for v in (plan.after or ())),
                ]
            )
