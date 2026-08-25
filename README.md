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
| 9 | **ICU plural coverage** — a `plural` that omits a form its language actually selects, plus malformed messages, a missing `other`, misspelt or duplicated categories | 🚸 Graded | structural errors always; missing forms only with real CLDR rules |
| 10 | **Self-test** — the analyzer run against a synthetic project with planted problems, one assertion per behaviour | 🧪 Meta | on demand |

### On the plural check

A Russian plural written with the two branches English needs passes every
other check in this file: the key exists, the value is Russian, the
placeholder is there. It is simply wrong for 2, 3, 4 and for 5 and up.

Findings are graded by *how they were reached*, never by how confident the
tool feels:

| Finding | Needs a rule table? | Severity |
|---|---|---|
| No `other` branch, braces that never close, a keyword that is not a plural category, the same branch twice | no — ICU says so | 🔥 always blocking |
| A form this language selects for everyday counts is missing (Russian `few`, Arabic `two`) | yes | ⚠️ blocking with Babel installed, capped at ⚠️ medium from the built-in table |
| A form only millions, decimals or compact notation reach (Italian `many`) | yes | ℹ️ low |
| A branch this language never selects (`zero` in English) | yes | ℹ️ low |
| A plural in the source flattened to a plain string in a translation | no | 🚸 medium |

That last split matters more than it looks: current CLDR gives Italian a
`many` category, but it only fires from a million upwards. Demanding it
would flag every correctly written Italian plural in existence. The tool
tells the two apart by *running each language's own rules over real
counts* rather than carrying a hand-written list of which languages are
which — so the distinction stays right for languages this tool has never
heard of.

Unknown language, no rules available? The structural checks still run; the
coverage ones stay quiet rather than guess.

`select` is left alone apart from requiring `other` — its branch names are
arbitrary (`male`/`female`/`other`), and judging them against CLDR
categories would flag every correct gender select.

**Collect-then-fail**: every check always runs, the Markdown report is
always generated, and only at the very end does the process exit non-zero
listing all blocking findings — one early failure never hides the rest.

## How it reads your code

Python is read with the standard library's `ast`. Every other language is
read with **tree-sitter** when its grammar is available, and with a regex
when it is not. Thirty-six file extensions are supported today: JS, TS,
JSX/TSX, Vue, Svelte, Astro, PHP, Kotlin, Java, C#, Go, Rust, Ruby, Dart,
QML, Lua, Swift, Objective-C, C, C++, Elixir, Scala, Groovy, Perl and Haxe.

The parse tree does not *replace* the regex, it **corrects** it. A straight
swap was written first and lost real keys, and losing a key is the worse
failure — it turns a live key into a false orphan and hides a real
unresolved-key finding. So the rule is:

> keys = (regex hits the tree cannot disprove) + (calls the tree found)

A regex hit is dropped only when the tree can point at the string literal
or the comment containing it. So `t('x')` written inside a string, or in a
mid-line `// t('old.key')` the regex's whole-line comment stripping never
saw, stops counting as usage — while everything tree-sitter cannot parse
keeps the regex result untouched.

A parse that reports **error nodes** counts as "cannot parse" for the
purpose of dropping: whatever the tree found is still added, but its idea
of where a string ends is no longer believed. That matters where one
extension has several languages behind it (`.h`, `.m`) and the grammar
picked may simply be the wrong one.

Two shapes need more than a grammar. **Single-file components** —
`.vue`, `.svelte`, `.astro` — keep their script body as raw text, so each
block is handed to the language it declares (`lang="ts"` included) and the
byte offsets are shifted back into the file's own coordinates. And a call's
key is **not always its first argument**: `pgettext(context, key)` puts it
second, `ngettext(singular, plural, n)` has one in each of the first two,
and the `d*` family leads with a domain. Reading slot 0 regardless does not
merely miss a key — it files a context or a domain string as one, which
then masks a real orphan.

Which backend read your sources is printed with the scan summary, so the
answer is never a guess.


**Python** sources get a **context-aware AST analysis**, not regexes:

- direct calls — `t('section.key')`, `tr(...)`, `_(...)`, `gettext(...)`…
- dynamic prefixes — `t(f'status.{value}')` keeps the whole family alive
- variables — `key = 'nav.home'; t(key)`
- concatenation — `t('section.' + var)`
- ternaries — `t('a.x' if cond else 'a.y')` (both branches)

Hardcoded-string detection distinguishes strings passed to Qt widget
setters/constructors (`setText`, `QLabel`, …) from generic literals, with
per-tier filtering to keep the noise down.

**Other languages** are read for the same things:

- calls — `t('key')`, `$t('key')`, `i18n.t("key")`, `__('key')`, `tr(...)`,
  `qsTr(...)`, `NSLocalizedString(...)`, the gettext family…
- factory calls — `useTranslations()('nav.home')`, where the key goes to
  what the call *returns*
- template-literal prefixes — `` t(`nav.${page}`) `` keeps the `nav.*`
  family alive for the orphan analysis
- hardcoded UI text, from the parse tree — see below

That covers the cross-language checks (**unresolved keys** and
**orphans**) on any codebase. Minified bundles (`*.min.js`) and generated
output are skipped by shape, not by name.

Commented-out code never counts as usage, but the two backends earn that
differently, and the difference is the reason the tree is worth having.
The regex has to blank comments before it can look, which means guessing
where one starts: it strips `/* … */` and whole-line `//` or `#`, and
deliberately leaves a mid-line `//` alone because eating that would eat
the `//` in every `https://` inside a string. So a stale
`doThing();  // t('old.key')` still counted. The tree does not guess —
it knows which bytes are a comment and which are a string literal, and a
match landing in either is dropped.

### Coverage guarantee by language tier

Estimated share of real-world key usages the extractor captures — every
run prints how many files were scanned in which mode, and which backend
read them.

| Tier | Languages | Method | Key extraction | Hardcoded detection | Notes |
|------|-----------|--------|:---:|:---:|-------|
| **Full** | Python | `ast` (stdlib) | ~99% | ✅ | Literals, f-string prefixes, variables, concatenation, ternaries, keys passed by keyword; severity-graded hardcoded detection with `line:column` and source preview |
| **High** | JS, TS, JSX/TSX, Vue, Svelte, Astro, PHP | tree-sitter → regex | ~90% | ✅ parsed | Dotted-key `t()`-style calls are the ecosystem norm (`i18next`, `vue-i18n`, Laravel `__()`); factory calls (`useTranslations()('k')`) are read too. Misses keys held in variables or built by concatenation |
| **Conditional** | Dart, Kotlin, Java, C#, Ruby, Go, Rust, Lua, Scala, Groovy, Perl, Haxe | tree-sitter → regex | ~60–75% | ✅ parsed | Captured **only if** the project uses a dotted-key `t()`-style API; ecosystem-native resource systems (Android `R.string`, .NET `.resx`, Flutter ARB codegen) are not parsed |
| **Low** | QML, Swift, Objective-C, C, C++, Elixir | tree-sitter → regex | ~40% | ✅ parsed | The idiomatic call carries the **source text**, not a key: `qsTr("English text")`, `NSLocalizedString("Save", …)`, gettext's `_("Save")`. The calls are recognised and their argument read; only a project that puts key-shaped strings in them gets usable output |

Grammars are present for every extension in the table, so "→ regex" is
the fallback for a machine where tree-sitter is not installed, not for a
language it cannot handle.

The **Hardcoded detection** column is about the strings a project forgot
to translate, and is a separate question from key extraction: it depends
on the syntax being readable, not on the i18n API being key-shaped. That
is why a language can sit in the Low tier for keys and still be ✅ here.

**Precision is measured; recall is estimated.** These are different
quantities and the table above is the second one. The first has a number:
all **36 supported extensions** reject a translation call written inside
a string literal *and* one written inside a comment — the two things a
regex cannot tell from a real call. Each was checked with a decoy of each
kind, and a language that kept a decoy was fixed rather than listed. That
says nothing about how many of a codebase's keys are shaped the way the
extractor can see, which is what the percentages are about.

**What the parse tree does and does not change.** It mostly does not
raise the percentages above, and the reason is structural: the tree
*corrects* the regex rather than replacing it, so the set of keys found is
the union of both and recall can only be ≥ the regex's own. What improves
is **precision** — a `t('x')` written inside a string literal, or inside a
mid-line `// t('old.key')` that whole-line comment stripping never saw,
stops counting as a usage. Both used to inflate the "used keys" set,
which hides real orphans and can raise a blocking unresolved-key finding
for a key nobody actually calls. Dynamic prefixes are read from the tree
too, so `` gettext(`menu.${x}`) `` yields its family even though the
prefix regex only knows the shorter list of function names.

Recall does move where a call shape was invisible to *both* backends:
Qt's `qsTr` (without which a `.qml` file came back empty, which reads as
"no keys here"), Objective-C's `@"…"` prefix before the opening quote,
and the second and third arguments of the gettext family.

On a project with no such cases nothing moves at all: a real-world
JS/JSX codebase measured here reported identical findings with the tree
and without it.

Percentages are honest engineering estimates, not measurements: they
describe how much of each ecosystem's *typical* usage the patterns can
see. When a tier's assumptions don't hold for your project, the
locale-vs-locale checks (1, 2, 4, 5, 8) still apply in full — only the
code-aware checks (3, 7) degrade.

**Hardcoded strings outside Python are read from the tree too.** A bare
string in JS says nothing about itself: it could be UI text, a CSS
selector, an object key or an import path. The tree knows which it is, and
that is now what the check asks:

- **text nodes** — the words between the tags, with a sentence broken by
  an interpolation reported whole (`Total for {…} nights`) rather than as
  the pieces either side of the hole, and an HTML entity counted as part
  of the label it sits in (`Succ &gt;` is `Succ >`, not the single word
  `Succ` that the multi-word rule would drop)
- **UI attributes** — the value of `placeholder=`, `title=`, `alt=`,
  `aria-label=` and the rest; `className=` and `id=` deliberately not
- **calls that show text** — `alert(…)`, `setText(…)`, the project's own
  `ui_functions`, and `setAttribute("placeholder", …)`, where the visible
  half is the second argument
- **excluded by structure, not by heuristic** — import paths, the key half
  of an object entry, and anything already going through `t()`

Argument shapes differ far more than the calls do, and each was read off
its grammar rather than assumed: PHP and C# wrap every argument in a node
of its own, Kotlin and Swift keep theirs behind a `call_suffix`, Groovy
behind an `arg_block`, and Dart has no call node at all — an identifier
and a selector side by side. A file whose parse reports **errors** falls
back to the heuristic tier rather than being read from a guessed
structure.

*Measured on a real 70-file JSX application:* the heuristic tier found 15
strings, the parsed tier finds 45 — all 15 of them plus 30 it could not
see, and nothing lost. On a synthetic project with one file per supported
language, all 22 planted UI strings are found across 23 languages.

The **heuristic tier is still there**, reported under its own section
labelled *LOW RELIABILITY*, and answers for whatever the tree cannot: a
missing grammar, a machine without tree-sitter, a file that will not
parse. Which tier answered is recorded per file and named in the report,
because "hint" and "read from the syntax" are not the same claim.


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

One optional file, `.i18n-quality.json`. **It writes itself** the first
time it is missing: a commented template with every value empty, which
changes nothing until something is filled in and is safe to delete. A
read-only checkout says so and carries on with the built-ins. Present but
unreadable also says so, rather than looking like a clean pass. A
byte-order mark — what Notepad and Windows PowerShell add by default — is
tolerated. Run `--vocab-help` for the short version.

**In a monorepo each package answers for itself.** The nearest file above
a source file is the one in force for it, inheriting everything it does
not mention: lists add to the parent's, objects merge key by key, and a
scalar is simply the nearer answer. Budgets are the exception and are read
from the root only — a budget is a ceiling on the whole run, and the
totals it compares against are global.

```json
{
  "tech_words":   ["acmecloud", "widgetdrive", "unreal"],
  "ui_functions": ["HouseLabel", "showBanner"],
  "exclude_dirs": ["vendor", "generated"],
  "exempt":       { "raise_arguments": false },
  "translation_kwargs":      ["msg_key"],
  "extra_translation_calls": ["houseT", "useHouseTranslations"],
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
- **`exclude_dirs`** — directories to skip on top of the universal ones
  (caches, virtualenvs, build output, the test tree). Non-shipping code
  goes here: dev-only scripts, vendored copies, an archive of old
  sources. Nothing about one repository belongs in the tool, which is why
  this is a list here and not a constant in the script.
- **`exempt`** — the three noise suppressions, each on by default:
  `raise_arguments` (the message of an exception the code raises),
  `regex_patterns`, `user_agents`. Whatever they hold back is **counted
  and named in the report** rather than dropped in silence, so turning one
  off is a decision made with the number in front of you. A project whose
  exception text reaches a dialog turns `raise_arguments` off.
- **`translation_kwargs`** — keyword names that carry the key, for a
  wrapper written `t(key='nav.home')`. The common ones (`key`, `msgid`,
  `id`, …) are built in.
- **`extra_translation_calls`** — the project's own translation call
  names, and factories whose *result* takes the key
  (`useTranslations()('nav.home')`). Both shapes are tried for every name,
  because declaring which one it is would be one more thing to get wrong.
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
🟢 Self-test passed (143 cases).
```

Three scenarios run, not one: a JSON/Python project, a JavaScript one
whose dictionaries live in a module under `src/`, and an ICU one carrying
Russian, Arabic and Italian plurals. One layout only ever proves itself —
the JS scenario exists because a real project reported *"no i18n
dictionaries found"* while its `src/i18n/translations.js` sat right there,
and the ICU scenario exists because this codebase contains no ICU at all,
so without a fixture the entire plural engine would ship unexercised.

A fourth scenario covers extraction precision: `t()` written inside a
string and inside a mid-line comment, next to genuine keys in Vue, PHP,
QML, Objective-C and Lua — a single-file component's `<script>` body, a
Qt `qsTr` call and an `@"…"` prefix among them, each added after being
measured to fail rather than on the strength of a grammar existing.

The JSON/Python scenario also carries a **monorepo**: a package with its
own `.i18n-quality.json` declaring a widget name and an excluded folder,
a sibling package declaring nothing, and cases asserting that the first
package's settings apply inside it, inherit the root's, and are unknown to
the sibling. Without that last one the feature would pass while being
global after all.

Two scenarios run **twice**, under both of their backends, because
otherwise which half of that code gets tested is decided by whichever
optional package happens to be installed — the ICU one against real CLDR
rules and against the built-in table, the extraction one with tree-sitter
and without. On top of the per-case assertions, the JavaScript scenario is
analysed under both extraction backends and its findings compared field by
field: a backend that quietly moved a line number or dropped a key would
keep every boolean case green while changing what the tool reports.

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
- `Babel` — optional, swaps the built-in plural table for real CLDR rules and lets missing-form findings block
- `tree-sitter` + `tree-sitter-language-pack` — optional, parse trees for non-Python sources instead of regex

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
   The installer treats **PyYAML, Babel and tree-sitter as optional** —
   PyYAML only matters for YAML locale files, Babel only sharpens the ICU
   plural check, tree-sitter only sharpens key extraction from non-Python
   sources. If any is unavailable the run says so and carries on; only a
   missing `langdetect` is fatal.

   Two notes on size and portability. Babel is a 10 MB wheel because it
   carries the whole CLDR database, which is precisely what makes it worth
   vendoring for a plural checker. tree-sitter ships **compiled** wheels
   with no practical sdist fallback — the language pack would have to build
   every grammar from source — so a vendored copy fits the OS and Python it
   was downloaded for, and elsewhere the regex extractor takes over. That is
   what the fallback is for; nothing fails.

   By hand, if you prefer:

   ```bash
   pip wheel langdetect --no-deps -w offline_deps    # universal wheel (any OS/Python 3)
   pip download langdetect pyyaml -d offline_deps    # six + platform pyyaml wheel + sdists
   pip download pyyaml --no-binary pyyaml -d offline_deps --no-deps  # pyyaml sdist: any OS
   pip download babel -d offline_deps                # universal wheel, CLDR plural rules
   pip download tree-sitter tree-sitter-language-pack -d offline_deps  # compiled: this OS/Python
   ```

   When the folder is present, the auto-installer uses it **first** with
   `--no-index` (zero network) and only falls back to PyPI if it's
   missing or insufficient. Note: wheels are OS/Python-specific — the
   sdists (`.tar.gz`) cover every platform.

2. **Pre-install** in the target environment:
   `pip install langdetect pyyaml babel tree-sitter tree-sitter-language-pack`.

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
- **Optional dependencies never change the verdict silently.** Babel and
  tree-sitter each sharpen a check, and each is replayed in the self-test
  with and without, so neither ships as the half that happens to be
  installed. Where an optional backend could disagree with the fallback,
  the run says which one answered.
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
