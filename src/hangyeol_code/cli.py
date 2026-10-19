"""Command-line interface for building Hangyeol Code."""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from importlib import metadata
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from hangyeol_code.builder import (
    DEFAULT_KOREAN_SCALE,
    DEFAULT_KOREAN_Y_OFFSET,
    DEFAULT_VARIANTS,
    DEFAULT_WEIGHTS,
    SUPPORTED_STYLES,
    SUPPORTED_WEIGHTS,
    FontVariant,
    MergedFont,
    add_ppem_shift_hints,
    build_merged_font,
    font_revision,
    fraction_digit_weight,
    get_variants_by_names,
    get_variants_by_weights_and_styles,
    log_cell_width_mismatches,
    make_font_variant,
    update_font_names,
)
from hangyeol_code.narrow import (
    NarrowSettings,
    Plan,
    add_group_hints,
    hint_groups,
    narrow_font,
    write_report,
)

logger = logging.getLogger(__name__)

FAMILIES = ("standard", "narrow")
DEFAULT_FAMILY_NAME = "Hangyeol Code"
DEFAULT_NARROW_FAMILY_NAME = "Hangyeol Code Narrow"
DEFAULT_HINT_TABLE = "data/hints.json"
DEFAULT_NARROW_HINT_TABLES = {
    "hangul": "data/hints-narrow.json",
    "symbols": "data/hints-narrow-symbols.json",
    "icons": "data/hints-narrow-icons.json",
}
DEFAULT_FALLBACK_FONT = "upstream/noto/NotoSansKR[wght].ttf"


def package_version() -> str | None:
    """Return the installed package version, which is also the font release version."""
    try:
        return metadata.version("hangyeol-code")
    except metadata.PackageNotFoundError:
        return None


def font_version_arg(value: str) -> str:
    """Validate ``--font-version`` (and the package version default) before building."""
    try:
        font_revision(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def family_file_stem(family_name: str) -> str:
    """Return the output filename stem for a family name."""
    return "".join(family_name.split())


def write_css(output_web_dir: Path, family_name: str, variants: list[FontVariant]) -> Path:
    """Generate @font-face rules for compiled web fonts."""
    css_content: list[str] = []
    stem = family_file_stem(family_name)
    for variant in variants:
        font_filename = f"{stem}-{variant.output_suffix}.woff2"
        css_content.append(
            "\n".join(
                [
                    "@font-face {",
                    f"  font-family: '{family_name}';",
                    f"  src: url('./{font_filename}') format('woff2');",
                    f"  font-weight: {variant.css_weight};",
                    f"  font-style: {variant.style};",
                    "  font-display: swap;",
                    "}",
                    "",
                ]
            )
        )

    css_path = output_web_dir / f"{stem.lower()}.css"
    css_path.write_text("\n".join(css_content), encoding="utf-8")
    logger.info("Wrote web font CSS to %s", css_path)
    return css_path


def load_hint_table(path: str) -> dict[str, dict[str, float]]:
    """Read a per-weight shift table; an empty path means no hints."""
    if not path:
        return {}
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def shifts_for(table: dict[str, dict[str, float]], weight: str) -> dict[int, float] | None:
    """Pick a weight's per-ppem shifts: its own entry, then "*", then a lone entry."""
    entry = table.get(weight) or table.get("*")
    if entry is None and len(table) == 1:
        entry = next(iter(table.values()))
    return {int(ppem): float(value) for ppem, value in entry.items()} if entry else None


def font_bytes(font: TTFont) -> bytes:
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def write_ttc(font_paths: list[Path], output_path: Path) -> Path:
    """Bundle TTF files into one TrueType Collection, sharing identical tables."""
    collection = TTCollection()
    collection.fonts = [TTFont(str(path)) for path in font_paths]
    collection.save(str(output_path), shareTables=True)
    for font in collection.fonts:
        font.close()
    logger.info("Wrote %d fonts to %s", len(font_paths), output_path)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser. Every default reproduces the released Hangyeol Code."""
    parser = argparse.ArgumentParser(
        description=(
            "Build Hangyeol Code and Hangyeol Code Narrow from JetBrainsMono Nerd Font Mono, "
            "Pretendard Hangul and Noto Sans KR. The defaults reproduce the released fonts."
        )
    )
    parser.add_argument(
        "--families",
        nargs="+",
        choices=FAMILIES,
        default=list(FAMILIES),
        help=(
            "Families to build: standard (600/1200-unit cells) and narrow (540/1080). "
            "Both share one merge per variant (default: both)."
        ),
    )
    parser.add_argument(
        "--latin-dir",
        default="upstream/jetbrainsmono",
        help="Directory containing JetBrainsMonoNerdFontMono TTF files.",
    )
    parser.add_argument(
        "--cjk-dir",
        default="upstream/pretendard",
        help="Directory containing Pretendard TTF files.",
    )
    parser.add_argument(
        "--output-dir",
        default="fonts",
        help="Directory to save generated fonts (default: fonts).",
    )
    parser.add_argument(
        "--family-name",
        default=DEFAULT_FAMILY_NAME,
        help=f"Name of the standard family (default: {DEFAULT_FAMILY_NAME}).",
    )
    parser.add_argument(
        "--narrow-family-name",
        default=DEFAULT_NARROW_FAMILY_NAME,
        help=f"Name of the narrow family (default: {DEFAULT_NARROW_FAMILY_NAME}).",
    )
    parser.add_argument(
        "--korean-scale",
        "--scale",
        dest="korean_scale",
        type=float,
        default=DEFAULT_KOREAN_SCALE,
        help=(
            "Visual scale factor for Korean/CJK glyphs after UPM normalization "
            f"(default: {DEFAULT_KOREAN_SCALE}, Hangul as tall as the rendered parentheses)."
        ),
    )
    parser.add_argument(
        "--korean-y-offset",
        dest="korean_y_offset",
        type=int,
        default=DEFAULT_KOREAN_Y_OFFSET,
        help=(
            "Vertical shift for Korean/CJK glyphs in Latin font units after scaling. "
            f"Negative moves glyphs down (default: {DEFAULT_KOREAN_Y_OFFSET}, centered on the "
            "parentheses)."
        ),
    )
    parser.add_argument(
        "--korean-hint-table",
        dest="korean_hint_table",
        default=DEFAULT_HINT_TABLE,
        help=(
            "JSON file with per-ppem vertical shifts (pixels) for Korean/CJK glyphs, "
            'keyed by weight name, e.g. {"Regular": {"12": 0.125}}. A "*" entry applies '
            "to weights without their own entry; italic variants use their weight's entry. "
            f'Pass "" to build without hints (default: {DEFAULT_HINT_TABLE}).'
        ),
    )
    for group, default in DEFAULT_NARROW_HINT_TABLES.items():
        parser.add_argument(
            f"--narrow-{group}-hints",
            default=default,
            help=f'Per-ppem shift table for the narrow {group} group, "" for none '
            f"(default: {default}).",
        )
    parser.add_argument(
        "--no-hints",
        action="store_true",
        help="Build every family without the per-ppem shift hints (to recompute the tables).",
    )
    defaults = NarrowSettings()
    parser.add_argument(
        "--narrow-ratio",
        type=float,
        default=defaults.ratio,
        help=f"Narrow cell width relative to the standard one (default: {defaults.ratio}).",
    )
    parser.add_argument(
        "--narrow-min-margin",
        type=float,
        default=defaults.min_margin,
        help=(
            "Side margin in font units a glyph keeps before it is squeezed "
            f"(default: {defaults.min_margin:g})."
        ),
    )
    parser.add_argument(
        "--narrow-max-shift",
        type=float,
        default=defaults.max_shift,
        help=(
            "Font units a glyph that does not fit between the narrow margins may move "
            "sideways, at most until it is centred, before it is squeezed; italics move as "
            "far as their upright glyphs. 0 keeps glyphs centred "
            f"(default: {defaults.max_shift:g})."
        ),
    )
    parser.add_argument(
        "--narrow-max-shrink",
        type=float,
        default=defaults.max_shrink,
        help=f"Largest horizontal squeeze (default: {defaults.max_shrink}).",
    )
    parser.add_argument(
        "--narrow-report",
        default="",
        help="Write a TSV of what happened to every glyph in the narrow family.",
    )
    parser.add_argument(
        "--narrow-groups-dir",
        default="",
        help=(
            "Write icons.json and symbols.json, the code points of the narrow hint groups, "
            "for scripts/compute_phase_hints.py."
        ),
    )
    parser.add_argument(
        "--ksx-symbols",
        dest="ksx_symbols",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Add the KS X 1001 symbols the Latin font lacks (e.g. U+203B, U+2605, U+321C). "
            "Wide characters take two cells, all others one cell (default: on)."
        ),
    )
    parser.add_argument(
        "--fallback-font",
        dest="fallback_font",
        default=DEFAULT_FALLBACK_FONT,
        help=(
            "Font for KS X 1001 characters Pretendard lacks. It is aligned to Pretendard's "
            "Hangul, and a variable font is set to the weight whose strokes match. "
            f'Pass "" to use Pretendard only (default: {DEFAULT_FALLBACK_FONT}).'
        ),
    )
    parser.add_argument(
        "--font-version",
        type=font_version_arg,
        default=package_version(),
        help=(
            "Release version written to the fonts as head.fontRevision and name ID 5, "
            "MAJOR.MINOR, e.g. 1.001 -> Version 1.001 (default: the package version)."
        ),
    )
    parser.add_argument(
        "--ttc",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also bundle each family's TTFs into <output-dir>/<family>.ttc (default: on).",
    )
    parser.add_argument(
        "--webfonts",
        action="store_true",
        help="Also write WOFF2 files and an @font-face CSS file to <output-dir>/webfont.",
    )
    parser.add_argument(
        "--weights",
        nargs="+",
        default=None,
        help=(
            "Weights to generate. With no --styles, this builds upright variants only. "
            f"Supported: {', '.join(SUPPORTED_WEIGHTS)}."
        ),
    )
    parser.add_argument(
        "--styles",
        nargs="+",
        default=None,
        choices=SUPPORTED_STYLES,
        help="Styles to generate with --weights, or across all weights when --weights is omitted.",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=None,
        help=(
            "Explicit output variants to generate, for example Regular Italic BoldItalic. "
            "Cannot be combined with --weights or --styles."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build all 16 variants (the default when no variant is selected).",
    )
    parser.add_argument(
        "--korean-italic-mode",
        choices=("upright",),
        default="upright",
        help=("Korean/CJK glyph policy for italic variants. Currently only upright is supported."),
    )
    return parser


def dedupe_preserving_order(values: list[str]) -> list[str]:
    """Remove duplicates while preserving user-specified order."""
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped


def validate_weights(weights: list[str]) -> list[str]:
    """Validate requested weight names."""
    deduped = dedupe_preserving_order(weights)
    unsupported = [weight for weight in deduped if weight not in SUPPORTED_WEIGHTS]
    if unsupported:
        supported = ", ".join(SUPPORTED_WEIGHTS)
        msg = f"Unsupported weight(s): {', '.join(unsupported)}. Supported: {supported}"
        raise ValueError(msg)
    return deduped


def validate_styles(styles: list[str]) -> list[str]:
    """Validate requested style names."""
    deduped = dedupe_preserving_order(styles)
    unsupported = [style for style in deduped if style not in SUPPORTED_STYLES]
    if unsupported:
        supported = ", ".join(SUPPORTED_STYLES)
        msg = f"Unsupported style(s): {', '.join(unsupported)}. Supported: {supported}"
        raise ValueError(msg)
    return deduped


def select_variants(
    *,
    all_variants: bool = False,
    variant_names: list[str] | None = None,
    weights: list[str] | None = None,
    styles: list[str] | None = None,
) -> list[FontVariant]:
    """Resolve CLI selectors to build variants."""
    if all_variants and (variant_names or weights or styles):
        msg = "--all cannot be combined with --variants, --weights, or --styles"
        raise ValueError(msg)
    if variant_names and (weights or styles):
        msg = "--variants cannot be combined with --weights or --styles"
        raise ValueError(msg)

    if all_variants or (variant_names is None and weights is None and styles is None):
        return list(DEFAULT_VARIANTS)

    if variant_names:
        return get_variants_by_names(variant_names)

    selected_weights = validate_weights(weights if weights is not None else list(DEFAULT_WEIGHTS))
    selected_styles = validate_styles(styles if styles is not None else ["normal"])
    return get_variants_by_weights_and_styles(selected_weights, selected_styles)


class FamilyBuilder:
    """Builds every requested family from one merge per variant."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.latin_dir = Path(args.latin_dir)
        self.cjk_dir = Path(args.cjk_dir)
        self.output_dir = Path(args.output_dir)
        self.ttf_dir = self.output_dir / "ttf"
        self.web_dir = self.output_dir / "webfont"
        self.fallback_path = Path(args.fallback_font) if args.fallback_font else None
        self.families = [family for family in FAMILIES if family in args.families]
        self.names = {"standard": args.family_name, "narrow": args.narrow_family_name}
        self.hints = load_hint_table("" if args.no_hints else args.korean_hint_table)
        self.narrow_hints = {
            group: load_hint_table("" if args.no_hints else getattr(args, f"narrow_{group}_hints"))
            for group in DEFAULT_NARROW_HINT_TABLES
        }
        self.settings = NarrowSettings(
            ratio=args.narrow_ratio,
            min_margin=args.narrow_min_margin,
            max_shrink=args.narrow_max_shrink,
            max_shift=args.narrow_max_shift,
        )
        self.upright: dict[str, bytes] = {}
        self.built: dict[str, list[Path]] = {family: [] for family in self.families}
        self.report: list[tuple[str, Plan]] = []
        self.group_codepoints: dict[str, set[int]] = {"icons": set(), "symbols": set()}

    def source_paths(self, variant: FontVariant) -> tuple[Path, Path]:
        latin_path = self.latin_dir / variant.latin_filename
        cjk_path = self.cjk_dir / f"Pretendard-{variant.cjk_weight_name}.ttf"
        for path, hint in ((latin_path, "JetBrainsMonoNerdFontMono"), (cjk_path, "Pretendard")):
            if not path.exists():
                msg = f"{path} not found. Run `make download` to fetch the {hint} files."
                raise FileNotFoundError(msg)
        return latin_path, cjk_path

    def merge(self, variant: FontVariant) -> MergedFont:
        latin_path, cjk_path = self.source_paths(variant)
        digit_variant = make_font_variant(fraction_digit_weight(variant.weight_name), variant.style)
        digit_path = self.latin_dir / digit_variant.latin_filename
        args = self.args
        merged = build_merged_font(
            latin_path=latin_path,
            cjk_path=cjk_path,
            family_name=args.family_name,
            subfamily_name=variant.subfamily_name,
            korean_scale=args.korean_scale,
            korean_y_offset=args.korean_y_offset,
            add_ksx_symbols=args.ksx_symbols,
            fallback_path=self.fallback_path,
            font_version=args.font_version,
            typographic_subfamily_name=variant.typographic_subfamily_name,
            is_italic=variant.is_italic,
            css_weight=variant.css_weight,
            fraction_digit_path=digit_path if digit_path.exists() else None,
        )
        stats = merged.stats
        logger.info(
            "%s: copied=%d symbols=%d capped=%d latin_advance=%d korean_advance=%d",
            variant.output_suffix,
            stats.copied_count,
            stats.symbol_count,
            stats.capped_count,
            stats.latin_advance,
            stats.korean_advance,
        )
        return merged

    def upright_font(self, variant: FontVariant) -> TTFont:
        """The unhinted upright font of an italic's weight, merged on demand."""
        weight = variant.weight_name
        if weight not in self.upright:
            upright = get_variants_by_names([weight])[0]
            merged = self.merge(upright)
            self.upright[weight] = font_bytes(merged.font)
            merged.font.close()
        return TTFont(io.BytesIO(self.upright[weight]))

    def save(self, family: str, variant: FontVariant, font: TTFont) -> None:
        stem = family_file_stem(self.names[family])
        path = self.ttf_dir / f"{stem}-{variant.output_suffix}.ttf"
        log_cell_width_mismatches(font, path.name)
        font.save(str(path))
        font.close()
        logger.info("Wrote %s", path)
        self.built[family].append(path)
        if self.args.webfonts:
            web_font = TTFont(str(path))
            web_font.flavor = "woff2"
            web_font.save(str(self.web_dir / f"{stem}-{variant.output_suffix}.woff2"))
            web_font.close()

    def build_variant(self, variant: FontVariant) -> None:
        merged = self.merge(variant)
        unhinted = font_bytes(merged.font) if "narrow" in self.families else b""
        if not variant.is_italic and unhinted:
            self.upright[variant.weight_name] = unhinted

        if "standard" in self.families:
            shifts = shifts_for(self.hints, variant.weight_name)
            if shifts:
                add_ppem_shift_hints(merged.font, merged.hint_glyphs, shifts)
            self.save("standard", variant, merged.font)
        else:
            merged.font.close()

        if "narrow" in self.families:
            font = TTFont(io.BytesIO(unhinted))
            upright = self.upright_font(variant) if variant.is_italic else None
            plans, _ = narrow_font(font, upright, self.settings)
            groups = hint_groups(plans, set(merged.hint_glyphs))
            for group in self.group_codepoints:
                self.group_codepoints[group].update(
                    cp for name in groups[group] for cp in plans[name].cps
                )
            tables = {
                group: shifts_for(table, variant.weight_name)
                for group, table in self.narrow_hints.items()
            }
            add_group_hints(font, groups, tables)
            update_font_names(
                font,
                self.names["narrow"],
                variant.subfamily_name,
                typographic_subfamily_name=variant.typographic_subfamily_name,
            )
            self.save("narrow", variant, font)
            self.report.extend((variant.output_suffix, plan) for plan in plans.values())

    def finish(self, variants: list[FontVariant]) -> None:
        for family, paths in self.built.items():
            stem = family_file_stem(self.names[family])
            if self.args.ttc and len(paths) > 1:
                write_ttc(paths, self.output_dir / f"{stem}.ttc")
            if self.args.webfonts:
                write_css(self.web_dir, self.names[family], variants)
        if self.args.narrow_report and self.report:
            write_report(Path(self.args.narrow_report), self.report)
        if self.args.narrow_groups_dir and "narrow" in self.families:
            groups_dir = Path(self.args.narrow_groups_dir)
            groups_dir.mkdir(parents=True, exist_ok=True)
            for group, codepoints in self.group_codepoints.items():
                (groups_dir / f"{group}.json").write_text(
                    json.dumps(sorted(codepoints)), encoding="utf-8"
                )


def main(argv: list[str] | None = None) -> int:
    """Run the font build."""
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    try:
        variants = select_variants(
            all_variants=args.all,
            variant_names=args.variants,
            weights=args.weights,
            styles=args.styles,
        )
    except ValueError as exc:
        parser.error(str(exc))

    fallback_path = Path(args.fallback_font) if args.fallback_font else None
    if args.ksx_symbols and fallback_path is not None and not fallback_path.exists():
        logger.error("Fallback font not found: %s", fallback_path)
        logger.error('Run `make download`, or pass --fallback-font "" to skip it.')
        return 1

    builder = FamilyBuilder(args)
    builder.ttf_dir.mkdir(parents=True, exist_ok=True)
    if args.webfonts:
        builder.web_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Building %s: %s",
        " and ".join(builder.names[family] for family in builder.families),
        ", ".join(variant.output_suffix for variant in variants),
    )

    for variant in variants:
        try:
            builder.build_variant(variant)
        except Exception:
            logger.exception("Failed to build variant %s", variant.output_suffix)
            return 1
    builder.finish(variants)
    logger.info(
        "All requested variants of %s built successfully",
        " and ".join(builder.names[family] for family in builder.families),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
