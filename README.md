# android-skills

Agent skills for modern Android development with Kotlin and Jetpack Compose. Every skill follows Google's official documentation; a skill only goes further than Google where a rule is stricter, and those rules are marked `(stricter than Google)`.

## Skills

### Architecture

| Skill | Covers | Sources |
|---|---|---|
| `android-architecture` | Layers, dependency direction, Hilt, modularization, models per layer, naming | [Guide to app architecture](https://developer.android.com/topic/architecture), [Recommendations](https://developer.android.com/topic/architecture/recommendations), [Modularization patterns](https://developer.android.com/topic/modularization/patterns) |
| `android-domain-layer` | When to add use cases, naming, invoke, main-safety, testing | [Domain layer](https://developer.android.com/topic/architecture/domain-layer) |
| `android-data-layer` | Repositories, data sources, models, lifetimes, errors, caching, offline-first | [Data layer](https://developer.android.com/topic/architecture/data-layer), [Offline-first](https://developer.android.com/topic/architecture/data-layer/offline-first) |
| `android-viewmodel` | UI state production, events as state, lifecycle-aware collection | [UI layer](https://developer.android.com/topic/architecture/ui-layer), [State production](https://developer.android.com/topic/architecture/ui-layer/state-production), [UI events](https://developer.android.com/topic/architecture/ui-layer/events) |

### UI

| Skill | Covers | Sources |
|---|---|---|
| `compose-ui` | remember and saveable state, state hoisting, screen vs reusable composables, component API conventions, modifiers, lifecycle effects, CompositionLocal, Material 3 theming, resources, previews | [State hoisting](https://developer.android.com/develop/ui/compose/state-hoisting), [API guidelines](https://android.googlesource.com/platform/frameworks/support/+/androidx-main/compose/docs/compose-component-api-guidelines.md), [CompositionLocal](https://developer.android.com/develop/ui/compose/compositionlocal) |
| `compose-side-effects` | Effect APIs, effect keys, derivedStateOf, snapshotFlow, backwards writes | [Side-effects](https://developer.android.com/develop/ui/compose/side-effects) |
| `compose-lists` | Lazy lists, grids, pagers, keys, contentType, Paging | [Lists and grids](https://developer.android.com/develop/ui/compose/lists), [Pager](https://developer.android.com/develop/ui/compose/layouts/pager) |
| `compose-adaptive-layouts` | Window size classes, canonical layouts, NavigationSuiteScaffold | [Adaptive apps](https://developer.android.com/develop/ui/compose/layouts/adaptive) |
| `compose-navigation` | Navigation 3 back stacks, entry decorators and lifecycle, ViewModel keys, scenes, transitions, results, deep links, modular features, Navigation 2 migration | [Navigation 3](https://developer.android.com/guide/navigation/navigation-3), [nav3-recipes](https://github.com/android/nav3-recipes) |
| `compose-performance` | Release builds, composition tracing, Layout Inspector, Macrobenchmark and JankStats, phases and deferred reads, backwards writes, stability, Baseline Profiles | [Compose performance](https://developer.android.com/develop/ui/compose/performance), [Stability](https://developer.android.com/develop/ui/compose/performance/stability) |
| `compose-images` | painterResource vs AsyncImage, Coil 3, sizing and downsampling, lists, painter state, ImageLoader with OkHttp and caching, previews, tests | [Loading images](https://developer.android.com/develop/ui/compose/graphics/images/loading), [Coil](https://coil-kt.github.io/coil/compose/) |
| `compose-accessibility` | Touch targets, labels, semantics properties, merging and clearing, custom actions, traversal, text scaling, contrast, debugging, automated checks | [Accessibility in Compose](https://developer.android.com/develop/ui/compose/accessibility) |

### Async

| Skill | Covers | Sources |
|---|---|---|
| `android-coroutines` | Dispatchers, main-safety, scopes, Flow context and sharing, lifecycle collection, cancellation, timeouts, exceptions, shared state, testing, concurrency review | [Coroutines best practices](https://developer.android.com/kotlin/coroutines/coroutines-best-practices), [Kotlin flows](https://developer.android.com/kotlin/flow), [Testing coroutines](https://developer.android.com/kotlin/coroutines/test) |
| `android-retrofit` | Retrofit declarations and return types, remote data sources, OkHttp and Hilt setup, interceptors, auth, logging, errors, security, R8, MockWebServer | [Data layer](https://developer.android.com/topic/architecture/data-layer), [Connect to the network](https://developer.android.com/develop/connectivity/network-ops/connecting), [Retrofit](https://lysine.dev/retrofit/), [OkHttp](https://lysine.dev/okhttp/) |

### Testing

| Skill | Covers | Sources |
|---|---|---|
| `android-testing` | Test scopes per layer, fakes, ViewModel and Flow tests, Hilt test bindings, Room DAO tests, Robolectric, Roborazzi and Compose Preview Screenshot Testing | [Testing strategies](https://developer.android.com/training/testing/fundamentals/strategies), [Test doubles](https://developer.android.com/training/testing/fundamentals/test-doubles), [Testing flows](https://developer.android.com/kotlin/flow/test) |
| `compose-testing` | Compose test rules, finders, synchronization, state restoration, accessibility checks | [Testing Compose](https://developer.android.com/develop/ui/compose/testing) |
| `android-emulator` | Android CLI and adb for AVDs, deploying APKs, UI layout, input, screenshots, logcat; Gradle Managed Devices | [Android CLI](https://developer.android.com/tools/agents/android-cli), [Emulator command line](https://developer.android.com/studio/run/emulator-commandline), [adb](https://developer.android.com/tools/adb), [Gradle Managed Devices](https://developer.android.com/studio/test/gradle-managed-devices) |

### Build

| Skill | Covers | Sources |
|---|---|---|
| `gradle-build-logic` | Settings and repositories, version catalogs, convention plugins, AGP 9 built-in Kotlin and new DSL, Compose Compiler plugin | [Gradle build overview](https://developer.android.com/build/gradle-build-overview), [Version catalogs](https://developer.android.com/build/migrate-to-catalogs), [Built-in Kotlin](https://developer.android.com/build/migrate-to-built-in-kotlin) |
| `gradle-build-performance` | Build Analyzer, gradle-profiler, configuration and build cache, remote CI cache, KSP, heap tuning, AGP 9 defaults, Isolated Projects | [Optimize build speed](https://developer.android.com/build/optimize-your-build), [Profile your build](https://developer.android.com/build/profile-your-build) |

### Migrations

| Skill | Covers | Sources |
|---|---|---|
| `migrate-xml-to-compose` | Incremental migration, interop, layout and widget mappings | [Migration strategy](https://developer.android.com/develop/ui/compose/migrate/strategy), [Interoperability APIs](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis) |
| `migrate-rxjava-to-coroutines` | Type and operator mappings, threading, UI state, interop, tests | [Kotlin flows](https://developer.android.com/kotlin/flow), [StateFlow and SharedFlow](https://developer.android.com/kotlin/flow/stateflow-and-sharedflow) |

## Install

Pick one method; using both loads every skill twice.

### Symlinks (Claude Code and other agents)

```bash
git clone https://github.com/pablitoarango/android-skills.git ~/Development/android-skills
~/Development/android-skills/install.sh
```

`install.sh` links every skill into `~/.claude/skills` and `~/.agents/skills`, and removes links for skills that were renamed or deleted. Run it again after pulling changes. `./install.sh --uninstall` removes the links.

### Claude Code plugin

```text
/plugin marketplace add pablitoarango/android-skills
/plugin install android-skills@android-skills
```

Plugin skills are namespaced, for example `android-skills:compose-ui`.

## Repository layout

```text
<category>/<skill-name>/SKILL.md     skill entry point
<category>/<skill-name>/*.md         reference files loaded only when needed
<category>/<skill-name>/scripts/     scripts the skill runs
.claude-plugin/                      plugin and marketplace manifests
tools/validate_skills.py             checks run locally and in CI
install.sh                           symlink installer
```

Contribution rules are in [`AGENTS.md`](AGENTS.md).

## Validate

```bash
python3 tools/validate_skills.py
python3 -m unittest discover -s tools/tests -v
```

The validator checks frontmatter and names, description length, `SKILL.md` size, the opening Google source links, references between skills, relative links, em dashes, and script syntax/help behavior. Regression tests cover `ui.py` element matching, device targeting and text input quoting, plus source-header validation. CI runs both on every push and pull request.

## License

[MIT](LICENSE). Some code samples are adapted from Apache 2.0 projects such as the Android Developers documentation, Now in Android, Retrofit, OkHttp and Coil; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Not affiliated with or endorsed by Google. Android is a trademark of Google LLC.
