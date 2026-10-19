.PHONY: dev lint format test download ensure-upstream run run-web run-minimal hints package clean

dev:
	uv sync --all-groups

lint:
	uv run ruff format --check .
	uv run ruff check .

format:
	uv run ruff format .

test:
	uv run pytest

download:
	uv run python download_upstream.py

ensure-upstream:
	@if [ ! -d "upstream/jetbrainsmono" ] || [ ! -d "upstream/pretendard" ] || [ ! -d "upstream/noto" ]; then \
		echo "Upstream font resources not found. Downloading..."; \
		$(MAKE) download; \
	fi

run: ensure-upstream
	uv run hangyeol-code

run-web: ensure-upstream
	uv run hangyeol-code --webfonts

run-minimal: ensure-upstream
	uv run hangyeol-code --variants Regular Bold --no-ttc

HINT_ARGS = --ppems 10 11 12 13 14 15 16 17 18 19 20 --max-shift 0.125 --step 0.015625 \
	--exponent 3 --samples 0
COMPUTE_HINTS = uv run --group hints python scripts/compute_phase_hints.py \
	--font-dir build/unhinted/ttf $(HINT_ARGS)

hints: ensure-upstream
	uv run hangyeol-code --no-hints --no-ttc --styles normal --output-dir build/unhinted \
		--narrow-groups-dir build/unhinted/groups
	$(COMPUTE_HINTS) --family-stem HangyeolCode --output data/hints.json
	$(COMPUTE_HINTS) --family-stem HangyeolCodeNarrow --output data/hints-narrow.json
	$(COMPUTE_HINTS) --family-stem HangyeolCodeNarrow \
		--codepoints-file build/unhinted/groups/symbols.json --output data/hints-narrow-symbols.json
	$(COMPUTE_HINTS) --family-stem HangyeolCodeNarrow --weights Regular \
		--codepoints-file build/unhinted/groups/icons.json --output data/hints-narrow-icons.json

VERSION = $(shell uv run python -c "import tomllib; \
	print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")

package:
	rm -rf dist
	for stem in HangyeolCode HangyeolCodeNarrow; do \
		mkdir -p dist/$$stem-$(VERSION)/ttf && \
		cp fonts/ttf/$$stem-*.ttf dist/$$stem-$(VERSION)/ttf/ && \
		cp fonts/$$stem.ttc LICENSE dist/$$stem-$(VERSION)/ && \
		(cd dist && uv run python -m zipfile -c $$stem-$(VERSION).zip $$stem-$(VERSION)) || exit 1; \
	done

clean:
	rm -rf fonts build dist
