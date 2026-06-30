# RxJava operators in Flow

Part of `migrate-rxjava-to-coroutines`. Sources: [Flow API reference](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/), [Asynchronous Flow](https://kotlinlang.org/docs/coroutines-flow.html), [RxJava wiki operator pages](https://github.com/ReactiveX/RxJava/wiki).

Before translating a chain operator by operator, check what it produces. A `Single`, `Maybe` or `Completable` chain usually becomes plain sequential code in a `suspend` function: `map` becomes an expression, `flatMap` becomes the next `suspend` call, `doOnSuccess` becomes a statement, `onErrorReturn` becomes `try` / `catch`. Use the tables below for chains that stay streams.

Opt-in: `debounce`, `sample` and `timeout` are `@FlowPreview`; `flatMapConcat`, `flatMapMerge`, `flatMapLatest`, `mapLatest`, `transformLatest` and `chunked` are `@ExperimentalCoroutinesApi`. Check each API page for its current status before adding `@OptIn`.

## Creating sources

| RxJava | Flow or coroutines | Check |
|---|---|---|
| `just(a, b)` | `flowOf(a, b)` | |
| `fromIterable(list)` | `list.asFlow()` | |
| `fromCallable { }` | A `suspend` function, or `flow { emit(block()) }` | |
| `defer { }` | `flow { }` | The builder body already runs again for every collector |
| `create { emitter -> }` | `callbackFlow { ...; awaitClose { unregister() } }` | See `android-coroutines` for callback wrapping |
| `empty()` / `never()` / `error(e)` | `emptyFlow()` / `flow { awaitCancellation() }` / `flow { throw e }` | |
| `interval(period)` | `flow { while (true) { emit(Unit); delay(period) } }` | The channel `ticker` API is `@ObsoleteCoroutinesApi` |
| `timer(delay)` | `delay(d)` in suspend code, or `flow { delay(d); emit(Unit) }` | |
| `using(open, source, close)` | `flow { val r = open(); try { emitAll(source(r)) } finally { r.close() } }` | |

## Per-value transformation

| RxJava | Flow | Check |
|---|---|---|
| `map` | `map` | The lambda is `suspend`, so it can call repositories directly |
| `map` followed by null filtering | `mapNotNull` | |
| `ofType(R::class.java)` | `filterIsInstance<R>()` | |
| `flatMapIterable { it }` | `transform { list -> list.forEach { emit(it) } }` | |
| `startWithItem(x)` | `onStart { emit(x) }` | RxJava 3 renamed `startWith(T)` to `startWithItem` |
| `defaultIfEmpty(x)` | `onEmpty { emit(x) }` | |
| `switchIfEmpty(other)` | `onEmpty { emitAll(other) }` | |

## Selecting values

| RxJava | Flow | Check |
|---|---|---|
| `filter` | `filter` | |
| `distinctUntilChanged()` | `distinctUntilChanged()` | Redundant on a `StateFlow`, which already skips equal values |
| `distinctUntilChanged { it.id }` | `distinctUntilChangedBy { it.id }` | |
| `take(n)` | `take(n)` | Cancels the upstream after `n` values |
| `takeWhile(p)` | `takeWhile(p)`, or `transformWhile` to also emit the value that ends it | |
| `skip(n)` / `skipWhile(p)` | `drop(n)` / `dropWhile(p)` | |
| `elementAt(i)` | `drop(i).first()` | |
| `takeUntil(signal)` | No operator; cancel the collecting `Job` when the signal arrives | |
| `ignoreElements()` | `collect()` with no action | Returns when the upstream completes |

## Nested sources

| RxJava | Flow or coroutines | Check |
|---|---|---|
| `flatMap` | `flatMapMerge(concurrency) { }` | Flow collects at most `DEFAULT_CONCURRENCY` (16) inner flows at once; RxJava's `Observable.flatMap` is unbounded and `Flowable.flatMap` uses `bufferSize()`. The Flow docs discourage `flatMapMerge` in app code: a `suspend` call inside `map` is often enough |
| `concatMap` | `flatMapConcat` | One inner flow at a time, order kept |
| `switchMap` | `flatMapLatest` | A new upstream value cancels the running inner flow |
| `switchMapSingle { load(it) }` | `mapLatest { load(it) }` | The previous `load` is cancelled |
| `concatMapSingle { load(it) }` | `map { load(it) }` | Sequential |
| `flatMapSingle` with parallelism | `flatMapMerge { flow { emit(load(it)) } }` | |
| `flatMapCompletable { save(it) }` | `collect { save(it) }` | |
| `fromIterable(ids).flatMapSingle(::load).toList()` | `coroutineScope { ids.map { async { load(it) } }.awaitAll() }` | `awaitAll` fails as soon as one call fails, and the scope cancels the rest |

## Several sources

| RxJava | Flow or coroutines | Check |
|---|---|---|
| `Single.zip(a, b, f)` | `coroutineScope { val x = async { a() }; val y = async { b() }; f(x.await(), y.await()) }` | A failure in one call cancels the other |
| `zip` (streams) | `zip` | Pairs values by position; finishes when either flow finishes and cancels the other |
| `combineLatest` | `combine` | Uses the most recent value of each flow |
| `withLatestFrom(state)` | Read `stateFlow.value` inside `map`, or `combine` if changes in the other source must also emit | |
| `merge` / `mergeWith` | `merge(a, b)` | Collects concurrently; values interleave |
| `concat` / `concatWith` | `flow { emitAll(a); emitAll(b) }` | |

## Accumulating and ending a stream

| RxJava | Flow | Check |
|---|---|---|
| `scan(seed, f)` | `scan(seed, f)` (alias `runningFold`) | Emits the seed first; keep the seed immutable, it is shared between collectors |
| `scan(f)` without seed | `runningReduce(f)` | |
| `reduce` | `reduce` | Terminal; throws `NoSuchElementException` on an empty flow |
| `buffer(count)` | `chunked(count)` | Time-based buffers and `window` have no operator |
| `toList()` / `count()` | `toList()` / `count()` | Terminal `suspend` calls |
| `firstOrError()` / `firstElement()` | `first()` / `firstOrNull()` | |
| `singleOrError()` | `single()` | |
| `lastElement()` | `lastOrNull()` | |

## Time

| RxJava | Flow or coroutines | Check |
|---|---|---|
| `debounce(t)` | `debounce(t)` | Emits a value only after `t` without newer values; the latest value is always emitted |
| `sample(t)` / `throttleLast(t)` | `sample(t)` | Emits the latest value of each period; the final value is dropped if it does not fit a window |
| `throttleFirst(t)` | Custom operator below | `sample` emits different values at different times |
| `throttleLatest(t)` | `conflate().onEach { delay(t) }` | Approximation: first value immediately, then the latest value after each wait |
| `timeout(t)` on a stream | `timeout(t)` | Fails with `TimeoutCancellationException` when the upstream is silent for `t`; slow downstream processing does not count |
| `timeout(t)` on a `Single` | `withTimeout(t) { }` or `withTimeoutOrNull(t) { }` | `TimeoutCancellationException` is a `CancellationException`; catch it explicitly or use the `OrNull` variant |
| `delay(t)` | `onEach { delay(t) }` | |
| `delaySubscription(t)` | `onStart { delay(t) }` | |

```kotlin
fun <T> Flow<T>.throttleFirst(
    window: Duration,
    timeSource: TimeSource.WithComparableMarks = TimeSource.Monotonic,
): Flow<T> = flow {
    var windowEnd: ComparableTimeMark? = null
    collect { value ->
        val now = timeSource.markNow()
        val end = windowEnd
        if (end == null || now >= end) {
            windowEnd = now + window
            emit(value)
        }
    }
}
```

In tests, pass `testScheduler.timeSource` so the window follows virtual time.

## Backpressure and rate

A Flow emitter suspends until the collector is ready; without an explicit operator nothing is dropped or queued.

| RxJava | Flow | Check |
|---|---|---|
| `onBackpressureBuffer()` | `buffer()` | Runs the upstream in a separate coroutine with a channel |
| `onBackpressureBuffer(n)` with an overflow strategy | `buffer(n, BufferOverflow.DROP_OLDEST)` or `DROP_LATEST` | |
| `onBackpressureLatest()` | `conflate()` | Same as `buffer(0, DROP_OLDEST)`; no effect on a `StateFlow` |
| `onBackpressureDrop()` | `buffer(0, BufferOverflow.DROP_LATEST)` | Close, not exact: a drop strategy still keeps one buffered element |
| `observeOn(scheduler)` for buffering | `flowOn` / `buffer` | Adjacent `buffer`, `flowOn` and `conflate` fuse into one channel |

## Side effects

| RxJava | Flow | Check |
|---|---|---|
| `doOnNext` | `onEach` | |
| `doOnSubscribe` | `onStart` | On a `SharedFlow`, `onSubscription` also guarantees delivery of values emitted inside the action |
| `doOnComplete` | `onCompletion { cause -> if (cause == null) ... }` | |
| `doOnError` | `catch { e -> log(e); throw e }` | `catch` sees upstream failures only |
| `doOnDispose` | `onCompletion { cause -> if (cause is CancellationException) ... }` | |
| `doFinally` / `doAfterTerminate` | `onCompletion { }` | Runs on success, failure and cancellation, and also observes downstream failures |

## Errors and retries

| RxJava | Flow | Check |
|---|---|---|
| `onErrorReturn { e -> fallback(e) }` | `catch { e -> emit(fallback(e)) }` | Handles failures above it only; rethrow what you do not handle; the flow then completes |
| `onErrorReturnItem(x)` | `catch { emit(x) }` | |
| `onErrorResumeNext { other }` / `onErrorResumeWith(other)` | `catch { emitAll(other) }` | |
| `onErrorComplete()` | `catch { e -> if (e !is IOException) throw e }` | Completes without emitting |
| `retry(n)` | `retry(n)` | Never retries cancellation; the optional predicate is `suspend`, so it can `delay` |
| `retry { e -> p(e) }` / `retryUntil` | `retry { e -> p(e) }` | |
| `retryWhen` with a backoff timer | `retryWhen { cause, attempt -> ... }` | `attempt` starts at 0; `delay` inside the predicate before returning `true` |

To keep a long-lived stream alive after one failed item (for example, a search that should survive a failed query), catch inside the `mapLatest` / `flatMapLatest` lambda instead of on the outer flow.
