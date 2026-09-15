---
name: android-domain-layer
description: "Use cases per Google's domain layer guide: when to add one, naming, operator invoke, main-safety, lifetime, testing. Use when creating, reviewing, or deciding whether to add a use case, and when business logic is duplicated across ViewModels or one ViewModel combines too many repositories."
---

# Android Domain Layer

Sources of truth: [Domain layer](https://developer.android.com/topic/architecture/domain-layer). Rules marked **(stricter than Google)** are deliberate choices.

## 1. Decide whether a use case is needed

The domain layer is **optional**. Add a use case only when at least one is true:

- The same business logic is needed by **more than one ViewModel**.
- The logic makes a ViewModel **hard to read or test** (combining several repositories, multi-step rules).

Otherwise the ViewModel calls the repository directly. A use case that only forwards one repository call adds a class without adding value.

Complex computations that benefit from caching usually belong in the **data layer**, not in a use case.

## 2. Shape of a use case

- One use case, one responsibility.
- Name: **verb in present tense + noun + `UseCase`**: `FormatDateUseCase`, `LogOutUserUseCase`, `GetLatestNewsWithAuthorsUseCase`.
- Expose `operator fun invoke` so callers use it like a function; overloads may support different inputs to the same responsibility.
- Suspending one-shot work uses `suspend operator fun invoke(...)`; synchronous work can use a regular `invoke`, and observable results return `Flow`.
- **Main-safe**: if the use case does blocking or CPU-heavy work, it moves that work to an **injected** dispatcher.
- **No mutable state.** Keep mutable data in the UI or data layer.
- **(Stricter than Google)** Pure Kotlin: no `android.*` imports.

```kotlin
class GetLatestNewsWithAuthorsUseCase @Inject constructor(
    private val newsRepository: NewsRepository,
    private val authorsRepository: AuthorsRepository,
    @Dispatcher(Default) private val defaultDispatcher: CoroutineDispatcher,
) {
    suspend operator fun invoke(): List<ArticleWithAuthor> = withContext(defaultDispatcher) {
        val news = newsRepository.fetchLatestNews()
        news.map { article ->
            ArticleWithAuthor(article, authorsRepository.getAuthor(article.authorId))
        }
    }
}
```

Combining streams:

```kotlin
class GetFollowableTopicsUseCase @Inject constructor(
    private val topicsRepository: TopicsRepository,
    private val userDataRepository: UserDataRepository,
) {
    operator fun invoke(): Flow<List<FollowableTopic>> = combine(
        userDataRepository.getUserDataStream(),
        topicsRepository.getTopicsStream(),
    ) { userData, topics ->
        topics.map { FollowableTopic(it, isFollowed = it.id in userData.followedTopics) }
    }
}
```

Calling it:

```kotlin
@HiltViewModel
class ForYouViewModel @Inject constructor(
    getFollowableTopics: GetFollowableTopicsUseCase,
) : ViewModel() {
    val uiState: StateFlow<ForYouUiState> = getFollowableTopics()
        .map(ForYouUiState::Success)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ForYouUiState.Loading)
}
```

## 3. Dependencies

- A use case may depend on **repositories** and on **other use cases**.
- The data layer never depends on the domain layer; repository interfaces belong to the data layer.
- Nothing in the domain layer depends on the UI layer.

## 4. Lifetime and injection

- Use cases have no lifecycle of their own; they live as long as the class that uses them.
- **Do not scope** use cases in Hilt (no `@Singleton`, `@ViewModelScoped`). A new instance per consumer is expected.

## 5. Restricting data layer access

Google describes two options:

- **Flexible (default)**: ViewModels may call repositories directly and use cases only where section 1 applies.
- **Strict**: all data access goes through use cases. Adopt it for a feature only when it already calls use cases almost exclusively, or when a cross-cutting concern (for example analytics on every access) needs one choke point.

## 6. Testing

- Unit test use cases on the JVM, preferring **fake repositories** (`FakeNewsRepository`); choose other test doubles when the behavior under test requires them.
- Inject a `TestDispatcher` for the dispatcher parameter and run tests with `runTest`.
- See `android-testing`.

## 7. Checklist

- [ ] The use case is shared by several ViewModels or removes real complexity.
- [ ] Named verb + noun + `UseCase`, exposes `operator fun invoke` for one responsibility.
- [ ] Main-safe; dispatchers are injected.
- [ ] Holds no mutable state and is not scoped.
- [ ] Depends only on repositories and other use cases; no `android.*` imports.
