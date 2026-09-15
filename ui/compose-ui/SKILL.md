---
name: compose-ui
description: "Compose UI fundamentals per Google's docs: remember and saveable state, state hoisting, API conventions, modifiers, lifecycle effects, CompositionLocal, Material 3 theming, resources, previews. Use when writing, reviewing or refactoring composables, and when state resets on rotation, UI ignores list changes, modifier order looks wrong, dark theme breaks, or previews fail."
---

# Compose UI Fundamentals

Sources of truth: [State and Jetpack Compose](https://developer.android.com/develop/ui/compose/state), [Where to hoist state](https://developer.android.com/develop/ui/compose/state-hoisting), [Compose UI architecture](https://developer.android.com/develop/ui/compose/architecture), [State holders and UI state](https://developer.android.com/topic/architecture/ui-layer/stateholders), [Compose API guidelines](https://android.googlesource.com/platform/frameworks/support/+/androidx-main/compose/docs/compose-api-guidelines.md), [Compose component API guidelines](https://android.googlesource.com/platform/frameworks/support/+/androidx-main/compose/docs/compose-component-api-guidelines.md), [Compose modifiers](https://developer.android.com/develop/ui/compose/modifiers), [Lifecycle in Compose](https://developer.android.com/topic/libraries/architecture/compose), [CompositionLocal](https://developer.android.com/develop/ui/compose/compositionlocal), [Material Design 3 in Compose](https://developer.android.com/develop/ui/compose/designsystems/material3), [Resources in Compose](https://developer.android.com/develop/ui/compose/resources), [Previews](https://developer.android.com/develop/ui/compose/tooling/previews).

Related skills: `compose-side-effects` (effects and keys), `compose-lists`, `compose-adaptive-layouts`, `compose-performance` (stability, deferred reads), `compose-images`, `compose-accessibility`, `compose-testing`, `android-viewmodel`.

## 1. State inside a composable

| API | Survives | Notes |
|---|---|---|
| `remember { mutableStateOf(x) }` | Recomposition | Dropped when the call leaves the composition |
| `rememberSaveable { mutableStateOf(x) }` | Recomposition, activity recreation, system-initiated process death | Values must fit a `Bundle`; otherwise `@Parcelize`, `mapSaver` or `listSaver`. Lost when the user dismisses the activity |
| `remember(key) { ... }` | Until `key` changes (compared with `equals`) | `rememberSaveable` names the same arguments `inputs` |

- `remember` also caches objects that are expensive to build (brushes, formatters). Key it on every input the object depends on.
- State must be observable. A `MutableList`, `ArrayList` or a class with plain `var` fields changes silently and the UI shows stale data. Store an immutable `List` in a `MutableState`, or use `mutableStateListOf()`.
- Convert other observables to `State` in the composable that reads them: `Flow.collectAsStateWithLifecycle()` on Android (`androidx.lifecycle:lifecycle-runtime-compose`), `collectAsState()` only in platform-agnostic code, `LiveData.observeAsState()`, and `produceState` for custom sources.
- A composable that calls `remember` is stateful: convenient for callers, harder to reuse and test. Reusable components often ship a stateless version (value plus event lambda) and a thin stateful wrapper around it.

## 2. Where state lives

The docs split UI state into two kinds, each with its own owner:

| Kind | Examples | Owner |
|---|---|---|
| Screen UI state, produced by business logic | Articles to show, follow status, a loaded profile | Screen-level state holder, usually a `ViewModel` |
| UI element state, used by UI logic | Expanded flag, `LazyListState`, `DrawerState`, selected tab | The composable, or a plain state holder class |

Placement rules:

- Move state up to at least the lowest common parent of every composable that reads it, and at least to the highest point that writes it. Two values that change in response to the same events move together.
- Stop there. Keeping state private to one composable is correct when nobody else needs it (animation state is the usual case).
- UI element state belongs in the `ViewModel` only if business logic reads or writes it, for example query text that drives server-side suggestions.
- Pipeline order: business logic produces the state, UI logic adapts it, the UI renders it. Business logic never depends on UI logic.
- If a `ViewModel` owns Compose element state with animating suspend functions (`DrawerState.close()`, `LazyListState.animateScrollToItem()`), running them in `viewModelScope` throws `IllegalStateException` (no `MonotonicFrameClock`). Pass in a scope from `rememberCoroutineScope()` and call them inside `withContext(uiScope.coroutineContext)`.

A hoisted value becomes a `value: T` parameter plus an event lambda that proposes the new value. The UI changes state only from event handlers, never during composition.

### Screen composables and the ViewModel

The `ViewModel` is injected in one screen-level composable, typically the navigation entry. That composable turns `uiState` into a `State` with `collectAsStateWithLifecycle()` and hands plain values and event lambdas to a stateless composable. Previews and UI tests render the stateless one.

```kotlin
@Composable
fun TopicScreen(
    onBack: () -> Unit,
    viewModel: TopicViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    TopicScreen(
        uiState = uiState,
        onBack = onBack,
        onFollowChange = viewModel::setFollowed,
    )
}

@Composable
fun TopicScreen(
    uiState: TopicUiState,
    onBack: () -> Unit,
    onFollowChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) { /* ... */ }
```

- Do not hand the `ViewModel` to child composables, to plain state holder classes or to a `CompositionLocal`. Google's reasons: it couples the child to that type, breaks previews and tests, and lets many callers mutate the screen state with no single owner.
- Passing state and individual lambdas down several levels ("property drilling") is preferred over bundling them into wrapper objects: each signature shows what the composable does.
- Give each child only what it reads: `Header(title, subtitle)` rather than `Header(article)`. A new `article` instance would otherwise recompose the header even when title and subtitle are unchanged. When a parameter list grows unwieldy, group closely related values in a class.
- Navigation, list item clicks and other user actions travel up as lambdas until they reach the screen composable, which calls the `ViewModel` or the navigator.

## 3. Plain state holder classes

When UI logic grows or is shared between screens, move it out of the composable into a class created by a `remember<Name>` function. Compose's own `LazyListState` and `DrawerState` follow this pattern, and Google recommends it for reusable pieces such as search bars and chip groups instead of a `ViewModel`.

```kotlin
@Stable
class AppState(
    val windowSizeClass: WindowSizeClass,
    val drawerState: DrawerState,
) {
    val shouldShowBottomBar: Boolean
        get() = !windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_MEDIUM_LOWER_BOUND)
}

@Composable
fun rememberAppState(
    windowSizeClass: WindowSizeClass = currentWindowAdaptiveInfo().windowSizeClass,
    drawerState: DrawerState = rememberDrawerState(DrawerValue.Closed),
): AppState = remember(windowSizeClass, drawerState) {
    AppState(windowSizeClass, drawerState)
}
```

- The class lives as long as the composition that remembers it, so it may hold UI-scoped objects (`Resources`, `LazyListState`, lifecycle APIs). It does not survive recreation; give it a `Saver` and use `rememberSaveable` when it must.
- A state holder may depend only on holders with the same or a shorter lifetime. When it needs data or actions from the `ViewModel`, pass that specific `StateFlow` or lambda, not the `ViewModel`.
- A screen can use both: a `ViewModel` for business logic and a plain class for its UI logic.

## 4. Composable API conventions

These come from the Compose API guidelines. Rules there written for library development are marked as such; apps are encouraged to follow them too.

### Naming

- A composable returning `Unit` is named like a class: a PascalCase noun, optionally with adjectives (`FilterChipRow`, `BackButtonHandler`), never a verb (`RenderChips`) or lowercase (`filterChips`).
- A composable returning a value uses normal function naming (`defaultCardColors()`). If its main job is to remember and return a mutable object, it starts with `remember` (`rememberSearchBarState()`).
- A composable either emits UI or returns a value, never both. Expose control through a hoisted state object parameter instead.
- `Basic` prefix for an undecorated building block (`BasicTextField`), the plain name for the styled, ready-to-use variant. Avoid company or module prefixes.
- Event lambdas are named `on` plus what happened: `onFollowChange`, `onRetryClick`, `onDismissRequest`.

### Parameters

The component guidelines fix this order:

1. Required parameters, data first and configuration after.
2. `modifier: Modifier = Modifier`.
3. Optional parameters.
4. An optional trailing `@Composable` content lambda.

The `modifier` parameter:

- Every component that emits UI has exactly one, of type `Modifier`. Do not add `iconModifier` or `rowModifier`; expose a slot instead.
- Its default is the empty `Modifier`. A default like `Modifier.padding(8.dp)` is silently lost as soon as a caller passes its own.
- It is applied once, to the outermost layout, before the component's internal modifiers: `Box(modifier.padding(16.dp))`.
- It may be required (no default) only for components without an intrinsic size, such as a drawing surface.

Other parameter rules:

- Prefer stateless, controlled components: `checked: Boolean` plus `onCheckedChange`, not `initialChecked` with internal `remember`, so callers can apply validation.
- No `MutableState<T>` parameters: the component and the caller would share ownership. Use a value plus lambda, or a state class.
- No `State<T>` parameters: take `T`, or `() -> T` when the value should be read later (for example only during drawing).
- Do not add a parameter for something a modifier already expresses, such as `clip` or `padding`. Parameters customize the component's internal behavior.
- Defaults are public and meaningful. Put several of them in a `<Component>Defaults` object. Do not use `null` to mean "use the default"; `null` is only for real absence, like `contentDescription: String?`.
- When many related values and callbacks pile up, group them into a hoisted state type: `@Stable`, named after the composable plus `State`, an interface unless it is final, and passed with a remembered default (`state: PlayerBarState = rememberPlayerBarState()`). Never create it internally when a `null` is passed.

### Slots

- Accept `@Composable` lambdas (`title: @Composable () -> Unit`) where callers need arbitrary content, instead of multiplying `String` and style parameters.
- Give a slot a layout scope (`content: @Composable RowScope.() -> Unit`) when several children are likely.
- Prefer plain lambda slots over DSL-based slot builders.
- A slot's content must not be disposed and recreated when the component only changes its internal layout. If the slot moves between branches, wrap it with `remember(content) { movableContentOf(content) }`.

## 5. Modifiers

- The chain runs in the order it is written, and each call acts on the result of the calls before it. `Modifier.background(Color.Yellow).padding(16.dp)` paints the padding yellow; `Modifier.padding(16.dp).background(Color.Yellow)` leaves the padding unpainted. Touch areas, clipping, borders and semantics follow the same rule.
- `size` is a request bounded by the parent's constraints; `requiredSize` ignores them. `padding` changes the measured size, `offset` only moves the content. `offset` follows layout direction, `absoluteOffset` does not.
- Modifiers that only make sense in one layout (`weight` in `Row`/`Column`, `align`, `matchParentSize` in `Box`) come from that layout's scope and affect direct children only. `matchParentSize` follows the `Box` size without growing it; `fillMaxSize` would make the `Box` expand.
- Modifier chains are immutable values. Chains that never change can be stored in a top-level `val` so they are not reallocated on every recomposition, which matters most for lazy list items and composables that recompose every frame. Store a chain that uses scoped modifiers inside that scope and apply it only to direct children. Extend a stored chain with more calls or `.then(other)`.
- Values that change every frame (scroll offset, animation) belong in lambda modifiers such as `offset { }` or `graphicsLayer { }`; see `compose-performance`.

## 6. Lifecycle-aware effects

Lifecycle-aware APIs from `lifecycle-runtime-compose` replace overriding Activity or Fragment callbacks. Put the effect in the composable that needs the resource, so it is cleaned up when that UI leaves the screen.

| Need | API |
|---|---|
| Collect a `Flow` for display | `collectAsStateWithLifecycle()` |
| One-shot work on an event, nothing to undo (analytics on resume) | `LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { }` |
| Start on `ON_START`, undo on `ON_STOP` or disposal (location, sensors) | `LifecycleStartEffect(key) { ...; onStopOrDispose { } }` |
| Start on `ON_RESUME`, undo on `ON_PAUSE` or disposal (camera preview, video) | `LifecycleResumeEffect(key) { ...; onPauseOrDispose { } }` |
| Read the current state | `LocalLifecycleOwner.current.lifecycle.currentStateAsState()` |
| Cap the lifecycle of a subtree (only the settled pager page `RESUMED`) | `rememberLifecycleOwner(maxState = ...)` provided through `LocalLifecycleOwner` |

```kotlin
@Composable
fun LocationChangedEffect(
    locationManager: LocationManager,
    onLocationChanged: (Location) -> Unit,
) {
    val currentOnLocationChanged by rememberUpdatedState(onLocationChanged)
    LifecycleStartEffect(locationManager) {
        val listener = LocationListener { currentOnLocationChanged(it) }
        locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1_000L, 1f, listener)
        onStopOrDispose { locationManager.removeUpdates(listener) }
    }
}
```

- `onStopOrDispose` and `onPauseOrDispose` are mandatory. With nothing to clean up, use `LifecycleEventEffect(Lifecycle.Event.ON_START)` instead.
- `LifecycleEventEffect` never sees `ON_DESTROY`: the composition is disposed first.
- Writing to `MutableState` while the app is stopped is safe; Compose renders the change once visible.
- Other effects (`LaunchedEffect`, `DisposableEffect`, keys): see `compose-side-effects`.

## 7. CompositionLocal

A `CompositionLocal` passes a value implicitly to a whole subtree. `MaterialTheme` uses it for colors, typography and shapes. Because every reader silently depends on a provider, Google discourages overuse. Create one only if all of these hold:

- It has a sensible default, or omitting the provider is nearly impossible. Without a default, every preview and test must provide it.
- Potentially any descendant may read it, not just a few.
- It is cross-cutting, and intermediate composables should not need to know it exists.

Never put a screen's `ViewModel` or screen data in one. Alternatives, in order of preference: explicit parameters with only what the child needs; inversion of control, where the parent passes an event lambda or a content slot so the child needs no dependency.

- `compositionLocalOf`: changing the provided value recomposes only the composables that read `current`.
- `staticCompositionLocalOf`: reads are not tracked, so a change recomposes the whole provided content. Use it for values that practically never change.
- Name keys `Local` plus a noun (`LocalElevations`), not `ElevationsLocal`.

## 8. Material 3 theming and resources

### Theme

- `MaterialTheme(colorScheme, typography, shapes)` wraps the app; M3 components pick up these values automatically.
- Feature code looks tokens up by role: `MaterialTheme.colorScheme.surfaceVariant`, `MaterialTheme.typography.titleMedium`, `MaterialTheme.shapes.medium`, or the equivalent tokens of the app's own design system. A literal `Color(0xFF...)`, font size or corner radius bypasses dark theme, dynamic color and the type scale; if no token fits, add one to the theme. Google also prefers theme colors over `colorResource`, which is meant for incremental migration.
- Color roles come in accessible pairs: `onPrimary` content on `primary`, `onPrimaryContainer` on `primaryContainer`, and the same for secondary, tertiary, error and surface roles. Crossing unrelated roles (for example `primaryContainer` content on `tertiaryContainer`) gives poor contrast.
- Show emphasis by combining neutral roles (`onSurfaceVariant` on `surface`) or by font weight. For disabled content, `onX` colors with reduced alpha are acceptable.
- Pick the light or dark scheme with `isSystemInDarkTheme()`. Use `dynamicLightColorScheme(context)` / `dynamicDarkColorScheme(context)` only when `Build.VERSION.SDK_INT >= Build.VERSION_CODES.S`, and fall back to static schemes. Generate static schemes and theme code with Material Theme Builder.
- Customize a single component through its defaults functions (`CardDefaults.cardColors(...)`, `ButtonDefaults.buttonColors(...)`) rather than rebuilding it.
- M3 elevation is mostly tonal: `Surface(tonalElevation = ..., shadowElevation = ...)`.
- Experimental M3 APIs need `@OptIn(ExperimentalMaterial3Api::class)`.

### Resources

- Text: `stringResource(R.string.x, args)`; plurals: `pluralStringResource(R.plurals.x, count, count)`, passing the count twice when the string formats it.
- Resolve text in composables. UI state carries resource IDs or typed values, not a `Context` or pre-formatted strings.
- `painterResource` loads vector and bitmap drawables (and `ColorDrawable`, `AnimatedVectorDrawable`), decoding on the main thread. Animated vectors: `AnimatedImageVector.animatedVectorResource` with `rememberAnimatedVectorPainter`.
- `dimensionResource` exists for migrated XML dimensions; new spacing belongs in the design system.
- `material-icons-extended` is large and slows builds and previews; shrink release builds with R8, or import only the vectors you need.
- Bundled fonts go in `res/font`, combined into a `FontFamily` and used in the theme's `Typography`.

## 9. Previews

Previews render in Android Studio through Layoutlib: no network, no file access, some `Context` APIs missing, and no way to build a `ViewModel` or a Hilt graph. Google's advice is to define screens by the state they receive and the events they emit, then preview that stateless composable with sample data.

- **(stricter than Google)** Every screen has a preview for each distinct state it can render (content, loading, empty, error), and every reusable component in a shared UI module has at least one preview.
- Wrap previews in the app theme so colors and typography match the app.
- Built-in multipreview annotations: `@PreviewLightDark`, `@PreviewFontScales`, `@PreviewScreenSizes`, `@PreviewDynamicColors`. For a project-specific set, declare an annotation class carrying several `@Preview` annotations. Stacked multipreview annotations each render their own variants; they are not combined into a cross product.
- Several data states: a `@PreviewParameter(Provider::class)` parameter backed by a `PreviewParameterProvider<T>`. `limit` caps the count, and overriding `getDisplayName(index)` labels each preview. Back `values` with a `List`.
- `@Preview` parameters worth knowing: `widthDp`/`heightDp`, `locale`, `fontScale`, `uiMode`, `device` (`"id:..."` or `"spec:width=...,height=...,dpi=..."`), `showBackground` with `backgroundColor` as an ARGB `Long`, `showSystemUi`, and `wallpaper` for dynamic color.
- `LocalInspectionMode.current` is `true` inside a preview. Branch on it only to replace what cannot run there (remote images, platform services); for Coil images see `compose-images`.
- "Run Preview" deploys the preview to a device as an `Activity`, but ignores the annotation's parameters.

## 10. Review checklist

- [ ] Observable state only; `rememberSaveable` wherever user input or selection must survive recreation.
- [ ] Each piece of state sits at the lowest owner that reads and writes it; business-driven state lives in the `ViewModel`.
- [ ] One screen-level composable touches the `ViewModel`; everything below receives values and lambdas.
- [ ] Composable names, parameter order and the single `modifier` parameter follow the API guidelines.
- [ ] No `MutableState`, `State` or `null`-means-default parameters; defaults are public.
- [ ] Modifier order produces the intended paint, touch and clip areas.
- [ ] Lifecycle-bound work uses lifecycle effects with cleanup.
- [ ] No `ViewModel` or screen data in a `CompositionLocal`.
- [ ] Colors, type and shapes come from theme roles, used in matching pairs.
- [ ] Stateless screens and shared components have themed previews covering their states, light and dark, and large fonts.
