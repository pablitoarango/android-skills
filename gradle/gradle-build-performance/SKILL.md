---
name: gradle-build-performance
description: "Gradle build speed per Google's docs: Build Analyzer, gradle-profiler, configuration cache, build cache and remote CI cache, KSP, heap and GC tuning, AGP 9 defaults, Isolated Projects. Use when builds or sync are slow, tasks rerun with no changes, remote cache misses, configuration cache problems appear, kapt dominates, or garbage collection eats build time."
---

# Gradle Build Performance

Sources of truth: [Optimize your build speed](https://developer.android.com/build/optimize-your-build), [Profile your build](https://developer.android.com/build/profile-your-build), [Build Analyzer](https://developer.android.com/build/build-analyzer), [Gradle build overview](https://developer.android.com/build/gradle-build-overview), [Migrate to KSP](https://developer.android.com/build/migrate-to-ksp), [Built-in Kotlin (AGP 9)](https://developer.android.com/build/migrate-to-built-in-kotlin), [AGP 9.0 release notes](https://developer.android.com/build/releases/agp-9-0-0-release-notes). Gradle facts: [build cache](https://docs.gradle.org/current/userguide/build_cache.html), [configuration cache](https://docs.gradle.org/current/userguide/configuration_cache.html), [Isolated Projects](https://docs.gradle.org/current/userguide/isolated_projects.html), [build environment](https://docs.gradle.org/current/userguide/build_environment.html).

## How to work on a slow build

Google splits the job into two stages: apply the configuration changes that help almost every Android project, then profile to find what is specific to this project or machine.

1. **Name the build that hurts.** Usually an incremental debug build after a code edit, sometimes sync or a CI job. Time it several times. The first build after the Gradle daemon starts is slower because the JVM warms up, so do not count it.
2. **Close the gaps in the baseline setup.** Check the project against sections 3 to 5: current Android Studio and AGP, KSP, the Gradle properties, Jetifier, static debug values. Deploy to a device on API 24 or higher while developing.
3. **Profile what is left.** Build Analyzer first. Use gradle-profiler when you need numbers you can compare, and build scans for CI.
4. **Treat tuning as an experiment.** Heap size, GC, worker count and shrinking gain different amounts on different projects and machines, and a bigger heap can slow a low-memory machine. Change one variable, rerun the identical scenario, and keep the change only if the gain is larger than run-to-run variation.

## 1. Measuring tools

### Build Analyzer

Build the project in Android Studio, then open **View > Tool Windows > Build** and the **Build Analyzer** tab. Compare several builds, because results vary. It shows:

- Plugins and tasks that determine the build's duration (grouped by category on AGP 8.0+).
- Warnings: **always-run tasks** (missing input/output declarations, or `upToDateWhen` returning false), **task setup issues** (several tasks writing the same output directory), **non-incremental annotation processors**, configuration cache not enabled (it can run the compatibility check and turn the cache on), and a **Jetifier** check.
- Time and failed requests per repository in **Downloads**. Downloads during incremental builds point to dynamic versions or a repository to move down or remove.
- On Windows, antivirus scanning of Gradle directories.

### Gradle `--profile`

```bash
./gradlew clean
./gradlew --profile --offline --rerun-tasks assembleDebug
./gradlew --profile --offline assembleDebug
```

The report lands in `build/reports/profile/`. The `--rerun-tasks` run times every task. The second run, with no changes, should show tasks as `UP-TO-DATE`. A task that still executes (for example a manifest processing task) means something in the build changes an input on every build. Build once without `--offline` first so dependencies are cached.

### gradle-profiler

Benchmark mode runs a scenario repeatedly and writes an HTML report to `profile-out/`. It can apply edits between runs:

```text
body_edit {
    tasks = [":app:assembleDebug"]
    apply-non-abi-change-to = ["core/data/src/main/kotlin/com/example/data/ArticleRepository.kt"]
}
public_api_edit {
    tasks = [":app:assembleDebug"]
    apply-abi-change-to = ["core/model/src/main/kotlin/com/example/model/Article.kt"]
}
strings_edit {
    tasks = [":app:assembleDebug"]
    apply-android-resource-value-change-to = "app/src/main/res/values/strings.xml"
}
full_rebuild_heap_8g {
    tasks = [":app:assembleDebug"]
    cleanup-tasks = ["clean"]
    jvm-args = ["-Xmx8g"]
}
```

```bash
gradle-profiler --benchmark --project-dir . --scenario-file performance.scenarios
```

Also useful: `apply-android-layout-change-to`, `gradle-args = ["--max-workers=4"]`, and `version = [...]` to compare Gradle versions.

### Build scans

`./gradlew assembleDebug --scan` publishes a scan with the task timeline, parallelism, build cache hits and misses, and dependency resolution time. Use it on CI, where Build Analyzer is not available.

## 2. Reading a build by lifecycle phase

Every Gradle build runs three phases in order. Find the slow phase before choosing a fix.

### Initialization

Gradle evaluates `settings.gradle.kts`, decides which projects take part, and builds the classpaths for build scripts and plugins, including compiling included builds such as `build-logic`.

- **Looks like:** a long pause before any project is configured; slow right after build logic or plugin versions change.
- **Levers:** few, well-filtered repositories; small, stable build logic; no work in settings beyond declarations.

### Configuration

Gradle runs every applied build script and plugin and registers tasks. The result is the task graph. Configuration code cannot use files that execution will produce. Unless the configuration cache is reused, this phase runs on every invocation, and IDE sync always runs it.

- **Looks like:** "Configuring projects" dominates the profile; even `./gradlew help` is slow; sync is slow.
- **Levers:** the configuration cache; moving logic out of build scripts into tasks (Google's guidance), so it runs only when needed and can be cached; lazy task registration; providers instead of eager reads; no dependency resolution, file reading or network calls while configuring; Isolated Projects for parallel configuration.

### Execution

Gradle runs the tasks in the graph whose inputs changed and skips the rest (`UP-TO-DATE`) or loads their outputs (`FROM-CACHE`).

- **Looks like:** a few tasks dominate Build Analyzer; tasks that execute without source changes; kapt or resource merging near the top.
- **Levers:** build cache, parallel execution, KSP, smaller modules with `implementation` dependencies, static debug values, WebP images and no PNG crunching.

## 3. gradle.properties

```properties
org.gradle.jvmargs=-Xmx6g -XX:MaxMetaspaceSize=1g -XX:+HeapDumpOnOutOfMemoryError -XX:+UseParallelGC -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
android.enableJetifier=false
```

| Property | Gradle default | What turning it on does |
|---|---|---|
| `org.gradle.parallel` | `false` | Runs tasks of different projects at the same time, up to `org.gradle.workers.max` |
| `org.gradle.caching` | off | Stores task outputs by input fingerprint; a later build on any branch or machine with the same inputs loads them instead of running the task |
| `org.gradle.configuration-cache` | off | Saves the task graph and skips configuration when nothing that influenced it has changed |
| `org.gradle.jvmargs` | `-Xmx512m -XX:MaxMetaspaceSize=384m` | Replaces the daemon's JVM arguments entirely |

- **Configuration cache.** Check compatibility first with Build Analyzer. The first build prints that no configuration cache is available; later builds print `Reusing configuration cache.` Gradle fails the build on configuration-cache problems by default; keep that. Google's page shows `org.gradle.configuration-cache.problems=warn` and warns to use it with care. Use it only for a diagnostic run, fix what it reports, then remove it.
- **JVM arguments.** Because `org.gradle.jvmargs` replaces the defaults, always pass `-XX:MaxMetaspaceSize` and `-XX:+HeapDumpOnOutOfMemoryError` with it (Google cites Gradle issue #19750; use `MaxMetaspaceSize=1g` once you raise the heap). Try the parallel collector, since JDK 9+ defaults to G1. Raise `-Xmx` (4g, 6g, 8g) only when Build Analyzer shows garbage collection above about 15% of build time, and benchmark each step. The Kotlin compiler daemon has its own `kotlin.daemon.jvmargs`; tune it separately if Kotlin compilation runs short of memory.
- **Jetifier.** Remove it after Build Analyzer's check confirms no dependency still uses the Support Library.
- **R classes.** Non-transitive and non-constant R classes are AGP 8.0+ defaults. AGP 9 also compiles app modules against a non-final R class (`android.enableAppCompileTimeRClass`). Do not re-add old R class flags.

### Worth measuring, not defaults

- `org.gradle.configuration-cache.parallel=true` loads and stores the configuration cache in parallel. It is incubating and not every build is compatible.
- `org.gradle.isolated-projects=true` configures projects in parallel and also speeds up sync. It is incubating, Gradle does not yet recommend it for production, it requires configuration-cache compatibility, and plugins often need changes. Now in Android enables it. Try it on a branch with current Gradle, AGP and Android Studio.

### AGP 9 defaults that affect speed

The AGP Upgrade Assistant can write flags into `gradle.properties` to keep AGP 8.13 behavior. After upgrading, look for these and remove them once the project works without them:

- `android.defaults.buildfeatures.resvalues=true`: enable `buildFeatures.resValues` only in modules that use it.
- `android.dependency.useConstraints=true`: the AGP 9 default (`false`) also shortens project import when there are many library modules.
- `android.onlyEnableUnitTestForTheTestedBuildType=false`: the new default creates unit tests only for the tested build type.
- `android.enableAppCompileTimeRClass=false`: needed only while app code uses R fields as constants, for example in `when` branches.

## 4. Annotation processing: KSP, not kapt

- kapt generates Java stubs from Kotlin before processing, which is expensive, and it is in maintenance mode. KSP reads Kotlin directly and is up to twice as fast.
- Migrate per module: apply `com.google.devtools.ksp` (declared `apply false` in the root), switch `kapt(...)` to `ksp(...)`, pass processor arguments in KSP's format, then remove the kapt plugin and any `kapt {}` block. Dagger/Hilt, Room, Moshi and Glide support KSP; some libraries (Glide) use a different artifact.
- Stub generation continues while **any** kapt processor remains in a module, so most of the speedup comes only when the last one is gone.
- KSP types are more precise (for example nullability), so the migration may need small source fixes.
- Data Binding has no KSP support. Isolate it in its own modules; on AGP 9 those modules need `com.android.legacy-kapt`, since `kotlin-kapt` does not work with built-in Kotlin.
- Take the KSP version from the [KSP releases](https://github.com/google/ksp/releases) page. AGP 9 raises older KSP and Kotlin Gradle plugin versions to its own minimum.

## 5. Build configuration

- **Debug builds use static values.** A version code, version name, manifest entry or resource that changes every build (timestamp, git hash, CI number) forces a full app build and prevents quick apply. Compute such values only for release variants, as task outputs wired in through `androidComponents.onVariants(selector().withBuildType("release"))`.
- **Fixed dependency versions.** Dynamic versions make Gradle check for updates and produce unexpected upgrades.
- **Only the resources you test.** A dev flavor does not need every language and density. `resourceConfigurations` is deprecated since AGP 8.8; for language filtering in apps, AGP points to `androidResources.localeFilters`.
- **Images.** Convert to WebP. PNG crunching is already off for debug; turn it off for release too (`isCrunchPngs = false`) when images are already optimized.
- **Repositories.** Declare few, filter them by content, and try `gradlePluginPortal()` last (see `gradle-build-logic`).
- **Modules without Kotlin on AGP 9.** `android { enableKotlin = false }` removes the Kotlin compile task.

## 6. Build logic and custom tasks

- Shared logic lives in convention plugins in an included `build-logic` build (see `gradle-build-logic`). A change to build logic recompiles it and invalidates configuration for its users, so keep it stable and small.
- Register tasks with `tasks.register(...)` and configure groups with `tasks.withType<T>().configureEach { }`. `tasks.create`, `tasks.getByName` and eager `withType(T) { }` realize tasks that the build may never run.
- Keep build scripts free of work. Read external values through providers so Gradle can track them as inputs, and derive anything expensive in a task. This release-only field needs `buildFeatures.buildConfig = true` in that module:

```kotlin
val buildNumber = providers.environmentVariable("BUILD_NUMBER").orElse("0")

androidComponents {
    onVariants(selector().withBuildType("release")) { variant ->
        variant.buildConfigFields?.put(
            "BUILD_NUMBER",
            buildNumber.map { BuildConfigField("String", "\"$it\"", null) },
        )
    }
}
```

- A custom task declares every input and output with annotations, gets its own output directory, and uses `@PathSensitive(PathSensitivity.RELATIVE)` for file inputs so its cache key does not depend on the checkout location. Mark it `@CacheableTask` when its work costs more than downloading the result.
- Do not resolve configurations or call `.get()` on task-derived providers at configuration time.

## 7. Modules

- Split large modules. Gradle then recompiles only what changed, caches outputs per module, and runs more work in parallel.
- Use `implementation` so an internal change does not recompile dependents; `api` only for types in the module's public API.
- Use plain Kotlin/JVM modules for code that needs no Android APIs or resources.

## 8. Symptoms and causes

| Symptom | Check first | Usual fix |
|---|---|---|
| Configuration slow on every build | Configuration cache off or rejected; I/O or resolution in scripts | Fix cache problems, move work into tasks, lazy APIs |
| Sync slow | Many projects configured sequentially; eager plugins | Lazy APIs, AGP 9 `useConstraints` default, try Isolated Projects |
| Tasks execute with no source change | Build Analyzer always-run and task setup warnings; volatile inputs in debug | Declare inputs and outputs, separate output directories, static debug values |
| Kotlin compile dominates | kapt, ABI changes in widely used modules, `api` edges | KSP, smaller modules, `implementation` |
| Remote cache misses between machines | Absolute paths in inputs, different JDKs, non-relocatable tasks | Relative path sensitivity, one JDK version everywhere |
| High GC share | Heap too small for the project | Raise `-Xmx` in steps and benchmark |
| Downloads in incremental builds | Dynamic versions, unfiltered or failing repositories | Fixed versions, content filters, fewer repositories |

## 9. CI and the remote build cache

Configure the cache in `settings.gradle.kts`. The local cache is on by default. For a remote cache, clean CI builds should write entries and every other build should only read them:

```kotlin
val remoteCacheUrl = providers.gradleProperty("myapp.remoteCacheUrl")
val isCiBuild = providers.environmentVariable("CI").isPresent

buildCache {
    remote<HttpBuildCache> {
        isEnabled = remoteCacheUrl.isPresent
        if (remoteCacheUrl.isPresent) {
            url = uri(remoteCacheUrl.get())
        }
        isPush = isCiBuild
        credentials {
            username = providers.environmentVariable("MYAPP_REMOTE_CACHE_LOGIN").orNull
            password = providers.environmentVariable("MYAPP_REMOTE_CACHE_SECRET").orNull
        }
    }
}
```

- Put the URL in `gradle.properties` or `~/.gradle/gradle.properties` and the credentials in CI secrets; never commit credentials. Credentials go over HTTP Basic auth, so use HTTPS. `isAllowInsecureProtocol` and `isAllowUntrustedServer` exist for exceptional setups only.
- Use the same JDK version on CI and developer machines, or outputs from one will not match inputs on the other.
- Invoke the tasks a change needs (`:feature:articles:testDebugUnitTest`) rather than a broad task with `-x` exclusions.
- Publish build scans from CI to follow cache hit rates and build time over time.

## 10. Checklist

- [ ] The slow scenario is named and timed over several warm runs.
- [ ] Android Studio and AGP are current; Build Analyzer warnings are resolved or explained.
- [ ] `org.gradle.jvmargs` keeps metaspace and heap-dump flags; heap and GC changes were benchmarked.
- [ ] Parallel execution, build cache and configuration cache are on, with configuration-cache problems failing the build.
- [ ] Jetifier is off; leftover AGP 8.13 compatibility flags are removed.
- [ ] No kapt in modules whose processors support KSP.
- [ ] Debug variants use static values; dependency versions are fixed.
- [ ] Build scripts do no I/O or resolution while configuring; tasks are registered lazily and declare inputs and outputs.
- [ ] CI writes to the remote cache, developers read from it, and CI publishes build scans.
