"""Unit tests for the builder logic."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

from hangyeol_code.builder import (
    AUTHOR,
    COPYRIGHT_NOTICE,
    DEFAULT_VARIANTS,
    calculate_centered_fit,
    calculate_fitted_transform,
    calculate_korean_target_width,
    cell_width,
    cell_width_mismatches,
    collect_cjk_codepoints,
    collect_ksx1001_symbol_codepoints,
    derive_latin_advance,
    enforce_monospace_flags,
    fraction_digit_weight,
    get_variants_by_names,
    is_cjk,
    legacy_names,
    make_font_variant,
    merge_fonts,
    merge_name_notices,
    set_project_names,
    update_font_names,
    update_style_metadata,
)


class DummyPanose:
    """Minimal Panose object for fixed-pitch flag tests."""

    bProportion = 0


def make_width_font(widths: dict[str, int]) -> TTFont:
    """Create a minimal font with cmap and hmtx tables for metric tests."""
    font = TTFont()
    cmap = newTable("cmap")
    cmap.tableVersion = 0
    subtable = CmapSubtable.newSubtable(4)
    subtable.platformID = 3
    subtable.platEncID = 1
    subtable.language = 0
    subtable.cmap = {ord(char): char for char in widths}
    cmap.tables = [subtable]
    font["cmap"] = cmap

    hmtx = newTable("hmtx")
    hmtx.metrics = {char: (width, 0) for char, width in widths.items()}
    font["hmtx"] = hmtx
    return font


def make_name_font() -> TTFont:
    """Create a minimal font with name and head tables."""
    font = TTFont()
    name = newTable("name")
    name.names = []
    font["name"] = name
    head = newTable("head")
    head.fontRevision = 1.0
    font["head"] = head
    return font


def make_style_font() -> TTFont:
    """Create a minimal font with head and OS/2 tables."""
    font = TTFont()
    head = newTable("head")
    head.macStyle = 0
    font["head"] = head
    os2 = newTable("OS/2")
    os2.fsSelection = 1 << 6
    os2.usWeightClass = 400
    font["OS/2"] = os2
    return font


def test_default_variants_cover_full_matrix() -> None:
    suffixes = [variant.output_suffix for variant in DEFAULT_VARIANTS]

    assert len(DEFAULT_VARIANTS) == 16
    assert suffixes == [
        "Thin",
        "ThinItalic",
        "ExtraLight",
        "ExtraLightItalic",
        "Light",
        "LightItalic",
        "Regular",
        "Italic",
        "Medium",
        "MediumItalic",
        "SemiBold",
        "SemiBoldItalic",
        "Bold",
        "BoldItalic",
        "ExtraBold",
        "ExtraBoldItalic",
    ]


def test_regular_italic_variant_uses_special_source_filename() -> None:
    variant = make_font_variant("Regular", "italic")

    assert variant.output_suffix == "Italic"
    assert variant.subfamily_name == "Italic"
    assert variant.latin_filename == "JetBrainsMonoNerdFontMono-Italic.ttf"
    assert variant.cjk_weight_name == "Regular"
    assert variant.css_weight == 400
    assert variant.is_italic is True


def test_get_variants_by_names_rejects_unknown_variant() -> None:
    with pytest.raises(ValueError, match="Unsupported variant"):
        get_variants_by_names(["Regular", "BookItalic"])


def test_is_cjk_supported_ranges() -> None:
    assert is_cjk(0xAC00) is True
    assert is_cjk(0xD7A3) is True
    assert is_cjk(0x1100) is True
    assert is_cjk(0x3131) is True
    assert is_cjk(0xA960) is True
    assert is_cjk(0xD7FF) is True
    assert is_cjk(0x4E00) is True
    assert is_cjk(0x3001) is True
    assert is_cjk(0xFF01) is True
    assert is_cjk(ord("A")) is False


def test_collect_cjk_codepoints_adds_required_jamo() -> None:
    codepoints = collect_cjk_codepoints({0xAC00: "uniAC00", ord("A"): "A"})
    assert 0xAC00 in codepoints
    assert 0x1100 in codepoints
    assert 0x1161 in codepoints
    assert 0x11A8 in codepoints
    assert ord("A") not in codepoints


def test_derive_latin_advance_from_monospaced_sample() -> None:
    font = make_width_font({char: 600 for char in " A0Hinmw"})
    assert derive_latin_advance(font) == 600


def test_derive_latin_advance_rejects_non_monospaced_sample() -> None:
    font = make_width_font({char: 600 for char in " A0Hinmw"})
    font["hmtx"].metrics["m"] = (700, 0)
    with pytest.raises(ValueError, match="not monospaced"):
        derive_latin_advance(font)


def test_calculate_korean_target_width() -> None:
    assert calculate_korean_target_width(600) == 1200


def test_calculate_korean_target_width_rejects_invalid_advance() -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_korean_target_width(0)


def test_fitted_transform_centers_uncapped_glyph() -> None:
    fitted = calculate_fitted_transform(
        (100, -100, 900, 700),
        target_width=1200,
        requested_scale=1.0,
        safe_ymin=-300,
        safe_ymax=900,
        side_bearing_guard=20,
    )

    assert fitted.capped is False
    assert fitted.transformed_bounds == pytest.approx((200, -100, 1000, 700))
    assert fitted.left_side_bearing == 200


def test_fitted_transform_caps_unsafe_scale() -> None:
    fitted = calculate_fitted_transform(
        (0, -100, 1000, 800),
        target_width=1200,
        requested_scale=1.3,
        safe_ymin=-300,
        safe_ymax=900,
        side_bearing_guard=20,
    )

    assert fitted.capped is True
    assert fitted.scale == pytest.approx(1.125)
    assert fitted.transformed_bounds is not None
    assert fitted.transformed_bounds[0] >= 20
    assert fitted.transformed_bounds[2] <= 1180
    assert fitted.transformed_bounds[3] <= 900


def test_update_font_names_sets_required_records() -> None:
    font = make_name_font()
    update_font_names(font, "Hangyeol Code", "Regular")

    name_table = font["name"]
    assert name_table.getName(1, 3, 1, 0x409).toUnicode() == "Hangyeol Code"
    assert name_table.getName(2, 3, 1, 0x409).toUnicode() == "Regular"
    assert name_table.getName(4, 3, 1, 0x409).toUnicode() == "Hangyeol Code Regular"
    assert name_table.getName(6, 3, 1, 0x409).toUnicode() == "HangyeolCode-Regular"
    assert name_table.getName(16, 3, 1, 0x409) is None
    assert name_table.getName(17, 3, 1, 0x409) is None
    assert all(record.platformID == 3 for record in name_table.names)


def test_update_font_names_moves_other_weights_into_the_family_name() -> None:
    font = make_name_font()
    update_font_names(font, "Hangyeol Code", "Thin Italic")

    name_table = font["name"]
    assert name_table.getName(1, 3, 1, 0x409).toUnicode() == "Hangyeol Code Thin"
    assert name_table.getName(2, 3, 1, 0x409).toUnicode() == "Italic"
    assert name_table.getName(4, 3, 1, 0x409).toUnicode() == "Hangyeol Code Thin Italic"
    assert name_table.getName(6, 3, 1, 0x409).toUnicode() == "HangyeolCode-ThinItalic"
    assert name_table.getName(16, 3, 1, 0x409).toUnicode() == "Hangyeol Code"
    assert name_table.getName(17, 3, 1, 0x409).toUnicode() == "Thin Italic"


def test_legacy_names_keep_only_regular_and_bold_in_the_family() -> None:
    assert legacy_names("Hangyeol Code", "Regular") == ("Hangyeol Code", "Regular")
    assert legacy_names("Hangyeol Code", "Italic") == ("Hangyeol Code", "Italic")
    assert legacy_names("Hangyeol Code", "Bold Italic") == ("Hangyeol Code", "Bold Italic")
    assert legacy_names("Hangyeol Code", "SemiBold") == ("Hangyeol Code SemiBold", "Regular")
    assert legacy_names("Hangyeol Code Narrow", "ExtraLight Italic") == (
        "Hangyeol Code Narrow ExtraLight",
        "Italic",
    )


def test_set_project_names_credits_the_project_and_drops_source_extras() -> None:
    font = make_name_font()
    font["OS/2"] = newTable("OS/2")
    font["OS/2"].achVendID = "JB  "
    name_table = font["name"]
    name_table.setName("Copyright 2020 Latin Authors", 0, 3, 1, 0x409)
    name_table.setName("JetBrains", 8, 3, 1, 0x409)
    name_table.setName("Latin Family", 16, 3, 1, 0x809)
    name_table.setName("Latin Family", 1, 1, 0, 0)

    set_project_names(font)

    assert name_table.getDebugName(0) == f"{COPYRIGHT_NOTICE}. Copyright 2020 Latin Authors"
    assert name_table.getDebugName(8) == AUTHOR
    assert name_table.getDebugName(14) == "https://openfontlicense.org"
    assert {(r.platformID, r.langID) for r in name_table.names} == {(3, 0x409)}
    assert font["OS/2"].achVendID == "NONE"


def test_update_font_names_supports_italic_postscript_names() -> None:
    font = make_name_font()
    update_font_names(font, "Hangyeol Code", "Bold Italic")

    name_table = font["name"]
    assert name_table.getName(2, 3, 1, 0x409).toUnicode() == "Bold Italic"
    assert name_table.getName(4, 3, 1, 0x409).toUnicode() == "Hangyeol Code Bold Italic"
    assert name_table.getName(6, 3, 1, 0x409).toUnicode() == "HangyeolCode-BoldItalic"
    assert name_table.getName(17, 3, 1, 0x409) is None  # a legacy style needs no ID 17


def test_update_style_metadata_sets_italic_and_bold_bits() -> None:
    font = make_style_font()
    update_style_metadata(font, is_italic=True, css_weight=700)

    assert font["head"].macStyle & (1 << 0)
    assert font["head"].macStyle & (1 << 1)
    assert font["OS/2"].fsSelection & (1 << 0)
    assert font["OS/2"].fsSelection & (1 << 5)
    assert not font["OS/2"].fsSelection & (1 << 6)
    assert font["OS/2"].usWeightClass == 700


def test_update_style_metadata_leaves_extrabold_unlinked() -> None:
    font = make_style_font()
    update_style_metadata(font, is_italic=False, css_weight=800, is_regular=True)

    assert not font["head"].macStyle & (1 << 0)
    assert not font["OS/2"].fsSelection & (1 << 5)
    assert font["OS/2"].fsSelection & (1 << 6)
    assert font["OS/2"].usWeightClass == 800


def test_update_style_metadata_sets_regular_upright_bits() -> None:
    font = make_style_font()
    update_style_metadata(font, is_italic=False, css_weight=400, is_regular=True)

    assert not font["head"].macStyle & (1 << 0)
    assert not font["head"].macStyle & (1 << 1)
    assert not font["OS/2"].fsSelection & (1 << 0)
    assert not font["OS/2"].fsSelection & (1 << 5)
    assert font["OS/2"].fsSelection & (1 << 6)
    assert font["OS/2"].usWeightClass == 400


def test_enforce_monospace_flags() -> None:
    font = TTFont()
    post = newTable("post")
    post.isFixedPitch = 0
    font["post"] = post
    os2 = newTable("OS/2")
    os2.panose = DummyPanose()
    font["OS/2"] = os2

    enforce_monospace_flags(font)

    assert font["post"].isFixedPitch == 1
    assert font["OS/2"].panose.bProportion == 9


def test_integration_merge_skips_without_upstream_fonts(tmp_path: Path) -> None:
    latin_path = Path("upstream/jetbrainsmono/JetBrainsMonoNerdFontMono-Regular.ttf")
    cjk_path = Path("upstream/pretendard/Pretendard-Regular.ttf")
    if not latin_path.exists() or not cjk_path.exists():
        pytest.skip("upstream fonts have not been downloaded")

    output_path = tmp_path / "HangyeolCode-Regular.ttf"
    stats = merge_fonts(
        latin_path=latin_path,
        cjk_path=cjk_path,
        output_path=output_path,
        family_name="Hangyeol Code",
        subfamily_name="Regular",
    )

    font = TTFont(str(output_path))
    cmap = font.getBestCmap()
    features = [record.FeatureTag for record in font["GSUB"].table.FeatureList.FeatureRecord]
    assert stats.copied_count > 10_000
    assert font["hmtx"].metrics[cmap[ord("가")]][0] == font["hmtx"].metrics[cmap[ord("A")]][0] * 2
    assert font["name"].getName(1, 3, 1, 0x409).toUnicode() == "Hangyeol Code"
    assert font["post"].isFixedPitch == 1
    assert "calt" in features
    assert "ccmp" in features
    font.close()


def test_integration_merge_symbols_follow_cell_widths(tmp_path: Path) -> None:
    latin_path = Path("upstream/jetbrainsmono/JetBrainsMonoNerdFontMono-Thin.ttf")
    digit_path = Path("upstream/jetbrainsmono/JetBrainsMonoNerdFontMono-Light.ttf")
    cjk_path = Path("upstream/pretendard/Pretendard-Thin.ttf")
    fallback_path = Path("upstream/noto/NotoSansKR[wght].ttf")
    if not all(path.exists() for path in (latin_path, digit_path, cjk_path, fallback_path)):
        pytest.skip("upstream fonts have not been downloaded")

    output_path = tmp_path / "HangyeolCode-Thin.ttf"
    merge_fonts(
        latin_path=latin_path,
        cjk_path=cjk_path,
        output_path=output_path,
        family_name="Hangyeol Code",
        subfamily_name="Thin",
        add_ksx_symbols=True,
        fallback_path=fallback_path,
        fraction_digit_path=digit_path,
        css_weight=100,
    )

    font = TTFont(str(output_path))
    cmap = font.getBestCmap()
    assert set(collect_ksx1001_symbol_codepoints()) <= set(cmap)
    assert cell_width_mismatches(font, 600) == []
    assert font["name"].getDebugName(1) == "Hangyeol Code Thin"
    assert font["name"].getDebugName(2) == "Regular"
    assert font["OS/2"].fsSelection & (1 << 6)
    font.close()


def test_integration_merge_italic_metadata_skips_without_upstream_fonts(tmp_path: Path) -> None:
    variant = make_font_variant("Regular", "italic")
    latin_path = Path("upstream/jetbrainsmono") / variant.latin_filename
    cjk_path = Path("upstream/pretendard/Pretendard-Regular.ttf")
    if not latin_path.exists() or not cjk_path.exists():
        pytest.skip("upstream italic fonts have not been downloaded")

    output_path = tmp_path / "HangyeolCode-Italic.ttf"
    stats = merge_fonts(
        latin_path=latin_path,
        cjk_path=cjk_path,
        output_path=output_path,
        family_name="Hangyeol Code",
        subfamily_name=variant.subfamily_name,
        typographic_subfamily_name=variant.typographic_subfamily_name,
        is_italic=variant.is_italic,
        css_weight=variant.css_weight,
    )

    font = TTFont(str(output_path))
    cmap = font.getBestCmap()
    features = [record.FeatureTag for record in font["GSUB"].table.FeatureList.FeatureRecord]
    assert stats.copied_count > 10_000
    assert font["hmtx"].metrics[cmap[ord("가")]][0] == font["hmtx"].metrics[cmap[ord("A")]][0] * 2
    assert font["name"].getName(2, 3, 1, 0x409).toUnicode() == "Italic"
    assert font["name"].getName(6, 3, 1, 0x409).toUnicode() == "HangyeolCode-Italic"
    assert font["head"].macStyle & (1 << 1)
    assert font["OS/2"].fsSelection & (1 << 0)
    assert "calt" in features
    assert "ccmp" in features
    font.close()


def test_full_matrix_integration_when_enabled(tmp_path: Path) -> None:
    if os.environ.get("HANGYEOL_RUN_FULL_INTEGRATION") != "1":
        pytest.skip("set HANGYEOL_RUN_FULL_INTEGRATION=1 to build the full variant matrix")

    missing_sources: list[Path] = []
    for variant in DEFAULT_VARIANTS:
        latin_path = Path("upstream/jetbrainsmono") / variant.latin_filename
        cjk_path = Path("upstream/pretendard") / f"Pretendard-{variant.cjk_weight_name}.ttf"
        if not latin_path.exists():
            missing_sources.append(latin_path)
        if not cjk_path.exists():
            missing_sources.append(cjk_path)
    if missing_sources:
        preview = ", ".join(str(path) for path in missing_sources[:4])
        pytest.skip(f"upstream fonts missing: {preview}")

    for variant in DEFAULT_VARIANTS:
        latin_path = Path("upstream/jetbrainsmono") / variant.latin_filename
        cjk_path = Path("upstream/pretendard") / f"Pretendard-{variant.cjk_weight_name}.ttf"
        output_path = tmp_path / f"HangyeolCode-{variant.output_suffix}.ttf"
        merge_fonts(
            latin_path=latin_path,
            cjk_path=cjk_path,
            output_path=output_path,
            family_name="Hangyeol Code",
            subfamily_name=variant.subfamily_name,
            typographic_subfamily_name=variant.typographic_subfamily_name,
            is_italic=variant.is_italic,
            css_weight=variant.css_weight,
        )

        font = TTFont(str(output_path))
        cmap = font.getBestCmap()
        features = [record.FeatureTag for record in font["GSUB"].table.FeatureList.FeatureRecord]
        assert font["hmtx"].metrics[cmap[ord("가")]][0] == (
            font["hmtx"].metrics[cmap[ord("A")]][0] * 2
        )
        assert bool(font["head"].macStyle & (1 << 1)) is variant.is_italic
        assert bool(font["OS/2"].fsSelection & (1 << 0)) is variant.is_italic
        assert cmap[0xE0B0]
        assert "ccmp" in features
        font.close()


def test_fitted_transform_applies_vertical_shift() -> None:
    transform = calculate_fitted_transform(
        (100, -150, 1900, 1650),
        target_width=1200,
        requested_scale=0.5,
        safe_ymin=-300,
        safe_ymax=1020,
        side_bearing_guard=12,
        shift_y=-25,
    )
    assert transform.transformed_bounds is not None
    assert transform.transformed_bounds[1] == pytest.approx(-150 * 0.5 - 25)
    assert transform.transformed_bounds[3] == pytest.approx(1650 * 0.5 - 25)


def test_collect_ksx1001_symbol_codepoints_covers_symbol_rows_only() -> None:
    codepoints = collect_ksx1001_symbol_codepoints()
    assert {0x203B, 0x2605, 0x2103, 0x321C, 0x3395, 0x2460, 0x3042, 0x30A2} <= set(codepoints)
    assert 0x327E in codepoints  # added in KS X 1001:2002
    assert 0xAC00 not in codepoints
    assert all(not (0x4E00 <= code <= 0x9FFF) for code in codepoints)
    assert len(codepoints) == len(set(codepoints)) == 988


def test_cell_width_follows_east_asian_width() -> None:
    assert cell_width(0x203B, 600) == 600  # reference mark, ambiguous
    assert cell_width(0x2160, 600) == 600  # Roman numeral one, ambiguous
    assert cell_width(0x321C, 600) == 1200  # parenthesized Hangul, wide
    assert cell_width(0x3042, 600) == 1200  # hiragana a, wide
    assert cell_width(0x26A1, 600) == 1200  # high voltage sign, wide
    assert cell_width(0xFFA1, 600) == 600  # half-width Hangul kiyeok
    assert cell_width(0x1161, 600) == 1200  # conjoining vowel a keeps two cells


def test_cell_width_mismatches_reports_wrong_advances() -> None:
    font = make_width_font({"A": 600, "가": 1200, "ﾡ": 1200, "※": 600, "⚡": 600})
    assert cell_width_mismatches(font, 600) == [(0x26A1, 600), (0xFFA1, 1200)]


def test_fraction_digit_weight_steps_up_two_weights() -> None:
    assert fraction_digit_weight("Thin") == "Light"
    assert fraction_digit_weight("Regular") == "SemiBold"
    assert fraction_digit_weight("Bold") == "ExtraBold"
    assert fraction_digit_weight("ExtraBold") == "ExtraBold"


def test_centered_fit_keeps_vertical_center_of_capped_glyph() -> None:
    bounds = (0, 0, 2000, 1000)
    requested_scale = 0.5
    fitted, y_shift = calculate_centered_fit(
        bounds,
        target_width=600,
        requested_scale=requested_scale,
        safe_ymin=-300,
        safe_ymax=1020,
        side_bearing_guard=12,
        shift_y=-25,
    )
    assert fitted.capped
    assert fitted.transformed_bounds is not None
    center = (fitted.transformed_bounds[1] + fitted.transformed_bounds[3]) / 2
    assert center == pytest.approx(500 * requested_scale - 25)
    assert fitted.transformed_bounds[2] - fitted.transformed_bounds[0] <= 600 - 24 + 1e-6
    assert y_shift > -25


def test_merge_name_notices_appends_source_copyright_once() -> None:
    font = make_name_font()
    font["name"].setName("Copyright 2020 Latin Authors", 0, 3, 1, 0x409)
    font["name"].setName("Latin is a trademark of A", 7, 3, 1, 0x409)
    source = make_name_font()
    source["name"].setName("Copyright 2023 CJK Author", 0, 3, 1, 0x409)
    source["name"].setName("CJK is a trademark of B", 7, 3, 1, 0x409)
    merge_name_notices(font, source)
    merge_name_notices(font, source)
    assert font["name"].getDebugName(0) == "Copyright 2020 Latin Authors. Copyright 2023 CJK Author"
    assert font["name"].getDebugName(7) == "Latin is a trademark of A; CJK is a trademark of B"


def test_centered_fit_leaves_uncapped_glyph_alone() -> None:
    fitted, y_shift = calculate_centered_fit(
        (0, 0, 800, 1000),
        target_width=600,
        requested_scale=0.5,
        safe_ymin=-300,
        safe_ymax=1020,
        side_bearing_guard=12,
        shift_y=-25,
    )
    assert not fitted.capped
    assert y_shift == -25


def make_hintable_font() -> TTFont:
    """Create a tiny TrueType font with empty fpgm/prep programs and one square glyph."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables import ttProgram

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "uniAC00"])
    builder.setupCharacterMap({0xAC00: "uniAC00"})
    glyphs = {}
    for name in (".notdef", "uniAC00"):
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0))
        pen.lineTo((100, 700))
        pen.lineTo((1100, 700))
        pen.lineTo((1100, 0))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({".notdef": (1200, 100), "uniAC00": (1200, 100)})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupNameTable({"familyName": "HintTest", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    font = builder.font
    for tag in ("fpgm", "prep"):
        table = newTable(tag)
        table.program = ttProgram.Program()
        table.program.fromBytecode(b"")
        font[tag] = table
    return font


def test_align_side_bearings_keeps_glyph_position(tmp_path: Path) -> None:
    from fontTools.pens.recordingPen import DecomposingRecordingPen

    from hangyeol_code.builder import align_side_bearings

    font = make_hintable_font()
    # Mimic a Nerd Fonts glyph whose header xMin and lsb are one unit left of its points.
    font["hmtx"]["uniAC00"] = (1200, 99)
    stale = tmp_path / "stale.ttf"
    font.save(str(stale), reorderTables=False)
    raw = bytearray(stale.read_bytes())
    source = TTFont(str(stale))
    offset = source.reader.tables["glyf"].offset + source["loca"][source.getGlyphID("uniAC00")]
    raw[offset + 2 : offset + 4] = (99).to_bytes(2, "big")
    stale.write_bytes(bytes(raw))

    def drawn(path: Path) -> list:
        loaded = TTFont(str(path))
        pen = DecomposingRecordingPen(loaded.getGlyphSet())
        loaded.getGlyphSet()["uniAC00"].draw(pen)
        return pen.value

    expected = drawn(stale)
    font = TTFont(str(stale))
    assert align_side_bearings(font) == 1
    assert font["hmtx"]["uniAC00"] == (1200, 100)
    fixed = tmp_path / "fixed.ttf"
    font.save(str(fixed))
    assert drawn(fixed) == expected
    assert align_side_bearings(TTFont(str(fixed))) == 0


def test_add_ppem_shift_hints_installs_programs() -> None:
    from hangyeol_code.builder import add_ppem_shift_hints

    font = make_hintable_font()
    functions_before = font["maxp"].maxFunctionDefs
    storage_before = font["maxp"].maxStorage
    hinted = add_ppem_shift_hints(font, ["uniAC00"], {12: 0.25, 13: 0.0, 16: -0.5})
    assert hinted == 1
    assert font["maxp"].maxFunctionDefs == functions_before + 1
    assert font["maxp"].maxStorage == storage_before + 1
    program = font["glyf"]["uniAC00"].program.getAssembly()
    assert any("CALL" in line for line in program)
    prep = " ".join(font["prep"].program.getAssembly())
    assert "MPPEM" in prep and "WS" in prep
    # A zero-only table must not add anything.
    assert add_ppem_shift_hints(make_hintable_font(), ["uniAC00"], {12: 0.0}) == 0


def test_add_ppem_shift_hints_moves_outline_in_freetype(tmp_path: Path) -> None:
    freetype = pytest.importorskip("freetype")
    from hangyeol_code.builder import add_ppem_shift_hints

    font = make_hintable_font()
    add_ppem_shift_hints(font, ["uniAC00"], {12: 0.25, 16: -0.5})
    path = tmp_path / "hinted.ttf"
    font.save(str(path))

    face = freetype.Face(str(path))

    def y_min(ppem: int, flags: int) -> float:
        face.set_pixel_sizes(0, ppem)
        face.load_char(chr(0xAC00), flags | freetype.FT_LOAD_NO_BITMAP)
        return face.glyph.outline.get_bbox().yMin / 64

    for ppem, expected in ((11, 0.0), (12, 0.25), (16, -0.5), (17, 0.0)):
        hinted = y_min(ppem, freetype.FT_LOAD_DEFAULT)
        unhinted = y_min(ppem, freetype.FT_LOAD_NO_HINTING)
        assert hinted - unhinted == pytest.approx(expected)


def make_box_font(boxes: dict[int, tuple[int, int, int, int]]) -> TTFont:
    """Create a TrueType font whose glyphs are single rectangles (xmin, ymin, xmax, ymax)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = {code: f"uni{code:04X}" for code in boxes}
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", *names.values()])
    builder.setupCharacterMap(names)
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    for code, (x0, y0, x1, y1) in boxes.items():
        pen = TTGlyphPen(None)
        pen.moveTo((x0, y0))
        pen.lineTo((x0, y1))
        pen.lineTo((x1, y1))
        pen.lineTo((x1, y0))
        pen.closePath()
        glyphs[names[code]] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (1000, 0) for name in [".notdef", *names.values()]})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupNameTable({"familyName": "BoxTest", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    return builder.font


def test_measure_stroke_approaches_width_of_long_strokes() -> None:
    from hangyeol_code.builder import measure_stroke

    font = make_box_font({0x3163: (400, -50, 410, 950)})
    assert measure_stroke(font.getGlyphSet(), "uni3163") == pytest.approx(10, rel=0.02)


def test_fit_fallback_mapping_recovers_scale_and_offset() -> None:
    from hangyeol_code.builder import fit_fallback_mapping

    reference_boxes = {0xAC00: (100, -100, 900, 800), 0xAC00 + 37: (100, 0, 900, 700)}
    # The fallback draws the same glyphs at half size, 10 units lower: y_ref = 2 * y_fb + 20.
    fallback_boxes = {
        code: (x0 // 2, (y0 - 20) // 2, x1 // 2, (y1 - 20) // 2)
        for code, (x0, y0, x1, y1) in reference_boxes.items()
    }
    reference, fallback = make_box_font(reference_boxes), make_box_font(fallback_boxes)
    ratio, offset = fit_fallback_mapping(
        reference.getBestCmap(),
        reference.getGlyphSet(),
        fallback.getBestCmap(),
        fallback.getGlyphSet(),
    )
    assert ratio == pytest.approx(2.0)
    assert offset == pytest.approx(20.0)


def test_match_fallback_weight_skips_static_fallback() -> None:
    from hangyeol_code.builder import match_fallback_weight

    font = make_box_font({0x3163: (400, -50, 480, 750), 0x3161: (100, 300, 900, 370)})
    assert match_fallback_weight(font, font, 1.0) is None


def test_font_revision_maps_release_versions() -> None:
    from hangyeol_code.builder import font_revision

    assert font_revision("1.001") == pytest.approx(1.001)
    assert font_revision("1.1") == pytest.approx(1.001)  # PEP 440 normalizes 1.001 to 1.1
    assert font_revision("1.203") == pytest.approx(1.203)
    assert font_revision("1.10") == pytest.approx(1.010)
    assert font_revision("2.0") == pytest.approx(2.0)
    with pytest.raises(ValueError, match="MAJOR.MINOR"):
        font_revision("1.0.1")


def test_set_font_version_writes_revision_and_sources() -> None:
    from hangyeol_code.builder import set_font_version

    font = make_name_font()
    latin = make_name_font()
    latin["name"].setName("JetBrainsMono Nerd Font Mono", 16, 3, 1, 0x409)
    latin["name"].setName("Version 2.304; ttfautohint (v1.8);Nerd Fonts 3.5.1", 5, 3, 1, 0x409)
    cjk = make_name_font()
    cjk["name"].setName("Pretendard", 1, 3, 1, 0x409)
    cjk["name"].setName("Version 1.309", 5, 3, 1, 0x409)
    set_font_version(font, "1.001", [latin, cjk])
    assert font["head"].fontRevision == pytest.approx(1.001)
    assert font["name"].getDebugName(5) == (
        "Version 1.001; JetBrainsMono Nerd Font Mono 2.304 (Nerd Fonts 3.5.1); Pretendard 1.309"
    )
