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
import html
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
    "an_member":      {"en": "🔗 KEYS READ AS OBJECT PROPERTIES (t.key)...",
                       "it": "🔗 ANALISI CHIAVI LETTE COME PROPRIETA' (t.chiave)..."},
    "member_off":     {"en": "   ℹ️ not configured — declare \"member_access_objects\" in .i18n-quality.json to enable",
                       "it": "   ℹ️ non configurato — dichiara \"member_access_objects\" in .i18n-quality.json per attivarlo"},
    "member_bad":     {"en": "   ❌ {n} key(s) read WITHOUT a fallback and absent from every locale (they render as \"undefined\"):",
                       "it": "   ❌ {n} chiave/i lette SENZA fallback e assenti da ogni lingua (a schermo escono come \"undefined\"):"},
    "member_fb":      {"en": "   ⚠️ {n} key(s) absent from every locale but always read with a fallback (the fallback text is hardcoded)",
                       "it": "   ⚠️ {n} chiave/i assenti da ogni lingua ma sempre lette con un fallback (il testo di ripiego e' scritto nel codice)"},
    "member_ok":      {"en": "   🟢 every key read as a property exists in the locales",
                       "it": "   🟢 ogni chiave letta come proprieta' esiste nei locale"},
    "member_seen":    {"en": "   ℹ️ {n} property reads scanned on: {o}",
                       "it": "   ℹ️ {n} letture di proprieta' analizzate su: {o}"},
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
    "fail_member": {"en": "{n} key(s) read as t.key without a fallback and defined in NO locale (they render as \"undefined\"): {items}",
                    "it": "{n} chiave/i lette come t.chiave senza fallback e non definite in NESSUNA lingua (a schermo escono come \"undefined\"): {items}"},
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
    "cat_member": {"en": "Property keys, no fallback, undefined",
                   "it": "Chiavi proprieta' senza fallback, non definite"},
    "cat_member_fb": {"en": "Property keys covered only by a fallback",
                      "it": "Chiavi proprieta' coperte solo dal fallback"},
    "cat_unresolved": {"en": "Keys used but not defined", "it": "Chiavi Usate ma Non Definite"},
    "cat_empty":      {"en": "Empty values", "it": "Valori Vuoti"},
    "cat_missing":    {"en": "Missing keys", "it": "Chiavi Mancanti"},
    "cat_hardcoded":  {"en": "Hardcoded texts", "it": "Testi Hardcoded"},
    "cat_orphans":    {"en": "Orphan keys", "it": "Chiavi Orfane"},
    "cat_mixed":      {"en": "Mixed languages", "it": "Lingue Miste"},
    "an_icu":         {"en": "🔢 ICU plural rules",
                       "it": "🔢 Regole di plurale ICU"},
    "icu_absent":     {"en": "   ℹ️ no ICU messages in this project",
                       "it": "   ℹ️ nessun messaggio ICU in questo progetto"},
    "icu_ok":         {"en": "   ✅ {n} ICU messages, every plural covers its "
                             "language",
                       "it": "   ✅ {n} messaggi ICU, ogni plurale copre la sua "
                             "lingua"},
    "icu_bad":        {"en": "   ⚠️ {n} problems over {scanned} ICU messages "
                             "({high} blocking)",
                       "it": "   ⚠️ {n} problemi su {scanned} messaggi ICU "
                             "({high} bloccanti)"},
    "icu_src_hint":   {"en": "   ℹ️ category sets came from the built-in table; "
                             "install babel for authoritative CLDR rules",
                       "it": "   ℹ️ categorie dalla tabella interna; installa "
                             "babel per le regole CLDR autorevoli"},
    "icu_src_builtin": {"en": "built-in table, not blocking",
                        "it": "tabella interna, non bloccante"},
    "icu_p_malformed": {"en": "malformed ICU message — it will raise at format "
                              "time",
                        "it": "messaggio ICU malformato — solleverà un errore "
                              "in fase di formattazione"},
    "icu_p_no_other": {"en": 'no "other" branch — ICU requires one in every '
                             'language',
                       "it": 'manca il ramo "other" — ICU lo richiede in ogni '
                             'lingua'},
    "icu_p_bad_keyword": {"en": '"{kw}" is not a plural category',
                          "it": '"{kw}" non è una categoria di plurale'},
    "icu_p_duplicate": {"en": 'branch "{kw}" appears more than once',
                        "it": 'il ramo "{kw}" compare più di una volta'},
    "icu_p_missing":  {"en": "missing {cats} — everyday counts in this language "
                             "select it ({src})",
                       "it": "manca {cats} — i conteggi di tutti i giorni in "
                             "questa lingua lo selezionano ({src})"},
    "icu_p_missing_rare": {"en": "missing {cats} — only large numbers, decimals "
                                 "or compact notation reach it",
                           "it": "manca {cats} — lo raggiungono solo numeri "
                                 "grandi, decimali o notazione compatta"},
    "icu_p_dead":     {"en": "{cats} is never selected in this language, so the "
                             "branch is dead; to special-case a number use an "
                             "explicit =N selector instead",
                       "it": "{cats} non viene mai selezionato in questa lingua, "
                             "quindi il ramo è morto; per un numero speciale usa "
                             "un selettore esplicito =N"},
    "icu_p_flattened": {"en": "plural in {master} but a plain string here",
                        "it": "plurale in {master} ma qui è una stringa semplice"},
    "fail_icu":       {"en": "ICU plurals broken: {n} ({items})",
                       "it": "plurali ICU rotti: {n} ({items})"},
    "cat_icu":        {"en": "ICU plural rules", "it": "Regole di plurale ICU"},
    "r_icu_h":        {"en": "\n## 🔢 ICU plural rules\n\n",
                       "it": "\n## 🔢 Regole di plurale ICU\n\n"},
    "r_icu_line":     {"en": "- `{lang}` → `{key}` — {detail}\n",
                       "it": "- `{lang}` → `{key}` — {detail}\n"},
    "scan_backend":   {"en": "   ℹ️  non-Python sources read with {how} ({exts})",
                       "it": "   ℹ️  sorgenti non-Python letti con {how} ({exts})"},
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
    "tier_ast_t":     {"en": "🔤 Hardcoded texts — non-Python sources (parsed)",
                        "it": "🔤 Testi Hardcoded — sorgenti non-Python (analizzati)"},
    "tier_ast_d":     {"en": "Read from the parse tree, not guessed: each of "
                             "these IS a text node, the value of a UI "
                             "attribute, or an argument to a call that shows "
                             "it. Import paths, object keys and code-shaped "
                             "strings are excluded by structure rather than "
                             "by heuristic.",
                        "it": "Letti dall'albero sintattico, non ipotizzati: "
                             "ognuno di questi È un nodo di testo, il valore "
                             "di un attributo UI, o l'argomento di una "
                             "chiamata che lo mostra. Percorsi di import, "
                             "chiavi di oggetti e stringhe di codice sono "
                             "esclusi per struttura, non per euristica."},
    "tier_rx_t":      {"en": "🔤 Hardcoded texts — non-Python sources (LOW RELIABILITY)",
                        "it": "🔤 Testi Hardcoded — sorgenti non-Python (BASSA AFFIDABILITÀ)"},
    "tier_rx_d":      {"en": "⚠️ Heuristic hints WITHOUT syntax context: expect false positives AND missed strings. UI-ish attributes (placeholder/title/label…), dialog-like calls and multi-word template text nodes only. Treat as hints, verify by hand.",
                        "it": "⚠️ Indizi euristici SENZA contesto sintattico: aspettati falsi positivi E stringhe mancate. Solo attributi UI (placeholder/title/label…), chiamate tipo dialog e nodi di testo multi-parola nei template. Trattali come indizi, verifica a mano."},
    "r_line":         {"en": "- [{line}:{col}]({rp}#L{line}): `{text}`\n",
                        "it": "- [{line}:{col}]({rp}#L{line}): `{text}`\n"},
    "r_preview":      {"en": "  ↳ `{preview}`\n",
                        "it": "  ↳ `{preview}`\n"},
    "st_header":      {"en": "🧪 SELF-TEST — the analyzer checked against itself",
                        "it": "🧪 AUTO-TEST — l'analizzatore verificato su se stesso"},
    "st_passed":      {"en": "🟢 Self-test passed ({n} cases).",
                        "it": "🟢 Auto-test superato ({n} casi)."},
    "st_failed":      {"en": "❌ Self-test FAILED — {n} case(s): {ids}",
                        "it": "❌ Auto-test FALLITO — {n} caso/i: {ids}"},
    "cfg_unreadable":  {"en": "   ⚠️ {file} could not be read ({err}) — built-in defaults only",
                        "it": "   ⚠️ {file} non leggibile ({err}) — solo impostazioni predefinite"},
    "cfg_created":    {"en": "   📝 {file} did not exist — wrote a commented "
                             "template. It is optional: an empty one changes "
                             "nothing, and deleting it is fine.",
                        "it": "   📝 {file} non esisteva — scritto un modello "
                             "commentato. È opzionale: vuoto non cambia "
                             "nulla, e cancellarlo va bene."},
    "cfg_uncreatable": {"en": "   ℹ️ {file} is absent and could not be created "
                              "({err}) — built-in defaults only",
                        "it": "   ℹ️ {file} assente e non creabile ({err}) — "
                              "solo impostazioni predefinite"},
    "exempt_note":    {"en": "   🤫 {n} finding(s) held back as known noise: "
                             "{detail}. Turn any of them back on with "
                             "\"exempt\" in {file}.",
                        "it": "   🤫 {n} risultato/i trattenuti come rumore "
                             "noto: {detail}. Riattivali con \"exempt\" in "
                             "{file}."},
    "r_exempt_h":     {"en": "\n## 🤫 Held back as known noise\n\n"
                             "> Not silently: each kind can be turned back on "
                             "with `\"exempt\"` in `{file}`.\n\n",
                        "it": "\n## 🤫 Trattenuti come rumore noto\n\n"
                             "> Non in silenzio: ogni tipo si riattiva con "
                             "`\"exempt\"` in `{file}`.\n\n"},
    "r_exempt_row":   {"en": "- `{kind}` — {n}: {why}\n",
                        "it": "- `{kind}` — {n}: {why}\n"},
    "ex_raise":       {"en": "messages of exceptions the code raises",
                        "it": "messaggi delle eccezioni sollevate dal codice"},
    "ex_regex":       {"en": "regular-expression patterns",
                        "it": "espressioni regolari"},
    "ex_agent":       {"en": "HTTP User-Agent strings",
                        "it": "stringhe User-Agent HTTP"},
    "an_severity":    {"en": "🎚️ FINDINGS BY SEVERITY...",
                        "it": "🎚️ RISULTATI PER GRAVITÀ..."},
    "sev_count":      {"en": "   {level}: {n}",
                        "it": "   {level}: {n}"},
    "sev_no_budget":  {"en": "   ℹ️ informational — declare \"budgets\" in "
                             "{file} to make these blocking",
                        "it": "   ℹ️ informativo — dichiara \"budgets\" in "
                             "{file} per renderli bloccanti"},
    "fail_budget":    {"en": "{level}-severity hardcoded texts: {n} "
                             "(budget {max})",
                        "it": "testi hardcoded di gravità {level}: {n} "
                             "(budget {max})"},
    "r_member_h": {"en": "## 🔗 Keys read as object properties (t.key)\n> Read off the catalogue object instead of passed to t(). Without a fallback a missing key reaches the screen as the string \"undefined\".\n\n",
                   "it": "## 🔗 Chiavi lette come proprieta' dell'oggetto (t.chiave)\n> Lette dall'oggetto catalogo invece che passate a t(). Senza fallback una chiave mancante arriva a schermo come la stringa \"undefined\".\n\n"},
    "r_member_bad": {"en": "### ❌ Missing, no fallback — they render as \"undefined\"\n",
                     "it": "### ❌ Mancanti, senza fallback — escono come \"undefined\"\n"},
    "r_member_fb": {"en": "### ⚠️ Missing, but always read with a fallback\n> Harmless on screen; the fallback text lives in the code and is usually untranslated.\n",
                    "it": "### ⚠️ Mancanti, ma sempre lette con un fallback\n> Innocue a schermo; il testo di ripiego sta nel codice ed e' di solito non tradotto.\n"},
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


def L(msg_id: str, /, **kw) -> str:
    """Look up a tool message and format it.

    The id is POSITIONAL-ONLY on purpose: it used to be a normal parameter
    named ``key``, so any message with a ``{key}`` placeholder — the
    mixed-language report line among them — collided with it and raised
    "got multiple values for argument 'key'". That crashed report generation
    on exactly the runs that had something to report.
    """
    msg = _L10N[msg_id]
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
# Directories no project wants scanned: caches, virtualenvs, build output,
# and the test tree. Anything BEYOND this is a statement about one
# particular repository — a folder of dev-only scripts, a vendored copy, an
# archive of old code — and belongs in that repository's own
# PROJECT_VOCAB_FILE under "exclude_dirs", not in here. This tool stays
# universal; the file next to the project says what the project is.
PYTHON_EXCLUDES_BUILTIN = {"__pycache__", ".git", ".venv", "venv",
                           "node_modules", "build", "dist", "tests",
                           "egg-info"}

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

TRANSLATION_FUNCTIONS = {'tr', '_', 'translate', 'get_text', 't', 'i18n',
                         'ngettext', 'gettext',
                         # gettext's disambiguating and domain-qualified
                         # forms, and Qt's own. See _KEY_ARG_POSITIONS: what
                         # these carry in slot 0 is a CONTEXT or a DOMAIN,
                         # and reading it as the key files a string nobody
                         # ever translates into the used-keys set — which
                         # then masks a real orphan.
                         'pgettext', 'npgettext', 'dgettext', 'dngettext',
                         'dcgettext', 'N_', 'NSLocalizedString'}

#: name -> the positional slots that carry a KEY. Anything absent uses (0,).
#:
#: ngettext takes the singular AND the plural, and both are keys: reading
#: only the first leaves the plural form looking unreferenced. pgettext
#: takes a disambiguating context first, npgettext a context and then both
#: forms, the d* family a domain first, and Qt's qsTranslate a context.
_KEY_ARG_POSITIONS = {
    'ngettext': (0, 1),
    'pgettext': (1,),
    'npgettext': (1, 2),
    'dgettext': (1,),
    'dcgettext': (1,),
    'dngettext': (1, 2),
    'qsTranslate': (1,),
}


def _key_positions(name: str):
    return _KEY_ARG_POSITIONS.get(name, (0,))

# ── Multi-language source scanning ──────────────────────────────────────────
# Python gets the FULL context-aware AST analysis (used keys + hardcoded
# strings). Every other language goes through a regex extractor that
# collects used keys and dynamic prefixes — enough to power the
# unresolved-keys and orphan checks across the whole codebase.
_REGEX_CODE_EXTENSIONS = {
    '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.vue', '.svelte',
    '.php', '.dart', '.kt', '.kts', '.java', '.cs', '.rb', '.go', '.rs',
    '.qml',
    # Added after measuring, not on the strength of a grammar existing:
    # each of these rejects a call written inside a string and inside a
    # comment, which is the thing the regex cannot do. What differs is how
    # much of each ecosystem is key-shaped at all — see the tier table in
    # the README, where the text-based ones say so.
    '.lua', '.swift', '.m', '.mm',
    '.c', '.h', '.cpp', '.cc', '.cxx', '.hpp',
    '.ex', '.exs', '.scala', '.groovy', '.pl', '.pm', '.hx', '.astro',
}

# t('key') / tr("key") / $t('key') / i18n.t('key') / __('key') …
# Longest first: the alternation is ordered, and `t` would otherwise win
# at a position where `translate` was meant. qsTr/qsTranslate/qsTrId are
# Qt's own, and QML has no others — without them a .qml file's keys were
# invisible to both backends at once.
_CODE_CALL_NAMES = ("NSLocalizedString", "qsTranslate", "qsTrId",
                    "ngettext", "translate", "get_text", "gettext",
                    "i18n", "qsTr", "tc", "tr", "N_", "__", "t")
# Objective-C writes @"key" and C/C++ can write L"key" / u8"key": the quote
# is not the first character after the bracket, and requiring it to be lost
# every NSLocalizedString in a .m file at once.
_STR_PREFIX = r"""(?:@|u8|L|u|U)?"""
_RX_CODE_CALL = re.compile(
    r"""(?:\b|\$)(?:""" + "|".join(_CODE_CALL_NAMES) + r""")"""
    r"""\s*\(\s*""" + _STR_PREFIX + r"""(['"])([A-Za-z0-9][A-Za-z0-9_.-]*)\1""")
# Hooks and getters that RETURN the translation function, so the key is
# passed to the call's RESULT and the outer call has no name of its own:
#   const t = useTranslations('nav'); t('home')     ← caught by the name t
#   useTranslations('nav')('home')                  ← caught only here
# next-intl and next-international are the ones in wide use; anything else
# goes in the project file under "extra_translation_calls".
_TS_FACTORY_NAMES = frozenset((
    'useTranslations', 'getTranslations',
    'useScopedI18n', 'getScopedI18n',
    'useI18n', 'getI18n', 'useTranslate',
))
_RX_CODE_FACTORY = re.compile(
    r"""(?:\b|\$)(?:""" + "|".join(sorted(_TS_FACTORY_NAMES)) + r""")"""
    r"""\s*\([^()]*\)\s*\(\s*(['"])([A-Za-z0-9][A-Za-z0-9_.-]*)\1""")
# The names whose key is NOT in the first slot need the leading arguments
# read together, so the right one can be picked afterwards.
_RX_CODE_CALL_MULTI = re.compile(
    r"""(?:\b|\$)(""" + "|".join(sorted(_KEY_ARG_POSITIONS, key=len,
                                         reverse=True)) + r""")"""
    r"""\s*\(\s*""" + _STR_PREFIX + r"""(['"])([^'"]*)\2"""
    r"""(?:\s*,\s*""" + _STR_PREFIX + r"""(['"])([^'"]*)\4)?"""
    r"""(?:\s*,\s*""" + _STR_PREFIX + r"""(['"])([^'"]*)\6)?""")


def _multi_arg_keys(src: str):
    """``[(offset, key)]`` for calls whose key is not the first argument."""
    out = []
    for m in _RX_CODE_CALL_MULTI.finditer(src):
        values = (m.group(3), m.group(5), m.group(7))
        for slot in _key_positions(m.group(1)):
            if slot < len(values) and values[slot]:
                out.append((m.start(), values[slot]))
    return out


# JS template literals: t(`section.${x}`) → dynamic family 'section.'
_RX_CODE_TEMPLATE = re.compile(
    r"""(?:\b|\$)(?:t|tr|tc|translate|i18n)\s*\(\s*`([A-Za-z0-9][A-Za-z0-9_.-]*\.)\$\{""")


# Strip comments BEFORE extraction: a commented-out t('old.key') call
# must not count as usage — a stale key there would raise a FALSE
# blocking "unresolved" finding. Block comments /* … */ and FULL-LINE
# // or # comments only; a mid-line '//' is deliberately left alone,
# stripping it would eat URLs inside string literals ('https://…').
_RX_CODE_COMMENTS = re.compile(r"/\*.*?\*/|^[ \t]*(?://|#).*?$", re.S | re.M)


_PREVIEW_MAX = 120


def _preview(lines: List[str], lineno: int) -> str:
    """The source line a finding sits on, trimmed for the report.

    The matched string alone often says nothing: `` ` should start at byte ` ``
    is unreadable until you can see it is the tail of an exception message.
    Showing the line it came from turns a coordinate into something you can
    judge without opening the file.
    """
    if not (0 < lineno <= len(lines)):
        return ""
    text = lines[lineno - 1].strip()
    if len(text) > _PREVIEW_MAX:
        text = text[:_PREVIEW_MAX - 1].rstrip() + "…"
    return text.replace("`", "'")      # keep the Markdown code span intact


def _blank_comments(src: str) -> str:
    """Replace comments with whitespace of the SAME shape (newlines kept),
    so offsets and line numbers of every later match stay valid."""
    return _RX_CODE_COMMENTS.sub(
        lambda m: re.sub(r'[^\n]', ' ', m.group(0)), src)


_rx_project_cache: Dict[str, object] = {}


def _rx_project_calls():
    """A pattern for the project's own translation names, or None.

    Both shapes at once — called directly and called through a factory —
    because a name declared in the project file could be either and asking
    which would be one more thing to get wrong.
    """
    names = _extra_translation_calls()
    cache_key = "|".join(sorted(names))
    if cache_key not in _rx_project_cache:
        rx = None
        if names:
            alt = "|".join(re.escape(n) for n in sorted(names))
            rx = re.compile(
                r"""(?:\b|\$)(?:""" + alt + r""")"""
                r"""\s*(?:\([^()]*\)\s*)?\(\s*(['"])"""
                r"""([A-Za-z0-9][A-Za-z0-9_.-]*)\1""")
        _rx_project_cache[cache_key] = rx
    return _rx_project_cache[cache_key]


def _extract_keys_regex(src: str) -> Tuple[Set[str], Set[str]]:
    """Best-effort key extraction for non-Python sources."""
    src = _blank_comments(src)
    keys: Set[str] = set()
    prefixes: Set[str] = set()
    for rx in (_RX_CODE_CALL, _RX_CODE_FACTORY, _rx_project_calls()):
        if rx is None:
            continue
        for m in rx.finditer(src):
            val = m.group(2)
            if PythonCodeAnalyzer._KEY_PATTERN.match(val):
                keys.add(val)
    for _off, val in _multi_arg_keys(src):
        if PythonCodeAnalyzer._KEY_PATTERN.match(val):
            keys.add(val)
    for m in _RX_CODE_TEMPLATE.finditer(src):
        prefixes.add(m.group(1))
    return keys, prefixes


# ── Tree-sitter backend for non-Python sources ──────────────────────────────
# Python gets a real AST from the standard library. Everything else got a
# regex, which cannot tell a call from a mention of one: t('x') written inside
# a string literal counts as usage, and a commented-out call only stops
# counting because comments are blanked first — a workaround that has to guess
# which '//' opens a comment and which sits inside a URL.
#
# tree-sitter parses 300+ grammars the same way. It is used here to CORRECT
# the regex rather than to replace it, and that is a deliberate choice made
# after measuring. The measurement has moved since: PHP now parses cleanly,
# and Vue and Svelte do too once their <script> bodies are handed to the
# JavaScript grammar themselves (the SFC grammars keep them as raw text —
# see _sfc_script_blocks). Every extension in _TS_LANG_BY_EXT now rejects a
# call written inside a string or a comment, which is the thing a regex
# cannot do.
#
# The rule stays as it is anyway, because it costs nothing and the failure
# it guards against is the expensive one: a grammar that goes missing, or a
# file that will not parse, must not turn live keys into false orphans and
# hide a real unresolved-key finding. So:
#
#   keys = (regex hits the tree cannot disprove) + (calls the tree found)
#
# A regex hit is dropped only when the parse tree can point at the string
# literal or comment containing it. Anything tree-sitter cannot parse, or has
# no grammar for, keeps the regex result untouched.

_TS_LANG_BY_EXT = {
    '.js': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.jsx': 'javascript',
    '.ts': 'typescript', '.tsx': 'tsx',
    '.vue': 'vue', '.svelte': 'svelte',
    '.php': 'php', '.dart': 'dart',
    '.kt': 'kotlin', '.kts': 'kotlin',
    '.java': 'java', '.cs': 'csharp',
    '.rb': 'ruby', '.go': 'go', '.rs': 'rust',
    '.qml': 'qmljs',
    '.lua': 'lua', '.swift': 'swift',
    '.m': 'objc', '.mm': 'objc',
    '.c': 'c', '.h': 'c',
    '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp',
    '.ex': 'elixir', '.exs': 'elixir',
    '.scala': 'scala', '.groovy': 'groovy',
    '.pl': 'perl', '.pm': 'perl',
    '.hx': 'haxe', '.astro': 'astro',
}

# Node types that mean "a function is being called". The grammars disagree on
# the name; they agree on the shape, which is what the walk relies on.
_TS_CALL_TYPES = frozenset((
    'call', 'call_expression', 'function_call_expression', 'function_call',
    'method_invocation', 'invocation_expression', 'method_call',
    'call_statement', 'scoped_call_expression', 'member_call_expression',
    # Groovy calls its call node `func`, which reads like a declaration and
    # is not one. Measured, not guessed.
    'func',
))

# Names accepted as translation calls, on top of TRANSLATION_FUNCTIONS, to
# match what the regex already recognises.
_TS_EXTRA_CALL_NAMES = frozenset((
    'tc', '__',
    # Qt. QML translates through these and nothing else, so a .qml file
    # read without them comes back empty however good the grammar is.
    'qsTr', 'qsTranslate', 'qsTrId',
    # Apple's, and gettext's mark-for-translation macro. Both carry the
    # source TEXT rather than a key in most projects, which is why the
    # tier table calls those languages text-based — but a project that
    # does use keys with them is now read.
    'NSLocalizedString', 'NSLocalizedStringWithDefaultValue', 'N_',
))

# Set true to ignore tree-sitter and exercise the regex path. The self-test
# flips it so BOTH backends are covered on the same fixture.
_FORCE_REGEX_EXTRACTION = False

# lang → parser, or None when unavailable, so a project with a thousand .kt
# files asks the pack once instead of a thousand times.
_ts_parser_cache: Dict[str, object] = {}

# ext → which backend actually read it, filled in as files are scanned.
_EXTRACTION_BACKENDS: Dict[str, str] = {}


def _ts_parser(lang: str):
    """A parser for *lang*, or None when tree-sitter cannot supply one."""
    if lang in _ts_parser_cache:
        return _ts_parser_cache[lang]
    parser = None
    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser(lang)
    except Exception:
        parser = None
    _ts_parser_cache[lang] = parser
    return parser


def _ts_dart_call(node):
    """``(name, argument container)`` when *node* is Dart's shape of a call.

    Dart's grammar has no call node: ``alert('x')`` parses as an
    identifier followed by a *selector* holding the arguments, both direct
    children of the statement. Recognised by that shape rather than by a
    type name, so it costs nothing in the grammars that do have one.
    """
    name = None
    for child in node.children:
        if child.type in ('identifier', 'scoped_identifier'):
            name = child.text.decode('utf-8', 'replace').strip()
        elif child.type == 'selector' and name:
            return name, child
        elif child.type not in (';', 'type_identifier'):
            name = name if child.type == 'selector' else None
    return "", None


def _ts_callee_name(node) -> str:
    """The bare function name of a call node.

    Takes the last identifier before the arguments, so ``i18n.t``,
    ``self.tr``, ``$t``, ``Foo::translate`` and ``obj->__`` all come back as
    the name TRANSLATION_FUNCTIONS is written in terms of.
    """
    target = (node.child_by_field_name('function')
              or node.child_by_field_name('method'))
    if target is None:
        for child in node.children:
            if child.type not in ('arguments', 'argument_list'):
                target = child
                break
    if target is None:
        return ""
    text = target.text.decode('utf-8', 'replace')
    for sep in ('::', '->', '.'):
        if sep in text:
            text = text.rsplit(sep, 1)[-1]
    return text.strip().lstrip('$@')


def _ts_factory_name(node) -> str:
    """When a call's callee is ITSELF a call, the inner call's name.

    ``useTranslations()('nav.home')`` parses as a call whose function is a
    call, so _ts_callee_name has nothing but ``useTranslations()`` to work
    with and matches nothing. The name that decides is one level down.
    """
    target = (node.child_by_field_name('function')
              or node.child_by_field_name('method'))
    if target is None or target.type not in _TS_CALL_TYPES:
        return ""
    return _ts_callee_name(target)


def _ts_string_value(node):
    """(text, is_interpolated) for a string-ish node, else (None, False).

    Interpolation is reported, not resolved: ``t(`menu.${name}`)`` cannot
    become a key, but everything before the hole is exactly the dynamic
    prefix the orphan check wants.
    """
    if 'string' not in node.type:
        return None, False
    raw = node.text.decode('utf-8', 'replace')
    # Same prefixes as _STR_PREFIX. Left on, the quote-stripping below
    # matches nothing and the key comes back with @ still attached.
    for _pfx in ('@', 'u8', 'L', 'u', 'U'):
        if (raw.startswith(_pfx) and len(raw) > len(_pfx)
                and raw[len(_pfx)] in ('"', "'")):
            raw = raw[len(_pfx):]
            break
    interpolated = any('interpolation' in c.type or 'substitution' in c.type
                       for c in node.children)
    for quote in ('"""', "'''", '`', '"', "'"):
        if (raw.startswith(quote) and raw.endswith(quote)
                and len(raw) >= 2 * len(quote)):
            raw = raw[len(quote):-len(quote)]
            break
    if interpolated:
        raw = re.split(r'\$\{|#\{|\{\{|\$\(', raw, maxsplit=1)[0]
    return raw, interpolated


#: Nodes that hold a call's arguments without being called that. Kotlin and
#: Swift put them behind a call_suffix, Groovy behind an arg_block, Dart
#: behind a selector — read off the grammars, because they agree on nothing.
_ARG_CONTAINERS = ('arguments', 'argument_list', 'value_arguments',
                   'call_suffix', 'arg_block', 'selector',
                   'value_argument_list', 'argument_part')
#: A wrapper around one argument. PHP and C# both have one; unwrapped, the
#: string inside is invisible to every check that looks at an argument.
_ARG_WRAPPERS = ('argument', 'value_argument', 'labeled_argument')


def _ts_arg_nodes(node):
    """The argument nodes of a call, punctuation and wrappers removed."""
    args = (node.child_by_field_name('arguments')
            or node.child_by_field_name('argument_list'))
    if args is None:
        for child in node.children:
            if child.type in _ARG_CONTAINERS or 'argument' in child.type:
                args = child
                break
    if args is None:
        return []
    # One more level where the container is itself a wrapper: Kotlin's
    # call_suffix holds a value_arguments, not the arguments themselves.
    while True:
        inner = [c for c in args.children
                 if c.type in _ARG_CONTAINERS and c.type != args.type]
        if len(inner) != 1:
            break
        args = inner[0]
    out = []
    for child in args.children:
        if child.type in (',', '(', ')', '[', ']'):
            continue
        if child.type in _ARG_WRAPPERS:
            real = [c for c in child.children if c.type not in (',', ':')]
            out.extend(real or [child])
        else:
            out.append(child)
    return out


def _ts_string_args(node, positions):
    """``[(text, interpolated)]`` for the given positional slots.

    Slots rather than "the first one", because pgettext's first argument
    is a context and ngettext's second is a key in its own right.
    """
    args = _ts_arg_nodes(node)
    out = []
    for slot in positions:
        if slot < len(args):
            text, interpolated = _ts_string_value(args[slot])
            if text is not None:
                out.append((text, interpolated))
    return out


def _ts_first_string_arg(node):
    """(literal_text, is_interpolated) of a call's first argument.

    (None, False) when the first argument is not a string — a variable, a
    number, another call. Those are dynamic by definition.
    """
    args = (node.child_by_field_name('arguments')
            or node.child_by_field_name('argument_list'))
    if args is None:
        for child in node.children:
            if 'argument' in child.type:
                args = child
                break
    if args is None:
        return None, False
    for child in args.children:
        if child.type in (',', '(', ')'):
            continue
        return _ts_string_value(child)
    return None, False


def _ts_scan(src_bytes: bytes, root):
    """One walk: (quoted_or_commented spans, holes, keys, prefixes).

    *spans* are byte ranges where a regex hit means nothing — inside a
    string literal or a comment. *holes* are the interpolation slots inside
    those strings, where code genuinely resumes: a call written in
    ``${t('x')}`` sits inside a template literal and must survive.
    """
    spans, holes = [], []
    keys: Set[str] = set()
    prefixes: Set[str] = set()
    stack = [root]
    seen = 0
    while stack:
        node = stack.pop()
        seen += 1
        if seen > 400_000:            # pathological input, not a parse
            break
        ntype = node.type
        if 'comment' in ntype or 'string' in ntype:
            spans.append((node.start_byte, node.end_byte))
        if 'interpolation' in ntype or 'substitution' in ntype:
            holes.append((node.start_byte, node.end_byte))
        if ntype in _TS_CALL_TYPES:
            name = _ts_callee_name(node)
            _extra = _extra_translation_calls()
            if (name in TRANSLATION_FUNCTIONS or name in _TS_EXTRA_CALL_NAMES
                    or name in _extra
                    or _ts_factory_name(node) in (_TS_FACTORY_NAMES | _extra)):
                for text, interpolated in _ts_string_args(
                        node, _key_positions(name)):
                    if not text:
                        continue
                    if interpolated:
                        if text.endswith('.'):
                            prefixes.add(text)
                    elif PythonCodeAnalyzer._KEY_PATTERN.match(text):
                        keys.add(text)
        stack.extend(node.children)
    return spans, holes, keys, prefixes


# Single-file components keep their <script> body as RAW TEXT: the Vue and
# Svelte grammars do not inject JavaScript into it, so the tree cannot point
# at a string or a comment in there and the regex result stood uncorrected —
# a call written inside a string counted as a use. Measured, not assumed:
# both were the only extensions whose decoys survived.
_RX_SFC_SCRIPT = re.compile(
    r"<script\b([^>]*)>(.*?)</script\s*>", re.S | re.I)
# Astro keeps its component script in --- fences at the top of the file, and
# its grammar hands that back as raw text for the same reason Vue's does.
_RX_ASTRO_FRONT = re.compile(r"\A\s*---\r?\n(.*?)\r?\n---", re.S)
_SFC_EXTS = frozenset(('.vue', '.svelte', '.astro'))


def _sfc_script_blocks(src: str):
    """``(language, start_byte, body)`` for each <script> in *src*.

    The offset is in BYTES of the utf-8 encoding, because that is what the
    spans the caller merges are measured in.
    """
    out = []
    front = _RX_ASTRO_FRONT.match(src)
    if front:
        out.append(('typescript',
                    len(src[:front.start(1)].encode('utf-8', 'replace')),
                    front.group(1)))
    for match in _RX_SFC_SCRIPT.finditer(src):
        attrs = (match.group(1) or "").lower()
        lang = 'typescript' if ('lang="ts"' in attrs or "lang='ts'" in attrs
                                or 'lang="typescript"' in attrs) else 'javascript'
        body = match.group(2) or ""
        start = len(src[:match.start(2)].encode('utf-8', 'replace'))
        out.append((lang, start, body))
    return out


def _extract_keys_ast(src: str, ext: str):
    """(keys, prefixes) with the regex corrected by a parse tree, or None.

    None means "this backend could not answer" — no tree-sitter, no grammar
    for the extension, or a parse that failed. It never means "nothing
    found", which is a legitimate answer returned as empty sets.
    """
    if _FORCE_REGEX_EXTRACTION:
        return None
    lang = _TS_LANG_BY_EXT.get(ext)
    if not lang:
        return None
    parser = _ts_parser(lang)
    if parser is None:
        return None
    try:
        data = src.encode('utf-8', 'replace')
        tree = parser.parse(data)
        if tree is None or tree.root_node is None:
            return None
        spans, holes, keys, prefixes = _ts_scan(data, tree.root_node)
        # A tree with error nodes has guessed at the structure, and its
        # idea of where a string ends is exactly what would drop a live
        # regex hit. Keep what it FOUND — a union can only help — and stop
        # believing it about what to discard. This matters most where one
        # extension has several languages behind it (.h, .m), where the
        # grammar picked may simply be the wrong one.
        if getattr(tree.root_node, 'has_error', False):
            spans, holes = [], []
        # A single-file component's script is raw text to its own grammar.
        # Parse each block with the language it declares and shift the
        # spans back into the file's coordinates, so `quoted()` below can
        # reject a call written inside a string in there.
        if ext in _SFC_EXTS:
            for _lang, _off, _body in _sfc_script_blocks(src):
                _p = _ts_parser(_lang)
                if _p is None:
                    continue
                try:
                    _d = _body.encode('utf-8', 'replace')
                    _t = _p.parse(_d)
                    if _t is None or _t.root_node is None:
                        continue
                    _sp, _ho, _k, _pf = _ts_scan(_d, _t.root_node)
                except Exception:
                    continue
                spans += [(a + _off, b + _off) for a, b in _sp]
                holes += [(a + _off, b + _off) for a, b in _ho]
                keys |= _k
                prefixes |= _pf
    except Exception:
        logger.debug("tree-sitter could not read a %s file", ext,
                     exc_info=True)
        return None

    def quoted(offset: int) -> bool:
        """True when a match at *offset* is inside a string or comment and
        not inside an interpolation slot within one."""
        if any(a <= offset < b for a, b in holes):
            return False
        return any(a <= offset < b for a, b in spans)

    # The regex runs on the RAW source here: blanking comments is the trick
    # the regex path needs precisely because it has no tree, and the tree
    # marks them properly.
    for rx in (_RX_CODE_CALL, _RX_CODE_FACTORY, _rx_project_calls()):
        if rx is None:
            continue
        for match in rx.finditer(src):
            value = match.group(2)
            if quoted(match.start()):
                continue
            if PythonCodeAnalyzer._KEY_PATTERN.match(value):
                keys.add(value)
    for offset, value in _multi_arg_keys(src):
        if not quoted(offset) and PythonCodeAnalyzer._KEY_PATTERN.match(value):
            keys.add(value)
    for match in _RX_CODE_TEMPLATE.finditer(src):
        if not quoted(match.start()):
            prefixes.add(match.group(1))
    return keys, prefixes


# ── Catalogue read as an OBJECT: `t.someKey` ────────────────────────────────
# Some projects never call t('key'): they hand the whole catalogue around as
# an object and read properties off it. Every call-shaped pattern above is
# blind to that — the key is never a string literal, so there is nothing to
# capture — and the tool would report "every key used in code exists" while
# seeing no usage at all. Enabled per project through
# ``member_access_objects`` in the project file, because guessing which
# single-letter identifiers are catalogues would be worse than asking.
#
# Two things make the finding useful rather than noisy:
#
#   1. SHADOWING. `t` is also the conventional name for a loop variable
#      (``tiers.filter(t => t.threshold > 0)``). Those property reads are not
#      translations. When a parse tree is available the identifier is
#      resolved against the enclosing function parameters and local
#      declarations, so a shadowed `t` is skipped — this is the reason the
#      tree path exists here at all.
#
#   2. THE FALLBACK IDIOM. ``t.qty || "Qta"`` still renders something when
#      the key is missing; ``t.qty`` alone renders the string "undefined" on
#      screen. The same missing key is therefore two different problems, and
#      they are reported apart: no fallback is blocking, fallback-only is
#      informational (the fallback text is hardcoded, usually untranslated).

# Flat identifiers: this style has no dotted namespace, so _KEY_PATTERN —
# which REQUIRES a separator and rejects capitals — would discard every one.
_MEMBER_KEY_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')

# Property names that are never catalogue keys: they belong to the objects a
# shadowed loop variable would carry, and to JS itself.
_MEMBER_KEY_STOPWORDS = frozenset((
    'length', 'name', 'value', 'type', 'id', 'key', 'map', 'filter', 'find',
    'forEach', 'reduce', 'push', 'slice', 'split', 'join', 'trim', 'toString',
    'then', 'catch', 'call', 'apply', 'bind', 'prototype', 'constructor',
    'default', 'current', 'props', 'state', 'children',
))

_TS_FUNC_TYPES = frozenset((
    'arrow_function', 'function_declaration', 'function_expression',
    'function', 'method_definition', 'generator_function',
    'generator_function_declaration',
))


def _member_access_objects() -> Set[str]:
    """Identifiers whose PROPERTY access is a translation lookup.

    Declared per project (``member_access_objects``): a project that writes
    ``t('key')`` needs nothing here, one that writes ``t.key`` needs `t`.
    """
    raw = _project_config().get("member_access_objects")
    return ({str(v).strip() for v in raw if str(v).strip()}
            if isinstance(raw, list) else set())


def _ts_binds_name(node, name: str) -> bool:
    """True when *node* binds *name* as a PLAIN parameter — a callback's own
    variable, not the catalogue.

    The shape of the binding is what separates the two, and it separates them
    cleanly:

        tiers.filter(t => t.threshold > 0)   ← plain identifier: a loop var
        const Comp = ({ t, th }) => …        ← destructured: the catalogue
        const { t } = ctx                    ← destructured: the catalogue

    An earlier version counted destructuring as shadowing too, on the
    reasoning that a binding is a binding. That silently switched the whole
    check off for every component that receives ``t`` as a prop — which is
    most of them — while still looking like it had run. Only a bare
    identifier parameter shadows here; a name pulled out of an object is how
    a catalogue is received, never how a callback variable is introduced.
    """
    def plain_params(target):
        """Identifier parameters, skipping anything inside a pattern."""
        if target is None:
            return []
        if target.type == 'identifier':
            return [target]
        out = []
        for child in target.children:
            if child.type == 'identifier':
                out.append(child)
            elif child.type in ('required_parameter', 'optional_parameter'):
                inner = child.child_by_field_name('pattern')
                if inner is not None and inner.type == 'identifier':
                    out.append(inner)
        return out

    targets = [node.child_by_field_name('parameters'),
               node.child_by_field_name('parameter')]
    if node.type == 'arrow_function' and not any(targets):
        for child in node.children:
            if child.type in ('identifier', 'formal_parameters'):
                targets.append(child)
                break
    for target in targets:
        for ident in plain_params(target):
            if ident.text.decode('utf-8', 'replace') == name:
                return True
    return False


def _ts_is_call_argument(node) -> bool:
    """True when *node* is written directly as an argument of a call.

    An inline callback (``list.filter(t => …)``) is an argument; a helper
    assigned to a name (``const label = (action, t) => …``) is not. That is
    the line between a loop variable called ``t`` and a catalogue handed to a
    helper on purpose, and it is the only signal that separates them without
    following the call site.
    """
    cur, parent = node, node.parent
    depth = 0
    while parent is not None and depth < 20:
        depth += 1
        if parent.type == 'parenthesized_expression':
            cur, parent = parent, parent.parent
            continue
        if parent.type in ('arguments', 'argument_list'):
            return True
        return parent.type in _TS_CALL_TYPES
    return False


def _ts_is_shadowed(node, name: str) -> bool:
    """True when *name* at *node* is bound as a PLAIN parameter nearby.

    Deliberately NOT read as "this is not the catalogue". Both of these bind
    ``t`` as a plain parameter and only one is a loop variable:

        tiers.filter(t => t.threshold > 0)        ← a tier
        const label = (action, t) => t.qty        ← the catalogue, passed in

    Nothing at the definition site separates them, so the answer here means
    "ambiguous", and the caller downgrades rather than discards: an ambiguous
    read still counts as USE (so a live key is never called an orphan) but
    never as evidence of a MISSING key (so ``t.threshold`` is never reported
    as an untranslated string). Under-reporting is the cheaper mistake — a
    false blocking finding is what makes a check stop being trusted."""
    cur = node.parent
    depth = 0
    while cur is not None and depth < 200:
        depth += 1
        if cur.type in _TS_FUNC_TYPES and _ts_binds_name(cur, name):
            return True
        if cur.type in ('catch_clause', 'for_in_statement'):
            param = cur.child_by_field_name('parameter') or cur.child_by_field_name('left')
            if param is not None and param.text.decode('utf-8', 'replace') == name:
                return True
        cur = cur.parent
    return False


def _ts_has_fallback(node) -> bool:
    """True when something stands to the RIGHT of the key in a ``||`` chain.

    "Has a fallback" means: if this key is missing, another value is reached.
    So the test is not "is it the left operand" but "does the chain continue
    past it" — and a chain is left-associative, which puts the middle term on
    the RIGHT of the inner node:

        t.a || t.b || "x"   parses as   (t.a || t.b) || "x"

    ``t.b`` is nobody's left operand, yet ``"x"`` still covers it. Reading only
    the immediate parent called that unprotected. So: climb while the node is
    the right operand of a ``||``/``??``, and answer yes the moment it is a
    left operand. ``a || t.qty`` correctly answers no — there the catalogue
    value IS the last resort, and a missing key reaches the screen.
    """
    cur, parent = node, node.parent
    depth = 0
    while parent is not None and depth < 100:
        depth += 1
        if parent.type == 'parenthesized_expression':
            cur, parent = parent, parent.parent
            continue
        if parent.type != 'binary_expression':
            return False
        op = parent.child_by_field_name('operator')
        if op is None or op.text.decode('utf-8', 'replace') not in ('||', '??'):
            return False
        left = parent.child_by_field_name('left')
        if left is not None and left.id == cur.id:
            return True
        cur, parent = parent, parent.parent
    return False


def _extract_member_keys_ast(src: str, ext: str, names: Set[str]):
    """``[(key, line, has_fallback, ambiguous)]`` from the parse tree, or None."""
    if _FORCE_REGEX_EXTRACTION:
        return None
    lang = _TS_LANG_BY_EXT.get(ext)
    if not lang:
        return None
    parser = _ts_parser(lang)
    if parser is None:
        return None
    try:
        data = src.encode('utf-8', 'replace')
        tree = parser.parse(data)
        if tree is None or tree.root_node is None:
            return None
        # A guessed structure cannot be trusted to resolve scope, and a wrong
        # shadowing answer is worse than no answer: hand back to the regex.
        if getattr(tree.root_node, 'has_error', False):
            return None
    except Exception:
        logger.debug("tree-sitter could not read a %s file", ext, exc_info=True)
        return None

    out = []
    stack = [tree.root_node]
    seen = 0
    while stack:
        node = stack.pop()
        seen += 1
        if seen > 400_000:
            break
        stack.extend(node.children)
        if node.type != 'member_expression':
            continue
        obj = node.child_by_field_name('object')
        prop = node.child_by_field_name('property')
        if obj is None or prop is None or obj.type != 'identifier':
            continue
        if prop.type not in ('property_identifier', 'identifier'):
            continue
        if obj.text.decode('utf-8', 'replace') not in names:
            continue
        key = prop.text.decode('utf-8', 'replace')
        if key in _MEMBER_KEY_STOPWORDS or not _MEMBER_KEY_PATTERN.match(key):
            continue
        ambiguous = _ts_is_shadowed(node, obj.text.decode('utf-8', 'replace'))
        line = src.count("\n", 0, node.start_byte) + 1
        out.append((key, line, _ts_has_fallback(node), ambiguous))
    return out


def _extract_member_keys_regex(src: str, names: Set[str]):
    """``[(key, line, has_fallback, ambiguous)]`` without a tree.

    Scope cannot be resolved here, so the binding test degrades to a
    line-local one: a line that BINDS the name marks its reads ambiguous. It
    catches the common ``list.filter(t => t.x)`` and misses a binding opened
    on an earlier line — which is why the tree path is preferred.
    """
    if not names:
        return []
    src = _blank_comments(src)
    alt = "|".join(re.escape(n) for n in sorted(names))
    rx_use = re.compile(r"\b(?:" + alt + r")\.([A-Za-z][A-Za-z0-9_]*)\s*(\|\||\?\?)?")
    rx_bind = re.compile(
        r"(?:\(\s*(?:" + alt + r")\s*[,)]|\b(?:" + alt + r")\s*=>"
        r"|\b(?:const|let|var|function)\s+(?:" + alt + r")\b)")
    out = []
    for lineno, line in enumerate(src.split("\n"), start=1):
        ambiguous = bool(rx_bind.search(line))
        for m in rx_use.finditer(line):
            key = m.group(1)
            if key in _MEMBER_KEY_STOPWORDS or not _MEMBER_KEY_PATTERN.match(key):
                continue
            out.append((key, lineno, bool(m.group(2)), ambiguous))
    return out


def _extract_member_keys(src: str, ext: str):
    """``[(key, line, has_fallback, ambiguous)]`` for the catalogue objects."""
    names = _member_access_objects()
    if not names:
        return []
    result = _extract_member_keys_ast(src, ext, names)
    if result is not None:
        return result
    return _extract_member_keys_regex(src, names)


def _extract_keys(src: str, ext: str) -> Tuple[Set[str], Set[str]]:
    """Keys and dynamic prefixes from a non-Python source.

    Tree-corrected when a grammar is available, plain regex when not. Which
    one ran is recorded so the run can say so, rather than leaving the user
    to guess how much to trust the result.
    """
    result = _extract_keys_ast(src, ext)
    if result is not None:
        _EXTRACTION_BACKENDS[ext] = "tree-sitter"
        return result
    _EXTRACTION_BACKENDS[ext] = "regex"
    return _extract_keys_regex(src)


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
# setAttribute("placeholder", "text") / el.attr("title", "text"): the visible
# text is the SECOND argument, so neither the attribute pattern (which wants
# name = "value") nor the call pattern (which reads the first argument) could
# see it — a very common way to set visible text in plain JS.
_RX_UI_SETATTR = re.compile(
    r"""\b(?:setAttribute|attr|setProperty)\s*\(\s*['"]"""
    r"""(?:placeholder|title|label|alt|aria-label|tooltip)['"]\s*,\s*"""
    r"""(['"])([^'"\n]{3,80})\1""", re.IGNORECASE)
# Operators that mean the capture came from code, not from a template.
_RX_CODE_SHAPED = re.compile(r'&&|\|\||=>|===|!==|\?\.|;\s|\+\+|--')
_RX_UI_TEXTNODE = re.compile(r">\s*([^<>{}\n|]{4,80}?)\s*<")
_TEXTNODE_EXTENSIONS = {'.vue', '.jsx', '.tsx', '.svelte'}


# A build artefact is recognised by its SHAPE, not its name. ".min." is one
# convention among many — Vite and friends emit index-4PCLXdBb.js, which no
# name test catches, and scanning one duplicated every string already found
# in the sources plus a lot of minifier noise. A line of a few hundred
# characters is normal; one of several thousand is a bundle.
_GENERATED_MAX_LINE = 600
_GENERATED_MEAN_LINE = 300


def _looks_generated(src: str) -> bool:
    """True for minified or machine-generated sources, whatever they're called."""
    lines = src.splitlines()
    if not lines:
        return False
    longest = max(len(line) for line in lines)
    if longest > _GENERATED_MAX_LINE:
        return True
    return (sum(len(line) for line in lines) / len(lines)) > _GENERATED_MEAN_LINE


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
    if _RX_CODE_SHAPED.search(t):
        # The text-node pattern reads "> … <", which in plain JS also spans
        # a pair of comparison operators: `length > 0 && depth < max` was
        # being reported as the UI string "0 && depth". Operators are the
        # tell — no interface label contains `&&` or `=>`.
        return False
    if t[0] in ')]}' or t[-1] in '([{':
        # A capture that opens or closes a bracket it does not own came from
        # the middle of an expression, not from a template. In JSX the
        # branches of a ternary look exactly like this: `) : cond ? (`.
        return False
    return True


# ── Hardcoded UI text, read from the tree ───────────────────────────────
# The regex tier below can only guess: a bare string in JS says nothing
# about itself, and `>text<` matches a comparison as readily as a text
# node. The tree knows which bytes are a JSX text node, which are the
# value of a `placeholder=`, and which are an import path or an object
# key — the three things the regex could not tell apart.
#
# Node type names were read off the grammars rather than assumed; they
# differ between the JSX family and the HTML family and agree on nothing.

#: Attributes whose value is shown to a person. Same list the regex uses.
_UI_ATTRS = frozenset((
    'placeholder', 'title', 'label', 'alt', 'aria-label', 'aria-placeholder',
    'tooltip', 'caption', 'hint', 'headertext', 'buttontext',
))
#: Calls whose first string argument is shown. Same list the regex uses.
_UI_CALLS = frozenset((
    'alert', 'confirm', 'prompt', 'setText', 'setTitle', 'setLabel',
    'setPlaceholder', 'setTooltip', 'setHeader', 'showMessage',
    'Text', 'Label', 'SnackBar',
))
#: Calls that put text into an attribute named by their FIRST argument.
_UI_SETTERS = frozenset(('setAttribute', 'attr', 'setProperty'))
#: Ancestors that make a string structural rather than visible.
_NOT_TEXT_PARENTS = frozenset((
    'import_statement', 'export_statement', 'import_specifier',
    'call_expression',        # handled separately, by callee name
))
#: A string sitting in the KEY half of an object entry.
_PAIR_TYPES = frozenset(('pair', 'object_assignment_pattern'))


def _ts_attr_name(node) -> str:
    """The attribute's name, whichever family the grammar belongs to."""
    named = (node.child_by_field_name('name')
             or node.child_by_field_name('attribute_name'))
    if named is not None:
        return named.text.decode('utf-8', 'replace').strip().lower()
    for child in node.children:
        if child.type in ('property_identifier', 'jsx_attribute_name',
                          'attribute_name', 'identifier'):
            return child.text.decode('utf-8', 'replace').strip().lower()
    return ""


def _ts_inner_text(node) -> str:
    """The text of a string-ish node with its quotes and prefix removed."""
    value, _ = _ts_string_value(node)
    if value is not None:
        return value
    return node.text.decode('utf-8', 'replace')


def _byte_position(data: bytes, offset: int):
    """``(line, column)`` of a byte offset, both 1-based, column in CHARS.

    Characters and not bytes: an editor counts columns the way a person
    reads them, and this project's own strings are full of accents.
    """
    line = data.count(b"\n", 0, offset) + 1
    start = data.rfind(b"\n", 0, offset) + 1
    col = len(data[start:offset].decode('utf-8', 'replace')) + 1
    return line, col


def _hardcoded_from_tree(data: bytes, root, out: list, offset: int = 0):
    """Collect UI-context strings from one parse tree into *out*."""
    stack = [(root, ())]
    while stack:
        node, ancestors = stack.pop()
        ntype = node.type

        # A sentence broken by an interpolation is still one sentence.
        # `<span>Total for {n} nights</span>` is three children — text,
        # expression, text — and reporting the pieces gave findings like
        # "Total for" and "nights", which read as noise and hide the fact
        # that a whole line of prose is hardcoded. Joined at the element,
        # with the holes marked, it reads as what it is.
        if ntype in ('jsx_element', 'element', 'template_element'):
            joined, first = _ts_element_text(node)
            if joined:
                out.append((first + offset, joined, 'element'))
                for child in node.children:
                    if child.type not in ('jsx_text', 'text'):
                        stack.append((child, ancestors + (ntype,)))
                continue

        # a person reads these directly
        elif ntype in ('jsx_text', 'text', 'raw_text') and not node.children:
            parent = ancestors[-1] if ancestors else ''
            if ntype != 'raw_text' or parent in ('element', 'template_element'):
                out.append((node.start_byte + offset,
                            _ts_inner_text(node), 'element'))

        elif ntype in ('jsx_attribute', 'attribute'):
            if _ts_attr_name(node) in _UI_ATTRS:
                for child in _ts_descendants(node):
                    if child.type in ('string_fragment', 'attribute_value'):
                        out.append((child.start_byte + offset,
                                    _ts_inner_text(child), 'attribute'))
                        break

        elif ntype in _TS_CALL_TYPES or ntype == 'expression_statement':
            if ntype == 'expression_statement':
                # Only Dart reaches here, and only in its own shape.
                name, container = _ts_dart_call(node)
                if not name or container is None:
                    for child in node.children:
                        stack.append((child, ancestors + (ntype,)))
                    continue
                args = _ts_arg_nodes(container)
            else:
                name = _ts_callee_name(node)
                args = _ts_arg_nodes(node)
            if name in _UI_SETTERS and len(args) >= 2:
                # setAttribute("placeholder", "text") — the visible half is
                # the SECOND argument, and the first says whether it is
                # visible at all.
                which, _ = _ts_string_value(args[0])
                text, interpolated = _ts_string_value(args[1])
                if (which or "").strip().lower() in _UI_ATTRS and text \
                        and not interpolated:
                    out.append((args[1].start_byte + offset, text, 'call'))
            elif name in _UI_CALLS or name in _ui_funcs():
                for arg in args:
                    text, interpolated = _ts_string_value(arg)
                    if text and not interpolated:
                        out.append((arg.start_byte + offset, text, 'call'))
                        break

        for child in node.children:
            stack.append((child, ancestors + (ntype,)))


def _ts_element_text(node):
    """``(visible text, first byte)`` of one element's own text children.

    Only DIRECT children: a nested element is its own line of prose and
    gets reported on its own, at its own position. Interpolations between
    the pieces become ``{…}``, because the text either side of a hole is
    one sentence and reporting the halves separately reads as noise.
    """
    parts, first, saw_hole = [], None, False
    for child in node.children:
        # An HTML entity is part of the label, not punctuation around it.
        # `<button>Succ &gt;</button>` parses as a text node beside a
        # character reference, and reading only the text left "Succ" — a
        # single word, which the multi-word rule then dropped. A real
        # button label, lost to a grammar detail.
        if child.type in ('jsx_text', 'text', 'html_character_reference',
                          'character_reference', 'entity'):
            piece = child.text.decode('utf-8', 'replace')
            if child.type != 'jsx_text' and child.type != 'text':
                piece = html.unescape(piece)
            piece = piece.strip()
            if not piece:
                continue
            if saw_hole and parts:
                parts.append('{…}')
                saw_hole = False
            parts.append(piece)
            if first is None:
                first = child.start_byte
        elif child.type in ('jsx_expression', 'interpolation'):
            if parts:
                saw_hole = True
    return (' '.join(parts) if parts else ""), (first or 0)


def _ts_descendants(node):
    stack = list(node.children)
    while stack:
        current = stack.pop()
        yield current
        stack.extend(current.children)


def _extract_hardcoded_ast(src: str, ext: str):
    """``[(line, col, text)]`` with syntax context, or None when unavailable.

    None means "ask the regex instead" — no grammar, no tree-sitter, or a
    parse that reported errors. It never means "nothing here", which is a
    legitimate answer returned as an empty list.
    """
    if _FORCE_REGEX_EXTRACTION:
        return None
    lang = _TS_LANG_BY_EXT.get(ext)
    if not lang:
        return None
    parser = _ts_parser(lang)
    if parser is None:
        return None
    try:
        data = src.encode('utf-8', 'replace')
        tree = parser.parse(data)
        if tree is None or tree.root_node is None:
            return None
        if getattr(tree.root_node, 'has_error', False):
            return None          # a guessed structure is not context
        found: list = []
        _hardcoded_from_tree(data, tree.root_node, found)
        # A single-file component's script is raw text to its own grammar,
        # so its alert()s are invisible until it is parsed on its own.
        if ext in _SFC_EXTS:
            for _lang, _off, _body in _sfc_script_blocks(src):
                _p = _ts_parser(_lang)
                if _p is None:
                    continue
                try:
                    _d = _body.encode('utf-8', 'replace')
                    _t = _p.parse(_d)
                    if _t is None or _t.root_node is None:
                        continue
                    if getattr(_t.root_node, 'has_error', False):
                        continue
                    _hardcoded_from_tree(_d, _t.root_node, found, _off)
                except Exception:
                    continue
    except Exception:
        logger.debug("tree-sitter could not read %s for text", ext,
                     exc_info=True)
        return None

    lines = src.splitlines()
    seen: set = set()
    out: list = []
    for byte_off, text, kind in sorted(found):
        text = (text or "").strip()
        if not text or text in seen or not _looks_like_ui_text(text):
            continue
        # A tail of a sentence whose middle is an interpolation: "/ ID",
        # ": max", "( {…} tot.)". Each IS hardcoded, and each is unusable
        # as a finding — there is nothing there to translate. Four letters
        # is the bar, counting neither punctuation nor the hole markers.
        #
        # ELEMENT text only. An attribute value and a call argument are
        # whole strings by construction, never fragments: applying this to
        # them cost `placeholder="Es. 5.00"`, which is exactly the kind of
        # short label the check exists to find.
        if kind == 'element' and len(
                re.sub(r'\{…\}|[^A-Za-zÀ-ÿ]', '', text)) < 4:
            continue
        lineno, col = _byte_position(data, byte_off)
        if 0 < lineno <= len(lines) and 'i18n-ignore' in lines[lineno - 1]:
            continue
        seen.add(text)
        out.append((lineno, col, text))
    return out[:40]      # same per-file cap as the regex tier


def _extract_hardcoded_regex(src: str, ext: str) -> List[Tuple[int, int, str]]:
    """Low-confidence hardcoded-text hints as ``(line, column, text)``.
    Comments are blanked shape-preservingly, so line numbers are exact;
    a line containing 'i18n-ignore' is skipped like in the AST path."""
    clean = _blank_comments(src)
    lines = src.splitlines()
    out: List[Tuple[int, int, str]] = []
    seen: Set[str] = set()

    def _add(m, group_idx):
        text = m.group(group_idx).strip()
        if not _looks_like_ui_text(text) or text in seen:
            return
        # Both coordinates from the start of the CAPTURED GROUP, never from
        # the match: _RX_UI_TEXTNODE's leading whitespace class can cross a
        # newline, so a text node indented under its tag was reported on the
        # tag's line, with a column measured against a different one.
        start = m.start(group_idx)
        lineno = clean.count(chr(10), 0, start) + 1
        if 0 < lineno <= len(lines) and 'i18n-ignore' in lines[lineno - 1]:
            return
        # 1-based, like every compiler diagnostic, so an editor can jump to it.
        col = start - (clean.rfind(chr(10), 0, start) + 1) + 1
        seen.add(text)
        out.append((lineno, col, text))

    for m in _RX_UI_ATTR.finditer(clean):
        _add(m, 2)
    for m in _RX_UI_CALL.finditer(clean):
        _add(m, 2)
    for m in _RX_UI_SETATTR.finditer(clean):
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
# Below this many informative words, langdetect is guessing: there is no
# function-word evidence to corroborate it, and it still reports 1.00.
_DETECT_MIN_WORDS = 8

_LANGDETECT_NOISE = {'cy','ro','ca','so','sw','tl','af','sq','hr','sl','et',
                     'lv','lt','id','ms','fi','eu','gl','da','no','nb','nl'}

# Words that carry no language: they are spelled the same in every locale, so
# they are never evidence that a string was left in the wrong language.
#
# ONLY genuinely cross-project vocabulary belongs here. A vendor name, a
# product, an engine, a site — those are the scanned project's business, not
# this tool's, and hardcoding one project's list here is what made the tool
# quietly wrong for every other project: their own domain words are absent,
# so each one becomes foreign-language evidence and the mixed-language check
# fills with false alarms.
#
# A project extends the set with its own terms via PROJECT_VOCAB_FILE — see
# the project file (see PROJECT_VOCAB_FILE). Nothing to edit in here.
# The line is drawn by REACH, not by category. These words are stripped
# before the string is handed to langdetect, so a name left out of the set is
# fed to a statistical language detector as if it were prose — which is how a
# short technical label with no function words gets flagged as the wrong
# language. Since none of them is a function word in any language, keeping
# one can never mask real evidence: the cost of including is ~zero, the cost
# of omitting is a false alarm. So anything a typical project might plausibly
# name — the big clouds, the operating systems, the protocols — belongs here
# even though it is a brand. Only names specific to ONE domain go in the
# project file, because a generic tool has no business knowing them.
_TECH_WORDS_BUILTIN = {
    # Protocols, formats, plumbing
    'oauth','api','json','xml','url','sdk','http','https','webdav','gcp',
    'app','client','server','id','token','key','secret','password','username',
    'scoped','access','full','service','account','create','redirect',
    'editor','console','portal','credentials',
    'backup','cloud','web','pc','zip','trusted','online','offline','link','tag',
    'provider','timeout','host','path','file','files','desktop','drive',
    # Operating systems and the major clouds — named by a large share of
    # projects, and never a function word anywhere.
    'windows','linux','macos','android','ios',
    'google','microsoft','azure','aws','dropbox','onedrive','nextcloud',
}

# Optional, project-supplied vocabulary. Same idea as the qa_lang_<code>.json
# packs this tool reads for its own UI language: drop a file in, no edit here.
# One optional file per project, read from the scanned root. Keys:
#   tech_words    — brand/domain names the language detector must ignore
#   ui_functions  — extra call names whose string args reach the screen
#   budgets       — per-severity ceilings that make findings blocking
PROJECT_VOCAB_FILE = ".i18n-quality.json"
_project_config_cache: Optional[dict] = None
# Whether the file was present and readable, for the run summary: a
# configuration that is quietly ignored is worse than none at all.
_config_state: dict = {"found": True, "error": "", "created": False}


def _tech_words() -> Set[str]:
    """The full neutral vocabulary: universal built-ins + this project's."""
    return _TECH_WORDS_BUILTIN | _project_config_list("tech_words")


CONFIG_TEMPLATE = {
    "_comment": (
        "Optional configuration for the i18n quality analyzer. Everything "
        "here describes THIS project; the analyzer itself stays "
        "project-agnostic. An empty file changes nothing, and deleting it "
        "is fine — the tool runs on its built-ins."),

    "_tech_words": (
        "Treated as language-neutral by the mixed-language check: spelled "
        "the same in every locale, so finding one in a translated string is "
        "not evidence it was left in the wrong language. The analyzer ships "
        "the wide-reach names (operating systems, clouds, protocols); this "
        "is where a project adds its own domain."),
    "tech_words": [],

    "_ui_functions": (
        "Extra call names whose string arguments reach the screen, on top "
        "of the toolkits the analyzer knows. Add house widgets here so the "
        "high-severity tier keeps working for them."),
    "ui_functions": [],

    "_exclude_dirs": (
        "Directories to skip, on top of the universal ones (caches, "
        "virtualenvs, build output, the test tree). This is where "
        "non-shipping code goes: dev-only scripts, vendored copies, an "
        "archive of old sources."),
    "exclude_dirs": [],

    "_exempt": (
        "Noise suppressions, each counted and named in the report rather "
        "than applied silently. Turn one off if your project localises that "
        "kind of string: exception messages reach a dialog in some apps."),
    "exempt": {
        "raise_arguments": True,
        "regex_patterns": True,
        "user_agents": True,
    },

    "_translation_kwargs": (
        "Keyword-argument names that carry the KEY when a translation call "
        "is written t(key='nav.home') rather than t('nav.home')."),
    "translation_kwargs": [],

    "_extra_translation_calls": (
        "Call names to treat as translation functions on top of the "
        "built-ins — for wrappers, and for JS/TS factories such as "
        "next-intl's useTranslations(), where the key is passed to what the "
        "call RETURNS."),
    "extra_translation_calls": [],

    "_budgets": (
        "Per-severity ceilings. Declaring one makes exceeding it a blocking "
        "failure, which is the only way a count of hundreds ever comes "
        "down. Left empty, the counts are informational."),
    "budgets": {},
}


def _write_config_template() -> None:
    """Drop a commented template next to the project, once.

    Written rather than described in the docs because a file that does not
    exist is a file nobody edits: the options below are discoverable only if
    they are sitting in the repository. Every value in it is empty, so the
    run it was created during behaves exactly as if it were still absent.

    Never overwrites, and never fails the run: a read-only checkout or a CI
    workspace simply says so and carries on with built-ins.
    """
    path = PROJECT_ROOT / PROJECT_VOCAB_FILE
    try:
        if path.exists():
            return
        path.write_text(
            json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        _config_state["created"] = True
        print(L("cfg_created", file=PROJECT_VOCAB_FILE))
    except Exception as exc:                                # noqa: BLE001
        _config_state["error"] = str(exc)
        print(L("cfg_uncreatable", file=PROJECT_VOCAB_FILE, err=exc))


#: Directory whose configuration is in force, or None for the root's.
#: Set around each file as it is scanned — see _config_scope.
_active_config_dir = None
#: dir -> the file's own contents (not merged). One read per directory.
_dir_config_cache: Dict[str, dict] = {}


def _load_config_at(directory) -> dict:
    """The config file sitting in *directory* itself, or ``{}``."""
    key = str(directory)
    if key not in _dir_config_cache:
        data: dict = {}
        path = Path(directory) / PROJECT_VOCAB_FILE
        try:
            if path.is_file():
                loaded = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    data = loaded
        except Exception as exc:                            # noqa: BLE001
            print(L("cfg_unreadable", file=str(path), err=exc))
            _config_state["error"] = str(exc)
        _dir_config_cache[key] = data
    return _dir_config_cache[key]


def _merge_config(base: dict, over: dict) -> dict:
    """*over* on top of *base*, one key at a time.

    Lists ADD rather than replace: a package declaring its own vocabulary
    means "these as well", not "forget the root's". Objects merge key by
    key, so switching one suppression off leaves the others alone.
    Anything else — a number, a string — is simply the nearer answer.
    """
    out = dict(base)
    for key, value in (over or {}).items():
        if key.startswith("_"):
            continue                     # the file's own documentation
        prev = out.get(key)
        if isinstance(prev, list) and isinstance(value, list):
            seen = {json.dumps(v, sort_keys=True) for v in prev}
            out[key] = prev + [v for v in value
                               if json.dumps(v, sort_keys=True) not in seen]
        elif isinstance(prev, dict) and isinstance(value, dict):
            out[key] = {**prev, **value}
        else:
            out[key] = value
    return out


def _config_chain(directory) -> dict:
    """Every config from PROJECT_ROOT down to *directory*, nearest winning.

    A monorepo is many projects in one tree, and one file at the top cannot
    describe them all: the web package's UI functions are not the CLI
    package's, and a folder one of them vendors is not excluded for the
    others. So each package answers for itself, and inherits everything it
    does not mention.
    """
    try:
        directory = Path(directory).resolve()
        root = Path(PROJECT_ROOT).resolve()
    except OSError:
        return _load_config_at(PROJECT_ROOT)
    if directory != root and root not in directory.parents:
        return _load_config_at(PROJECT_ROOT)      # outside the tree
    branch = [directory] + [p for p in directory.parents if p != root]
    branch = [p for p in branch if p == root or root in p.parents]
    merged = _load_config_at(root)
    for part in reversed(branch):
        if part == root:
            continue
        merged = _merge_config(merged, _load_config_at(part))
    return merged


class _config_scope:
    """Put *path*'s package configuration in force for the block.

    A context manager rather than an argument on nine helpers: the helpers
    are called from deep inside the visitors, and threading a path through
    all of them is how one of them ends up forgetting.
    """

    def __init__(self, path):
        try:
            p = Path(path)
            self.directory = p if p.is_dir() else p.parent
        except Exception:                                   # noqa: BLE001
            self.directory = None

    def __enter__(self):
        global _active_config_dir
        self.previous = _active_config_dir
        _active_config_dir = self.directory
        return self

    def __exit__(self, *_exc):
        global _active_config_dir
        _active_config_dir = self.previous
        return False


def _project_config() -> dict:
    """The configuration in force: the nearest one, or the root's.

    Lazy for the same reason as the vocabulary: ``--root`` reassigns
    PROJECT_ROOT after this module is imported.
    """
    global _project_config_cache
    if _active_config_dir is not None:
        return _config_chain(_active_config_dir)
    if _project_config_cache is None:
        data: dict = {}
        try:
            path = PROJECT_ROOT / PROJECT_VOCAB_FILE
            if path.is_file():
                # utf-8-SIG, not utf-8: Notepad and Windows PowerShell write
                # a BOM by default, and a BOM makes json.loads fail, which
                # this except would swallow — the user's whole configuration
                # silently ignored because of an invisible byte.
                loaded = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    data = loaded
            else:
                _config_state["found"] = False
                _write_config_template()
        except Exception as exc:
            # Said out loud, not swallowed: a configuration file that is
            # present but unreadable used to leave the run silently using
            # built-ins only, which looks exactly like a clean pass.
            print(L("cfg_unreadable", file=PROJECT_VOCAB_FILE, err=exc))
            _config_state["error"] = str(exc)
            data = {}
        _project_config_cache = data
    return _project_config_cache


def _project_config_list(key: str) -> Set[str]:
    raw = _project_config().get(key)
    if not isinstance(raw, list):
        return set()
    return {str(v).strip().lower() for v in raw if str(v).strip()}


#: What each suppression is for, in the report's own words.
_EXEMPT_KINDS = {
    "raise_arguments": "ex_raise",
    "regex_patterns": "ex_regex",
    "user_agents": "ex_agent",
}


_RX_LOOKS_REGEX = re.compile(
    r"\(\?P?[<:=!#]"          # (?P<name>  (?:  (?=  (?!  (?#
    r"|\\[dwsbAZWSB]"          # \d \w \s \b \A \Z and their negations
    r"|\[\^?[^\]]{0,40}\][*+?{]"  # a character class with a quantifier
)


def _looks_like_regex(text: str) -> bool:
    """A pattern, not prose. Anchors alone are not enough on their own.

    ``^`` and ``$`` appear in perfectly ordinary strings ("$5", "^ up"), so
    an anchor only counts when the rest of the string also reads like a
    pattern. Groups, escape classes and quantified character classes do
    not occur in text meant for a person.
    """
    if not text:
        return False
    if _RX_LOOKS_REGEX.search(text):
        return True
    anchored = text.startswith("^") or text.endswith("$")
    return anchored and any(c in text for c in "()[]|\\*+?")


def _looks_like_user_agent(text: str) -> bool:
    """``Name/1.0 (…)`` — a protocol header, never a label.

    The shape is the whole test: a slash-separated version at the start,
    which no interface string has.
    """
    return bool(re.match(r"^[A-Za-z][\w.-]{1,40}/\d[\w.]*(\s|$)", text or ""))


def _exempt_flags() -> Dict[str, bool]:
    """Which noise suppressions are on. All of them, unless told otherwise.

    On by default because every one of these is noise in the overwhelming
    majority of projects — but a project that puts exception text in front
    of the user says so here rather than being quietly under-reported.
    Whatever is suppressed is counted and named in the report either way.
    """
    raw = _project_config().get("exempt")
    out = {k: True for k in _EXEMPT_KINDS}
    if isinstance(raw, dict):
        for key in out:
            if isinstance(raw.get(key), bool):
                out[key] = raw[key]
    return out


def _translation_kwargs() -> Set[str]:
    """Keyword names that carry the key: ``t(key='nav.home')``.

    The built-ins are the names the common libraries use; a wrapper with a
    name of its own is declared in the project file.
    """
    raw = _project_config().get("translation_kwargs")
    extra = ({str(v).strip() for v in raw if str(v).strip()}
             if isinstance(raw, list) else set())
    return {"key", "msgid", "message_id", "string_id", "id"} | extra


def _extra_translation_calls() -> Set[str]:
    """Project call names that are translation calls, or return one.

    Two shapes at once, deliberately: a wrapper called like ``t()``, and a
    FACTORY whose result is called with the key — next-intl's
    ``useTranslations()('nav.home')``. Which one a name is need not be
    declared, because trying both costs nothing and asking would be one
    more thing to get wrong.
    """
    raw = _project_config().get("extra_translation_calls")
    return ({str(v).strip() for v in raw if str(v).strip()}
            if isinstance(raw, list) else set())


def _excluded_dirs() -> Set[str]:
    """Directories to skip: the universal ones plus this project's own.

    Case-sensitive, because directory names are. ``_project_config_list``
    lowercases (right for vocabulary, wrong for paths), so the project's
    entries are read raw here.
    """
    raw = _project_config().get("exclude_dirs")
    extra = ({str(v).strip() for v in raw if str(v).strip()}
             if isinstance(raw, list) else set())
    return PYTHON_EXCLUDES_BUILTIN | extra


def _ui_funcs() -> Set[str]:
    """UI-displaying call names: built-ins plus the project's own widgets.

    Case is preserved here, unlike the vocabulary: these are identifiers.
    """
    raw = _project_config().get("ui_functions")
    extra = ({str(v).strip() for v in raw if str(v).strip()}
             if isinstance(raw, list) else set())
    return PythonCodeAnalyzer._UI_FUNCS_BUILTIN | extra


# ── Severity ────────────────────────────────────────────────────────────────
# A flat list of findings is an inventory; a report that always ends "all
# blocking checks passed" while listing hundreds of them teaches the reader to
# ignore it. Severity is what turns it into a worklist, and what lets a
# project set a budget it must not exceed (see _project_budgets).
SEVERITY_ORDER = ("high", "medium", "low")
_CONTEXT_SEVERITY = {
    # Argument to a call that puts text on screen — user-visible almost by
    # definition, and the reason this tool exists.
    'ui': 'high',
    # Read from the tree: the string IS a JSX text node or the value of a
    # placeholder=, established rather than guessed at.
    'ast_ui': 'high',
    'regex_ui': 'high',
    # A label-shaped string handed to a function we do not know.
    'func_arg': 'medium',
    # Passed the general heuristics and nothing more. Often an exception
    # message or internal diagnostic, which no one is asking to translate.
    'general': 'low',
}


def _severity_for(context: str) -> str:
    return _CONTEXT_SEVERITY.get(context, 'low')


def _project_budgets() -> Dict[str, int]:
    """Per-severity ceilings from the project file, if it sets any.

    Absent means informational, exactly as before — a tool that starts
    failing builds the day it is upgraded would just be turned off.
    """
    # The root's, whatever package is in force: a budget is a ceiling on
    # the whole run, and one counted per package would be a different
    # feature — the totals it compares against are global.
    with _config_scope(PROJECT_ROOT):
        raw = _project_config().get("budgets")
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, int] = {}
    for level in SEVERITY_ORDER:
        value = raw.get(level)
        if isinstance(value, int) and value >= 0:
            out[level] = value
    return out

# ==========================================
# 🔎 AUTO-DISCOVERY
# ==========================================
# ── JavaScript / TypeScript dictionary modules ──────────────────────────────
# The JS ecosystem very often keeps its dictionaries in a module rather than
# in JSON:  export const translations = { it: {...}, en: {...} }
# Reading t('key') out of JavaScript while being unable to read the
# JavaScript that DEFINES those keys left whole projects reporting
# "no i18n dictionaries found" — the tool saw the calls and none of the data.
_JS_MODULE_EXTENSIONS = {'.js', '.mjs', '.cjs', '.ts', '.mts'}

_JS_OBJECT_START = re.compile(
    r"""(?:export\s+default|export\s+const\s+[\w$]+\s*=|"""
    r"""module\.exports\s*=|const\s+[\w$]+\s*=)\s*\{""")
_JS_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def _js_object_to_json(text: str) -> Optional[str]:
    """Normalise a JS object literal into JSON, or None if it is not one.

    A scanner rather than a pile of regexes, because everything that needs
    fixing — bare keys, single quotes, trailing commas, comments — also
    occurs INSIDE string values, where it must be left alone. Tracking
    string state is the only way to tell the two apart.

    Deliberately conservative: anything whose values are not plain strings,
    numbers, booleans, null or nested objects/arrays is rejected rather
    than guessed at, so a module holding functions or template literals is
    reported as unreadable instead of silently half-parsed.
    """
    match = _JS_OBJECT_START.search(text)
    if not match:
        return None
    i = match.end() - 1          # position of the opening brace
    out: List[str] = []
    depth = 0
    n = len(text)
    expect_key = False
    while i < n:
        ch = text[i]
        # ── strings ──
        if ch in "\"'`":
            if ch == '`':
                return None       # template literal: not a static dictionary
            quote = ch
            j = i + 1
            buf: List[str] = []
            while j < n:
                c = text[j]
                if c == '\\':
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                if c == quote:
                    break
                if c == '\n':
                    return None   # unterminated string
                buf.append('\\"' if c == '"' else c)
                j += 1
            out.append('"' + ''.join(buf) + '"')
            i = j + 1
            expect_key = False
            continue
        # ── comments ──
        if ch == '/' and i + 1 < n and text[i + 1] == '/':
            i = text.find('\n', i)
            if i == -1:
                break
            continue
        if ch == '/' and i + 1 < n and text[i + 1] == '*':
            end = text.find('*/', i + 2)
            if end == -1:
                break
            i = end + 2
            continue
        # ── structure ──
        if ch == '{' or ch == '[':
            depth += 1
            out.append(ch)
            expect_key = (ch == '{')
            i += 1
            continue
        if ch == '}' or ch == ']':
            depth -= 1
            # Trailing comma: whitespace was emitted between it and the
            # closing brace, so the popping has to walk past that too — the
            # first version only looked at the immediately previous token
            # and left every trailing comma in place.
            while out and (not out[-1].strip() or out[-1].strip() == ','):
                if out.pop().strip() == ',':
                    break
            out.append(ch)
            i += 1
            if depth == 0:
                return ''.join(out)
            expect_key = False
            continue
        if ch == ',':
            out.append(ch)
            expect_key = True
            i += 1
            continue
        if ch == ':':
            out.append(ch)
            expect_key = False
            i += 1
            continue
        if ch.isspace():
            out.append(' ')
            i += 1
            continue
        # ── bare identifier: a key to quote, or a literal to keep ──
        ident = _JS_IDENT.match(text, i)
        if ident:
            word = ident.group(0)
            after = i + len(word)
            while after < n and text[after].isspace():
                after += 1
            if after < n and text[after] == ':' and expect_key:
                out.append('"' + word + '"')
            elif word in ('true', 'false', 'null'):
                out.append(word)
            elif word == 'undefined':
                out.append('null')
            else:
                return None        # a reference or a call — not static data
            i = ident.end()
            continue
        if ch.isdigit() or (ch == '-' and i + 1 < n and text[i + 1].isdigit()):
            j = i + 1
            while j < n and (text[j].isdigit() or text[j] in '.eE+-'):
                j += 1
            out.append(text[i:j])
            i = j
            continue
        return None                # anything else: give up rather than guess
    return None


def _load_js_module_dict(path: Path) -> Optional[dict]:
    """Parse a JS/TS translations module into a plain dict."""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    as_json = _js_object_to_json(text)
    if not as_json:
        return None
    try:
        data = json.loads(as_json)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


_LOCALE_DIR_NAMES = {'i18n', 'locales', 'locale', 'lang', 'languages', 'translations', 'l10n'}
_SINGLE_FILE_NAMES = {'translations', 'strings', 'messages', 'i18n', 'lang', 'locale'}
_DATA_EXTENSIONS = {'.json'} | _JS_MODULE_EXTENSIONS
if yaml_mod:
    _DATA_EXTENSIONS |= {'.yml', '.yaml'}


# How deep to hunt for a locale directory. The layout that matters here is
# src/i18n — the default in every Vite/CRA/Vue project — and app/locales,
# frontend/src/i18n and friends; scanning only the root's immediate children
# meant those projects were told they had no dictionaries at all.
_LOCALE_SEARCH_DEPTH = 4


def _locale_search_dirs(root: Path) -> List[Path]:
    """*root* and every non-excluded directory beneath it, bounded by depth."""
    found = [root]
    frontier = [(root, 0)]
    while frontier:
        current, depth = frontier.pop()
        if depth >= _LOCALE_SEARCH_DEPTH:
            continue
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            if child.name.startswith('.') or child.name in _excluded_dirs():
                continue
            found.append(child)
            frontier.append((child, depth + 1))
    return found


def _has_lang_files(directory: Path) -> bool:
    """True when *directory* holds per-language dictionary files (en.json…)."""
    try:
        return any(
            f.stem.lower().replace('-', '_').split('_')[0] in _ISO_CODES
            and f.suffix.lower() in _DATA_EXTENSIONS
            for f in directory.iterdir() if f.is_file()
        )
    except OSError:
        return False


def _scan_dir_for_locales(parent: Path,
                          per_lang_dirs: List[Path],
                          single_files: List[Path]) -> None:
    """Collect locale sources found directly under *parent*."""
    try:
        children = sorted(parent.iterdir())
    except OSError:
        return
    for child in children:
        if child.name.startswith('.') or child.name in _excluded_dirs():
            continue

        if child.is_dir():
            if child.name.lower() not in _LOCALE_DIR_NAMES:
                continue
            if _has_lang_files(child):
                per_lang_dirs.append(child)
                continue
            # e.g. i18n/locales/en.json
            try:
                subdirs = [s for s in child.iterdir() if s.is_dir()]
            except OSError:
                subdirs = []
            for sub in subdirs:
                if sub.name.lower() in _LOCALE_DIR_NAMES and _has_lang_files(sub):
                    per_lang_dirs.append(sub)
            # a single multi-language file inside the locale dir
            for f in child.iterdir():
                if (f.is_file() and f.suffix.lower() in _DATA_EXTENSIONS
                        and f.stem.lower() in _SINGLE_FILE_NAMES):
                    single_files.append(f)

        elif child.is_file() and child.suffix.lower() in _DATA_EXTENSIONS:
            if child.stem.lower() in _SINGLE_FILE_NAMES:
                single_files.append(child)


def _discover_locale_sources(root: Path) -> Tuple[List[Path], List[Path]]:
    """Return (directories_with_per_lang_files, single_multilang_files).

    Searched to a bounded depth, not just among the root's own children:
    the layout that matters most in the JS world is ``src/i18n``, the
    default in every Vite/CRA/Vue project, and a root-only scan told those
    projects they had no dictionaries at all.
    """
    per_lang_dirs: List[Path] = []
    single_files: List[Path] = []
    for parent in _locale_search_dirs(root):
        _scan_dir_for_locales(parent, per_lang_dirs, single_files)
    # One directory can be reached twice (i18n/ and i18n/locales/) —
    # de-duplicate while keeping first-seen order.
    return (list(dict.fromkeys(per_lang_dirs)),
            list(dict.fromkeys(single_files)))


def _load_data_file(path: Path) -> Optional[dict]:
    """Load a dictionary file: JSON, YAML, or a JS/TS module."""
    suffix = path.suffix.lower()
    if suffix in _JS_MODULE_EXTENSIONS:
        return _load_js_module_dict(path)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            if suffix in {'.yml', '.yaml'} and yaml_mod:
                return yaml_mod.safe_load(f)
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

    # Functions/methods whose string arguments are DISPLAYED to the user.
    #
    # Toolkit-shaped by necessity — "does this argument reach a screen" cannot
    # be answered without knowing the toolkit. Several are covered rather than
    # only the one this file grew up with, and a project adds its own through
    # ``ui_functions`` in the project file, so a house widget library or a
    # toolkit not listed here does not silently switch this tier off.
    _UI_FUNCS_BUILTIN = {
        # ── Qt (PySide / PyQt) ──
        'setText', 'setToolTip', 'setPlaceholderText', 'setWindowTitle',
        'setStatusTip', 'setWhatsThis', 'setSuffix', 'setPrefix',
        'setTitle', 'setTabText', 'setItemText', 'setLabelText',
        'showMessage',
        'QLabel', 'QPushButton', 'QCheckBox', 'QRadioButton',
        'QGroupBox', 'QAction', 'QMenu', 'QMessageBox',
        'addItem', 'addTab',
        # ── tkinter ──
        'showinfo', 'showwarning', 'showerror', 'askyesno', 'askokcancel',
        'Label', 'Button', 'Checkbutton', 'Radiobutton', 'LabelFrame',
        # ── GTK / PyGObject ──
        'set_label', 'set_text', 'set_title', 'set_tooltip_text',
        'set_markup', 'set_placeholder_text',
        # ── wxPython ──
        'SetLabel', 'SetToolTip', 'SetTitle', 'SetStatusText', 'MessageBox',
        # ── Kivy / generic ──
        'set_caption',
    }

    # Names that are never UI when called as a PLAIN FUNCTION — constructors,
    # logging, builtins.
    _IGNORE_FUNCS = {
        # Logging / exceptions
        'print', 'Exception', 'ValueError', 'RuntimeError', 'TypeError',
        'FileNotFoundError', 'KeyError', 'ImportError', 'AttributeError',
        'OSError', 'IOError', 'PermissionError', 'NotImplementedError',
        # Introspection / builtins
        'isinstance', 'hasattr', 'getattr', 'setattr', 'type',
        'getenv', 'open', 'compile',
        # Path / non-UI constructors
        'Path',
        'QFont', 'QColor', 'QSize', 'QPoint', 'QRect',
        'QIcon', 'QPixmap', 'QCursor', 'QBrush', 'QPen',
        'Signal', 'Slot', 'QTimer', 'QThread',
    }

    # Names that are never UI when called as a METHOD (``x.name(...)``).
    #
    # Split from the above deliberately. One flat set was matched by bare
    # name whatever the call looked like, so a project with a FUNCTION named
    # get(), format() or read() had its user-facing strings silently dropped
    # — a recall hole that leaves no trace in the report.
    _IGNORE_METHODS = {
        # Logging
        'debug', 'info', 'warning', 'error', 'critical', 'exception',
        # Environment. 'getenv' is in _IGNORE_FUNCS as well, and that is not
        # a duplicate: nearly everyone writes os.getenv(...), which is an
        # ATTRIBUTE call and never reached the function set — so every
        # os.getenv("APPDATA", "") in a codebase came back as a label.
        'getenv',
        # Styling / formatting
        'setStyleSheet', 'strftime', 'strptime', 'set_style', 'setObjectName',
        # OS / IO
        'setdefault', 'mkdir', 'write_text', 'read_text', 'write', 'read',
        # Regex
        'match', 'search', 'sub', 'findall',
        # String / collection plumbing
        'connect', 'emit', 'format', 'join', 'replace', 'split',
        'startswith', 'endswith', 'encode', 'decode', 'get', 'pop',
    }

    def __init__(self):
        self.hardcoded_strings: Set[Tuple[int, int, str]] = set()   # general context
        self.ui_context_strings: Set[Tuple[int, int, str]] = set()  # UI widget context
        self.func_arg_strings: Set[Tuple[int, int, str]] = set()    # unknown function arg context
        self.raise_positions: Set[Tuple[int, int]] = set()          # inside a raise
        self.used_translation_keys: Set[str] = set()
        # Literal first-args of t()-family CALLS only — unlike
        # used_translation_keys this never mixes in dotted literals found
        # in data structures (module paths etc.), so it is safe to demand
        # that every one of these keys actually EXISTS in the locales.
        self.t_call_keys: Set[str] = set()
        self.dynamic_key_prefixes: Set[str] = set()
        self._string_vars: Dict[str, Set[str]] = defaultdict(set)

    @staticmethod
    def _pos(node, fallback_line: int = 0) -> Tuple[int, int]:
        """``(line, column)`` of *node*, both 1-based.

        ast counts columns from 0; every compiler, linter and editor counts
        them from 1, and a report is read next to those — so it is shifted
        here once rather than everywhere it is printed.
        """
        return (getattr(node, 'lineno', fallback_line) or fallback_line,
                getattr(node, 'col_offset', 0) + 1)

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
        _is_t_call = (func_name in TRANSLATION_FUNCTIONS
                      or func_name in _extra_translation_calls())
        # t(key='nav.home') — the key is not node.args[0], and reading that
        # slot regardless picked up whatever else happened to be positional.
        if _is_t_call and not node.args:
            _kwnames = _translation_kwargs()
            for kw in node.keywords:
                if kw.arg not in _kwnames:
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    self.used_translation_keys.add(kw.value.value)
                    self.t_call_keys.add(kw.value.value)
                elif isinstance(kw.value, ast.JoinedStr):
                    self._extract_dynamic_prefix(kw.value)
        if _is_t_call and node.args:
            for _slot in _key_positions(func_name)[1:]:
                if _slot < len(node.args):
                    _extra = node.args[_slot]
                    if (isinstance(_extra, ast.Constant)
                            and isinstance(_extra.value, str)):
                        self.used_translation_keys.add(_extra.value)
                        self.t_call_keys.add(_extra.value)
                    elif isinstance(_extra, ast.JoinedStr):
                        self._extract_dynamic_prefix(_extra)
            _first = _key_positions(func_name)[0]
            if _first >= len(node.args):
                self.generic_visit(node)
                return
            arg = node.args[_first]
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

        is_method = isinstance(node.func, ast.Attribute)

        # ── UI-context string collection ──
        if func_name in _ui_funcs():
            for arg in node.args:
                self._collect_ui_strings(arg, node.lineno)
            for kw in node.keywords:
                if kw.arg in ('text', 'title', 'label', 'tooltip', 'message',
                              'suffix', 'prefix', 'placeholder'):
                    self._collect_ui_strings(kw.value, node.lineno)
            # Still recurse for nested t() calls
            self._visit_calls_only(node)
            return

        # ── Ignored calls (logging, system) — matched by CALL SHAPE ──
        ignored = (func_name in self._IGNORE_METHODS if is_method
                   else func_name in self._IGNORE_FUNCS)
        if ignored:
            self._visit_calls_only(node)
            return

        # ── Unknown function — collect positional string args as func-arg context ──
        if func_name and not _is_t_call:
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    self.func_arg_strings.add((*self._pos(arg, node.lineno), arg.value))

        self.generic_visit(node)

    def _collect_ui_strings(self, node, fallback_line: int):
        """Extract string values from an AST node in a UI context."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.ui_context_strings.add((*self._pos(node, fallback_line), node.value))
        elif isinstance(node, ast.JoinedStr):
            # Extract static fragments from f-strings in UI context
            for val in node.values:
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    raw = val.value
                    # Also extract visible text from HTML fragments
                    visible = re.sub(r'<[^>]+>', ' ', raw).strip()
                    visible = re.sub(r'\s+', ' ', visible).strip()
                    if raw.strip():
                        self.ui_context_strings.add((*self._pos(val, fallback_line), raw.strip()))
                    if visible and visible != raw.strip():
                        self.ui_context_strings.add((*self._pos(val, fallback_line), visible))
            self._extract_dynamic_prefix(node)
        elif isinstance(node, ast.Call):
            # Nested call like QLabel(t(...)) — process the call
            self.visit_Call(node)

    def _visit_calls_only(self, node):
        """Walk child nodes looking ONLY for translation and UI function calls.
        Does NOT process other calls — prevents false collection of strings
        inside nested non-UI calls like .get(), .format(), etc."""
        _PROPAGATE = TRANSLATION_FUNCTIONS | _ui_funcs()
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

    def visit_Raise(self, node):
        """Positions of every string this ``raise`` carries.

        Not dropped here — the strings are still collected, and the caller
        decides. That keeps the suppression countable and reversible
        instead of a hole nothing can see: a project whose exception text
        reaches a dialog turns it off and gets its findings back.
        """
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                self.raise_positions.add(self._pos(child, node.lineno))
            elif isinstance(child, ast.JoinedStr):
                for val in child.values:
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        self.raise_positions.add(self._pos(val, node.lineno))
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            val = node.value
            self.hardcoded_strings.add((*self._pos(node), val))
            if self._KEY_PATTERN.match(val):
                self.used_translation_keys.add(val)
        self.generic_visit(node)

    def visit_JoinedStr(self, node):
        for val in node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                self.hardcoded_strings.add((*self._pos(val, node.lineno), val.value))
        self.generic_visit(node)


# ==========================================
# 🧠 ANALIZZATORE PRINCIPALE
# ==========================================
# ═══════════════════════════════════════════════════════════════════════════
# ICU MessageFormat — plural rule coverage
# ═══════════════════════════════════════════════════════════════════════════
# A plural whose language needs six forms and got two reads perfectly in
# review: the English is right, the translation is right, nothing is empty
# and no placeholder is missing. It is wrong only for the counts that land
# on the branch nobody wrote — which in Russian is most of them, and in
# Arabic nearly all of them. That is invisible to every other check in this
# file, so it gets its own.

_ICU_CATEGORIES = frozenset(("zero", "one", "two", "few", "many", "other"))
_ICU_SUBMESSAGE_KINDS = frozenset(("plural", "selectordinal", "select"))

# Cheap gate: only messages that look like ICU pay for the parser. A project
# with no ICU at all (SaveSync is one) spends one regex per string.
_RX_ICU_HINT = re.compile(
    r"\{\s*[\w.]+\s*,\s*(?:plural|select|selectordinal)\s*,")

# Counts a user actually sees. Probing the real rules with these tells us
# which categories are everyday and which exist only for millions, decimals
# or compact notation — see _plural_categories.
_PLURAL_PROBE_INTS = tuple(range(0, 201))

# Set true to ignore babel and exercise the built-in table. The self-test
# flips it so BOTH sources are covered, whatever the machine has installed.
_FORCE_BUILTIN_PLURALS = False


def _icu_skip_quote(s: str, i: int) -> int:
    """Index just past the ICU quote starting at *i* (which is an apostrophe).

    ICU rules: '' is one literal apostrophe; an apostrophe before { } # or |
    opens a quoted run that ends at the next apostrophe; anywhere else it is
    an ordinary character. Getting this wrong would mis-read every Italian
    l'utente and French d'accord in the file.
    """
    n = len(s)
    if i + 1 < n and s[i + 1] == "'":
        return i + 2
    if i + 1 < n and s[i + 1] in "{}#|":
        end = s.find("'", i + 2)
        return n if end == -1 else end + 1
    return i + 1


def _icu_find_close(s: str, start: int) -> int:
    """Index of the '}' matching the '{' at *start*, or -1 if it never closes."""
    depth = 0
    i = start
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "'":
            i = _icu_skip_quote(s, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _icu_branches(body: str):
    """Parse "one{...} other{...}" into ({keyword: body}, order, errors).

    *order* keeps repeats, so a duplicated keyword is visible as
    len(order) != len(branches). "offset:N" is consumed. Explicit "=0"
    selectors stay in the mapping; they are values, not plural categories,
    and the caller filters them out.
    """
    branches, order, errors = {}, [], []
    i, n = 0, len(body)
    while i < n:
        while i < n and body[i].isspace():
            i += 1
        if i >= n:
            break
        j = i
        while j < n and not body[j].isspace() and body[j] != "{":
            j += 1
        keyword = body[i:j]
        while j < n and body[j].isspace():
            j += 1
        if not keyword:
            break
        if keyword.lower().startswith("offset:"):
            i = j
            continue
        if j >= n or body[j] != "{":
            errors.append(keyword)
            break
        close = _icu_find_close(body, j)
        if close == -1:
            errors.append(keyword)
            break
        order.append(keyword)
        branches[keyword] = body[j + 1:close]
        i = close + 1
    return branches, order, errors


def _icu_arguments(text: str):
    """Every argument in *text*: (submessages, simple_names, errors).

    A submessage is a plural/select/selectordinal dict with its branches;
    a simple name is the argument of a plain {name} or {n, number}. Nested
    arguments inside branch bodies are found too. *errors* holds structural
    problems that make the message unformattable at runtime.
    """
    subs, simples, errors = [], set(), []

    def walk(s: str, depth: int = 0):
        if depth > 8:
            return
        i, n = 0, len(s)
        while i < n:
            ch = s[i]
            if ch == "'":
                i = _icu_skip_quote(s, i)
                continue
            if ch != "{":
                i += 1
                continue
            close = _icu_find_close(s, i)
            if close == -1:
                errors.append(s[i:i + 60])
                return
            inner = s[i + 1:close]
            i = close + 1
            head, _, rest = inner.partition(",")
            kind, _, body = rest.partition(",")
            name, kind = head.strip(), kind.strip()
            if kind in _ICU_SUBMESSAGE_KINDS and name:
                branches, order, berrs = _icu_branches(body)
                errors.extend(berrs)
                subs.append({"name": name, "kind": kind,
                             "branches": branches, "order": order})
                for sub_body in branches.values():
                    walk(sub_body, depth + 1)
            elif "{" not in inner and name and re.fullmatch(r"[\w.]+", name):
                simples.add(name)
            else:
                walk(inner, depth + 1)

    walk(text)
    return subs, simples, errors


def _icu_placeholders(text: str):
    """Placeholder set for an ICU message, or None when it will not parse.

    The point is that this must come out IDENTICAL across languages. The
    plain-brace regex cannot: on {count, plural, one{# item} other{# items}}
    it never sees "count" and instead reports "# item" and "# items" — the
    translated prose — as if those were variable names. Compared against a
    Russian translation that is a guaranteed mismatch, reported as critical,
    on every plural in the project.
    """
    try:
        subs, simples, errors = _icu_arguments(text)
    except Exception:
        return None
    if errors:
        return None
    names = {a["name"] for a in subs} | simples
    if not names:
        return None
    return names | set(re.findall(r"(%[sdif])", text))


def _base_lang(code: str) -> str:
    """'pt_BR' / 'zh-Hans' -> 'pt' / 'zh'."""
    return re.split(r"[-_]", str(code).strip(), maxsplit=1)[0].lower()


# Fallback when babel is absent. Two sets per language: categories a plain
# count 0-200 selects, and the extra ones only large numbers, decimals or
# compact notation reach. Findings drawn from here are capped at medium and
# say so — a wrong row costs a noisy line, never a broken build.
_ONLY_OTHER = ("ja", "ko", "zh", "th", "vi", "id", "ms", "my", "km", "lo",
               "yue", "jv", "su", "bo", "dz", "ig", "yo", "to", "wo")
_ONE_OTHER = ("en", "de", "nl", "sv", "da", "nb", "nn", "no", "fi", "et",
              "el", "bg", "af", "sw", "ur", "tr", "az", "hu", "ka", "kk",
              "ky", "uz", "mn", "ne", "sq", "ta", "te", "kn", "ml", "mr",
              "hi", "bn", "gu", "pa", "as", "or", "si", "am", "fa", "eu",
              "is", "mk", "fil", "tl", "hy", "so", "zu", "nso")
_BUILTIN_PLURAL_SETS: Dict[str, tuple] = {}
for _c in _ONLY_OTHER:
    _BUILTIN_PLURAL_SETS[_c] = ({"other"}, set())
for _c in _ONE_OTHER:
    _BUILTIN_PLURAL_SETS[_c] = ({"one", "other"}, set())
_BUILTIN_PLURAL_SETS.update({
    # Romance: "many" is the compact/million form ("1 milione"), not everyday.
    "it": ({"one", "other"}, {"many"}),
    "es": ({"one", "other"}, {"many"}),
    "fr": ({"one", "other"}, {"many"}),
    "pt": ({"one", "other"}, {"many"}),
    "ca": ({"one", "other"}, {"many"}),
    # Slavic: few/many fire at 2 and 5. Missing one is an everyday bug.
    "ru": ({"one", "few", "many"}, {"other"}),
    "uk": ({"one", "few", "many"}, {"other"}),
    "be": ({"one", "few", "many"}, {"other"}),
    "pl": ({"one", "few", "many"}, {"other"}),
    "cs": ({"one", "few", "other"}, {"many"}),
    "sk": ({"one", "few", "other"}, {"many"}),
    "hr": ({"one", "few", "other"}, set()),
    "sr": ({"one", "few", "other"}, set()),
    "bs": ({"one", "few", "other"}, set()),
    "sl": ({"one", "two", "few", "other"}, set()),
    "lt": ({"one", "few", "other"}, {"many"}),
    "lv": ({"zero", "one", "other"}, set()),
    "ro": ({"one", "few", "other"}, set()),
    "ar": ({"zero", "one", "two", "few", "many", "other"}, set()),
    "he": ({"one", "two", "other"}, set()),
    "ga": ({"one", "two", "few", "many", "other"}, set()),
    "gd": ({"one", "two", "few", "other"}, set()),
    "cy": ({"zero", "one", "two", "few", "many", "other"}, set()),
    "br": ({"one", "two", "few", "many", "other"}, set()),
    "mt": ({"one", "two", "few", "many", "other"}, set()),
})


def _plural_categories(lang: str, ordinal: bool = False):
    """(everyday, rare, source, rule) for *lang*, or None when the language is new.

    everyday — categories a plain integer count 0-200 selects. A missing one
               shows the wrong text for numbers users type every day.
    rare     — categories only large numbers, decimals or compact notation
               reach. Nearly every real project omits these and is fine.

    The split is DERIVED by running the language's own rules over real
    counts, not hardcoded per language, so it stays correct for languages
    this file has never heard of. Unknown language -> None, and the caller
    falls back to the checks that need no table at all.

    *rule* maps a count to its category, or is None when the sets came
    from the built-in table. Callers need it to decide whether an
    explicit =1 selector already covers a category.
    """
    base = _base_lang(lang)
    if not _FORCE_BUILTIN_PLURALS:
        try:
            from babel import Locale
            loc = Locale.parse(base)
            rule = loc.ordinal_form if ordinal else loc.plural_form
            every = {rule(n) for n in _PLURAL_PROBE_INTS}
            # "other" is the implicit fallback: babel leaves it out of .tags,
            # so English would come back needing only "one" without this.
            allcats = set(rule.tags) | {"other"}
            every &= allcats
            return every, allcats - every, "CLDR", rule
        except Exception:
            pass
    if ordinal:
        return None          # ordinal sets differ from cardinal; no guessing
    sets = _BUILTIN_PLURAL_SETS.get(base)
    if not sets:
        return None
    return set(sets[0]), set(sets[1]), "built-in", None


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
            'orphan_keys': set(), 'unresolved_code_keys': [], 'icu_plurals': [],
            'member_missing': [], 'member_fallback_only': [],
        }
        self.all_known_keys: Set[str] = set()
        self.all_used_code_keys: Set[str] = set()
        self.all_t_call_keys: Set[str] = set()
        # Letture t.chiave: chiave, file, riga e se c'e' un fallback.
        self.member_key_uses = []
        self.all_dynamic_prefixes: Set[str] = set()
        # kind -> how many findings that suppression held back. Reported,
        # never silent: see _exempt_flags.
        self.exempt_counts: Dict[str, int] = {}
        # context -> how many files that tier answered for.
        self.text_backends: Dict[str, int] = {}
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
        self.test_member_access_keys()
        self.test_empty_values_and_placeholders()
        self.test_mixed_languages()
        self.test_orphan_keys()
        self.test_json_real_duplicates()
        self.test_icu_plural_rules()
        self.test_severity_budgets()

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
        """Variables a message expects, for the cross-language comparison.

        ICU messages take a different path because the plain regex below
        matches only innermost braces: on a plural it returns the branch
        PROSE ("# item", "# items") and never the argument. Two languages
        then never agree and every plural is reported as a critical
        placeholder mismatch. Anything that does not look like ICU, or that
        fails to parse, keeps the original behaviour untouched.
        """
        s = str(text)
        if _RX_ICU_HINT.search(s):
            icu = _icu_placeholders(s)
            if icu is not None:
                return icu
        braces = set(re.findall(r'\{([^{}]+)\}', s))
        percents = set(re.findall(r'(%[sdif])', s))
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
        _EXTRACTION_BACKENDS.clear()
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # This directory's own configuration decides what is pruned
            # under it, and what counts as vocabulary or a UI widget in the
            # files it holds — see _config_scope. In a single-root project
            # there is one config and this changes nothing.
            with _config_scope(root):
                _skip = _excluded_dirs()
            dirs[:] = [d for d in dirs
                       if d not in _skip and not d.startswith('.')]
            for fname in files:
                ext = Path(fname).suffix.lower()
                fpath = Path(root) / fname
                if ext in _REGEX_CODE_EXTENSIONS:
                    # Non-Python source: key extraction via tree-sitter
                    # when a grammar is available, regex otherwise —
                    # minified bundles are skipped either way (no keys a
                    # human wrote, and megabytes of them).
                    try:
                        _src = fpath.read_text(encoding='utf-8', errors='replace')
                    except Exception:
                        continue
                    if '.min.' in fname.lower() or _looks_generated(_src):
                        continue
                    try:
                      with _config_scope(fpath):
                        _keys, _prefixes = _extract_keys(_src, ext)
                        self.all_used_code_keys.update(_keys)
                        self.all_t_call_keys.update(_keys)
                        self.all_dynamic_prefixes.update(_prefixes)
                        _rel = str(fpath.relative_to(PROJECT_ROOT))
                        # Catalogo letto come oggetto (t.chiave): tenuto a
                        # parte dalle chiamate t('chiave') perche' la regola
                        # del fallback vale solo qui, ma confluisce comunque
                        # in all_used_code_keys — altrimenti l'analisi delle
                        # chiavi orfane le direbbe tutte inutilizzate.
                        for _mk, _mline, _mfb, _mamb in _extract_member_keys(_src, ext):
                            self.all_used_code_keys.add(_mk)
                            self.member_key_uses.append(
                                {'key': _mk, 'file': _rel, 'line': _mline,
                                 'fallback': _mfb, 'ambiguous': _mamb,
                                 'preview': _preview(_src.splitlines(), _mline)})
                        _other_lines = _src.splitlines()
                        # The tree when it can answer, the regex when it
                        # cannot. Which one answered is recorded per file,
                        # because "hint" and "read from the syntax" are not
                        # the same claim and the report says which.
                        _ast_hits = _extract_hardcoded_ast(_src, ext)
                        _ctx = 'ast_ui' if _ast_hits is not None else 'regex_ui'
                        _hits = (_ast_hits if _ast_hits is not None
                                 else _extract_hardcoded_regex(_src, ext))
                        self.text_backends[_ctx] = (
                            self.text_backends.get(_ctx, 0) + 1)
                        for _lineno, _col, _text in _hits:
                            self.results['hardcoded'].append({
                                'file': _rel, 'line': _lineno, 'col': _col,
                                'text': _text, 'context': _ctx,
                                'severity': _severity_for(_ctx),
                                'preview': _preview(_other_lines, _lineno)})
                        n_other += 1
                    except Exception:
                        pass
                    continue
                if ext != '.py':
                    continue
                n_py += 1
                rel = fpath.relative_to(PROJECT_ROOT)
                _scope = _config_scope(fpath)
                try:
                    _scope.__enter__()
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
                    for lineno, col, text in ana.ui_context_strings:
                        if _suppressed(lineno):
                            continue
                        if self._is_ui_context_string(text):
                            key = (str(rel), lineno, text)
                            if key not in seen:
                                seen.add(key)
                                self.results['hardcoded'].append({
                                    'file': str(rel), 'line': lineno, 'col': col,
                                    'text': text, 'context': 'ui',
                                    'severity': _severity_for('ui'),
                                    'preview': _preview(src_lines, lineno)})

                    # Known noise, held back rather than dropped: what is
                    # skipped here is counted by kind and named in the
                    # report, and any kind can be switched back on. A silent
                    # filter would read as "nothing to see" for a project
                    # that does put this text in front of the user.
                    _flags = _exempt_flags()

                    def _exempt(lineno, col, text) -> bool:
                        if _flags["raise_arguments"] and (lineno, col) in ana.raise_positions:
                            kind = "raise_arguments"
                        elif _flags["regex_patterns"] and _looks_like_regex(text):
                            kind = "regex_patterns"
                        elif _flags["user_agents"] and _looks_like_user_agent(text):
                            kind = "user_agents"
                        else:
                            return False
                        self.exempt_counts[kind] = self.exempt_counts.get(kind, 0) + 1
                        return True

                    # Tier 2: Function-arg strings — ALL-CAPS labels passed to unknown functions
                    for lineno, col, text in ana.func_arg_strings:
                        if _suppressed(lineno):
                            continue
                        key = (str(rel), lineno, text)
                        if key not in seen and self._is_func_arg_label(text):
                            if _exempt(lineno, col, text):
                                continue
                            seen.add(key)
                            self.results['hardcoded'].append({
                                'file': str(rel), 'line': lineno, 'col': col,
                                'text': text, 'context': 'func_arg',
                                'severity': _severity_for('func_arg'),
                                'preview': _preview(src_lines, lineno)})

                    # Tier 3: General strings (strict filter)
                    for lineno, col, text in ana.hardcoded_strings:
                        if _suppressed(lineno):
                            continue
                        key = (str(rel), lineno, text)
                        if key not in seen and self._is_ui_string(text):
                            if _exempt(lineno, col, text):
                                continue
                            seen.add(key)
                            self.results['hardcoded'].append({
                                'file': str(rel), 'line': lineno, 'col': col,
                                'text': text, 'context': 'general',
                                'severity': _severity_for('general'),
                                'preview': _preview(src_lines, lineno)})
                except Exception:
                    pass
                finally:
                    _scope.__exit__(None, None, None)
        print(L("scan_summary", py=n_py, other=n_other))
        if self.exempt_counts:
            print(L("exempt_note",
                    n=sum(self.exempt_counts.values()),
                    detail=", ".join(
                        f"{n} {L(_EXEMPT_KINDS[k])}"
                        for k, n in sorted(self.exempt_counts.items())),
                    file=PROJECT_VOCAB_FILE))
        if _EXTRACTION_BACKENDS:
            used = sorted(set(_EXTRACTION_BACKENDS.values()))
            exts = ", ".join(sorted(_EXTRACTION_BACKENDS))
            print(L("scan_backend", how=" + ".join(used), exts=exts))

    def severity_counts(self) -> Dict[str, int]:
        counts = {level: 0 for level in SEVERITY_ORDER}
        for it in self.results['hardcoded']:
            counts[it.get('severity') or _severity_for(it.get('context', ''))] += 1
        return counts

    def test_icu_plural_rules(self):
        """ICU MessageFormat: does every plural cover its language's forms?

        Every other check in this file would pass a Russian plural written
        with the two branches English needs. The key exists, nothing is
        empty, the placeholder is there, the prose is Russian. It is simply
        wrong for 2, 3, 4 (few) and for 5 and up (many) — which is to say,
        for most numbers a user ever sees.

        Findings are graded by how they were reached, not by how confident
        this file feels:

        - Structural problems need no table at all and always block: a
          missing "other" branch (ICU raises without one), a keyword that is
          not a plural category, the same branch twice, braces that never
          close.
        - "This language needs a category you did not write" leans on plural
          rules. With babel installed those are real CLDR and the finding
          blocks; from the built-in table it is capped at medium and says
          so, so a wrong row here can never break somebody's build.

        Categories only reachable through millions, decimals or compact
        notation are reported separately at low severity, because nearly
        every correct project omits them — requiring Italian "many" would
        flag every well-written Italian plural in existence.
        """
        print("\n" + L("an_icu"))
        if not self.flat_locales:
            return
        master_lang = max(self.flat_locales, key=lambda k: len(self.flat_locales[k]))
        master = self.flat_locales.get(master_lang, {})
        scanned = 0
        sources = set()

        def add(lang, key, severity, problem, detail, snippet):
            # *problem* is a stable code. The self-test asserts on it, and it
            # must not move when the tool runs in another language.
            self.results['icu_plurals'].append({
                'lang': lang, 'key': key, 'severity': severity,
                'problem': problem, 'detail': detail,
                'snippet': str(snippet)[:120]})

        for lang, flat in sorted(self.flat_locales.items()):
            cats = None
            for key, text in flat.items():
                text = str(text)
                if not _RX_ICU_HINT.search(text):
                    # Master has a plural here and this language flattened it
                    # into a plain string. Only this direction is a finding:
                    # the reverse is legitimate, since a richer language may
                    # need branches English never had.
                    if (lang != master_lang and key in master
                            and _RX_ICU_HINT.search(str(master[key]))):
                        add(lang, key, 'medium', 'flattened',
                            L("icu_p_flattened", master=master_lang), text)
                    continue
                scanned += 1
                try:
                    subs, _simples, errors = _icu_arguments(text)
                except Exception:
                    subs, errors = [], ["?"]
                if errors:
                    add(lang, key, 'high', 'malformed',
                        L("icu_p_malformed"), text)
                    continue
                if cats is None:
                    cats = _plural_categories(lang) or ()
                for arg in subs:
                    kind = arg['kind']
                    present = set(arg['branches'])
                    if len(arg['order']) != len(present):
                        dupes = sorted({k for k in arg['order']
                                        if arg['order'].count(k) > 1})
                        add(lang, key, 'high', 'duplicate',
                            L("icu_p_duplicate", kw=", ".join(dupes)), text)
                    if 'other' not in present:
                        add(lang, key, 'high', 'no_other',
                            L("icu_p_no_other"), text)
                    if kind == 'select':
                        # Branch names here are arbitrary (male/female/other);
                        # validating them against CLDR categories would flag
                        # every correct gender select in the project.
                        continue
                    named = {k for k in present if not k.startswith('=')}
                    bad = sorted(named - _ICU_CATEGORIES)
                    if bad:
                        add(lang, key, 'high', 'bad_keyword',
                            L("icu_p_bad_keyword", kw=", ".join(bad)), text)
                    if kind != 'plural' or not cats:
                        # selectordinal selects from a different category set
                        # that is not worth reconstructing from memory; it
                        # keeps every structural check above.
                        continue
                    everyday, rare, src, rule = cats
                    sources.add(src)
                    # "=1{One file} other{# files}" is COMPLETE in a
                    # two-form language: the explicit selector takes the
                    # count "one" would have handled. Reporting a missing
                    # "one" there would block a correct message — and the
                    # advice this very check prints elsewhere is to reach
                    # for exactly that syntax.
                    explicit = {int(k[1:]) for k in present
                                if k.startswith('=') and k[1:].isdigit()}

                    def covered(cat, _e=explicit, _r=rule, _ev=everyday):
                        if not _e:
                            return False
                        if _r is not None:
                            hits = {n for n in _PLURAL_PROBE_INTS
                                    if _r(n) == cat}
                            return bool(hits) and hits <= _e
                        # No rule function to ask. One inference is still
                        # safe: where a language has two everyday forms,
                        # "one" IS the singular and fires at 1 alone, so an
                        # explicit =1 covers it. Languages whose "one" also
                        # picks 21 and 31 (Russian, Polish) have more than
                        # two everyday forms and never reach this branch.
                        return (cat == "one" and 1 in _e
                                and _ev == {"one", "other"})

                    missing = sorted(c for c in everyday - named
                                     if not covered(c))
                    if missing:
                        blocking = src == "CLDR"
                        add(lang, key, 'high' if blocking else 'medium',
                            'missing',
                            L("icu_p_missing", cats=", ".join(missing),
                              src=src if blocking else L("icu_src_builtin")),
                            text)
                    missing_rare = sorted(rare - named)
                    if missing_rare:
                        add(lang, key, 'low', 'missing_rare',
                            L("icu_p_missing_rare",
                              cats=", ".join(missing_rare)), text)
                    dead = sorted(named - everyday - rare)
                    if dead:
                        add(lang, key, 'low', 'dead_branch',
                            L("icu_p_dead", cats=", ".join(dead)), text)

        found = self.results['icu_plurals']
        if not scanned:
            print(L("icu_absent"))
            return
        high = [f for f in found if f['severity'] == 'high']
        if not found:
            print(L("icu_ok", n=scanned))
        else:
            print(L("icu_bad", n=len(found), scanned=scanned, high=len(high)))
            for f in found[:12]:
                print(f"      - {f['lang']}:{f['key']} — {f['detail']}")
        if "built-in" in sources:
            print(L("icu_src_hint"))
        if high:
            self.failures.append(L(
                "fail_icu", n=len(high),
                items=", ".join(f"{f['lang']}:{f['key']}" for f in high[:6])))

    def test_severity_budgets(self):
        """Compare the findings against the ceilings the project set.

        No budgets declared → purely informational, exactly as before: a
        tool that started failing builds the day it was upgraded would just
        get switched off. A project that DOES declare one gets a ratchet it
        cannot quietly slip past, which is the only way a count of hundreds
        ever comes down.
        """
        print("\n" + L("an_severity"))
        counts = self.severity_counts()
        budgets = _project_budgets()
        for level in SEVERITY_ORDER:
            budget = budgets.get(level)
            suffix = "" if budget is None else f"  (max {budget})"
            print(L("sev_count", level=level, n=counts[level]) + suffix)
            if budget is not None and counts[level] > budget:
                self.failures.append(
                    L("fail_budget", level=level, n=counts[level], max=budget))
        if not budgets:
            print(L("sev_no_budget", file=PROJECT_VOCAB_FILE))

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

    def test_member_access_keys(self):
        """Catalogo letto come OGGETTO: ``t.chiave`` invece di ``t('chiave')``.

        Le chiamate non vedono questo stile — la chiave non e' mai una
        stringa letterale — quindi senza questo controllo un progetto cosi'
        scritto riceve un "ogni chiave usata esiste" che non ha guardato
        niente. Le chiavi arrivano gia' filtrate dallo shadowing (una ``t``
        di ciclo non e' il catalogo).

        Due esiti distinti per la stessa chiave mancante, perche' sono due
        problemi diversi:
          - letta senza fallback  -> a schermo esce "undefined": bloccante;
          - sempre con fallback   -> innocua, ma il testo di ripiego e' nel
            codice e di norma non tradotto: informativa.
        """
        print("\n" + L("an_member"))
        if not _member_access_objects():
            print(L("member_off"))
            return
        if not self.member_key_uses:
            print(L("member_ok"))
            return
        print(L("member_seen", n=len(self.member_key_uses),
                o=", ".join(sorted(_member_access_objects()))))

        # Solo le letture NON ambigue accusano una chiave di essere mancante:
        # da un binding indistinguibile non si puo' dire se l'oggetto era il
        # catalogo, e un falso bloccante costa piu' di una chiave non vista.
        missing = defaultdict(list)
        for use in self.member_key_uses:
            if use.get('ambiguous'):
                continue
            if use['key'] not in self.all_known_keys:
                missing[use['key']].append(use)

        bad, fb_only = [], []
        for key, uses in missing.items():
            naked = [u for u in uses if not u['fallback']]
            (bad if naked else fb_only).append(
                {'key': key, 'uses': naked or uses})

        bad.sort(key=lambda r: r['key'])
        fb_only.sort(key=lambda r: r['key'])
        self.results['member_missing'] = bad
        self.results['member_fallback_only'] = fb_only

        if bad:
            print(L("member_bad", n=len(bad)))
            for row in bad:
                where = row['uses'][0]
                print(f"      - {row['key']}  ({where['file']}:{where['line']})")
            self.failures.append(L("fail_member", n=len(bad),
                                   items=", ".join(r['key'] for r in bad[:10])))
        if fb_only:
            print(L("member_fb", n=len(fb_only)))
        if not bad and not fb_only:
            print(L("member_ok"))

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

        neutral_words = _tech_words()   # built-ins + this project's own

        def _paren(m):
            toks = re.findall(r'[\w.]+', m.group(1))
            neutral = all(
                t0[:1].isupper() or any(c.isdigit() for c in t0)
                or '.' in t0 or t0.lower() in neutral_words
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
            if lw in neutral_words or len(lw) == 1:
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
                    # A length floor for the langdetect-only route, not just
                    # for the noisy languages. A short string made entirely
                    # of content words carries no function-word evidence
                    # either way, and langdetect answers confidently anyway:
                    # "Total includes promos/discounts/service cost." came
                    # back as Spanish at 1.00, "Promo professional price
                    # (total lot)" as Italian at 1.00. Both are English.
                    # The deterministic stopword route below is untouched —
                    # it stays as sensitive as it was on any length.
                    if len(words) < _DETECT_MIN_WORDS:
                        strong_detect = False
                    elif top.lang in _LANGDETECT_NOISE:
                        strong_detect = top.prob >= 0.99
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
                (L("cat_member"), self.results['member_missing'], L("sev_crit")),
                (L("cat_member_fb"), self.results['member_fallback_only'], L("sev_med")),
                (L("cat_unresolved"), self.results['unresolved_code_keys'], L("sev_crit")),
                (L("cat_icu") + " — high",
                 [i for i in self.results['icu_plurals'] if i['severity'] == 'high'],
                 L("sev_crit")),
                (L("cat_icu") + " — medium",
                 [i for i in self.results['icu_plurals'] if i['severity'] == 'medium'],
                 L("sev_med")),
                (L("cat_icu") + " — low",
                 [i for i in self.results['icu_plurals'] if i['severity'] == 'low'],
                 L("sev_low")),
                (L("cat_empty"), self.results['empty_values'], L("sev_high")),
                (L("cat_missing"), self.results['missing_keys'], L("sev_high")),
                (L("cat_hardcoded") + " — high",
                 [i for i in self.results['hardcoded']
                  if (i.get('severity') or _severity_for(i.get('context', ''))) == 'high'],
                 L("sev_high")),
                (L("cat_hardcoded") + " — medium",
                 [i for i in self.results['hardcoded']
                  if (i.get('severity') or _severity_for(i.get('context', ''))) == 'medium'],
                 L("sev_med")),
                (L("cat_hardcoded") + " — low",
                 [i for i in self.results['hardcoded']
                  if (i.get('severity') or _severity_for(i.get('context', ''))) == 'low'],
                 L("sev_low")),
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

            if self.exempt_counts:
                f.write(L("r_exempt_h", file=PROJECT_VOCAB_FILE))
                for kind, n in sorted(self.exempt_counts.items()):
                    f.write(L("r_exempt_row", kind=kind, n=n,
                              why=L(_EXEMPT_KINDS[kind])))
                f.write("\n")

            if self.results['unresolved_code_keys']:
                f.write(L("r_unresolved_h"))
                for k in self.results['unresolved_code_keys']:
                    f.write(f"- [ ] `{k}`\n")
                f.write("\n")

            if (self.results['member_missing']
                    or self.results['member_fallback_only']):
                f.write(L("r_member_h"))
                if self.results['member_missing']:
                    f.write(L("r_member_bad"))
                    for row in self.results['member_missing']:
                        f.write(f"- [ ] `{row['key']}`\n")
                        for use in row['uses'][:5]:
                            f.write(f"  - [{use['file']}:{use['line']}]"
                                    f"(../{use['file']}#L{use['line']})"
                                    f" — `{use['preview']}`\n")
                    f.write("\n")
                if self.results['member_fallback_only']:
                    f.write(L("r_member_fb"))
                    for row in self.results['member_fallback_only']:
                        use = row['uses'][0]
                        f.write(f"- `{row['key']}` — {use['file']}:{use['line']}\n")
                    f.write("\n")

            if self.results['hardcoded']:
                tiers = [
                    ('ui', L("tier_ui_t"), L("tier_ui_d")),
                    ('func_arg', L("tier_func_t"), L("tier_func_d")),
                    ('general', L("tier_gen_t"), L("tier_gen_d")),
                    ('ast_ui', L("tier_ast_t"), L("tier_ast_d")),
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
                        # line THEN column: two findings on one line read in
                        # the order they appear in it.
                        for it in sorted(fitems,
                                         key=lambda x: (x['line'], x.get('col', 0))):
                            st = str(it['text']).replace('`', "'").replace('\n', '\\n')
                            f.write(L("r_line", line=it['line'],
                                      col=it.get('col', 1), rp=rp, text=st))
                            prev = it.get('preview')
                            # Only when it adds something: for a bare string
                            # literal on its own line the preview IS the
                            # finding, and repeating it is noise.
                            if prev and prev.strip("'\" ") != st.strip("'\" "):
                                f.write(L("r_preview", preview=prev))
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

            if self.results['icu_plurals']:
                f.write(L("r_icu_h"))
                rank = {'high': 0, 'medium': 1, 'low': 2}
                for it in sorted(self.results['icu_plurals'],
                                 key=lambda x: (rank.get(x['severity'], 3),
                                                x['lang'], x['key'])):
                    f.write(L("r_icu_line", lang=it['lang'], key=it['key'],
                              detail=it['detail']))
                    # The snippet is ICU source, so it is full of braces. It
                    # goes through an f-string, never through L(): a template
                    # would try to format those braces as fields and raise.
                    f.write(f"    - `{it['snippet']}`\n")
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




# ==========================================
# 🧪 SELF-TEST
# ==========================================
# The tool checks the project; until now nothing checked the tool. Its
# heuristics are hand-curated lists, and a mistake in one is invisible on the
# codebase it was written against — which is exactly how a vocabulary full of
# ONE project's brand names shipped as "universal" and went unnoticed.
#
# So: a synthetic project with planted problems and planted non-problems, and
# an assertion for each. Every case below guards a specific behaviour, and a
# failure names which one broke.

_SELF_TEST_FILES = {
    "locales/en.json": """{
  "app": {"title": "Settings", "save": "Save"},
  "dead": {"unused": "Nobody references this"}
}""",
    "locales/it.json": """{
  "app": {"title": "Impostazioni", "save": "Salva"},
  "dead": {"unused": "Nessuno la usa"},
  "leftover": {"english": "The backup could not be created because the disk is full"},
  "brandy": {"ok": "Sincronizzazione con Acmecloud e Widgetdrive completata senza errori"}
}""",
    ".i18n-quality.json": """{
  "tech_words": ["acmecloud", "widgetdrive"],
  "ui_functions": ["HouseLabel"],
  "exclude_dirs": ["vendored"],
  "translation_kwargs": ["msg_key"],
  "extra_translation_calls": ["houseT"]
}""",
    "app.py": '''
from i18n import t

def build(ui):
    ui.setText(t("app.title"))
    ui.setToolTip("Save your progress now")          # planted: UI hardcoded
    ui.setText(t("app.nonexistent"))                 # planted: unresolved key
    ui.setText("Internal debug marker")              # i18n-ignore
    cfg = {}
    cfg.get("Config lookup value")                   # method ignore: not a finding
    HouseLabel("Custom widget text")                 # project ui_functions -> high
    ui.setText(pgettext("menu bar", "app.title"))    # key is arg 1, not arg 0
    ui.setText(ngettext("app.save", "app.title", n)) # BOTH are keys
    ui.setText(t(key="app.save"))                    # key by KEYWORD, not position
    ui.setText(t(msg_key="app.title"))               # project's own kwarg name
    ui.setText(houseT("app.save"))                   # project's own call name
    import os
    os.getenv("APPDATA", "")                         # env read, not a label
    # A custom class on purpose: RuntimeError and friends were already
    # ignored by name, so only a project's OWN exception exercises this.
    raise HouseError("The archive could not be opened for reading")
''',
    # A folder the project excluded. Everything in it is planted to be
    # found, so if any of it turns up the exclusion did not happen.
    "vendored/skipped.py": '''
def build(ui):
    ui.setText("This vendored string must never be reported")
''',
    # A monorepo package that answers for itself: its own widget name, its
    # own excluded folder, and everything it does not mention inherited
    # from the root above it.
    "packages/web/.i18n-quality.json": """{
  "ui_functions": ["WebLabel"],
  "exclude_dirs": ["generated"]
}""",
    "packages/web/page.py": '''
def build(ui):
    WebLabel("Package widget text")                  # the PACKAGE's widget
    HouseLabel("Inherited widget text")              # the ROOT's, still known
''',
    "packages/web/generated/build.py": '''
def build(ui):
    ui.setText("This generated string must never be reported")
''',
    # A sibling package that declares nothing. The web package's widget must
    # not be known here, or the configuration was global after all.
    "packages/cli/main.py": '''
def build(ui):
    WebLabel("Sibling package text")
''',
    # Non-Python sources: the regex tier had no coverage here at all, which
    # is how a text node indented under its tag kept being reported on the
    # tag's line, with a column measured against a different one.
    "web/a.js": """
const title = t('app.title');
const miss  = t('js.absent.key');
el.setAttribute("placeholder", "Type your name here");
""",
    "web/b.vue": """<template>
  <div>
    Indented text node here
  </div>
</template>
<script>
export default { mounted() { this.$t('vue.absent.key'); } }
</script>
""",
    "web/c.php": "<?php echo __('php.absent.key'); ?>",
    "helpers.py": '''
def get(label):                                      # a FUNCTION named get
    return label

def build():
    return get("Plain function argument text")       # planted: not suppressed

_UA = "HouseApp/2.1 (integration probe)"             # user-agent, not a label
_RX = r"^(?P<head>[A-Za-z_][\\w .-]*)\\s*[=:]"          # a pattern, not prose
''',
}

# (case id, description, predicate over the finished analyzer)
_SELF_TEST_CASES = [
    ("package_ui_function",
     "a package's own ui_functions apply inside that package",
     lambda a: any(i['text'] == "Package widget text" and i['severity'] == 'high'
                   for i in a.results['hardcoded'])),
    ("package_inherits_the_root",
     "and what it does not mention is inherited from the root above it",
     lambda a: any(i['text'] == "Inherited widget text" and i['severity'] == 'high'
                   for i in a.results['hardcoded'])),
    ("package_exclude_dirs",
     "a folder excluded by the package is skipped under it",
     lambda a: not any("generated" in str(i['file'])
                       for i in a.results['hardcoded'])),
    ("package_config_does_not_leak",
     "and the package's widget is unknown in a sibling that never declared it",
     lambda a: not any(i['text'] == "Sibling package text"
                       and i['severity'] == 'high'
                       for i in a.results['hardcoded'])),
    ("root_exclude_still_applies",
     "the root's own excludes keep working with packages in the tree",
     lambda a: not any("vendored" in str(i['file'])
                       for i in a.results['hardcoded'])),
    ("pgettext_key_position",
     "pgettext's key is its SECOND argument; the first is a context",
     lambda a: "app.title" in a.all_t_call_keys),
    ("pgettext_context_is_not_a_key",
     "and the context is not filed as one, where it would mask an orphan",
     lambda a: "menu bar" not in a.all_t_call_keys),
    ("ngettext_both_forms",
     "ngettext carries a key in each of its first two arguments",
     lambda a: {"app.save", "app.title"} <= a.all_t_call_keys),
    ("key_by_keyword",
     "t(key='app.save') registers the key, not just t('app.save')",
     lambda a: "app.save" in a.all_t_call_keys),
    ("key_by_project_keyword",
     "and a keyword name the project declared works the same way",
     lambda a: "app.title" in a.all_t_call_keys),
    ("project_translation_call",
     "a call name from extra_translation_calls counts as a translation call",
     lambda a: "app.save" in a.all_t_call_keys
               and not any(i['text'] == "app.save"
                           for i in a.results['hardcoded'])),
    ("exclude_dirs_honoured",
     "a directory named in exclude_dirs is not scanned at all",
     lambda a: not any("vendored" in str(i['file'])
                       for i in a.results['hardcoded'])),
    ("getenv_is_not_a_label",
     "os.getenv('APPDATA') is an environment read, not a heading",
     lambda a: not any(i['text'] == "APPDATA"
                       for i in a.results['hardcoded'])),
    ("raise_message_exempt",
     "an exception message is held back, not reported",
     lambda a: not any(i['text'].startswith("The archive could not be opened")
                       for i in a.results['hardcoded'])),
    ("raise_exemption_is_counted",
     "and it is counted by kind rather than dropped in silence",
     lambda a: a.exempt_counts.get("raise_arguments", 0) >= 1),
    ("user_agent_exempt",
     "a User-Agent string is held back and counted",
     lambda a: a.exempt_counts.get("user_agents", 0) >= 1
               and not any(i['text'].startswith("HouseApp/2.1")
                           for i in a.results['hardcoded'])),
    ("regex_exempt",
     "so is a regular expression",
     lambda a: a.exempt_counts.get("regex_patterns", 0) >= 1),
    ("real_text_still_found",
     "and none of that quietened a string that IS user-facing",
     lambda a: any(i['text'] == "Save your progress now"
                   for i in a.results['hardcoded'])),
    ("ui_hardcoded",
     "a string passed to a UI setter is found at high severity",
     lambda a: any(i['text'] == "Save your progress now" and i['severity'] == 'high'
                   for i in a.results['hardcoded'])),
    ("project_ui_function",
     "a widget named in the project's ui_functions counts as UI",
     lambda a: any(i['text'] == "Custom widget text" and i['severity'] == 'high'
                   for i in a.results['hardcoded'])),
    ("unresolved_key",
     "t() on a key absent from every locale is blocking",
     lambda a: "app.nonexistent" in a.results['unresolved_code_keys']),
    ("orphan_key",
     "a locale key nothing references is reported orphan",
     lambda a: "dead.unused" in a.results['orphan_keys']),
    ("ignore_comment",
     "# i18n-ignore silences the line it sits on",
     lambda a: not any(i['text'] == "Internal debug marker"
                       for i in a.results['hardcoded'])),
    ("method_ignored",
     "a string argument to .get() is not a finding",
     lambda a: not any(i['text'] == "Config lookup value"
                       for i in a.results['hardcoded'])),
    ("function_not_ignored",
     "a string argument to a FUNCTION named get() still is",
     lambda a: any(i['text'] == "Plain function argument text"
                   for i in a.results['hardcoded'])),
    ("mixed_language",
     "an English sentence in the Italian file is flagged",
     lambda a: any(r['key'] == "leftover.english" for r in a.results['mixed_langs'])),
    # Asserted on the vocabulary itself, not through the pipeline. The
    # pipeline route looked fine and proved nothing: the fixture sentence
    # carried Italian function words, so the check short-circuited before the
    # vocabulary was ever consulted and the case passed with the project file
    # disabled. A test that passes while the thing it names is broken is
    # worse than no test.
    ("vocab_loaded",
     "the project's own tech_words reach the neutral vocabulary",
     lambda a: {"acmecloud", "widgetdrive"} <= a.probe["tech_words"]),
    ("config_error_survivable",
     "a malformed configuration warns instead of crashing the run",
     lambda a: isinstance(a.probe["budgets"], dict)),
    ("config_bom_tolerated",
     "a configuration file saved with a BOM is still read",
     lambda a: "acmecloud" in a.probe["tech_words"]),
    ("vocab_builtin_kept",
     "the built-in vocabulary survives alongside the project's",
     lambda a: {"json", "windows", "dropbox"} <= a.probe["tech_words"]),
    ("brand_sentence_clean",
     "a translated sentence naming brands is not flagged wrong-language",
     lambda a: not any(r['key'] == "brandy.ok" for r in a.results['mixed_langs'])),
    ("regex_keys_js",
     "t() keys are extracted from JavaScript",
     lambda a: "js.absent.key" in a.results['unresolved_code_keys']),
    ("regex_keys_vue",
     "$t() keys are extracted from a Vue single-file component",
     lambda a: "vue.absent.key" in a.results['unresolved_code_keys']),
    ("regex_keys_php",
     "__() keys are extracted from PHP",
     lambda a: "php.absent.key" in a.results['unresolved_code_keys']),
    ("regex_setattr",
     "setAttribute('placeholder', text) is caught in plain JS",
     lambda a: any(i['text'] == "Type your name here"
                   for i in a.results['hardcoded'])),
    ("regex_textnode_position",
     "an indented text node reports ITS OWN line and column",
     lambda a: any(i['text'] == "Indented text node here"
                   and i['preview'].strip() == "Indented text node here"
                   and i['col'] >= 1
                   for i in a.results['hardcoded'])),
    ("column_recorded",
     "every finding carries a 1-based column",
     lambda a: all(i.get('col', 0) >= 1 for i in a.results['hardcoded'])),
    ("preview_recorded",
     "every finding carries the source line it sits on",
     lambda a: all(i.get('preview') for i in a.results['hardcoded'])),
]


# ── Second scenario: the JavaScript layout ─────────────────────────────────
# A different world from the JSON one above: dictionaries living in a module
# under src/, no Python at all. Both the module parser and the nested
# discovery were added after a real project reported "no i18n dictionaries
# found" while its src/i18n/translations.js sat right there.
_SELF_TEST_FILES_JS = {
    "src/i18n/translations.js": """
export const translations = {
  it: {
    save: "Salva",
    nav: { home: "Pagina iniziale" },
    // un commento fra le chiavi
    onlyItalian: "Presente solo in italiano",
  },
  en: {
    save: "Save",
    nav: { home: "Home page" },
    leftInItalian: "Il totale include promo e sconti applicati al carrello",
    shortEnglish: "Promo professional price (total lot)",
  },
};
""",
    "src/App.jsx": """
export default function App() {
  return (
    <div>
      <span>Hardcoded label here</span>
      {items.length > 0 && depth < maxDepth ? <A /> : <B />}
      <button title={t('save')}>{t('save')}</button>
      <p>{useTranslations()('nav.home')}</p>
    </div>
  );
}
""",
    "dist/assets/index-a1b2c3.js": (
        'const a=1;' + 'const bundled="Minified label text";' * 60 + '\n'),
}

_SELF_TEST_CASES_JS = [
    ("js_module_parsed",
     "a JS translations module is read as a dictionary",
     lambda a: set(a.flat_locales) == {"it", "en"}),
    ("js_nested_discovery",
     "dictionaries under src/i18n are found, not just at the root",
     lambda a: any("i18n" in str(p) for p in a.locale_source_files)),
    ("js_missing_key",
     "a key present in one language and absent in the other is reported",
     lambda a: any(r['missing_key'] == "onlyItalian"
                   for r in a.results['missing_keys'])),
    ("js_factory_call",
     "a key passed to what a factory returns — useTranslations()('k') — is a use",
     lambda a: "nav.home" in a.all_t_call_keys),
    ("js_factory_key_not_orphan",
     "so the key it names is not reported as unreferenced",
     lambda a: "nav.home" not in a.results['orphan_keys']),
    ("js_hardcoded_found",
     "hardcoded JSX text is still reported",
     lambda a: any(i['text'] == "Hardcoded label here"
                   for i in a.results['hardcoded'])),
    ("js_code_shape_rejected",
     "a JSX comparison is not mistaken for a text node",
     lambda a: not any('&&' in i['text'] or i['text'].strip().startswith(')')
                       for i in a.results['hardcoded'])),
    ("js_generated_skipped",
     "a bundled asset is skipped whatever it is named",
     lambda a: not any('Minified label text' in i['text']
                       for i in a.results['hardcoded'])),
    ("js_untranslated_flagged",
     "a long Italian sentence left in the English file is flagged",
     lambda a: any(r['key'] == "leftInItalian" for r in a.results['mixed_langs'])),
    ("js_short_string_spared",
     "a short English string of content words is NOT flagged",
     lambda a: not any(r['key'] == "shortEnglish"
                       for r in a.results['mixed_langs'])),
]


# ── Scenario 3: ICU MessageFormat ──────────────────────────────────────────
# SaveSync itself has no ICU at all, so without this fixture the whole plural
# engine would ship unexercised. Every planted problem below is one a human
# reviewer waves through: the prose is right in each language, and only the
# branch coverage is wrong.
_SELF_TEST_FILES_ICU = {
    "locales/en.json": """{
  "cart": {
    "items_ok":  "{count, plural, one{# item} other{# items}}",
    "files":     "{count, plural, one{# file} other{# files}}",
    "photos":    "{count, plural, one{# photo} other{# photos}}",
    "flat":      "{count, plural, one{# note} other{# notes}}",
    "no_other":  "{count, plural, one{# item} few{# items}}",
    "broken":    "{count, plural, one{# item other{# items}}",
    "typo":      "{count, plural, one{# item} ohter{# items}}",
    "dupe":      "{count, plural, one{# item} one{# thing} other{# items}}",
    "zero_dead": "{count, plural, zero{no items} one{# item} other{# items}}",
    "who":       "{gender, select, male{He wrote} female{She wrote} other{They wrote}}",
    "nested":    "{count, plural, one{# item for {name}} other{# items for {name}}}",
    "one_file":  "{n, plural, =1{One file} other{# files}}"
  }
}""",
    "locales/ru.json": """{
  "cart": {
    "items_ok": "{count, plural, one{# товар} few{# товара} many{# товаров} other{# товара}}",
    "files":    "{count, plural, one{# файл} other{# файла}}",
    "flat":     "заметки",
    "nested":   "{count, plural, one{# товар для {name}} few{# товара для {name}} many{# товаров для {name}} other{# товара для {name}}}",
    "one_file": "{n, plural, =1{Один файл} other{# файлов}}"
  }
}""",
    "locales/ar.json": """{
  "cart": {
    "photos": "{count, plural, one{صورة} other{# صورة}}"
  }
}""",
    "locales/it.json": """{
  "cart": {
    "items_ok": "{count, plural, one{# articolo} other{# articoli}}",
    "apos":     "{count, plural, one{l'utente ha # file} other{gli utenti hanno # file}}",
    "quoted":   "{count, plural, one{una '{'graffa'}' letterale} other{# graffe}}"
  }
}""",
    "app.py": '''
from i18n import t

def build(ui):
    ui.setText(t("cart.items_ok"))
    ui.setText(t("cart.files"))
    ui.setText(t("cart.photos"))
    ui.setText(t("cart.flat"))
    ui.setText(t("cart.no_other"))
    ui.setText(t("cart.broken"))
    ui.setText(t("cart.typo"))
    ui.setText(t("cart.dupe"))
    ui.setText(t("cart.zero_dead"))
    ui.setText(t("cart.who"))
    ui.setText(t("cart.nested"))
    ui.setText(t("cart.apos"))
    ui.setText(t("cart.quoted"))
    ui.setText(t("cart.one_file"))
''',
}


def _icu_find(analyzer, lang, key, problem=None):
    """Findings for one locale key, optionally narrowed to one problem code."""
    return [f for f in analyzer.results['icu_plurals']
            if f['lang'] == lang and f['key'] == key
            and (problem is None or f['problem'] == problem)]


_SELF_TEST_CASES_ICU = [
    # ── the point of the whole check ────────────────────────────────────────
    ("icu_ru_missing_forms",
     "a Russian plural written with English's two branches is caught",
     lambda a: bool(_icu_find(a, 'ru', 'cart.files', 'missing'))),
    ("icu_ru_names_the_forms",
     "and it names few and many, the ones actually absent",
     lambda a: all(c in _icu_find(a, 'ru', 'cart.files', 'missing')[0]['detail']
                   for c in ('few', 'many'))),
    ("icu_ar_missing_forms",
     "Arabic missing zero/two/few/many is caught",
     lambda a: bool(_icu_find(a, 'ar', 'cart.photos', 'missing'))),
    ("icu_severity_follows_source",
     "missing-form severity is high from CLDR, medium from the built-in table",
     lambda a: _icu_find(a, 'ru', 'cart.files', 'missing')[0]['severity']
     == ('high' if (_plural_categories('ru') or (0, 0, ''))[2] == 'CLDR'
         else 'medium')),

    # ── structural, table-free, always blocking ─────────────────────────────
    ("icu_no_other",
     "a plural with no other branch is blocking",
     lambda a: bool(_icu_find(a, 'en', 'cart.no_other', 'no_other'))),
    ("icu_malformed",
     "braces that never close are blocking",
     lambda a: bool(_icu_find(a, 'en', 'cart.broken', 'malformed'))),
    ("icu_bad_keyword",
     "a misspelt category (ohter) is blocking",
     lambda a: bool(_icu_find(a, 'en', 'cart.typo', 'bad_keyword'))),
    ("icu_duplicate_branch",
     "the same branch twice is blocking",
     lambda a: bool(_icu_find(a, 'en', 'cart.dupe', 'duplicate'))),
    ("icu_blocking_exit",
     "those findings make the run fail, not just report",
     lambda a: any('ICU' in f or 'plural' in f.lower() for f in a.failures)),

    # ── graded down, so the check stays usable ──────────────────────────────
    ("icu_dead_branch_low",
     "zero in English is low severity, not a build breaker",
     lambda a: [f['severity'] for f in
                _icu_find(a, 'en', 'cart.zero_dead', 'dead_branch')] == ['low']),
    ("icu_rare_form_low",
     "Italian's million-only many is low severity",
     lambda a: [f['severity'] for f in
                _icu_find(a, 'it', 'cart.items_ok', 'missing_rare')] == ['low']),
    ("icu_flattened",
     "a plural flattened to a plain string in translation is medium",
     lambda a: [f['severity'] for f in
                _icu_find(a, 'ru', 'cart.flat', 'flattened')] == ['medium']),

    # ── negatives: what must NOT be reported ────────────────────────────────
    ("icu_correct_is_silent",
     "a fully covered Russian plural produces nothing at all",
     lambda a: _icu_find(a, 'ru', 'cart.items_ok') == []),
    ("icu_select_names_are_free",
     "male/female in a select are not judged against CLDR categories",
     lambda a: _icu_find(a, 'en', 'cart.who') == []),
    ("icu_apostrophe_safe",
     "l'utente and a quoted brace do not confuse the parser",
     lambda a: not [f for f in a.results['icu_plurals']
                    if f['key'] in ('cart.apos', 'cart.quoted')
                    and f['severity'] == 'high']),

    ("icu_explicit_selector_ok",
     "=1 covers the singular in a two-form language: nothing to report",
     lambda a: _icu_find(a, 'en', 'cart.one_file') == []),
    ("icu_explicit_not_a_free_pass",
     "but =1 does NOT cover Russian one, which also fires at 21 and 31",
     lambda a: bool(_icu_find(a, 'ru', 'cart.one_file', 'missing'))),

    # ── the regression this fix exists for ──────────────────────────────────
    ("icu_placeholder_not_confused",
     "plural prose is no longer compared as if it were variable names",
     lambda a: not [v for v in a.results['mismatched_vars']
                    if v['key'] == 'cart.items_ok']),
    ("icu_placeholder_sees_the_argument",
     "the plural argument itself is what gets compared",
     lambda a: UniversalQualityAnalyzer._extract_placeholders(
         "{count, plural, one{# item} other{# items}}") == {'count'}),
    ("icu_placeholder_nested",
     "placeholders inside branch bodies are compared too",
     lambda a: UniversalQualityAnalyzer._extract_placeholders(
         "{count, plural, one{# item for {name}} other{# for {name}}}")
     == {'count', 'name'}),
    ("icu_placeholder_plain_untouched",
     "a non-ICU string keeps the original behaviour exactly",
     lambda a: UniversalQualityAnalyzer._extract_placeholders(
         "Hello {name}, you have {n} files and %s") == {'name', 'n', '%s'}),
]


# ── Scenario 4: extraction precision ───────────────────────────────────────
# What a parse tree knows and a regex cannot: which t() is a call. Also the
# languages where a straight tree-sitter swap LOST keys during development
# (Vue keeps its <script> as raw text, PHP returned no calls), which is why
# the tree corrects the regex instead of replacing it.
_SELF_TEST_FILES_EXTRACT = {
    "locales/en.json": """{
  "real": {"one": "First", "two": "Second"},
  "vue": {"hello": "Hello", "script": "From the script block"},
  "php": {"key": "Key"},
  "qml": {"label": "Label"},
  "objc": {"title": "Title"},
  "lua": {"name": "Name"}
}""",
    "locales/it.json": """{
  "real": {"one": "Primo", "two": "Secondo"},
  "vue": {"hello": "Ciao", "script": "Dal blocco script"},
  "php": {"key": "Chiave"},
  "qml": {"label": "Etichetta"},
  "objc": {"title": "Titolo"},
  "lua": {"name": "Nome"}
}""",
    "app.js": '''
const good = t("real.one");
const doc = "call it with t('ghost.in_a_string') if you like";
const mid = compute();   // t("ghost.in_a_comment") left from the rewrite
const tpl = t(`real.${which}`);
''',
    "widget.vue": """<template><p>{{ $t("vue.hello") }}</p></template>
<script>
export default {
  mounted() {
    this.$t("vue.script");
    const doc = "t('ghost.in_vue_script')";
  }
}
</script>""",
    "helper.php": """<?php
echo __("php.key");
function warn() { alert("The invoice is already issued"); }
""",
    # Argument shapes that differ from the JS family and were all missed
    # until the containers were read off the grammars: PHP and C# wrap each
    # argument in a node of its own, Kotlin and Swift hide them behind a
    # call_suffix, Dart has no call node at all.
    "Screen.kt": """fun warn() { alert("The warehouse is locked") }""",
    "Screen.cs": """class A { void W() { alert("The customer was not found"); } }""",
    "screen.dart": """void warn() { alert('No table has been selected'); }""",
    # Qt translates through qsTr and nothing else. Without it a .qml file
    # came back empty from BOTH backends, which reads as "no keys here".
    "panel.qml": """import QtQuick 2.0
Text { text: qsTr("qml.label") }""",
    # Objective-C puts an @ in front of the opening quote, so the quote is
    # not the first character after the bracket.
    "View.m": """NSString *a = NSLocalizedString(@"objc.title", nil);""",
    # A language added after the grammar was measured, not before.
    "mod.lua": """local label = t('lua.name')""",
    "extra.js": '''export const x = t("real.two");''',
    # The parsed hardcoded tier. Every string here is planted to be found
    # or planted to be ignored, and which one it is depends on where the
    # SYNTAX puts it, not on how it reads.
    "Panel.jsx": '''
import helper from "./some/module/path.js";
const config = { "notAVisibleLabel": 1 };
export default function Panel({ n }) {
  return (
    <div className="only-a-css-class">
      Plain visible sentence here
      <input placeholder="Type the customer name" />
      <span>Total for {n} nights</span>
      <button>Next &gt;</button>
      <b>{t("real.one")}</b>
    </div>
  );
}
''',
}


def _extract_backend():
    """Which backend actually read the .js files of the last analysis."""
    return _EXTRACTION_BACKENDS.get(".js", "regex")


_SELF_TEST_CASES_EXTRACT = [
    ("extract_real_key",
     "a genuine t() call is found by either backend",
     lambda a: "real.one" in a.all_used_code_keys),
    ("extract_template_prefix",
     "a template literal still yields its dynamic prefix",
     lambda a: "real." in a.all_dynamic_prefixes),
    ("extract_vue_key",
     "Vue keys survive: the tree corrects the regex, it does not replace it",
     lambda a: "vue.hello" in a.all_used_code_keys),
    ("extract_php_key",
     "PHP keys survive for the same reason",
     lambda a: "php.key" in a.all_used_code_keys),
    ("ast_arg_wrapper_php",
     "PHP wraps each argument in a node; the string inside is still text",
     lambda a: any(i['text'].startswith("The invoice is already")
                   for i in a.results['hardcoded'])
               or _extract_backend() == "regex"),
    ("ast_call_suffix_kotlin",
     "Kotlin hides its arguments behind a call_suffix",
     lambda a: any(i['text'].startswith("The warehouse is locked")
                   for i in a.results['hardcoded'])
               or _extract_backend() == "regex"),
    ("ast_arg_list_csharp",
     "C# wraps them too, in an argument_list of arguments",
     lambda a: any(i['text'].startswith("The customer was not found")
                   for i in a.results['hardcoded'])
               or _extract_backend() == "regex"),
    ("ast_dart_has_no_call_node",
     "and Dart has no call node: an identifier and a selector, side by side",
     lambda a: any(i['text'].startswith("No table has been selected")
                   for i in a.results['hardcoded'])
               or _extract_backend() == "regex"),
    ("ast_text_node_found",
     "a JSX text node is user-facing text and is reported",
     lambda a: any(i['text'] == "Plain visible sentence here"
                   for i in a.results['hardcoded'])),
    ("ast_ui_attribute_found",
     "so is the value of a placeholder=",
     lambda a: any(i['text'] == "Type the customer name"
                   for i in a.results['hardcoded'])),
    ("ast_sentence_is_not_split",
     "a sentence broken by an interpolation is reported whole, once",
     lambda a: any(i['text'] == "Total for {…} nights"
                   for i in a.results['hardcoded'])
               or _extract_backend() == "regex"),
    ("ast_entity_is_part_of_the_label",
     "an HTML entity belongs to the text beside it: Next &gt; is two words",
     lambda a: any(i['text'] == "Next >" for i in a.results['hardcoded'])
               or _extract_backend() == "regex"),
    ("ast_import_path_ignored",
     "an import path is structure, not text",
     lambda a: not any("some/module/path" in i['text']
                       for i in a.results['hardcoded'])),
    ("ast_object_key_ignored",
     "and neither is the key half of an object entry",
     lambda a: not any(i['text'] == "notAVisibleLabel"
                       for i in a.results['hardcoded'])),
    ("ast_css_class_ignored",
     "className is not a UI attribute, whatever it contains",
     lambda a: not any(i['text'] == "only-a-css-class"
                       for i in a.results['hardcoded'])),
    ("ast_translated_call_ignored",
     "and a string already going through t() is not a finding",
     lambda a: not any(i['text'] == "real.one"
                       for i in a.results['hardcoded'])),
    ("ast_tier_is_labelled",
     "the parsed tier says so, rather than borrowing the hint tier's name",
     lambda a: (any(i.get('context') == 'ast_ui'
                    for i in a.results['hardcoded'])
                or _extract_backend() == "regex")),
    ("extract_objc_prefixed_string",
     "an Objective-C @\"key\" is read despite the prefix before the quote",
     lambda a: "objc.title" in a.all_used_code_keys),
    ("extract_lua_key",
     "and a language added later is read like any other",
     lambda a: "lua.name" in a.all_used_code_keys),
    ("extract_qml_key",
     "qsTr is how Qt translates, so a .qml key is found at all",
     lambda a: "qml.label" in a.all_used_code_keys),
    ("extract_sfc_script_key",
     "a key inside a single-file component's <script> is found",
     lambda a: "vue.script" in a.all_used_code_keys),
    ("extract_sfc_script_string",
     "and a call written inside a STRING in that script is not a use",
     lambda a: ("ghost.in_vue_script" not in a.all_used_code_keys)
               or _extract_backend() == "regex"),
    ("extract_second_file",
     "every non-Python file is read, not just the first",
     lambda a: "real.two" in a.all_used_code_keys),
    ("extract_string_is_not_a_call",
     "t() written inside a string counts only for the regex backend",
     lambda a: ("ghost.in_a_string" in a.all_used_code_keys)
     == (_extract_backend() == "regex")),
    ("extract_midline_comment",
     "t() in a mid-line comment likewise: the regex only strips whole lines",
     lambda a: ("ghost.in_a_comment" in a.all_used_code_keys)
     == (_extract_backend() == "regex")),
    ("extract_no_false_unresolved",
     "and with a tree those two never raise a blocking unresolved-key finding",
     lambda a: (not [k for k in a.results['unresolved_code_keys']
                     if k.startswith('ghost.')])
     or _extract_backend() == "regex"),
]


def _analyse_fixture(files: dict):
    """Write *files* to a temp project, analyse it, return the analyzer."""
    import codecs
    import contextlib
    import io
    import tempfile
    global PROJECT_ROOT, _project_config_cache

    with tempfile.TemporaryDirectory(prefix="i18nqa_selftest_") as td:
        root = Path(td)
        for rel, body in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            text = body
            if rel == ".i18n-quality.json":
                # Written WITH a byte-order mark on purpose: Notepad and
                # Windows PowerShell add one by default, and it used to make
                # the whole file unreadable without a word of complaint.
                path.write_bytes(codecs.BOM_UTF8 + text.encode("utf-8"))
                continue
            if rel == "app.py":
                text = text.replace(
                    'ui.setText("Internal debug marker")',
                    'ui.setText("Internal debug marker")  # i18n-ignore')
            path.write_text(text, encoding="utf-8")

        saved_root, saved_cfg = PROJECT_ROOT, _project_config_cache
        PROJECT_ROOT, _project_config_cache = root, None
        _dir_config_cache.clear()
        analyzer = UniversalQualityAnalyzer(report_path=root / "report.md")
        try:
            # The synthetic project is SUPPOSED to fail: run_all_tests exits
            # non-zero when it finds blocking problems, and finding them is
            # the point. Its console output is swallowed too — what matters
            # here is the case table below, not another copy of the run.
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    analyzer.run_all_tests()
                except SystemExit:
                    pass
            # Snapshot what the config-driven helpers RESOLVED TO while the
            # synthetic root was active. Reading them from a predicate would
            # read the real project again — the globals are restored below.
            analyzer.probe = {
                "tech_words": _tech_words(),
                "ui_funcs": _ui_funcs(),
                "budgets": _project_budgets(),
            }
        finally:
            PROJECT_ROOT, _project_config_cache = saved_root, saved_cfg
            _dir_config_cache.clear()
    return analyzer


def _check_cases(analyzer, cases, failed: list) -> None:
    for case_id, description, predicate in cases:
        try:
            ok = bool(predicate(analyzer))
        except Exception as exc:                       # a broken case is a failure
            ok = False
            description = f"{description} - {exc!r}"
        print(f"  [{'OK  ' if ok else 'FAIL'}] {case_id:26} {description}")
        if not ok:
            failed.append(case_id)


def _run_self_test() -> int:
    """Analyse each synthetic project and assert every case. Exit code.

    Two scenarios, because one layout only ever proves itself: a
    JSON/Python project, and a JavaScript one whose dictionaries live in a
    module under src/. The second exists because a real project reported
    "no i18n dictionaries found" while its src/i18n/translations.js sat
    right there.
    """
    scenarios = [
        ("json + python", _SELF_TEST_FILES, _SELF_TEST_CASES),
        ("js module", _SELF_TEST_FILES_JS, _SELF_TEST_CASES_JS),
    ]
    print(chr(10) + "=" * 80)
    print(L("st_header"))
    failed: List[str] = []
    total = 0
    for scenario, files, cases in scenarios:
        analyzer = _analyse_fixture(files)
        print("  -- " + scenario)
        total += len(cases)
        _check_cases(analyzer, cases, failed)

    # The ICU scenario runs TWICE: once on whatever plural rules the machine
    # can supply (real CLDR when babel is installed), once forced onto the
    # built-in table. Otherwise half the plural engine ships unexercised, and
    # which half is decided by a package that may or may not be present.
    # Same reasoning for the extraction backend: the JS scenario is
    # replayed under both, and its findings must come out IDENTICAL — a
    # backend that quietly moved a line number or dropped a key would keep
    # every boolean case green while changing what the tool reports. The
    # precision scenario is where the two are ALLOWED to differ, and each
    # case there says which way.
    global _FORCE_REGEX_EXTRACTION
    js_shots = []
    for forced in (False, True):
        _FORCE_REGEX_EXTRACTION = forced
        _ts_parser_cache.clear()
        analyzer = _analyse_fixture(_SELF_TEST_FILES_EXTRACT)
        print('  -- extraction (' + _extract_backend() + ')')
        total += len(_SELF_TEST_CASES_EXTRACT)
        _check_cases(analyzer, _SELF_TEST_CASES_EXTRACT, failed)
        js = _analyse_fixture(_SELF_TEST_FILES_JS)
        js_shots.append(sorted(
            (i['file'], i['line'], i.get('col'), i['text'], i['severity'])
            for i in js.results['hardcoded']))
        js_shots[-1] += sorted(js.all_used_code_keys)
    _FORCE_REGEX_EXTRACTION = False
    total += 1
    _check_cases(_analyse_fixture(_SELF_TEST_FILES_JS), [
        ("extract_backends_agree",
         "the JS scenario analyses identically under both backends",
         lambda _a: js_shots[0] == js_shots[1]),
    ], failed)

    global _FORCE_BUILTIN_PLURALS
    for forced in (False, True):
        _FORCE_BUILTIN_PLURALS = forced
        probe = _plural_categories('ru')
        print('  -- icu plurals (' + (probe[2] if probe else 'no rules') + ')')
        analyzer = _analyse_fixture(_SELF_TEST_FILES_ICU)
        total += len(_SELF_TEST_CASES_ICU)
        _check_cases(analyzer, _SELF_TEST_CASES_ICU, failed)
    _FORCE_BUILTIN_PLURALS = False
    print("=" * 80)
    if failed:
        print(L("st_failed", n=len(failed), ids=", ".join(failed)))
        return 1
    print(L("st_passed", n=total))
    return 0


if __name__ == '__main__':
    import argparse
    _ap = argparse.ArgumentParser(
        description="Universal i18n quality analysis (multi-format)")
    _ap.add_argument("--root", type=Path, default=None,
                     help="project root to scan (default: this repo's root)")
    _ap.add_argument("--report", type=Path, default=None,
                     help="output path for the Markdown report "
                          "(default: tests/UNIVERSAL_QUALITY_REPORT.md)")
    _ap.add_argument("--self-test", action="store_true",
                     help="analyse a synthetic project with planted problems "
                          "and assert every check still catches them, then "
                          "exit (nonzero on failure)")
    _ap.add_argument("--vocab-help", action="store_true",
                     help=f"explain {PROJECT_VOCAB_FILE}, the optional file in "
                          "the project root that adds brand/product names to "
                          "the language-neutral vocabulary, then exit")
    _ap.add_argument("--lang", choices=TOOL_LANGS, default=None,
                     help="tool output language (default: auto-detected "
                          "from the system locale; extend by dropping a "
                          "qa_lang_<code>.json pack next to this script)")
    _ap.add_argument("--export-lang-template", metavar="CODE", default=None,
                     help="write qa_lang_<CODE>.json with every message in "
                          "English as a translation starting point, then exit")
    _args = _ap.parse_args()
    if _args.lang:
        TOOL_LANG = _args.lang
    if _args.self_test:
        raise SystemExit(_run_self_test())
    if _args.vocab_help:
        print(
              PROJECT_VOCAB_FILE + " — optional, in the scanned project root (or --root). Written\n"
              "for you the first time it is missing, with every value empty: it\n"
              "changes nothing until you fill something in, and deleting it is fine.\n"
              "\n"
              "Everything project-specific lives here, so the analyzer itself stays\n"
              "project-agnostic:\n"
              "\n"
              "  tech_words               brand, vendor and engine names, so the\n"
              "                           mixed-language check stops reading them as\n"
              "                           the wrong language\n"
              "  ui_functions             house widget names whose string arguments\n"
              "                           reach the screen, so they are judged at\n"
              "                           high severity\n"
              "  exclude_dirs             directories to skip on top of caches,\n"
              "                           virtualenvs and build output — vendored\n"
              "                           copies, dev-only scripts, old sources\n"
              "  exempt                   which noise suppressions are on (exception\n"
              "                           messages, regular expressions, User-Agent\n"
              "                           strings). Whatever is suppressed is counted\n"
              "                           and named in the report either way\n"
              "  translation_kwargs       keyword names that carry the key, as in\n"
              "                           t(key='nav.home')\n"
              "  extra_translation_calls  your own translation call names, and\n"
              "                           factories whose RESULT takes the key —\n"
              "                           useTranslations()('nav.home')\n"
              "  budgets                  per-severity ceilings; declaring one makes\n"
              "                           exceeding it blocking, which is how a count\n"
              "                           of hundreds ever comes down\n"
              "\n"
              "  { \"tech_words\": [\"acme\", \"postgres\"], \"exclude_dirs\": [\"vendor\"] }\n"
              "\n"
              "Present but unreadable is said out loud, not swallowed."
              )
        raise SystemExit(0)
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
    UniversalQualityAnalyzer(report_path=_args.report).run_all_tests()
