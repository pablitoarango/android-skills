---
name: android-architecture
description: "Android app architecture per Google's guide: layers and dependency direction, Hilt, modularization, models per layer, naming. Use for project structure, where code belongs, module setup, or dependency injection, and when UI calls DAOs or APIs directly, features depend on each other's internals, or classes cannot be tested in isolation."
---

# Android App Architecture

Sources of truth: [Guide to App Architecture](https://developer.android.com/topic/architecture), [Architecture recommendations](https://developer.android.com/topic/architecture/recommendations), [Modularization patterns](https://developer.android.com/topic/modularization/patterns), [Hilt](https://developer.android.com/training/dependency-injection/hilt-android).

Rules marked **(stricter than Google)** are deliberate choices that go beyond the guide; follow them too.

Layer-specific detail lives in sibling skills:

| Topic | Skill |
|---|---|
| ViewModels, UI state, UI events | `android-viewmodel` |
| Composables, UI state holders, lifecycle effects | `compose-ui` |
| Use cases | `android-domain-layer` |
| Repositories, data sources, offline-first | `android-data-layer` |
| Coroutines and Flow | `android-coroutines` |
| Navigation | `compose-navigation` |
| Tests | `android-testing` |

## 1. Principles

- **Separation of concerns**: every class, module and layer has one clearly defined responsibility. Activities and composables display state and forward user actions; they hold no business logic.
- **Drive UI from data models**, preferably persistent ones, so the app survives process death and poor connectivity.
- **Single source of truth (SSOT)**: every data type has one owner. The owner exposes it as an immutable type and exposes functions to change it.
- **Unidirectional data flow (UDF)**: state flows down (data sources → repositories → ViewModel → UI), events flow up (UI → ViewModel → repository).

## 2. Layers

Dependencies point **downward only**: UI → domain (when present) → data.

```
UI layer        UI elements (Compose) + state holders (ViewModel, plain state holder classes)
   ↓
Domain layer    optional; use cases that encapsulate complex or reused business logic
   ↓
Data layer      repositories (public API) + data sources (internal); owns business logic and app data
```

### UI layer (required)
- Displays application data and handles user interaction.
- A screen-level `ViewModel` produces UI state from the data or domain layer.
- UI components never talk to data sources (Room DAOs, Retrofit services, DataStore, SharedPreferences, Firebase, GPS, Bluetooth, connectivity managers). They go through a repository or a use case.

### Data layer (required)
- Contains the app data **and most of the business logic**: exposing data, centralizing changes, resolving conflicts between sources.
- Create a repository even when there is only one data source.
- Repositories are the only public entry point; data sources stay internal.

### Domain layer (optional)
- Add use cases only when business logic is **reused by several ViewModels** or makes a ViewModel **too complex**. Otherwise the ViewModel calls the repository directly.
- Use cases depend on repositories and other use cases. The data layer never depends on the domain layer.
- **(Stricter than Google)** Domain code is pure Kotlin: no `android.*` imports.
- Full rules: `android-domain-layer`.

## 3. General practices

- **App components are not data sources.** Activities, services and broadcast receivers only coordinate; they never own or cache data.
- **Keep Android framework types at the edges.** ViewModels stay independent of `Context`, `Resources` and lifecycle types. Platform-backed data sources and DI providers can receive framework dependencies, using `@ApplicationContext` for app-lived work. Repositories and use cases delegate platform access to those adapters; UI behavior such as `Toast` stays in the UI.
- **Types own their concurrency policy.** A class doing blocking work moves it off the main thread itself, so every public API is main-safe.
- **Persist relevant, fresh data** so the app works offline.
- **Preserve UI state across configuration changes** (rotation, resizing, folding) with `ViewModel`, `SavedStateHandle` and `rememberSaveable`.
- **Make every part testable in isolation**: constructor injection plus interfaces at layer boundaries so tests can use fakes.
- **Single activity + Jetpack Compose + Navigation 3** for apps with multiple screens.

## 4. Dependency injection

- Use constructor injection where supported; use Hilt field injection for framework-created components and providers for third-party types.
- **(Stricter than Google)** Use **Hilt** for all dependency injection. No manual DI containers or service locators.
    - `@HiltAndroidApp` on the `Application`, `@AndroidEntryPoint` on activities and fragments, `@HiltViewModel` on ViewModels.
    - Bind interfaces to implementations with `@Binds` in an abstract module.
- **Scope only when necessary.** Scope a binding (for example `@Singleton`) only if the type holds mutable data that must be shared, or is expensive to create (OkHttp, Room database). Use cases, mappers and stateless classes stay unscoped.

```kotlin
@Module
@InstallIn(SingletonComponent::class)
internal abstract class DataModule {
    @Binds
    abstract fun bindsNewsRepository(impl: OfflineFirstNewsRepository): NewsRepository
}
```

## 5. Modularization

Follow Google's [common modularization patterns](https://developer.android.com/topic/modularization/patterns): high cohesion inside a module, low coupling between modules.

| Module type | Contains | Depends on |
|---|---|---|
| `:app` | Application, single Activity, root `NavDisplay`, DI wiring | feature modules |
| `:feature:<name>:api` | Navigation keys only | `:core:model` |
| `:feature:<name>:impl` | Composables, ViewModels, entry builders | its own `:api`, other features' `:api`, `:core:data` or `:core:domain`, `:core:ui` |
| `:core:data` (or `:data:<domain>`) | Repository interfaces and implementations, data sources, mappers | `:core:model`, `:core:network`, `:core:database` |
| `:core:domain` | Use cases (optional) | `:core:data`, `:core:model` |
| `:core:model` | Shared models (pure Kotlin) | nothing |
| `:core:ui`, `:core:network`, `:core:database`, `:core:testing` | Shared UI, HTTP client setup, Room database, fakes and test rules | as needed |

Rules:
- A **data module** exposes its repositories and keeps co-located data sources, network/database models and mappers `internal`. If sources live in separate `:core:network` or `:core:database` modules, expose only the types their repository consumers need. Kotlin `internal` cannot cross a module boundary; keep those lower-level APIs out of feature dependencies.
- A **feature module never depends on another feature's `impl`**. Features navigate by depending on the other feature's `:api` keys and exchange IDs, not objects.
- Prefer `implementation` over `api` in Gradle dependencies, and prefer pure Kotlin/JVM modules when no Android resources or manifest are needed.
- Split a data module into separate `api`/`impl` modules only when Google's criteria apply: several implementations (for example per build type), capabilities shared across apps, independent teams, or build-time isolation in a large codebase.
- Share build logic with convention plugins and a version catalog (`gradle-build-logic`).

## 6. Models per layer

In non-trivial apps, map models at each boundary so every layer only sees what it needs:

| Layer | Example | Notes |
|---|---|---|
| Network | `NetworkArticle` | Mirrors the API response, `@Serializable`; `internal` when co-located with its repository |
| Database | `ArticleEntity` | Room `@Entity`; `internal` when co-located with its repository |
| External (repository output) | `Article` | Trimmed to what the app needs; lives in `:core:model` |
| UI | `ArticleUiState`, `NewsFeedUiState` | Built by the ViewModel |

Mappers are extension functions next to the source model: `NetworkArticle.asEntity()`, `ArticleEntity.asExternalModel()`.

## 7. Naming

| Kind | Convention | Example |
|---|---|---|
| Methods | Verb phrase | `makePayment()` |
| Properties | Noun phrase | `inProgressTopicSelection` |
| Data streams | `get<Model>Stream()`, plural for lists | `getAuthorStream(): Flow<Author>`, `getAuthorsStream(): Flow<List<Author>>` |
| Repositories | `<DataType>Repository` | `NewsRepository` |
| Data sources | `<DataType><Kind>DataSource`, kind names the role, not the technology | `NewsRemoteDataSource`, `NewsLocalDataSource` |
| Interface implementations | Meaningful prefix, else `Default` | `OfflineFirstNewsRepository`, `DefaultNewsRepository` |
| Test doubles | `Fake` prefix | `FakeNewsRepository` |
| Use cases | Verb in present tense + noun + `UseCase` | `GetLatestNewsWithAuthorsUseCase` |
| UI state | `<Functionality>UiState` | `NewsUiState`, `NewsItemUiState` |

## 8. Checklist

- [ ] Dependencies point downward only: UI → domain → data.
- [ ] No UI component touches a data source directly.
- [ ] Business logic sits in repositories, or in use cases when reused or complex. No pass-through use cases.
- [ ] Domain code has no `android.*` imports.
- [ ] Every repository and data source API is main-safe (`suspend` or `Flow`).
- [ ] ViewModels take no `Context`, `Activity` or `Resources`.
- [ ] All injection goes through Hilt; scoped bindings are justified by shared mutable state or creation cost.
- [ ] Co-located data implementation types are `internal`; separate network/database modules expose only the APIs repositories need.
- [ ] Feature modules depend only on other features' `:api` modules.
