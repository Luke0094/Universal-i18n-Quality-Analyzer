# 🔍 Universal i18n Quality Analyzer

> One-file, zero-config quality gate for translated projects: point it at
> a repo and it cross-checks the translation dictionaries against each
> other **and against the code that uses them** — Python gets a full
> AST analysis, most other languages a key-usage scan.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Formats](https://img.shields.io/badge/i18n-JSON%20%7C%20YAML-orange)
![Languages](https://img.shields.io/badge/tool%20UI-en%20%7C%20it%20%2B%20packs-green)
![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-green)

Works on any project — it auto-discovers the i18n layout, needs no
configuration, and ships as a single script plus an optional Windows
launcher.

---

## What it checks

| # | Check | Severity | Blocking |
|---|-------|----------|----------|
| 1 | **Duplicate JSON keys** (same nesting level — silent data loss) | 🔥 Critical | yes |
| 2 | **Broken placeholders** — `{name}`/`{count}` sets differ between languages | 🔥 Critical | yes |
| 3 | **Keys used in code but defined in no locale** — render as raw keys in the UI | 🔥 Critical | yes |
| 4 | **Empty translation values** | ⚠️ High | yes |
| 5 | **Missing keys** — defined in one language, absent in another | ⚠️ High | yes |
| 6 | **Hardcoded UI strings** — untranslated text passed to Qt widgets, three context tiers | 🚸 Medium | no |
| 7 | **Orphan keys** — defined but never referenced, classified by confidence (dynamic-prefix families are flagged, never assumed dead) | 🚸 Medium | no |
| 8 | **Mixed-language values** — e.g. English text inside the Italian dictionary, backed by stopword evidence + langdetect | ℹ️ Low | yes |

**Collect-then-fail**: every check always runs, the Markdown report is
always generated, and only at the very end does the process exit non-zero
listing all blocking findings — one early failure never hides the rest.

## How it reads your code

**Python** sources get a **context-aware AST analysis**, not regexes:

- direct calls — `t('section.key')`, `tr(...)`, `_(...)`, `gettext(...)`…
- dynamic prefixes — `t(f'status.{value}')` keeps the whole family alive
- variables — `key = 'nav.home'; t(key)`
- concatenation — `t('section.' + var)`
- ternaries — `t('a.x' if cond else 'a.y')` (both branches)

Hardcoded-string detection distinguishes strings passed to Qt widget
setters/constructors (`setText`, `QLabel`, …) from generic literals, with
per-tier filtering to keep the noise down.

**Other languages** go through a regex key extractor:

- calls — `t('key')`, `$t('key')`, `i18n.t("key")`, `__('key')`, `tr(...)`…
- template-literal prefixes — `` t(`nav.${page}`) `` keeps the `nav.*`
  family alive for the orphan analysis

That covers the cross-language checks (**unresolved keys** and
**orphans**) on any codebase. Commented-out code is stripped first, so a
stale `// t('old.key')` never raises a false blocking finding; minified
bundles (`*.min.js`) are skipped.

### Coverage guarantee by language tier

Estimated share of real-world key usages the extractor captures — every
run prints how many files were scanned in which mode:

| Tier | Languages | Method | Key extraction | Hardcoded detection | Notes |
|------|-----------|--------|:---:|:---:|-------|
| **Full** | Python | AST | ~99% | ✅ | Literals, f-string prefixes, variables, concatenation, ternaries; context-aware hardcoded tiers |
| **High** | JS, TS, JSX/TSX, Vue, Svelte, PHP | regex | ~90% | ❌ | Dotted-key `t()`-style calls are the ecosystem norm (`i18next`, `vue-i18n`, Laravel `__()`); misses keys held in variables or built by concatenation |
| **Conditional** | Dart, Kotlin, Java, C#, Ruby, Go, Rust | regex | ~60–75% | ❌ | Captured **only if** the project uses a dotted-key `t()`-style API; ecosystem-native resource systems (Android `R.string`, .NET `.resx`, Flutter ARB codegen) are not parsed |
| **Low** | QML | regex | ~40% | ❌ | `qsTr("English text")` is text-based, not key-based — only key-style helper calls are caught |

Percentages are honest engineering estimates, not measurements: they
describe how much of each ecosystem's *typical* usage the patterns can
see. When a tier's assumptions don't hold for your project, the
locale-vs-locale checks (1, 2, 4, 5, 8) still apply in full — only the
code-aware checks (3, 7) degrade.

**Hardcoded strings outside Python — hints only.** A bare string in
JS/TS says nothing about itself — it could be UI text, a CSS selector,
an object key or a log message. Python's AST provides the call context
(`setText(...)` → user-visible) that makes the check reliable; a regex
can't. Non-Python sources therefore get a **minimal heuristic tier**,
reported under its own section explicitly labelled *LOW RELIABILITY*:

- UI-ish attributes — `placeholder=`, `title=`, `label=`, `tooltip=`, …
- dialog-like calls — `alert("…")`, `setText("…")`, `Text("…")`, …
- multi-word text nodes in `.vue`/`.jsx`/`.tsx`/`.svelte` templates

Multi-word strings only, hard-capped per file, `i18n-ignore` honoured.
Treat these as hints to verify by hand — expect both false positives and
missed strings; the reliable tiers remain the Python ones.

## Supported i18n layouts (auto-discovered)

```
A) one file per language     locales/en.json, locales/it.json   (flat or nested)
B) single multilanguage file translations.json  {"en": {...}, "it": {...}}
C) inline per-key            strings.json       {"greeting": {"en": "Hello", "it": "Ciao"}}
D) YAML variants of A/B/C    (if PyYAML is installed)
```

Scanned directory names: `i18n`, `locales`, `locale`, `lang`,
`translations` — plus common single-file names at the repo root.

## Usage

```bash
python test_universal_quality_analysis.py                 # scan the repo it lives in
python test_universal_quality_analysis.py --root C:\path\to\project
python test_universal_quality_analysis.py --report out.md
python test_universal_quality_analysis.py --lang en       # force tool language
```

On Windows, double-click **`quality_analysis.bat`** — it finds Python
(`py -3` or `python`), forwards any arguments, prints an OK/failure
summary and keeps the window open. On Linux/macOS use
**`./quality_analysis.sh`** (`chmod +x` once): it probes for a working
Python **≥ 3.10** — a stale `python3` on PATH is skipped, not trusted.
Both propagate the exit code, so the same launchers work in CI.

**Exit codes**: `0` = no blocking findings · `1` = blocking findings
(full list printed at the end, report generated either way).

**Report**: `UNIVERSAL_QUALITY_REPORT.md` next to the script (override
with `--report`). Summary table plus one detail section per category,
with clickable file/line links for hardcoded strings.

## Suppressing a finding

Add a trailing comment on the offending line:

```python
splash_label.setText("SaveSync")   # i18n-ignore
```

Declared exceptions instead of permanently tolerated noise.

## Tool language & language packs

The tool itself speaks **English** and **Italian** (auto-detected from
the system locale, forced with `--lang`). Adding a language needs **no
code changes**:

```bash
# 1. generate a template with every message in English
python test_universal_quality_analysis.py --export-lang-template es

# 2. translate the values in qa_lang_es.json (partial is fine —
#    untranslated messages fall back to English)

# 3. done: 'es' now appears in --lang and in the auto-detection
```

Packs are flat JSON files named `qa_lang_<code>.json` living next to the
script.

## Requirements

- Python **3.10+**, standard library only for the core
- `langdetect` — auto-installed on first run (mixed-language check)
- `PyYAML` — optional, enables YAML i18n layouts

### Offline use / vendored dependencies

The only network access the tool may ever perform is the **one-time**
auto-install of `langdetect` on first run. Two ways to make runs fully
offline (CI runners, air-gapped machines, packages gone from PyPI):

1. **Vendored folder (recommended)** — ship an `offline_deps/` folder
   next to the script. Populate it once, from any online machine:

   ```bash
   pip wheel langdetect --no-deps -w offline_deps    # universal wheel (any OS/Python 3)
   pip download langdetect pyyaml -d offline_deps    # six + platform pyyaml wheel + sdists
   pip download pyyaml --no-binary pyyaml -d offline_deps --no-deps  # pyyaml sdist: any OS
   ```

   When the folder is present, the auto-installer uses it **first** with
   `--no-index` (zero network) and only falls back to PyPI if it's
   missing or insufficient. Note: wheels are OS/Python-specific — the
   sdists (`.tar.gz`) cover every platform.

2. **Pre-install** in the target environment: `pip install langdetect pyyaml`.

With either in place the tool never touches the network.

## Design notes

- **(pid-)Deterministic**: `langdetect` is seeded, results are stable
  across runs.
- **Orphans are never auto-deleted**: keys reachable through dynamic
  prefixes can't be proven dead statically, so the report flags them with
  a confidence level and leaves the decision to a human.
- Directories named `build`, `dist`, `venv`, `__pycache__`, `tests`,
  `node_modules` (and any dot-directory) are excluded from the code scan.

---

## License

Released under the [PolyForm Noncommercial License 1.0.0](LICENSE) —
© 2026 [Luke0094](https://github.com/Luke0094).

You may use, modify and share this tool freely **for noncommercial
purposes** (personal use, hobby, research, education, nonprofits),
keeping the copyright notice with every copy. Selling it, or
distributing it as part of a paid product or service, is not permitted.

> Required Notice: Copyright (c) 2026 Luke0094
> (https://github.com/Luke0094) — Universal i18n Quality Analyzer
