# Hangyeol Code (한결 코드)

한결 코드는 한글과 영문을 함께 쓰는 고정폭 코딩 폰트입니다. Windows에서 10–20px로 볼 때
읽기 좋도록 맞췄습니다. 이름은 '한결같다'에서 따왔습니다. 크기가 바뀌어도 한글이 괄호
중심에서 흔들리지 않게 하는 것이 이 폰트의 핵심입니다.

영문·합자·Nerd Font 아이콘은 JetBrains Mono(Nerd Fonts)에서, 한글은 Pretendard에서, 나머지
KS X 1001 특수문자는 Pretendard와 Noto Sans KR에서 가져왔습니다. 칸 너비를 10% 줄인
Hangyeol Code Narrow도 같은 소스에서 함께 만듭니다. SIL Open Font License 1.1로 배포합니다.

![Hangyeol Code 11·14·18px 렌더링 예시](assets/sample.png)

*11·14·18px을 FreeType으로 힌팅을 적용해 렌더링하고 5배 확대한 이미지입니다.*

[English](README.en.md)

## 특징

- **영문·합자·아이콘:** JetBrainsMono Nerd Font Mono를 그대로 씁니다. 원본의 TrueType
  힌팅도 손대지 않았습니다.
- **한글:** Pretendard의 한글을 영문 두 칸(1200 단위)에 넣었습니다.
  - 배율 1.08404, 아래로 25단위입니다. Windows에서 실제로 그려진 `( )`의 위·아래 끝에
    한글을 맞춘 값입니다.
  - 9–12pt·12–16px에서 높이 차이의 표준편차는 0.03px, 중심 차이는 0.08px입니다.
- **한글 힌팅(10–20px):** 크기와 굵기마다 한글 전체를 최대 1/8px 위아래로 옮겨,
  가로획이 픽셀 경계에 최대한 붙게 했습니다.
  - 모든 한글이 함께 움직이므로 음절끼리 들쭉날쭉해지지 않습니다.
  - 선명도는 Regular 기준 11–20px에서 +0.8–4.4% 좋아집니다(검은 픽셀에 가중치를 둔 점수).
    10px에서는 이득이 없어 옮기지 않습니다.
- **특수문자:** KS X 1001의 한글·한자 외 문자 988자를 모두 담았습니다.
  - 영문 폰트에 없는 것은 Pretendard에서, Pretendard에도 없는 197자는 Noto Sans KR에서
    가져왔습니다.
  - 어느 원본에도 없거나 모양이 맞지 않는 `⅓ ⅔ ⅛ ⅜ ⅝ ⅞ ≒`는 JetBrains Mono의 부품으로
    만들었습니다. 분수는 JetBrains Mono의 `½ ¼ ¾`와 같은 모양입니다.
- **문자 폭:** Unicode 동아시아 폭 규칙을 따릅니다. 넓은 문자는 두 칸, 나머지는 한 칸이라
  터미널에서 겹치지 않습니다. 폭이 모호한 `※ ★ ℃ ①`과 반각 한글도 한 칸입니다.
  - 빌드할 때 모든 문자의 폭을 이 규칙과 대조하고, 어긋나면 경고합니다.
- **16종:** Thin, ExtraLight, Light, Regular, Medium, SemiBold, Bold, ExtraBold ×
  똑바로/기울임. 기울임꼴에서도 한글은 똑바로 둡니다.
  - Office 같은 Windows 앱에서는 `Hangyeol Code Thin`처럼 굵기별 이름으로 보입니다.
    Regular와 Bold는 `Hangyeol Code` 하나로 묶여 굵게·기울임 버튼으로 바꿀 수 있습니다.

## Hangyeol Code Narrow

칸 너비를 10% 줄인 판입니다. 반각은 540, 전각은 1080 단위이고 줄 높이는 같습니다. 같은
너비의 창에 한 줄로 약 11% 더 많은 글자가 들어갑니다. 버전은 Hangyeol Code와 함께 갑니다.

![Hangyeol Code Narrow 11·14·18px 렌더링 예시](assets/sample-narrow.png)

- **위치:** 글자는 칸 가운데를 기준으로 제자리를 지킵니다. 한쪽으로 치우쳐 여백이 모자란
  글자만 옆으로 조금 옮깁니다.
- **축소 규칙:**
  - 좁아진 칸에서도 좌우 여백이 7.5단위 이상 남으면 칸과 함께 옮기기만 합니다. 반각 한글을
    뺀 한글은 모두 여기에 해당합니다.
  - 여백이 모자라면 먼저 옆으로 최대 20단위, 칸 가운데에 올 때까지만 옮깁니다. 기울임꼴은
    똑바른 글자와 같은 거리만큼 옮기고, 결합 부호는 옮기지 않습니다.
  - 그래도 모자라면 7.5단위가 남을 때까지 가로로 줄이되, 최대 10%까지만 줄입니다.
  - 원래 칸을 넘던 글자는 옮기지 않고 10% 줄입니다.
  - 원 문자, 도형, 별, 아이콘처럼 정사각형에 그린 기호는 세로도 같은 비율로 줄입니다.
  - 박스 문자, 블록, Powerline 구분자는 이웃 칸과 이어지도록 정확히 0.9배로 맞춥니다.
- **힌팅:** 영문 힌팅은 세로 방향만 다루므로 그대로 둡니다. 세로로 줄인 영문 도형(○ ■ ⊕
  등)도 FreeType 10–20px에서 원래와 같은 정도로 윤곽을 따라갑니다.
  - 한글, 세로로 줄인 KS X 1001 기호, 아이콘은 묶음마다 10–20px 이동표를 따로
    계산했습니다(`data/hints-narrow*.json`).
- **이름:** 글꼴 이름은 `Hangyeol Code Narrow`라서 Hangyeol Code와 함께 설치할 수
  있습니다.

## 설치

[릴리스](https://github.com/jaff2836/hangyeol-code/releases/latest)에서
`HangyeolCode-<버전>.zip`을 받습니다. 압축 안의 `HangyeolCode.ttc` 하나를 설치하거나,
`ttf/` 폴더의 TTF 16개를 설치하세요. 둘 중 하나만 설치하면 됩니다. Narrow는
`HangyeolCodeNarrow-<버전>.zip`에 같은 구성으로 들어 있습니다.

- **Windows:** 파일을 선택하고 오른쪽 클릭 → **모든 사용자용으로 설치**.
- **macOS:** 파일을 열어 서체 관리자에서 **설치**를 누릅니다.
- **Linux:** `~/.local/share/fonts`에 복사하고 `fc-cache -f`를 실행합니다.

**Windows Terminal** (`settings.json`)

```json
"font": { "face": "Hangyeol Code", "size": 11 }
```

**VS Code** (`settings.json`)

```json
"editor.fontFamily": "'Hangyeol Code'",
"editor.fontLigatures": true,
"terminal.integrated.fontFamily": "'Hangyeol Code'"
```

Narrow를 쓰려면 `Hangyeol Code` 자리에 `Hangyeol Code Narrow`를 넣습니다.

- 힌팅은 화면의 실제 픽셀 크기 10–20px에서 적용됩니다.
  - 배율 100%: 8–15pt, 10–20px
  - 배율 125%: 6–12pt, 8–16px
- macOS는 TrueType 힌팅을 쓰지 않습니다.
- Windows Terminal과 VS Code 터미널은 박스 문자·블록·Powerline 기호를 폰트 대신 직접
  그립니다(기본 설정).

**웹** — `HangyeolCode-webfont-<버전>.zip`에는 두 글꼴의 WOFF2 32개와 CSS 두 개
(`hangyeolcode.css`, `hangyeolcodenarrow.css`)가 들어 있습니다. 파일을 같은 폴더에 올리고
CSS를 연결합니다.

```html
<link rel="stylesheet" href="hangyeolcode.css">
<style>
  code, pre { font-family: 'Hangyeol Code', monospace; }
</style>
```

WOFF2 하나가 약 1.7MB입니다. 쓰는 굵기만 올리고, CSS에서 나머지 `@font-face`를 지우면
가벼워집니다. 브라우저는 `@font-face`에 적힌 파일 중 페이지에서 쓰는 굵기만 내려받습니다.

## 빌드

[uv](https://docs.astral.sh/uv/)와 `make`가 필요합니다. Python 3.12는 uv가 받아 옵니다.
원본 폰트로 약 250MB를 내려받습니다.

```bash
uv sync --all-groups
make download   # JetBrainsMono Nerd Font 3.5.1, Pretendard 1.3.9, Noto Sans KR 2.004
make run        # Hangyeol Code와 Narrow: fonts/ttf/*.ttf, fonts/*.ttc
make test
make package    # 배포용 압축 파일: dist/HangyeolCode-<버전>.zip, -Narrow-, -webfont-
```

한 번의 빌드로 두 글꼴을 함께 만듭니다. 변형마다 영문과 한글을 한 번 합친 뒤, 거기서
Hangyeol Code와 Narrow를 각각 마무리합니다. 하나만 만들려면 `--families standard` 또는
`--families narrow`를 줍니다. 16종 두 벌을 만드는 데 5–10분 걸립니다.

기본값만으로 배포본과 같은 폰트가 나옵니다. 내려받은 원본(`upstream/`)과 결과물(`fonts/`,
`dist/`)은 git에 넣지 않습니다. 원본 압축 파일은 SHA-256으로 확인합니다.

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--korean-scale` | `1.08404` | 한글 배율 (UPM 정규화 후) |
| `--korean-y-offset` | `-25` | 한글 세로 이동 (영문 폰트 단위, 음수는 아래) |
| `--korean-hint-table` | `data/hints.json` | 크기별 한글 이동표, `""`이면 힌팅 없음 |
| `--ksx-symbols` / `--no-ksx-symbols` | 켬 | KS X 1001 특수문자 추가 |
| `--fallback-font` | `upstream/noto/NotoSansKR[wght].ttf` | Pretendard에 없는 문자의 출처, `""`이면 Pretendard만 |
| `--ttc` / `--no-ttc` | 켬 | 글꼴마다 `.ttc`도 만듦 |
| `--webfonts` | 끔 | WOFF2와 `@font-face` CSS도 만듦 |
| `--families` | `standard narrow` | 만들 글꼴 |
| `--family-name` / `--narrow-family-name` | `Hangyeol Code` / `Hangyeol Code Narrow` | 글꼴 이름 |
| `--font-version` | 패키지 버전 (`1.001`) | 폰트에 기록할 버전 (`MAJOR.MINOR`, `1.001` → `Version 1.001`) |
| `--variants` / `--weights` / `--styles` | 16종 전부 | 일부만 빌드 |
| `--narrow-ratio` | `0.9` | Narrow 칸 너비 비율 |
| `--narrow-min-margin` | `7.5` | 줄이기 전에 남길 좌우 여백 (폰트 단위) |
| `--narrow-max-shift` | `20` | 여백 사이에 들지 않는 글자를 줄이기 전에 옆으로 옮길 최대 거리 (폰트 단위, 칸 가운데까지만), `0`이면 옮기지 않음 |
| `--narrow-max-shrink` | `0.1` | 가로 최대 축소 |
| `--narrow-hangul-hints` / `--narrow-symbols-hints` / `--narrow-icons-hints` | `data/hints-narrow*.json` | Narrow 묶음별 이동표 |
| `--no-hints` | 끔 | 두 글꼴 모두 이동표 힌팅 없이 빌드 |
| `--narrow-report` | 없음 | Narrow에서 글자마다 어떻게 처리했는지 TSV로 남김 |

`make hints`는 똑바른 8종을 힌팅 없이 한 번 빌드한 뒤 이동표 네 개(`data/hints.json`,
`data/hints-narrow.json`, `-symbols`, `-icons`)를 모두 다시 계산합니다.

패키지 버전은 폰트 버전과 같은 `MAJOR.MINOR` 형식(`1.001`)입니다. uv는 이를 PEP 440에 따라
`1.1`로 표시하지만, 폰트에는 `Version 1.001`로 기록됩니다.

### 릴리스

`pyproject.toml`의 버전과 같은 이름의 태그(예: `v1.001`)를 푸시하면 GitHub Actions가 원본을
내려받아 테스트하고, 두 글꼴을 빌드해 압축 파일 세 개(TTF·TTC 두 개, 웹폰트 하나)와
`.ttc`를 붙인 초안 릴리스를 만듭니다. `make package`는 `fonts/ttf`의 TTF로 웹폰트(`make
webfonts`)를 다시 만든 뒤 압축합니다.

### Windows ClearType 렌더링

`tools/render-windows`는 Windows에서 DirectWrite로 폰트를 렌더링하는 .NET 8 도구입니다. 폰트를
설치하지 않고 파일에서 바로 읽고, 렌더링 설정을 코드에서 정하므로 서비스로 도는 CI 에이전트에서도
사용자 ClearType 설정과 상관없이 같은 결과가 나옵니다.

```bash
dotnet run --project tools/render-windows -c Release -- --fonts fonts/ttf --out renders
```

- 두 글꼴을 ClearType(natural symmetric), 그레이스케일, GDI classic으로 11·14·18px씩 그려
  5배 확대한 PNG와 실제 크기 PNG(`-1x`)를 `renders/`에 남깁니다. 합자는 DirectWrite가 적용합니다.
- `tools/render-windows/probe/`의 시험용 폰트(`scripts/make_hint_probe.py`)는 사각형 하나를 정해진
  거리만큼(+1/8, +1/2, −1/8px) 옮깁니다. DirectWrite가 실제로 얼마나 옮기는지 모드별로
  `renders/probe.tsv`에 적습니다. `--strict`를 주면, 명령과 반대로 움직인 크기가 있거나 natural
  모드에서 10–20px 평균 이동이 명령의 절반 넘게 어긋날 때 실패합니다. 명령이 없는 폰트가 힌팅을
  켜고 끌 때 움직이거나, 시험용 폰트 폴더나 폰트가 없을 때도 실패합니다.
- DirectWrite는 세로 경계를 natural 모드에서 약 1/4px, GDI classic에서 1px 단위로 그립니다. 그래서
  1/8px 이동은 크기에 따라 0, 약 1/8, 1/4px(GDI classic은 0이나 1px)로 나타납니다.
- 한글은 grid fitting을 켜고 끈 두 상태의 잉크 중심 차이를 `data/hints*.json`의 크기별 이동값과 함께
  `renders/hint-check.tsv`에 적습니다. 가는 획은 이 양자화로 두께도 바뀌어 중심이 더 크게 움직이므로,
  이 표는 참고용이고 합격 여부는 시험용 폰트로 정합니다.
- `renders/info.json`에 Windows·DirectWrite 버전과 렌더링 설정을 적습니다. DirectWrite는 Windows
  빌드마다 결과가 조금씩 다르므로 이미지를 비교할 때 함께 봅니다.
- `.buildkite/pipeline.yml`은 Linux 에이전트에서 폰트를 빌드하고 Windows 에이전트에서 이 도구를
  돌리는 예시입니다. 에이전트 큐 이름은 환경에 맞게 바꾸고, Windows 에이전트에는 .NET 8 SDK
  이상을 설치합니다.

### 프로젝트 구조

| 경로 | 내용 |
|---|---|
| `src/hangyeol_code/builder.py` | 영문·한글·특수문자 합치기, 문자 폭, 이름과 버전, 크기별 이동 힌팅 |
| `src/hangyeol_code/narrow.py` | Narrow 변환: 글자별 이동·축소, 결합 부호·합자·마크 위치, 힌팅 묶음 |
| `src/hangyeol_code/cli.py` | `hangyeol-code` 명령. 변형마다 한 번 합친 뒤 두 글꼴로 마무리 |
| `scripts/compute_phase_hints.py` | 이동표 계산 (FreeType, `hints` 의존성 그룹) |
| `data/` | 이동표 JSON |
| `download_upstream.py` | 원본 폰트 내려받기 (버전·해시 고정) |
| `tests/` | 합치기·CLI·Narrow 테스트 |
| `.github/workflows/` | 검사(CI)와 릴리스 |
| `assets/` | README 이미지 |
| `tools/render-windows/` | Windows DirectWrite 렌더링과 한글 힌팅 검사 (.NET 8) |
| `.buildkite/` | Windows 렌더링 파이프라인 예시 |

## 만드는 방법

1. **바탕:** JetBrainsMono Nerd Font Mono를 그대로 씁니다. 영문 글리프의 윤곽과 힌팅
   명령은 원본과 바이트 단위로 같습니다.
2. **한글 크기와 위치:** JetBrains Mono는 `( )`를 세로로 힌팅하지 않습니다. 그래서
   `( )`는 어느 크기에서나 윤곽 비율대로 그려지고, 배율과 오프셋 하나로 모든 크기에서
   맞출 수 있습니다.
   - `[ ]`, `{ }`는 원본 힌팅으로 픽셀에 붙어 크기마다 `( )`보다 최대 0.7px 위아래로
     움직입니다. 이 부분은 원본 그대로 두었습니다.
3. **한글 힌팅:** `scripts/compute_phase_hints.py`가 힌팅 없는 빌드의 한글을 FreeType으로
   1/64px씩 위아래로 옮겨 가며 렌더링합니다.
   - 점수는 KS X 1001 한글 2,350자 전부에 대한 `Σa³/Σa`(a는 픽셀 농도)입니다. 검은
     픽셀일수록 무게가 커집니다.
   - ±1/8px 안에서 점수가 가장 높은 위치를 고릅니다. 이 범위는 ±1/4px일 때 얻는 이득의
     61%를 유지하면서 `( )`와 어긋나는 정도를 절반으로 줄이는 값입니다.
   - 빌더는 이 표를 크기별 TrueType 명령(SHPIX)으로 각 한글 글리프에 넣습니다. Windows
     DirectWrite에서 의도한 만큼 움직이는 것을 확인했습니다.
4. **특수문자:** Noto Sans KR은 Pretendard 한글의 원본(Source Han Sans)입니다.
   - 공통 한글 음절로 Pretendard 좌표계에 맞추고(오차 약 1단위), 굵기마다 한글 획 두께가
     같은 `wght`를 찾습니다. 획 두께 비는 0.98–1.01입니다.
   - 한 칸에 줄여 넣는 기호는 획이 가늘어진 만큼의 절반을 더 굵은 인스턴스로 보정합니다.
   - 원 숫자(①–⑮), `㈜`, `♡`, `♪`는 같은 묶음(원 문자, 괄호 한글, 카드, 음표)이 한
     디자인이 되도록 Noto Sans KR에서 가져옵니다.
   - 분수는 JetBrains Mono의 `½`처럼 칸 전체를 가로지르는 사선에 분자·분모 숫자를 0.73배로
     줄여 붙입니다. 줄인 만큼 획이 가늘어지므로 숫자는 두 단계 굵은 원본에서 가져옵니다.
   - `≒`는 `=`와 마침표 두 개를 조합한 글리프라 각 부품의 힌팅이 그대로 적용됩니다. 점과
     가로획 사이는 `÷`와 같습니다.
5. **문자 폭:** 넓은 문자(W·F)는 두 칸, 나머지는 한 칸으로 맞춥니다. 원본에서 한 칸이던
   넓은 문자(`⚡` U+26A1, `﹢` U+FE62)는 두 칸 가운데로 옮깁니다.
6. **이름 표:** 저작권 표기 맨 앞에 Hangyeol Code를 넣고, Pretendard와 Noto Sans KR의
   저작권·상표 고지를 덧붙입니다. 제작사·디자이너·URL은 이 프로젝트 것으로 바꾸고,
   Regular·Bold 외 굵기는 패밀리 이름에 굵기를 넣습니다(`Hangyeol Code Thin` / `Regular`).

## 알려진 한계

- 한 칸에 맞춘 기호(`℃ ① ★` 등)와 반각 한글은 작게 보입니다. 두 칸으로 넣으면 터미널에서
  다음 칸과 겹칩니다.
- `♥`(U+2665)는 Nerd Fonts가 넣은 Octicons 하트(외곽선) 그대로입니다.
- 첫가끝 중성·종성 자모(U+1161–11C2)는 두 칸 너비입니다. 따로 쓰이면 호환 자모 모양으로
  그리고, 초성과 이어지면 ccmp로 음절을 만들기 때문입니다. 터미널은 이 자모를 0칸으로
  셉니다. 거의 쓰이지 않는 문자입니다.
- `⅓ ⅔ ⅛ ⅜ ⅝ ⅞`는 새로 만든 윤곽이라 TrueType 힌팅이 없습니다. JetBrains Mono의
  `½ ¼ ¾`보다 작은 크기에서 조금 흐릴 수 있습니다.
- 한글 힌팅은 글자 전체를 옮기는 방식이라, 획 하나하나를 맞추는 힌팅보다는 효과가
  작습니다. ttfautohint로 획마다 맞추는 방식도 시험했지만, 음절마다 높이가 1px씩 달라져서
  쓰지 않았습니다.
- Narrow에서 `đ ħ ư ƒ`처럼 획이 한쪽 끝에만 닿는 글자는 20단위까지 옮겨도 모자라 조금
  줄어듭니다(`đ`는 0.94배). 옮긴 글자는 `d`와 `đ`처럼 짝을 이루는 글자와 그만큼 어긋납니다.
  한 칸 기호(`① ★`)는 Hangyeol Code보다 조금 더 작습니다.

## 변경 기록

- **1.001** (2026-10-17, Narrow 2026-10-18)
  - 칸 너비를 10% 줄인 Hangyeol Code Narrow를 추가했습니다.
  - Nerd Fonts를 3.4.0에서 3.5.1로 올렸습니다. 아이콘이 10,396개에서 10,610개로 늘었고,
    점자 패턴(U+2800–U+28FF) 256자가 들어왔으며, `❬ ❭` 모양이 바뀌었습니다.
  - Nerd Fonts 아이콘 약 600개가 원본보다 1단위(1/1000em) 왼쪽에 그려지던 문제를
    고쳤습니다. 원본 글리프 머리의 xMin이 실제 윤곽과 1단위 어긋나 있었는데, 저장할 때
    xMin을 다시 계산하면서 글리프가 밀렸습니다. 이제 왼쪽 여백을 함께 맞춰서 원본과 같은
    위치에 그려집니다.
  - 폰트에 버전 정보를 넣었습니다. `head.fontRevision`은 1.001이고, 이름 표 5번에 원본
    버전을 함께 적습니다.
  - KS X 1001 특수문자 988자를 모두 담았습니다. `㉾`(KS X 1001:2002 추가)를 넣고, `⅔ ≒`를
    새로 만들었으며, `⅓ ⅛ ⅜ ⅝ ⅞`는 Pretendard 모양에서 `½`와 같은 모양으로 바꿨습니다.
  - 반각 한글(U+FFA1–FFDC)을 두 칸에서 한 칸으로, `⚡`(U+26A1)와 `﹢`(U+FE62)를 한 칸에서
    두 칸으로 바꿨습니다.
  - 웹용 WOFF2와 CSS 묶음(`HangyeolCode-webfont-<버전>.zip`)을 함께 배포합니다.
  - Regular·Bold 외 굵기의 이름을 Windows 규칙에 맞췄습니다. Office 같은 앱에서 모든
    굵기를 고를 수 있습니다.
  - 제작사·디자이너·URL·vendor ID를 JetBrains에서 이 프로젝트 것으로 바꾸고, 저작권
    표기에 Hangyeol Code를 넣었습니다. Mac용 이름 레코드와 FontForge 전용 표(`PfEd`)를
    뺐습니다.
  - 한글 정렬 값과 힌팅 값은 1.000과 같습니다.
- **1.000** (2026-10-17): 첫 배포.

## 라이선스

[SIL Open Font License 1.1](LICENSE)입니다. Hangyeol Code는 아래 원본들의 수정판(Modified
Version)이며, 폰트 파일뿐 아니라 이 저장소의 빌드 스크립트와 문서도 같은 라이선스로
배포합니다. 빌드 코드는 Jetendard와 Yeomil Mono에서 이어받았고, 둘 다 OFL로
배포되었습니다.

- 폰트를 내려받아 쓰고, 문서에 넣고, 소프트웨어와 함께 배포하는 것은 자유입니다. 폰트만
  따로 팔 수는 없습니다.
- 수정판도 OFL 1.1로 배포해야 하고, [LICENSE](LICENSE)의 저작권 고지를 함께 넣어야 합니다.
- **Hangyeol Code는 예약 폰트 이름(Reserved Font Name)을 두지 않았습니다.** 수정판은 이
  이름을 그대로 쓰거나 바꿔 쓸 수 있습니다.
- 원본들의 예약 이름 때문에 수정판의 이름에는 다음 단어를 쓸 수 없습니다: Jetendard,
  Yeomil Mono, Pretendard, Source, Inter, M PLUS 1.
- 상표: JetBrains Mono는 JetBrains s.r.o.의, Pretendard는 Kil Hyung-jin의, Inter는 rsms의,
  Source는 Adobe의 상표입니다.
- Nerd Fonts 아이콘은 세트마다 라이선스가 다릅니다(Font Awesome·Codicons는 CC BY 4.0,
  Material Design Icons는 Apache 2.0, Octicons·Devicons 등은 MIT 등). 자세한 내용은
  [Nerd Fonts license audit](https://github.com/ryanoasis/nerd-fonts/blob/-/license-audit.md)를
  보세요.

| 원본 | 버전 | 쓰인 부분 | 라이선스 |
|---|---|---|---|
| [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) | 2.304 | 영문, 합자, 기호, 힌팅 | OFL 1.1 |
| [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) (JetBrainsMono NFM) | 3.5.1 | 아이콘, 점자 패턴 | OFL 1.1, 아이콘별 라이선스 |
| [Pretendard](https://github.com/orioncactus/pretendard) | 1.3.9 | 한글, 특수문자, 가나 | OFL 1.1 (RFN Pretendard) |
| [Noto Sans KR](https://fonts.google.com/noto/specimen/Noto+Sans+KR) (Source Han Sans) | 2.004 | Pretendard에 없는 특수문자, 옛한글 자모 | OFL 1.1 (RFN Source) |
| [Jetendard](https://github.com/kuskhan/jetendard) | 4b018fc | 빌드 파이프라인 | OFL 1.1 (RFN Jetendard) |
| [Yeomil Mono](https://github.com/taevel02/yeomil-mono) | — | Jetendard가 바탕으로 삼은 구조 | OFL 1.1 (RFN Yeomil Mono) |

버전은 2026-10-17 기준 각 원본의 최신 배포판입니다.

- JetBrains Mono 저장소에는 2024년 8월에 다시 빌드한 2.305가 있습니다. 하지만 정식
  릴리스가 아니고, 힌팅 없는 가변 폰트뿐이며, Nerd Fonts 최신판도 2.304를 씁니다. 그래서
  2.304를 유지합니다.
- Nerd Fonts 3.5.1 이후의 커밋은 설치 스크립트와 패처의 진행 표시만 고쳤고, 글리프는
  바뀌지 않았습니다.
- Pretendard는 1.3.9 이후 소스 정리만 있고 새로 빌드한 폰트가 없습니다.
- Noto Sans KR은 google/fonts 저장소의 최신 파일과 같습니다. 해시로 고정해 두었습니다.

## 감사의 말

이 폰트는 [Jetendard](https://github.com/kuskhan/jetendard)(Jung Woong Park)의 빌드 파이프라인을
바탕으로 만들었습니다. Jetendard는 [Yeomil Mono](https://github.com/taevel02/yeomil-mono)
(Taehoon Kwon)의 구조를 이어받았습니다. JetBrains Mono, Nerd Fonts, Pretendard, Source Han Sans와
Noto Sans KR을 만든 분들께 감사드립니다. 이 이름들은 출처를 밝히기 위한 것이며, 원저작자들이
이 폰트를 보증한다는 뜻은 아닙니다.
