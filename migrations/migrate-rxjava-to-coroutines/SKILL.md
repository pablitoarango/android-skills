---
name: migrate-rxjava-to-coroutines
description: "RxJava to coroutines and Flow migration: type and operator mappings, threading, UI state instead of view callbacks, interop adapters, test migration. Use when converting Singles, Observables, Flowables, Subjects, Disposables, subscribeOn/observeOn chains or RxJava tests, or when Rx and coroutine code must interoperate mid-migration."
---

# RxJava to Kotlin Coroutines Migration

Sources of truth: [Coroutines best practices](https://developer.android.com/kotlin/coroutines/coroutines-best-practices), [Kotlin flows on Android](https://developer.android.com/kotlin/flow), [StateFlow and SharedFlow](https://developer.android.com/kotlin/flow/stateflow-and-sharedflow), [UI layer](https://developer.android.com/topic/architecture/ui-layer), [Asynchronous Flow](https://kotlinlang.org/docs/coroutines-flow.html), [kotlinx.coroutines.flow API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/), [kotlinx-coroutines-rx3](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-rx3/).

These sources define the target patterns; check each Rx operator's semantics in the RxJava docs before replacing it. The migrated code must follow `android-coroutines`, `android-data-layer` and `android-viewmodel`.

## 1. Migration order

Migrate **incrementally**, from the data layer up:

1. **Data sources and repositories**: change return types to `suspend` / `Flow`.
2. **Use cases**, if any.
3. **ViewModels / presenters**: replace subscriptions with coroutines in `viewModelScope` producing `StateFlow` UI state.
4. **UI**: collect with `repeatOnLifecycle` or `collectAsStateWithLifecycle()`.
5. **Tests** for each migrated class.
6. Remove RxJava dependencies once nothing uses them.

Use interop adapters (section 7) at the boundary while both styles coexist.

## 2. Choosing the target type

Decide by two questions: how many values does the source produce, and does it run per subscriber (cold) or independently of subscribers (hot)? Default to `suspend`; use `Flow` only for values that change over time.

### One result

| RxJava | Coroutines | Behavior to preserve |
|---|---|---|
| `Completable` | `suspend fun archive(id: String)` | Completion is a normal return; failure is a thrown exception |
| `Maybe<T>` | `suspend fun find(id: String): T?` | "Empty" becomes `null`. If `null` is already a valid value, return a sealed result instead |
| `Single<T>` | `suspend fun load(id: String): T` | |
| `AsyncSubject<T>`, or a `Single` shared with `cache()` | `CompletableDeferred<T>`, or `async` in the owning scope | Many callers `await()` one computation |

### Cold streams

| RxJava | Coroutines | Behavior to preserve |
|---|---|---|
| `Flowable<T>` | `Flow<T>` | Flow applies backpressure by suspending the emitter. Replace `onBackpressure*` with an explicit `buffer` / `conflate` ([operators](operators.md#backpressure-and-rate)) |
| `Observable<T>` | `Flow<T>` | An `Observable` never slows its producer; a Flow producer waits for a slow collector. Add `buffer()` where the producer must not wait |
| `Observable.create` over a listener | `callbackFlow` with `awaitClose` | Unregister the listener in `awaitClose` |

### Hot, multicast and state

| RxJava | Coroutines | Behavior to preserve |
|---|---|---|
| `BehaviorSubject.createDefault(x)` | Private `MutableStateFlow(x)`, exposed with `asStateFlow()` | `StateFlow` requires an initial value, conflates fast updates, and drops values `equals` to the current one. If every emission matters, use `MutableSharedFlow(replay = 1)` |
| `BehaviorSubject.create()` (no default) | `MutableSharedFlow<T>(replay = 1)` | Or `MutableStateFlow<T?>(null)` when `null` can mean "not loaded" |
| `ReplaySubject.createWithSize(n)` | `MutableSharedFlow<T>(replay = n)` | Bound unbounded `ReplaySubject`s during migration |
| `PublishSubject<T>` | Private `MutableSharedFlow<T>()`, exposed with `asSharedFlow()` | Values emitted with no subscribers are lost, as in Rx. Without a buffer, `emit` suspends until every subscriber receives the value and `tryEmit` only succeeds when nobody is subscribed; set `extraBufferCapacity` when non-suspending callers emit. **Not** for ViewModel-to-UI events (section 5) |
| `UnicastSubject<T>` / work queue | `Channel<T>` read with `receiveAsFlow()` | Each value goes to exactly one collector |
| `share()` (`publish().refCount()`) | `shareIn(scope, SharingStarted.WhileSubscribed())` | Starts with the first subscriber, stops after the last; late subscribers get no past values |
| `replay(1).refCount()` | `shareIn(scope, SharingStarted.WhileSubscribed(), replay = 1)`, or `stateIn` when there is a sensible initial value | `WhileSubscribed` keeps the replay cache after stopping unless `replayExpirationMillis` is set |
| `publish().autoConnect()` | `shareIn(scope, SharingStarted.Lazily)` | Starts with the first subscriber and never stops |

- Serialized subjects are unnecessary: every `MutableSharedFlow` / `MutableStateFlow` method is thread-safe.
- A `SharedFlow` never completes and cannot carry an error. If subscribers relied on `onComplete` / `onError` from a subject, turn those outcomes into values (for example with `onCompletion` and `catch` before `shareIn`). Test unsubscribe and resubscribe behavior against the original Rx chain.

### Subscriptions

| RxJava | Coroutines |
|---|---|
| `subscribe(onNext, onError, onComplete)` | `launch { flow.catch { }.collect { } }`; code after `collect` runs on completion |
| `Disposable` | The `Job` returned by `launch` |
| `CompositeDisposable` | The owning `CoroutineScope` (`viewModelScope`), cancelled with its owner |

## 3. Operators

When converting a chain with operators, read [`operators.md`](operators.md). It groups Flow equivalents by task (creating, selecting, nesting, combining, time, backpressure, side effects, errors) and lists the semantic differences to check for each.

## 4. Threading

- Remove `subscribeOn` and `observeOn`.
- Classes doing blocking work switch with `withContext(injectedDispatcher)` internally, so every `suspend` function is main-safe. **Inject** the dispatcher; do not hardcode `Dispatchers.IO`.
- Room and Retrofit `suspend` / `Flow` APIs are already main-safe; call them without switching.
- For CPU-heavy flow operators, apply `flowOn(injectedDispatcher)` after them; it only affects upstream.
- Do not `emit` from another coroutine or `withContext` inside `flow { }`; wrap callback sources with `callbackFlow` and `awaitClose`.

| Scheduler | Replacement |
|---|---|
| `Schedulers.io()` | Injected `@Dispatcher(IO) CoroutineDispatcher` |
| `Schedulers.computation()` | Injected `@Dispatcher(Default) CoroutineDispatcher` |
| `AndroidSchedulers.mainThread()` | Nothing; `viewModelScope` and UI scopes already run on Main |

## 5. From view callbacks to UI state

Rx presenters usually push results into a view interface from `subscribe`. After migration, the ViewModel exposes state and the UI renders it; nothing calls back into the view.

A search screen that pushes results into the view:

```kotlin
disposables += queryInput
    .debounce(300, TimeUnit.MILLISECONDS)
    .distinctUntilChanged()
    .switchMapSingle { text -> catalogApi.search(text).subscribeOn(Schedulers.io()) }
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe(view::renderResults, view::renderSearchError)
```

The same screen as state:

```kotlin
@HiltViewModel
class CatalogSearchViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
) : ViewModel() {

    private val query = MutableStateFlow("")

    @OptIn(FlowPreview::class, ExperimentalCoroutinesApi::class)
    val uiState: StateFlow<SearchUiState> = query
        .debounce(300.milliseconds)
        .mapLatest { text ->
            if (text.isBlank()) {
                SearchUiState.Idle
            } else {
                try {
                    SearchUiState.Results(catalogRepository.search(text))
                } catch (e: IOException) {
                    SearchUiState.Failed
                }
            }
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), SearchUiState.Idle)

    fun onQueryChange(text: String) {
        query.value = text
    }
}
```

What changed beyond syntax:

- `PublishSubject` input became a `MutableStateFlow`, which already skips equal values, so `distinctUntilChanged` is gone.
- `switchMapSingle` became `mapLatest`: a new query cancels the running search.
- In the Rx chain, one failed search terminates the subscription and search stops working. Catching inside `mapLatest` turns the failure into state and keeps the stream alive.
- `subscribeOn` / `observeOn` are gone; `catalogRepository.search` is main-safe.

One-shot actions (`Completable` / `Single` triggered by a click) become a `launch` that updates state:

```kotlin
fun onArchiveClick() {
    viewModelScope.launch {
        _uiState.update { it.copy(isArchiving = true) }
        val archived = try {
            notesRepository.archive(noteId)
            true
        } catch (e: IOException) {
            false
        }
        _uiState.update { it.copy(isArchiving = false, isArchived = archived, archiveFailed = !archived) }
    }
}
```

- A `PublishSubject` used to push navigation or messages to the UI becomes a field in UI state, cleared by a "shown" callback (`android-viewmodel`).
- Collect in the UI with `repeatOnLifecycle(Lifecycle.State.STARTED)` or `collectAsStateWithLifecycle()`.

## 6. Errors

- `suspend` functions: `try` / `catch` around the call, catching **specific** exception types.
- Never swallow `CancellationException`. A broad `catch (e: Exception)` must rethrow it first; `runCatching` catches it too (`android-coroutines`).
- `withTimeout` throws `TimeoutCancellationException`, a subclass of `CancellationException`; catch it explicitly where a timeout is an expected outcome, or use `withTimeoutOrNull`.
- Flows: `catch { }` handles upstream errors only; place it before `stateIn` / `collect`. As in Rx, an error ends the flow; handle per-item failures inside the inner lambda when the stream must continue.
- `RxJavaPlugins.setErrorHandler` for undeliverable errors has no one-to-one replacement: uncaught exceptions in `launch` go to the scope's `CoroutineExceptionHandler`; without one, the app crashes.

## 7. Interop during migration

Add `org.jetbrains.kotlinx:kotlinx-coroutines-rx3` (or `-rx2` for RxJava 2) at the same version as `kotlinx-coroutines-core`; see the [kotlinx.coroutines releases](https://github.com/Kotlin/kotlinx.coroutines/releases). Use the adapters at boundaries so layers can migrate one at a time:

| Direction | API | Notes |
|---|---|---|
| `Flowable<T>` → `Flow<T>` | `flowable.asFlow()` | Comes from `kotlinx-coroutines-reactive`, which the rx3 artifact exposes as an API dependency; the buffer size sets the subscription's request |
| `Observable<T>` → `Flow<T>` | `observable.asFlow()` | Subscribes on every collection; uses a default-size channel, so add `buffer()` to choose the overflow behavior |
| `Observable<T>` → one value | `awaitFirst()`, `awaitFirstOrNull()`, `awaitFirstOrDefault(x)`, `awaitLast()`, `awaitSingle()` | |
| `Completable` → `Unit` | `completable.await()` | |
| `Maybe<T>` → `T?` | `maybe.awaitSingleOrNull()` | `awaitSingle()` throws when the `Maybe` is empty |
| `Single<T>` → `T` | `single.await()` | |
| `suspend` → `Single` / `Maybe` / `Completable` | `rxSingle { }`, `rxMaybe { }`, `rxCompletable { }` | Cold: each subscription starts a coroutine and disposal cancels it. Without a dispatcher in `context`, the block runs on `Dispatchers.Default`. `rxMaybe` completes empty when the block returns `null` |
| Producer coroutine → `Observable` / `Flowable` | `rxObservable { send(x) }`, `rxFlowable { send(x) }` | `rxFlowable` respects backpressure |
| `Flow<T>` → `Observable<T>` / `Flowable<T>` | `flow.asObservable()`, `flow.asFlowable()` | Disposal cancels the flow. Observer calls run on `Dispatchers.Unconfined` unless you pass a `context`. `T` must be non-null |
| `Deferred` / `Job` → Rx | `deferred.asSingle(context)`, `deferred.asMaybe(context)`, `job.asCompletable(context)` | Hot: they reflect work already running |
| `Scheduler` ↔ dispatcher | `scheduler.asCoroutineDispatcher()`, `dispatcher.asScheduler()` | Lets both halves of a partly migrated class share one test scheduler |

Remove each adapter once both sides of the boundary are migrated.

## 8. Tests

| RxJava test | Coroutines test |
|---|---|
| `TestObserver` / `test()` | `runTest` plus assertions on returned values |
| `RxJavaPlugins.setIoSchedulerHandler` / `TestScheduler` | Inject `StandardTestDispatcher(testScheduler)`; `advanceUntilIdle()`, `advanceTimeBy()` |
| `RxAndroidPlugins.setInitMainThreadSchedulerHandler` | `MainDispatcherRule` |
| `assertValues(...)` on a stream | `toList()` / `take(n).toList()`, or collect in `backgroundScope`; Turbine for complex streams |
| Asserting a `BehaviorSubject` value | Assert on `stateFlow.value`, with a `backgroundScope` collector for `WhileSubscribed` flows |
| Operators that read wall-clock time | Inject a `TimeSource` and pass `testScheduler.timeSource` |
| `blockingGet()` / `blockingFirst()` | `runTest { flow.first() }` or a direct `suspend` call |

Use fakes, not mocks, for repositories (`android-testing`).

## 9. Checklist

- [ ] Layers migrate from data to UI, with rx3 adapters only at boundaries that still mix styles.
- [ ] Each source's target type was chosen by value count and hot or cold behavior; one-shot work is `suspend`.
- [ ] Subject replacements are private and exposed read-only; `StateFlow` equality and conflation and `SharedFlow`'s lack of terminal signals were checked against how subscribers used the subject.
- [ ] Every operator was mapped with its semantic difference checked (concurrency limits, timing edge cases, backpressure, where `catch` sits).
- [ ] No `subscribeOn` / `observeOn` equivalents left; dispatchers injected; Room and Retrofit called directly.
- [ ] ViewModels expose `StateFlow` UI state; no view callbacks or UI events through `SharedFlow`; long-lived streams survive single-item failures where the Rx version should have.
- [ ] Errors caught by type; `CancellationException` and `TimeoutCancellationException` handled deliberately.
- [ ] Tests use `runTest`, `MainDispatcherRule`, a single test scheduler and fakes.
- [ ] RxJava and adapter dependencies removed when unused.
