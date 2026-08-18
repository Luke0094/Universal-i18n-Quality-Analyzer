# 🔍 Universal i18n Quality Analyzer

> One-file, zero-config quality gate for translated projects: point it at
> a repo and it cross-checks the translation dictionaries against each
> other **and against the code that uses them** — Python gets a full
> AST analysis, most other languages a key-usage scan.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Formats](https://img.shields.io/badge/i18n-JSON%20%7C%20YAML-orange)
![Languages](https://img.shields.io/badge/tool%20UI-en%20%7C%20it%20%2B%20packs-green)
![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-green)

Works on any project — it auto-discovers the i18n layout, runs with no
configuration at all, and ships as a single script plus an optional
Windows launcher. Nothing about any one project is baked into it: a
codebase that wants to teach it its own brand names, house widgets or
quality budgets does so from an optional file in its own root.

---

## What it checks

| # | Check | Severity | Blocking |
|---|-------|----------|----------|
| 1 | **Duplicate JSON keys** (same nesting level — silent data loss) | 🔥 Critical | yes |
| 2 | **Broken placeholders** — `{name}`/`{count}` sets differ between languages | 🔥 Critical | yes |
| 3 | **Keys used in code but defined in no locale** — render as raw keys in the UI | 🔥 Critical | yes |
| 4 | **Empty translation values** | ⚠️ High | yes |
| 5 | **Missing keys** — defined in one language, absent in another | ⚠️ High | yes |
| 6 | **Hardcoded UI strings** — untranslated text reaching a widget, graded `high`/`medium`/`low` by how certain it is that a user sees it | 🚸 Graded | only past a declared budget |
| 7 | **Orphan keys** — defined but never referenced, classified by confidence (dynamic-prefix families are flagged, never assumed dead) | 🚸 Medium | no |
| 8 | **Mixed-language values** — e.g. English text inside the Italian dictionary, backed by stopword evidence + langdetect | ℹ️ Low | yes |
| 9 | **Self-test** — the analyzer run against a synthetic project with planted problems, one assertion per behaviour | 🧪 Meta | on demand |

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
| **Full** | Python | AST | ~99% | ✅ | Literals, f-string prefixes, variables, concatenation, ternaries; severity-graded hardcoded detection with `line:column` and source preview |
| **High** | JS, TS, JSX/TSX, Vue, Svelte, PHP | regex | ~90% | ⚠️ hints | Dotted-key `t()`-style calls are the ecosystem norm (`i18next`, `vue-i18n`, Laravel `__()`); misses keys held in variables or built by concatenation |
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
E) JS/TS module              src/i18n/translations.js
                             export const translations = { en: {...}, it: {...} }
```

Scanned directory names: `i18n`, `locales`, `locale`, `lang`,
`translations` — searched to a bounded depth, not only at the repo root,
because `src/i18n` is the default in every Vite/CRA/Vue project.

**JS/TS modules** (`export const … = {…}`, `export default {…}`,
`module.exports = {…}`) are parsed with a tolerant scanner that handles
bare keys, single quotes, trailing commas and comments, and that stops
rather than guesses when it meets a template literal, a function or a
reference — a module that is not static data is reported as unreadable,
never half-parsed. Reading `t('key')` out of JavaScript while being unable
to read the JavaScript that *defines* those keys is the gap this closes.

**Build output is skipped by shape, not by name.** `*.min.js` is one
convention; Vite emits `index-4PCLXdBb.js`, which no name test catches.
A file whose longest line runs to hundreds of characters is a bundle, and
scanning one duplicates every string already found in the sources.

## Usage

```bash
python test_universal_quality_analysis.py                 # scan the repo it lives in
python test_universal_quality_analysis.py --root C:\path\to\project
python test_universal_quality_analysis.py --report out.md
python test_universal_quality_analysis.py --lang en       # force tool language
python test_universal_quality_analysis.py --self-test     # check the analyzer itself
python test_universal_quality_analysis.py --vocab-help    # explain the project file
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
with `--report`). Summary table plus one detail section per category.
Every hardcoded finding is written the way a compiler writes a
diagnostic — `line:column`, clickable — followed by the source line it
sits on, so a fragment like `` ` file(s) missing, e.g. ` `` can be judged
without opening the file:

```
- [3554:51](../core/backup.py#L3554): ` file(s) missing, e.g. `
  ↳ `detail = f"{len(gone)} file(s) missing, e.g. {gone[0]}"`
```

Columns are exact inside f-strings too: they point at the offending
fragment, not at the expression containing it.

## Severity and budgets

Hardcoded-string findings are graded by how confident the tool is that a
user actually reads the string:

| Severity | What it is | Typical content |
|---|---|---|
| **high** | an argument to a call that puts text on screen | button labels, tooltips, window titles |
| **medium** | a label-shaped string handed to a function the tool does not know | constants passed to house helpers |
| **low** | passed the general heuristics and nothing more | exception messages, internal diagnostics |

The grading is what separates a worklist from an inventory. A typical run
looks like `high: 0 · medium: 24 · low: 288` — the low tier is mostly
engine error text nobody is asking to translate, and the handful that
matter are no longer buried in it.

By default the counts are informational. Declare **budgets** and they
become a ratchet: exceeding one is a blocking failure, so the numbers can
only come down.

```json
{ "budgets": { "high": 0, "medium": 24, "low": 288 } }
```

A tool that starts failing builds the day it is adopted gets switched off,
so budgets are opt-in and absent means "report only".

## Project configuration

One optional file, `.i18n-quality.json`, in the scanned root (or under
`--root`). Absent, it is ignored. Unreadable, it says so and falls back to the
built-ins rather than looking like a clean pass. A byte-order mark — what
Notepad and Windows PowerShell add by default — is tolerated. Run
`--vocab-help` for the short version.

```json
{
  "tech_words":   ["acmecloud", "widgetdrive", "unreal"],
  "ui_functions": ["HouseLabel", "showBanner"],
  "budgets":      { "high": 0 }
}
```

- **`tech_words`** — names the language detector must treat as neutral.
  Brands, products, engines and sites are spelled the same in every
  locale, so finding one in a translated string is not evidence it was
  left in the wrong language. The analyzer ships the wide-reach names
  every project may use — operating systems, major clouds, protocols —
  and this is where a project adds its own domain. Nothing about one
  project belongs in the tool.
- **`ui_functions`** — extra call names whose string arguments reach the
  screen. The tool knows Qt, tkinter, GTK, wxPython and Kivy; a house
  widget library goes here so the high-severity tier keeps working for
  it instead of silently switching off.
- **`budgets`** — see above.

## Checking the analyzer itself

`--self-test` builds a synthetic project in a temp directory, plants
known problems **and known non-problems** in it, runs the full analysis
and asserts each one:

```
🧪 SELF-TEST — the analyzer checked against itself
  [OK  ] ui_hardcoded           a string passed to a UI setter is found at high severity
  [OK  ] ignore_comment         # i18n-ignore silences the line it sits on
  [OK  ] method_ignored         a string argument to .get() is not a finding
  [OK  ] function_not_ignored   a string argument to a FUNCTION named get() still is
  [OK  ] vocab_loaded           the project's own tech_words reach the neutral vocabulary
  …
🟢 Self-test passed (26 cases).
```

Two scenarios run, not one: a JSON/Python project and a JavaScript one
whose dictionaries live in a module under `src/`. One layout only ever
proves itself — the second scenario exists because a real project
reported *"no i18n dictionaries found"* while its
`src/i18n/translations.js` sat right there.

The heuristics here are hand-curated lists, and a mistake in one is
invisible on the codebase it was written against. The negative cases
carry as much weight as the positive ones: several assert that something
is **not** reported, which is where a silent recall hole would otherwise
hide. Exit code is nonzero on failure, so it belongs in CI next to the
analysis itself.

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
   next to the script. Two scripts do both halves:

   ```bash
   ./download_offline_deps.sh    # once, on a machine WITH network
   ./install_offline_deps.sh     # on the offline machine
   ```

   On Windows: `download_offline_deps.bat` / `install_offline_deps.bat`.
   The installer treats **PyYAML as optional** — it only matters for YAML
   locale files, so if its wheel does not fit the target's OS/Python the
   run says so and carries on; only a missing `langdetect` is fatal.

   By hand, if you prefer:

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
- **Ignore lists are matched by call shape**: a name is skipped as a
  method (`x.get(...)`) or as a plain function (`get(...)`), never both.
  One flat list meant a project with a *function* named `get()` or
  `format()` had its user-facing strings dropped without trace.
- **The tool is tested against itself** — see `--self-test`. Its
  heuristics are curated lists, and the only thing that catches a wrong
  one is an assertion, not a clean-looking report.
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
> (https://github.com/Luke0094/Universal-i18n-Quality-Analyzer) — Universal i18n Quality Analyzer
