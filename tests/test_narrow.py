"""Tests for Hangyeol Code Narrow (hangyeol_code.narrow)."""

from __future__ import annotations

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from hangyeol_code import narrow
from hangyeol_code.cli import shifts_for

BOXES = {
    "H": (0x48, (100, 0, 500, 730)),  # roomy: only moved
    "W": (0x57, (10, 0, 590, 730)),  # tight: squeezed to the minimum margin
    "ampersand": (0x26, (-20, 0, 620, 730)),  # already over the edges: full 10%
    "icon": (0xF09B, (0, 60, 600, 660)),  # square icon: scaled both ways
    "l": (0x6C, (20, 0, 400, 730)),  # one-sided: squeezed, or shifted with max_shift
    "d": (0x64, (0, 0, 450, 730)),  # one-sided beyond max_shift: shifted, then squeezed
}
SHIFT_SETTINGS = narrow.NarrowSettings()  # 7.5-unit margins, shifts up to 20 units
CENTRED_SETTINGS = narrow.NarrowSettings(min_margin=8, max_shift=0)


def make_font(boxes=BOXES):
    fb = FontBuilder(1000, isTTF=True)
    order = [".notdef", *boxes]
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({cp: name for name, (cp, _) in boxes.items()})
    glyphs, metrics = {}, {}
    for name in order:
        pen = TTGlyphPen(None)
        x0, y0, x1, y1 = boxes.get(name, (None, (50, 0, 550, 700)))[1]
        pen.moveTo((x0, y0))
        pen.lineTo((x0, y1))
        pen.lineTo((x1, y1))
        pen.lineTo((x1, y0))
        pen.closePath()
        glyphs[name] = pen.glyph()
        metrics[name] = (600, x0)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=1020, descent=-300)
    fb.setupNameTable({"familyName": "Hangyeol Code", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    return fb.font


def bounds(font, name):
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return pen.bounds


@pytest.fixture
def narrowed():
    font = make_font()
    plans, _ = narrow.narrow_font(font, None, narrow.NarrowSettings())
    return font, plans


def test_roomy_glyph_is_only_moved(narrowed):
    font, plans = narrowed
    assert plans["H"].sx == 1.0
    assert font["hmtx"]["H"][0] == 540
    assert bounds(font, "H") == (70, 0, 470, 730)


def test_tight_glyph_keeps_minimum_margin(narrowed):
    font, plans = narrowed
    assert plans["W"].sx == pytest.approx(262.5 / 290)
    x0, _, x1, _ = bounds(font, "W")
    assert x0 == pytest.approx(7.5, abs=0.5)
    assert 540 - x1 == pytest.approx(7.5, abs=0.5)


def test_overflowing_glyph_shrinks_by_the_limit(narrowed):
    font, plans = narrowed
    assert plans["ampersand"].sx == pytest.approx(0.9)
    assert bounds(font, "ampersand")[0] == pytest.approx(-18, abs=0.5)


def test_square_icon_scales_both_ways(narrowed):
    font, plans = narrowed
    plan = plans["icon"]
    assert plan.sx == pytest.approx(0.9)
    assert plan.sy == pytest.approx(0.9)
    x0, y0, x1, y1 = bounds(font, "icon")
    assert (x0, x1) == pytest.approx((0, 540), abs=0.5)
    assert (y0, y1) == pytest.approx((90, 630), abs=0.5)


def test_hint_groups_split_added_glyphs_and_icons(narrowed):
    _, plans = narrowed
    groups = narrow.hint_groups(plans, added={"H", "W"})
    assert groups == {"hangul": ["H", "W"], "icons": ["icon"], "symbols": []}


def test_shifts_for_falls_back_to_star_and_single_entry():
    assert shifts_for({"Regular": {"12": 0.125}}, "Bold") == {12: 0.125}
    assert shifts_for({"*": {"10": -0.125}, "Bold": {"10": 0}}, "Thin") == {10: -0.125}
    assert shifts_for({"Regular": {"12": 0.1}, "Bold": {"12": 0.2}}, "Thin") is None


def test_shift_moves_a_one_sided_glyph_instead_of_squeezing_it():
    font = make_font()
    plans, _ = narrow.narrow_font(font, None, SHIFT_SETTINGS)
    assert plans["H"].dx == 0 and plans["H"].sx == 1.0
    assert bounds(font, "H") == (70, 0, 470, 730)
    assert plans["l"].dx == pytest.approx(17.5)
    assert plans["l"].sx == 1.0
    assert bounds(font, "l") == pytest.approx((7.5, 0, 387.5, 730), abs=0.5)


def test_shift_stops_at_max_shift_and_squeezes_the_rest():
    font = make_font()
    plans, _ = narrow.narrow_font(font, None, SHIFT_SETTINGS)
    assert plans["d"].dx == pytest.approx(20)  # 37.5 would fit it without squeezing
    assert plans["d"].sx == pytest.approx(262.5 / 280)
    assert bounds(font, "d")[0] == pytest.approx(7.5, abs=0.5)


def test_shift_leaves_centred_and_overflowing_glyphs_in_place():
    font = make_font()
    plans, _ = narrow.narrow_font(font, None, SHIFT_SETTINGS)
    assert plans["W"].dx == 0
    assert plans["W"].sx == pytest.approx(262.5 / 290)
    assert plans["ampersand"].dx == 0
    assert bounds(font, "ampersand")[0] == pytest.approx(-18, abs=0.5)


def test_italic_shifts_as_far_as_its_upright_glyph():
    upright = make_font()
    italic = make_font({**BOXES, "l": (0x6C, (40, 0, 420, 730))})
    plans, _ = narrow.narrow_font(italic, upright, SHIFT_SETTINGS)
    assert plans["l"].dx == pytest.approx(17.5)  # its own fit would not move it
    assert bounds(italic, "l") == pytest.approx((27.5, 0, 407.5, 730), abs=0.5)


def test_max_shift_zero_keeps_glyphs_centred():
    font = make_font()
    plans, _ = narrow.narrow_font(font, None, CENTRED_SETTINGS)
    assert plans["l"].dx == 0
    assert plans["l"].sx == pytest.approx(262 / 280)  # squeezed to 8 units on the left
    assert plans["W"].sx == pytest.approx(262 / 290)
