# Offline-first data

Source of truth: [Build an offline-first app](https://developer.android.com/topic/architecture/data-layer/offline-first). Read this when a repository must keep working without a network.

## Data sources

An offline-first repository has at least two data sources:

- **Local** (Room, DataStore): the **source of truth**. Everything the app reads comes from here.
- **Network**: the real state on the server. Used only to keep the local copy up to date.

```
data/
├── local/     ArticleEntity, ArticleDao, AppDatabase
├── network/   NetworkArticle, NewsNetworkDataSource
├── model/     Article
└── repository/ OfflineFirstNewsRepository
```

Mapping: `NetworkArticle.asEntity()` when saving, `ArticleEntity.asExternalModel()` when reading.

## Reads

- Read **only from the local data source**, as a `Flow`, so the UI updates when a sync writes new data.
- Handle read errors at the consumer:

```kotlin
val authorUiState: StateFlow<AuthorUiState> =
    authorsRepository.getAuthorStream(id = authorId)
        .map<Author, AuthorUiState>(AuthorUiState::Success)
        .catch { emit(AuthorUiState.Error) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), AuthorUiState.Loading)
```

- When a network read fails, retry with **exponential backoff**, or queue it until connectivity returns.

## Writes

Writes are `suspend` functions. Choose a strategy per operation:

| Strategy | Flow | Use for |
|---|---|---|
| Online-only | Write to network; update local only on success; throw on failure | Money transfers, anything that needs real-time confirmation |
| Queued | Save to a local queue; WorkManager drains it with backoff when online | Analytics, logging, non-critical fire-and-forget |
| Lazy | Write to local first; queue a network sync; resolve conflicts on sync | User data that must never be lost (to-do items, bookmarks) |

## Synchronization

| Approach | How | Trade-off |
|---|---|---|
| Pull-based | Fetch on demand as the user navigates (for example Paging with `RemoteMediator`) | Simple; wasteful on repeat visits; weak for relational data |
| Push-based | Keep a full local mirror; server notifies (for example FCM) when data is stale; app syncs | Works offline indefinitely; needs versioning and conflict handling |
| Hybrid | Pull for some data types, push for others | Common in real apps |

Push-style repository sync:

```kotlin
internal class OfflineFirstUserDataRepository @Inject constructor(
    private val localDataSource: UserDataLocalDataSource,
    private val networkDataSource: UserDataNetworkDataSource,
) : UserDataRepository {
    suspend fun synchronize() {
        val userData = networkDataSource.fetchUserData()
        localDataSource.saveUserData(userData.asEntity())
    }
}
```

Run sync with WorkManager, enqueued once at startup (App Startup `Initializer` or `Application.onCreate`):

```kotlin
WorkManager.getInstance(context).enqueueUniqueWork(
    SYNC_WORK_NAME,
    ExistingWorkPolicy.KEEP,
    OneTimeWorkRequestBuilder<SyncWorker>()
        .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
        .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
        .build(),
)

@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val topicRepository: TopicsRepository,
    private val newsRepository: NewsRepository,
    @Dispatcher(IO) private val ioDispatcher: CoroutineDispatcher,
) : CoroutineWorker(appContext, workerParams) {
    override suspend fun doWork(): Result = withContext(ioDispatcher) {
        val syncedSuccessfully = awaitAll(
            async { topicRepository.sync() },
            async { newsRepository.sync() },
        ).all { it }
        if (syncedSuccessfully) Result.success() else Result.retry()
    }
}
```

## Conflict resolution

- **Last write wins** is the common mobile default: every write carries a timestamp, and the server keeps the newest.
- Anything more complex (merging, user choice) must be designed with the backend.

## Testing

- Fake both data sources to test repository read, write and sync logic on the JVM.
- Test DAOs with an in-memory Room database.
- Test workers with `androidx.work:work-testing` (`TestListenableWorkerBuilder`).
