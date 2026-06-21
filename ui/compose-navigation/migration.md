# Migrate from Navigation 2 to Navigation 3

Part of `compose-navigation`. Follows Google's [migration guide](https://developer.android.com/guide/navigation/navigation-3/migration-guide); code adapted from it and from [nav3-recipes](https://github.com/android/nav3-recipes) (Apache 2.0). Re-read the guide before migrating; it changes with each Navigation 3 release.

## 0. Check before touching code

**Prerequisites**

- `compileSdk` 36 or higher, `minSdk` 23 or higher.
- Every destination is a composable. Fragment or View destinations must first become composables (interop in `migrate-xml-to-compose`).
- Routes are already type-safe. If the app uses string routes, migrate to type-safe Navigation 2 routes first.
- Tests cover the current navigation behavior, so the migration can be verified. Add them first if missing.

**Assumptions of the guide.** Confirm each holds; if one does not, stop and ask the user how to proceed:

- One or more top-level routes (typically a navigation bar), each with its own back stack.
- Switching tabs retains each stack and its destinations' state.
- The user always exits through the start (Home) route.
- The migration happens in one atomic change, not incrementally alongside Navigation 2.

**Covered by the guide:** composable destinations, dialog destinations.

**Covered by recipes:** bottom sheets, modularized navigation with injected entries, passing arguments to ViewModels, returning results. If the project uses any, read the matching recipe and agree a plan with the user before changing code.

**Not covered:** more than one level of nested navigation, destinations shared between back stacks, custom destination types. If the project uses any, stop and report it to the user.

## 1. Add Navigation 3 dependencies

Add `androidx.navigation3:navigation3-runtime`, `androidx.navigation3:navigation3-ui` and, if screens use ViewModels, `androidx.lifecycle:lifecycle-viewmodel-navigation3`. Take versions from the [get started page](https://developer.android.com/guide/navigation/navigation-3/get-started) and release notes. Keep the Navigation 2 dependencies until step 8.

## 2. Make every route a NavKey

```kotlin
@Serializable data object RouteA : NavKey
@Serializable data class RouteB(val id: String) : NavKey
```

Implementing `NavKey` is what lets `rememberNavBackStack` save the stack.

## 3. Add a navigation state holder and a navigator

Create these two files (package name adjusted). They replace `NavController`: `NavigationState` holds one saved back stack per top-level route plus the selected top-level route; `Navigator` turns navigation events into state changes.

```kotlin
@Composable
fun rememberNavigationState(startRoute: NavKey, topLevelRoutes: Set<NavKey>): NavigationState {
    val topLevelRoute = rememberSerializable(
        startRoute, topLevelRoutes,
        serializer = MutableStateSerializer(NavKeySerializer()),
    ) {
        mutableStateOf(startRoute)
    }
    val backStacks = topLevelRoutes.associateWith { key -> rememberNavBackStack(key) }
    return remember(startRoute, topLevelRoutes) {
        NavigationState(startRoute = startRoute, topLevelRoute = topLevelRoute, backStacks = backStacks)
    }
}

class NavigationState(
    val startRoute: NavKey,
    topLevelRoute: MutableState<NavKey>,
    val backStacks: Map<NavKey, NavBackStack<NavKey>>,
) {
    var topLevelRoute: NavKey by topLevelRoute

    val stacksInUse: List<NavKey>
        get() = if (topLevelRoute == startRoute) listOf(startRoute) else listOf(startRoute, topLevelRoute)
}

@Composable
fun NavigationState.toEntries(entryProvider: (NavKey) -> NavEntry<NavKey>): SnapshotStateList<NavEntry<NavKey>> {
    val decoratedEntries = backStacks.mapValues { (_, stack) ->
        rememberDecoratedNavEntries(
            backStack = stack,
            entryDecorators = listOf(rememberSaveableStateHolderNavEntryDecorator<NavKey>()),
            entryProvider = entryProvider,
        )
    }
    return stacksInUse.flatMap { decoratedEntries[it] ?: emptyList() }.toMutableStateList()
}
```

```kotlin
class Navigator(val state: NavigationState) {
    fun navigate(route: NavKey) {
        if (route in state.backStacks.keys) {
            state.topLevelRoute = route
        } else {
            state.backStacks[state.topLevelRoute]?.add(route)
        }
    }

    fun goBack() {
        val currentStack = state.backStacks[state.topLevelRoute]
            ?: error("Stack for ${state.topLevelRoute} not found")
        if (currentStack.last() == state.topLevelRoute) {
            state.topLevelRoute = state.startRoute
        } else {
            currentStack.removeLastOrNull()
        }
    }
}
```

- `rememberSerializable` is intentional; do not change it to `rememberSaveable`.
- If destinations use ViewModels, add `rememberViewModelStoreNavEntryDecorator()` after the saveable state decorator in `toEntries`. With several back stacks, the lifecycle release notes describe an overload taking a hoisted `ViewModelStoreProvider` for entries that exist in more than one stack.

Create both where the `NavController` was created:

```kotlin
val navigationState = rememberNavigationState(startRoute = Home, topLevelRoutes = setOf(Home, Search, Profile))
val navigator = remember { Navigator(navigationState) }
```

## 4. Replace NavController usages

Work through every `NavController` reference:

| Navigation 2 | Navigation 3 |
|---|---|
| `navController.navigate(route)` | `navigator.navigate(route)` |
| `navController.popBackStack()` | `navigator.goBack()` |
| `currentBackStack` | `navigationState.backStacks[navigationState.topLevelRoute]` |
| `currentBackStackEntry`, `currentBackStackEntryAsState()`, `currentDestination` | `navigationState.backStacks[navigationState.topLevelRoute].last()` |
| Selected navigation bar item via `destination.hierarchy.any { it.hasRoute(...) }` | `key == navigationState.topLevelRoute` |
| `previousBackStackEntry.savedStateHandle.set(...)` | `LocalResultEventBus.current.sendResult(...)` (step 4.2) |
| `currentBackStackEntry.savedStateHandle.getLiveData(...)` / `getStateFlow(...)` | `ResultEffect` (events) or `conflateAsState` (state) |
| `navOptions { popUpTo(...); launchSingleTop = true }` | Explicit edits to the back stack list in `Navigator` |

Finish with no `NavController` references or imports left.

### 4.1 Lifecycle-aware code

`NavBackStackEntry` was the `LifecycleOwner` in Navigation 2. In Navigation 3, each entry's content gets its own `LocalLifecycleOwner`, so collect inside the destination without passing an owner:

```kotlin
val state by flow.collectAsStateWithLifecycle()
```

### 4.2 Results

Add `rememberResultEventBusNavEntryDecorator()` to the decorators. The sender's `entry` calls `LocalResultEventBus.current.sendResult(result = value)` and then `navigator.goBack()`; the receiver uses `ResultEffect<T> { ... }`. Unlike `SavedStateHandle`, the bus does not survive process death; results that must survive go in a key, a scoped ViewModel's `SavedStateHandle` or `rememberSaveable`. Requires Navigation 3 1.2.

## 5. Move destinations into an entryProvider

Create the provider at the same scope as `NavigationState`:

```kotlin
val entryProvider = entryProvider<NavKey> {
}
```

Then convert each `NavHost` destination:

| In `NavHost` | Becomes |
|---|---|
| `navigation<BaseRoute>(startDestination = FirstChild) { ... }` | Delete it and `BaseRoute`; keep the children. Replace references to `BaseRoute` (often the navigation bar list) with `FirstChild` |
| `composable<Route> { entry -> }` | `entry<Route> { key -> }` |
| `dialog<Route> { }` | `entry<Route>(metadata = DialogSceneStrategy.dialog()) { }` |
| `bottomSheet` | Copy `BottomSheetSceneStrategy` from the bottom sheet recipe and use its metadata |
| `NavGraphBuilder.featureSection()` | `EntryProviderScope<NavKey>.featureSection()` |
| `entry.toRoute<Route>().id` | `key.id` from the `entry` lambda |
| `hiltViewModel()` with `SavedStateHandle.toRoute()` | `hiltViewModel` with `creationCallback` passing the key (see `compose-navigation` section 4) |

```kotlin
@Serializable data class RouteA(val id: String) : NavKey
@Serializable data object RouteB : NavKey
@Serializable data object RouteD : NavKey

val entryProvider = entryProvider {
    entry<RouteA> { key -> ScreenA(title = "Screen has ID: ${key.id}") }
    featureBSection()
    entry<RouteD>(metadata = DialogSceneStrategy.dialog()) { ScreenD() }
}

fun EntryProviderScope<NavKey>.featureBSection() {
    entry<RouteB> { ScreenB() }
}
```

The entry provider has no parent-child relationships. Hierarchy lives in `NavigationState` (top-level routes and their stacks); a route that is not top-level is pushed onto the current stack. Navigating from one stack into another needs explicit logic in `Navigator`.

## 6. Replace NavHost with NavDisplay

```kotlin
NavDisplay(
    entries = navigationState.toEntries(entryProvider),
    onBack = { navigator.goBack() },
    sceneStrategies = remember { listOf(DialogSceneStrategy()) },
)
```

Add `DialogSceneStrategy` only if there are dialog destinations, and append any other strategies (bottom sheet, list-detail).

## 7. Migrate deep links

Navigation 2 declared `deepLinks = listOf(navDeepLink { uriPattern = ... })` on destinations. Navigation 3 (1.2) keeps deep links out of the UI:

```kotlin
val userMatcher = UriDeepLinkMatcher(DeepLinkUri("www.example.com/user/{id}"), serializer<RouteA>())
```

In the activity's `onCreate` (and `onNewIntent`), build `DeepLinkRequest(intent = intent)`, run it through every matcher, take `maxOrNull()`, and seed the back stack from the result (`compose-navigation` section 9). Custom `NavType`s and `typeMap` become a `DeepLinkSerializer`. Keep the manifest intent filters.

## 8. Remove Navigation 2

Delete all `androidx.navigation:navigation-*` dependencies and imports (`NavHost`, `NavController`, `NavGraphBuilder`, `composable`, `navigation`, `toRoute`, `hiltNavGraphViewModels`), then build and run the navigation tests from step 0.

## Verify

- Every existing navigation test passes; add a test for each tab switch, Back from each tab's root, dialog dismissal and deep link entry.
- Rotate and trigger process death (`adb shell am kill` with the app in the background) on a nested destination of a non-start tab: the tab, its stack and screen state must be restored.
- Back from a non-start tab's root returns to the start route, and Back from the start route exits.
