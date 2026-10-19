"""Tests for the CLI helpers."""

from __future__ import annotations

import pytest

from hangyeol_code.builder import DEFAULT_VARIANTS, get_variants_by_names
from hangyeol_code.cli import (
    family_file_stem,
    select_variants,
    validate_styles,
    validate_weights,
    write_css,
)


def test_family_file_stem_removes_spaces() -> None:
    assert family_file_stem("Hangyeol Code") == "HangyeolCode"


def test_validate_weights_accepts_supported_weights() -> None:
    assert validate_weights(["Regular", "Light", "Bold"]) == ["Regular", "Light", "Bold"]


def test_validate_weights_rejects_unknown_weight() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        validate_weights(["Regular", "Book"])


def test_validate_weights_rejects_black_until_matching_latin_source_exists() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        validate_weights(["Black"])


def test_validate_styles_accepts_supported_styles() -> None:
    assert validate_styles(["normal", "italic", "normal"]) == ["normal", "italic"]


def test_validate_styles_rejects_unknown_style() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        validate_styles(["oblique"])


def test_select_variants_defaults_to_full_coverage() -> None:
    assert select_variants() == list(DEFAULT_VARIANTS)


def test_select_variants_weights_default_to_upright() -> None:
    variants = select_variants(weights=["Regular", "Bold"])
    assert [variant.output_suffix for variant in variants] == ["Regular", "Bold"]


def test_select_variants_weights_and_styles_cross_product() -> None:
    variants = select_variants(weights=["Regular", "Bold"], styles=["normal", "italic"])
    assert [variant.output_suffix for variant in variants] == [
        "Regular",
        "Italic",
        "Bold",
        "BoldItalic",
    ]


def test_select_variants_explicit_names() -> None:
    variants = select_variants(variant_names=["Regular", "BoldItalic"])
    assert [variant.output_suffix for variant in variants] == ["Regular", "BoldItalic"]


def test_select_variants_rejects_ambiguous_combinations() -> None:
    with pytest.raises(ValueError, match="--all cannot be combined"):
        select_variants(all_variants=True, weights=["Regular"])
    with pytest.raises(ValueError, match="--variants cannot be combined"):
        select_variants(variant_names=["Regular"], styles=["italic"])


def test_write_css_generates_font_face_rules(tmp_path) -> None:
    variants = get_variants_by_names(["Regular", "Italic", "BoldItalic"])
    css_path = write_css(tmp_path, "Hangyeol Code", variants)
    content = css_path.read_text(encoding="utf-8")

    assert css_path.name == "hangyeolcode.css"
    assert "font-family: 'Hangyeol Code';" in content
    assert "HangyeolCode-Regular.woff2" in content
    assert "font-weight: 400;" in content
    assert "font-style: normal;" in content
    assert "HangyeolCode-Italic.woff2" in content
    assert "font-style: italic;" in content
    assert "HangyeolCode-BoldItalic.woff2" in content
    assert "font-weight: 700;" in content


def test_parser_builds_both_families_by_default() -> None:
    from hangyeol_code.cli import build_parser

    args = build_parser().parse_args([])
    assert args.families == ["standard", "narrow"]
    assert args.narrow_family_name == "Hangyeol Code Narrow"
    assert build_parser().parse_args(["--families", "narrow"]).families == ["narrow"]


def test_parser_checks_font_version() -> None:
    from hangyeol_code.cli import build_parser

    assert build_parser().parse_args(["--font-version", "1.001"]).font_version == "1.001"
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--font-version", "1.0.1"])
