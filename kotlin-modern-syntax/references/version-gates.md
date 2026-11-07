# Version gates: feature, introduced, stable, how to enable

Use this to decide the tier before writing a pattern. S = stable release; S-next = marked stable in 2.5.0-Beta2 only (use when target is 2.5+); E = experimental; P = experimental in 2.5.0-Beta2. "Flag" means a compiler option via
`kotlin { compilerOptions { freeCompilerArgs.add("-X...") } }`; "OptIn" means `@OptIn(..)` or
`-opt-in=..`.

## Release timeline (as of 2026-11-07)

| Version | Date | Kind |
|---|---|---|
| 2.3.0 | 2025-12-16 | language release |
| 2.3.10 | 2026-02-05 | bug fix |
| 2.3.20 | 2026-03-16 | tooling release |
| 2.3.21 | 2026-04-23 | bug fix |
| 2.4.0 | 2026-06-03 | language release |
| 2.4.10 | 2026-07-14 | bug fix |
| 2.4.20 | 2026-09-07 | tooling release |
| 2.4.21 | 2026-10-08 | bug fix, **latest stable** |
| 2.5.0-Beta2 | 2026-10-21 | **latest preview** |
| 2.5.0 | planned Dec 2026 (about a month out) | language release |
| 2.5.20 | planned Mar 2027 | tooling release |

Dates are from the notes' `INDEX.md`. The 2.4.0 what's-new page header says "July 14, 2026",
which `INDEX.md` assigns to 2.4.10; treat June 3 as the 2.4.0 date. Anything marked "planned" or
"not yet" may have shipped since 2026-11-07: if the user's compiler is newer than 2.4.21, check
the current release notes before relying on the Tier E/P classifications below.

## Language

| Feature | Experimental / introduced | Stable | Enable (while E) |
|---|---|---|---|
| Nested type aliases | 2.2 | 2.3.0 | none |
| Data-flow exhaustiveness for `when` | 2.2.20 | 2.3.0 | none |
| `return` in expression bodies with explicit return type | 2.2.20 | default 2.3.0 | none |
| Unused return value checker | 2.3.0 | S-next: 2.5.0-Beta2 (default on) | `-Xreturn-value-checker=check\|full` |
| `returnsResultOf` contract | 2.4.0 | not yet | `-Xallow-returns-result-of`, `@OptIn(ExperimentalContracts)` |
| Explicit backing fields | 2.3.0 | 2.4.0 | `-Xexplicit-backing-fields` |
| Context parameters | 2.2.0 | 2.4.0 (not explicit args, not callable refs) | none on 2.4+ |
| Explicit context arguments | 2.4.0 | not yet in the notes | `-Xexplicit-context-arguments` |
| `@all` meta-target, new use-site defaults | 2.2 | 2.4.0 | `-Xannotation-default-target=first-only` reverts |
| Name-based destructuring | 2.3.20 | S-next: `only-syntax` in 2.5.0-Beta2 | `-Xname-based-destructuring=only-syntax\|name-mismatch\|complete` |
| Collection literals | 2.4.0 | not yet | `-Xcollection-literals` |
| Improved compile-time constants | 2.4.0 | S-next: 2.5.0-Beta2 | `-Xintrinsic-const-evaluation` |
| `@IntroducedAt` version overloads | 2.4.0 | S-next: 2.5.0-Beta2 | `@OptIn(ExperimentalVersionOverloading)` |
| Companion blocks and extensions | 2.5.0-Beta2 | not yet | `-Xcompanion-blocks-and-extensions` |
| Full value classes (+ `value object`) | 2.5.0-Beta2 | not yet | `-Xfull-value-classes` |
| Strict equality for structural classes | 2.5.0-Beta2 | not yet | `-Xstrict-equality-for-structural-classes` |
| Context-sensitive resolution | before 2.3 | not yet | (see KEEP-0379) |

## Standard library

| API | E | S | OptIn |
|---|---|---|---|
| `kotlin.time.Clock` / `Instant` | 2.1.20 | 2.3.0 | check your compiler (notes' samples still show `ExperimentalTime`) |
| `Uuid` (parse, format, compare, `parseOrNull`) | 2.0.20 | 2.4.0 | none |
| `Uuid.generateV4()/generateV7()/generateV7NonMonotonicAt()` | 2.3.0 | not yet | `ExperimentalUuidApi` |
| `isSorted*` family | (none, shipped stable) | 2.4.0 | none |
| `UInt/ULong.toBigInteger()` (JVM) | (none, shipped stable) | 2.4.0 | none |
| `Map.Entry.copy()` | 2.3.20 | not yet | `ExperimentalStdlibApi` |
| `getOrElse/getOrPut` `IfNull`/`IfMissing` | 2.4.0 | not yet | `ExperimentalStdlibApi` |
| `StackTraceRecoverable` | 2.4.20 | not yet | `ExperimentalStdlibCoroutineSupportApi` |
| `allDistinct*`, `allEqual*` | 2.4.20 | not yet | `ExperimentalStdlibApi` |
| `kotlin.test` lazy-message overloads | 2.4.20 | not yet | `ExperimentalKotlinTestApi` |
| `onTrue`, `onFalse`, `ifOrNull` | 2.5.0-Beta2 | not yet | `ExperimentalStdlibApi` |
| `CodePoint` + `kotlin.text.unicode` | 2.5.0-Beta2 | not yet | `ExperimentalUnicodeApi` |

## JVM, compiler plugins, build

| Item | Version |
|---|---|
| Java bytecode targets | 25 (2.3.0), 26 (2.4.0), 28 (2.5.0-Beta2, as written in the notes) |
| `when` via `invokedynamic` on JVM 21+ | stable and default 2.4.20 |
| Annotations in Kotlin metadata | default 2.4.0 |
| Java `@Unmodifiable`/`@UnmodifiableView`, Vert.x `@Nullable` | 2.3.20 (mismatch warning; error planned 2.5.0) |
| Power-assert runtime library, `@PowerAssert`, `CallExplanation` | 2.4.0 |
| Lombok plugin | Alpha 2.3.20 |
| JPA plugin applies all-open automatically | 2.3.20 |
| Maven `<extensions>true</extensions>` smart defaults | S 2.3.20 |
| Maven Java/JVM target alignment, Toolchains | S 2.4.0 |
| KGP uses Build tools API for JVM | 2.3.20 |
| Compiler native image, `kotlinr` | E 2.4.20 |
| JDK 17 required to run the compiler | error in 2.5.0-Beta2, mandatory 2.5.20 or 2.6.0 |
| Removed Gradle/Compose APIs | see `build-tooling.md` (2.4.0 batch) |
