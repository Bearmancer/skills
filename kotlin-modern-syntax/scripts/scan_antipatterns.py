#!/usr/bin/env python3
"""Scan Kotlin sources and build files for superseded patterns.

Rules come from the Kotlin 2.3.0 - 2.5.0-Beta2 release notes, compatibility guides and
changelogs (plus a few `baseline` modernizations). Heuristic, regex-based: it reports likely
antipatterns with file:line, a replacement, and the version where the old form changed state.

Usage:
  scan_antipatterns.py PATH [PATH...] [--target 2.4.21] [--json] [--min-severity warn]
                       [--include-experimental] [--list-rules]

Severity:
  error      the old form does not compile (or the build fails) on the target version
  warn       deprecated, still compiles, scheduled to break
  modernize  still valid, superseded by a stable replacement
  info       needs human judgement (library vs app code, opt-in required, ...)

Rules that only bite in a version newer than --target are reported as `info` with an UPCOMING
prefix, so code written today does not need migrating again.

Rules whose replacement is experimental (tier E) are only reported with --include-experimental,
because writing them unasked would force compiler flags on the project.

Exit status: 1 if any `error` finding, else 0 (use --strict to fail on `warn` too).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

SEVERITY_ORDER = {"info": 0, "modernize": 1, "warn": 2, "error": 3}
KT = {".kt", ".kts"}
BUILD = {".kts", ".gradle"}
PROPS = {".properties"}
TOML = {".toml"}
XML = {".xml"}
SKIP_DIRS = {".git", ".gradle", "build", "node_modules", ".idea", "out", "target", ".kotlin"}


def parse_version(text: str) -> tuple[int, int, int]:
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not m:
        raise ValueError(f"bad version: {text!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


@dataclass
class Rule:
    id: str
    severity: str            # error | warn | modernize | info
    since: str               # version where the old form became deprecated/dead/superseded
    exts: set[str]
    pattern: str
    message: str
    fix: str
    source: str = "notes"    # notes | changelog | baseline
    experimental: bool = False
    flags: int = re.MULTILINE
    # optional post-filter: (match, full_text) -> bool (True keeps the finding)
    keep: Optional[Callable[[re.Match, str], bool]] = None
    rx: re.Pattern = field(init=False)

    def __post_init__(self) -> None:
        self.rx = re.compile(self.pattern, self.flags)


def _prev_lines(text: str, pos: int, n: int = 3) -> str:
    start = text.rfind("\n", 0, pos)
    chunk_start = pos
    for _ in range(n):
        chunk_start = text.rfind("\n", 0, max(chunk_start - 1, 0))
        if chunk_start == -1:
            chunk_start = 0
            break
    return text[chunk_start:pos]


def _not_annotated_jvminline(m: re.Match, text: str) -> bool:
    line_start = text.rfind("\n", 0, m.start()) + 1
    same_line = text[line_start:m.end()]
    return "@JvmInline" not in same_line and "@JvmInline" not in _prev_lines(text, m.start(), 2)


def _not_kdoc_or_comment(m: re.Match, text: str) -> bool:
    line_start = text.rfind("\n", 0, m.start()) + 1
    prefix = text[line_start:m.start()].lstrip()
    return not prefix.startswith(("//", "*", "/*"))


RULES: list[Rule] = [
    # ---------------- Language ----------------
    Rule("context-receivers", "error", "2.3.20", KT,
         r"\bcontext\(\s*[A-Z][\w.<>?]*(?:\s*,\s*[A-Z][\w.<>?]*)*\s*\)\s*(?:(?:public|private|internal|protected|inline|suspend|operator|override|open|abstract|final|data|sealed|const|tailrec|infix)\s+)*(?:fun|val|var|class|interface|object)\b",
         "Context receivers `context(Type)` are no longer supported.",
         "Use named context parameters: `context(logger: Logger)` and access `logger.` explicitly (stable 2.4.0).",
         flags=re.MULTILINE | re.DOTALL),
    Rule("backing-property", "modernize", "2.4.0", KT,
         r"private\s+val\s+_(\w+)\s*(?::[^=\n]+)?=\s*[^\n]*\n\s*(?:public\s+)?val\s+\1\s*:[^\n=]*?(?:\bget\(\)\s*=\s*_\1\b|=\s*_\1\b(?:\.as\w+\(\))?)[ \t]*(?://[^\n]*)?$",
         "Backing-property boilerplate (`_x` private mutable + public read-only `x`).",
         "Explicit backing field (stable 2.4.0):\n    val x: StateFlow<T>\n        field = MutableStateFlow(..)"),
    Rule("return-in-expression-body", "error", "2.4.0", KT,
         r"^[^\n/]*\bfun\b[^\n=]*\)\s*=[^\n]*\breturn\b(?!@)",
         "`return` inside an expression body without a declared return type (error since 2.4.0).",
         "Declare the return type (`fun f(): T = ... return ...`) or drop the `return`.",
         keep=_not_kdoc_or_comment),
    Rule("javaclass-reference", "warn", "2.4.0", KT,
         r"::javaClass\b",
         "Property reference to `javaClass` is deprecated.",
         "Use `x.javaClass` for the runtime class or `X::class.java` for a class literal."),
    Rule("suppress-deprecation-file", "info", "2.4.0", KT,
         r"@file:Suppress\([^)]*\"DEPRECATION\"",
         "File-wide DEPRECATION suppression (often added to dodge import warnings, which 2.4.0 no longer reports).",
         "Remove it and migrate the deprecated calls; import the symbol explicitly."),
    Rule("value-class-no-jvminline", "warn", "2.5.20", KT,
         r"^[ \t]*(?:(?:public|internal|private)\s+)?value\s+class\s+\w+\s*(?:<[^>(]*>)?\s*\(\s*(?:(?:private|internal|public)\s+)?(?:val|var)\s+\w+\s*:[^,)]+\)",
         "Single-field `value class` without `@JvmInline` (plain `value class` stops meaning inline; warning planned 2.5.20).",
         "`@JvmInline value class Name(val raw: T)`",
         keep=_not_annotated_jvminline),
    Rule("builder-inference", "warn", "2.5.0", KT,
         r"@BuilderInference\b",
         "`@BuilderInference` is deprecated (changelog KT-52400).",
         "Rely on regular type inference; follow the compiler's deprecation hint.",
         source="changelog"),
    Rule("array-literal-outside-annotation", "error", "2.4.0", KT,
         r"(?<![@\w)\]])\s*=\s*\[[^\]\n]*\]\s*$",
         "Bracket literal assigned outside an annotation (array literals outside annotations are errors since 2.4.0; `[..]` collection literals need `-Xcollection-literals`).",
         "Use `arrayOf(..)` / `listOf(..)` (collection literals are experimental).",
         keep=lambda m, t: "@" not in t[t.rfind("\n", 0, m.start()) + 1:m.start()] and "-Xcollection-literals" not in t),
    Rule("when-values-entries", "modernize", "1.9", KT,
         r"\b[A-Z]\w*\.values\(\)|\benumValues<",
         "`Enum.values()` / `enumValues<T>()` are superseded.",
         "`Enum.entries` / `enumEntries<T>()`.",
         source="baseline"),

    # ---------------- Standard library ----------------
    Rule("readline", "warn", "2.4.0", KT,
         r"(?<![.\w])readLine\(\)",
         "`kotlin.io.readLine()` is deprecated.",
         "`readln()` instead of `readLine()!!`; `readlnOrNull()` instead of `readLine()`."),
    Rule("char-to-number", "error", "2.3.0", KT,
         r"'(?:[^'\\]|\\.)'\s*\.to(?:Int|Long|Byte|Short|Double|Float)\(\)",
         "`Char.toX()` numeric conversion is an error since 2.3.0.",
         "`c.code` for the code, `c.digitToInt()` / `digitToIntOrNull()` for digit values, `Char(code)` for the reverse."),
    Rule("char-to-int-var", "info", "2.3.0", KT,
         r"\b(?:ch|char|c|chr|letter|symbol)\.to(?:Int|Long|Byte|Short)\(\)",
         "Possible `Char.toInt()`-style conversion (error since 2.3.0 when the receiver is a Char).",
         "`.code`, `.digitToInt()`, `Char(code)`."),
    Rule("number-to-char", "error", "2.3.0", KT,
         r"\.to(?:Double|Float|Long|Short|Byte)\(\)\.toChar\(\)",
         "`Number.toChar()` (non-Int) is an error since 2.3.0.",
         "`Char(n.toInt())` or `n.toInt().toChar()`."),
    Rule("kotlin-io-tempfile", "error", "2.3.0", KT,
         r"\bimport\s+kotlin\.io\.createTemp(?:File|Directory)\b|\bkotlin\.io\.createTemp(?:File|Directory)\(",
         "`kotlin.io.createTempFile/createTempDirectory` are errors since 2.3.0.",
         "`kotlin.io.path.createTempFile` / `createTempDirectory` (returns `Path`)."),
    Rule("string-subsequence-named", "error", "2.3.0", KT,
         r"\.subSequence\(\s*start\s*=",
         "`String.subSequence(start, end)` is an error since 2.3.0.",
         "`subSequence(startIndex = .., endIndex = ..)`."),
    Rule("abstract-coroutine-context-key", "warn", "2.4.0", KT,
         r"\bAbstractCoroutineContextKey\b|\bgetPolymorphicElement\b|\bminusPolymorphicKey\b",
         "`AbstractCoroutineContextKey` and polymorphic key helpers are deprecated.",
         "Use plain `CoroutineContext.Key` keys."),
    Rule("uuid-parse-try-catch", "modernize", "2.4.0", KT,
         r"try\s*\{[^{}]*\bUuid\.parse(?:HexDash|Hex)?\([^{}]*\}\s*catch",
         "try/catch around `Uuid.parse`.",
         "`Uuid.parseOrNull(..)` / `parseHexDashOrNull` / `parseHexOrNull` (stable 2.4.0).",
         flags=re.MULTILINE | re.DOTALL),
    Rule("java-uuid", "info", "2.4.0", KT,
         r"\bUUID\.randomUUID\(\)",
         "`java.util.UUID.randomUUID()`; in common/multiplatform code prefer the stdlib type.",
         "`kotlin.uuid.Uuid.random()` (stable 2.4.0). Keep `java.util.UUID` only where a Java API requires it."),
    Rule("sorted-equality", "modernize", "2.4.0", KT,
         r"(\b\w+(?:\.\w+)*)\s*==\s*\1\.sorted(?:Descending)?\(\)",
         "Equality-with-sorted-copy used to test sort order.",
         "`xs.isSorted()` / `isSortedDescending()` / `isSortedBy {}` (stable 2.4.0)."),
    Rule("sorted-zipwithnext", "modernize", "2.4.0", KT,
         r"zipWithNext\(\)\s*\.all\s*\{[^}]*<=?[^}]*\}",
         "Hand-rolled sorted check with `zipWithNext().all { a <= b }`.",
         "`xs.isSorted()` / `isSortedBy {}` (stable 2.4.0).",
         flags=re.MULTILINE | re.DOTALL),
    Rule("distinct-size-check", "modernize", "2.4.20", KT,
         r"\.(?:distinct|toSet)\(\)\.size\s*(?:==|!=|<=|>)\s*(?:\w+\.)?size\b|\.distinct\(\)\.size\s*(?:<=|<)\s*[12]\b",
         "Uniqueness/equality check via `distinct().size`.",
         "`allDistinct()` / `allEqual()` (experimental 2.4.20, `@OptIn(ExperimentalStdlibApi::class)`).",
         experimental=True),
    Rule("test-eager-message", "modernize", "2.4.20", KT,
         r"\bassert(?:True|False|Equals|NotEquals|Null|Same|NotSame|Contains|ContentEquals)\([^()\n]*(?:\([^()\n]*\)[^()\n]*)*,\s*\"[^\"\n]*\$[^\"\n]*\"\s*\)",
         "`kotlin.test` assertion with an eagerly built message string.",
         "Lazy message: `assertEquals(a, b) { \"msg $x\" }` (experimental 2.4.20, `@OptIn(ExperimentalKotlinTestApi::class)`).",
         experimental=True),
    Rule("legacy-case-api", "modernize", "1.5", KT,
         r"\.(?:toUpperCase|toLowerCase|capitalize|decapitalize)\(\)|\.(?:appendln)\(|\.sumBy(?:Double)?\s*[({]",
         "Removed/deprecated text and collection helpers.",
         "`uppercase()` / `lowercase()`, `replaceFirstChar { it.titlecase() }`, `appendLine`, `sumOf`.",
         source="baseline"),
    Rule("jvmoverloads", "info", "2.5.0", KT,
         r"@JvmOverloads\b",
         "`@JvmOverloads`: fine for app code, but in a published library prefer version-aware overloads.",
         "`@IntroducedAt(\"x.y\")` on newly added optional parameters (stable 2.5.0-Beta2; experimental in 2.4.0).",
         experimental=True),

    # ---------------- Build and tooling ----------------
    Rule("kotlinoptions", "error", "2.3.0", BUILD,
         r"\bkotlinOptions\b",
         "`kotlinOptions {}` DSL: all properties are errors since 2.3.0.",
         "`kotlin { compilerOptions { jvmTarget.set(JvmTarget.JVM_21); freeCompilerArgs.add(..) } }`."),
    Rule("testapi", "warn", "2.3.0", BUILD,
         r"\btestApi\s*\(|\bcommon(?:Test)\b[^\n]*\bapi\s*\(",
         "`testApi` configuration is deprecated.",
         "`testImplementation(..)` (or `implementation` in KMP test source sets)."),
    Rule("androidtarget", "warn", "2.3.0", BUILD,
         r"\bandroidTarget\s*[({]",
         "`androidTarget` is deprecated; configuration error with AGP 9.0.0+.",
         "Google's `com.android.kotlin.multiplatform.library` plugin and `android { }`."),
    Rule("kotlin-android-plugin", "info", "2.3.0", BUILD,
         r"kotlin\(\s*\"android\"\s*\)|org\.jetbrains\.kotlin\.android\b",
         "`kotlin-android` plugin: unnecessary and an error with AGP 9.0.0+ (built-in Kotlin).",
         "Remove it when on AGP 9+; AGP provides Kotlin support."),
    Rule("kotlinartifacts", "error", "2.4.0", BUILD,
         r"\bkotlinArtifacts\b",
         "`kotlinArtifacts` API was removed in 2.4.0.",
         "Use the binaries DSL (`binaries.framework { }`) to build native artifacts."),
    Rule("target-hierarchy", "error", "2.4.0", BUILD,
         r"\btargetHierarchy\b",
         "`targetHierarchy` was removed in 2.4.0.",
         "Use the default hierarchy template (applied automatically) or the current hierarchy DSL."),
    Rule("with-java", "error", "2.5.0", BUILD,
         r"\bwithJava\(\)",
         "`withJava()` deprecation is raised to error in 2.5.0-Beta2 (changelog KT-89878).",
         "Follow the compiler's deprecation hint.",
         source="changelog"),
    Rule("js-compiler-type", "warn", "2.4.0", BUILD,
         r"\bjs\(\s*(?:IR|LEGACY|BOTH)\b|\bKotlinJsCompilerType\b",
         "Legacy Kotlin/JS compiler type selection was removed/deprecated in 2.4.0.",
         "`js { .. }` with no compiler type argument."),
    Rule("compose-legacy-flags", "error", "2.4.0", BUILD,
         r"\b(?:generateFunctionKeyMetaClasses|enableIntrinsicRemember|enableNonSkippingGroupOptimization|enableStrongSkippingMode)\b|\bstabilityConfigurationFile\b(?!s)|ComposeFeatureFlag\.(?:StrongSkipping|IntrinsicRemember)\b",
         "Obsolete Compose compiler Gradle plugin options are errors since 2.4.0.",
         "`featureFlags` and `stabilityConfigurationFiles`; strong skipping/intrinsic remember are default-on."),
    Rule("abi-legacy-tasks", "warn", "2.3.20", BUILD | PROPS,
         r"\b(?:check|update|dump)LegacyAbi\b|\blegacyDump\s*\{",
         "Legacy ABI-validation task names / DSL.",
         "`checkKotlinAbi`, `updateKotlinAbi`, `internalDumpKotlinAbi`; configure reports directly in `abiValidation {}`."),
    Rule("native-cachekind", "warn", "2.3.20", PROPS | BUILD,
         r"\bkotlin\.native\.cacheKind\b",
         "`kotlin.native.cacheKind` property is deprecated.",
         "Remove it; if the cache truly must be disabled use `disableNativeCache(version = .., reason = .., issue = ..)` in `binaries {}`."),
    Rule("removed-gradle-properties", "warn", "2.4.0",
         PROPS,
         r"^\s*kotlin\.(?:mpp\.enableKotlinToolingMetadataArtifact|publishJvmEnvironmentAttribute|kmp\.isolated-projects\.support|mpp\.import\.enableKgpDependencyResolution|compiler\.preciseCompilationResultsBackup|compiler\.keepIncrementalCompilationCachesInMemory|mpp\.resourcesResolutionStrategy)\s*=",
         "Gradle property removed or deprecated (2.3.0 to 2.4.0).",
         "Delete the property; the behavior is now fixed."),
    Rule("language-version-1-8", "error", "2.3.0", BUILD | TOML | PROPS,
         r"-language-version[= ]1\.[0-8]\b|KOTLIN_1_[0-8]\b|(?:languageVersion|apiVersion)\s*(?:=|\.set\()[^\n]*\"1\.[0-8]\"",
         "Language version 1.8 and older is unsupported since 2.3.0.",
         "Use language version 2.0 or newer (default = the compiler's own)."),
    Rule("language-version-1-9", "error", "2.4.0", BUILD | TOML | PROPS,
         r"-language-version[= ]1\.9\b|KOTLIN_1_9\b|(?:languageVersion|apiVersion)\s*(?:=|\.set\()[^\n]*\"1\.9\"",
         "Language version 1.9 is unsupported on JVM since 2.4.0 (non-JVM since 2.3.0); K1 is gone.",
         "Use language version 2.0 or newer (default = the compiler's own)."),
    Rule("language-version-2-1", "warn", "2.4.0", BUILD | TOML | PROPS,
         r"KOTLIN_2_1\b|-language-version[= ]2\.1\b",
         "Language version 2.1 is deprecated (changelog KT-85062, 2.4.0).",
         "Drop the pin and use the default language version.",
         source="changelog"),
    Rule("language-version-2-2", "warn", "2.5.0", BUILD | TOML | PROPS,
         r"KOTLIN_2_2\b|-language-version[= ]2\.2\b",
         "Language version 2.2 is deprecated (changelog KT-86131, 2.5.0-Beta1).",
         "Drop the pin and use the default language version.",
         source="changelog"),
    Rule("maven-no-extensions", "modernize", "2.3.20", XML,
         r"<artifactId>kotlin-maven-plugin</artifactId>(?:(?!</plugin>).)*</plugin>",
         "`kotlin-maven-plugin` without `<extensions>true</extensions>` (hand-maintained source roots and stdlib dependency).",
         "Add `<extensions>true</extensions>` to the plugin (stable 2.3.20); drop the manual `kotlin-stdlib` dependency and source roots.",
         flags=re.MULTILINE | re.DOTALL,
         keep=lambda m, t: "<extensions>true</extensions>" not in m.group(0)),
    Rule("maven-jpa-allopen", "info", "2.3.20", XML,
         r"<artifactId>kotlin-maven-allopen</artifactId>",
         "Explicit `kotlin-maven-allopen`: with `kotlin-maven-noarg` JPA setups it is now implied.",
         "Remove it from the plugin's `<dependencies>` if it was only there for JPA."),
    Rule("kotlin-script-mojo", "error", "2.4.0", XML,
         r"KotlinScriptMojo|kotlin-maven-plugin[^<]*</artifactId>\s*(?:(?!</plugin>).)*<goal>script</goal>",
         "Kotlin script execution through the Maven plugin was removed in 2.4.0.",
         "Run scripts outside the Maven Kotlin plugin.",
         flags=re.MULTILINE | re.DOTALL),

    # ---------------- JS / Wasm ----------------
    Rule("js-default-hack", "modernize", "2.3.0", KT,
         r"@JsName\(\s*\"default \"\s*\)",
         "`@JsName(\"default \")` trailing-space hack for default exports.",
         "`@JsExport.Default` (stable 2.3.0)."),
    Rule("wasm-exports", "warn", "2.4.20", KT | {".js", ".mjs", ".ts"},
         r"\bwasmExports\.(?!memory\b)\w+",
         "Generated `wasmExports` JS API is deprecated (only `wasmExports.memory` is temporarily allowed).",
         "Use `kotlin.wasm.unsafe.wasmMemory` for `WebAssembly.Memory`."),
]


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    severity: str
    since: str
    source: str
    message: str
    fix: str
    snippet: str


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def iter_files(paths: Iterable[str]) -> Iterable[Path]:
    exts = KT | BUILD | PROPS | TOML | XML | {".js", ".mjs", ".ts"}
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix in exts and not (set(f.parts) & SKIP_DIRS):
                    yield f
        else:
            print(f"warning: {raw} not found", file=sys.stderr)


def effective_exts(path: Path) -> set[str]:
    name = path.name
    if name.endswith(".gradle.kts"):
        return {".kts", ".gradle"}
    if name == "pom.xml":
        return {".xml"}
    if name == "gradle.properties":
        return {".properties"}
    return {path.suffix}


def scan_file(path: Path, rules: list[Rule], target: Optional[tuple[int, int, int]],
              include_experimental: bool) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"warning: cannot read {path}: {e}", file=sys.stderr)
        return []
    exts = effective_exts(path)
    lines = text.splitlines()
    out: list[Finding] = []
    for rule in rules:
        if not (rule.exts & exts):
            continue
        if rule.experimental and not include_experimental:
            continue
        upcoming = target is not None and parse_version(rule.since) > target
        for m in rule.rx.finditer(text):
            if rule.keep and not rule.keep(m, text):
                continue
            ln = line_of(text, m.start() + (len(m.group(0)) - len(m.group(0).lstrip("\n\t "))))
            snippet = lines[ln - 1].strip() if 0 < ln <= len(lines) else ""
            # skip commented-out lines
            if snippet.startswith(("//", "*", "/*", "#", "<!--")):
                continue
            sev, msg = rule.severity, rule.message
            if upcoming:
                # Not a problem on the target yet, but writing it now guarantees a later migration.
                sev = "info"
                msg = f"UPCOMING (becomes {rule.severity} in {rule.since}): {msg}"
            out.append(Finding(str(path), ln, rule.id, sev, rule.since,
                               rule.source, msg, rule.fix, snippet[:160]))
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="files or directories")
    ap.add_argument("--target", default=None,
                    help="Kotlin version of the project (e.g. 2.4.21); rules that only bite in a later "
                         "version are reported as info 'UPCOMING' instead of error/warn")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--min-severity", default="modernize", choices=list(SEVERITY_ORDER),
                    help="lowest severity to report (default: modernize)")
    ap.add_argument("--include-experimental", action="store_true",
                    help="also report rules whose replacement needs an experimental opt-in")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warn as well as error")
    ap.add_argument("--list-rules", action="store_true", help="print the rule table and exit")
    args = ap.parse_args(argv)

    if args.list_rules:
        for r in RULES:
            flag = " [E]" if r.experimental else ""
            print(f"{r.id:34} {r.severity:9} since {r.since:7} {r.source:9}{flag}  {r.message}")
        return 0
    if not args.paths:
        ap.error("no paths given")

    target = parse_version(args.target) if args.target else None
    floor = SEVERITY_ORDER[args.min_severity]
    findings: list[Finding] = []
    for f in iter_files(args.paths):
        findings += scan_file(f, RULES, target, args.include_experimental)
    findings = [f for f in findings if SEVERITY_ORDER[f.severity] >= floor]
    findings.sort(key=lambda f: (-SEVERITY_ORDER[f.severity], f.file, f.line))

    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        for f in findings:
            tag = "" if f.source == "notes" else f" [{f.source}]"
            print(f"{f.file}:{f.line}: {f.severity.upper()} {f.rule} (since {f.since}){tag}")
            print(f"    {f.snippet}")
            print(f"    {f.message}")
            print(f"    -> {f.fix.replace(chr(10), chr(10) + '       ')}")
        counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITY_ORDER}
        summary = ", ".join(f"{counts[s]} {s}" for s in ("error", "warn", "modernize", "info"))
        tgt = f" (target {args.target})" if args.target else ""
        print(f"\n{len(findings)} finding(s){tgt}: {summary}")

    worst = max((SEVERITY_ORDER[f.severity] for f in findings), default=-1)
    if worst >= SEVERITY_ORDER["error"] or (args.strict and worst >= SEVERITY_ORDER["warn"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
