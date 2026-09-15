---
name: gradle-build-logic
description: "Gradle build logic per Google's build docs: settings and repositories, version catalogs, convention plugins, Kotlin DSL, AGP 9 built-in Kotlin and new DSL, the Compose Compiler plugin. Use for build.gradle.kts, settings.gradle.kts, convention plugin, or libs.versions.toml changes, and for AGP 9 upgrade errors (kotlinOptions, kapt, applicationVariants) or config copied between modules."
---

# Android Gradle Build Logic

Sources of truth: [Gradle build overview](https://developer.android.com/build/gradle-build-overview), [Configure your build](https://developer.android.com/build), [Migrate to version catalogs](https://developer.android.com/build/migrate-to-catalogs), [Add build dependencies](https://developer.android.com/build/dependencies), [Modularization patterns](https://developer.android.com/topic/modularization/patterns), [Built-in Kotlin (AGP 9)](https://developer.android.com/build/migrate-to-built-in-kotlin), [AGP 9.0 release notes](https://developer.android.com/build/releases/agp-9-0-0-release-notes), [Compose Compiler Gradle plugin](https://developer.android.com/develop/ui/compose/compiler), [Migrate to KSP](https://developer.android.com/build/migrate-to-ksp). Reference implementation: [Now in Android](https://github.com/android/nowinandroid).

## 1. Principles

- **(stricter than Google)** Write build files in **Kotlin DSL** (`*.gradle.kts`). Google strongly recommends Kotlin; this skill requires it.
- Build files describe **what** a module is: plugins, namespace, dependencies. The **how** (logic, task declarations) belongs in plugins, which can be tested and reused. Google's build overview makes this split explicit.
- Share configuration through **convention plugins**, never by copying blocks between modules or through `allprojects` / `subprojects`.
- Every plugin and library version is declared once, in the **version catalog**, as a fixed version (dynamic versions such as `2.+` slow builds and make them unpredictable).
- Take current versions of AGP, Gradle, Kotlin, KSP and libraries from their release pages ([AGP](https://developer.android.com/build/releases/gradle-plugin), [KSP](https://github.com/google/ksp/releases), [Compose BOM](https://developer.android.com/develop/ui/compose/bom)). Never copy a version from a sample.

## 2. Where each piece lives

| File | Contains |
|---|---|
| `settings.gradle.kts` | Repositories for plugins and libraries, `includeBuild("build-logic")`, the list of modules |
| `build.gradle.kts` (root) | Every external plugin the build uses, declared `apply false`; no configuration |
| `gradle/libs.versions.toml` | Versions, libraries and plugins, including the project's own convention plugin IDs |
| `gradle.properties` | Gradle and AGP flags (see `gradle-build-performance`) |
| `build-logic/settings.gradle.kts` | Repositories and the shared catalog for the included build |
| `build-logic/convention/build.gradle.kts` | `kotlin-dsl`, `compileOnly` Gradle plugin artifacts, plugin registrations |
| `build-logic/convention/src/main/kotlin/` | One `Plugin<Project>` class per convention, plus internal `configure*` helpers |
| `<module>/build.gradle.kts` | Convention plugin aliases, `namespace`, the module's own dependencies |

**(stricter than Google)** Put convention plugins in an included build named `build-logic`, not in `buildSrc`. An included build is an ordinary build with explicit dependencies, which makes the boundary visible; editing it still invalidates configuration-cache entries that depend on it, so measure rather than assume.

Declaring every plugin with `apply false` in the root build file puts them all on one shared build classpath, so two modules cannot end up with different versions of a plugin's transitive dependencies:

```kotlin
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.compose.compiler) apply false
    alias(libs.plugins.hilt) apply false
    alias(libs.plugins.ksp) apply false
}
```

## 3. settings.gradle.kts

```kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        google {
            content {
                includeGroupByRegex("androidx.*")
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        google {
            content {
                includeGroupByRegex("androidx.*")
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
            }
        }
        mavenCentral()
    }
}

enableFeaturePreview("TYPESAFE_PROJECT_ACCESSORS")

rootProject.name = "myapp"
include(":app")
include(":core:data")
include(":feature:articles")
```

- `includeBuild("build-logic")` inside `pluginManagement` is what makes convention plugin IDs resolvable from module `plugins {}` blocks.
- Repositories are declared only here. `FAIL_ON_PROJECT_REPOS` turns a `repositories {}` block in any module into a build error.
- Gradle queries repositories in declaration order. The content filter keeps Google Maven from being asked for artifacts it does not host, and `gradlePluginPortal()` goes last. Android Studio's template lists the portal first; Google's build speed guide recommends trying it last, because AGP and most Android plugins live in Google Maven or Maven Central.
- `TYPESAFE_PROJECT_ACCESSORS` generates `projects.core.data` style accessors. Without it, module build files must use `project(":core:data")`.
- Add a third-party repository only when a dependency needs it, and filter it to that dependency's group.

## 4. Version catalog

Keep the catalog at the default path `gradle/libs.versions.toml`; renaming it requires extra build configuration. Excerpt:

```toml
[versions]
agp = "..."
kotlin = "..."
ksp = "..."
hilt = "..."
composeBom = "..."
compileSdk = "..."
minSdk = "..."
targetSdk = "..."

[libraries]
androidx-compose-bom = { module = "androidx.compose:compose-bom", version.ref = "composeBom" }
androidx-compose-material3 = { module = "androidx.compose.material3:material3" }
androidx-compose-ui-tooling = { module = "androidx.compose.ui:ui-tooling" }
androidx-compose-ui-tooling-preview = { module = "androidx.compose.ui:ui-tooling-preview" }
hilt-android = { module = "com.google.dagger:hilt-android", version.ref = "hilt" }
hilt-compiler = { module = "com.google.dagger:hilt-compiler", version.ref = "hilt" }
android-gradleApi = { module = "com.android.tools.build:gradle-api", version.ref = "agp" }
compose-gradlePlugin = { module = "org.jetbrains.kotlin:compose-compiler-gradle-plugin", version.ref = "kotlin" }
ksp-gradlePlugin = { module = "com.google.devtools.ksp:com.google.devtools.ksp.gradle.plugin", version.ref = "ksp" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
android-library = { id = "com.android.library", version.ref = "agp" }
compose-compiler = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
hilt = { id = "com.google.dagger.hilt.android", version.ref = "hilt" }
ksp = { id = "com.google.devtools.ksp", version.ref = "ksp" }
myapp-android-application = { id = "myapp.android.application" }
myapp-android-library = { id = "myapp.android.library" }
myapp-android-library-compose = { id = "myapp.android.library.compose" }
myapp-android-feature = { id = "myapp.android.feature" }
myapp-hilt = { id = "myapp.hilt" }
```

- Aliases are **kebab-case**, as Google recommends for code completion. Separators become dots in accessors: `androidx-compose-material3` is `libs.androidx.compose.material3`.
- Artifacts versioned by a BOM (Compose, Firebase, OkHttp) have no version; modules add `platform(libs.androidx.compose.bom)`.
- The `com.android.tools.build:gradle-api` and `*-gradlePlugin` libraries exist only so `build-logic` can compile against those plugins' APIs.
- For the project's own convention plugins, use versionless `[plugins]` entries and apply them with `alias(...)`, as Now in Android does. Google's catalog guide applies convention plugins with `id("...")` instead; pick one style per project.
- Migrate an existing build one entry at a time: add the catalog entry, sync, then replace the string declaration. Old and catalog declarations work side by side during the migration.

## 5. AGP 9: built-in Kotlin and the new DSL

- **Built-in Kotlin is on by default.** Remove `org.jetbrains.kotlin.android` from module and root build files and from the catalog. Kotlin Multiplatform library modules still use `org.jetbrains.kotlin.multiplatform` with `com.android.kotlin.multiplatform.library`.
- Configure the compiler with top-level `kotlin { compilerOptions { ... } }`; `android.kotlinOptions` is gone. `jvmTarget` defaults to `android.compileOptions.targetCompatibility`, so set it only when it must differ.
- Extra Kotlin source directories go in `android.sourceSets.named("main") { kotlin.directories += "..." }`. `kotlin.sourceSets` and `java.directories` for Kotlin sources are unsupported. Generated or per-variant directories use `variant.sources.kotlin` in `androidComponents.onVariants`.
- `org.jetbrains.kotlin.kapt` does not work with built-in Kotlin. Move processors to **KSP** (`ksp(...)` plus `com.google.devtools.ksp`). Processors without KSP support, such as Data Binding, need `com.android.legacy-kapt` at the AGP version; keep them in their own modules.
- Modules without Kotlin sources: `android { enableKotlin = false }` removes the Kotlin compile task and the implicit Kotlin stdlib dependency.
- AGP 9 brings in the Kotlin Gradle plugin at runtime and raises older KGP and KSP versions to its minimum. To use a newer KGP or KSP than AGP bundles, add it to the root `buildscript { dependencies { classpath(...) } }` as the release notes show.
- **New DSL is on by default** (`android.newDsl=true`): the legacy implementation classes and the old variant API (`applicationVariants`, `libraryVariants`) are unavailable. Convention plugins must use `com.android.build.api.dsl` types (`ApplicationExtension`, `LibraryExtension`, `CommonExtension`) and `androidComponents` for per-variant work.
- AGP 9 changed defaults a build may silently rely on: `targetSdk` now falls back to `compileSdk` (set it explicitly for apps and tests), and `resValues` is off unless a module sets `buildFeatures.resValues = true`. See the release notes table for the rest.
- **Temporary opt-outs**: `android.builtInKotlin=false` together with `android.newDsl=false` keeps `org.jetbrains.kotlin.android` working; AGP 9.4 also accepts `android.newDsl.optOut=:module` for individual modules. To migrate built-in Kotlin module by module, set `android.builtInKotlin=false` and apply `com.android.built-in-kotlin` to each migrated module. AGP 10 removes these opt-outs; delete them as soon as plugins allow.

## 6. Convention plugins

### build-logic/settings.gradle.kts

```kotlin
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}

rootProject.name = "build-logic"
include(":convention")
```

### build-logic/convention/build.gradle.kts

```kotlin
plugins {
    `kotlin-dsl`
}

dependencies {
    compileOnly(libs.android.gradleApi)
    compileOnly(libs.compose.gradlePlugin)
    compileOnly(libs.ksp.gradlePlugin)
}

tasks.validatePlugins {
    enableStricterValidation = true
    failOnWarning = true
}

gradlePlugin {
    plugins {
        register("androidApplication") {
            id = libs.plugins.myapp.android.application.get().pluginId
            implementationClass = "AndroidApplicationConventionPlugin"
        }
        register("androidLibrary") {
            id = libs.plugins.myapp.android.library.asProvider().get().pluginId
            implementationClass = "AndroidLibraryConventionPlugin"
        }
        register("androidLibraryCompose") {
            id = libs.plugins.myapp.android.library.compose.get().pluginId
            implementationClass = "AndroidLibraryComposeConventionPlugin"
        }
        register("hilt") {
            id = libs.plugins.myapp.hilt.get().pluginId
            implementationClass = "HiltConventionPlugin"
        }
    }
}
```

- Plugin artifacts are `compileOnly`: the real plugin versions come from the root build's `apply false` declarations.
- When an alias is also the prefix of another (`myapp-android-library` and `myapp-android-library-compose`), the shorter accessor needs `.asProvider()`.

### Shared helpers

```kotlin
internal val Project.libs: VersionCatalog
    get() = extensions.getByType<VersionCatalogsExtension>().named("libs")

internal fun Project.configureAndroid(commonExtension: CommonExtension) {
    commonExtension.apply {
        compileSdk = libs.findVersion("compileSdk").get().requiredVersion.toInt()
        defaultConfig.minSdk = libs.findVersion("minSdk").get().requiredVersion.toInt()
        compileOptions.sourceCompatibility = JavaVersion.VERSION_17
        compileOptions.targetCompatibility = JavaVersion.VERSION_17
    }
}
```

SDK levels live in the catalog so one edit changes every module.

### Application and library plugins

```kotlin
class AndroidApplicationConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply("com.android.application")
        extensions.configure<ApplicationExtension> {
            configureAndroid(this)
            defaultConfig.targetSdk = libs.findVersion("targetSdk").get().requiredVersion.toInt()
        }
    }
}

class AndroidLibraryConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply("com.android.library")
        extensions.configure<LibraryExtension> {
            configureAndroid(this)
        }
    }
}
```

### Compose plugin

```kotlin
internal fun Project.configureAndroidCompose(commonExtension: CommonExtension) {
    commonExtension.buildFeatures.compose = true
    dependencies {
        val bom = platform(libs.findLibrary("androidx-compose-bom").get())
        add("implementation", bom)
        add("androidTestImplementation", bom)
        add("implementation", libs.findLibrary("androidx-compose-ui-tooling-preview").get())
        add("debugImplementation", libs.findLibrary("androidx-compose-ui-tooling").get())
    }
    extensions.configure<ComposeCompilerGradlePluginExtension> {
        @Suppress("UnstableApiUsage")
        stabilityConfigurationFiles.add(
            isolated.rootProject.projectDirectory.file("compose_stability.conf"),
        )
    }
}

class AndroidLibraryComposeConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply("myapp.android.library")
        pluginManager.apply("org.jetbrains.kotlin.plugin.compose")
        configureAndroidCompose(extensions.getByType<LibraryExtension>())
    }
}
```

- Every Compose module needs the Compose Compiler Gradle plugin (`org.jetbrains.kotlin.plugin.compose`, Kotlin 2.0+), versioned with Kotlin, plus `buildFeatures.compose = true`.
- Read root-level files through `isolated.rootProject` rather than `rootProject`, so the plugin stays compatible with Gradle's Isolated Projects.
- Compiler reports and metrics (`reportsDestination`, `metricsDestination`) are opt-in, typically behind a Gradle property, for performance investigations (see `compose-performance`).

### Hilt plugin

```kotlin
class HiltConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply("com.google.devtools.ksp")
        dependencies {
            add("ksp", libs.findLibrary("hilt-compiler").get())
        }
        pluginManager.withPlugin("com.android.base") {
            pluginManager.apply("com.google.dagger.hilt.android")
            dependencies {
                add("implementation", libs.findLibrary("hilt-android").get())
            }
        }
    }
}
```

`pluginManager.withPlugin` reacts to whichever Android plugin the module applies, so one Hilt convention serves apps and libraries.

### Feature plugin

A feature convention applies the library and Compose conventions and Hilt, then adds what every feature module needs (`:core:ui`, lifecycle and navigation artifacts). Module boundaries and allowed dependencies are defined in `android-architecture`.

## 7. Module build files

```kotlin
plugins {
    alias(libs.plugins.myapp.android.feature)
}

android {
    namespace = "com.example.feature.articles"
}

dependencies {
    implementation(projects.core.data)
}
```

- A module file applies conventions, sets `namespace`, and lists its own dependencies. Anything a second module would copy belongs in a convention plugin.
- Use `implementation` unless a type from the dependency appears in the module's public API; only then use `api`.
- Keep values that change between builds (CI version codes, timestamps, git hashes) out of debug variants; see `gradle-build-performance`.

## 8. Checklist

- [ ] All build files are Kotlin DSL; module files contain no logic or task declarations.
- [ ] Repositories exist only in settings, with `FAIL_ON_PROJECT_REPOS`, filtered Google Maven, and the Plugin Portal last.
- [ ] Conventions live in the `build-logic` included build; their plugin artifacts are `compileOnly`.
- [ ] Every version is fixed and declared once in `libs.versions.toml` with kebab-case aliases; the root build file declares all plugins `apply false`.
- [ ] AGP 9+: no `org.jetbrains.kotlin.android`, no `kotlinOptions`, no `kotlin-kapt`, no legacy variant API; `targetSdk` set explicitly.
- [ ] Temporary `android.builtInKotlin=false` / `android.newDsl=false` opt-outs have an owner and a removal plan.
- [ ] Compose modules get the Compose Compiler plugin, `buildFeatures.compose` and the BOM from a convention plugin.
