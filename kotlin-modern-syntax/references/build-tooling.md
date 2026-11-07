# Build and tooling antipatterns (Gradle, Maven, KGP, Compose plugin, KMP)

Compatibility baseline in the notes: Kotlin 2.3.0 works with Gradle 7.6.3 to 9.0.0; 2.3.20 to
9.3.0; 2.4.0 to 9.5.0; 2.4.20 to 9.7.0. Minimum AGP: 8.2.2 (2.3.0), 8.5.2 (2.4.0). Support for
Gradle 7.6 to 8.13 is being deprecated (`[changelog]`, 2.4.0 line). Prefer a current Gradle.

## Compiler options

```kotlin
// BAD: dead since 2.3.0 (all kotlinOptions properties are errors)
tasks.withType<KotlinCompile> { kotlinOptions { jvmTarget = "21"; freeCompilerArgs += "-Xfoo" } }
android { kotlinOptions { jvmTarget = "21" } }

// GOOD
kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_21)
        freeCompilerArgs.add("-Xfoo")
    }
}
```
Per-target in KMP: `kotlin { jvm { compilerOptions { .. } } }`. To restore the pre-2.4 JVM module
name: `kotlin { compilerOptions.moduleName(project.name) }`; 2.4.0 standardizes default names to
`{group}:{project_name}` on every platform.

## Dependencies and source sets

- `testApi(..)` and `commonTest.dependencies { api(..) }`: deprecated 2.3.0. Use `testImplementation` / `implementation`. For JVM, Gradle test fixtures if you must share test code.
- Generated sources: register with `generatedKotlin` on the `KotlinSourceSet` (E, 2.3.0); read everything with `allKotlinSources` instead of `kotlin`.
- `HasKotlinDependencies` on `KotlinCompilation`: deprecated 2.3.0; use `KotlinSourceSet` dependency APIs.
- `KotlinDependencyHandler.platform()/enforcedPlatform()`, `KotlinCompilation.compileKotlinTask(Provider)`, `KotlinTarget.sourceSets`, `KotlinMultiplatformExtension.targetHierarchy`, `parentKotlinOptions`: removed in 2.4.0. Follow the compiler's replacement hint.
- Gradle plugin extras: `ExtrasProperty` is internal since 2.3.0; use Gradle's `ExtraPropertiesExtension`.
- `kotlin-dsl` plus `kotlin("jvm")` in one project (convention plugins): do not apply `kotlin("jvm")` explicitly (let `kotlin-dsl` supply it), or pin it to `embeddedKotlinVersion`, or drop `kotlin-dsl`.

## Android

- AGP 9.0.0+ has built-in Kotlin: remove `org.jetbrains.kotlin.android` (configuration error since 2.3.0 with new AGP).
- KMP Android targets: migrate to Google's `com.android.kotlin.multiplatform.library` plugin and rename `androidTarget {}` to `android {}`. On AGP 9+, `androidTarget` is a configuration error; the stop-gap is AGP 8.x plus Kotlin 2.3.10.
- `kotlin { sourceSets }` on the Android extension (`KotlinAndroidProjectExtension`): deprecated 2.4.0, error in 2.5 `[changelog]`. Configure `android { sourceSets { .. } }` instead.
- Direct integration with AGP is being deprecated unconditionally in 2.5 `[changelog]`.

## Compose compiler Gradle plugin

Errors since 2.4.0: `generateFunctionKeyMetaClasses`, `enableIntrinsicRemember`,
`enableNonSkippingGroupOptimization`, `enableStrongSkippingMode`, `stabilityConfigurationFile`,
`ComposeFeatureFlag.StrongSkipping`, `ComposeFeatureFlag.IntrinsicRemember`.

```kotlin
// GOOD: use the plural/feature-flag forms (check the exact property types against your plugin version)
composeCompiler {
    // featureFlags: replaces enableStrongSkippingMode, enableIntrinsicRemember, ...
    // stabilityConfigurationFiles: replaces stabilityConfigurationFile
    includeComposeMappingFile.set(false)   // only if the R8 group-key mapping tasks cause trouble (default is on)
}
```
Flags that graduated and are default-on: strong skipping and intrinsic remember (removed in 2.5.0);
`OptimizeNonSkippingGroups` and `PausableComposition` deprecated, removal in 2.6.0. Compose runtime
1.10+ is needed for group-key stack traces on minified Android builds.

## Maven

```xml
<!-- GOOD (S in 2.3.20): auto source roots + kotlin-stdlib -->
<plugin>
  <groupId>org.jetbrains.kotlin</groupId>
  <artifactId>kotlin-maven-plugin</artifactId>
  <version>${kotlin.version}</version>
  <extensions>true</extensions>
</plugin>
```
- BAD: hand-listed `src/main/kotlin` roots and an explicit `kotlin-stdlib` dependency when `<extensions>true</extensions>` is available. Opt out with `<kotlin.smart.defaults.enabled>false</kotlin.smart.defaults.enabled>`.
- JPA: the Gradle `kotlin.plugin.jpa` plugin now applies `all-open` with a JPA preset automatically; `kotlin-maven-noarg` implicitly includes `kotlin-maven-allopen`. Delete redundant `allopen` JPA config and hand-written no-arg constructors made only for JPA.
- 2.4.0: Java and JVM target versions align automatically; Maven Toolchains supported (S). Remove manual `jvmTarget` duplication where it merely repeats the Java target.
- Removed: Ant support (2.3.0), `KotlinScriptMojo` script execution (2.4.0).
- kapt on Maven: set `includeCompileClasspath` to `false` (or `kapt.include.compile.classpath=false`) and list processors in `annotationProcessorPaths`; the discovery-from-classpath default now warns.

## Native, ABI, caches (Gradle)

- `kotlin.native.cacheKind` property: replaced by `disableNativeCache(version = DisableCacheInKotlinVersion.2_3_0, reason = "..", issue = URI("..."))` inside `binaries.framework {}` (2.3.20). Delete the property. Disabling the cache is a temporary exception with a written reason.
- Binary compatibility validation tasks: `checkLegacyAbi` -> `checkKotlinAbi`, `updateLegacyAbi` -> `updateKotlinAbi`, `dumpLegacyAbi` -> `internalDumpKotlinAbi` (2.3.20). `check` now runs `checkKotlinAbi` automatically. 2.4.0 DSL: configure reports directly in `abiValidation {}` (no `legacyDump {}`), delete `klib { enabled = .. }`, use `keepLocallyUnsupportedTargets`.
- `CInteropProcess`: `destinationDir` -> `destinationDirectory.set()`; `konanVersion` -> `kotlinNativeVersion`. `getPluginArtifactForNative()` -> `getPluginArtifact()`.
- Removed 2.4.0: `kotlinArtifacts {}`; many `KotlinNativeCompile`/`KotlinNativeLink`/`CInteropProcess` properties (`konanHome`, `konanDataDir`, `languageVersion`, `apiVersion`, `moduleName`, ...). Use the replacement named by the diagnostic.
- `withJava()` (KMP): error-level deprecation in 2.5.0-Beta2 `[changelog]`.

## Compiler execution and BTA

- The "out of process" compiler execution strategy is removed in 2.4.0; use "daemon" or "in process". The non-BTA JVM compiler path is being deprecated; Kotlin/JVM compilation in KGP uses the Build tools API by default since 2.3.20.
- BTA authors: use builders that produce immutable operations (`build()`), `CancellableBuildOperation.cancel()`, `COMPILER_PLUGINS` instead of raw `-P` plugin arguments, and do not set `shrunkClasspathSnapshot` (managed automatically, error `[changelog]` in 2.5). Compiler argument values should match the documented letter case (warning 2.4.20).
- Diagnostics flow to Gradle's Problems API (compiler messages for JVM since 2.4.0, diagnostic IDs since 2.4.20). Use a recent Gradle to benefit.

## Gradle JS/Wasm plugin leftovers (removed 2.4.0)

`js(IR)`, `js(LEGACY)`, `js(BOTH)` and `KotlinJsCompilerType`: write `js { .. }`.
`ExperimentalWasmDsl` and `ExperimentalDceDsl` annotation classes, `NodeJsExec.create()` (use
`register()`), `karmaPhantomjsLauncher`, internal npm/Yarn helpers, and the old D8/Binaryen
package locations (now under `...targets.wasm`) are gone or moved. Subclassing `KotlinTest`,
`KotlinJsTest`, `KotlinMocha`, `KotlinWebpack` and similar is prohibited; use the DSL blocks.

## CLI

- `kotlin` runner command -> `kotlinr` (2.4.20; naming clash with the Kotlin Toolchain).
- Experimental compiler native image (2.4.20) as a drop-in `kotlinc` with faster startup; bundles Serialization, Compose, all-open, no-arg, SAM-with-receiver, Assignment, Lombok and Power-assert.
- Compiler JDK: 2.5.0-Beta2 errors on JDK < 17 (`-Xallow-pre-17-runtime-jdk` is a short-lived opt-out).
- `-Xwarning-level=DEPRECATION:warning` style flags: JPS does not support them yet `[changelog]`.

## Java target and bytecode

Java 25 bytecode (2.3.0), Java 26 (2.4.0), and Java 28 as written in the 2.5.0-Beta2 notes. When a
project sets a JVM target, match it to the JDK toolchain instead of hard-coding an older constant.
`when` over strings/enums/sealed types compiles via `invokedynamic` by default on JVM 21+ (S, 2.4.20).
