---
name: android-data-layer
description: "Repositories and data sources per Google's data layer guide: models per layer, main-safety, lifetimes, errors, caching, WorkManager, offline-first sync. Use for repository, data source, Room, DataStore, network, or sync work, and when saves are cancelled on leaving a screen, work must survive process death, network or database models leak past repositories, or the app must work offline."
---

# Android Data Layer

Sources of truth: [Data layer](https://developer.android.com/topic/architecture/data-layer), [Offline-first](https://developer.android.com/topic/architecture/data-layer/offline-first).

For offline-first reads, write strategies, synchronization and conflict resolution, read [`offline-first.md`](offline-first.md).

## 1. Responsibilities

The data layer holds the app data **and the business logic** that gives it value:

- Exposes data to the rest of the app as immutable types.
- Centralizes every change to that data.
- Resolves conflicts between data sources.
- Hides data sources from the rest of the app.

## 2. Structure

```
Repository (public)          one per data type; the only entry point
  ├── XxxLocalDataSource     internal; one source each (Room, DataStore, file)
  └── XxxRemoteDataSource    internal; one source each (Retrofit, Firebase)
```

- Create a repository **even for a single data source**.
- Each repository defines **one source of truth**. For offline-first data it is the local database.
- Each data source works with exactly one source of data.
- Name data sources by role, not technology: `NewsRemoteDataSource`, not `NewsRetrofitDataSource`.
- Repositories may depend on other repositories when combining data; name such a class `<DataType>Manager` if it only coordinates (`UserManager`).
- ViewModels, use cases and composables never inject a DAO, Retrofit service, DataStore or data source.

```kotlin
interface NewsRepository {
    fun getNewsStream(): Flow<List<Article>>
    suspend fun refreshNews()
}

internal class OfflineFirstNewsRepository @Inject constructor(
    private val localDataSource: NewsLocalDataSource,
    private val remoteDataSource: NewsRemoteDataSource,
) : NewsRepository {

    override fun getNewsStream(): Flow<List<Article>> =
        localDataSource.getArticlesStream().map { entities -> entities.map(ArticleEntity::asExternalModel) }

    override suspend fun refreshNews() {
        val articles = remoteDataSource.fetchLatestNews()
        localDataSource.upsertArticles(articles.map(NetworkArticle::asEntity))
    }
}
```

Bind it in the data module:

```kotlin
@Module
@InstallIn(SingletonComponent::class)
internal abstract class NewsDataModule {
    @Binds
    abstract fun bindsNewsRepository(impl: OfflineFirstNewsRepository): NewsRepository
}
```

## 3. API shape

- **One-shot operations**: `suspend fun`.
- **Data that changes over time**: `Flow<T>`, named `get<Model>Stream()` (`getArticlesStream()` for lists).
- Expose immutable types only.
- Every public function is **main-safe**.

## 4. Models per layer

| Model | Example | Visibility |
|---|---|---|
| Network | `NetworkArticle` (`@Serializable`, mirrors the API) | `internal` |
| Database | `ArticleEntity` (Room `@Entity`) | `internal` |
| External | `Article` (only fields the app needs) | public, in `:core:model` |

Mappers are extension functions: `NetworkArticle.asEntity()`, `ArticleEntity.asExternalModel()`. Create a separate model whenever the source shape differs from what the app needs; do not leak network or database models past the repository.

The table assumes sources and repositories share a module. For separate network/database modules, expose a minimal API to repository consumers; `internal` types cannot cross module boundaries. See `android-architecture`.

## 5. Threading

- Classes that do blocking work move it to an **injected** dispatcher with `withContext`.
- Room DAO `suspend`/`Flow` functions and Retrofit `suspend` functions are already main-safe. Do not wrap them in `withContext(io)` or `flowOn(io)`; reserve dispatcher switching for truly blocking work (file I/O, parsing large payloads, legacy blocking SDKs).

```kotlin
internal class NewsRemoteDataSource @Inject constructor(
    private val newsApi: NewsApi,
) {
    suspend fun fetchLatestNews(): List<NetworkArticle> = newsApi.fetchLatestNews()
}
```

## 6. Lifetime of operations

| Operation | Must survive | Implementation |
|---|---|---|
| UI-oriented | Caller's lifetime | Caller's scope through `suspend`; `viewModelScope` cancels when the ViewModel is cleared, not merely hidden |
| App-oriented | Navigation away from the screen, while the app is open | Injected application `CoroutineScope` (`externalScope`) |
| Business-oriented | Process death | WorkManager |

App-oriented work with an in-memory cache uses a separate one-shot contract in this example:

```kotlin
interface LatestNewsRepository {
    suspend fun getLatestNews(refresh: Boolean = false): List<Article>
}

@Singleton
internal class DefaultLatestNewsRepository @Inject constructor(
    private val remoteDataSource: NewsRemoteDataSource,
    @ApplicationScope private val externalScope: CoroutineScope,
) : LatestNewsRepository {

    private val latestNewsMutex = Mutex()
    private var latestNews: List<Article> = emptyList()

    override suspend fun getLatestNews(refresh: Boolean): List<Article> {
        if (refresh || latestNewsMutex.withLock { latestNews.isEmpty() }) {
            externalScope.async {
                remoteDataSource.fetchLatestNews().map(NetworkArticle::asExternalModel).also { fresh ->
                    latestNewsMutex.withLock { latestNews = fresh }
                }
            }.await()
        }
        return latestNewsMutex.withLock { latestNews }
    }
}
```

Business-oriented work:

```kotlin
@HiltWorker
class RefreshLatestNewsWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val newsRepository: NewsRepository,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = try {
        newsRepository.refreshNews()
        Result.success()
    } catch (e: IOException) {
        Result.retry()
    }
}
```

Scope DI bindings to the lifetime of the data they hold: `@Singleton` for app-wide caches, a narrower component for flow-specific data, nothing for stateless classes.

## 7. Errors

- Let data sources throw; the repository either lets exceptions propagate or translates them into meaningful custom exceptions (`UserNotAuthenticatedException`).
- Alternatively return `Result<T>` from the repository. Pick one style per repository and keep it consistent.
- Never swallow `CancellationException`. When wrapping in `Result`, use `suspendRunCatching` from `android-coroutines`, not `runCatching`.
- Flows: handle with the `catch` operator at the consumer (usually the ViewModel).
- The UI layer decides how an error is shown.

## 8. Choosing storage

| Data | Storage |
|---|---|
| Large, queryable, relational, partial updates | Room |
| Small key-value data (settings, preferences) | DataStore (one instance per concern) |
| Large blobs (JSON documents, images) | Files |

## 9. Testing

- Unit test repositories on the JVM with **fake data sources**; tests of consumers use **fake repositories**.
- Integration test Room DAOs with an in-memory database.
- Integration test network data sources against MockWebServer.
- See `android-testing`.

## 10. Checklist

- [ ] Every data type is exposed by a repository; nothing outside the data layer touches a data source.
- [ ] Each repository has one source of truth.
- [ ] Co-located data implementation types are `internal`; split modules expose a minimal repository-facing API. Mappers convert at the repository.
- [ ] `suspend` for one-shot, `Flow` named `get...Stream()` for changes; all main-safe.
- [ ] Dispatchers are injected and used only for blocking work.
- [ ] Work that must outlive the screen uses the external scope; work that must survive process death uses WorkManager.
- [ ] Errors propagate as exceptions or `Result` consistently; `CancellationException` is rethrown.
