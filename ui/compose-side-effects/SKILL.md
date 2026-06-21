---
name: compose-side-effects
description: "Compose effects per Google's docs: LaunchedEffect keys, rememberCoroutineScope, rememberUpdatedState, DisposableEffect, produceState, derivedStateOf, snapshotFlow. Use when a composable launches work, registers listeners, or reacts to state."
---

# Compose Side Effects

Sources of truth: [Side-effects in Compose](https://developer.android.com/develop/ui/compose/side-effects), [State](https://developer.android.com/develop/ui/compose/state), [Performance best practices](https://developer.android.com/develop/ui/compose/performance/bestpractices).

Composables must be **free of side effects**: they only describe UI from their inputs and may run at any time, in any order, as often as every frame. Any work that changes something outside the composition goes through an effect API.

## 1. Pick the effect

| Need | API |
|---|---|
| Run suspending work tied to the composable, restarting when inputs change | `LaunchedEffect(keys) { }` |
| Launch a coroutine from an event handler (click, gesture) | `rememberCoroutineScope()` |
| Register something that must be cleaned up (listener, observer, receiver) | `DisposableEffect(keys) { ...; onDispose { } }` |
| Publish Compose state to non-Compose objects after every successful recomposition | `SideEffect { }` |
| Turn a non-Compose source (Flow, callback, repository call) into `State` | `produceState(initial, keys) { }` |
| Recompose only when a computed value actually changes | `remember { derivedStateOf { } }` |
| Use Flow operators on Compose state | `snapshotFlow { }` inside `LaunchedEffect` |
| Start and stop work with the Activity lifecycle | `LifecycleStartEffect` / `LifecycleResumeEffect` (see `compose-ui`) |
| Observe a ViewModel `StateFlow` | `collectAsStateWithLifecycle()` (see `android-viewmodel`) |

Business logic, data loading and anything that must survive configuration changes belong in the ViewModel, not in an effect.

## 2. Keys decide when an effect restarts

**Every value the effect block reads must be a key**, unless it is wrapped in `rememberUpdatedState` or never changes.

```kotlin
@Composable
fun HomeScreen(
    onStart: () -> Unit,
    onStop: () -> Unit,
    lifecycleOwner: LifecycleOwner = LocalLifecycleOwner.current,
) {
    val currentOnStart by rememberUpdatedState(onStart)
    val currentOnStop by rememberUpdatedState(onStop)

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> currentOnStart()
                Lifecycle.Event.ON_STOP -> currentOnStop()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
}
```

- Too few keys: the effect keeps using stale values (bug).
- Too many keys: the effect restarts needlessly (wasted work, restarted animations).
- A constant key (`LaunchedEffect(Unit)` / `LaunchedEffect(true)`) ties the effect to the call site's lifetime. Treat it like `while (true)`: use it only when the effect must never restart, and read changing values through `rememberUpdatedState`.

```kotlin
@Composable
fun LandingScreen(onTimeout: () -> Unit) {
    val currentOnTimeout by rememberUpdatedState(onTimeout)
    LaunchedEffect(Unit) {
        delay(SplashWaitTimeMillis)
        currentOnTimeout()
    }
}
```

## 3. Effect APIs

### LaunchedEffect
Launches when entering composition, is cancelled when leaving, and restarts when a key changes.

```kotlin
LaunchedEffect(pulseRateMs) {
    while (isActive) {
        delay(pulseRateMs)
        alpha.animateTo(0f)
        alpha.animateTo(1f)
    }
}
```

### rememberCoroutineScope
For coroutines started by user events. The scope is cancelled when the call site leaves composition. Never call `launch` directly in the composable body.

```kotlin
val scope = rememberCoroutineScope()
Button(onClick = { scope.launch { snackbarHostState.showSnackbar(message) } }) {
    Text(stringResource(R.string.show))
}
```

### DisposableEffect
The block must end with `onDispose { }`, and that block must actually undo what the effect did. An empty `onDispose` means you want a different API.

### SideEffect
Runs after every successful recomposition; use it to push Compose state into objects Compose does not manage.

```kotlin
@Composable
fun rememberAnalytics(user: User): Analytics {
    val analytics = remember { Analytics() }
    SideEffect { analytics.setUserProperty("userType", user.userType) }
    return analytics
}
```

### produceState
Converts a non-Compose source into `State`. Use `awaitDispose { }` to unsubscribe from callback sources.

```kotlin
@Composable
fun loadNetworkImage(url: String, imageRepository: ImageRepository): State<Result<Image>> =
    produceState<Result<Image>>(initialValue = Result.Loading, url, imageRepository) {
        val image = imageRepository.load(url)
        value = if (image == null) Result.Error else Result.Success(image)
    }
```

### derivedStateOf
Use **only** when the inputs change more often than the result you need. It has a cost.

```kotlin
val showScrollToTop by remember {
    derivedStateOf { listState.firstVisibleItemIndex > 0 }
}
```

When the result changes as often as its inputs, compute it directly:

```kotlin
val fullName = "$firstName $lastName"
```

If a `derivedStateOf` reads a composable parameter that can change, pass it as a `remember` key.

### snapshotFlow
Turns state reads into a cold Flow that emits when the read values change (conflated, like `distinctUntilChanged`).

```kotlin
LaunchedEffect(listState) {
    snapshotFlow { listState.firstVisibleItemIndex }
        .map { it > 0 }
        .distinctUntilChanged()
        .filter { it }
        .collect { analytics.sendScrolledPastFirstItemEvent() }
}
```

## 4. Never write state during composition

Writing to state that was already read in the same composition (a **backwards write**) causes endless recomposition. Write state only from event lambdas or effects.

```kotlin
@Composable
fun Counter() {
    var count by remember { mutableIntStateOf(0) }
    Button(onClick = { count++ }) { Text("$count") }
}
```

## 5. Compose animation state and the ViewModel

Suspend functions on Compose UI state holders that animate (`LazyListState.animateScrollToItem`, `DrawerState.close`) need the composition's frame clock. Calling them from `viewModelScope` throws `IllegalStateException`. Call them from `rememberCoroutineScope()` or `LaunchedEffect`; if a ViewModel must drive one, pass the UI scope in and switch with `withContext(uiScope.coroutineContext)`.

## 6. Checklist

- [ ] No coroutine launches, listener registrations or state writes in the composable body.
- [ ] Every value read inside an effect is a key or goes through `rememberUpdatedState`.
- [ ] `LaunchedEffect(Unit)` / `(true)` is used only when the effect must never restart.
- [ ] Every `DisposableEffect` cleans up in `onDispose`.
- [ ] `derivedStateOf` is only used where the result changes less often than its inputs.
- [ ] Animating Compose state is driven from a composition scope, not `viewModelScope`.
