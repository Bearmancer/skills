# Language antipatterns

Contents: [1 Explicit backing fields](#1-explicit-backing-fields) · [2 Context receivers](#2-context-receivers-to-context-parameters) · [3 Return in expression bodies](#3-return-in-expression-bodies) · [4 Array and collection literals](#4-array-and-collection-literals) · [5 javaClass](#5-javaclass-property-reference) · [6 Import deprecation workarounds](#6-import-deprecation-workarounds) · [7 Destructuring](#7-destructuring) · [8 Value classes](#8-value-classes) · [9 Unused results](#9-unused-return-values) · [10 Evolving APIs](#10-evolving-published-apis) · [11 Annotation use-site targets](#11-annotation-use-site-targets) · [12 Nested type aliases and when](#12-nested-type-aliases-and-when-exhaustiveness) · [13 Checks that became errors](#13-checks-that-became-errors-in-24) · [14 Companion blocks](#14-companion-blocks-and-extensions-preview) · [15 Dropped language versions](#15-dropped-language-versions)

Tier key: **S** stable, **S-next** stable only in 2.5.0-Beta2 (use when target is 2.5+), **E** experimental (needs flag/opt-in), **P** experimental in 2.5.0-Beta2.

## 1. Explicit backing fields

**Antipattern.** The "backing property" dance: a private mutable `_x` plus a public read-only `x`.
The `.asStateFlow()` / `.asSharedFlow()` variant is the same pattern.

```kotlin
// BAD
private val _city = MutableStateFlow("")
val city: StateFlow<String> get() = _city
// BAD (same pattern)
private val _count = MutableStateFlow(0)
val count: StateFlow<Int> = _count.asStateFlow()

fun updateCity(newCity: String) { _city.value = newCity }
```

```kotlin
// GOOD (S since 2.4.0)
val city: StateFlow<String>
    field = MutableStateFlow("")

fun updateCity(newCity: String) {
    city.value = newCity          // smart-cast to the field type inside the same private scope
}
```

- Status: E in 2.3.0 (`-Xexplicit-backing-fields`), **S in 2.4.0**, no flag needed on 2.4+.
- Callers see the declared property type; the field type is visible only in the declaring scope.
- Applies to any "internal type differs from exposed type" case (`ArrayList` exposed as `List`, `MutableStateFlow` as `StateFlow`), not just flows.
- On a target below 2.4.0 without the flag: say so and offer the flag; do not silently fall back.

## 2. Context receivers to context parameters

**Antipattern.** `context(Logger)` with an unnamed type (context receivers). They are unsupported
since 2.3.20.

```kotlin
// BAD
context(Logger)
fun saveUser(id: Int) { info("Saving $id") }        // implicit receiver-style access

// GOOD (S since 2.4.0; preview was 2.2.0)
context(logger: Logger)
fun saveUser(id: Int) { logger.info("Saving $id") }
```

- Name every context parameter and access it by name.
- **Overloads that differ only by context parameters are ambiguous (2.3.20).** Rename them, or
  disambiguate at the call site with explicit context arguments (E, `-Xexplicit-context-arguments`):

```kotlin
context(emailSender: EmailSender) fun sendNotification() { /* .. */ }
context(smsSender: SmsSender)     fun sendNotification() { /* .. */ }

context(defaultEmail: EmailSender, defaultSms: SmsSender)
fun notifyUser() {
    sendNotification(emailSender = defaultEmail)    // E: explicit context argument
    sendNotification(smsSender = defaultSms)
}
```
- Several calls sharing the same contexts: use the `context(a, b) { ... }` scope function.
- `kotlin.context` overloads dropped from 22 to 6 in 2.3.20.
- Context parameters are stable except explicit context arguments and callable references.

## 3. `return` in expression bodies

```kotlin
// BAD: error since 2.4.0 (warning in 2.3.0), no declared return type
fun parse(s: String) = s.toIntOrNull() ?: return -1

// GOOD A: declare the return type (return in an expression body is allowed, default since 2.3.0)
fun parse(s: String): Int = s.toIntOrNull() ?: return -1
// GOOD B: avoid return
fun parse(s: String): Int = s.toIntOrNull() ?: -1
```
Prefer B.

## 4. Array and collection literals

```kotlin
// BAD: array literal outside annotations: error since 2.4.0
val roles = Roles(["admin", "user"])
// GOOD
val roles = Roles(arrayOf("admin", "user"))
```
Square brackets remain valid in **annotation arguments** and annotation parameter defaults.

**Collection literals are E** (2.4.0, `-Xcollection-literals`): `val xs: MutableList<String> = ["a", "b"]`;
an untyped literal becomes a `List`; custom types opt in with `operator fun of(vararg ..)` in the
companion. They cannot construct Java-defined collections. Write them only when the build enables
the flag or the user asks; otherwise `listOf(..)` is correct code, not an antipattern.

## 5. `javaClass` property reference

```kotlin
// BAD: warning since 2.4.0
val ref = obj::javaClass
// GOOD
val cls = obj.javaClass          // runtime class of an instance
val cls2 = Foo::class.java       // class literal
```

## 6. Import deprecation workarounds

Since 2.4.0 a deprecated symbol is no longer reported on the *last segment of the import*, only at
use sites. Drop the tricks that existed to dodge it:

```kotlin
// BAD
@file:Suppress("DEPRECATION")
import com.example.legacy.*
// GOOD
import com.example.legacy.OldThing     // use-site warnings still tell you to migrate
```
Never leave `@file:Suppress("DEPRECATION")` on code you are touching: fix the deprecated call.

## 7. Destructuring

Position-based destructuring silently swaps values when names do not line up:

```kotlin
data class User(val username: String, val email: String)
val (email, username) = user      // BAD: email == user.username, username == user.email
```

Name-based destructuring: E in 2.3.20 behind `-Xname-based-destructuring=<mode>`; the
`only-syntax` mode is **S-next: stable and the default in 2.5.0-Beta2**.

```kotlin
// GOOD on 2.5 (or with the flag)
(val email, val username) = user                // matches by property name
(val mail = email, val name = username) = user  // rename while matching
```
- `only-syntax` (default 2.5): old `val (x, y)` stays position-based, new `(val x, val y)` is name-based.
- `name-mismatch` (E): warns when a positional destructuring's variable names do not match the data class properties. A useful lint on 2.3.20+.
- `complete` (E): `val (a, b)` becomes name-based and positional becomes `val [a, b]`. Do not emit `[a, b]` unless the build uses `complete`.
- Full value classes (P) have no `componentN()`; name-based destructuring is the only way.
- Targets below 2.5 with no flag: keep `val (a, b)`, make variable names equal the property names in declaration order, and offer `-Xname-based-destructuring=name-mismatch`.

## 8. Value classes

```kotlin
// BAD: plain `value class` will stop meaning "inline"
value class UserId(val raw: Long)
// GOOD
@JvmInline
value class UserId(val raw: Long)
```
Roadmap in the notes: 2.5.20 warns for unmarked single-field value classes; 2.6.0 or 2.7.0 makes
it an error; `-Xinline-value-class-migration=warning|strict` previews it. Inline value classes
must be declared explicitly via the `inline` modifier and `@JvmInline value class`.

**Full value classes (P, `-Xfull-value-classes`)**: multi-property
`value class Complex(val real: Double, val imaginary: Double)`, `sealed value class`, and
`value object`. Auto `equals/hashCode/toString`, no `copy()`, no `componentN()`. Only on request.
Libraries can prepare with `@WillBecomeValue` (E, `@OptIn(ExperimentalValueClassApi::class)`).

## 9. Unused return values

The unused return value checker is E in 2.3.0 (`-Xreturn-value-checker=check|full`) and **S-next, on
by default, in 2.5.0-Beta2**.

```kotlin
// BAD: result silently dropped
name.trim()                          // warning
items.map { audit(it) }              // builds a list nobody reads; use forEach

// GOOD
val trimmed = name.trim()
items.forEach { audit(it) }
val _ = computeValue()               // deliberate discard, silences the warning at this site
```
- `@MustUseReturnValues` marks a scope (file, class) whose results must be used; `@IgnorableReturnValue` marks helpers whose results may be dropped (the notes' example wraps `MutableList.add`).
- `-Xreturn-value-checker=full` treats the whole project as marked.
- Custom higher-order helpers: `contract { returnsResultOf(block) }` lets the checker see through the lambda (E, `-Xallow-returns-result-of`, `@OptIn(ExperimentalContracts::class)`).
- In new library code on 2.5, annotate functions whose result matters.

## 10. Evolving published APIs

```kotlin
// BAD: @JvmOverloads generates more overloads than needed and cannot encode versions
@JvmOverloads
fun Button(label: String = "", color: Color = DefaultColor, borderColor: Color = DefaultBorder) { }

// GOOD (S-next in 2.5.0-Beta2; E in 2.4.0 with @OptIn(ExperimentalVersionOverloading::class))
fun Button(
    label: String = "",
    color: Color = DefaultColor,
    @IntroducedAt("1.1") borderColor: Color = DefaultBorder,
    @IntroducedAt("1.2") borderWidth: Int = 1,
) { }
```
Using both annotations together yields conflicting overloads; the compiler warns and prefers
`@IntroducedAt`. For application code that is not a binary-compatibility surface, `@JvmOverloads`
for Java callers is fine; flag it only in libraries.

## 11. Annotation use-site targets

S in 2.4.0: the `@all` meta-target for properties and the new defaulting rules. With no explicit
target the compiler now picks `param` and `property` if applicable, and `field` only if `property`
does not apply. Do not write defensive `@field:` / `@param:` pairs by habit; use `@all:Ann` for
every applicable site and an explicit target only for a single one. To restore old defaulting
project-wide: `-Xannotation-default-target=first-only` (a migration crutch, not a goal).

## 12. Nested type aliases and `when` exhaustiveness

- Nested type aliases are **S in 2.3.0**: declare an alias inside the class that owns it instead of a file-level alias that exists only for that class.
- Data-flow-based exhaustiveness for `when` is **S in 2.3.0**: do not add a dead `else -> error(..)` the flow already exhausts. Keep `else` where the subject is genuinely open.
- **Non-abstract Java sealed class**: `when` over it needs an `else` or a branch for the class itself (error since 2.4.0).

## 13. Checks that became errors in 2.4

Do not write these (errors in 2.4.0 after warnings in 2.0 to 2.3):
- `is` checks between definitely incompatible types (always false).
- Inline functions exposing less-visible types or declarations.
- Implicit references to inaccessible types from indirect dependencies (add the dependency or fix the API).
- `::class` on an expression whose type is a reified parameter with a nullable upper bound (null-check or `!!` first).
- `init` blocks in anonymous objects assigning a property declared later.
- `operator getValue/setValue` with wrong parameter counts (exactly 2 and 3).
- Generic calls whose explicit type arguments violate inter-parameter bounds.
- `inline` on enum entries; implicit enum constructor calls that need `@OptIn`.
- Flexible treatment of explicit nullable type arguments for Java generics; ignoring Jakarta `@Nullable`/`@Nonnull` (now enforced).
- Using a companion object that requires opt-in without `@OptIn`.
- Callable references with type arguments on the wrong qualifier segment (warning): write `Outer<Int>.Inner<String>::toString`.

2.3.0 errors: `@JvmSerializableLambda` on `inline`/`crossinline` lambdas, delegating a Kotlin
interface to a Java class with mismatched generic signatures, inheriting from a nullable typealias,
reified type parameters inferred as intersection types, type-parameter bounds exposing
less-visible types.

## 14. Companion blocks and extensions (preview)

P, `-Xcompanion-blocks-and-extensions`. Only on request:

```kotlin
companion val Vector.UnitX get() = Vector(1.0, 0.0)     // companion extension, no companion object needed

data class Vector(val x: Double, val y: Double) {
    companion { val Zero: Vector get() = Vector(0.0, 0.0) }   // static where supported, no @JvmStatic
}
```
Until the user opts in, keep the existing `companion object`.

## 15. Dropped language versions

`-language-version` 1.8 is unsupported from 2.3.0 (1.9 too on non-JVM platforms); 1.9 on JVM and the
K1 compiler from 2.4.0. By the changelogs, language version 2.1 was deprecated in 2.4.0 and 2.2 in
2.5.0-Beta1 (`[changelog]`). Do not recommend an
old `languageVersion` to "fix" a build; fix the code. In 2.5.0-Beta2 the compiler wants JDK 17+ to
run; `-Xallow-pre-17-runtime-jdk` is a temporary opt-out removed in 2.5.20 or 2.6.0.
