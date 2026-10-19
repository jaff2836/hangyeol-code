"""Download and extract the upstream fonts Hangyeol Code is built from."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from hangyeol_code.builder import DEFAULT_VARIANTS, SUPPORTED_WEIGHTS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

NERD_FONTS_VERSION = "v3.5.1"
PRETENDARD_VERSION = "1.3.9"
JETBRAINS_MONO_SHA256 = "fab782a66f7d3019da64f6572db9fc5d3a4bcb19f9fa13e2d8a62e3693d6396e"
PRETENDARD_SHA256 = "04be351a74d6bf7d60c480a3087e51d185485d35a52023142af1df19eb8c428a"

JETBRAINS_MONO_URL = (
    f"https://github.com/ryanoasis/nerd-fonts/releases/download/"
    f"{NERD_FONTS_VERSION}/JetBrainsMono.zip"
)
PRETENDARD_URL = (
    "https://github.com/orioncactus/pretendard/releases/download/"
    f"v{PRETENDARD_VERSION}/Pretendard-{PRETENDARD_VERSION}.zip"
)
# Noto Sans KR (Source Han Sans, the origin of Pretendard's Hangul) fills KS X 1001
# characters Pretendard lacks. Pinned by content hash; Google Fonts serves it from main.
NOTO_SANS_KR_VERSION = "2.004"
NOTO_SANS_KR_FILE = "NotoSansKR[wght].ttf"
NOTO_SANS_KR_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
)
NOTO_SANS_KR_LICENSE_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/OFL.txt"
)
NOTO_SANS_KR_SHA256 = "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252"

UPSTREAM_DIR = Path("upstream")
ARCHIVE_DIR = UPSTREAM_DIR / "_archives"
JETBRAINS_DIR = UPSTREAM_DIR / "jetbrainsmono"
PRETENDARD_DIR = UPSTREAM_DIR / "pretendard"
NOTO_DIR = UPSTREAM_DIR / "noto"


def download_file(url: str, output_path: Path) -> None:
    """Download a URL to a file, reusing an existing non-empty file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 0:
        logger.info("Archive already exists: %s", output_path)
        return

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    logger.info("Downloading %s", url)
    request = urllib.request.Request(url, headers={"User-Agent": "Hangyeol Code builder"})
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            tmp_path.open("wb") as handle,
        ):
            shutil.copyfileobj(response, handle)
    except Exception as exc:
        if not shutil.which("curl"):
            raise
        logger.warning("Python download failed (%s). Retrying with curl.", exc)
        subprocess.run(
            [
                "curl",
                "-fL",
                "--retry",
                "3",
                "--connect-timeout",
                "30",
                "-A",
                "Hangyeol Code builder",
                "-o",
                str(tmp_path),
                url,
            ],
            check=True,
        )
    tmp_path.replace(output_path)
    logger.info("Downloaded %s", output_path)


def extract_expected_fonts(
    archive_path: Path,
    output_dir: Path,
    required_basenames: set[str],
) -> None:
    """Extract the requested font basenames from a zip archive."""
    output_dir.mkdir(parents=True, exist_ok=True)
    found: dict[str, str] = {}

    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            basename = Path(member.filename).name
            if basename not in required_basenames:
                continue

            target_path = output_dir / basename
            logger.info("Extracting %s -> %s", member.filename, target_path)
            with archive.open(member) as source, target_path.open("wb") as target:
                shutil.copyfileobj(source, target)
            found[basename] = member.filename

    missing = sorted(required_basenames - set(found))
    if missing:
        msg = (
            f"{archive_path} did not contain expected files: {', '.join(missing)}. "
            "Check the pinned upstream version or archive layout."
        )
        raise FileNotFoundError(msg)


def verify_sha256(path: Path, expected: str) -> None:
    """Fail if a downloaded file does not have the pinned content hash."""
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        msg = f"{path} has SHA-256 {digest}, expected {expected}. Upstream changed; re-pin it."
        raise ValueError(msg)


def write_sources_note() -> None:
    """Write a small note documenting the downloaded upstream versions."""
    jetbrains_files = sorted({variant.latin_filename for variant in DEFAULT_VARIANTS})
    pretendard_files = [f"Pretendard-{weight}.ttf" for weight in SUPPORTED_WEIGHTS]
    note = "\n".join(
        [
            "# Hangyeol Code Upstream Sources",
            "",
            f"- Nerd Fonts JetBrainsMono: {NERD_FONTS_VERSION} "
            f"(sha256 {JETBRAINS_MONO_SHA256[:16]}...)",
            f"- Pretendard: {PRETENDARD_VERSION} (sha256 {PRETENDARD_SHA256[:16]}...)",
            f"- Noto Sans KR: {NOTO_SANS_KR_VERSION} (sha256 {NOTO_SANS_KR_SHA256[:16]}...)",
            "",
            "## Extracted JetBrainsMono Nerd Font Mono Files",
            "",
            *[f"- `{filename}`" for filename in jetbrains_files],
            "",
            "## Extracted Pretendard Files",
            "",
            *[f"- `{filename}`" for filename in pretendard_files],
            "",
            "## Noto Sans KR",
            "",
            f"- `noto/{NOTO_SANS_KR_FILE}` (fallback for KS X 1001 symbols)",
            "- `noto/OFL.txt`",
            "",
        ]
    )
    (UPSTREAM_DIR / "SOURCES.md").write_text(note, encoding="utf-8")


def main() -> int:
    """Download upstream JetBrainsMono Nerd Font Mono, Pretendard and Noto Sans KR files."""
    jetbrains_archive = ARCHIVE_DIR / f"JetBrainsMono-{NERD_FONTS_VERSION}.zip"
    pretendard_archive = ARCHIVE_DIR / f"Pretendard-{PRETENDARD_VERSION}.zip"

    jetbrains_expected = {variant.latin_filename for variant in DEFAULT_VARIANTS}
    pretendard_expected = {f"Pretendard-{weight}.ttf" for weight in SUPPORTED_WEIGHTS}

    try:
        download_file(JETBRAINS_MONO_URL, jetbrains_archive)
        verify_sha256(jetbrains_archive, JETBRAINS_MONO_SHA256)
        download_file(PRETENDARD_URL, pretendard_archive)
        verify_sha256(pretendard_archive, PRETENDARD_SHA256)
        extract_expected_fonts(jetbrains_archive, JETBRAINS_DIR, jetbrains_expected)
        extract_expected_fonts(pretendard_archive, PRETENDARD_DIR, pretendard_expected)
        download_file(NOTO_SANS_KR_URL, NOTO_DIR / NOTO_SANS_KR_FILE)
        verify_sha256(NOTO_DIR / NOTO_SANS_KR_FILE, NOTO_SANS_KR_SHA256)
        download_file(NOTO_SANS_KR_LICENSE_URL, NOTO_DIR / "OFL.txt")
        write_sources_note()
    except Exception:
        logger.exception("Failed to prepare upstream resources")
        return 1

    logger.info("All upstream resources are ready under %s", UPSTREAM_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
