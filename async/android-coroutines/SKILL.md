---
name: android-coroutines
description: "Coroutines and Flow per Google's best practices and the Kotlin coroutines guide: dispatchers, main-safety, scopes, Flow, lifecycle collection, cancellation, exceptions, shared state, testing, concurrency reviews. Use for async code or coroutine tests, and for ANRs, leaks, races, hangs, viewModelScope crashes, silently lost errors, work that ignores cancellation, or runTest timeouts."
---

# Android Coroutines

Sources of truth: [Best practices for coroutines in Android](https://developer.android.com/kotlin/coroutines/coroutines-best-practices), [Improve app performance with Kotlin coroutines](https://developer.android.com/kotlin/coroutines/coroutines-adv), [Kotlin flows on Android](https://developer.android.com/kotlin/flow), [StateFlow and SharedFlow](https://developer.android.com/kotlin/flow/stateflow-and-sharedflow), [Lifecycle-aware coroutines](https://developer.android.com/topic/libraries/architecture/coroutines), [Testing coroutines](https://developer.android.com/kotlin/coroutines/test), [Testing flows](https://developer.android.com/kotlin/flow/test), [Kotlin coroutines guide](https://kotlinlang.org/docs/coroutines-guide.html), [kotlinx.coroutines API](https://kotlinlang.org/api/kotlinx.coroutines/).

To audit existing code or chase a concurrency bug, use [`review.md`](review.md). Library versions: [kotlinx.coroutines releases](https://github.com/Kotlin/kotlinx.coroutines/releases), [Lifecycle releases](https://developer.android.com/jetpack/androidx/releases/lifecycle).

## 1. Dispatchers and main-safety

A `suspend` modifier does not move work off the main thread. The dispatcher decides the thread: `Dispatchers.Main` for UI and quick work, `Dispatchers.IO` for blocking disk and network I/O, `Dispatchers.Default` for CPU-heavy work such as parsing or sorting.

- **The class that blocks owns the thread switch.** Any `suspend` function, in any layer, must be callable from the main thread. If it performs blocking or CPU-heavy work, it wraps that work in `withContext(dispatcher)` itself. Callers never guess which dispatcher a callee needs.
- **Libraries that are already main-safe need no wrapper**: Room `suspend` and `Flow` DAOs, Retrofit `suspend` functions (see `android-retrofit`), DataStore.
- **Take dispatchers as constructor parameters.** Writing `Dispatchers.IO` inside a class body makes the class untestable with a `TestDispatcher`. Google's samples hardcode them only for brevity.
- `withContext` is cheap and switching between `Default` and `IO` is optimized, so one outer `withContext` around many small blocking calls is fine. A pooled dispatcher may resume on a different thread after each suspension, so do not rely on `ThreadLocal` values inside the block.
- `Dispatchers.Unconfined` is a special-purpose tool; do not use it in app code.

With Hilt, provide dispatchers behind a qualifier:

```kotlin
@Qualifier
@Retention(AnnotationRetention.RUNTIME)
annotation class Dispatcher(val dispatcher: AppDispatchers)

enum class AppDispatchers { Default, IO }

@Module
@InstallIn(SingletonComponent::class)
object DispatchersModule {
    @Provides
    @Dispatcher(AppDispatchers.IO)
    fun providesIODispatcher(): CoroutineDispatcher = Dispatchers.IO

    @Provides
    @Dispatcher(AppDispatchers.Default)
    fun providesDefaultDispatcher(): CoroutineDispatcher = Dispatchers.Default
}

class InvoicePdfRenderer @Inject constructor(
    @Dispatcher(AppDispatchers.Default) private val defaultDispatcher: CoroutineDispatcher,
    @Dispatcher(AppDispatchers.IO) private val ioDispatcher: CoroutineDispatcher,
) {
    suspend fun render(invoice: Invoice, target: File) {
        val bytes = withContext(defaultDispatcher) { layOutPages(invoice) }
        withContext(ioDispatcher) { target.writeBytes(bytes) }
    }
}
```

## 2. Structured concurrency: who launches, who waits

Every coroutine belongs to a scope, and the scope decides when it is cancelled. Pick the owner by how long the result stays relevant.

| Lifetime of the work | Where to start it |
|---|---|
| Only while the screen's state holder exists | `viewModelScope.launch` in the ViewModel |
| Only while a composable is in composition | `LaunchedEffect` / `rememberCoroutineScope` (see `compose-side-effects`) |
| Only for the duration of one suspend call | `coroutineScope { }` or `supervisorScope { }` inside the function |
| Must finish even if the user leaves the screen | An injected application `CoroutineScope` |
| Must finish even if the process dies | WorkManager (see `android-data-layer`) |

- **ViewModels start coroutines; the data and domain layers expose `suspend` functions for one-shot work and `Flow` for values that change over time.** The caller then controls when that work runs and when it is cancelled. Coroutines in `viewModelScope` survive configuration changes; work launched from a View's `lifecycleScope` does not.
- A ViewModel may expose a `suspend` function when the caller only needs a single value and should own its cancellation. For anything the screen observes, expose state instead (see `android-viewmodel`).
- Views trigger coroutines only for UI work such as formatting text or decoding an image, not for business logic.
- Launch from regular functions with `launch`. Use `async` only inside a coroutine for parallel decomposition, and always `await` it: an `async` started from a regular function and never awaited drops its exception silently.
- **Avoid `GlobalScope`.** It hardcodes an uncontrolled scope, cannot be replaced in tests and cannot carry a shared context. Inject a scope instead. `GlobalScope` also requires `@OptIn(DelicateCoroutinesApi::class)`.
- Do not pass `Job()` or `SupervisorJob()` to `launch`, `async` or `withContext`. The new Job replaces the parent, so the coroutine is no longer cancelled with its scope.

Parallel decomposition inside a suspend function. `coroutineScope` waits for every child and rethrows the first failure after cancelling the rest:

```kotlin
class LoadTripSummaryUseCase @Inject constructor(
    private val flightsRepository: FlightsRepository,
    private val hotelsRepository: HotelsRepository,
    private val weatherRepository: WeatherRepository,
) {
    suspend operator fun invoke(tripId: String): TripSummary = coroutineScope {
        val flights = async { flightsRepository.flightsFor(tripId) }
        val hotels = async { hotelsRepository.bookingsFor(tripId) }
        val forecasts = async { weatherRepository.forecastFor(tripId) }
        TripSummary(flights.await(), hotels.await(), forecasts.await())
    }
}
```

Use `supervisorScope` when siblings may fail independently, for example a batch of downloads where one failure must not cancel the others. Handle each child's failure: `await` each `async`, or catch inside each `launch`.

Application scope for work that outlives the screen. Create it once with a `SupervisorJob` so one failed child does not cancel the whole scope:

```kotlin
@Qualifier
@Retention(AnnotationRetention.RUNTIME)
annotation class ApplicationScope

@Module
@InstallIn(SingletonComponent::class)
object CoroutineScopesModule {
    @Provides
    @Singleton
    @ApplicationScope
    fun providesApplicationScope(
        @Dispatcher(AppDispatchers.Default) dispatcher: CoroutineDispatcher,
    ): CoroutineScope = CoroutineScope(SupervisorJob() + dispatcher)
}

class DraftsRepository @Inject constructor(
    private val draftsDao: DraftsDao,
    @ApplicationScope private val appScope: CoroutineScope,
) {
    suspend fun saveDraft(draft: Draft) {
        appScope.async { draftsDao.upsert(draft.toEntity()) }.await()
    }
}
```

The caller suspends until the save completes, but cancelling the caller does not cancel the save. Google's page shows `launch { }.join()`; `join` returns normally even when the child failed, so this skill uses `async { }.await()`, which rethrows the failure to the caller, as the `CoroutineExceptionHandler` docs recommend (stricter than Google).

## 3. Flow

A `flow { }` is cold: its body runs again for every collector, in the collector's coroutine, one value at a time.

- **Do not change context inside `flow { }`.** Calling `emit` from `withContext` or from a launched coroutine throws. Change the upstream context with `flowOn(dispatcher)`: it affects the operators above it and leaves the collector and downstream operators in the collector's context. `flowOn` does nothing on a `StateFlow` or `SharedFlow`.
- Use `channelFlow` when a producer needs concurrent coroutines, and `callbackFlow` for multi-shot listener APIs.
- **Handle upstream errors with `catch`**, which can `emit` a fallback. It only sees exceptions thrown above it. To catch failures from per-item work, move that work into `onEach` before `catch` and collect with an empty `collect()`. Rethrow exceptions you do not expect. Use `retry` / `retryWhen` for transient failures.
- **Never expose mutable flows.** Keep `MutableStateFlow` / `MutableSharedFlow` private and expose `StateFlow` / `SharedFlow` / `Flow` (`asStateFlow()`, `asSharedFlow()`). Update state atomically with `update { }` when the new value depends on the old one.
- **Share expensive cold flows** instead of collecting them once per consumer:
  - `stateIn(scope, started, initialValue)` for state. In a ViewModel use `SharingStarted.WhileSubscribed(5_000)`, which keeps the upstream alive for 5 seconds after the last collector leaves, long enough to survive a configuration change.
  - `shareIn(scope, started, replay)` for streams shared from the data layer, in a scope that outlives every collector.
  - `Eagerly` starts immediately and never stops; `Lazily` starts on the first subscriber and never stops. Prefer `WhileSubscribed` unless the upstream must always run.
  - An exception in the upstream of `stateIn` / `shareIn` cancels the sharing coroutine and goes to the scope's handler, which crashes the app from `viewModelScope`. Put `catch` before `stateIn`.
- **Slow collectors**: `buffer()` lets the producer run ahead; `conflate()` keeps only the latest value; `collectLatest { }` cancels the previous block when a new value arrives. `StateFlow` is already conflated, so collectors may skip intermediate values.

Multi-shot callback API. `awaitClose` is mandatory: without it the builder throws `IllegalStateException` when the block returns, and the listener would leak. The API's register and unregister calls must be thread-safe.

```kotlin
fun ConnectivityManager.isOnline(): Flow<Boolean> = callbackFlow {
    val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            trySend(true)
        }

        override fun onLost(network: Network) {
            trySend(false)
        }
    }
    trySend(activeNetwork != null)
    registerDefaultNetworkCallback(callback)
    awaitClose { unregisterNetworkCallback(callback) }
}.conflate()
```

Single-shot callback API. Use `suspendCancellableCoroutine`, never `suspendCoroutine`, which ignores cancellation:

```kotlin
suspend fun LabelPrinter.printLabel(label: Label): PrintReceipt =
    suspendCancellableCoroutine { continuation ->
        val handle = print(label, object : PrintCallback {
            override fun onPrinted(receipt: PrintReceipt) = continuation.resume(receipt)
            override fun onFailed(error: PrinterException) = continuation.resumeWithException(error)
        })
        continuation.invokeOnCancellation { handle.cancel() }
    }
```

## 4. Collecting in the UI

Collect only while the UI is visible. Plain collection keeps running in the background, wastes resources and can crash when it touches a stopped view.

- **Compose**: `collectAsStateWithLifecycle()` from `androidx.lifecycle:lifecycle-runtime-compose`. It collects from `STARTED` and stops at `STOPPED`; change that with `minActiveState`.
- **Views**: inside `lifecycleScope.launch` (in Fragments `viewLifecycleOwner.lifecycleScope`), call `repeatOnLifecycle(Lifecycle.State.STARTED) { }`. It restarts the block each time the lifecycle reaches `STARTED` and cancels it at `STOPPED`. For several flows, `launch` one child per flow inside the block. For exactly one flow, `flow.flowWithLifecycle(lifecycle, Lifecycle.State.STARTED)` is shorter.
- **Do not** collect UI flows with a bare `lifecycleScope.launch` or `launchIn(lifecycleScope)`. **Do not** use `launchWhenStarted` / `whenStarted` and the other `launchWhenX` / `whenX` APIs: they are deprecated because they pause the coroutine instead of cancelling it, which keeps upstream flows running.

```kotlin
class InboxFragment : Fragment(R.layout.fragment_inbox) {
    private val viewModel: InboxViewModel by viewModels()

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { viewModel.threads.collect(threadAdapter::submitList) }
                launch { viewModel.unreadCount.collect(::showUnreadBadge) }
            }
        }
    }
}
```

## 5. Cancellation and timeouts

Cancellation is cooperative. A cancelled coroutine keeps running until it reaches a suspension point that checks, at which point a `CancellationException` is thrown.

- Every suspending function in `kotlinx.coroutines` (`delay`, `withContext`, `await`, `Channel.receive`, `Mutex.lock`) checks cancellation. Custom suspend functions built on `suspendCoroutine` do not.
- In long loops or CPU-bound code that never suspends, call `ensureActive()` (throws if cancelled), check `isActive`, or call `yield()`. `yield()` also lets other coroutines on the same thread run.
- Blocking JVM calls such as `Thread.sleep` or `BlockingQueue.take` are not interrupted by cancellation. Wrap them in `runInterruptible { }` to turn cancellation into a thread interrupt.
- `withContext` checks cancellation when it returns. A result computed on `IO` is never delivered to a screen that was cancelled in the meantime.
- Prompt cancellation can lose a resource that was already returned. Close resources in `finally`. For suspending cleanup, run it in `withContext(NonCancellable) { }` inside `finally`. Never pass `NonCancellable` to `launch` or `async`.
- **Timeouts**: `withTimeoutOrNull(duration) { }` returns `null` on timeout. `withTimeout` throws `TimeoutCancellationException`, a subclass of `CancellationException`, so an uncaught timeout inside `launch` ends the coroutine silently instead of failing it. Prefer `withTimeoutOrNull` and handle the `null`. A timeout also cannot stop code that does not cooperate with cancellation.

```kotlin
suspend fun importContacts(files: List<File>, dao: ContactsDao) = withContext(ioDispatcher) {
    for (file in files) {
        ensureActive()
        dao.insertAll(parseVcf(file.readText()))
    }
}
```

## 6. Exceptions

An uncaught exception in a `launch` started from `viewModelScope` or `lifecycleScope` crashes the app.

- **Catch expected failures inside the coroutine**, near the call, and turn them into state. Catch specific types such as `IOException` or `HttpException` rather than `Exception` or `Throwable`.
- **Never swallow `CancellationException`.** If you catch a broad type, rethrow cancellation. The same applies to `catch` blocks inside `flow { }`.
- The standard `runCatching` catches every `Throwable`, cancellation included. In suspending code use this helper instead:

```kotlin
inline fun <R> suspendRunCatching(block: () -> R): Result<R> = try {
    Result.success(block())
} catch (e: CancellationException) {
    throw e
} catch (e: Exception) {
    Result.failure(e)
}
```

How failures travel, per the Kotlin guide:

- `launch` propagates a failure to its parent. The parent cancels its other children and fails in turn, up to the root. `coroutineScope` rethrows the failure to its caller.
- `async` keeps its failure until `await`, which rethrows it. As a child of a regular `Job`, a failed `async` also cancels its parent right away, so wrapping only `await()` in `try`/`catch` does not contain it. Catch inside the `async` block, or use `supervisorScope`.
- `SupervisorJob` and `supervisorScope` do not fail when a child fails. Each child must handle its own failure; an unhandled one in a supervised `launch` is uncaught.
- **`CoroutineExceptionHandler` is a last resort, not recovery.** It runs only for failures with no other path: a root `launch`, or a `launch` directly under a `SupervisorJob` / `supervisorScope`. It runs after the coroutine has already completed, so it cannot retry or resume. Installed on an ordinary child it is ignored, and on `async` it is never called. Use it for logging or a generic error message; handle errors you expect with `try`/`catch`.
- When several children fail, the first exception is delivered and the later ones are attached as suppressed exceptions.

## 7. Shared mutable state

Coroutines on `Dispatchers.Default` or `IO` run in parallel, so unsynchronized mutation races. `@Volatile` does not make compound actions like `count++` atomic.

| Approach | Use when |
|---|---|
| `MutableStateFlow.update { }` | The state is already a `StateFlow`; the update function is retried on conflict, so keep it pure |
| `AtomicInteger`, `ConcurrentHashMap`, other thread-safe types | Counters, maps and queues with simple operations |
| Confinement to one thread (for example keep UI state on `Main`) | Most updates already happen there |
| `Mutex.withLock { }` | A multi-step critical section that may suspend |

- Never hold a `java.util.concurrent` lock or `synchronized` block across a suspension point; use `Mutex`.
- `Mutex` is not reentrant: locking it again from the coroutine that holds it suspends forever.
- `dispatcher.limitedParallelism(1)` serializes the code between suspension points but is **not** a mutex; coroutines on it still interleave at every suspension. Use `Mutex` or `Semaphore` to limit concurrent operations.

## 8. Testing

Test APIs are in `org.jetbrains.kotlinx:kotlinx-coroutines-test`. Details and flow examples: `android-testing`.

- **Wrap each test body in `runTest`** (expression body). It runs on a single thread, skips `delay` with virtual time, waits for coroutines on its scheduler, and fails after a default 60-second timeout.
- **Inject a `TestDispatcher` wherever production code takes a dispatcher.** A real dispatcher inside `withContext` brings back other threads and real delays.
- **One `TestCoroutineScheduler` per test.** Pass `testScheduler` to every dispatcher you create inside `runTest`. Once `Dispatchers.Main` is set to a `TestDispatcher`, new `TestDispatcher`s pick up its scheduler automatically, but a dispatcher created as a test class property before the rule runs gets its own scheduler. Declare the rule first and reuse its dispatcher.
- **`StandardTestDispatcher`** (the `runTest` default) queues new coroutines until the test yields: `advanceUntilIdle()`, `advanceTimeBy()`, `runCurrent()`, or `join` / `await`. It matches production scheduling; use it for tests about ordering and concurrency.
- **`UnconfinedTestDispatcher`** enters new coroutines eagerly, which suits simple tests and collectors that must be ready before values are emitted. It still suspends at the first real suspension point, and it makes no ordering guarantees. It is `@ExperimentalCoroutinesApi`.
- **Replace `Dispatchers.Main` in local unit tests** that touch `viewModelScope` (which runs on `Dispatchers.Main.immediate`). Do not replace it in instrumented tests.

```kotlin
class MainDispatcherRule(
    val testDispatcher: TestDispatcher = UnconfinedTestDispatcher(),
) : TestWatcher() {
    override fun starting(description: Description) = Dispatchers.setMain(testDispatcher)
    override fun finished(description: Description) = Dispatchers.resetMain()
}
```

- **Collectors that never finish go in `backgroundScope`**, which is cancelled when the test ends. Otherwise `runTest` waits for them and times out. A class that takes a `CoroutineScope` (an application scope, or a ViewModel through the `ViewModel(viewModelScope)` constructor) can receive `backgroundScope` or the `TestScope` itself.
- **A `stateIn(WhileSubscribed)` flow only updates while collected.** Start a collector in `backgroundScope` (for example `backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { flow.collect() }`), then assert on `.value`. Prefer asserting on `StateFlow.value` over collecting every emission, since conflation may skip intermediate values.
- **Finite flows**: `first()`, `take(n).toList()`, `toList()`. **Interleaved emit-and-assert**: collect into a list in `backgroundScope`, or use the third-party [Turbine](https://github.com/cashapp/turbine) (`flow.test { awaitItem() }`) that Google's flow testing page shows.
- A worked ViewModel test with `stateIn`, `backgroundScope` and a failing upstream is in [`review.md`](review.md).
