# Standard library antipatterns

Tier key: **S** stable, **E** experimental (needs `@OptIn` or `-opt-in=`), **P** experimental in 2.5.0-Beta2.
`[baseline]` = long-established modernization outside the supplied notes. `[changelog]` = only a
changelog line; the replacement is not documented in the notes.

## Removed or deprecated APIs (stop using)

```kotlin
// readLine: warning 2.4.0
val a = readLine()!!        // BAD
val b = readLine()          // BAD
val a = readln()            // GOOD
val b = readlnOrNull()      // GOOD
```
(`reader.readLine()` on a `BufferedReader` is a different, fine API.)

```kotlin
// Char <-> number conversions: errors since 2.3.0
val n = c.toInt()           // BAD
val c2 = n.toChar()         // BAD on Number; prefer the explicit forms everywhere
val n = c.code              // GOOD
val c2 = Char(n)            // GOOD
val d = c.digitToInt()      // GOOD (digit value); digitToIntOrNull() when it may not be a digit
```

```kotlin
// kotlin.io temp files: errors since 2.3.0
kotlin.io.createTempFile(..)                 // BAD
kotlin.io.path.createTempFile(..)            // GOOD (returns Path)
kotlin.io.path.createTempDirectory(..)       // GOOD
```

- `InputStream.readBytes(estimatedSize)` is hidden (2.3.0): call `readBytes()`.
- `String.subSequence(start, end)`: error since 2.3.0. Use `subSequence(startIndex, endIndex)`.
- `AbstractCoroutineContextKey`, `getPolymorphicElement()`, `minusPolymorphicKey()`: deprecated 2.4.0 (error-prone since 1.3). Use plain `CoroutineContext.Key` keys.
- `Random.nextDouble(until)` now requires a **finite** `until` (behavior contract change 2.4.0).
- `Iterable.intersect()/subtract()` now test membership with `equals` on each receiver element (2.3.0 behavior fix). Do not rely on identity-based argument collections.
- `StringBuilder.append(obj: Any?)`: deprecation level raised to ERROR in 2.5.0-Beta2 `[changelog]`. Use typed overloads or a template instead of passing `Any?`.
- Assigning a Java collection annotated `@Unmodifiable`/`@UnmodifiableView` to a `Mutable*` type: warning since 2.3.20, error planned 2.5.0. Copy with `toMutableList()` when mutation is needed.
- Baseline `[baseline]`: `toUpperCase()/toLowerCase()` -> `uppercase()/lowercase()`; `capitalize()/decapitalize()` -> `replaceFirstChar { it.titlecase() }` / `replaceFirstChar { it.lowercase() }`; `appendln` -> `appendLine`; `sumBy/sumByDouble` -> `sumOf`; `Enum.values()` -> `entries` and `enumValues<T>()` -> `enumEntries<T>()` (changelog KT-48872 tracks the `values()` replacement).

## UUIDs (S in 2.4.0)

`kotlin.uuid.Uuid` is stable in common code. Only `generateV4()` and `generateV7()` (and
`generateV7NonMonotonicAt(instant)`) still need `@OptIn(ExperimentalUuidApi::class)`.

```kotlin
// BAD
val id = java.util.UUID.randomUUID()                 // in common/multiplatform code
val parsed = try { Uuid.parse(s) } catch (e: IllegalArgumentException) { null }

// GOOD
val id = Uuid.random()                               // v4, unchanged and stable
val parsed = Uuid.parseOrNull(s)                     // also parseHexDashOrNull / parseHexOrNull
```
`java.util.UUID` is still right where a Java API demands it; convert with the stdlib helpers.
Use `Uuid.generateV7()` for time-ordered ids (E).

## Time (S in 2.3.0)

`kotlin.time.Clock` and `kotlin.time.Instant` are the stdlib time-tracking types. Prefer them to
`System.currentTimeMillis()` for domain timestamps and to library-specific clocks in new common
code. Caution: the 2.3.0 notes' own samples still carry `@OptIn(ExperimentalTime::class)` on
`Instant`; check what the project's compiler actually demands and keep the opt-in if it does.

## Sorted order (S in 2.4.0)

```kotlin
// BAD
val ok = xs == xs.sorted()
val ok2 = xs.zipWithNext().all { (a, b) -> a <= b }
// GOOD (iterables, arrays, sequences; short-circuits on the first out-of-order pair)
val ok = xs.isSorted()
users.isSortedBy(User::age)
xs.isSortedDescending(); xs.isSortedWith(comparator); xs.isSortedByDescending { it.score }
```
Fewer than two elements returns `true`.

## All-equal and all-distinct (E in 2.4.20, `ExperimentalStdlibApi`)

```kotlin
// BAD
val unique = xs.distinct().size == xs.size
val same = xs.distinct().size <= 1
// GOOD
@OptIn(ExperimentalStdlibApi::class)
val unique = xs.allDistinct()            // allDistinctBy { it.id }
val same = xs.allEqual()                 // allEqualBy { it.date }
```
Collections, sequences, arrays; structural equality.

## Maps with nullable values (E in 2.4.0, `ExperimentalStdlibApi`)

`getOrPut`/`getOrElse` on `Map<K, V?>` conflate "missing key" and "stored null". Say which you mean:

```kotlin
@OptIn(ExperimentalStdlibApi::class)
fun cached(key: String): Response? =
    cache.getOrPutIfMissing(key) { service.query(key) }   // caches a null result; does not re-query
// getOrPutIfNull / getOrElseIfNull: null counts as missing (old getOrPut behavior)
```

## Unsigned to BigInteger (S in 2.4.0, JVM)

```kotlin
// BAD
val big = BigInteger(u.toString())
// GOOD
val big = u.toBigInteger()               // UInt and ULong
```

## `Map.Entry.copy()` (E in 2.3.20, `ExperimentalStdlibApi`)

Snapshot entries before mutating the map: `map.entries.filter { .. }.map { it.copy() }`, then
`map.entries.removeAll(snapshot)`. Do not hold live `Map.Entry` views across mutation.

## `kotlin.test` lazy messages (E in 2.4.20, `@OptIn(ExperimentalKotlinTestApi::class)`)

```kotlin
// BAD: message string built on every call, even when the assertion passes
assertEquals(expected, actual, "Unexpected: ${items.joinToString()}")
// GOOD
assertEquals(expected, actual) { "Unexpected: ${items.joinToString()}" }
```
Applies to `assertTrue/False`, `assertEquals/NotEquals`, `assertSame/NotSame`, `assertIs/IsNot`,
`assertNull`, `assertContains`, `assertContentEquals`. Matters most with the Power-assert plugin,
which now has a runtime library and a `@PowerAssert` annotation (2.4.0) for library authors.

## Coroutine exception copies (E in 2.4.20)

An exception with extra required constructor arguments loses `kotlinx.coroutines` stack trace
recovery unless it implements `StackTraceRecoverable<T>` and overrides `copyForStackTraceRecovery()`
(`@OptIn(ExperimentalStdlibCoroutineSupportApi::class)`). Exceptions with constructors taking only
message/cause/both/none need nothing.

## `if` helpers (P, 2.5.0-Beta2, `ExperimentalStdlibApi`)

```kotlin
val added = tags.add("wasm").onTrue { println("Tag added") }          // returns the Boolean
val message = ifOrNull("wasm" in tags) { "Wasm tag is available" }    // String? without an else
```
Preview only; plain `if` expressions are correct on stable.

## Unicode code points (P, 2.5.0-Beta2, `ExperimentalUnicodeApi`)

Iterating a string as `Char` splits surrogate pairs. `CodePoint` (an `Int` value class in
`kotlin.text.unicode`) counts, iterates and edits by code point. Mention it when code claims to
handle emoji or supplementary characters with `Char` loops; do not apply unasked.

## Compile-time constants (E in 2.4.0, S-next in 2.5.0-Beta2; `-Xintrinsic-const-evaluation` before 2.5)

Unsigned operations, string functions (`lowercase()`, `uppercase()`, `trim()`), and `.name` of
enum constants and `KCallable` can be evaluated in `const val` initializers. `@IntrinsicConstEvaluation`
marks which stdlib functions qualify; not all are annotated yet.
