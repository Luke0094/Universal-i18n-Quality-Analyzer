#!/usr/bin/env python3
"""
🔍 TEST UNIVERSALE DI QUALITÀ i18n + CODICE
Versione 8.0 — Multi-Format, Auto-Discovery

Supported i18n layouts:
  A) Separate files per locale:     locales/en.json, locales/it.json  (flat or nested)
  B) Single file, lang top-keys:    translations.json  {"en":{…}, "it":{…}}
  C) Inline per-key translations:   strings.json       {"greeting":{"en":"Hello","it":"Ciao"}}
  D) YAML variants of A/B/C         (if PyYAML is installed)

Auto-discovery: scans common directory names (i18n, locales, locale, lang, translations)
and common file names (translations.json, strings.json, messages.json, i18n.json, lang.json).

Source scanning: Python gets the full context-aware AST analysis (used
keys + hardcoded strings); JS/TS/JSX/TSX/Vue/Svelte/PHP/Dart/Kotlin/
Java/C#/Ruby/Go/Rust/QML sources go through a regex extractor for used
keys and dynamic prefixes (template literals) — so the unresolved-keys
and orphan checks cover the whole codebase, whatever it is written in.
"""

import os
import sys
import json
import ast
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict

# The tool's output is full of emoji/box-drawing characters: on consoles
# whose default encoding is not UTF-8 (Windows cp1252, some CI logs) the
# very first print would crash with UnicodeEncodeError. Force UTF-8 with
# replacement — degraded glyphs beat a dead run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==========================================
# 🌐 TOOL LOCALISATION (console + report)
# ==========================================
# The tool speaks English and Italian. Language is auto-detected from the
# system locale and can be forced with --lang en|it.
TOOL_LANG = "en"


def _detect_tool_lang() -> str:
    """Best-match the system locale against the AVAILABLE tool languages
    (embedded + loaded packs) — never against a hardcoded list."""
    cand = ""
    try:
        import locale as _loc
        try:
            _loc.setlocale(_loc.LC_CTYPE, "")
        except Exception:
            pass
        cand = (_loc.getlocale()[0] or "")
    except Exception:
        pass
    cand = (cand or os.environ.get("LANG", "")).lower()
    for code in TOOL_LANGS:
        if cand.startswith(code) or cand.startswith(_LANG_EN_NAMES.get(code, code)):
            return code
    return "en"


# Windows spells locales with English language names ("Italian_Italy",
# "Spanish_Spain") — map pack codes to those prefixes for detection.
_LANG_EN_NAMES = {
    "it": "italian", "es": "spanish", "fr": "french", "de": "german",
    "pt": "portuguese", "ru": "russian", "ja": "japanese", "zh": "chinese",
    "pl": "polish", "nl": "dutch", "tr": "turkish", "ko": "korean",
}


_L10N = {
    # console
    "dep_installing": {"en": "📦 Dependency 'langdetect' not found. Installing...",
                        "it": "📦 Dipendenza 'langdetect' non trovata. Installazione in corso..."},
    "dep_failed":     {"en": "❌ Could not install langdetect: {err}",
                        "it": "❌ Impossibile installare langdetect: {err}"},
    "start":          {"en": "🔍 STARTING UNIVERSAL i18n QUALITY TEST (v8.0 Multi-Format)...",
                        "it": "🔍 AVVIO TEST UNIVERSALE DI QUALITÀ (v8.0 Multi-Format)..."},
    "no_locales":     {"en": "⚠️ No i18n dictionaries found in the project.",
                        "it": "⚠️ Nessun dizionario i18n trovato nel progetto."},
    "fmt_detected":   {"en": "   Detected format: {fmt}", "it": "   Formato rilevato: {fmt}"},
    "langs_found":    {"en": "   Languages found: {langs}", "it": "   Lingue trovate:   {langs}"},
    "total_keys":     {"en": "   Total keys:      {n}", "it": "   Chiavi totali:    {n}"},
    "blocking":       {"en": "❌ {n} BLOCKING ISSUE CATEGORY(-IES):",
                        "it": "❌ {n} CATEGORIA/E DI PROBLEMI BLOCCANTI:"},
    "all_pass":       {"en": "🟢 All blocking checks passed.",
                        "it": "🟢 Tutti i controlli bloccanti superati."},
    "an_python":      {"en": "🔤 SOURCE CODE ANALYSIS (keys + hardcoded strings)...",
                        "it": "🔤 ANALISI CODICE SORGENTE (chiavi + hardcoded)..."},
    "scan_summary":   {"en": "   scanned: {py} Python file(s) [AST, full analysis] + {other} other-language file(s) [regex, key extraction]",
                        "it": "   analizzati: {py} file Python [AST, analisi completa] + {other} file in altri linguaggi [regex, estrazione chiavi]"},
    "an_missing":     {"en": "📊 MISSING KEYS ANALYSIS...", "it": "📊 ANALISI CHIAVI MANCANTI..."},
    "an_unresolved":  {"en": "🧩 KEYS USED IN CODE BUT NOT DEFINED...",
                        "it": "🧩 ANALISI CHIAVI USATE NEL CODICE MA NON DEFINITE..."},
    "unresolved_bad": {"en": "   ❌ {n} key(s) called with t() but absent from EVERY locale:",
                        "it": "   ❌ {n} chiave/i chiamate con t() ma assenti da OGNI locale:"},
    "unresolved_ok":  {"en": "   🟢 every key used in code exists in the locales",
                        "it": "   🟢 ogni chiave usata nel codice esiste nei locale"},
    "an_empty":       {"en": "🕳️ EMPTY VALUES & PLACEHOLDER ANALYSIS...",
                        "it": "🕳️ ANALISI VALORI VUOTI E PLACEHOLDER..."},
    "an_orphans":     {"en": "👻 ORPHAN KEYS ANALYSIS (v2 — classified)...",
                        "it": "👻 ANALISI CHIAVI ORFANE (v2 — classificate)..."},
    "orphan_high":    {"en": "   ⚠️ {n} key(s) with NO static reference at all:",
                        "it": "   ⚠️ {n} chiave/i senza ALCUN riferimento statico:"},
    "orphan_low":     {"en": "   ℹ️ {n} key(s) in families with dynamic prefixes (low confidence)",
                        "it": "   ℹ️ {n} chiave/i in famiglie con prefissi dinamici (bassa confidenza)"},
    "orphan_none":    {"en": "   🟢 no orphan keys", "it": "   🟢 nessuna chiave orfana"},
    "an_mixed":       {"en": "🌍 MIXED-LANGUAGE ANALYSIS (v2 — stopword evidence)...",
                        "it": "🌍 ANALISI LINGUE MISTE (v2 — stopword evidence)..."},
    "report_gen":     {"en": "📝 GENERATING REPORT...", "it": "📝 GENERAZIONE REPORT IN CORSO..."},
    "done":           {"en": "🎉 Done! Report: {path}", "it": "🎉 Finito! Report: {path}"},
    # blocking-failure summaries
    "fail_missing":    {"en": "{n} missing translation key(s): {items}",
                         "it": "{n} chiave/i di traduzione mancanti: {items}"},
    "fail_unresolved": {"en": "{n} key(s) used in code but defined in NO locale (they render as raw keys in the UI): {items}",
                         "it": "{n} chiave/i usate nel codice ma definite in NESSUN locale (in UI appaiono come chiave grezza): {items}"},
    "fail_empty":      {"en": "{n} empty translation value(s): {items}",
                         "it": "{n} valore/i di traduzione vuoti: {items}"},
    "fail_dups":       {"en": "{n} duplicate JSON key(s): {items}",
                         "it": "{n} chiave/i JSON duplicate: {items}"},
    "fail_mixed":      {"en": "{n} mixed-language translation(s): {items}",
                         "it": "{n} traduzione/i in lingua mista: {items}"},
    # report
    "r_title":        {"en": "# 📊 Universal i18n Quality Report (v8.0)\n",
                        "it": "# 📊 Report Universale Qualità i18n (v8.0)\n"},
    "r_format":       {"en": "> Format: **{fmt}**\n\n", "it": "> Formato: **{fmt}**\n\n"},
    "r_summary":      {"en": "## 🎯 Summary\n", "it": "## 🎯 Riepilogo\n"},
    "r_table":        {"en": "| Category | Issues | Status | Severity |\n|-----------|----------|-------|---------|\n",
                        "it": "| Categoria | Problemi | Stato | Gravità |\n|-----------|----------|-------|---------|\n"},
    "cat_dups":       {"en": "Duplicate JSON keys (same level)", "it": "JSON Duplicati (stesso livello)"},
    "cat_vars":       {"en": "Broken variables (placeholders)", "it": "Variabili Rotte (Placeholder)"},
    "cat_unresolved": {"en": "Keys used but not defined", "it": "Chiavi Usate ma Non Definite"},
    "cat_empty":      {"en": "Empty values", "it": "Valori Vuoti"},
    "cat_missing":    {"en": "Missing keys", "it": "Chiavi Mancanti"},
    "cat_hardcoded":  {"en": "Hardcoded texts", "it": "Testi Hardcoded"},
    "cat_orphans":    {"en": "Orphan keys", "it": "Chiavi Orfane"},
    "cat_mixed":      {"en": "Mixed languages", "it": "Lingue Miste"},
    "sev_crit":       {"en": "🔥 Critical", "it": "🔥 Critica"},
    "sev_high":       {"en": "⚠️ High", "it": "⚠️ Alta"},
    "sev_med":        {"en": "🚸 Medium", "it": "🚸 Media"},
    "sev_low":        {"en": "ℹ️ Low", "it": "ℹ️ Bassa"},
    "st_ok":          {"en": "🟢 OK", "it": "🟢 OK"},
    "st_err":         {"en": "🔴 Error", "it": "🔴 Errore"},
    "st_warn":        {"en": "🟠 Warning", "it": "🟠 Avviso"},
    "st_info":        {"en": "🟡 Info", "it": "🟡 Info"},
    "tier_ui_t":      {"en": "🔤 Hardcoded texts (UI widget context)",
                        "it": "🔤 Testi Hardcoded (contesto UI widget)"},
    "tier_ui_d":      {"en": "Strings passed directly to Qt widgets (setText, QLabel, etc.) without translation.",
                        "it": "Stringhe passate direttamente a widget Qt (setText, QLabel, ecc.) senza traduzione."},
    "tier_func_t":    {"en": "🔤 Hardcoded texts (function-arg labels)",
                        "it": "🔤 Testi Hardcoded (label in funzioni)"},
    "tier_func_d":    {"en": "ALL-CAPS strings passed as function arguments — likely UI headings/labels.",
                        "it": "Stringhe ALL-CAPS passate come argomento a funzioni — probabili intestazioni/etichette UI."},
    "tier_gen_t":     {"en": "🔤 Hardcoded texts (general context)",
                        "it": "🔤 Testi Hardcoded (contesto generico)"},
    "tier_gen_d":     {"en": "Strings that look like UI text but are not in direct widget calls.",
                        "it": "Stringhe che sembrano testo UI ma non sono in chiamate widget dirette."},
    "tier_rx_t":      {"en": "🔤 Hardcoded texts — non-Python sources (LOW RELIABILITY)",
                        "it": "🔤 Testi Hardcoded — sorgenti non-Python (BASSA AFFIDABILITÀ)"},
    "tier_rx_d":      {"en": "⚠️ Heuristic hints WITHOUT syntax context: expect false positives AND missed strings. UI-ish attributes (placeholder/title/label…), dialog-like calls and multi-word template text nodes only. Treat as hints, verify by hand.",
                        "it": "⚠️ Indizi euristici SENZA contesto sintattico: aspettati falsi positivi E stringhe mancate. Solo attributi UI (placeholder/title/label…), chiamate tipo dialog e nodi di testo multi-parola nei template. Trattali come indizi, verifica a mano."},
    "r_line":         {"en": "- [Line {line}]({rp}#L{line}): `{text}`\n",
                        "it": "- [Linea {line}]({rp}#L{line}): `{text}`\n"},
    "r_unresolved_h": {"en": "## 🧩 Keys used in code but not defined\n> Passed literally to a t()-family call, absent from every locale — they render as raw keys in the UI.\n\n",
                        "it": "## 🧩 Chiavi usate nel codice ma non definite\n> Passate letteralmente a una chiamata t(), assenti da ogni locale — in UI appaiono come chiave grezza.\n\n"},
    "r_missing_h":    {"en": "## 🔑 Missing keys\n", "it": "## 🔑 Chiavi Mancanti\n"},
    "r_vars_h":       {"en": "## 💥 Broken variables\n", "it": "## 💥 Variabili Rotte\n"},
    "r_vars_line":    {"en": "- `{key}` in `{lang}`: expected `{master}`, found `{found}`\n",
                        "it": "- `{key}` in `{lang}`: atteso `{master}`, trovato `{found}`\n"},
    "r_empty_h":      {"en": "## 🕳️ Empty translations\n", "it": "## 🕳️ Traduzioni Vuote\n"},
    "r_orphans_h":    {"en": "## 👻 Orphan keys\n", "it": "## 👻 Chiavi Orfane\n"},
    "r_orphan_high":  {"en": "### 🔴 No static reference (high confidence)\n> No literal occurrence, no dynamic prefix, no variable/concatenation reaching it.\n\n",
                        "it": "### 🔴 Nessun riferimento statico (alta confidenza)\n> Nessuna occorrenza del literal, nessun prefisso dinamico, nessuna variabile/concatenazione che la raggiunga.\n\n"},
    "r_orphan_low":   {"en": "### 🟡 Family with dynamic prefixes (low confidence)\n> A sibling key of the same parent IS reached dynamically: this one COULD be too with other runtime values. Do not remove without checking.\n\n",
                        "it": "### 🟡 Famiglia con prefissi dinamici (bassa confidenza)\n> Una chiave sorella dello stesso padre è raggiunta dinamicamente: questa POTREBBE esserlo con altri valori a runtime. Non rimuovere senza verifica.\n\n"},
    "r_mixed_h":      {"en": "## 🌍 Mixed languages\n", "it": "## 🌍 Lingue Miste\n"},
    "r_mixed_line":   {"en": "- `{lang}` / `{key}`: `{text}` *(detected {det} at {pct}%)*\n",
                        "it": "- `{lang}` / `{key}`: `{text}` *(rilevato {det} al {pct}%)*\n"},
    "r_dups_h":       {"en": "## 🚨 Duplicate keys (same JSON level)\n",
                        "it": "## 🚨 Chiavi Duplicate (stesso livello JSON)\n"},
    # detected-format descriptions
    "fmt_a":          {"en": "A — one file per language ({path})",
                        "it": "A — file separati per lingua ({path})"},
    "fmt_b":          {"en": "B — single file, language top-level keys ({path})",
                        "it": "B — file singolo, chiavi lingua al top-level ({path})"},
    "fmt_c":          {"en": "C — inline per-key translations ({path})",
                        "it": "C — traduzioni inline per chiave ({path})"},
}


def _load_language_packs() -> None:
    """Merge external language packs into the embedded catalog.

    A pack is a flat JSON file named  qa_lang_<code>.json  next to this
    script: {"start": "...", "done": "...", ...} — same keys as _L10N,
    missing keys simply fall back to English. Dropping such a file is ALL
    it takes to add a language: the CLI choices, the auto-detection and
    every message pick it up with zero code changes (generate a starting
    point with --export-lang-template <code>)."""
    for f in sorted(Path(__file__).parent.glob("qa_lang_*.json")):
        code = f.stem[len("qa_lang_"):].strip().lower()
        if not code:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ language pack {f.name} ignored: {e}")
            continue
        for key, text in data.items():
            if key in _L10N and isinstance(text, str) and text.strip():
                _L10N[key][code] = text


_load_language_packs()
# Available tool languages, derived from the catalog — NOT hardcoded.
TOOL_LANGS = sorted({lang for msg in _L10N.values() for lang in msg})


def L(key: str, **kw) -> str:
    msg = _L10N[key]
    text = msg.get(TOOL_LANG) or msg["en"]
    return text.format(**kw) if kw else text


TOOL_LANG = _detect_tool_lang()   # --lang overrides this in __main__


# ==========================================
# 📦 AUTO-INSTALLAZIONE DIPENDENZE
# ==========================================
def _ensure_langdetect():
    try:
        from langdetect import detect_langs, DetectorFactory
        from langdetect.lang_detect_exception import LangDetectException
        DetectorFactory.seed = 0
        return detect_langs, LangDetectException
    except ImportError:
        print(L("dep_installing"))
        # VENDORED-FIRST: if an offline_deps/ folder sits next to this
        # script (populated once with `pip download langdetect pyyaml -d
        # offline_deps`), install from there with NO network access —
        # covers fresh machines and the day a package vanishes from PyPI.
        # Only when that folder is absent or insufficient fall back to PyPI.
        _offline = Path(__file__).parent / "offline_deps"
        _cmds = []
        if _offline.is_dir() and any(_offline.iterdir()):
            # --no-build-isolation: if only sdists are vendored, pip must
            # not try to fetch build deps from the index it can't reach.
            _cmds.append([sys.executable, "-m", "pip", "install", "--no-index",
                          "--no-build-isolation",
                          f"--find-links={_offline}", "langdetect", "--quiet"])
        _cmds.append([sys.executable, "-m", "pip", "install", "langdetect", "--quiet"])
        _err = None
        for _cmd in _cmds:
            try:
                subprocess.check_call(_cmd)
                _err = None
                break
            except Exception as e:
                _err = e
        try:
            if _err is not None:
                raise _err
            from langdetect import detect_langs, DetectorFactory
            from langdetect.lang_detect_exception import LangDetectException
            DetectorFactory.seed = 0
            return detect_langs, LangDetectException
        except Exception as e:
            print(L("dep_failed", err=e))
            sys.exit(1)

detect_langs, LangDetectException = _ensure_langdetect()

def _try_import_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        return None

yaml_mod = _try_import_yaml()

# ==========================================
# ⚙️ CONFIGURAZIONE
# ==========================================
PROJECT_ROOT = Path(__file__).parent.parent
PYTHON_EXCLUDES = {"__pycache__", ".git", ".venv", "venv", "node_modules",
                   "build", "dist", "tests", "egg-info",
                   # Non-shipping code: the user's manual backup tree and the
                   # dev-only asset generators — scanning them duplicated
                   # every finding and flagged Pillow mode strings (PNG/RGBA).
                   "OLD", "tools"}

# ISO 639-1 codes we recognise as language keys
_ISO_CODES = {
    'af','am','ar','az','be','bg','bn','bs','ca','cs','cy','da','de','el',
    'en','es','et','eu','fa','fi','fr','ga','gl','gu','ha','he','hi','hr',
    'hu','hy','id','is','it','ja','jv','ka','kk','km','kn','ko','ku','ky',
    'lb','lo','lt','lv','mg','mk','ml','mn','mr','ms','mt','my','nb','ne',
    'nl','nn','no','or','pa','pl','ps','pt','ro','ru','rw','sd','si','sk',
    'sl','so','sq','sr','sv','sw','ta','te','tg','th','tk','tl','tr','tt',
    'uk','ur','uz','vi','xh','yo','zh','zu',
    # Common extended codes
    'zh-cn','zh-tw','pt-br','en-us','en-gb','es-mx','fr-ca',
}

LANGUAGE_MAP = {c: c.split('-')[0] for c in _ISO_CODES}

TRANSLATION_FUNCTIONS = {'tr', '_', 'translate', 'get_text', 't', 'i18n', 'ngettext', 'gettext'}

# ── Multi-language source scanning ──────────────────────────────────────────
# Python gets the FULL context-aware AST analysis (used keys + hardcoded
# strings). Every other language goes through a regex extractor that
# collects used keys and dynamic prefixes — enough to power the
# unresolved-keys and orphan checks across the whole codebase.
_REGEX_CODE_EXTENSIONS = {
    '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.vue', '.svelte',
    '.php', '.dart', '.kt', '.kts', '.java', '.cs', '.rb', '.go', '.rs',
    '.qml',
}

# t('key') / tr("key") / $t('key') / i18n.t('key') / __('key') …
_RX_CODE_CALL = re.compile(
    r"""(?:\b|\$)(?:t|tr|tc|translate|gettext|ngettext|i18n|get_text|__)"""
    r"""\s*\(\s*(['"])([A-Za-z0-9][A-Za-z0-9_.-]*)\1""")
# JS template literals: t(`section.${x}`) → dynamic family 'section.'
_RX_CODE_TEMPLATE = re.compile(
    r"""(?:\b|\$)(?:t|tr|tc|translate|i18n)\s*\(\s*`([A-Za-z0-9][A-Za-z0-9_.-]*\.)\$\{""")


# Strip comments BEFORE extraction: a commented-out t('old.key') call
# must not count as usage — a stale key there would raise a FALSE
# blocking "unresolved" finding. Block comments /* … */ and FULL-LINE
# // or # comments only; a mid-line '//' is deliberately left alone,
# stripping it would eat URLs inside string literals ('https://…').
_RX_CODE_COMMENTS = re.compile(r"/\*.*?\*/|^[ \t]*(?://|#).*?$", re.S | re.M)


def _blank_comments(src: str) -> str:
    """Replace comments with whitespace of the SAME shape (newlines kept),
    so offsets and line numbers of every later match stay valid."""
    return _RX_CODE_COMMENTS.sub(
        lambda m: re.sub(r'[^\n]', ' ', m.group(0)), src)


def _extract_keys_regex(src: str) -> Tuple[Set[str], Set[str]]:
    """Best-effort key extraction for non-Python sources."""
    src = _blank_comments(src)
    keys: Set[str] = set()
    prefixes: Set[str] = set()
    for m in _RX_CODE_CALL.finditer(src):
        val = m.group(2)
        if PythonCodeAnalyzer._KEY_PATTERN.match(val):
            keys.add(val)
    for m in _RX_CODE_TEMPLATE.finditer(src):
        prefixes.add(m.group(1))
    return keys, prefixes


# ── Heuristic hardcoded-text hints for non-Python sources ───────────────────
# DECLAREDLY UNRELIABLE (reported as its own low-confidence tier): without
# syntax context a regex cannot prove a string is user-visible. These
# patterns only catch the most indicative shapes, and only multi-word
# strings, to keep the noise floor low. Treat results as HINTS.
_RX_UI_ATTR = re.compile(
    r"""\b(?:placeholder|title|label|alt|aria-label|tooltip|caption|hint"""
    r"""|headerText|buttonText)\s*[=:]\s*(['"])([^'"\n]{3,80})\1""", re.IGNORECASE)
_RX_UI_CALL = re.compile(
    r"""\b(?:alert|confirm|prompt|setText|setTitle|setLabel|setPlaceholder"""
    r"""|setTooltip|setHeader|showMessage|Text|Label|SnackBar)\s*\(\s*(['"])([^'"\n]{3,80})\1""")
_RX_UI_TEXTNODE = re.compile(r">\s*([^<>{}\n|]{4,80}?)\s*<")
_TEXTNODE_EXTENSIONS = {'.vue', '.jsx', '.tsx', '.svelte'}


def _looks_like_ui_text(text: str) -> bool:
    t = text.strip()
    if ' ' not in t:                       # multi-word only — single tokens
        return False                        # are hopeless without context
    if not re.search(r'[A-Za-zÀ-ÿ]{2}', t):
        return False
    if PythonCodeAnalyzer._KEY_PATTERN.match(t):
        return False                        # i18n key, not text
    if '://' in t or re.search(r'[\\/]\w+[\\/]', t):
        return False                        # URL / path
    if re.fullmatch(r'[A-Z0-9_ ]+', t):
        return False                        # SHOUTING_CONSTANTS
    return True


def _extract_hardcoded_regex(src: str, ext: str) -> List[Tuple[int, str]]:
    """Low-confidence hardcoded-text hints with 1-based line numbers.
    Comments are blanked shape-preservingly, so line numbers are exact;
    a line containing 'i18n-ignore' is skipped like in the AST path."""
    clean = _blank_comments(src)
    lines = src.splitlines()
    out: List[Tuple[int, str]] = []
    seen: Set[str] = set()

    def _add(m, group_idx):
        text = m.group(group_idx).strip()
        if not _looks_like_ui_text(text) or text in seen:
            return
        lineno = clean.count('\n', 0, m.start()) + 1
        if 0 < lineno <= len(lines) and 'i18n-ignore' in lines[lineno - 1]:
            return
        seen.add(text)
        out.append((lineno, text))

    for m in _RX_UI_ATTR.finditer(clean):
        _add(m, 2)
    for m in _RX_UI_CALL.finditer(clean):
        _add(m, 2)
    if ext in _TEXTNODE_EXTENSIONS:
        for m in _RX_UI_TEXTNODE.finditer(clean):
            _add(m, 1)
    return out[:40]   # hard cap per file — hints, not an inventory

# ── Mixed-language detection: deterministic stopword evidence ──────────────
# Function-word sets per language. Deliberately FUNCTION words only (articles,
# prepositions, auxiliaries): they are near-impossible in a text genuinely
# written in another language, which makes them a far stronger signal than
# statistical n-gram detection on short UI strings.
_STOPWORDS: Dict[str, Set[str]] = {
    'en': {'the','a','an','and','or','of','to','in','on','for','with','is','are',
           'was','were','be','been','being','will','would','shall','should','can',
           'could','may','might','must','this','that','these','those','it','its',
           'you','your','yours','not','no','nor','from','by','at','as','if','when',
           'while','all','any','each','both','has','have','had','do','does','did',
           'done','more','most','than','then','there','here','into','about','after',
           'before','again','once','only','also','but','so','up','down','out','over',
           'under','new','available','without','within','between','because'},
    'it': {'il','lo','la','i','gli','le','un','uno','una','di','del','della','dei',
           'delle','dello','degli','a','al','alla','ai','alle','allo','agli','da',
           'dal','dalla','dai','dalle','in','nel','nella','nei','nelle','su','sul',
           'sulla','sui','sulle','con','per','tra','fra','e','o','ma','se','che',
           'chi','cui','non','più','meno','come','quando','dove','mentre','dopo',
           'prima','ora','già','ancora','anche','solo','sono','è','sei','siamo',
           'siete','sarà','saranno','essere','stato','stata','stati','state',
           'questo','questa','questi','queste','quello','quella','quelli','quelle',
           'ogni','tutti','tutte','tutto','tutta','altro','altra','altri','altre',
           'nessun','nessuna','qualsiasi','viene','vengono','può','possono','deve',
           'devono','fare','stesso','stessa','sì','senza','verso','oltre','fino',
           'qui','suo','sua','suoi','sue','tuo','tua','tuoi','tue','mio','mia',
           'loro','nostro','nostra','ci','vi','si','li','ne','ed','od','alcun',
           'alcuni','alcune','presente','presenti','durante','contro','però'},
    'fr': {'le','la','les','un','une','des','de','du','au','aux','et','ou','mais',
           'si','que','qui','ne','pas','plus','moins','avec','pour','dans','sur',
           'sous','par','ce','cette','ces','est','sont','sera','être','été','vous',
           'votre','vos','nous','notre','nos','il','elle','ils','elles','tout',
           'tous','toute','toutes','autre','autres','sans','avant','après','chez'},
    'de': {'der','die','das','ein','eine','einen','einem','einer','und','oder',
           'aber','wenn','nicht','kein','keine','mit','für','von','zu','zum','zur',
           'im','am','auf','aus','bei','nach','vor','über','unter','ist','sind',
           'war','waren','sein','wird','werden','wurde','dieser','diese','dieses',
           'alle','jede','mehr','sie','ihre','ihr','wir','unsere','auch','nur',
           'noch','schon','sehr','durch','gegen','ohne'},
    'es': {'el','la','los','las','un','una','unos','unas','de','del','al','y','o',
           'pero','si','que','no','con','para','en','por','sobre','entre','sin',
           'es','son','está','están','ser','será','sido','este','esta','estos',
           'estas','ese','esa','todo','todos','toda','todas','otro','otra','más',
           'menos','cada','su','sus','tu','tus','nuestro','también','sólo','ya',
           'cuando','donde','mientras','antes','después','desde','hasta'},
}

# Languages langdetect notoriously mis-fires on for SHORT latin-script text
# (statistical noise, not real detections). A flag from these needs far more
# evidence than one from a well-separated language.
_LANGDETECT_NOISE = {'cy','ro','ca','so','sw','tl','af','sq','hr','sl','et',
                     'lv','lt','id','ms','fi','eu','gl','da','no','nb','nl'}

_TECH_WORDS = {
    'oauth','api','json','xml','url','sdk','gcp','http','https','webdav',
    'rclone','mega','dropbox','onedrive','google','drive','nextcloud',
    'microsoft','windows','linux','macos','steam','desktop','app','client',
    'server','id','token','key','secret','password','username',
    'scoped','access','full','service','account','create','redirect',
    'savesync','editor','console','portal','azure','credentials',
    'itch','dlsite','mobygames','wikipedia','brave','bing','searxng',
    'duckduckgo','vndb','renpy','unity','regedit','playerprefs','backup',
    'cloud','web','pc','zip','trusted','online','offline','link','tag',
    'hotkey','overlay','provider','timeout','host','path','file','files',
}

# ==========================================
# 🔎 AUTO-DISCOVERY
# ==========================================
_LOCALE_DIR_NAMES = {'i18n', 'locales', 'locale', 'lang', 'languages', 'translations', 'l10n'}
_SINGLE_FILE_NAMES = {'translations', 'strings', 'messages', 'i18n', 'lang', 'locale'}
_DATA_EXTENSIONS = {'.json'}
if yaml_mod:
    _DATA_EXTENSIONS |= {'.yml', '.yaml'}


def _discover_locale_sources(root: Path) -> Tuple[List[Path], List[Path]]:
    """Return (directories_with_per_lang_files, single_multilang_files)."""
    per_lang_dirs: List[Path] = []
    single_files: List[Path] = []

    for child in sorted(root.iterdir()):
        if child.name.startswith('.') or child.name in PYTHON_EXCLUDES:
            continue

        # Check directories
        if child.is_dir():
            if child.name.lower() in _LOCALE_DIR_NAMES:
                # Check if it contains per-lang files (en.json, it.json…)
                has_lang_files = any(
                    f.stem.lower().replace('-', '_').split('_')[0] in _ISO_CODES
                    and f.suffix.lower() in _DATA_EXTENSIONS
                    for f in child.iterdir() if f.is_file()
                )
                if has_lang_files:
                    per_lang_dirs.append(child)
                    continue

                # Check subdirectories (e.g. i18n/locales/)
                for sub in child.iterdir():
                    if sub.is_dir() and sub.name.lower() in _LOCALE_DIR_NAMES:
                        has_sub = any(
                            f.stem.lower().replace('-', '_').split('_')[0] in _ISO_CODES
                            and f.suffix.lower() in _DATA_EXTENSIONS
                            for f in sub.iterdir() if f.is_file()
                        )
                        if has_sub:
                            per_lang_dirs.append(sub)

                # Also check for single multilang files inside the dir
                for f in child.iterdir():
                    if f.is_file() and f.suffix.lower() in _DATA_EXTENSIONS:
                        if f.stem.lower() in _SINGLE_FILE_NAMES:
                            single_files.append(f)

        # Check single multilang files at project root
        elif child.is_file() and child.suffix.lower() in _DATA_EXTENSIONS:
            if child.stem.lower() in _SINGLE_FILE_NAMES:
                single_files.append(child)

    return per_lang_dirs, single_files


def _load_data_file(path: Path) -> Optional[dict]:
    """Load JSON or YAML file into a dict."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix.lower() in {'.yml', '.yaml'} and yaml_mod:
                return yaml_mod.safe_load(f)
            else:
                return json.load(f)
    except Exception:
        return None


def _detect_format(data: dict) -> str:
    """Detect i18n format: 'per_lang_keys', 'inline', or 'nested'."""
    if not data or not isinstance(data, dict):
        return 'nested'

    top_keys = set(data.keys())

    # Format B: top-level keys are ALL language codes → {"en":{…}, "it":{…}}
    if top_keys and all(k.lower() in _ISO_CODES for k in top_keys):
        if all(isinstance(v, dict) for v in data.values()):
            return 'per_lang_keys'

    # Format C: values are dicts whose keys are language codes
    #   {"greeting": {"en":"Hello", "it":"Ciao"}, …}
    sample_values = [v for v in data.values() if isinstance(v, dict)]
    if sample_values and len(sample_values) > len(data) * 0.5:
        inner_keys = set()
        for v in sample_values[:20]:  # sample
            inner_keys.update(k.lower() for k in v.keys())
        lang_ratio = len(inner_keys & _ISO_CODES) / max(len(inner_keys), 1)
        if lang_ratio > 0.6:
            return 'inline'

    # Format A: regular nested dict (used with per-lang files)
    return 'nested'


# ==========================================
# 🌳 AST PARSER
# ==========================================
class PythonCodeAnalyzer(ast.NodeVisitor):
    """Context-aware extractor for translation keys and hardcoded UI strings.

    Key detection:
      - Direct:   t('key')
      - F-string: t(f'prefix.{var}')  → registers prefix
      - Variable: key = 'nav.lib'; t(key)
      - Literals that look like i18n dotted keys in data structures

    Hardcoded string detection (two tiers):
      - **UI-context** strings (args to setText, QLabel, QGroupBox, etc.)
        → flagged even if short/single-word, with minimal false-positive filtering
      - **General** strings (everywhere else)
        → flagged only if they pass strict heuristic filtering
    """

    _KEY_PATTERN = re.compile(r'^[a-z][a-z0-9]*(?:[._][a-z][a-z0-9]*)+$')

    # Functions/methods whose string arguments are DISPLAYED to the user
    _UI_FUNCS = {
        # Qt widget constructors & setters
        'setText', 'setToolTip', 'setPlaceholderText', 'setWindowTitle',
        'setStatusTip', 'setWhatsThis', 'setSuffix', 'setPrefix',
        'setTitle', 'setTabText', 'setItemText', 'setLabelText',
        'showMessage',
        # Constructors that take a visible label as first arg
        'QLabel', 'QPushButton', 'QCheckBox', 'QRadioButton',
        'QGroupBox', 'QAction', 'QMenu', 'QMessageBox',
        'addItem', 'addTab',
    }

    # Functions whose direct string args are NOT UI (logging, system, etc.)
    _IGNORE_FUNCS = {
        # Logging / exceptions
        'print', 'debug', 'info', 'warning', 'error', 'critical', 'exception',
        'Exception', 'ValueError', 'RuntimeError', 'TypeError',
        'FileNotFoundError', 'KeyError', 'ImportError', 'AttributeError',
        'OSError', 'IOError', 'PermissionError', 'NotImplementedError',
        # Styling / formatting
        'setStyleSheet', 'strftime', 'strptime', 'set_style', 'setObjectName',
        # OS / IO
        'getenv', 'setdefault', 'mkdir', 'write_text', 'read_text',
        # Regex
        'compile', 'match', 'search', 'sub', 'findall',
        # String / collection methods
        'connect', 'emit', 'format', 'join', 'replace', 'split',
        'startswith', 'endswith', 'encode', 'decode', 'get', 'pop',
        # Introspection
        'isinstance', 'hasattr', 'getattr', 'setattr', 'type',
        # Path / file
        'Path', 'open', 'write', 'read',
        # Qt non-UI constructors (take technical args, not user text)
        'QFont', 'QColor', 'QSize', 'QPoint', 'QRect',
        'QIcon', 'QPixmap', 'QCursor', 'QBrush', 'QPen',
        'Signal', 'Slot', 'QTimer', 'QThread',
    }

    def __init__(self):
        self.hardcoded_strings: Set[Tuple[int, str]] = set()       # general context
        self.ui_context_strings: Set[Tuple[int, str]] = set()      # UI widget context
        self.func_arg_strings: Set[Tuple[int, str]] = set()        # unknown function arg context
        self.used_translation_keys: Set[str] = set()
        # Literal first-args of t()-family CALLS only — unlike
        # used_translation_keys this never mixes in dotted literals found
        # in data structures (module paths etc.), so it is safe to demand
        # that every one of these keys actually EXISTS in the locales.
        self.t_call_keys: Set[str] = set()
        self.dynamic_key_prefixes: Set[str] = set()
        self._string_vars: Dict[str, Set[str]] = defaultdict(set)

    def _remove_docstring(self, node):
        if ast.get_docstring(node) and hasattr(node, 'body') and node.body:
            if isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                node.body.pop(0)

    def visit_Module(self, node):     self._remove_docstring(node); self.generic_visit(node)
    def visit_ClassDef(self, node):   self._remove_docstring(node); self.generic_visit(node)
    def visit_FunctionDef(self, node):self._remove_docstring(node); self.generic_visit(node)
    def visit_AsyncFunctionDef(self, node): self._remove_docstring(node); self.generic_visit(node)

    def visit_Assign(self, node):
        if (len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            self._string_vars[node.targets[0].id].add(node.value.value)
        # key = f"section.{var}"  (later passed to t(key)) — the prefix
        # keeps the whole dynamic family alive for orphan analysis.
        if isinstance(node.value, ast.JoinedStr):
            self._extract_dynamic_prefix(node.value)
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        # ── i18n key extraction ──
        if func_name in TRANSLATION_FUNCTIONS and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                self.used_translation_keys.add(arg.value)
                self.t_call_keys.add(arg.value)
            elif isinstance(arg, ast.JoinedStr):
                self._extract_dynamic_prefix(arg)
            elif isinstance(arg, ast.Name):
                for val in self._string_vars.get(arg.id, []):
                    if self._KEY_PATTERN.match(val):
                        self.used_translation_keys.add(val)
                        self.t_call_keys.add(val)
            elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
                # t('section.' + var) — register the static prefix
                left = arg.left
                if isinstance(left, ast.Constant) and isinstance(left.value, str) and left.value:
                    self.dynamic_key_prefixes.add(left.value)
            elif isinstance(arg, ast.IfExp):
                # t('a.x' if cond else 'a.y') — both branches are live
                for br in (arg.body, arg.orelse):
                    if isinstance(br, ast.Constant) and isinstance(br.value, str):
                        self.used_translation_keys.add(br.value)
                        self.t_call_keys.add(br.value)
                    elif isinstance(br, ast.JoinedStr):
                        self._extract_dynamic_prefix(br)

        # ── UI-context string collection ──
        if func_name in self._UI_FUNCS:
            for arg in node.args:
                self._collect_ui_strings(arg, node.lineno)
            for kw in node.keywords:
                if kw.arg in ('text', 'title', 'label', 'tooltip', 'message',
                              'suffix', 'prefix', 'placeholder'):
                    self._collect_ui_strings(kw.value, node.lineno)
            # Still recurse for nested t() calls
            self._visit_calls_only(node)
            return

        # ── Ignored functions (logging, system) ──
        if func_name in self._IGNORE_FUNCS:
            self._visit_calls_only(node)
            return

        # ── Unknown function — collect positional string args as func-arg context ──
        if func_name and func_name not in TRANSLATION_FUNCTIONS:
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    self.func_arg_strings.add((getattr(arg, 'lineno', node.lineno), arg.value))

        self.generic_visit(node)

    def _collect_ui_strings(self, node, fallback_line: int):
        """Extract string values from an AST node in a UI context."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.ui_context_strings.add((getattr(node, 'lineno', fallback_line), node.value))
        elif isinstance(node, ast.JoinedStr):
            # Extract static fragments from f-strings in UI context
            for val in node.values:
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    raw = val.value
                    # Also extract visible text from HTML fragments
                    visible = re.sub(r'<[^>]+>', ' ', raw).strip()
                    visible = re.sub(r'\s+', ' ', visible).strip()
                    if raw.strip():
                        self.ui_context_strings.add((getattr(node, 'lineno', fallback_line), raw.strip()))
                    if visible and visible != raw.strip():
                        self.ui_context_strings.add((getattr(node, 'lineno', fallback_line), visible))
            self._extract_dynamic_prefix(node)
        elif isinstance(node, ast.Call):
            # Nested call like QLabel(t(...)) — process the call
            self.visit_Call(node)

    def _visit_calls_only(self, node):
        """Walk child nodes looking ONLY for translation and UI function calls.
        Does NOT process other calls — prevents false collection of strings
        inside nested non-UI calls like .get(), .format(), etc."""
        _PROPAGATE = TRANSLATION_FUNCTIONS | self._UI_FUNCS
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and child is not node:
                func_name = ""
                if isinstance(child.func, ast.Name):
                    func_name = child.func.id
                elif isinstance(child.func, ast.Attribute):
                    func_name = child.func.attr
                if func_name in _PROPAGATE:
                    self.visit_Call(child)

    def _extract_dynamic_prefix(self, fstring_node: ast.JoinedStr):
        parts = []
        for val in fstring_node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                parts.append(val.value)
            else:
                break
        prefix = "".join(parts)
        if prefix:
            self.dynamic_key_prefixes.add(prefix)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            val = node.value
            self.hardcoded_strings.add((node.lineno, val))
            if self._KEY_PATTERN.match(val):
                self.used_translation_keys.add(val)
        self.generic_visit(node)

    def visit_JoinedStr(self, node):
        for val in node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                self.hardcoded_strings.add((node.lineno, val.value))
        self.generic_visit(node)


# ==========================================
# 🧠 ANALIZZATORE PRINCIPALE
# ==========================================
class UniversalQualityAnalyzer:
    def __init__(self, report_path: Optional[Path] = None):
        self.flat_locales: Dict[str, Dict[str, str]] = {}   # lang → {flat_key: value}
        self.locale_source_files: List[Path] = []            # for duplicate scanning
        self.report_path = report_path
        # COLLECT-THEN-FAIL: checks never abort the run; blocking findings
        # land here, EVERY check runs, the report is always generated, and
        # only at the very end does the run exit non-zero with the full
        # list. (The old per-check asserts meant one parity error hid all
        # later findings and skipped the report exactly when needed most.)
        self.failures: List[str] = []
        self.results = {
            'hardcoded': [], 'json_duplicates': [], 'mixed_langs': [],
            'missing_keys': [], 'empty_values': [], 'mismatched_vars': [],
            'orphan_keys': set(), 'unresolved_code_keys': [],
        }
        self.all_known_keys: Set[str] = set()
        self.all_used_code_keys: Set[str] = set()
        self.all_t_call_keys: Set[str] = set()
        self.all_dynamic_prefixes: Set[str] = set()
        self.detected_format: str = ""

    # ── Loading ──────────────────────────────────────────────────────────────

    def run_all_tests(self):
        print(L("start"))
        print("=" * 80)

        self._auto_load()
        if not self.flat_locales:
            print(L("no_locales"))
            return

        langs = ", ".join(sorted(self.flat_locales.keys()))
        print(L("fmt_detected", fmt=self.detected_format))
        print(L("langs_found", langs=langs))
        print(L("total_keys", n=len(self.all_known_keys)))

        self.test_python_code()
        self.test_missing_keys_global()
        self.test_unresolved_code_keys()
        self.test_empty_values_and_placeholders()
        self.test_mixed_languages()
        self.test_orphan_keys()
        self.test_json_real_duplicates()

        self.generate_report()

        # Collect-then-fail epilogue: the report above ALWAYS exists;
        # blocking findings only decide the exit code, at the very end.
        if self.failures:
            print("\n" + "=" * 80)
            print(L("blocking", n=len(self.failures)))
            for m in self.failures:
                print(f"   - {m}")
            raise SystemExit(1)
        print("\n" + L("all_pass"))

    def _auto_load(self):
        """Auto-discover and load i18n data from any supported format."""
        per_lang_dirs, single_files = _discover_locale_sources(PROJECT_ROOT)

        # Priority: per-lang directory files first
        if per_lang_dirs:
            for d in per_lang_dirs:
                self._load_per_lang_dir(d)
            if self.flat_locales:
                self.detected_format = L("fmt_a", path=per_lang_dirs[0].relative_to(PROJECT_ROOT))
                return

        # Then single multilang files
        for fpath in single_files:
            data = _load_data_file(fpath)
            if not data:
                continue
            fmt = _detect_format(data)
            if fmt == 'per_lang_keys':
                self._load_format_b(data, fpath)
                if self.flat_locales:
                    self.detected_format = L("fmt_b", path=fpath.relative_to(PROJECT_ROOT))
                    return
            elif fmt == 'inline':
                self._load_format_c(data, fpath)
                if self.flat_locales:
                    self.detected_format = L("fmt_c", path=fpath.relative_to(PROJECT_ROOT))
                    return

    def _load_per_lang_dir(self, directory: Path):
        """Format A: one file per language (en.json, it.json, etc.)"""
        for fpath in sorted(directory.iterdir()):
            if not fpath.is_file() or fpath.suffix.lower() not in _DATA_EXTENSIONS:
                continue
            lang_code = fpath.stem.lower()
            # Accept 2-3 letter codes, or codes with region (en-US → en)
            base = lang_code.replace('-', '_').split('_')[0]
            if base not in _ISO_CODES and lang_code not in _ISO_CODES:
                continue
            data = _load_data_file(fpath)
            if not data or not isinstance(data, dict):
                continue
            flat = self._flatten_dict(data)
            self.flat_locales[lang_code] = flat
            self.all_known_keys.update(flat.keys())
            self.locale_source_files.append(fpath)

    def _load_format_b(self, data: dict, fpath: Path):
        """Format B: single file {"en":{…}, "it":{…}}"""
        self.locale_source_files.append(fpath)
        for lang_code, lang_data in data.items():
            if not isinstance(lang_data, dict):
                continue
            lc = lang_code.lower()
            flat = self._flatten_dict(lang_data)
            self.flat_locales[lc] = flat
            self.all_known_keys.update(flat.keys())

    def _load_format_c(self, data: dict, fpath: Path):
        """Format C: {"greeting":{"en":"Hello","it":"Ciao"}, "farewell":{"en":"Bye","it":"Ciao"}}"""
        self.locale_source_files.append(fpath)
        # Collect all languages first
        langs: Set[str] = set()
        for val in data.values():
            if isinstance(val, dict):
                langs.update(k.lower() for k in val.keys() if k.lower() in _ISO_CODES)

        # Build flat dicts per language
        for lang in langs:
            flat: Dict[str, str] = {}
            self._extract_inline_recursive(data, lang, "", flat)
            if flat:
                self.flat_locales[lang] = flat
                self.all_known_keys.update(flat.keys())

    def _extract_inline_recursive(self, data: dict, lang: str, prefix: str, out: Dict[str, str]):
        """Recursively extract translations for a given language from inline format."""
        for key, val in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict):
                # If this dict has language keys → it's a translation node
                if any(k.lower() in _ISO_CODES for k in val.keys()):
                    translation = val.get(lang) or val.get(lang.upper()) or val.get(lang.split('-')[0])
                    if translation is not None and not isinstance(translation, dict):
                        out[full_key] = str(translation)
                else:
                    # Nested namespace, recurse
                    self._extract_inline_recursive(val, lang, full_key, out)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _flatten_dict(d: dict, parent_key: str = '') -> Dict[str, str]:
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(UniversalQualityAnalyzer._flatten_dict(v, new_key).items())
            else:
                items.append((new_key, str(v)))
        return dict(items)

    @staticmethod
    def _extract_placeholders(text: str) -> Set[str]:
        braces = set(re.findall(r'\{([^{}]+)\}', str(text)))
        percents = set(re.findall(r'(%[sdif])', str(text)))
        return braces | percents

    # ALL-CAPS tokens that are technical arguments, never UI headings
    # (Pillow modes, unicode normalization forms, formats, HTTP verbs).
    _CAPS_TECH_TOKENS = {
        'RGB', 'RGBA', 'PNG', 'JPEG', 'JPG', 'GIF', 'BMP', 'ICO', 'WEBP',
        'AVIF', 'NFC', 'NFD', 'NFKC', 'NFKD', 'UTF', 'ASCII', 'GET', 'POST',
        'PUT', 'HEAD', 'DELETE', 'PATCH', 'HTTP', 'HTTPS', 'GZIP', 'ZIP',
        'EXE', 'DLL', 'GUID', 'UUID', 'JSON', 'YAML', 'XML', 'HTML', 'CSS',
        'POSIX', 'API', 'URL', 'URI', 'SQL', 'CSV', 'PDF', 'MZ', 'CRLF',
    }

    @classmethod
    def _is_func_arg_label(cls, text: str) -> bool:
        """Medium filter for strings passed as positional args to unknown functions.
        Catches ALL-CAPS section headings / labels that are almost always UI text.
        Very conservative — only flags strings that are unmistakably UI labels."""
        text = text.strip()
        if not text or len(text) < 3 or len(text) > 35:
            return False
        # ALL-CAPS letters+spaces: "APPEARANCE", "BACKUP POLICY", "GAMES"
        # These are section headers / card labels — never code constants (those use UPPER_SNAKE_CASE)
        if re.match(r'^[A-Z][A-Z ]+$', text) and '_' not in text:
            words = text.split()
            # Single ALL-CAPS words: technical tokens (RGB, PNG, NFC…) are
            # far more common than one-word headings — require length ≥6
            # and absence from the known technical-token set.
            if len(words) == 1:
                return len(text) >= 6 and text not in cls._CAPS_TECH_TOKENS
            return all(w not in cls._CAPS_TECH_TOKENS for w in words)
        return False

    @staticmethod
    def _is_ui_context_string(text: str) -> bool:
        """Light filter for strings found as direct arguments to UI widget functions.
        These are very likely user-facing, so we only filter out clearly technical content."""
        text = text.strip()
        if not text:
            return False
        # Skip if already wrapped in a t() call (the collector should handle this, but double-check)
        if text.startswith(('t(', 'i18n.')):
            return False
        # Skip CSS / stylesheet content
        css = ['px;','em;','font-weight','color:','border:','padding:','background',
               'font-size','border-radius','rgba(','margin','QWidget','QLabel',
               'QPushButton','QFrame','QGroupBox','subcontrol-','qlineargradient']
        if any(m in text for m in css):
            return False
        # Skip rich-text/CSS FRAGMENTS from f-string interpolation sites:
        # "</b> —", ";'>", ":</b>", "☁  <b>" — punctuation and markup with
        # no real word. Require at least one alphabetic run of ≥2 letters
        # once tags are stripped.
        no_tags = re.sub(r'<[^>]+>', ' ', text)
        if not re.search(r'[A-Za-zÀ-ÿ]{2,}', no_tags):
            return False
        # Inline-style fragments: a ';' plus a quote/bracket tail and no
        # spaced words is a stylesheet shard, not UI text.
        if ';' in text and not re.search(r'[A-Za-zÀ-ÿ]{2,}\s+[A-Za-zÀ-ÿ]{2,}', no_tags):
            return False
        # Skip pure HTML tags without visible text
        stripped = re.sub(r'<[^>]+>', '', text).strip()
        if not stripped:
            return False
        # Skip identifiers / code patterns
        if re.match(r'^[a-z_][a-z_0-9]*$', text):  # snake_case identifier
            return False
        if re.match(r'^[A-Z][a-z]+[A-Z]', text):  # camelCase
            return False
        # Skip file paths
        if re.search(r'[/\\]\w+[/\\]', text) or re.search(r'^[a-zA-Z]:[/\\]', text):
            return False
        # Skip format patterns
        if '%(asctime)' in text or re.match(r'^%[a-zA-Z]', text):
            return False
        # Skip pure emoji / icon characters (single symbols used as button icons)
        stripped_text = re.sub(r'[\s\u2000-\u206F\u2190-\u27FF\U0001F000-\U0001FFFF\u2600-\u26FF\u2700-\u27BF]+', '', text)
        if len(stripped_text) <= 1:
            return False
        # Skip pure punctuation / separators / HTML fragments
        if re.match(r'^[\s:;,.\-—–•+×✕✓⟳…|/\\<>]+$', text):
            return False
        # Skip HTML tag fragments (e.g. "</b> —", "<br>", "<span>")
        if re.match(r'^(</?[a-z]+[^>]*>[\s\-—]*)+$', text, re.IGNORECASE):
            return False
        # Skip very short label-like strings (1-3 chars + colon, e.g. "ID:", "N:")
        if re.match(r'^[A-Z]{1,4}:$', text):
            return False
        # Skip unit suffixes (e.g. " MB", " sec", " hours", " min")
        if re.match(r'^\s*\w{1,5}$', text) and text.strip().lower() in {
                'mb', 'gb', 'kb', 'b', 'sec', 'min', 'hours', 'ms', 'px', 'em', '%'}:
            return False
        # Accept everything else — it's in a UI context
        return True

    @staticmethod
    def _is_ui_string(text: str) -> bool:
        """Return True if text looks like user-facing UI content that should be translated."""
        text = text.strip()
        if len(text) < 4 or " " not in text:
            return False

        # URLs, imports, raw paths
        if text.startswith(('http', '/', '\\', '#', '.', 'SELECT ', 'INSERT ', 'from ', 'import ')):
            return False
        # File extensions
        if re.search(r'\.\w{1,4}$', text) and any(text.endswith(e) for e in
                ('.json','.zip','.txt','.log','.exe','.dll','.png','.jpg',
                 '.ini','.css','.py','.pyc','.sav','.dat','.bin','.tmp',
                 '.plist','.desktop','.yaml','.yml','.xml','.html','.po','.pot')):
            return False
        # CSS / Qt stylesheets
        css = ['px;','em;','font-weight','color:','line-height','margin-','border:',
               'padding:','background-','font-size','border-radius','rgba(','QWidget',
               'QLabel','QPushButton','QFrame','QGroupBox','subcontrol-']
        if any(m in text for m in css):
            return False
        # Datetime format
        if re.search(r'%[YyBbHMSdmf]', text) and any(c in text for c in ':/-'):
            return False
        # Logging format
        if '%(asctime)' in text or '%(name)' in text or '%(levelname)' in text:
            return False
        # Type annotations (string form): Optional[X] | tuple[Y, bool] …
        if re.match(r'^[A-Za-z_]+\s*\|\s*[A-Za-z_]+$', text):
            return False
        if ('[' in text and ']' in text
                and re.match(r'^[A-Za-z_0-9\[\]\|, \.]+$', text)):
            return False
        # Search-engine operators and quoted query fragments
        if 'site:' in text or text.startswith('"') or text.startswith("'"):
            return False
        # HTTP header values / client hints
        if ';v=' in text or re.match(r'^[a-z]+(?:, [a-z]+)+$', text):
            return False
        # Technical enumerations: ≥2 commas not followed by a space
        # (API field lists like "id,title,alttitle{...}")
        if len(re.findall(r',(?!\s)', text)) >= 2:
            return False
        # Path fragments (":/Program Files")
        if text.startswith(':/'):
            return False
        # Product/launcher names: every word TitleCase or ALL-CAPS, ≤3 words
        words_ = text.split()
        if (1 <= len(words_) <= 3 and len(text) < 25
                and all(re.match(r'^[A-Z][a-z]+$', w) or w.isupper()
                        for w in words_)):
            return False
        # Env-var paths
        if re.search(r'\{[A-Z_]+\}/', text):
            return False
        # Drive letters
        if re.search(r'^[a-zA-Z]:[/\\]', text):
            return False
        # Path-like (≥2 slashes, not URL)
        if text.count('/') >= 2 and not text.startswith('http'):
            return False
        # API/query fragments
        for p in ("and trashed=false","in parents","mimeType=","application/vnd.",
                  "Content-Range","Content-Length","Bearer ","Authorization"):
            if p in text:
                return False
        # File filters
        if re.search(r'\*\.\w+', text):
            return False
        # Identifiers
        if text.isupper() or re.match(r'^[a-z_A-Z0-9]+$', text):
            return False
        # Technical markers
        if text.startswith((' — ',' - ',' > ','HKEY_','Software\\')) or text.endswith((':','-','=','>')):
            return False
        # Low alpha ratio
        if sum(c.isalpha() for c in text) < len(text) * 0.3:
            return False
        # OS folder names
        if text.strip().lower() in {'application support','saved games','program files',
                'program files (x86)','my games','my documents','app data','local low'}:
            return False
        # Font names (Capitalized 1-3 words, short)
        if re.match(r'^[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}$', text) and len(text) < 25:
            return False
        # Lowercase short phrases (enum values, internal labels)
        if re.match(r'^[a-z]+(?: [a-z]+){0,2}$', text) and len(text) < 25:
            return False
        # Keyboard key names
        if text.strip().lower() in {'page up','page down','num lock','scroll lock',
                'caps lock','print screen','pause break'}:
            return False
        # Short query fragments with quotes
        if "'" in text and len(text) < 15:
            return False
        # Parenthetical fragments or containing parentheses (likely internal labels)
        if text.endswith('(') or text.startswith('('):
            return False
        if re.match(r'^[\w\s]+\([^)]+\)$', text) and len(text) < 30:
            return False
        # Percentage expressions (e.g. "100% accurate" — typically internal/debug)
        if re.search(r'\d+%', text) and len(text) < 25:
            return False
        return True

    # ── Tests ────────────────────────────────────────────────────────────────

    def test_python_code(self):
        print("\n" + L("an_python"))
        n_py = n_other = 0
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in PYTHON_EXCLUDES and not d.startswith('.')]
            for fname in files:
                ext = Path(fname).suffix.lower()
                fpath = Path(root) / fname
                if ext in _REGEX_CODE_EXTENSIONS:
                    # Non-Python source: regex key extraction only —
                    # minified bundles are skipped (regex soup, no keys
                    # a human wrote).
                    if '.min.' in fname.lower():
                        continue
                    try:
                        _src = fpath.read_text(encoding='utf-8', errors='replace')
                        _keys, _prefixes = _extract_keys_regex(_src)
                        self.all_used_code_keys.update(_keys)
                        self.all_t_call_keys.update(_keys)
                        self.all_dynamic_prefixes.update(_prefixes)
                        _rel = str(fpath.relative_to(PROJECT_ROOT))
                        for _lineno, _text in _extract_hardcoded_regex(_src, ext):
                            self.results['hardcoded'].append({
                                'file': _rel, 'line': _lineno, 'text': _text,
                                'context': 'regex_ui'})
                        n_other += 1
                    except Exception:
                        pass
                    continue
                if ext != '.py':
                    continue
                n_py += 1
                rel = fpath.relative_to(PROJECT_ROOT)
                try:
                    src = fpath.read_text(encoding='utf-8')
                    src_lines = src.splitlines()

                    def _suppressed(lineno: int) -> bool:
                        # Inline opt-out: a trailing `# i18n-ignore` comment
                        # on the offending line silences hardcoded-string
                        # findings for that line — declared exceptions
                        # instead of permanently tolerated noise.
                        return (0 < lineno <= len(src_lines)
                                and 'i18n-ignore' in src_lines[lineno - 1])

                    tree = ast.parse(src)
                    ana = PythonCodeAnalyzer()
                    ana.visit(tree)
                    self.all_used_code_keys.update(ana.used_translation_keys)
                    self.all_t_call_keys.update(ana.t_call_keys)
                    self.all_dynamic_prefixes.update(ana.dynamic_key_prefixes)

                    # Tier 1: UI-context strings — args to known UI widget functions
                    seen = set()
                    for lineno, text in ana.ui_context_strings:
                        if _suppressed(lineno):
                            continue
                        if self._is_ui_context_string(text):
                            key = (str(rel), lineno, text)
                            if key not in seen:
                                seen.add(key)
                                self.results['hardcoded'].append({
                                    'file': str(rel), 'line': lineno, 'text': text, 'context': 'ui'})

                    # Tier 2: Function-arg strings — ALL-CAPS labels passed to unknown functions
                    for lineno, text in ana.func_arg_strings:
                        if _suppressed(lineno):
                            continue
                        key = (str(rel), lineno, text)
                        if key not in seen and self._is_func_arg_label(text):
                            seen.add(key)
                            self.results['hardcoded'].append({
                                'file': str(rel), 'line': lineno, 'text': text, 'context': 'func_arg'})

                    # Tier 3: General strings (strict filter)
                    for lineno, text in ana.hardcoded_strings:
                        if _suppressed(lineno):
                            continue
                        key = (str(rel), lineno, text)
                        if key not in seen and self._is_ui_string(text):
                            seen.add(key)
                            self.results['hardcoded'].append({
                                'file': str(rel), 'line': lineno, 'text': text, 'context': 'general'})
                except Exception:
                    pass
        print(L("scan_summary", py=n_py, other=n_other))

    def test_missing_keys_global(self):
        print("\n" + L("an_missing"))
        for lang, flat in self.flat_locales.items():
            for key in self.all_known_keys - set(flat.keys()):
                self.results['missing_keys'].append({'target_lang': lang, 'missing_key': key})
        if self.results['missing_keys']:
            self.failures.append(L(
                "fail_missing", n=len(self.results['missing_keys']),
                items=", ".join(f"{r['target_lang']}:{r['missing_key']}"
                                for r in self.results['missing_keys'][:10])))

    def test_unresolved_code_keys(self):
        """REVERSE direction of test_missing_keys_global: every key passed
        LITERALLY to a t()-family call must exist in the locales.

        This was the tool's structural blind spot: all_known_keys is built
        from the locale FILES, so a key missing from EVERY locale never
        enters it — the parity check can't see it and the orphan analysis
        (which iterates all_known_keys too) can't either. Such a key
        renders as its own raw name in the UI ("restore.files_failed").
        Only t_call_keys is used here — never used_translation_keys, which
        also collects dotted literals from data structures (module paths
        like 'core.library') and would drown this check in false alarms."""
        print("\n" + L("an_unresolved"))
        unresolved = sorted(
            k for k in self.all_t_call_keys
            if PythonCodeAnalyzer._KEY_PATTERN.match(k)
            and k not in self.all_known_keys
        )
        self.results['unresolved_code_keys'] = unresolved
        if unresolved:
            print(L("unresolved_bad", n=len(unresolved)))
            for k in unresolved:
                print(f"      - {k}")
            self.failures.append(L("fail_unresolved", n=len(unresolved),
                                   items=", ".join(unresolved[:10])))
        else:
            print(L("unresolved_ok"))

    def test_empty_values_and_placeholders(self):
        print("\n" + L("an_empty"))
        if not self.flat_locales:
            return
        master_lang = max(self.flat_locales, key=lambda k: len(self.flat_locales[k]))
        master = self.flat_locales[master_lang]
        for lang, flat in self.flat_locales.items():
            for key, text in flat.items():
                if not text.strip():
                    self.results['empty_values'].append({'lang': lang, 'key': key})
                    continue
                if key in master:
                    mv = self._extract_placeholders(master[key])
                    lv = self._extract_placeholders(text)
                    if mv != lv:
                        self.results['mismatched_vars'].append({
                            'key': key, 'lang': lang, 'master_lang': master_lang,
                            'master_vars': sorted(mv), 'lang_vars': sorted(lv)})
        if self.results['empty_values']:
            self.failures.append(L(
                "fail_empty", n=len(self.results['empty_values']),
                items=", ".join(f"{r['lang']}:{r['key']}" for r in self.results['empty_values'][:10])))

    def test_orphan_keys(self):
        """Orphan detection, v2 — extraction now also follows f-strings
        assigned to variables, string concatenation and conditional
        expressions inside t() calls, so a surviving orphan is a key with
        genuinely NO static reference anywhere.

        Classification instead of a blunt list:
        - "famiglia dinamica viva": a SIBLING key of the same parent IS
          used via a dynamic prefix — flagged low-confidence, because the
          same construction site may reach this key with other values.
        - "nessun riferimento": no reference of any kind — high confidence.

        Deliberately NON-fatal (matching the long-standing project stance:
        keys are never auto-stripped; the report is the deliverable)."""
        print("\n" + L("an_orphans"))
        if not self.all_used_code_keys and not self.all_dynamic_prefixes:
            return
        high, low = set(), set()
        for key in self.all_known_keys:
            if key in self.all_used_code_keys:
                continue
            if any(key.startswith(p) for p in self.all_dynamic_prefixes):
                continue
            parent = key.rsplit('.', 1)[0] + '.'
            sibling_dynamic = any(p.startswith(parent) or parent.startswith(p)
                                  for p in self.all_dynamic_prefixes)
            (low if sibling_dynamic else high).add(key)
        self.results['orphan_keys'] = high | low
        self.results['orphan_high'] = high
        self.results['orphan_low'] = low
        if high:
            by_section = defaultdict(list)
            for k in sorted(high):
                by_section[k.split('.', 1)[0]].append(k)
            print(L("orphan_high", n=len(high)))
            for sec, keys in sorted(by_section.items()):
                print(f"      [{sec}] {', '.join(keys)}")
        if low:
            print(L("orphan_low", n=len(low)))
        if not high and not low:
            print(L("orphan_none"))

    def test_json_real_duplicates(self):
        """Find true duplicate keys at the same JSON object level."""
        for fpath in self.locale_source_files:
            if fpath.suffix.lower() != '.json':
                continue
            lang = fpath.stem.lower()
            try:
                raw = fpath.read_text(encoding='utf-8')
                dups: List[Tuple[str, int]] = []
                def _hook(pairs):
                    seen = {}
                    for k, v in pairs:
                        seen[k] = seen.get(k, 0) + 1
                    for k, c in seen.items():
                        if c > 1:
                            dups.append((k, c))
                    return dict(pairs)
                json.loads(raw, object_pairs_hook=_hook)
                for path, count in dups:
                    self.results['json_duplicates'].append({'lang': lang, 'key': path, 'count': count})
            except Exception:
                pass
        if self.results['json_duplicates']:
            self.failures.append(L(
                "fail_dups", n=len(self.results['json_duplicates']),
                items=", ".join(f"{r['lang']}:{r['key']}(x{r['count']})"
                                for r in self.results['json_duplicates'][:10])))

    @staticmethod
    def _informative_words(text: str) -> List[str]:
        """Reduce a UI string to the lowercase words that actually carry
        language signal: strips URLs/placeholders/paths, parenthesized
        brand lists, tech vocabulary, numbers, ALL-CAPS tokens, and
        mid-sentence TitleCase tokens (proper nouns)."""
        clean = re.sub(r'https?://\S+', ' ', text)
        clean = re.sub(r'\{[^\}]+\}|%[a-zA-Z]', ' ', clean)
        clean = re.sub(r'[A-Z]:\\[^\s]+', ' ', clean)
        clean = re.sub(r'/[^\s]+/[^\s]+', ' ', clean)
        # Bare domains with optional path (developer.microsoft.com/graph/…):
        # shredding them into words feeds langdetect pure noise.
        clean = re.sub(r'\b[\w-]+(?:\.[\w-]+)+(?:/\S*)?', ' ', clean)

        def _paren(m):
            toks = re.findall(r'[\w.]+', m.group(1))
            neutral = all(
                t0[:1].isupper() or any(c.isdigit() for c in t0)
                or '.' in t0 or t0.lower() in _TECH_WORDS
                for t0 in toks) if toks else True
            return ' ' if neutral else ' ' + m.group(1) + ' '

        clean = re.sub(r'\(([^)]*)\)', _paren, clean)
        clean = re.sub(r'[^\w\s]', ' ', clean)
        out: List[str] = []
        for i, w in enumerate(clean.split()):
            if any(c.isdigit() for c in w):
                continue
            if w.isupper() and len(w) > 1:
                continue
            if i > 0 and w[:1].isupper():
                continue                    # mid-sentence TitleCase = proper noun
            lw = w.lower()
            if lw in _TECH_WORDS or len(lw) == 1:
                continue
            out.append(lw)
        return out

    def test_mixed_languages(self):
        """Wrong-language detector, v2.

        Primary signal: STOPWORD EVIDENCE — deterministic function-word
        counts per language. A string with ≥2 expected-language function
        words can't be "in the wrong language"; one with ZERO expected
        function words and ≥2 of another language's is flagged even when
        langdetect is unsure (higher sensitivity than v1). langdetect is
        only a secondary confirmation, with its known noise languages held
        to a much higher bar — this removes the short-string
        misclassifications (cy/fr on plain English) that were v1's false
        positives."""
        print("\n" + L("an_mixed"))
        for lang, flat in self.flat_locales.items():
            expected = LANGUAGE_MAP.get(lang)
            if not expected:
                continue
            sw_exp = _STOPWORDS.get(expected, set())
            for key, text in flat.items():
                words = self._informative_words(text)
                if len(words) < 4:
                    continue                 # too short to judge reliably
                hits_exp = sum(1 for w in words if w in sw_exp)
                if hits_exp >= 2:
                    continue
                if hits_exp == 1 and len(words) <= 8:
                    continue
                other_lang, other_hits = "", 0
                for lg, sw in _STOPWORDS.items():
                    if lg == expected:
                        continue
                    h = sum(1 for w in words if w in sw)
                    if h > other_hits:
                        other_lang, other_hits = lg, h
                strong_cross = other_hits >= 2 and hits_exp == 0
                try:
                    probs = detect_langs(" ".join(words))
                except LangDetectException:
                    probs = []
                if any(p.lang == expected and p.prob >= 0.05 for p in probs[:3]):
                    if not strong_cross:
                        continue
                top = probs[0] if probs else None
                strong_detect = False
                if top is not None and top.lang != expected:
                    if top.lang in _LANGDETECT_NOISE:
                        strong_detect = top.prob >= 0.99 and len(words) >= 8
                    else:
                        strong_detect = top.prob >= 0.97
                if not (strong_cross or (strong_detect and hits_exp == 0)):
                    continue
                detected = (other_lang if strong_cross and other_lang
                            else (top.lang if top else "?"))
                prob = top.prob if top else 0.0
                self.results['mixed_langs'].append({
                    'lang': lang, 'key': key, 'text': text,
                    'detected': detected, 'prob': prob,
                    'evidence': (f"stopwords {other_lang}×{other_hits}"
                                 if strong_cross else f"langdetect {prob:.2f}")})
        if self.results['mixed_langs']:
            self.failures.append(L(
                "fail_mixed", n=len(self.results['mixed_langs']),
                items=", ".join(f"{r['lang']}:{r['key']}(detected {r['detected']}, {r['evidence']})"
                                for r in self.results['mixed_langs'][:10])))

    # ── Report ───────────────────────────────────────────────────────────────

    def generate_report(self):
        print("\n" + L("report_gen"))
        rpath = self.report_path or (Path(__file__).parent / "UNIVERSAL_QUALITY_REPORT.md")

        with open(rpath, 'w', encoding='utf-8') as f:
            f.write(L("r_title"))
            f.write(L("r_format", fmt=self.detected_format))

            f.write(L("r_summary"))
            f.write(L("r_table"))
            rows = [
                (L("cat_dups"), self.results['json_duplicates'], L("sev_crit")),
                (L("cat_vars"), self.results['mismatched_vars'], L("sev_crit")),
                (L("cat_unresolved"), self.results['unresolved_code_keys'], L("sev_crit")),
                (L("cat_empty"), self.results['empty_values'], L("sev_high")),
                (L("cat_missing"), self.results['missing_keys'], L("sev_high")),
                (L("cat_hardcoded"), self.results['hardcoded'], L("sev_med")),
                (L("cat_orphans"), self.results['orphan_keys'], L("sev_med")),
                (L("cat_mixed"), self.results['mixed_langs'], L("sev_low")),
            ]
            for name, items, sev in rows:
                n = len(items)
                st = (L("st_ok") if n == 0 else
                      (L("st_err") if '🔥' in sev else
                       (L("st_warn") if '⚠' in sev else L("st_info"))))
                f.write(f"| {name} | {n} | {st} | {sev} |\n")
            f.write("\n")

            if self.results['unresolved_code_keys']:
                f.write(L("r_unresolved_h"))
                for k in self.results['unresolved_code_keys']:
                    f.write(f"- [ ] `{k}`\n")
                f.write("\n")

            if self.results['hardcoded']:
                tiers = [
                    ('ui', L("tier_ui_t"), L("tier_ui_d")),
                    ('func_arg', L("tier_func_t"), L("tier_func_d")),
                    ('general', L("tier_gen_t"), L("tier_gen_d")),
                    ('regex_ui', L("tier_rx_t"), L("tier_rx_d")),
                ]
                for ctx, title, desc in tiers:
                    items = [it for it in self.results['hardcoded'] if it.get('context') == ctx]
                    if not items:
                        continue
                    f.write(f"## {title}\n> {desc}\n\n")
                    g = defaultdict(list)
                    for it in items:
                        g[it['file']].append(it)
                    for fp, fitems in sorted(g.items()):
                        f.write(f"### 📁 `{fp}`\n")
                        rp = f"../{fp.replace(chr(92), '/')}"
                        for it in sorted(fitems, key=lambda x: x['line']):
                            st = str(it['text']).replace('`', "'").replace('\n', '\\n')
                            f.write(L("r_line", line=it['line'], rp=rp, text=st))
                        f.write("\n")

            if self.results['missing_keys']:
                f.write(L("r_missing_h"))
                g = defaultdict(list)
                for it in self.results['missing_keys']:
                    g[it['target_lang']].append(it['missing_key'])
                for lang, keys in sorted(g.items()):
                    f.write(f"### 🌐 `{lang}`\n")
                    for k in sorted(keys):
                        f.write(f"- [ ] `{k}`\n")
                    f.write("\n")

            if self.results['mismatched_vars']:
                f.write(L("r_vars_h"))
                for it in self.results['mismatched_vars']:
                    f.write(L("r_vars_line", key=it['key'], lang=it['lang'],
                              master=it['master_vars'], found=it['lang_vars']))
                f.write("\n")

            if self.results['empty_values']:
                f.write(L("r_empty_h"))
                for it in sorted(self.results['empty_values'], key=lambda x: (x['lang'], x['key'])):
                    f.write(f"- `{it['lang']}` → `{it['key']}`\n")
                f.write("\n")

            if self.results['orphan_keys']:
                f.write(L("r_orphans_h"))
                high = self.results.get('orphan_high', set())
                low = self.results.get('orphan_low', set())
                if high:
                    f.write(L("r_orphan_high"))
                    for k in sorted(high):
                        f.write(f"- [ ] `{k}`\n")
                    f.write("\n")
                if low:
                    f.write(L("r_orphan_low"))
                    for k in sorted(low):
                        f.write(f"- [ ] `{k}`\n")
                    f.write("\n")

            if self.results['mixed_langs']:
                f.write(L("r_mixed_h"))
                for it in self.results['mixed_langs']:
                    st = str(it['text']).replace('`', "'").replace('\n', '\\n')
                    f.write(L("r_mixed_line", lang=it['lang'], key=it['key'],
                              text=st, det=it['detected'], pct=int(it['prob'] * 100)))
                f.write("\n")

            if self.results['json_duplicates']:
                f.write(L("r_dups_h"))
                for it in self.results['json_duplicates']:
                    f.write(f"- `{it['lang']}`: `{it['key']}` x{it['count']}\n")
                f.write("\n")

        print(L("done", path=rpath.absolute()))


if __name__ == '__main__':
    import argparse
    _ap = argparse.ArgumentParser(
        description="Universal i18n quality analysis (multi-format)")
    _ap.add_argument("--root", type=Path, default=None,
                     help="project root to scan (default: this repo's root)")
    _ap.add_argument("--report", type=Path, default=None,
                     help="output path for the Markdown report "
                          "(default: tests/UNIVERSAL_QUALITY_REPORT.md)")
    _ap.add_argument("--lang", choices=TOOL_LANGS, default=None,
                     help="tool output language (default: auto-detected "
                          "from the system locale; extend by dropping a "
                          "qa_lang_<code>.json pack next to this script)")
    _ap.add_argument("--export-lang-template", metavar="CODE", default=None,
                     help="write qa_lang_<CODE>.json with every message in "
                          "English as a translation starting point, then exit")
    _args = _ap.parse_args()
    if _args.export_lang_template:
        _code = _args.export_lang_template.strip().lower()
        _out = Path(__file__).parent / f"qa_lang_{_code}.json"
        _out.write_text(
            json.dumps({k: v["en"] for k, v in sorted(_L10N.items())},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"Template written: {_out} — translate the values, rerun, "
              f"and '{_code}' appears in --lang and in the auto-detection.")
        raise SystemExit(0)
    if _args.root:
        PROJECT_ROOT = _args.root.resolve()
    if _args.lang:
        TOOL_LANG = _args.lang
    UniversalQualityAnalyzer(report_path=_args.report).run_all_tests()
