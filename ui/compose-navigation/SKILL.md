---
name: compose-navigation
description: "Navigation 3 per Google's docs: NavKey back stacks, NavDisplay, entry decorators, Hilt ViewModel keys, scenes, transitions, results, deep links, modular features, Navigation 2 migration. Use for navigation, back stack or deep link work, or migrating from Navigation Compose, and when double taps push twice, entries share a ViewModel, state or back stack is lost, or Back skips deep link parents."
---

# Navigation 3

Sources of truth: [Navigation 3 guide](https://developer.android.com/guide/navigation/navigation-3) and its pages on [basics](https://developer.android.com/guide/navigation/navigation-3/basics), [saving state](https://developer.android.com/guide/navigation/navigation-3/save-state), [decorators](https://developer.android.com/guide/navigation/navigation-3/naventrydecorators), [scenes](https://developer.android.com/guide/navigation/navigation-3/scenes), [metadata](https://developer.android.com/guide/navigation/navigation-3/metadata), [animations](https://developer.android.com/guide/navigation/navigation-3/animate-destinations), [results](https://developer.android.com/guide/navigation/navigation-3/return-results), [deep links](https://developer.android.com/guide/navigation/navigation-3/deep-links), [modularization](https://developer.android.com/guide/navigation/navigation-3/modularize) and [migration](https://developer.android.com/guide/navigation/navigation-3/migration-guide); the [release notes](https://developer.android.com/jetpack/androidx/releases/navigation3); the official [nav3-recipes](https://github.com/android/nav3-recipes). Google strongly recommends a **single-activity app using Navigation 3**.

In Navigation 3 you own the back stack: it is an observable list of **keys**, and `NavDisplay` renders the entries for those keys. There is no `NavController`, no navigation graph and no route strings.

Core APIs are stable since **1.1**. `ResultEventBus` and the deep link matcher APIs arrive in **1.2**. Read the release notes before editing Gradle files to get current versions and to check whether 1.2 is stable yet; do not copy versions from samples.

## 1. Dependencies

| Artifact | Provides |
|---|---|
| `androidx.navigation3:navigation3-runtime` | `NavKey`, `NavBackStack`, `rememberNavBackStack`, `NavEntry`, `entryProvider`, `rememberSaveableStateHolderNavEntryDecorator`, metadata DSL; in 1.2 also results and deep links |
| `androidx.navigation3:navigation3-ui` | `NavDisplay`, `Scene`, `SceneStrategy`, `DialogSceneStrategy` |
| `androidx.lifecycle:lifecycle-viewmodel-navigation3` | `rememberViewModelStoreNavEntryDecorator` |
| `androidx.hilt:hilt-lifecycle-viewmodel-compose` | `hiltViewModel` (package `androidx.hilt.lifecycle.viewmodel.compose`) with `creationCallback` |
| `androidx.compose.material3.adaptive:adaptive-navigation3` | Material `ListDetailSceneStrategy`, `SupportingPaneSceneStrategy` |
| `org.jetbrains.kotlinx:kotlinx-serialization-core` + plugin `org.jetbrains.kotlin.plugin.serialization` | `@Serializable` keys |

Navigation 3 needs `compileSdk` 36 or higher.

## 2. Keys

A key is a reference to a destination, not the destination's data. The back stack is saved by serializing its keys, so a key must be a small, immutable, `@Serializable` value that implements `NavKey`.

- Put in the key exactly what identifies the screen (`articleId`), and let the destination's ViewModel load everything else from the data layer. Anything in a key is written to saved state on every configuration change and process death, and goes stale while the data layer moves on.
- Model argument-free destinations as `data object`, destinations with arguments as `data class`.
- A sealed parent interface keeps the back stack strongly typed (see the custom remember function in the saving state page).

```kotlin
@Serializable
data object Home : NavKey

@Serializable
data class ArticleDetail(val articleId: String) : NavKey
```

## 3. Back stack and NavDisplay

`rememberNavBackStack(vararg keys)` returns a `NavBackStack<NavKey>` that survives configuration changes and process death. `NavDisplay` needs the back stack, an `onBack` callback and an `entryProvider`.

```kotlin
@Composable
fun AppNavigation() {
    val backStack = rememberNavBackStack(Home)

    NavDisplay(
        backStack = backStack,
        onBack = { backStack.removeLastOrNull() },
        entryDecorators = listOf(
            rememberSaveableStateHolderNavEntryDecorator(),
            rememberViewModelStoreNavEntryDecorator(),
        ),
        entryProvider = entryProvider {
            entry<Home> {
                HomeRoute(onArticleClick = { id -> backStack.add(ArticleDetail(id)) })
            }
            entry<ArticleDetail> { key ->
                ArticleDetailRoute(key)
            }
        },
    )
}
```

Navigating is ordinary list mutation, so any `MutableList` operation is a valid navigation action. Pushing is `add`, popping is `removeLastOrNull`, and compound changes combine the two:

```kotlin
backStack.add(ArticleDetail(id))
backStack.removeLastOrNull()

backStack.removeIf { it is ArticleDetail }
backStack.add(ArticleDetail(newId))

backStack.retainAll { it == Home }
```

- Keep back stack mutations in one place (the `NavDisplay` owner or a navigator class, section 8). Route composables receive navigation as lambdas; screens never see the back stack.
- Wrap navigating click handlers in `dropUnlessResumed { }` so a double tap or a tap during a transition does not push twice. Entries are capped at `STARTED` during transitions and under overlays, which is what makes this work.
- Navigation caused by business logic follows `android-viewmodel`: the ViewModel exposes state, the route composable reacts by calling its navigation lambda.
- The `entryProvider` DSL throws for keys with no `entry`. Every key type that can reach the back stack needs one.

## 4. Decorators, lifecycle and ViewModels

Entry decorators add per-entry behavior. Order matters: put `rememberSaveableStateHolderNavEntryDecorator()` **first** so `rememberSaveable` works in every entry, then `rememberViewModelStoreNavEntryDecorator()` so each entry gets its own `ViewModelStore`, created on push and cleared on pop. Install both in every app that uses ViewModels. Write a custom `NavEntryDecorator` (with `decorate` and `onPop`) only for something every entry needs; pass single-entry dependencies directly instead.

Each entry gets its own `LifecycleOwner` through `LocalLifecycleOwner`. An entry is `RESUMED` only when it is on the back stack and its scene is settled with no overlay above it; it is capped at `STARTED` during transitions or under a dialog, and at `CREATED` while it animates out after being popped. Plain `collectAsStateWithLifecycle()` inside the entry is therefore correct.

Pass the key into the ViewModel with **Hilt assisted injection**. The ViewModel store decorator already keys the ViewModel to the entry, so no extra `key` argument is needed for multiple instances of the same destination.

```kotlin
@HiltViewModel(assistedFactory = ArticleDetailViewModel.Factory::class)
class ArticleDetailViewModel @AssistedInject constructor(
    @Assisted private val key: ArticleDetail,
    articlesRepository: ArticlesRepository,
) : ViewModel() {

    val uiState: StateFlow<ArticleDetailUiState> = articlesRepository
        .getArticleStream(key.articleId)
        .map(ArticleDetailUiState::Success)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ArticleDetailUiState.Loading)

    @AssistedFactory
    interface Factory {
        fun create(key: ArticleDetail): ArticleDetailViewModel
    }
}

@Composable
fun ArticleDetailRoute(key: ArticleDetail) {
    val viewModel = hiltViewModel<ArticleDetailViewModel, ArticleDetailViewModel.Factory>(
        creationCallback = { factory -> factory.create(key) },
    )
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    ArticleDetailScreen(uiState = uiState)
}
```

`SavedStateHandle.toRoute()` is a Navigation 2 API and does not apply here.

## 5. Scenes: dialogs and adaptive layouts

A `SceneStrategy` decides how the entries at the top of the back stack are arranged into a `Scene`. `NavDisplay(sceneStrategies = listOf(...))` asks each strategy in order and falls back to a single pane. Entries opt in through **metadata**.

Dialogs use the built-in strategy:

```kotlin
NavDisplay(
    backStack = backStack,
    onBack = { backStack.removeLastOrNull() },
    sceneStrategies = remember { listOf(DialogSceneStrategy()) },
    entryProvider = entryProvider {
        entry<ConfirmDelete>(metadata = DialogSceneStrategy.dialog()) { key ->
            ConfirmDeleteDialog(key)
        }
    },
)
```

Bottom sheets are not in the library; copy `BottomSheetSceneStrategy` from the bottom sheet recipe.

For list-detail on larger windows, use the Material adaptive strategy; on narrow windows it falls back to one pane:

```kotlin
@OptIn(ExperimentalMaterial3AdaptiveApi::class)
@Composable
fun ConversationsNavigation() {
    val backStack = rememberNavBackStack(ConversationList)
    val listDetailStrategy = rememberListDetailSceneStrategy<NavKey>()

    NavDisplay(
        backStack = backStack,
        onBack = { backStack.removeLastOrNull() },
        sceneStrategies = listOf(listDetailStrategy),
        entryDecorators = listOf(
            rememberSaveableStateHolderNavEntryDecorator(),
            rememberViewModelStoreNavEntryDecorator(),
        ),
        entryProvider = entryProvider {
            entry<ConversationList>(
                metadata = ListDetailSceneStrategy.listPane(
                    detailPlaceholder = { SelectConversationPlaceholder() },
                ),
            ) {
                ConversationListRoute(onConversationClick = { id -> backStack.add(ConversationDetail(id)) })
            }
            entry<ConversationDetail>(metadata = ListDetailSceneStrategy.detailPane()) { key ->
                ConversationDetailRoute(key)
            }
        },
    )
}
```

- `extraPane()` marks a third pane. Window size handling is in `compose-adaptive-layouts`.
- Custom `Scene` implementations must implement `equals`/`hashCode` over `key`, `entries` and `previousEntries` (a `data class` without callback properties does this). `previousEntries` drives predictive back.
- `SceneDecoratorStrategy` (passed as `sceneDecoratorStrategies`) wraps scenes in shared chrome such as an app bar or navigation rail. Overlay scenes are never decorated, and a decorating scene should derive its `key` from the wrapped scene's class and key so transitions still animate.

## 6. Transitions

- Set app-wide animations with `transitionSpec`, `popTransitionSpec` and `predictivePopTransitionSpec` on `NavDisplay`.
- Override per destination with the type-safe metadata DSL:

```kotlin
entry<Player>(
    metadata = metadata {
        put(NavDisplay.TransitionKey) { slideInVertically { it } togetherWith ExitTransition.KeepUntilTransitionsFinished }
        put(NavDisplay.PopTransitionKey) { EnterTransition.None togetherWith slideOutVertically { it } }
        put(NavDisplay.PredictivePopTransitionKey) { EnterTransition.None togetherWith slideOutVertically { it } }
    },
) { PlayerRoute() }
```

- When one entry moves between scenes (single pane to list-detail), wrap `NavDisplay` in `SharedTransitionLayout` and pass `sharedTransitionScope = this` to avoid jumpy transitions.

## 7. Returning results (1.2)

Add `rememberResultEventBusNavEntryDecorator()` to `entryDecorators`. Send from the entry, not from the screen composable, then navigate back; receive with `ResultEffect` (queued, for events such as forwarding to a ViewModel) or `LocalResultEventBus.current.conflateAsState(...)` (latest value only, for light UI state).

```kotlin
entry<ContactPicker> {
    val resultBus = LocalResultEventBus.current
    ContactPickerScreen(
        onContactSelected = { contact ->
            resultBus.sendResult(result = contact)
            backStack.removeLastOrNull()
        },
    )
}

@Composable
fun ComposeMessageRoute(viewModel: ComposeMessageViewModel = hiltViewModel()) {
    ResultEffect<Contact> { contact -> viewModel.onRecipientSelected(contact) }
    // ...
}
```

- Senders and receivers must both use the type-derived key or both use the same explicit `resultKey`. Use explicit keys for common types (`String`) or when two pickers return the same type.
- The bus is in memory: results do not survive process death. Results that must survive belong in a key, a `SavedStateHandle` of a scoped ViewModel, or `rememberSaveable`.

## 8. Modular features and navigator classes

Follow the modularization page:

- `:feature:<name>:api` holds only that feature's keys.
- `:feature:<name>:impl` holds screens, ViewModels and an **entry builder**: an `EntryProviderScope<NavKey>` extension that registers the feature's entries.
- A feature that opens another depends only on the other's `:api`, and navigates through an injected navigator rather than a raw back stack reference.
- The app module calls entry builders directly, or collects them with Hilt multibindings as the app grows (consistent with the stricter Hilt policy in `android-architecture`). Feature modules can contribute `DeepLinkMatcher`s the same way.

```kotlin
@ActivityRetainedScoped
class Navigator @Inject constructor() {
    val backStack: SnapshotStateList<NavKey> = mutableStateListOf(Home)

    fun navigate(key: NavKey) {
        backStack.add(key)
    }

    fun goBack() {
        backStack.removeLastOrNull()
    }
}

fun EntryProviderScope<NavKey>.articlesEntries(navigator: Navigator) {
    entry<ArticleList> { ArticleListRoute(onArticleClick = { navigator.navigate(ArticleDetail(it)) }) }
    entry<ArticleDetail> { key -> ArticleDetailRoute(key) }
}

@Module
@InstallIn(ActivityRetainedComponent::class)
object ArticlesNavigationModule {
    @IntoSet
    @Provides
    fun provideArticlesEntries(navigator: Navigator): EntryProviderScope<NavKey>.() -> Unit = {
        articlesEntries(navigator)
    }
}

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject
    lateinit var entryBuilders: Set<@JvmSuppressWildcards EntryProviderScope<NavKey>.() -> Unit>

    @Inject
    lateinit var navigator: Navigator

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            NavDisplay(
                backStack = navigator.backStack,
                onBack = { navigator.goBack() },
                entryDecorators = listOf(
                    rememberSaveableStateHolderNavEntryDecorator(),
                    rememberViewModelStoreNavEntryDecorator(),
                ),
                entryProvider = entryProvider { entryBuilders.forEach { builder -> builder() } },
            )
        }
    }
}
```

An activity-retained `Navigator` survives configuration changes but not process death. If the back stack must survive process death, keep `rememberNavBackStack` (or the `NavigationState` holder in [`migration.md`](migration.md)) in the app module and give the navigator that state, or save the serialized keys yourself.

**Bottom navigation with one back stack per tab** uses a state holder with a back stack per top-level key, decorated with `rememberDecoratedNavEntries` and passed to `NavDisplay(entries = ...)`. The migration guide's `NavigationState` and `Navigator` (reproduced in `migration.md`) and the multiple back stacks recipe are the reference implementation.

## 9. Deep links (1.2)

Deep links live outside the UI: match the incoming `Intent` to keys, then build the back stack.

```kotlin
val deepLinkMatchers: List<DeepLinkMatcher<*, *>> = listOf(
    UriDeepLinkMatcher(DeepLinkUri("www.example.com/articles/{articleId}"), serializer<ArticleDetail>())
        .withBackStack { match -> listOf(Home, match.key) },
)

fun initialBackStack(intent: Intent): List<NavKey> {
    val match = deepLinkMatchers.mapNotNull { it.match(DeepLinkRequest(intent = intent)) }.maxOrNull()
    @Suppress("UNCHECKED_CAST")
    return when (match) {
        null -> listOf(Home)
        is BackStackMatchResult<*, *> -> match.backStack as List<NavKey>
        else -> listOf(match.key as NavKey)
    }
}
```

- Declare URI patterns with placeholders that match the key's property names; let `UriDeepLinkMatcher` extract and convert arguments. Do not split paths or parse query strings manually.
- Use `withBackStack` to build a **synthetic back stack** so Back and Up lead to the destination's logical parents.
- `StaticKeyDeepLinkMatcher` is for argument-free requests matched by filters (`DeepLinkMatcher.actionFilter`, `mimeTypeFilter`), not for fixed URIs. Non-primitive arguments need a `DeepLinkSerializer`.
- Run the matching in `onCreate` to seed the back stack and again from `onNewIntent` (through `addOnNewIntentListener`) to replace it. Declare matching `<intent-filter>`s in the manifest.
- The synthetic back stack recipe shows correct Up behavior when another app's task opens the link.

## 10. Testing

- Back stack logic in a navigator class is plain state: test it on the JVM.
- Test route composables with fake navigation lambdas and assert they are called; deep link matchers are unit-testable with a `DeepLinkRequest(uri = ...)`.
- Add at least one UI navigation test per user flow (`android-testing`, `compose-testing`).

## 11. Migration from Navigation 2

Follow [`migration.md`](migration.md), which follows Google's step-by-step migration guide, including its prerequisites and stop conditions. Migrate in one atomic change; do not run `NavController` and `NavDisplay` side by side for the same flow.

## 12. Checklist

- [ ] Single activity; `NavDisplay` renders a back stack the app owns.
- [ ] Keys are `@Serializable` `NavKey`s holding identifiers only.
- [ ] Back stack comes from `rememberNavBackStack` or a state holder that saves it.
- [ ] Saveable state decorator first, then the ViewModel store decorator.
- [ ] ViewModels receive their key through assisted injection.
- [ ] Screens get navigation as lambdas; navigating clicks use `dropUnlessResumed`.
- [ ] Dialogs and panes are expressed with scene strategies and entry metadata.
- [ ] Deep links resolve through matchers into a synthetic back stack.
- [ ] Feature modules expose keys in `:api` and register entries from `:impl`.
