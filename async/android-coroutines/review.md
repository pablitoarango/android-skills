# Coroutine concurrency review and debugging

Sources of truth: [Best practices for coroutines in Android](https://developer.android.com/kotlin/coroutines/coroutines-best-practices), [Kotlin flows on Android](https://developer.android.com/kotlin/flow), [StateFlow and SharedFlow](https://developer.android.com/kotlin/flow/stateflow-and-sharedflow), [Lifecycle-aware coroutines (Views)](https://developer.android.com/topic/libraries/architecture/views/coroutines-views), [Testing coroutines](https://developer.android.com/kotlin/coroutines/test), [Testing flows](https://developer.android.com/kotlin/flow/test), [Cancellation and timeouts](https://kotlinlang.org/docs/coroutines-cancellation.html), [Coroutine exceptions handling](https://kotlinlang.org/docs/exception-handling.html), [Shared mutable state](https://kotlinlang.org/docs/shared-mutable-state-and-concurrency.html), [CoroutineExceptionHandler](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/-coroutine-exception-handler/).

The rules live in [`SKILL.md`](SKILL.md). This file is the procedure for applying them to code that already exists.

## Workflow

### 1. Reproduce what the user sees

Write down the observable symptom before reading code: an ANR dialog or Play vitals ANR cluster, a crash stack trace, a spinner that never ends, stale or duplicated UI, battery or network use in the background, a test that hangs or fails intermittently. Reproduce it the way a user would: rotate, background and return, toggle airplane mode, leave the screen mid-request, or enable "Don't keep activities" in Developer options.

### 2. Draw the coroutine tree for the failing path

For each coroutine on the path, answer:

| Question | Where to look |
|---|---|
| Which builder starts it (`launch`, `async`, `stateIn`, `callbackFlow`, `LaunchedEffect`)? | The call site |
| Which scope, and what cancels that scope? | `viewModelScope`, `lifecycleScope`, injected scope, `GlobalScope`, `CoroutineScope(...)` created ad hoc |
| Is its parent Job intact? | `Job()`, `SupervisorJob()` or `NonCancellable` passed to a builder breaks the link |
| Which dispatcher runs each step? | `withContext`, `flowOn`, the scope's context; `viewModelScope` is `Dispatchers.Main.immediate` |
| Where does a thrown exception go? | `try`/`catch`, `catch` operator, `await`, parent Job, `CoroutineExceptionHandler`, or nowhere |
| Who waits for the result? | `await`, `join`, `collect`, or nobody (fire and forget) |

For tree and thread visibility in JVM unit tests, add `CoroutineName("...")` to contexts and run with `-Dkotlinx.coroutines.debug`, which appends the coroutine name and id to thread names. If `kotlinx-coroutines-debug` is on the test classpath with `DebugProbes` installed, a `runTest` timeout prints a dump of live coroutines.

### 3. Scan for known-bad patterns

Run from the module root and review each hit in context:

```bash
rg -n 'GlobalScope|runBlocking' --type kotlin
rg -n 'withContext\(Dispatchers\.|launch\(Dispatchers\.|flowOn\(Dispatchers\.' --type kotlin
rg -n 'catch \((e|_|t|throwable|exception): (Exception|Throwable)\)|runCatching' --type kotlin
rg -n 'launchWhen(Created|Started|Resumed)|whenStarted|launchIn\((viewLifecycleOwner\.)?lifecycleScope' --type kotlin
rg -n 'SharingStarted\.(Eagerly|Lazily)' --type kotlin
rg -n 'va[lr] [a-zA-Z]+ = MutableStateFlow|va[lr] [a-zA-Z]+ = MutableSharedFlow' --type kotlin
rg -n 'suspendCoroutine|Thread\.sleep|NonCancellable|CoroutineExceptionHandler|SupervisorJob\(\)|Job\(\)' --type kotlin
rg -n 'synchronized|ReentrantLock|@Volatile' --type kotlin
```

Hits in test sources and in DI modules that provide dispatchers or the application scope are expected.

### 4. Classify with the diagnosis tables

Find the symptom below. More than one row often applies; fix the one that explains the reproduction first.

### 5. Prove it with a failing test, then fix in the owning class

Write a `runTest` test that fails for the reported reason (section "Worked fixes" has patterns). Then change the class that owns the violated responsibility: the class that blocks owns the dispatcher switch, the ViewModel owns the launch, the data layer owns the application scope. Keep public signatures unless the signature is the defect, for example a fire-and-forget function whose callers need to know when the work ends.

### 6. Verify the way it was reported

Run the new test, the module's existing tests, and the reproduction from step 1 again.

## Diagnosis tables

### Main thread and responsiveness

| Observed | Likely cause | Correction |
|---|---|---|
| ANR or dropped frames when a screen opens | Blocking I/O or parsing in a `suspend` function that never switches thread; `suspend` alone does not move work | `withContext(injectedDispatcher)` inside the function that blocks |
| ANR on startup or in a `BroadcastReceiver` | `runBlocking` on the main thread | Make the caller suspend, or launch in an owned scope; `goAsync()` for receivers |
| UI freezes while a `Flow` is collected | Heavy `map` / `filter` upstream running on `Main` | `flowOn(injectedDispatcher)` below the heavy operators |
| Callers wrap a repository call in `withContext(Dispatchers.IO)` | The repository is not main-safe, or callers do not trust it | Make the repository main-safe and remove the callers' wrappers |

### Lifetime and leaks

| Observed | Likely cause | Correction |
|---|---|---|
| Network or location keeps running after leaving the screen | `GlobalScope`, an ad hoc `CoroutineScope(...)` never cancelled, or `SharingStarted.Eagerly` in a ViewModel | Owner scope from section 2 of `SKILL.md`; `WhileSubscribed(5_000)` for UI state |
| Work restarts or duplicates after rotation | Started from `lifecycleScope` or from composition instead of `viewModelScope` | Move the launch into the ViewModel and expose state |
| A save or upload is lost when the user navigates away | Launched in `viewModelScope` although it must finish | Injected application scope in the data layer, or WorkManager if it must survive process death |
| Listener, receiver or sensor stays registered | `callbackFlow` without cleanup, or cleanup outside `awaitClose` | Unregister inside `awaitClose { }` |
| Coroutine not cancelled with its screen | `Job()` / `SupervisorJob()` passed to `launch` or `withContext` | Remove it; use `supervisorScope` if siblings must fail independently |

### Lifecycle collection

| Observed | Likely cause | Correction |
|---|---|---|
| Crash touching views after `onStop`, or updates while in background | `lifecycleScope.launch { flow.collect }` or `launchIn(lifecycleScope)` | `repeatOnLifecycle(STARTED)` or `flowWithLifecycle`; `collectAsStateWithLifecycle()` in Compose |
| Upstream still active while the app is in background | `launchWhenStarted` / `whenStarted` pause instead of cancel | Replace with `repeatOnLifecycle` |
| Fragment collection leaks across view recreation | Collected with the Fragment's `lifecycleScope` instead of `viewLifecycleOwner` | `viewLifecycleOwner.lifecycleScope` and `viewLifecycleOwner.repeatOnLifecycle` |
| Only the first of several flows updates | Sequential `collect` calls in one block; the first never returns | One `launch` per flow inside `repeatOnLifecycle` |

### Cancellation and timeouts

| Observed | Likely cause | Correction |
|---|---|---|
| Work continues after its scope was cancelled | Loop or blocking code with no suspension point | `ensureActive()` per iteration; `runInterruptible` around interruptible blocking calls |
| Coroutine keeps going after cancellation, often logging an error | `catch (e: Exception)`, `catch (e: Throwable)` or `runCatching` consumed `CancellationException` | Catch specific types; rethrow cancellation; `suspendRunCatching` |
| Operation silently stops, no error, no result | `withTimeout` threw `TimeoutCancellationException`, which ends a `launch` as a cancellation | `withTimeoutOrNull` and handle `null` |
| Timeout never fires | Code inside the block does not cooperate with cancellation | Make the block cancellable first |
| Callback-based suspend call hangs after cancel | `suspendCoroutine` | `suspendCancellableCoroutine` with `invokeOnCancellation` |
| File, cursor or stream left open when the screen closes | Resource returned across a cancellation point | Close in `finally`; suspending cleanup in `withContext(NonCancellable)` |

### Exceptions and crashes

| Observed | Likely cause | Correction |
|---|---|---|
| Crash from `viewModelScope` with an `IOException` | Expected failure not caught inside the coroutine | `try`/`catch` near the call, map to UI state |
| Crash from a `StateFlow` built with `stateIn` | Upstream threw; the sharing coroutine fails into `viewModelScope` | `catch { }` before `stateIn`, emit an error state |
| Handler installed but crash still happens, or handler never called | `CoroutineExceptionHandler` on a child `launch` or on `async` | Handle with `try`/`catch`; install handlers only on root or directly supervised `launch` |
| Exception disappears | `async` never awaited, or failure lost in `launch { }.join()` | `await` every `async`; use `async { }.await()` when the caller must see the failure |
| One failing child cancels unrelated siblings | Siblings under `coroutineScope` or a regular `Job` | `supervisorScope` or `SupervisorJob`, with per-child handling |
| `IllegalStateException: Flow invariant is violated` | `emit` from `withContext` or from a launched coroutine inside `flow { }` | `flowOn`, or `channelFlow` for concurrent producers |

### Shared state and ordering

| Observed | Likely cause | Correction |
|---|---|---|
| Lost updates, wrong counts, `ConcurrentModificationException` | Mutable field written from coroutines on `Default` / `IO` | `MutableStateFlow.update`, atomic or concurrent types, or `Mutex` |
| Read-modify-write on `StateFlow` loses changes | `_state.value = _state.value.copy(...)` from several coroutines | `_state.update { it.copy(...) }` |
| Deadlock after adding a lock | Nested `Mutex.withLock` on the same mutex, or a JVM lock held across a suspension | Restructure the critical section; `Mutex` is not reentrant |
| Duplicate requests, for example several token refreshes at once | Check-then-act without mutual exclusion | Guard the check and the action with one `Mutex` |
| Intermediate `StateFlow` values missing | `StateFlow` conflates | Expected; model each event as state, or use a flow that does not conflate if every value matters |

### Tests

| Observed | Likely cause | Correction |
|---|---|---|
| Main dispatcher fails to initialize, or `Looper` not mocked | Local test touches `viewModelScope` or `Dispatchers.Main` without replacing `Main` | `MainDispatcherRule` |
| Test hangs until the 60-second `runTest` timeout | Infinite collector launched in the test scope | Launch it in `backgroundScope` |
| `stateIn` value never changes | No collector, so `WhileSubscribed` never starts upstream | Collector in `backgroundScope` before asserting |
| Assertion runs before the work | New coroutines queued on `StandardTestDispatcher` | `advanceUntilIdle()` / `runCurrent()`, or `await` a returned `Deferred` |
| Delays not skipped, flaky timing | Real dispatcher inside the code under test, or a second scheduler | Inject `TestDispatcher`s sharing `testScheduler` |
| `Thread.sleep` or `CountDownLatch` in coroutine tests | Waiting on real threads | Virtual time and test dispatchers |

## Worked fixes

### Crash when a stream fails behind `stateIn`

Before: an `IOException` from the socket-backed stream fails the sharing coroutine and crashes the app.

```kotlin
class OrderTrackingViewModel(repository: OrderRepository, orderId: String) : ViewModel() {
    val uiState: StateFlow<OrderUiState> = repository.observeOrder(orderId)
        .map { order -> OrderUiState.Tracking(order.status) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), OrderUiState.Loading)
}
```

After: the failure becomes state before it reaches `stateIn`.

```kotlin
class OrderTrackingViewModel(repository: OrderRepository, orderId: String) : ViewModel() {
    val uiState: StateFlow<OrderUiState> = repository.observeOrder(orderId)
        .map<Order, OrderUiState> { order -> OrderUiState.Tracking(order.status) }
        .catch { error ->
            if (error !is IOException) throw error
            emit(OrderUiState.Unavailable)
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), OrderUiState.Loading)
}
```

Test that proves both paths:

```kotlin
class FakeOrderRepository : OrderRepository {
    private val updates = MutableSharedFlow<Order>()
    var streamFailure: Throwable? = null

    override fun observeOrder(orderId: String): Flow<Order> = flow {
        streamFailure?.let { throw it }
        emitAll(updates.filter { it.id == orderId })
    }

    suspend fun push(order: Order) = updates.emit(order)
}

class OrderTrackingViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private val repository = FakeOrderRepository()

    @Test
    fun uiState_followsOrderStatus() = runTest {
        val viewModel = OrderTrackingViewModel(repository, orderId = "A-17")
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { viewModel.uiState.collect() }

        assertEquals(OrderUiState.Loading, viewModel.uiState.value)
        repository.push(Order(id = "A-17", status = OrderStatus.Shipped))
        assertEquals(OrderUiState.Tracking(OrderStatus.Shipped), viewModel.uiState.value)
    }

    @Test
    fun uiState_isUnavailable_whenStreamFails() = runTest {
        repository.streamFailure = IOException("socket closed")
        val viewModel = OrderTrackingViewModel(repository, orderId = "A-17")
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { viewModel.uiState.collect() }

        assertEquals(OrderUiState.Unavailable, viewModel.uiState.value)
    }
}
```

### Timeout that ends silently

Before: when the geocoder is slow, `withTimeout` cancels the coroutine, nothing is shown, and no error is logged.

```kotlin
fun onLocationPicked(point: GeoPoint) {
    viewModelScope.launch {
        val address = withTimeout(3.seconds) { geocoder.reverseGeocode(point) }
        _uiState.update { it.copy(address = address) }
    }
}
```

After: the timeout is an ordinary outcome that the UI can show.

```kotlin
fun onLocationPicked(point: GeoPoint) {
    viewModelScope.launch {
        val address = withTimeoutOrNull(3.seconds) { geocoder.reverseGeocode(point) }
        _uiState.update {
            if (address != null) it.copy(address = address, addressLookupFailed = false)
            else it.copy(addressLookupFailed = true)
        }
    }
}
```

### Concurrent token refresh

Before: five requests receive `401` at the same time and each one refreshes the token.

```kotlin
class SessionManager(private val authApi: AuthApi, private val tokenStore: TokenStore) {
    suspend fun validToken(): String {
        val current = tokenStore.read()
        if (!current.isExpired()) return current.value
        val refreshed = authApi.refresh(current.refreshToken)
        tokenStore.write(refreshed)
        return refreshed.value
    }
}
```

After: one `Mutex` covers the check and the refresh, so waiting callers reuse the new token.

```kotlin
class SessionManager(private val authApi: AuthApi, private val tokenStore: TokenStore) {
    private val refreshMutex = Mutex()

    suspend fun validToken(): String = refreshMutex.withLock {
        val current = tokenStore.read()
        if (!current.isExpired()) return@withLock current.value
        val refreshed = authApi.refresh(current.refreshToken)
        tokenStore.write(refreshed)
        refreshed.value
    }
}
```

Test the race with `StandardTestDispatcher` so several callers are queued before any of them runs:

```kotlin
@Test
fun validToken_refreshesOnce_forConcurrentCallers() = runTest {
    val authApi = FakeAuthApi(refreshDelay = 100.milliseconds)
    val sessionManager = SessionManager(authApi, FakeTokenStore(expiredToken))

    val tokens = List(5) { async { sessionManager.validToken() } }.awaitAll()

    assertEquals(1, authApi.refreshCalls)
    assertEquals(1, tokens.toSet().size)
}
```

### Export loop that ignores cancellation

Before: leaving the screen does not stop an export of thousands of rows, because nothing in the loop suspends.

```kotlin
suspend fun exportCsv(rows: List<Row>, out: File) = withContext(ioDispatcher) {
    out.bufferedWriter().use { writer ->
        rows.forEach { row -> writer.appendLine(row.toCsvLine()) }
    }
}
```

After: the loop checks for cancellation, and `use` still closes the writer when cancellation is thrown.

```kotlin
suspend fun exportCsv(rows: List<Row>, out: File) = withContext(ioDispatcher) {
    out.bufferedWriter().use { writer ->
        rows.forEach { row ->
            ensureActive()
            writer.appendLine(row.toCsvLine())
        }
    }
}
```

## Report

- Symptom as reproduced, and the reproduction steps.
- The coroutine tree for the failing path, with the broken link marked (scope, Job, dispatcher, or exception path), and file and line references.
- The fix as a diff in the owning class, and why the smaller alternatives were rejected.
- The test that failed before and passes after, plus the re-run of the original reproduction.
