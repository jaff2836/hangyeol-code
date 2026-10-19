"""Font merging and fitting logic for Hangyeol Code."""

from __future__ import annotations

import itertools
import logging
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.otlLib.builder import buildLigatureSubstSubtable, buildLookup
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables, ttProgram

logger = logging.getLogger(__name__)

Bounds = tuple[float, float, float, float]

DEFAULT_KOREAN_SCALE = 1.08404
DEFAULT_KOREAN_Y_OFFSET = -25
ASCII_WIDTH_SAMPLE = tuple(ord(char) for char in " A0Hinmw")

AUTHOR = "Sangwon Chae"
AUTHOR_URL = "https://github.com/jaff2836"
PROJECT_URL = "https://github.com/jaff2836/hangyeol-code"
COPYRIGHT_NOTICE = f"Copyright 2026 {AUTHOR} ({PROJECT_URL})"
DESIGNER = (
    f"{AUTHOR}; based on JetBrains Mono by Philipp Nurullin and Konstantin Bulenkov, "
    "Pretendard by Kil Hyung-jin and Noto Sans KR by Adobe"
)
LICENSE_DESCRIPTION = (
    "This Font Software is licensed under the SIL Open Font License, Version 1.1. "
    "This license is available with a FAQ at: https://openfontlicense.org"
)
LICENSE_URL = "https://openfontlicense.org"
VENDOR_ID = "NONE"


CHOSEONG_MAP = {
    0x1100: 0x3131,
    0x1101: 0x3132,
    0x1102: 0x3134,
    0x1103: 0x3137,
    0x1104: 0x3138,
    0x1105: 0x3139,
    0x1106: 0x3141,
    0x1107: 0x3142,
    0x1108: 0x3143,
    0x1109: 0x3145,
    0x110A: 0x3146,
    0x110B: 0x3147,
    0x110C: 0x3148,
    0x110D: 0x3149,
    0x110E: 0x314A,
    0x110F: 0x314B,
    0x1110: 0x314C,
    0x1111: 0x314D,
    0x1112: 0x314E,
}
JUNGSEONG_MAP = {code: 0x314F + (code - 0x1161) for code in range(0x1161, 0x1175 + 1)}
JONGSEONG_MAP = {
    0x11A8: 0x3131,
    0x11A9: 0x3132,
    0x11AA: 0x3133,
    0x11AB: 0x3134,
    0x11AC: 0x3135,
    0x11AD: 0x3136,
    0x11AE: 0x3137,
    0x11AF: 0x3139,
    0x11B0: 0x313A,
    0x11B1: 0x313B,
    0x11B2: 0x313C,
    0x11B3: 0x313D,
    0x11B4: 0x313E,
    0x11B5: 0x313F,
    0x11B6: 0x3140,
    0x11B7: 0x3141,
    0x11B8: 0x3142,
    0x11B9: 0x3144,
    0x11BA: 0x3145,
    0x11BB: 0x3146,
    0x11BC: 0x3147,
    0x11BD: 0x3148,
    0x11BE: 0x314A,
    0x11BF: 0x314B,
    0x11C0: 0x314C,
    0x11C1: 0x314D,
    0x11C2: 0x314E,
}
JAMO_COMPATIBILITY_MAP = CHOSEONG_MAP | JUNGSEONG_MAP | JONGSEONG_MAP


@dataclass(frozen=True)
class FittedGlyphTransform:
    """A safe transform for one copied Korean/CJK glyph."""

    scale: float
    shift_x: float
    left_side_bearing: int
    capped: bool
    transformed_bounds: Bounds | None


@dataclass(frozen=True)
class MergeStats:
    """Summary of a font merge."""

    copied_count: int
    capped_count: int
    latin_advance: int
    korean_advance: int
    requested_total_scale: float
    symbol_count: int = 0


@dataclass
class MergedFont:
    """A merged, named font before hinting, with the glyphs the Hangul hints apply to."""

    font: TTFont
    stats: MergeStats
    hint_glyphs: list[str]


@dataclass(frozen=True)
class FontVariant:
    """One buildable output variant."""

    weight_name: str
    css_weight: int
    style: str
    latin_filename: str
    cjk_weight_name: str
    output_suffix: str
    subfamily_name: str
    typographic_subfamily_name: str
    is_italic: bool


WEIGHT_TO_CSS = {
    "Thin": 100,
    "ExtraLight": 200,
    "Light": 300,
    "Regular": 400,
    "Medium": 500,
    "SemiBold": 600,
    "Bold": 700,
    "ExtraBold": 800,
}
SUPPORTED_WEIGHTS = tuple(WEIGHT_TO_CSS)
DEFAULT_WEIGHTS = SUPPORTED_WEIGHTS
SUPPORTED_STYLES = ("normal", "italic")


def new_ot_table(class_name: str) -> Any:
    """Create a fontTools OpenType table class generated at import time."""
    table_class = getattr(cast("Any", otTables), class_name)
    return table_class()


def make_font_variant(weight_name: str, style: str) -> FontVariant:
    """Create a build variant for a supported weight/style pair."""
    if weight_name not in WEIGHT_TO_CSS:
        supported = ", ".join(SUPPORTED_WEIGHTS)
        msg = f"Unsupported weight {weight_name!r}. Supported: {supported}"
        raise ValueError(msg)
    if style not in SUPPORTED_STYLES:
        supported = ", ".join(SUPPORTED_STYLES)
        msg = f"Unsupported style {style!r}. Supported: {supported}"
        raise ValueError(msg)

    is_italic = style == "italic"
    if is_italic:
        latin_suffix = "Italic" if weight_name == "Regular" else f"{weight_name}Italic"
        output_suffix = latin_suffix
        subfamily_name = "Italic" if weight_name == "Regular" else f"{weight_name} Italic"
    else:
        latin_suffix = weight_name
        output_suffix = weight_name
        subfamily_name = weight_name

    return FontVariant(
        weight_name=weight_name,
        css_weight=WEIGHT_TO_CSS[weight_name],
        style=style,
        latin_filename=f"JetBrainsMonoNerdFontMono-{latin_suffix}.ttf",
        cjk_weight_name=weight_name,
        output_suffix=output_suffix,
        subfamily_name=subfamily_name,
        typographic_subfamily_name=subfamily_name,
        is_italic=is_italic,
    )


DEFAULT_VARIANTS = tuple(
    make_font_variant(weight_name, style)
    for weight_name in SUPPORTED_WEIGHTS
    for style in SUPPORTED_STYLES
)
VARIANTS_BY_SUFFIX = {variant.output_suffix: variant for variant in DEFAULT_VARIANTS}


def get_variants_by_names(variant_names: list[str] | tuple[str, ...]) -> list[FontVariant]:
    """Resolve output suffix names to variants, preserving request order."""
    variants: list[FontVariant] = []
    seen: set[str] = set()
    unsupported: list[str] = []

    for name in variant_names:
        variant = VARIANTS_BY_SUFFIX.get(name)
        if variant is None:
            unsupported.append(name)
            continue
        if variant.output_suffix in seen:
            continue
        variants.append(variant)
        seen.add(variant.output_suffix)

    if unsupported:
        supported = ", ".join(VARIANTS_BY_SUFFIX)
        msg = f"Unsupported variant(s): {', '.join(unsupported)}. Supported: {supported}"
        raise ValueError(msg)

    return variants


def get_variants_by_weights_and_styles(
    weights: list[str] | tuple[str, ...],
    styles: list[str] | tuple[str, ...],
) -> list[FontVariant]:
    """Resolve weight/style selectors to variants."""
    return [make_font_variant(weight, style) for weight in weights for style in styles]


def is_cjk(code: int) -> bool:
    """Return whether a Unicode codepoint belongs to supported Korean/CJK ranges."""
    return (
        0xAC00 <= code <= 0xD7A3
        or 0x1100 <= code <= 0x11FF
        or 0x3130 <= code <= 0x318F
        or 0xA960 <= code <= 0xA97F
        or 0xD7B0 <= code <= 0xD7FF
        or 0x4E00 <= code <= 0x9FFF
        or 0x3000 <= code <= 0x303F
        or 0xFF00 <= code <= 0xFFEF
    )


def collect_cjk_codepoints(cmap: dict[int, str]) -> list[int]:
    """Collect CJK codepoints and required Hangul Jamo codepoints."""
    codepoints = {code for code in cmap if is_cjk(code)}
    codepoints.update(JAMO_COMPATIBILITY_MAP)
    return sorted(codepoints)


KSX1001_SYMBOL_LEAD_BYTES = range(0xA1, 0xAD)
# KS X 1001:2002 added U+327E (0xA2E8), which Python's euc_kr codec does not decode.
KSX1001_2002_ADDITIONS = (0x327E,)


def collect_ksx1001_symbol_codepoints() -> list[int]:
    """Return the KS X 1001 characters outside the Hangul and Hanja rows.

    These are rows 1-12 of the standard (EUC-KR lead bytes 0xA1-0xAC): symbols,
    full-width forms, compatibility Jamo, Roman numerals, box drawing, units,
    circled and parenthesized characters, kana, Greek and Cyrillic.
    """
    codepoints: set[int] = set(KSX1001_2002_ADDITIONS)
    for lead in KSX1001_SYMBOL_LEAD_BYTES:
        for trail in range(0xA1, 0xFF):
            try:
                char = bytes([lead, trail]).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            codepoints.add(ord(char))
    return sorted(codepoints)


def is_conjoining_jamo(code: int) -> bool:
    """Return whether a codepoint is a conjoining Hangul medial vowel or final consonant."""
    return 0x1160 <= code <= 0x11FF or 0xD7B0 <= code <= 0xD7FF


def cell_width(codepoint: int, latin_advance: int) -> int:
    """Return the advance a character should have, following Unicode East Asian Width.

    Wide and full-width characters take two Latin cells. Everything else, including
    East Asian Ambiguous characters such as U+203B and half-width forms, takes one
    cell, matching how terminals lay them out. Conjoining medial and final Jamo keep
    two cells: alone they are drawn as full compatibility Jamo, and ccmp joins them
    into syllables.
    """
    wide = unicodedata.east_asian_width(chr(codepoint)) in ("W", "F")
    if wide or is_conjoining_jamo(codepoint):
        return latin_advance * 2
    return latin_advance


def cell_width_mismatches(font: TTFont, latin_advance: int) -> list[tuple[int, int]]:
    """Return ``(codepoint, advance)`` for every spacing character that breaks ``cell_width``.

    Combining marks, format and control characters and zero-width glyphs are skipped.
    """
    hmtx = cast("Any", font["hmtx"])
    mismatches: list[tuple[int, int]] = []
    for codepoint, glyph_name in sorted(font.getBestCmap().items()):
        advance = hmtx[glyph_name][0]
        if advance == 0 or unicodedata.category(chr(codepoint)) in ("Mn", "Me", "Cf", "Cc"):
            continue
        if advance != cell_width(codepoint, latin_advance):
            mismatches.append((codepoint, advance))
    return mismatches


def log_cell_width_mismatches(font: TTFont, label: str) -> None:
    """Warn about characters whose advance does not match their East Asian Width."""
    mismatches = cell_width_mismatches(font, derive_latin_advance(font))
    if mismatches:
        preview = ", ".join(f"U+{code:04X}={advance}" for code, advance in mismatches[:12])
        logger.warning("%s: %d cell width mismatches: %s", label, len(mismatches), preview)


def calculate_korean_target_width(latin_advance: int) -> int:
    """Calculate the exact two-cell Korean/CJK advance width."""
    if latin_advance <= 0:
        msg = f"Latin advance must be positive, got {latin_advance}"
        raise ValueError(msg)
    return latin_advance * 2


def derive_latin_advance(
    font: TTFont,
    sample_codepoints: tuple[int, ...] = ASCII_WIDTH_SAMPLE,
) -> int:
    """Derive the Latin monospace advance from representative ASCII glyphs."""
    cmap = font.getBestCmap()
    if not cmap:
        msg = "Base font has no usable cmap table"
        raise ValueError(msg)
    hmtx = font["hmtx"]

    widths: dict[str, int] = {}
    for codepoint in sample_codepoints:
        glyph_name = cmap.get(codepoint)
        if glyph_name is None or glyph_name not in hmtx.metrics:
            continue
        widths[chr(codepoint)] = hmtx.metrics[glyph_name][0]

    if not widths:
        msg = "Could not derive a Latin advance from the base font"
        raise ValueError(msg)

    unique_widths = set(widths.values())
    if len(unique_widths) != 1:
        details = ", ".join(f"{char}={width}" for char, width in sorted(widths.items()))
        msg = f"Base font is not monospaced across the ASCII sample: {details}"
        raise ValueError(msg)

    return unique_widths.pop()


def default_side_bearing_guard(latin_advance: int) -> int:
    """Return a modest guard that keeps fitted glyphs off cell edges."""
    return max(8, round(latin_advance * 0.02))


def get_vertical_safe_bounds(font: TTFont) -> tuple[int, int]:
    """Return conservative vertical bounds from the base font metrics."""
    hhea = cast("Any", font["hhea"])
    os2 = cast("Any", font["OS/2"])
    safe_ymax = min(int(hhea.ascent), int(os2.sTypoAscender))
    safe_ymin = max(int(hhea.descent), int(os2.sTypoDescender))
    if safe_ymin >= safe_ymax:
        safe_ymin = int(hhea.descent)
        safe_ymax = int(hhea.ascent)
    return safe_ymin, safe_ymax


def get_glyph_bounds(glyph_set: Any, glyph_name: str) -> Bounds | None:
    """Measure glyph bounds with fontTools pens."""
    bounds_pen = BoundsPen(glyph_set)
    glyph_set[glyph_name].draw(bounds_pen)
    return bounds_pen.bounds


def calculate_fitted_transform(
    bounds: Bounds | None,
    *,
    target_width: int,
    requested_scale: float,
    safe_ymin: int,
    safe_ymax: int,
    side_bearing_guard: int,
    vertical_guard: int = 0,
    shift_y: float = 0,
) -> FittedGlyphTransform:
    """Calculate a scale and horizontal shift that avoids clipping."""
    if requested_scale <= 0:
        msg = f"Scale must be positive, got {requested_scale}"
        raise ValueError(msg)
    if bounds is None:
        return FittedGlyphTransform(
            scale=requested_scale,
            shift_x=0,
            left_side_bearing=0,
            capped=False,
            transformed_bounds=None,
        )

    xmin, ymin, xmax, ymax = bounds
    scale = requested_scale

    source_width = xmax - xmin
    horizontal_limit = target_width - (side_bearing_guard * 2)
    if source_width > 0 and horizontal_limit > 0:
        scale = min(scale, horizontal_limit / source_width)

    top_limit = safe_ymax - vertical_guard - shift_y
    bottom_limit = safe_ymin + vertical_guard - shift_y
    if ymax > 0 and top_limit > 0:
        scale = min(scale, top_limit / ymax)
    if ymin < 0 and bottom_limit < 0:
        scale = min(scale, bottom_limit / ymin)

    if scale <= 0:
        msg = f"Could not fit glyph bounds {bounds} into target width {target_width}"
        raise ValueError(msg)

    scaled_xmin = xmin * scale
    scaled_xmax = xmax * scale
    current_center = (scaled_xmin + scaled_xmax) / 2
    shift_x = (target_width / 2) - current_center
    transformed_bounds = (
        scaled_xmin + shift_x,
        ymin * scale + shift_y,
        scaled_xmax + shift_x,
        ymax * scale + shift_y,
    )
    capped = scale < requested_scale - 0.000001

    return FittedGlyphTransform(
        scale=scale,
        shift_x=shift_x,
        left_side_bearing=round(transformed_bounds[0]),
        capped=capped,
        transformed_bounds=transformed_bounds,
    )


def calculate_centered_fit(
    bounds: Bounds | None,
    *,
    target_width: int,
    requested_scale: float,
    safe_ymin: int,
    safe_ymax: int,
    side_bearing_guard: int,
    shift_y: float = 0,
) -> tuple[FittedGlyphTransform, float]:
    """Fit a glyph like ``calculate_fitted_transform`` but keep a capped glyph's center.

    A capped glyph is scaled down about its own vertical center instead of the
    baseline, so a symbol squeezed into one cell stays at the height it would have
    had at the requested scale. Returns the fit and the vertical shift to apply.
    """
    fit_kwargs = {
        "target_width": target_width,
        "requested_scale": requested_scale,
        "safe_ymin": safe_ymin,
        "safe_ymax": safe_ymax,
        "side_bearing_guard": side_bearing_guard,
    }
    fitted = calculate_fitted_transform(bounds, shift_y=shift_y, **fit_kwargs)
    if bounds is None or not fitted.capped:
        return fitted, float(shift_y)
    center_y = (bounds[1] + bounds[3]) / 2
    adjusted = float(shift_y)
    for _ in range(4):
        adjusted = shift_y + (requested_scale - fitted.scale) * center_y
        fitted = calculate_fitted_transform(bounds, shift_y=adjusted, **fit_kwargs)
    return fitted, adjusted


# Modern Hangul compatibility Jamo. Their average stroke width stands for a font's Hangul
# stroke weight when matching a fallback font to Pretendard.
STROKE_PROBES = tuple(range(0x3131, 0x3164))

# Symbols taken from the fallback font even though Pretendard has them, so that each
# visually related set comes from one design: circled numbers (next to the fallback's
# circled letters and Hangul), the parenthesized U+321C (next to the other
# parenthesized Hangul), and the white heart suit and eighth note (next to the other
# card suits and notes).
KSX_PREFER_FALLBACK: frozenset[int] = frozenset([*range(0x2460, 0x246F), 0x321C, 0x2661, 0x266A])

# How much of the stroke thinning from shrinking a fallback glyph into its cell is undone
# with a heavier instance: 0 keeps plain scaling, 1 restores full-size strokes. A glyph
# shrunk to a scale s ends up with strokes s ** (1 - this) times their full-size width.
FALLBACK_STROKE_COMPENSATION = 0.5


class _SegmentPen(BasePen):
    """Collect a glyph outline as straight segments, flattening curves."""

    def __init__(self, glyph_set: Any, steps: int = 16) -> None:
        super().__init__(glyph_set)
        self.steps = steps
        self.segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self._start: tuple[float, float] = (0.0, 0.0)
        self._last: tuple[float, float] = (0.0, 0.0)

    def _moveTo(self, pt: tuple[float, float]) -> None:
        self._start = self._last = pt

    def _lineTo(self, pt: tuple[float, float]) -> None:
        self.segments.append((self._last, pt))
        self._last = pt

    def _curveToOne(
        self, pt1: tuple[float, float], pt2: tuple[float, float], pt3: tuple[float, float]
    ) -> None:
        p0 = self._last
        for i in range(1, self.steps + 1):
            t = i / self.steps
            m = 1 - t
            point = (
                m**3 * p0[0] + 3 * m * m * t * pt1[0] + 3 * m * t * t * pt2[0] + t**3 * pt3[0],
                m**3 * p0[1] + 3 * m * m * t * pt1[1] + 3 * m * t * t * pt2[1] + t**3 * pt3[1],
            )
            self._lineTo(point)

    def _qCurveToOne(self, pt1: tuple[float, float], pt2: tuple[float, float]) -> None:
        p0 = self._last
        for i in range(1, self.steps + 1):
            t = i / self.steps
            m = 1 - t
            point = (
                m * m * p0[0] + 2 * m * t * pt1[0] + t * t * pt2[0],
                m * m * p0[1] + 2 * m * t * pt1[1] + t * t * pt2[1],
            )
            self._lineTo(point)

    def _closePath(self) -> None:
        if self._last != self._start:
            self.segments.append((self._last, self._start))
        self._last = self._start

    def _endPath(self) -> None:
        self._closePath()


def measure_stroke(glyph_set: Any, glyph_name: str) -> float:
    """Estimate a glyph's stroke width as ``2 * area / perimeter`` of its outline.

    For strokes much longer than they are wide this approaches the stroke width.
    """
    pen = _SegmentPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    perimeter = sum(math.dist(p, q) for p, q in pen.segments)
    area = abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in pen.segments)) / 2
    return 2 * area / perimeter if perimeter else 0.0


def fit_fallback_mapping(
    reference_cmap: dict[int, str],
    reference_glyph_set: Any,
    fallback_cmap: dict[int, str],
    fallback_glyph_set: Any,
) -> tuple[float, float]:
    """Fit ``y_reference = r * y_fallback + d`` from Hangul syllables both fonts share.

    Pretendard's Hangul comes from Source Han Sans, so a fallback from the same family
    (Noto Sans CJK / Noto Sans KR) maps onto it almost exactly.
    """
    rows: list[tuple[float, float]] = []
    for codepoint in range(0xAC00, 0xD7A4, 37):
        if codepoint not in reference_cmap or codepoint not in fallback_cmap:
            continue
        ref = get_glyph_bounds(reference_glyph_set, reference_cmap[codepoint])
        fb = get_glyph_bounds(fallback_glyph_set, fallback_cmap[codepoint])
        if ref is None or fb is None:
            continue
        rows += [(fb[3], ref[3]), (fb[1], ref[1])]
    if len(rows) < 4:
        msg = "Fallback font shares too few Hangul syllables with Pretendard to align it"
        raise ValueError(msg)
    n = len(rows)
    mean_x = sum(x for x, _ in rows) / n
    mean_y = sum(y for _, y in rows) / n
    sxx = sum((x - mean_x) ** 2 for x, _ in rows)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in rows)
    r = sxy / sxx
    return r, mean_y - r * mean_x


class FallbackWeightMatcher:
    """Find the ``wght`` of a variable fallback font whose Hangul strokes match a reference.

    The fallback's average stroke width over ``STROKE_PROBES`` is sampled along its
    ``wght`` axis once; a target is then found by linear interpolation.
    """

    def __init__(self, reference_font: TTFont, fallback_font: TTFont, samples: int = 33) -> None:
        self.target = 0.0
        self.curve: list[tuple[float, float]] = []
        if "fvar" not in fallback_font:
            return
        axis = next((a for a in fallback_font["fvar"].axes if a.axisTag == "wght"), None)
        ref_cmap = reference_font.getBestCmap()
        fb_cmap = fallback_font.getBestCmap()
        probes = [c for c in STROKE_PROBES if c in ref_cmap and c in fb_cmap]
        if axis is None or not probes:
            return
        ref_set = reference_font.getGlyphSet()
        self.target = sum(measure_stroke(ref_set, ref_cmap[c]) for c in probes) / len(probes)
        for i in range(samples):
            wght = axis.minValue + (axis.maxValue - axis.minValue) * i / (samples - 1)
            fb_set = fallback_font.getGlyphSet(location={"wght": wght})
            stroke = sum(measure_stroke(fb_set, fb_cmap[c]) for c in probes) / len(probes)
            self.curve.append((wght, stroke))

    def wght_for(self, scale_ratio: float, stem_gain: float = 1.0) -> float | None:
        """Return the ``wght`` whose strokes, scaled by ``scale_ratio``, match the reference.

        ``stem_gain`` asks for strokes that many times thicker. Returns None when the
        fallback has no ``wght`` axis.
        """
        if not self.curve:
            return None
        goal = self.target * stem_gain / scale_ratio
        if goal <= self.curve[0][1]:
            return self.curve[0][0]
        for (w0, s0), (w1, s1) in itertools.pairwise(self.curve):
            if s0 <= goal <= s1:
                return round(w0 + (goal - s0) / (s1 - s0) * (w1 - w0), 1)
        return self.curve[-1][0]


def match_fallback_weight(
    reference_font: TTFont,
    fallback_font: TTFont,
    scale_ratio: float,
    stem_gain: float = 1.0,
) -> float | None:
    """Return the ``wght`` at which the fallback's Hangul strokes match the reference font.

    ``stem_gain`` asks for strokes that many times thicker, which compensates a glyph that
    will be scaled down to fit its cell. Returns None for a fallback without ``wght``.
    """
    return FallbackWeightMatcher(reference_font, fallback_font).wght_for(scale_ratio, stem_gain)


def copy_symbol_glyph(
    font: TTFont,
    codepoint: int,
    *,
    glyph_set: Any,
    glyph_name: str,
    target_width: int,
    requested_scale: float,
    shift_y: float,
    safe_ymin: int,
    safe_ymax: int,
    side_bearing_guard: int,
    glyph_order: list[str],
    glyph_order_set: set[str],
) -> str:
    """Copy one symbol into ``font``, fitted to ``target_width`` with its center kept."""
    fitted, y_shift = calculate_centered_fit(
        get_glyph_bounds(glyph_set, glyph_name),
        target_width=target_width,
        requested_scale=requested_scale,
        safe_ymin=safe_ymin,
        safe_ymax=safe_ymax,
        side_bearing_guard=side_bearing_guard,
        shift_y=shift_y,
    )
    recording = DecomposingRecordingPen(glyph_set)
    glyph_set[glyph_name].draw(recording)
    glyph_pen = TTGlyphPen(None)
    recording.replay(
        TransformPen(glyph_pen, (fitted.scale, 0, 0, fitted.scale, fitted.shift_x, y_shift))
    )
    target_glyph_name = f"uni{codepoint:04X}"
    if target_glyph_name in glyph_order_set:
        target_glyph_name += ".ksx"
    font["glyf"][target_glyph_name] = glyph_pen.glyph()
    font["hmtx"].metrics[target_glyph_name] = (target_width, fitted.left_side_bearing)
    update_unicode_cmaps(font, codepoint, target_glyph_name)
    glyph_order.append(target_glyph_name)
    glyph_order_set.add(target_glyph_name)
    return target_glyph_name


# KS X 1001 fractions JetBrains Mono lacks, as (numerator, denominator) digit names.
KSX_FRACTIONS = {
    0x2153: ("one", "three"),
    0x2154: ("two", "three"),
    0x215B: ("one", "eight"),
    0x215C: ("three", "eight"),
    0x215D: ("five", "eight"),
    0x215E: ("seven", "eight"),
}
# How JetBrains Mono draws 1/2, 1/4 and 3/4: the .numr and .dnom digits scaled by 0.73
# (numerators keep their top), moved by these offsets (upright, italic), and laid over
# the full-cell fraction slash. Fitted to the source fractions; its digits match the
# .numr/.dnom glyphs of a weight about two steps heavier (FRACTION_DIGIT_WEIGHT_STEPS).
FRACTION_DIGIT_SCALE = 0.73
FRACTION_NUMERATOR_OFFSET = {False: (-57, 197), True: (-39, 197)}
FRACTION_DENOMINATOR_OFFSET = {False: (225, 0), True: (213, 0)}
FRACTION_DIGIT_WEIGHT_STEPS = 2


def fraction_digit_weight(weight_name: str) -> str:
    """Return the weight whose .numr/.dnom digits match the fractions of ``weight_name``."""
    index = SUPPORTED_WEIGHTS.index(weight_name) + FRACTION_DIGIT_WEIGHT_STEPS
    return SUPPORTED_WEIGHTS[min(index, len(SUPPORTED_WEIGHTS) - 1)]


def add_fraction_glyphs(
    font: TTFont, digit_font: TTFont, *, is_italic: bool, latin_advance: int
) -> list[int]:
    """Add the KS X 1001 fractions JetBrains Mono lacks, drawn like its own 1/2.

    Each fraction is one outline: the fraction slash of ``font`` with the scaled digits
    of ``digit_font``. Returns the codepoints added.
    """
    glyf_table = cast("Any", font["glyf"])
    hmtx_table = cast("Any", font["hmtx"])
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    digit_set = digit_font.getGlyphSet()
    scale = FRACTION_DIGIT_SCALE
    added: list[int] = []
    for codepoint, (numerator, denominator) in KSX_FRACTIONS.items():
        parts = [
            (digit_set, f"{numerator}.numr", FRACTION_NUMERATOR_OFFSET[is_italic], scale),
            (glyph_set, "fraction", (0, 0), 1.0),
            (digit_set, f"{denominator}.dnom", FRACTION_DENOMINATOR_OFFSET[is_italic], scale),
        ]
        if codepoint in cmap or any(name not in source for source, name, _, _ in parts):
            continue
        glyph_pen = TTGlyphPen(None)
        for source, name, (dx, dy), part_scale in parts:
            recording = DecomposingRecordingPen(source)
            source[name].draw(recording)
            recording.replay(TransformPen(glyph_pen, (part_scale, 0, 0, part_scale, dx, dy)))
        glyph_name = f"uni{codepoint:04X}"
        glyph = glyph_pen.glyph()
        glyf_table[glyph_name] = glyph
        glyph.recalcBounds(glyf_table)
        hmtx_table[glyph_name] = (latin_advance, glyph.xMin)
        update_unicode_cmaps(font, codepoint, glyph_name)
        added.append(codepoint)
    return added


def _contour_bounds(glyph_set: Any, glyph_name: str) -> list[Bounds]:
    """Return the bounds of each contour of a glyph."""
    recording = DecomposingRecordingPen(glyph_set)
    glyph_set[glyph_name].draw(recording)
    bounds: list[Bounds] = []
    pen = BoundsPen(None)
    for operator, operands in recording.value:
        getattr(pen, operator)(*operands)
        if operator in ("closePath", "endPath"):
            if pen.bounds is not None:
                bounds.append(pen.bounds)
            pen = BoundsPen(None)
    return bounds


def add_approximately_equal_glyph(font: TTFont, *, shear: float) -> int | None:
    """Add U+2252 (approximately equal to or the image of) built from JetBrains Mono parts.

    A composite of the equal sign and two periods, so each part keeps its hints. The
    dots sit as far from the bars as the divide sign's dots sit from its bar: one over
    the left end of the upper bar, one under the right end of the lower bar. ``shear``
    is the italic slant (tan of the angle); dots move along it.
    """
    codepoint = 0x2252
    glyf_table = cast("Any", font["glyf"])
    if codepoint in font.getBestCmap() or not all(
        name in glyf_table for name in ("equal", "period", "divide")
    ):
        return None
    glyph_set = font.getGlyphSet()
    divide = sorted(_contour_bounds(glyph_set, "divide"), key=lambda b: b[1])
    if len(divide) != 3:
        return None
    gap = divide[2][1] - divide[1][3]

    def upright_bounds(name: str) -> Bounds:
        pen = BoundsPen(glyph_set)
        glyph_set[name].draw(TransformPen(pen, (1, 0, -shear, 1, 0, 0)))
        return pen.bounds

    eq_x0, eq_y0, eq_x1, eq_y1 = upright_bounds("equal")
    dot_x0, dot_y0, dot_x1, dot_y1 = upright_bounds("period")
    top_dy = eq_y1 + gap - dot_y0
    bottom_dy = eq_y0 - gap - dot_y1
    offsets = [
        (eq_x0 - dot_x0 + shear * top_dy, top_dy),
        (eq_x1 - dot_x1 + shear * bottom_dy, bottom_dy),
    ]
    pen = TTGlyphPen(glyf_table)
    pen.addComponent("equal", (1, 0, 0, 1, 0, 0))
    for dx, dy in offsets:
        pen.addComponent("period", (1, 0, 0, 1, round(dx), round(dy)))
    glyph_name = f"uni{codepoint:04X}"
    glyph = pen.glyph()
    glyf_table[glyph_name] = glyph
    glyph.recalcBounds(glyf_table)
    advance = cast("Any", font["hmtx"])["equal"][0]
    cast("Any", font["hmtx"])[glyph_name] = (advance, glyph.xMin)
    update_unicode_cmaps(font, codepoint, glyph_name)
    return codepoint


def widen_wide_glyphs(font: TTFont, latin_advance: int) -> list[int]:
    """Give one-cell glyphs of wide characters (e.g. U+26A1) two cells, centered.

    A glyph that other codepoints or composites also use is copied first. Returns the
    codepoints changed.
    """
    glyf_table = cast("Any", font["glyf"])
    hmtx_table = cast("Any", font["hmtx"])
    cmap = font.getBestCmap()
    users = Counter(cmap.values())
    for glyph_name in list(glyf_table.glyphs):
        glyph = glyf_table[glyph_name]
        if glyph.isComposite():
            users.update(component.glyphName for component in glyph.components)

    shift = latin_advance // 2
    changed: list[int] = []
    for codepoint, glyph_name in sorted(cmap.items()):
        advance, lsb = hmtx_table[glyph_name]
        if advance != latin_advance or cell_width(codepoint, latin_advance) == advance:
            continue
        if unicodedata.category(chr(codepoint)) in ("Mn", "Me", "Cf", "Cc"):
            continue
        glyph = glyf_table[glyph_name]
        if users.get(glyph_name, 0) > 1:
            pen = TTGlyphPen(glyf_table)
            pen.addComponent(glyph_name, (1, 0, 0, 1, shift, 0))
            new_name = f"uni{codepoint:04X}.wide"
            glyf_table[new_name] = pen.glyph()
            glyf_table[new_name].recalcBounds(glyf_table)
            hmtx_table[new_name] = (latin_advance * 2, lsb + shift)
            update_unicode_cmaps(font, codepoint, new_name)
        else:
            if glyph.isComposite():
                for component in glyph.components:
                    component.x += shift
            elif glyph.numberOfContours > 0:
                glyph.coordinates.translate((shift, 0))
            hmtx_table[glyph_name] = (latin_advance * 2, lsb + shift)
            if hasattr(glyph, "xMin"):
                glyph.xMin += shift
                glyph.xMax += shift
        changed.append(codepoint)
    return changed


def merge_name_notices(
    font: TTFont, source_font: TTFont, name_ids: tuple[int, ...] = (0, 7)
) -> None:
    """Append the source font's copyright (0) and trademark (7) notices to ``font``.

    The merged font keeps the Latin font's name records, so without this the
    Pretendard notices would be missing from the font files.
    """
    name_table = font["name"]
    for name_id in name_ids:
        extra = source_font["name"].getDebugName(name_id)
        if not extra:
            continue
        current = (name_table.getDebugName(name_id) or "").rstrip()
        if extra in current:
            continue
        if not current:
            merged = extra
        elif name_id == 0:
            merged = f"{current} {extra}" if current.endswith(".") else f"{current}. {extra}"
        else:
            merged = f"{current}; {extra}"
        name_table.setName(merged, name_id, 3, 1, 0x409)
        if name_table.getName(name_id, 1, 0, 0) is not None:
            name_table.setName(merged, name_id, 1, 0, 0)


def align_side_bearings(font: TTFont) -> int:
    """Make each left side bearing match the recomputed xMin without moving the glyph.

    Rasterizers place an outline at ``header xMin - lsb`` from the origin, using the
    xMin stored in the glyph header. About 600 Nerd Fonts glyphs carry a header
    xMin one unit off from their points. fontTools recomputes the header on save,
    which would shift those glyphs by that unit. Moving the side bearing by the
    same amount keeps every glyph exactly where the source font draws it.
    Returns the number of side bearings changed.
    """
    glyf_table = cast("Any", font["glyf"])
    hmtx_table = cast("Any", font["hmtx"])
    changed = 0
    for name in font.getGlyphOrder():
        glyph = glyf_table[name]
        if glyph.numberOfContours == 0 or not hasattr(glyph, "xMin"):
            continue
        advance, lsb = hmtx_table[name]
        origin_offset = glyph.xMin - lsb
        glyph.recalcBounds(glyf_table)
        new_lsb = glyph.xMin - origin_offset
        if new_lsb != lsb:
            hmtx_table[name] = (advance, new_lsb)
            changed += 1
    return changed


def font_revision(version: str) -> float:
    """Map a ``MAJOR.MINOR`` release to a ``head.fontRevision``: 1.001 -> 1.001.

    MINOR counts thousandths, so the PEP 440 form that package metadata reports for
    1.001, which is 1.1, maps to 1.001 as well.
    """
    match = re.fullmatch(r"(\d+)(?:\.(\d{1,3}))?", version.strip())
    if match is None:
        msg = f"Font version must be MAJOR.MINOR with up to 3 MINOR digits, e.g. 1.001: {version!r}"
        raise ValueError(msg)
    major, minor = int(match.group(1)), int(match.group(2) or 0)
    return round(major + minor / 1000, 3)


def describe_source(font: TTFont) -> str:
    """Return ``family version`` for a source font, e.g. ``Pretendard 1.309``."""
    name_table = font["name"]
    family = name_table.getDebugName(16) or name_table.getDebugName(1) or "?"
    version_string = name_table.getDebugName(5) or ""
    version = re.search(r"Version\s+([0-9][0-9.]*)", version_string)
    nerd_fonts = re.search(r"Nerd Fonts\s+([0-9][0-9.]*)", version_string)
    text = f"{family} {version.group(1) if version else '?'}"
    if nerd_fonts:
        text += f" (Nerd Fonts {nerd_fonts.group(1)})"
    return text


def set_font_version(font: TTFont, version: str, sources: list[TTFont]) -> None:
    """Set ``head.fontRevision`` and the version string (name ID 5) for a release."""
    revision = font_revision(version)
    cast("Any", font["head"]).fontRevision = revision
    text = f"Version {revision:.3f}; " + "; ".join(describe_source(f) for f in sources)
    name_table = font["name"]
    name_table.setName(text, 5, 3, 1, 0x409)
    if name_table.getName(5, 1, 0, 0) is not None:
        name_table.setName(text, 5, 1, 0, 0)


LEGACY_WEIGHTS = ("Regular", "Bold")


def legacy_names(family_name: str, style_name: str) -> tuple[str, str]:
    """Return name IDs 1 and 2 for a typographic family and style.

    Windows groups fonts by name ID 1 into families of at most Regular, Italic, Bold
    and Bold Italic. Other weights move into the family name: "Thin Italic" becomes
    family "<family> Thin" with style "Italic".
    """
    is_italic = style_name.endswith("Italic")
    weight = style_name.removesuffix("Italic").strip() or "Regular"
    if weight in LEGACY_WEIGHTS:
        return family_name, style_name
    return f"{family_name} {weight}", "Italic" if is_italic else "Regular"


def set_project_names(font: TTFont) -> None:
    """Credit Hangyeol Code in the name table and drop records only the Latin source needs.

    Keeps only Windows English records, so the Mac and en-GB copies of the source names
    go. The source's copyright stays after the Hangyeol Code notice; manufacturer,
    designer, URLs, license URL and vendor ID become this project's. FontForge's private
    PfEd table is dropped.
    """
    name_table = font["name"]
    name_table.names = [
        record for record in name_table.names if record.platformID == 3 and record.langID == 0x409
    ]
    source_copyright = (name_table.getDebugName(0) or "").strip()
    values = {
        0: f"{COPYRIGHT_NOTICE}. {source_copyright}" if source_copyright else COPYRIGHT_NOTICE,
        8: AUTHOR,
        9: DESIGNER,
        11: PROJECT_URL,
        12: AUTHOR_URL,
        13: LICENSE_DESCRIPTION,
        14: LICENSE_URL,
    }
    for name_id, value in values.items():
        name_table.setName(value, name_id, 3, 1, 0x409)
    cast("Any", font["OS/2"]).achVendID = VENDOR_ID
    if "PfEd" in font:
        del font["PfEd"]


def update_font_names(
    font: TTFont,
    family_name: str,
    subfamily_name: str,
    typographic_subfamily_name: str | None = None,
) -> None:
    """Update family, subfamily, full, PostScript, and typographic names.

    Name IDs 1 and 2 follow ``legacy_names``; IDs 16 and 17 carry the typographic
    family and style only when they differ from IDs 1 and 2.
    """
    logger.info("Updating font names to %s %s", family_name, subfamily_name)
    name_table = font["name"]

    typographic_subfamily = typographic_subfamily_name or subfamily_name
    legacy_family, legacy_subfamily = legacy_names(family_name, typographic_subfamily)
    ps_family = "".join(family_name.split())
    ps_subfamily = "".join(typographic_subfamily.split())
    ps_name = f"{ps_family}-{ps_subfamily}"
    full_name = f"{family_name} {typographic_subfamily}"
    head_table = cast("Any", font["head"])
    unique_id = f"{ps_name};{head_table.fontRevision:.3f}"

    values = {
        1: legacy_family,
        2: legacy_subfamily,
        3: unique_id,
        4: full_name,
        6: ps_name,
    }
    if (family_name, typographic_subfamily) != (legacy_family, legacy_subfamily):
        values |= {16: family_name, 17: typographic_subfamily}

    for name_id in (*values, 16, 17):
        name_table.removeNames(nameID=name_id)
    for name_id, value in values.items():
        name_table.setName(value, name_id, 3, 1, 0x409)


def update_style_metadata(
    font: TTFont,
    *,
    is_italic: bool,
    css_weight: int | None = None,
    is_regular: bool = False,
) -> None:
    """Set style bits and weight metadata that identify upright and italic variants."""
    head_table = cast("Any", font["head"])
    os2_table = cast("Any", font["OS/2"])

    mac_bold = 1 << 0
    mac_italic = 1 << 1
    fs_italic = 1 << 0
    fs_bold = 1 << 5
    fs_regular = 1 << 6

    if is_italic:
        head_table.macStyle |= mac_italic
        os2_table.fsSelection |= fs_italic
    else:
        head_table.macStyle &= ~mac_italic
        os2_table.fsSelection &= ~fs_italic

    if css_weight is not None:
        os2_table.usWeightClass = css_weight
        if css_weight == WEIGHT_TO_CSS["Bold"]:
            head_table.macStyle |= mac_bold
            os2_table.fsSelection |= fs_bold
        else:
            head_table.macStyle &= ~mac_bold
            os2_table.fsSelection &= ~fs_bold

    if is_regular and not is_italic:
        os2_table.fsSelection |= fs_regular
    else:
        os2_table.fsSelection &= ~fs_regular


def enforce_monospace_flags(font: TTFont) -> None:
    """Set common fixed-pitch indicators."""
    post_table = cast("Any", font["post"])
    post_table.isFixedPitch = 1
    os2_table = cast("Any", font["OS/2"])
    os2_table.panose.bProportion = 9


def merge_os2_ranges(target_font: TTFont, source_font: TTFont) -> None:
    """OR CJK Unicode/codepage range bits into the base font."""
    target_os2 = target_font["OS/2"]
    source_os2 = source_font["OS/2"]
    for field in (
        "ulUnicodeRange1",
        "ulUnicodeRange2",
        "ulUnicodeRange3",
        "ulUnicodeRange4",
        "ulCodePageRange1",
        "ulCodePageRange2",
    ):
        target_value = int(getattr(target_os2, field, 0))
        source_value = int(getattr(source_os2, field, 0))
        setattr(target_os2, field, target_value | source_value)


def update_unicode_cmaps(font: TTFont, codepoint: int, glyph_name: str) -> None:
    """Add a cmap entry to Unicode subtables that can carry normal mappings."""
    for table in font["cmap"].tables:
        if table.format == 14 or not table.isUnicode():
            continue
        table.cmap[codepoint] = glyph_name


def sync_glyph_order(font: TTFont, glyf_table: Any, preferred_order: list[str]) -> list[str]:
    """Synchronize TTFont and glyf glyph order with duplicate names removed."""
    seen: set[str] = set()
    normalized_order: list[str] = []
    for glyph_name in preferred_order:
        if glyph_name in seen or glyph_name not in glyf_table.glyphs:
            continue
        normalized_order.append(glyph_name)
        seen.add(glyph_name)

    for glyph_name in glyf_table.glyphs:
        if glyph_name in seen:
            continue
        normalized_order.append(glyph_name)
        seen.add(glyph_name)

    font.setGlyphOrder(normalized_order)
    glyf_table.glyphOrder = normalized_order
    return normalized_order


def source_glyph_for_codepoint(
    codepoint: int,
    cjk_cmap: dict[int, str],
) -> str | None:
    """Find the Pretendard glyph name for a target CJK/Jamo codepoint."""
    source_codepoint = JAMO_COMPATIBILITY_MAP.get(codepoint, codepoint)
    return cjk_cmap.get(source_codepoint)


def build_hangul_ccmp_features() -> str:
    """Build GSUB ccmp feature text for decomposed Hangul Jamo composition."""
    fea_lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "languagesystem hang dflt;",
        "",
        "feature ccmp {",
    ]

    choseong_list = sorted(CHOSEONG_MAP)
    jungseong_list = sorted(JUNGSEONG_MAP)
    jongseong_list = sorted(JONGSEONG_MAP)

    for c_idx, c_code in enumerate(choseong_list):
        for v_idx, v_code in enumerate(jungseong_list):
            for t_idx, t_code in enumerate(jongseong_list):
                syllable_code = 0xAC00 + (c_idx * 21 * 28) + (v_idx * 28) + (t_idx + 1)
                fea_lines.append(
                    f"    sub uni{c_code:04X} uni{v_code:04X} "
                    f"uni{t_code:04X} by uni{syllable_code:04X};"
                )

    for c_idx, c_code in enumerate(choseong_list):
        for v_idx, v_code in enumerate(jungseong_list):
            syllable_code = 0xAC00 + (c_idx * 21 * 28) + (v_idx * 28)
            fea_lines.append(f"    sub uni{c_code:04X} uni{v_code:04X} by uni{syllable_code:04X};")

    fea_lines.append("} ccmp;")
    return "\n".join(fea_lines)


def build_hangul_ccmp_mapping() -> dict[tuple[str, ...], str]:
    """Build glyph-name mappings for decomposed Hangul Jamo composition."""
    mapping: dict[tuple[str, ...], str] = {}
    choseong_list = sorted(CHOSEONG_MAP)
    jungseong_list = sorted(JUNGSEONG_MAP)
    jongseong_list = sorted(JONGSEONG_MAP)

    for c_idx, c_code in enumerate(choseong_list):
        for v_idx, v_code in enumerate(jungseong_list):
            for t_idx, t_code in enumerate(jongseong_list):
                syllable_code = 0xAC00 + (c_idx * 21 * 28) + (v_idx * 28) + (t_idx + 1)
                mapping[(f"uni{c_code:04X}", f"uni{v_code:04X}", f"uni{t_code:04X}")] = (
                    f"uni{syllable_code:04X}"
                )

    for c_idx, c_code in enumerate(choseong_list):
        for v_idx, v_code in enumerate(jungseong_list):
            syllable_code = 0xAC00 + (c_idx * 21 * 28) + (v_idx * 28)
            mapping[(f"uni{c_code:04X}", f"uni{v_code:04X}")] = f"uni{syllable_code:04X}"

    return mapping


def add_hangul_ccmp_features(font: TTFont) -> None:
    """Compile Hangul ccmp substitutions into the merged font."""
    logger.info("Adding GSUB ccmp lookups for Hangul Jamo support")
    if "GSUB" not in font:
        addOpenTypeFeaturesFromString(font, build_hangul_ccmp_features(), tables=["GSUB"])
        return

    gsub = font["GSUB"].table
    if getattr(gsub, "LookupList", None) is None or getattr(gsub, "FeatureList", None) is None:
        addOpenTypeFeaturesFromString(font, build_hangul_ccmp_features(), tables=["GSUB"])
        return

    subtable = buildLigatureSubstSubtable(build_hangul_ccmp_mapping())
    lookup = buildLookup([subtable], table="GSUB")
    if lookup is None:
        return

    lookup_index = gsub.LookupList.LookupCount
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)

    ccmp_records = [
        record for record in gsub.FeatureList.FeatureRecord if record.FeatureTag == "ccmp"
    ]
    if not ccmp_records:
        feature = new_ot_table("Feature")
        feature.FeatureParams = None
        feature.LookupListIndex = []
        feature.LookupCount = 0

        record = new_ot_table("FeatureRecord")
        record.FeatureTag = "ccmp"
        record.Feature = feature
        gsub.FeatureList.FeatureRecord.append(record)
        gsub.FeatureList.FeatureRecord.sort(key=lambda item: item.FeatureTag)
        gsub.FeatureList.FeatureCount = len(gsub.FeatureList.FeatureRecord)
        ccmp_records = [record]

    for record in ccmp_records:
        record.Feature.LookupListIndex.append(lookup_index)
        record.Feature.LookupCount = len(record.Feature.LookupListIndex)

    logger.info("Appended Hangul ccmp lookup at GSUB lookup index %d", lookup_index)


def _assemble(lines: list[str]) -> bytes:
    """Assemble TrueType instructions written in fontTools assembly syntax."""
    program = ttProgram.Program()
    program.fromAssembly("\n".join(lines))
    return program.getBytecode()


def _append_program(font: TTFont, tag: str, bytecode: bytes) -> None:
    """Append bytecode to the end of the fpgm or prep program."""
    table = cast("Any", font[tag])
    current = table.program.getBytecode() if table.program is not None else b""
    program = ttProgram.Program()
    program.fromBytecode(current + bytecode)
    table.program = program


def add_ppem_shift_hints(
    font: TTFont,
    glyph_names: list[str],
    shifts_px: dict[int, float],
) -> int:
    """Shift the given glyphs vertically by a per-ppem amount with TrueType instructions.

    The prep program stores the shift for the current ppem (F26Dot6) in a new storage
    slot. Each target glyph calls a new fpgm function that touches point 0 in y,
    moves it by the stored amount and shifts the rest of the glyph zone with SHZ.
    Only y-direction moves are used, which DirectWrite/GDI ClearType and FreeType's
    v40 interpreter honor. Sizes without an entry are left untouched.
    """
    shifts = {int(ppem): round(value * 64) for ppem, value in shifts_px.items()}
    shifts = {ppem: value for ppem, value in shifts.items() if value != 0}
    if not shifts or "fpgm" not in font or "prep" not in font:
        return 0

    maxp = cast("Any", font["maxp"])
    function_index = int(maxp.maxFunctionDefs)
    storage_index = int(maxp.maxStorage)

    _append_program(
        font,
        "fpgm",
        _assemble(
            [
                f"PUSH[ ] {function_index}",
                "FDEF[ ]",
                f"PUSH[ ] {storage_index}",
                "RS[ ]",
                "DUP[ ]",
                "IF[ ]",
                "PUSH[ ] 1",
                "SZPS[ ]",
                "SVTCA[0]",
                "PUSH[ ] 0",
                "MDAP[0]",
                "PUSH[ ] 0",
                "SWAP[ ]",
                "SHPIX[ ]",
                "PUSH[ ] 0",
                "SRP1[ ]",
                "PUSH[ ] 1",
                "SHZ[1]",
                "ELSE[ ]",
                "POP[ ]",
                "EIF[ ]",
                "ENDF[ ]",
            ]
        ),
    )

    prep_lines = [f"PUSH[ ] {storage_index} 0", "WS[ ]"]
    for ppem, value in sorted(shifts.items()):
        prep_lines += [
            "MPPEM[ ]",
            f"PUSH[ ] {ppem}",
            "EQ[ ]",
            "IF[ ]",
            f"PUSH[ ] {storage_index} {value}",
            "WS[ ]",
            "EIF[ ]",
        ]
    _append_program(font, "prep", _assemble(prep_lines))

    call = _assemble([f"PUSH[ ] {function_index}", "CALL[ ]"])
    glyf_table = cast("Any", font["glyf"])
    hinted = 0
    for name in glyph_names:
        glyph = glyf_table[name]
        if getattr(glyph, "numberOfContours", 0) <= 0:
            continue
        program = ttProgram.Program()
        program.fromBytecode(call)
        glyph.program = program
        hinted += 1

    maxp.maxFunctionDefs = function_index + 1
    maxp.maxStorage = storage_index + 1
    maxp.maxSizeOfInstructions = max(int(maxp.maxSizeOfInstructions), len(call))
    maxp.maxStackElements = max(int(maxp.maxStackElements), 8)
    logger.info(
        "Added per-ppem shift hints to %d glyphs (function %d, storage %d): %s",
        hinted,
        function_index,
        storage_index,
        ", ".join(f"{ppem}ppem={value / 64:+.3f}px" for ppem, value in sorted(shifts.items())),
    )
    return hinted


def build_merged_font(
    latin_path: str | Path,
    cjk_path: str | Path,
    family_name: str,
    subfamily_name: str,
    korean_scale: float = DEFAULT_KOREAN_SCALE,
    *,
    korean_y_offset: int = 0,
    add_ksx_symbols: bool = False,
    fallback_path: str | Path | None = None,
    prefer_fallback: frozenset[int] = KSX_PREFER_FALLBACK,
    font_version: str | None = None,
    typographic_subfamily_name: str | None = None,
    is_italic: bool = False,
    css_weight: int | None = None,
    fraction_digit_path: str | Path | None = None,
) -> MergedFont:
    """Merge JetBrainsMono Nerd Font Mono with Pretendard CJK glyphs, without hints.

    The caller adds hints and saves; ``hint_glyphs`` lists every glyph taken from
    Pretendard or Noto Sans KR, which the per-ppem Hangul shift applies to.
    ``fraction_digit_path`` is the JetBrainsMono file whose digits the added KS X 1001
    fractions use (default: ``latin_path``; see ``fraction_digit_weight``).
    """
    logger.info("Merging %s + %s", latin_path, cjk_path)
    latin_font = TTFont(str(latin_path))
    realigned = align_side_bearings(latin_font)
    if realigned:
        logger.info("Realigned %d Latin side bearings to their glyph outlines", realigned)
    cjk_font = TTFont(str(cjk_path))
    fallback_font = TTFont(str(fallback_path)) if fallback_path else None

    latin_head = cast("Any", latin_font["head"])
    cjk_head = cast("Any", cjk_font["head"])
    upm_scale = latin_head.unitsPerEm / cjk_head.unitsPerEm
    requested_total_scale = upm_scale * korean_scale

    latin_advance = derive_latin_advance(latin_font)
    korean_advance = calculate_korean_target_width(latin_advance)
    side_guard = default_side_bearing_guard(latin_advance)
    safe_ymin, safe_ymax = get_vertical_safe_bounds(latin_font)

    logger.info(
        "Metrics: latin UPM=%d, cjk UPM=%d, latin advance=%d, korean advance=%d",
        latin_head.unitsPerEm,
        cjk_head.unitsPerEm,
        latin_advance,
        korean_advance,
    )
    logger.info(
        "Korean fitting: korean_scale=%.4f, y_offset=%d, total_scale=%.6f, side_guard=%d, "
        "y_bounds=(%d,%d)",
        korean_scale,
        korean_y_offset,
        requested_total_scale,
        side_guard,
        safe_ymin,
        safe_ymax,
    )

    cjk_cmap = cjk_font.getBestCmap()
    if not cjk_cmap:
        msg = "Pretendard font has no usable cmap table"
        raise ValueError(msg)

    cjk_glyph_set = cjk_font.getGlyphSet()
    glyf_table = latin_font["glyf"]
    hmtx_table = latin_font["hmtx"]
    glyph_order = latin_font.getGlyphOrder()
    glyph_order_set = set(glyph_order)
    codepoints = collect_cjk_codepoints(cjk_cmap)

    copied_count = 0
    capped_codepoints: list[int] = []
    copied_glyph_names: list[str] = []

    for codepoint in codepoints:
        cjk_glyph_name = source_glyph_for_codepoint(codepoint, cjk_cmap)
        if cjk_glyph_name is None or cjk_glyph_name not in cjk_glyph_set:
            continue

        target_glyph_name = f"uni{codepoint:04X}"
        target_width = cell_width(codepoint, latin_advance)
        bounds = get_glyph_bounds(cjk_glyph_set, cjk_glyph_name)
        fitted, y_shift = calculate_centered_fit(
            bounds,
            target_width=target_width,
            requested_scale=requested_total_scale,
            safe_ymin=safe_ymin,
            safe_ymax=safe_ymax,
            side_bearing_guard=side_guard,
            shift_y=korean_y_offset,
        )

        if fitted.capped:
            capped_codepoints.append(codepoint)

        decomposed_pen = DecomposingRecordingPen(cjk_glyph_set)
        cjk_glyph_set[cjk_glyph_name].draw(decomposed_pen)

        glyph_pen = TTGlyphPen(None)
        transform_pen = TransformPen(
            glyph_pen,
            (fitted.scale, 0, 0, fitted.scale, fitted.shift_x, y_shift),
        )
        decomposed_pen.replay(transform_pen)

        glyf_table[target_glyph_name] = glyph_pen.glyph()
        hmtx_table.metrics[target_glyph_name] = (
            target_width,
            fitted.left_side_bearing,
        )
        update_unicode_cmaps(latin_font, codepoint, target_glyph_name)

        if target_glyph_name not in glyph_order_set:
            glyph_order.append(target_glyph_name)
            glyph_order_set.add(target_glyph_name)
        copied_glyph_names.append(target_glyph_name)
        copied_count += 1

    symbol_count = 0
    fallback_count = 0
    if add_ksx_symbols:
        digit_font = TTFont(str(fraction_digit_path or latin_path))
        built = add_fraction_glyphs(
            latin_font, digit_font, is_italic=is_italic, latin_advance=latin_advance
        )
        digit_font.close()
        shear = math.tan(math.radians(-cast("Any", latin_font["post"]).italicAngle))
        approx = add_approximately_equal_glyph(latin_font, shear=shear)
        built += [approx] if approx is not None else []
        logger.info(
            "Built %d KS X 1001 symbols from JetBrains Mono parts: %s",
            len(built),
            " ".join(chr(code) for code in built),
        )
        latin_cmap = latin_font.getBestCmap()
        fallback_cmap: dict[int, str] = {}
        fallback_glyph_set: Any = None
        fallback_scale = fallback_shift = ratio = 0.0
        wght: float | None = None
        matcher: FallbackWeightMatcher | None = None
        if fallback_font is not None:
            fallback_cmap = fallback_font.getBestCmap() or {}
            matcher = FallbackWeightMatcher(cjk_font, fallback_font)
            wght = matcher.wght_for(
                fit_fallback_mapping(
                    cjk_cmap, cjk_glyph_set, fallback_cmap, fallback_font.getGlyphSet()
                )[0]
            )
            location = {"wght": wght} if wght is not None else None
            fallback_glyph_set = fallback_font.getGlyphSet(location=location)
            ratio, offset = fit_fallback_mapping(
                cjk_cmap, cjk_glyph_set, fallback_cmap, fallback_glyph_set
            )
            fallback_scale = requested_total_scale * ratio
            fallback_shift = requested_total_scale * offset + korean_y_offset
            logger.info(
                "Fallback %s: wght=%s, y_pretendard = %.4f * y_fallback %+.1f",
                fallback_path,
                wght,
                ratio,
                offset,
            )

        for codepoint in collect_ksx1001_symbol_codepoints():
            if codepoint in latin_cmap:
                continue
            from_fallback = codepoint in fallback_cmap and (
                codepoint not in cjk_cmap or codepoint in prefer_fallback or is_cjk(codepoint)
            )
            target_width = cell_width(codepoint, latin_advance)
            if from_fallback:
                glyph_set, glyph_name = fallback_glyph_set, fallback_cmap[codepoint]
                scale, shift = fallback_scale, fallback_shift
                if matcher is not None and wght is not None and FALLBACK_STROKE_COMPENSATION > 0:
                    # A glyph shrunk to fit its cell gets thinner strokes; take it from a
                    # heavier instance to win part of that back.
                    for _ in range(2):
                        probe = calculate_fitted_transform(
                            get_glyph_bounds(glyph_set, glyph_name),
                            target_width=target_width,
                            requested_scale=scale,
                            safe_ymin=safe_ymin,
                            safe_ymax=safe_ymax,
                            side_bearing_guard=side_guard,
                            shift_y=shift,
                        )
                        shrink = probe.scale / scale
                        if shrink > 0.98:
                            break
                        heavier = matcher.wght_for(
                            ratio, stem_gain=shrink**-FALLBACK_STROKE_COMPENSATION
                        )
                        glyph_set = fallback_font.getGlyphSet(location={"wght": heavier})
            elif codepoint in cjk_cmap and not is_cjk(codepoint):
                glyph_set, glyph_name = cjk_glyph_set, cjk_cmap[codepoint]
                scale, shift = requested_total_scale, float(korean_y_offset)
            else:
                continue
            copied_glyph_names.append(
                copy_symbol_glyph(
                    latin_font,
                    codepoint,
                    glyph_set=glyph_set,
                    glyph_name=glyph_name,
                    target_width=target_width,
                    requested_scale=scale,
                    shift_y=shift,
                    safe_ymin=safe_ymin,
                    safe_ymax=safe_ymax,
                    side_bearing_guard=side_guard,
                    glyph_order=glyph_order,
                    glyph_order_set=glyph_order_set,
                )
            )
            symbol_count += 1
            fallback_count += from_fallback
        logger.info(
            "Added %d KS X 1001 symbols (%d from Pretendard, %d from fallback)",
            symbol_count,
            symbol_count - fallback_count,
            fallback_count,
        )

    widened = widen_wide_glyphs(latin_font, latin_advance)
    if widened:
        logger.info(
            "Widened %d wide characters to two cells: %s",
            len(widened),
            " ".join(f"U+{code:04X}" for code in widened),
        )
    glyph_order = sync_glyph_order(latin_font, glyf_table, glyph_order)
    merge_os2_ranges(latin_font, cjk_font)
    enforce_monospace_flags(latin_font)
    add_hangul_ccmp_features(latin_font)
    glyph_order = sync_glyph_order(latin_font, glyf_table, glyph_order)
    update_style_metadata(
        latin_font,
        is_italic=is_italic,
        css_weight=css_weight,
        is_regular=legacy_names(family_name, typographic_subfamily_name or subfamily_name)[1]
        == "Regular",
    )
    set_project_names(latin_font)
    if font_version:
        sources = [TTFont(str(latin_path), lazy=True), cjk_font]
        if fallback_font is not None and fallback_count:
            sources.append(fallback_font)
        set_font_version(latin_font, font_version, sources)
    update_font_names(
        latin_font,
        family_name,
        subfamily_name,
        typographic_subfamily_name=typographic_subfamily_name,
    )
    merge_name_notices(latin_font, cjk_font)
    if fallback_font is not None and fallback_count:
        merge_name_notices(latin_font, fallback_font)

    glyph_names = set(glyph_order)
    glyf_names = set(glyf_table.glyphs)
    if len(glyph_order) != len(glyf_table.glyphs):
        logger.warning(
            "Glyph bookkeeping mismatch: order=%d unique_order=%d glyf=%d "
            "missing_glyf=%d extra_glyf=%d",
            len(glyph_order),
            len(glyph_names),
            len(glyf_table.glyphs),
            len(glyph_names - glyf_names),
            len(glyf_names - glyph_names),
        )
    if capped_codepoints:
        preview = ", ".join(f"U+{code:04X}" for code in capped_codepoints[:12])
        if len(capped_codepoints) > 12:
            preview += ", ..."
        logger.info("Capped %d glyphs to avoid clipping: %s", len(capped_codepoints), preview)
    logger.info("Copied %d CJK glyphs", copied_count)
    cjk_font.close()

    stats = MergeStats(
        copied_count=copied_count,
        capped_count=len(capped_codepoints),
        latin_advance=latin_advance,
        korean_advance=korean_advance,
        requested_total_scale=requested_total_scale,
        symbol_count=symbol_count,
    )
    return MergedFont(font=latin_font, stats=stats, hint_glyphs=copied_glyph_names)


def merge_fonts(
    latin_path: str | Path,
    cjk_path: str | Path,
    output_path: str | Path,
    family_name: str,
    subfamily_name: str,
    korean_scale: float = DEFAULT_KOREAN_SCALE,
    *,
    korean_hint_shifts: dict[int, float] | None = None,
    **options: Any,
) -> MergeStats:
    """Build one Hangyeol Code font: merge, add the Hangul hints and save it."""
    merged = build_merged_font(
        latin_path, cjk_path, family_name, subfamily_name, korean_scale, **options
    )
    if korean_hint_shifts:
        add_ppem_shift_hints(merged.font, merged.hint_glyphs, korean_hint_shifts)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    merged.font.save(str(output))
    merged.font.close()
    logger.info("Wrote %s", output)
    return merged.stats
