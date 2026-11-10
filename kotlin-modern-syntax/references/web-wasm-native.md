# Kotlin/JS, Wasm, Native and KMP antipatterns

Read this only when the code targets JS, Wasm, Native, or multiplatform. Tier key as in `language.md` (S, S-next, E, P).

## Kotlin/JS

| Superseded                                                                                                  | Modern                                                                                                      | Since / tier                                                 |
| ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `@JsExport @JsName("default ") class X` (trailing space hack)                                               | `@JsExport.Default class X`                                                                                 | S 2.3.0 (ES modules emit `export default`)                   |
| Hand-wrapping each `suspend fun` for JS callers                                                             | `@JsExport` directly on suspend functions (consumed as `async`)                                             | E 2.3.0, `-Xenable-suspend-function-exporting`               |
| Exporting suspending lambdas through wrappers                                                               | Export as async functions                                                                                   | E 2.4.20                                                     |
| Calling companions of exported interfaces as `Foo.getInstance().bar()` (ES modules) vs `Foo.bar()` (others) | `Foo.Companion.bar()` everywhere, or `@JsStatic` on the member and `Foo.bar()`                              | S 2.3.0                                                      |
| `@JsQualifier` only at file level, forcing separate files for externals                                     | `@JsQualifier("pkg")` directly on `external` functions and classes                                          | S 2.3.0                                                      |
| Reimplementing Kotlin interfaces in TS impossible/forbidden                                                 | Implement exported interfaces from TS with `[Iface.Symbol] = true`; reuse defaults via `Iface.DefaultImpls` | E 2.3.20, `-Xenable-implementing-interfaces-from-typescript` |
| `LongArray` as `Array<bigint>`                                                                              | `BigInt64Array`                                                                                             | E 2.3.0, `-Xes-long-as-bigint`                               |
| ES5-only inline JS                                                                                          | ES2015 syntax inside inlined JS                                                                             | S 2.4.0                                                      |
| Value classes unexportable                                                                                  | Value class export to JS/TS                                                                                 | S 2.4.0                                                      |
| Targeting only `es5`/`es2015`, enabling BigInt separately                                                   | `target.set("es2020")`                                                                                      | 2.5.0-Beta2                                                  |
| Custom browser-test plumbing                                                                                | New browser testing DSL                                                                                     | E 2.4.20                                                     |
| `useEsModules()` missing when webpack 5.108+ sees `import.meta`                                             | Configure ES modules                                                                                        | 2.4.20 note                                                  |
| `js(IR)` / compiler-type argument                                                                           | `js { }`                                                                                                    | Removed 2.4.0                                                |

## Kotlin/Wasm

- `KClass.qualifiedName` works by default (2.3.0): delete the manual enabling flag/workaround.
- New exception-handling proposal is default for `wasmWasi` (2.3.0); for `wasmJs` still opt in with `-Xwasm-use-new-exception-proposal`.
- Module initialization happens at instantiation (2.3.20): remove external JS calls to `_initialize()`; avoid `@EagerInitialization` unless truly needed.
- `@nativeInvoke` (E 2.3.20, `@OptIn(ExperimentalWasmJsInterop::class)`) is a temporary bridge and warns; do not build new designs on it.
- `wasmExports` JS API deprecated (2.4.20): only `wasmExports.memory` survives with a warning; use `kotlin.wasm.unsafe.wasmMemory`.
- `@JsFun` top-level `require()` handling changed (2.4.20), companion object initialization order improved, incremental compilation on by default (2.4.0), Wasmtime supported in the Gradle plugin, WebAssembly Component Model (E 2.4.0).

## Kotlin/Native

- Do not use AtomicFU atomic operations inside `public inline` functions, or `internal inline` functions called from other files (Native compiler prohibits, 2.4.20).
- Cross-module inlining during klib compilation is on by default in 2.5.0-Beta2 (`-Xklib-ir-inliner=disabled` to opt out).
- Native release link tasks are up to 40% faster in 2.3.0; concurrent marking GC default and LLVM 21 in 2.4.0.

## Multiplatform libraries

- New publication format for KMP libraries and a new experimental compilation scheme exist in 2.5.0-Beta2. Preview only.
- Stricter dependency matching (2.3.20) can fail metadata compilation when resolution differs between common and platform source sets; the notes link a YouTrack workaround (KT-84533).
- Use `kotlin.uuid.Uuid`, `kotlin.time.Clock`/`Instant` in common code rather than `java.util.UUID` / platform clocks.
