---
name: kotlin-modern-syntax
description: Enforces modern Kotlin (2.3 to 2.5) and bans superseded patterns, built from the official 2.3.0 to 2.5.0-Beta2 release notes, changelogs and compatibility guides. Use this skill whenever writing, reviewing, refactoring, migrating or explaining ANY Kotlin code or Kotlin build config (.kt, .kts, build.gradle.kts, libs.versions.toml, gradle.properties, pom.xml, Compose or KMP code), even when the user never mentions "modern", "idiomatic" or "migration". Also use it for "is this deprecated", "what's the new way to do X in Kotlin", Kotlin upgrade questions, and code review of Kotlin pull requests. It carries an antipattern catalog (old pattern, modern replacement, version and stability) and a scanner script, so Kotlin you produce never uses context receivers, kotlinOptions, readLine, backing-property boilerplate, Char.toInt and similar leftovers.
---

# Modern Kotlin, enforced

Model knowledge of Kotlin skews old: most training text predates 2.3. This skill exists to
override that skew. The rule is simple: **never emit a superseded pattern when a modern
replacement exists for the project's Kotlin version.** If the replacement needs a newer
compiler than the project has, say so once (one line, with the version) and still write the
modern form, rather than silently falling back to the old idiom.

Source of truth: the Kotlin release notes for 2.3.0, 2.3.20, 2.4.0, 2.4.20 and 2.5.0-Beta2,
the 2.3.x and 2.4.x compatibility guides, and the changelogs (collected 2026-11-07; as of that date the latest
stable is 2.4.21, the latest preview 2.5.0-Beta2, and 2.5.0 is planned for Dec 2026). Everything below traces to those unless flagged
`[baseline]` (long-established modernizations outside the supplied notes) or `[changelog]`
(only seen as a changelog line, details unverified).

## Workflow

1. **Find the target version.** Check, in order: `libs.versions.toml` (`kotlin = "..."`),
   `kotlin("jvm") version`, the `org.jetbrains.kotlin.*` plugin versions, `<kotlin.version>` in
   `pom.xml`, `languageVersion`/`-language-version`/`apiVersion`. Nothing found: assume
   **2.4.21** and say so in one line. Treat **2.5.0-Beta2 as preview**: use its features only
   if the user asks or the build already targets it.
2. **Classify each pattern by tier** (details in `references/version-gates.md`):
   - **Tier S, stable**: use always, no opt-in. Example: explicit backing fields (2.4.0), context parameters (2.4.0).
   - **Tier E, experimental**: use only if the build already enables the flag/opt-in, or the user asks. Otherwise write the stable form and mention the flag in one line. Experimental features emit pre-release binaries that older compilers cannot read, which matters for libraries.
   - **Tier S-next**: stable in the 2.5.0-Beta2 notes but not in a stable release yet (unused-return checker default, `@IntroducedAt`, name-based destructuring `only-syntax`). Use only when the target is 2.5 or later.
   - **Tier P, 2.5 experimental**: companion blocks, full value classes, `if` helpers. Only on explicit request.
3. **Write with the catalog in mind** (table below, details in `references/`). Do not narrate
   every substitution. Modern code is the default, not a talking point.
4. **Self-audit.** If code touches the filesystem, run the scanner on what you wrote:
   `python scripts/scan_antipatterns.py <path...> --target <version>`
   Fix every `error` and `warn` finding. In a chat with no files, walk the table mentally.
5. **Review/migrate mode** (user hands you existing code): report findings, then give the
   corrected code. Use the format at the bottom.

## Quick reference: superseded -> modern

Status: **S** stable, **S-next** stable in 2.5.0-Beta2 only, **E** experimental (opt-in), **P** experimental in 2.5.0-Beta2. "Dead" means the
old form no longer compiles at that version.

### Language

| Superseded                                                                                              | Modern                                                                                                           | Since / status                                                                                                               |
| ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `private val _x = MutableStateFlow(..)` plus `val x: StateFlow<T> get() = _x` (or `= _x.asStateFlow()`) | `val x: StateFlow<T>` then `field = MutableStateFlow(..)` on the next line                                       | S 2.4.0 (E 2.3.0, `-Xexplicit-backing-fields`)                                                                               |
| Context receivers `context(Logger)`                                                                     | Context parameters `context(logger: Logger)`                                                                     | Receivers dead 2.3.20; params S 2.4.0                                                                                        |
| Overloads that differ only by context parameters                                                        | Distinct names, or explicit context arguments `f(emailSender = s)`                                               | Ambiguity error 2.3.20; explicit args E 2.4.0                                                                                |
| `fun f() = ... return ...` with no declared return type                                                 | Declare the return type (then `return` in an expression body is allowed) or drop the `return`                    | Dead 2.4.0; allowed with explicit type by default 2.3.0                                                                      |
| `[a, b]` array literal outside annotations                                                              | `arrayOf(a, b)` (or `listOf`)                                                                                    | Dead 2.4.0. Collection literals `[..]` build `List` etc. but are E (`-Xcollection-literals`)                                 |
| `::javaClass` property reference                                                                        | `x.javaClass` or `X::class.java`                                                                                 | Warn 2.4.0                                                                                                                   |
| `@file:Suppress("DEPRECATION")` or `import a.b.*` just to silence a deprecated import                   | Import the symbol explicitly                                                                                     | No import-site warning since 2.4.0                                                                                           |
| `@JvmOverloads` to grow a published API                                                                 | `@IntroducedAt("1.2")` on each new optional parameter                                                            | S-next 2.5.0-Beta2 (E in 2.4.0 with `@OptIn(ExperimentalVersionOverloading::class)`)                                         |
| Unmarked single-field `value class Id(val v: Long)`                                                     | `@JvmInline value class Id(val v: Long)`                                                                         | Warn planned 2.5.20, error 2.6/2.7                                                                                           |
| Position-based destructuring where variable names differ from property names (silent swap)              | Name-based `(val email, val username) = user` or `(val mail = email, val name = username) = user`                | S-next 2.5.0-Beta2 (`only-syntax` default); E since 2.3.20                                                                   |
| Discarding non-`Unit` results (`list.map { sideEffect(it) }`, ignored `String` builders)                | `forEach` for effects; keep results; `val _ = call()` to ignore deliberately; `@IgnorableReturnValue` on helpers | S-next 2.5.0-Beta2, on by default; E since 2.3.0                                                                             |
| `@BuilderInference`                                                                                     | Plain inference                                                                                                  | Deprecated `[changelog]`                                                                                                     |
| `-language-version` 1.8/1.9, K1                                                                         | Language 2.0+                                                                                                    | Dead: 1.8 and non-JVM 1.9 in 2.3.0; JVM 1.9 and K1 in 2.4.0. Language 2.1 deprecated 2.4.0, 2.2 in 2.5.0-Beta1 `[changelog]` |
| Hand-written `companion object { @JvmStatic ... }` for statics, `Foo.Companion` shims                   | `companion { }` blocks and `companion val Type.X` extensions                                                     | P, 2.5.0-Beta2 only                                                                                                          |

### Standard library

| Superseded                                                                     | Modern                                                                                  | Since / status                                                                     |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `readLine()`, `readLine()!!`                                                   | `readlnOrNull()`, `readln()`                                                            | Warn 2.4.0                                                                         |
| `c.toInt()`, `n.toChar()` on `Char`/`Number`                                   | `c.code`, `Char(code)`, `c.digitToInt()`, `c.digitToIntOrNull()`                        | Dead 2.3.0                                                                         |
| `s.subSequence(start = a, end = b)`                                            | `s.subSequence(startIndex = a, endIndex = b)`                                           | Dead 2.3.0                                                                         |
| `kotlin.io.createTempFile/createTempDirectory`                                 | `kotlin.io.path.createTempFile/createTempDirectory`                                     | Dead 2.3.0                                                                         |
| `InputStream.readBytes(estimatedSize)`                                         | `readBytes()`                                                                           | Hidden 2.3.0                                                                       |
| `AbstractCoroutineContextKey`, `getPolymorphicElement`, `minusPolymorphicKey`  | Plain `CoroutineContext.Key`                                                            | Warn 2.4.0                                                                         |
| `java.util.UUID` and `try { Uuid.parse(..) } catch` in common code             | `kotlin.uuid.Uuid`, `Uuid.parseOrNull(..)`, `Uuid.random()`                             | S 2.4.0 (`generateV4()/generateV7()` stay E, `@OptIn(ExperimentalUuidApi::class)`) |
| `xs == xs.sorted()`, `zipWithNext().all { a, b -> a <= b }`                    | `xs.isSorted()`, `isSortedBy`, `isSortedDescending`, `isSortedWith`                     | S 2.4.0                                                                            |
| `xs.distinct().size == xs.size`, `xs.distinct().size <= 1`                     | `allDistinct()`, `allDistinctBy {}`, `allEqual()`, `allEqualBy {}`                      | E 2.4.20 (`ExperimentalStdlibApi`)                                                 |
| `getOrPut` on maps with nullable values (null treated as missing, silently)    | `getOrPutIfMissing` / `getOrPutIfNull` (and `getOrElse...`)                             | E 2.4.0 (`ExperimentalStdlibApi`)                                                  |
| `assertEquals(a, b, "msg $expensive")` eager messages                          | `assertEquals(a, b) { "msg $expensive" }`                                               | E 2.4.20 (`ExperimentalKotlinTestApi`)                                             |
| `Enum.values()`, `enumValues<T>()`                                             | `Enum.entries`, `enumEntries<T>()`                                                      | `[baseline]`                                                                       |
| `if (flag) value else null`                                                    | `ifOrNull(flag) { value }`; `.onTrue {}` / `.onFalse {}`                                | P, 2.5.0-Beta2 (`ExperimentalStdlibApi`)                                           |
| `StringBuilder.append(obj: Any?)`                                              | Typed overloads or a string template                                                    | Error `[changelog]` 2.5.0-Beta2                                                    |
| Assigning a Java `@Unmodifiable` collection to `MutableList`                   | Keep it read-only, copy with `toMutableList()`                                          | Warn 2.3.20, error planned 2.5.0                                                   |
| `toUpperCase()/toLowerCase()/capitalize()/decapitalize()`, `appendln`, `sumBy` | `uppercase()/lowercase()`, `replaceFirstChar { it.titlecase() }`, `appendLine`, `sumOf` | `[baseline]`                                                                       |

### Build and tooling

| Superseded                                                                                                                               | Modern                                                                                                   | Since                                                    |
| ---------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| `kotlinOptions { jvmTarget = ".." }`                                                                                                     | `compilerOptions { jvmTarget.set(JvmTarget.JVM_21) }`                                                    | Dead 2.3.0                                               |
| `testApi(..)`                                                                                                                            | `testImplementation(..)`                                                                                 | Warn 2.3.0                                               |
| `org.jetbrains.kotlin.android` with AGP 9+; `androidTarget {}` in KMP                                                                    | AGP built-in Kotlin; `com.android.kotlin.multiplatform.library` and `android {}`                         | Config error 2.3.0                                       |
| Maven: hand-listed source roots and `kotlin-stdlib` dependency; explicit `kotlin-maven-allopen` for JPA                                  | `<extensions>true</extensions>` on `kotlin-maven-plugin`; `kotlin-maven-noarg` already pulls in all-open | S 2.3.20                                                 |
| `kotlin.native.cacheKind` property                                                                                                       | `disableNativeCache(version = .., reason = .., issue = ..)`                                              | Deprecated 2.3.20                                        |
| ABI tasks `checkLegacyAbi`/`updateLegacyAbi`; `abiValidation { legacyDump {} }`, `klib { enabled }`                                      | `checkKotlinAbi`/`updateKotlinAbi`; settings directly in `abiValidation {}`                              | 2.3.20 / 2.4.0                                           |
| Compose plugin `enableStrongSkippingMode`, `enableIntrinsicRemember`, `enableNonSkippingGroupOptimization`, `stabilityConfigurationFile` | `featureFlags`, `stabilityConfigurationFiles`                                                            | Error 2.4.0                                              |
| `kotlin { sourceSets }` on the Android extension                                                                                         | `android { sourceSets { .. } }` in the AGP block                                                         | Warn 2.4.0, error `[changelog]` 2.5.0                    |
| `withJava()` in KMP                                                                                                                      | Follow the compiler's deprecation hint (no replacement named in the notes)                               | Error `[changelog]` 2.5.0-Beta2                          |
| `js(IR)`, `js(LEGACY)`, `kotlinArtifacts {}`, `targetHierarchy`, "out of process" compiler strategy                                      | `js { }`, current binaries DSL, the default hierarchy template, daemon or in-process strategy            | Removed 2.4.0                                            |
| Running the compiler on JDK < 17                                                                                                         | JDK 17+                                                                                                  | Error 2.5.0-Beta2 (`-Xallow-pre-17-runtime-jdk` opt-out) |
| `kotlin` runner command                                                                                                                  | `kotlinr`                                                                                                | 2.4.20                                                   |

Full detail, Bad/Good code and edge cases: `references/language.md`, `references/stdlib.md`,
`references/build-tooling.md`, `references/web-wasm-native.md`.

## Rules of engagement

- **Do not downgrade to stay safe.** Writing `Enum.values()` "because everyone knows it" is the failure this skill exists to prevent.
- **Do not upgrade into Tier E silently.** Collection literals, full value classes, companion blocks and the `-X` flags change the compiler flags and binary format. Offer, do not impose.
- **Never invent a replacement.** If a deprecation is only a changelog line (`[changelog]`) or the notes give no replacement, say "follow the compiler's deprecation hint" instead of guessing an API.
- **Stable beats clever.** Prefer the stable form even when a preview feature would be shorter.
- **Dates are as of 2026-11-07.** Release dates live in `references/version-gates.md`. If the user mentions a compiler newer than 2.4.21 (for example 2.5.0 final), treat Tier P features as possibly stable and say you are going by Beta2 notes.
- **Compiler help is free.** For unused return values and structural-class equality, the 2.5 compiler reports the problems itself; recommend `-Xreturn-value-checker=full` for older targets instead of hand-auditing.

## Review/migration output format

```
Target: Kotlin 2.4.21 (assumed: no version found)

| #   | Where     | Antipattern                        | Replace with              | Why / since    |
| --- | --------- | ---------------------------------- | ------------------------- | -------------- |
| 1   | Foo.kt:12 | context receiver `context(Logger)` | `context(logger: Logger)` | removed 2.3.20 |

<corrected code>

Needs opt-in (not applied): collection literals -> add `-Xcollection-literals`.
```

Order findings: `error` (will not compile on target), then `warn` (deprecated), then
`modernize` (still compiles, superseded). Keep the explanation to the "Why / since" cell.
