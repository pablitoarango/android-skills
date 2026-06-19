---
name: android-viewmodel
description: "ViewModels and UI state per Google's UI layer guide: StateFlow with stateIn, events modeled as state, lifecycle-aware collection. Use for ViewModels, UI state classes, snackbars, navigation triggers, or one-off events."
---

# Android ViewModel and UI State

Sources of truth: [UI layer](https://developer.android.com/topic/architecture/ui-layer), [State production](https://developer.android.com/topic/architecture/ui-layer/state-production), [UI events](https://developer.android.com/topic/architecture/ui-layer/events), [State holders](https://developer.android.com/topic/architecture/ui-layer/stateholders).

The core idea: **state is; events happen.** The ViewModel turns inputs (repository data, user actions) into one observable UI state. Everything the UI needs to render, including messages and navigation triggers, is part of that state.

## 1. Role and boundaries

- A ViewModel is the **business logic state holder for one screen** (a navigation destination). Use it only in screen-level composables.
- Reusable components use plain state holder classes (`compose-ui`), never a ViewModel.
- ViewModels hold **no** `Context`, `Activity`, `Resources`, `View`, or lifecycle types. Extend `ViewModel`, never `AndroidViewModel`.
- Business logic is delegated to repositories, or to use cases when reused or complex.
- The screen composable reads state and passes plain values and lambdas down. **Never pass the ViewModel to child composables.**

## 2. UI state

- Name it `<Functionality>UiState`.
- Make it immutable: a `data class` with `val`s, or a `sealed interface` for mutually exclusive states. A read-only `List` can still have a mutable alias: publish owned snapshots or persistent immutable collections, and keep their elements immutable too.
- Expose **one** `uiState: StateFlow<...>` per screen. Use a second stream only for data that is truly unrelated and changes independently.
- Derive values instead of storing duplicates:

```kotlin
data class NewsUiState(
    val isSignedIn: Boolean = false,
    val isPremium: Boolean = false,
    val newsItems: List<NewsItemUiState> = emptyList(),
    val userMessage: UserMessage? = null,
)

val NewsUiState.canBookmarkNews: Boolean get() = isSignedIn && isPremium
```

Loading, content and error when they are mutually exclusive:

```kotlin
sealed interface AuthorUiState {
    data object Loading : AuthorUiState
    data class Success(val author: Author) : AuthorUiState
    data object Error : AuthorUiState
}
```

Expose `PagingData` as its own `Flow`, not inside the immutable UI state.

## 3. Producing state

Pick the pattern by input type.

### Stream inputs (default): transform and `stateIn`

```kotlin
@HiltViewModel
class InterestsViewModel @Inject constructor(
    authorsRepository: AuthorsRepository,
    topicsRepository: TopicsRepository,
) : ViewModel() {

    private val interests: Flow<InterestsUiState> = combine(
        authorsRepository.getAuthorsStream(),
        topicsRepository.getTopicsStream(),
    ) { authors, topics ->
        InterestsUiState.Interests(authors = authors, topics = topics)
    }

    val uiState: StateFlow<InterestsUiState> = interests
        .catch { emit(InterestsUiState.Error) }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = InterestsUiState.Loading,
        )
}
```

- `WhileSubscribed(5_000)` stops upstream work 5 seconds after the UI stops collecting, and survives configuration changes. Use `SharingStarted.Lazily` only when the pipeline must keep running while the screen is off-screen (for example a tab kept in memory).

### One-shot inputs only: private `MutableStateFlow`

```kotlin
@HiltViewModel
class AddEditTaskViewModel @Inject constructor(
    private val tasksRepository: TasksRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(AddEditTaskUiState())
    val uiState: StateFlow<AddEditTaskUiState> = _uiState.asStateFlow()

    fun updateTitle(newTitle: String) {
        _uiState.update { it.copy(title = newTitle) }
    }

    fun saveTask() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true) }
            try {
                tasksRepository.saveTask(Task(uiState.value.title, uiState.value.description))
                _uiState.update { it.copy(isLoading = false, isTaskSaved = true) }
            } catch (e: IOException) {
                _uiState.update { it.copy(isLoading = false, userMessage = UserMessage.SaveFailed) }
            }
        }
    }
}
```

- Always change state with `update { }`, which is atomic. Do not write `_uiState.value = _uiState.value.copy(...)`.
- Never expose the `MutableStateFlow`.

### Mixed inputs: turn one-shot results into a stream, then `combine`

```kotlin
@HiltViewModel
class TaskDetailViewModel @Inject constructor(
    private val tasksRepository: TasksRepository,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val taskId: String = checkNotNull(savedStateHandle["taskId"])
    private val isTaskDeleted = MutableStateFlow(false)

    val uiState: StateFlow<TaskDetailUiState> = combine(
        tasksRepository.getTaskStream(taskId),
        isTaskDeleted,
    ) { task, deleted ->
        TaskDetailUiState(task = task, isTaskDeleted = deleted)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), TaskDetailUiState())

    fun deleteTask() {
        viewModelScope.launch {
            tasksRepository.deleteTask(taskId)
            isTaskDeleted.value = true
        }
    }
}
```

With Navigation 3, the ViewModel receives its navigation key through assisted injection instead of `SavedStateHandle` (see `compose-navigation`).

### Starting work

- **Do not launch coroutines in `init {}`.** Prefer `stateIn`, which starts lazily when the UI subscribes.
- When a one-time load cannot be a stream, expose an idempotent `@MainThread fun initialize()` guarded by a flag and call it from a `LaunchedEffect(Unit)`.
- Work that must finish even if the user leaves, or takes longer than a few seconds, belongs in the data layer (external scope) or WorkManager, not `viewModelScope`.

## 4. Events

### Decide where an event is handled

| Event | Handled by | How |
|---|---|---|
| UI element behavior only (expand, scroll, open a menu) | UI | `remember` / `rememberSaveable` state, or a UI state holder |
| User action that needs business logic (refresh, save, follow) | ViewModel | Call a ViewModel function; it updates UI state |
| Result produced in the ViewModel (error, success, "go to next screen") | ViewModel → UI | **Update UI state.** The UI reacts to state. |

ViewModel functions are verb phrases (`refreshNews()`, `tryLogin()`); composable lambdas are `on` + verb (`onRefreshClick`, `onLoginAttempt`).

### The ViewModel never sends events to the UI

Do not use `SharedFlow`, `Channel`, or event wrappers to push navigation, snackbars, toasts or dialogs from a ViewModel. The ViewModel outlives the UI, so events emitted while no one collects are lost or processed twice. Model the outcome as state instead: state is kept across configuration changes, is always delivered, and is easy to test.

### Transient messages (snackbar, toast)

State holds the message; the UI shows it and then tells the ViewModel it was consumed.

```kotlin
class LatestNewsViewModel(...) : ViewModel() {
    private val _uiState = MutableStateFlow(LatestNewsUiState())
    val uiState: StateFlow<LatestNewsUiState> = _uiState.asStateFlow()

    fun refreshNews() {
        viewModelScope.launch {
            if (!connectivity.isOnline()) {
                _uiState.update { it.copy(userMessage = UserMessage.NoInternet) }
                return@launch
            }
        }
    }

    fun userMessageShown() {
        _uiState.update { it.copy(userMessage = null) }
    }
}

@Composable
fun LatestNewsScreen(
    snackbarHostState: SnackbarHostState,
    viewModel: LatestNewsViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    uiState.userMessage?.let { message ->
        val text = stringResource(message.textRes)
        LaunchedEffect(message) {
            snackbarHostState.showSnackbar(text)
            viewModel.userMessageShown()
        }
    }
}
```

If several messages can queue, hold `userMessages: List<UserMessage>` and remove by id in `userMessageShown(id)`.

### Navigation after business logic

State carries the outcome; the UI navigates through a callback it received from the navigation layer.

```kotlin
data class LoginUiState(
    val isLoginInProgress: Boolean = false,
    val errorMessage: UserMessage? = null,
    val isUserLoggedIn: Boolean = false,
)

@Composable
fun LoginRoute(
    onUserLoggedIn: () -> Unit,
    viewModel: LoginViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val currentOnUserLoggedIn by rememberUpdatedState(onUserLoggedIn)

    LaunchedEffect(uiState.isUserLoggedIn) {
        if (uiState.isUserLoggedIn) currentOnUserLoggedIn()
    }

    LoginScreen(uiState = uiState, onLoginAttempt = viewModel::tryLogin)
}
```

Navigation that needs no business logic (a "Help" button) calls the navigation lambda directly, wrapped in `dropUnlessResumed { }`.

When a screen stays on the back stack and must not navigate again on return (multi-step flows), keep a UI-side `rememberSaveable` flag such as `validationInProgress` that is set when the user acts and cleared when navigation happens, and navigate only while it is `true`.

If several screens need the same result, hoist the state to a shared, higher-scoped state holder rather than broadcasting an event.

## 5. Collecting state

- Compose: `val uiState by viewModel.uiState.collectAsStateWithLifecycle()`.
- Views: collect inside `repeatOnLifecycle(Lifecycle.State.STARTED)`.

```kotlin
viewLifecycleOwner.lifecycleScope.launch {
    viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.uiState.collect(::render)
    }
}
```

## 6. Coroutines in ViewModels

- Prefer launching business work in `viewModelScope` and exposing results as state. A public `suspend` function can serve a single-value result when caller-owned cancellation is appropriate; see `android-coroutines`.
- Catch expected exceptions inside the launched coroutine and turn them into UI state. Catch specific types; if you catch broadly, rethrow `CancellationException` (see `android-coroutines`).
- The ViewModel itself stays main-safe because repositories and use cases are main-safe.

## 7. Checklist

- [ ] Screen-level only; no `Context`/`Resources`/`AndroidViewModel`; never passed to child composables.
- [ ] One immutable `<Functionality>UiState` exposed as `StateFlow`.
- [ ] Streams use `stateIn(viewModelScope, WhileSubscribed(5_000), initial)`.
- [ ] Mutable state is private and changed with `update { }`.
- [ ] No work launched from `init {}`.
- [ ] No `SharedFlow`/`Channel` events to the UI; messages and navigation outcomes are state, cleared by a "shown" callback.
- [ ] UI collects with `collectAsStateWithLifecycle()` or `repeatOnLifecycle`.
- [ ] Tests assert on `uiState.value` (see `android-testing`).
