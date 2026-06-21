---
name: compose-performance
description: "Compose performance per Google's docs: release builds with R8 and Baseline Profiles, composition tracing, Layout Inspector recomposition counts, Macrobenchmark and JankStats, phases and deferred reads, backwards writes, stability and strong skipping. Use for jank, slow startup or scrolling, or excessive recompositions."
---

# Jetpack Compose performance

Sources of truth: [Compose performance](https://developer.android.com/develop/ui/compose/performance), [Best practices](https://developer.android.com/develop/ui/compose/performance/bestpractices), [Phases](https://developer.android.com/develop/ui/compose/performance/phases), [Modifier phases](https://developer.android.com/develop/ui/compose/performance/modifier-phases), [Backwards writes](https://developer.android.com/develop/ui/compose/performance/backwards-write), [Stability](https://developer.android.com/develop/ui/compose/performance/stability), [Diagnose stability](https://developer.android.com/develop/ui/compose/performance/stability/diagnose), [Fix stability](https://developer.android.com/develop/ui/compose/performance/stability/fix), [Strong skipping](https://developer.android.com/develop/ui/compose/performance/stability/strongskipping), [Tooling](https://developer.android.com/develop/ui/compose/performance/tooling), [Composition tracing](https://developer.android.com/develop/ui/compose/tooling/tracing), [Recomposition counts](https://developer.android.com/develop/ui/compose/tooling/debug), [Baseline Profiles](https://developer.android.com/develop/ui/compose/performance/baseline-profiles), [Macrobenchmark](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-overview), [Macrobenchmark metrics](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-metrics), [JankStats](https://developer.android.com/topic/performance/jankstats).

Compose is fast by default. Most real problems are a misconfigured build or a handful of coding mistakes that force Compose to rerun phases it could skip. Work in this order: **configure, locate, understand by phase, change, confirm**. Do not optimize code that no tool has pointed at.

## 1. Configure the build before judging performance

Debug builds interpret and JIT-compile code and add checks, so their timing is not meaningful.

- Measure a **non-debuggable build with R8 minification enabled**. For benchmarks, add a `benchmark` build type that copies `release` and signs with the debug key:

```kotlin
buildTypes {
    release {
        isMinifyEnabled = true
        isShrinkResources = true
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
    create("benchmark") {
        initWith(getByName("release"))
        signingConfig = signingConfigs.getByName("debug")
        matchingFallbacks += listOf("release")
    }
}
```

- The app under test must be `<profileable>` (the Benchmark module template adds it) so traces can be read without a debuggable build.
- Ship an **app-specific Baseline Profile** (section 5). Compose's bundled profile only covers Compose library code.
- Keep the Compose compiler on a Kotlin version where strong skipping is the default (Kotlin 2.0.20 and later).

## 2. Locate the slow work

Pick the tool by the question being asked.

| Question | Tool | Build |
|---|---|---|
| Where does frame or startup time go? | System trace with **composition tracing** | Profileable, non-debuggable |
| Which composables recompose or fail to skip? | **Layout Inspector** recomposition and skip counts | Debuggable |
| Why is a composable not skippable? | **Compose compiler reports** | Release |
| How slow is it, reproducibly, and did a change help? | **Macrobenchmark** | `benchmark` |
| How much jank do real users see? | **JankStats** | Production |

### Composition tracing

A system trace only shows composable functions when the app depends on `androidx.compose.runtime:runtime-tracing` (version from the Compose BOM). Record from the Android Studio Profiler (CPU timeline, System Trace) on a device running API 30 or higher; double-click a composable in the trace to jump to its source. Google calls traces the best starting point: they turn "it feels slow" into a hypothesis about which composable and which phase.

To capture composition traces inside Macrobenchmark runs, add `androidx.tracing:tracing-perfetto` and `androidx.tracing:tracing-perfetto-binary` to the benchmark module and pass the instrumentation argument `androidx.benchmark.fullTracing.enable=true`. Never ship `tracing-perfetto-binary` in the app.

The compiler embeds tracing strings in every Compose app. The tracing page gives an `-assumenosideeffects` R8 rule that strips them from production builds; keeping them means the profiled APK matches what users run.

### Layout Inspector recomposition counts

On a debuggable build (API 29 or higher), open Layout Inspector; the Component Tree shows a composition count and a skip count per node (enable **Show Recomposition Counts** in View Options if the columns are missing). Press **Reset**, perform one interaction, then read the counts. Recomposition itself is fine; look for counts that grow with frames (scroll, animation) where the content did not change, and for composables with zero recompositions whose UI should have updated. Counts explain behavior; they are not timing data.

### Compose compiler reports

```kotlin
composeCompiler {
    reportsDestination = layout.buildDirectory.dir("compose_compiler")
    metricsDestination = layout.buildDirectory.dir("compose_compiler")
}
```

Build a **release** variant, then read `<module>-composables.txt` (each composable is `restartable`, `skippable`, both or neither, with `stable`/`unstable` per parameter), `<module>-classes.txt` (inferred stability per class and property) and `<module>-composables.csv`. Only reach for reports once a stability problem is suspected; making every composable skippable is premature optimization.

### Macrobenchmark

A `com.android.test` module (Android Studio's Benchmark module template) drives the app with `MacrobenchmarkRule`:

```kotlin
@RunWith(AndroidJUnit4::class)
class FeedScrollBenchmark {
    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    @Test
    fun scrollFeed() = benchmarkRule.measureRepeated(
        packageName = "com.example.app",
        metrics = listOf(FrameTimingMetric()),
        compilationMode = CompilationMode.Partial(baselineProfileMode = BaselineProfileMode.Require),
        startupMode = StartupMode.WARM,
        iterations = 10,
        setupBlock = { uiAutomator { startApp(packageName) } },
    ) {
        uiAutomator { onElement { isScrollable }.fling(Direction.DOWN) }
    }
}
```

- `FrameTimingMetric`: read `frameOverrunMs` (API 31 and higher; positive means a missed deadline) and `frameDurationCpuMs` at **P95 and P99**, where jank lives.
- `StartupTimingMetric`: compare the **median** `timeToInitialDisplayMs` and `timeToFullDisplayMs`. Signal full display from Compose with `ReportDrawn`, `ReportDrawnWhen` or `ReportDrawnAfter`, not `reportFullyDrawn()`.
- `TraceSectionMetric` (experimental) with `Mode.Sum` counts and times a trace section. With composition tracing enabled, a pattern such as `"%FeedItem%"` counts how often a composable recomposed during the journey.
- Compare `CompilationMode.None()` with `CompilationMode.Partial(baselineProfileMode = BaselineProfileMode.Require)` to measure what the Baseline Profile buys.

### JankStats

`androidx.metrics:metrics-performance` reports per-frame jank from production: create a tracker with `JankStats.createAndTrack(window, listener)`, toggle `isTrackingEnabled` in `onResume`/`onPause`, and tag frames with the current screen through `PerformanceMetricsState.getHolderForHierarchy(view).state?.putState(...)`. The listener runs every frame on a non-UI thread and reuses its `FrameData`, so copy what you keep and return quickly.

## 3. Understand the problem by phase

Every frame runs **composition** (what to show), **layout** (measure, then place) and **drawing**. A state read registers a dependency with the phase that read it, and a change reruns that phase and every later one. Most fixes move work or reads out of composition, or stop invalidating an earlier phase from a later one.

| What the tools show | Probable cause | Fix |
|---|---|---|
| A composable recomposes every frame during scroll or animation | Fast-changing state read in composition | Defer the read (4.3) |
| Recompositions continue with no input, or a layout flickers for one frame | Backwards write | 4.4 |
| Long composition slices for a composable whose data did not change | Expensive calculation in the body | 4.1 |
| Many list items recompose when one item changes or moves | Missing lazy keys | 4.2 |
| Recomposition on every scroll pixel for a value that changes rarely | Missing `derivedStateOf` | 4.5 |
| Composable recomposes although its inputs look equal | Unstable parameter or new instances each time | 4.6 |
| Long measure slices in lists | Intrinsic measurements, subcomposition, nested layouts | 4.7 |
| Slow first launch or first use of a screen | Code interpreted and JIT-compiled | Baseline Profiles (5) |

## 4. Apply the documented fixes

### 4.1 Keep the composable body cheap

A composable can run on every animation frame. Do sorting, filtering, mapping and formatting in the ViewModel when possible; for purely presentational work, cache it with `remember` keyed on its inputs.

```kotlin
@Composable
fun ContactList(contacts: List<Contact>, comparator: Comparator<Contact>, modifier: Modifier = Modifier) {
    val sortedContacts = remember(contacts, comparator) { contacts.sortedWith(comparator) }
    LazyColumn(modifier) {
        items(sortedContacts, key = { it.id }) { contact -> ContactRow(contact) }
    }
}
```

### 4.2 Give lazy layouts stable keys

Without a `key`, moving one item makes Compose treat every following item as new. Provide a stable, unique key (and `contentType` for mixed item types). List-specific guidance lives in `compose-lists`.

### 4.3 Defer state reads to the latest phase

Pass a frequently changing value as a lambda so only the child that needs it reads it, then read it inside a lambda-based modifier so only layout or drawing reruns.

```kotlin
@Composable
private fun Title(snack: Snack, scrollProvider: () -> Int) {
    Column(modifier = Modifier.offset { IntOffset(x = 0, y = scrollProvider()) }) {
        Text(snack.name)
    }
}
```

| Instead of (read in composition) | Use (deferred) | Phase rerun on change |
|---|---|---|
| `Modifier.offset(x, y)` | `Modifier.offset { IntOffset(x, y) }` | Placement |
| `Modifier.alpha(a)` | `Modifier.graphicsLayer { alpha = a }` | Draw |
| `Modifier.rotate(d)` / `scale(s)` | `Modifier.graphicsLayer { rotationZ = d; scaleX = s; scaleY = s }` | Draw |
| `Modifier.background(color)` | `Modifier.drawBehind { drawRect(color) }` | Draw |

Be suspicious of any recomposition whose only effect is a new position, size or color.

### 4.4 Remove backwards writes

A backwards write changes state after an earlier phase (or an earlier scope in the same composition) has read it, forcing that phase to run again. The result is extra frames, a wrong first frame, or an endless loop.

- Write state from **events** (`onClick`, `onValueChange`) or effects, never in a composable body after it was read.
- Do not write state read in composition from `onSizeChanged`, `onGloballyPositioned`, a `LayoutModifier` or a draw block. Compute size-dependent layout inside layout instead (`Modifier.layout`, a custom `Layout`, `Modifier.aspectRatio`, `FlowRow`), and read sizes needed only for drawing in `drawWithCache`.
- Branch on window size classes hoisted from the window, not on locally measured sizes. `BoxWithConstraints` and `SubcomposeLayout` work but cost subcomposition; use them only when children truly differ by available space.
- Writing in layout and reading in draw, or measuring then reading in placement, flows forward and is fine.

### 4.5 Use derivedStateOf when outputs change less often than inputs

```kotlin
val showScrollToTop by remember { derivedStateOf { listState.firstVisibleItemIndex > 0 } }
```

Do not use it when the result changes as often as its inputs (for example concatenating two text fields). Effect-related usage is in `compose-side-effects`.

### 4.6 Stability, only when tools show skipping fails

With strong skipping (default since Kotlin 2.0.20), every restartable composable is skippable: unstable parameters are compared by instance (`===`) and stable ones with `equals`, and every lambda inside a composable is memoized automatically. Do not wrap lambdas in `remember` or rewrite them as method references for performance. So the question is usually "why is a **new instance** arriving", not "why is this class unstable".

Fix in this order:

1. **Stop producing new instances** for unchanged data (for example, a mapper that allocates new UI models on every emission). When a source such as Room re-emits equal but new objects, stable types compared with `equals` avoid the recomposition.
2. **Make the class immutable**: `val` properties of immutable types; use Compose state (`mutableStateOf`) for anything that must change.
3. **Collections**: `List`, `Set` and `Map` are always inferred unstable. Use kotlinx immutable collections (`ImmutableList`, `persistentListOf()`), or a wrapper class annotated `@Immutable`.
4. **Types you do not own or modules without the Compose compiler** (for example `java.time.LocalDateTime` or a data module's models): list them in a stability configuration file, enable the Compose compiler (runtime dependency only) on that module, or map them to UI models.

```kotlin
composeCompiler {
    stabilityConfigurationFiles.add(rootProject.layout.projectDirectory.file("compose_stability.conf"))
}
```

   `stabilityConfigurationFile` (singular) is deprecated in the Compose compiler Gradle plugin. The file takes one fully qualified name or wildcard (`com.example.data.*`, `com.example.data.**`) per line.

5. **`@Immutable` / `@Stable`** only when the class honors the contract. The compiler trusts them without checking; a wrong annotation makes UI stop updating.

Leave alone composables that rarely recompose, that only call skippable children, or whose many parameters have expensive `equals`. `@NonSkippableComposable` and `@DontMemoize` opt out of strong skipping when needed.

### 4.7 Keep layout passes cheap

- Avoid intrinsic measurements (`IntrinsicSize`) and subcomposition inside large lists.
- Prefer one custom `Layout` or `FlowRow`/`LazyVerticalGrid` over nested rows and columns that recompose to rearrange.
- For list items or composables that recompose every frame, hoist constant modifier chains to a top-level `val` so they are not reallocated. Do not restructure ordinary chains without evidence.
- Size images to their display size and give placeholders a fixed size (`compose-images`).

## 5. Startup and first-use jank: Baseline Profiles

Baseline Profiles let ART compile listed code ahead of time at install, improving code execution by about 30% from the first launch.

- Add a module with Android Studio's **Baseline Profile Generator** template, which applies the `androidx.baselineprofile` Gradle plugin and creates a generator and a benchmark.
- Cover critical user journeys, not just launch. Startup journeys go in a `collect` block with `includeInStartupProfile = true`; others must not.

```kotlin
@RunWith(AndroidJUnit4::class)
class BaselineProfileGenerator {
    @get:Rule
    val baselineProfileRule = BaselineProfileRule()

    @Test
    fun generate() = baselineProfileRule.collect(
        packageName = "com.example.app",
        includeInStartupProfile = true,
    ) {
        uiAutomator { startApp(packageName) }
    }
}
```

- Generate with `./gradlew :app:generateBaselineProfile` (or `generate<Variant>BaselineProfile`). Output lands in `src/<variant>/generated/baselineProfiles/`. Profiles are installed only for release builds.
- Verify the gain with the `CompilationMode` comparison in section 2 on a physical device.

## 6. Confirm the change

- Re-run the same Macrobenchmark on the same device, build type and compilation mode, before and after. Report P50/P90/P95/P99 frame metrics or median startup, not a single run.
- Re-check Layout Inspector counts for the same interaction to confirm the recomposition you targeted is gone.
- If numbers do not move, revert the change; an optimization without measured benefit is only added complexity.
- Keep a benchmark for journeys that regressed so CI catches the next regression.

## Checklist

- [ ] Timing came from a non-debuggable, R8-minified build, never from debug.
- [ ] The problem was located with a trace, recomposition counts or a benchmark before code changed.
- [ ] No backwards writes; no layout or draw callbacks write state read in composition.
- [ ] Fast-changing state is read in lambda modifiers or passed as lambdas.
- [ ] Lazy items have stable keys; expensive work is out of the composable body.
- [ ] Stability fixes target measured failures; annotations are honest.
- [ ] The app ships a generated Baseline Profile covering critical journeys.
- [ ] Before and after numbers were compared on the same setup.
