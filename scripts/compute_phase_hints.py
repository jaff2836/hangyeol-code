"""Compute per-ppem vertical shifts that make Korean glyphs render crisper.

Hangul glyphs copied from Pretendard carry no hinting, so at small sizes their
horizontal strokes land on fractional pixel rows and get blurred by vertical
anti-aliasing. A uniform vertical shift per ppem (applied with
``hangyeol-code --korean-hint-table``) can move the bulk of those strokes closer to
pixel boundaries. This script renders Hangul syllables from an *unhinted*
Hangyeol Code build with FreeType at sub-pixel vertical phases and picks, per
weight and ppem, the phase within ``--max-shift`` pixels that maximizes a
sharpness score.

The score is ``sum(a ** exponent) / sum(a)`` over all rendered coverage values
``a`` (0..1). It is the ink-weighted mean of ``a ** (exponent - 1)``, so an
exponent above 2 weights near-black pixels more heavily (a convex curve).
``--exponent 2`` reproduces the original linear weighting.

``--codepoints-file`` scores another glyph group instead of Hangul, e.g. the symbols and
icons that Hangyeol Code Narrow scales down (``hangyeol-code --narrow-groups-dir`` writes
those lists).

Usage (``make hints`` runs this for all four tables):
    uv run hangyeol-code --no-hints --no-ttc --styles normal --output-dir build/unhinted
    uv run --group hints python scripts/compute_phase_hints.py --font-dir build/unhinted/ttf \
        --family-stem HangyeolCode --ppems 10 11 12 13 14 15 16 17 18 19 20 \
        --max-shift 0.125 --step 0.015625 --exponent 3 --samples 0 \
        --output data/hints.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import freetype
import numpy as np

WEIGHTS = ("Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold")


def common_hangul(limit: int, seed: int) -> list[str]:
    """Return KS X 1001 Hangul syllables: all of them when ``limit`` <= 0, else a sample."""
    chars = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            if 0xAC00 <= ord(ch) <= 0xD7A3:
                chars.append(ch)
    if limit <= 0 or limit >= len(chars):
        return chars
    rng = np.random.default_rng(seed)
    return list(rng.choice(chars, size=limit, replace=False))


def sharpness(
    face: freetype.Face, ppem: int, phase: float, sample: list[str], exponent: float
) -> float:
    """Return sum(a^exponent)/sum(a) of unhinted renders shifted vertically by ``phase`` px."""
    face.set_pixel_sizes(0, ppem)
    face.set_transform(
        freetype.Matrix(0x10000, 0, 0, 0x10000), freetype.Vector(0, round(phase * 64))
    )
    num = den = 0.0
    for ch in sample:
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        cov = np.asarray(face.glyph.bitmap.buffer, dtype=float) / 255.0
        num += float((cov**exponent).sum())
        den += float(cov.sum())
    return num / den if den else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--font-dir", required=True, help="Directory with unhinted <stem>-<Weight>.ttf files."
    )
    parser.add_argument("--family-stem", required=True, help="File name stem, e.g. HangyeolCode.")
    parser.add_argument("--weights", nargs="+", default=list(WEIGHTS))
    parser.add_argument("--ppems", type=int, nargs="+", default=[11, 12, 13, 14, 15, 16])
    parser.add_argument("--max-shift", type=float, default=0.25, help="Largest shift in pixels.")
    parser.add_argument(
        "--step", type=float, default=1 / 32, help="Phase search step in pixels (>= 1/64)."
    )
    parser.add_argument(
        "--exponent",
        type=float,
        default=2.0,
        help="Coverage exponent of the score; above 2 favours near-black pixels.",
    )
    parser.add_argument(
        "--min-gain", type=float, default=0.005, help="Keep 0 unless the gain is larger."
    )
    parser.add_argument(
        "--samples", type=int, default=600, help="Syllables to sample; 0 uses all 2,350."
    )
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument(
        "--codepoints-file",
        default="",
        help="JSON list of code points to score instead of the KS X 1001 Hangul syllables.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    step = max(args.step, 1 / 64)
    if args.codepoints_file:
        chars = [chr(cp) for cp in json.loads(Path(args.codepoints_file).read_text())]
        if 0 < args.samples < len(chars):
            rng = np.random.default_rng(args.seed)
            chars = list(rng.choice(chars, size=args.samples, replace=False))
        sample = chars
    else:
        sample = common_hangul(args.samples, args.seed)
    phases = np.round(np.arange(-args.max_shift, args.max_shift + 1e-9, step) * 64) / 64
    table: dict[str, dict[str, float]] = {}
    report: dict[str, dict[str, dict[str, object]]] = {}
    for weight in args.weights:
        path = Path(args.font_dir) / f"{args.family_stem}-{weight}.ttf"
        if not path.exists():
            continue
        face = freetype.Face(str(path))
        table[weight], report[weight] = {}, {}
        for ppem in args.ppems:
            base = sharpness(face, ppem, 0.0, sample, args.exponent)
            scores = [sharpness(face, ppem, float(p), sample, args.exponent) for p in phases]
            best = int(np.argmax(scores))
            gain = scores[best] / base - 1
            shift = float(phases[best]) if gain > args.min_gain else 0.0
            table[weight][str(ppem)] = round(shift, 6)
            report[weight][str(ppem)] = {
                "shift": shift,
                "base": base,
                "best": scores[best],
                "phases": [float(p) for p in phases],
                "scores": scores,
            }
            print(
                f"{weight:10} {ppem:2d}ppem shift {shift:+.4f}px  "
                f"sharpness {base:.4f} -> {scores[best]:.4f} ({100 * gain:+.1f}%)",
                flush=True,
            )
    Path(args.output).write_text(json.dumps(table, indent=2), encoding="utf-8")
    Path(args.output).with_suffix(".report.json").write_text(json.dumps(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
