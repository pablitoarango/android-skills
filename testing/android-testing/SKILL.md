---
name: android-testing
description: "Android test strategy per Google's testing docs: test scopes, fakes over mocks, ViewModel and Flow tests, Hilt test bindings, Room DAO tests, Robolectric, Roborazzi and Compose Preview screenshot tests. Use when planning or writing unit, integration, Hilt, Room, or screenshot tests, or when a StateFlow test sees only its initial value or a local test throws Method not mocked."
---

# Android Testing

Sources of truth: [Testing strategies](https://developer.android.com/training/testing/fundamentals/strategies), [Test doubles](https://developer.android.com/training/testing/fundamentals/test-doubles), [Local tests](https://developer.android.com/training/testing/local-tests), [Robolectric strategies](https://developer.android.com/training/testing/local-tests/robolectric), [Screenshot testing](https://developer.android.com/training/testing/ui-tests/screenshot), [Compose Preview Screenshot Testing with test suites](https://developer.android.com/studio/preview/compose-screenshot-testing-with-testsuites), [Testing Kotlin flows](https://developer.android.com/kotlin/flow/test), [Testing coroutines](https://developer.android.com/kotlin/coroutines/test), [Hilt testing](https://developer.android.com/training/dependency-injection/hilt-testing), [Test your Room database](https://developer.android.com/training/data-storage/room/testing-db), the testing section of the [architecture recommendations](https://developer.android.com/topic/architecture/recommendations#testing), and the [Roborazzi README](https://github.com/takahirom/roborazzi).

Compose UI and component tests (test rules, semantics finders, synchronization, accessibility checks) are covered in `compose-testing`. MockWebServer tests for Retrofit data sources are covered in `android-retrofit`.

Read versions from [Robolectric releases](https://github.com/robolectric/robolectric/releases), [Roborazzi releases](https://github.com/takahirom/roborazzi/releases), [Dagger releases](https://github.com/google/dagger/releases), the [Room release notes](https://developer.android.com/jetpack/androidx/releases/room3) and the [Compose Preview Screenshot Testing release notes](https://developer.android.com/studio/preview/compose-screenshot-testing-release-notes).

## 1. What to test

Keep a pyramid: many small, fast JVM tests; fewer large tests. Pick the lowest scope that gives the feedback you need.

**Minimum for every feature:**
- Unit tests for **ViewModels**, including every `StateFlow` they expose.
- Unit tests for **repositories and data sources** (and use cases, when present).
- **UI navigation tests** that guard against regressions in screen-to-screen flows.

| Scope | Covers | Runs on | When |
|---|---|---|---|
| Unit | ViewModels, use cases, repositories, mappers, validators | Local JVM | Every commit |
| Component | A composable or screen in isolation, screenshots | JVM (Robolectric, Layoutlib) | Every commit |
| Feature | Several components together; network data sources vs MockWebServer; Room DAOs | JVM, emulator (Room: device, section 6) | Before merge |
| Application | Full app flows on a debuggable build, configuration changes | Emulator or device | After merge |
| Release candidate | Critical user journeys, performance, on a minified release build | Devices | Before release |

Debug-only tests do not cover R8 shrinking and obfuscation, so run critical journeys on a release candidate.

## 2. Test doubles: prefer fakes

- Use **fakes**: working, lightweight implementations of the production interface (in-memory lists, `MutableStateFlow`s). Name them `Fake<Interface>`.
- Prefer fakes for behavior tests. Use mocks when interaction verification is the purpose of the test or a suitable fake is impractical; keep assertions focused on meaningful behavior rather than implementation details.
- Put shared fakes in a test module (for example `:core:testing`) so every feature reuses the same ones.
- Before writing a fake for a library, check whether the library ships an official one.

```kotlin
class FakeNewsRepository : NewsRepository {
    private val articles = MutableStateFlow<List<Article>>(emptyList())
    var shouldFailRefresh = false

    fun sendArticles(value: List<Article>) {
        articles.value = value
    }

    override fun getNewsStream(): Flow<List<Article>> = articles

    override suspend fun refreshNews() {
        if (shouldFailRefresh) throw IOException("Refresh failed")
    }
}
```

Interfaces and constructor injection make fakes easy to substitute (`android-architecture`); they are design choices, not technical prerequisites for every fake. Framework-provided fakes and substitutable class implementations can also work.

Local tests run against a stub `android.jar` that throws `Method ... not mocked`. Move framework calls out of the class under test, or use Robolectric. Avoid `unitTests.isReturnDefaultValues = true`; Google calls it a last resort because null and zero defaults can hide failures.

## 3. Coroutine test setup

- Wrap tests in `runTest`.
- Replace `Dispatchers.Main` with `MainDispatcherRule` (defined in `android-coroutines`) in every class that tests a ViewModel.
- Inject `TestDispatcher`s that share the test's scheduler (`StandardTestDispatcher(testScheduler)`) wherever production code takes a dispatcher. A test has exactly one scheduler.

## 4. ViewModel and StateFlow tests

- **Prefer assertions on `uiState.value`.** Collect emissions only when transitions are the behavior under test, controlling producer/collector scheduling and accounting for `StateFlow` conflation; rapid intermediate values are not guaranteed to reach a collector.
- A `StateFlow` built with `stateIn(..., WhileSubscribed(...), ...)` produces nothing until something collects it. Start an empty collector in `backgroundScope` with `UnconfinedTestDispatcher`.

```kotlin
class ForYouViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private val newsRepository = FakeNewsRepository()
    private lateinit var viewModel: ForYouViewModel

    @Before
    fun setup() {
        viewModel = ForYouViewModel(newsRepository)
    }

    @Test
    fun uiState_whenArticlesArrive_isSuccess() = runTest {
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { viewModel.uiState.collect() }

        assertEquals(ForYouUiState.Loading, viewModel.uiState.value)

        newsRepository.sendArticles(sampleArticles)

        assertEquals(ForYouUiState.Success(sampleArticles), viewModel.uiState.value)
    }
}
```

Transient messages live in a data class UI state (`NewsUiState(userMessage = ...)`) and are cleared by a "shown" callback:

```kotlin
class NewsViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private val newsRepository = FakeNewsRepository()

    @Test
    fun refresh_whenNetworkFails_showsMessageUntilShown() = runTest {
        val viewModel = NewsViewModel(newsRepository)
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { viewModel.uiState.collect() }
        newsRepository.shouldFailRefresh = true

        viewModel.refreshNews()
        assertEquals(UserMessage.RefreshFailed, viewModel.uiState.value.userMessage)

        viewModel.userMessageShown()
        assertNull(viewModel.uiState.value.userMessage)
    }
}
```

UI messages and navigation triggers are part of UI state (`android-viewmodel`), so they are tested with the same `value` assertions.

## 5. Flow tests (repositories, use cases)

- Finite flows: `first()`, `toList()`, `take(n).toList()`, `single()`, `count()`.
- Infinite flows: collect continuously in `backgroundScope`, then interleave emissions and assertions.

```kotlin
@Test
fun scores_multipliesEachCount() = runTest {
    val dataSource = FakeCountsDataSource()
    val repository = ScoresRepository(dataSource)

    val values = mutableListOf<Int>()
    backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
        repository.getScoresStream().toList(values)
    }

    dataSource.emit(1)
    assertEquals(10, values[0])
}
```

- [Turbine](https://github.com/cashapp/turbine) (`flow.test { awaitItem() }`) is an acceptable alternative, including for `StateFlow` when the test accounts for conflation and deliberately checks transitions.

## 6. Room DAO tests

Google recommends testing the database with JUnit tests **on a device** (`src/androidTest`); they need no activity, so they run faster than UI tests. Google does **not** recommend Robolectric for Room. Host JVM tests are supported only through a Room KMP JVM target.

- Build a fresh **in-memory** database per test and close it after. Nothing persists between tests, so they stay hermetic and order-independent.
- Build the database directly; Hilt is not needed to test a DAO. Injecting the app's database module would hand the test the production on-disk database.
- Use the same `SQLiteDriver` as production (Google's samples use `BundledSQLiteDriver` from `androidx.sqlite:sqlite-bundled`) so SQL behaves identically.
- Repositories and ViewModels do not need a database: give them a fake DAO or fake data source.
- Test schema migrations separately with `MigrationTestHelper` from the Room testing artifact ([Test migrations](https://developer.android.com/training/data-storage/room/migrating-db-versions#test)).

```kotlin
@RunWith(AndroidJUnit4::class)
class BookmarkDaoTest {

    private lateinit var database: LibraryDatabase
    private lateinit var bookmarkDao: BookmarkDao

    @Before
    fun openDatabase() {
        database = Room.inMemoryDatabaseBuilder<LibraryDatabase>(ApplicationProvider.getApplicationContext())
            .setDriver(BundledSQLiteDriver())
            .build()
        bookmarkDao = database.bookmarkDao()
    }

    @After
    fun closeDatabase() {
        database.close()
    }

    @Test
    fun observeBookmarks_ordersBySavedTimeDescending() = runTest {
        bookmarkDao.upsert(BookmarkEntity(id = 7, title = "Older", savedAtMillis = 1_000))
        bookmarkDao.upsert(BookmarkEntity(id = 9, title = "Newer", savedAtMillis = 2_000))

        val titles = bookmarkDao.observeBookmarks().first().map { it.title }

        assertEquals(listOf("Newer", "Older"), titles)
    }

    @Test
    fun upsert_sameId_replacesRow() = runTest {
        bookmarkDao.upsert(BookmarkEntity(id = 7, title = "Draft", savedAtMillis = 1_000))
        bookmarkDao.upsert(BookmarkEntity(id = 7, title = "Final", savedAtMillis = 1_000))

        assertEquals(listOf("Final"), bookmarkDao.observeBookmarks().first().map { it.title })
    }
}
```

## 7. Hilt in tests

**Unit tests do not use Hilt.** Call the constructor with fakes, including for ViewModels that production obtains with `hiltViewModel()`. Use Hilt in larger Robolectric or instrumented tests, where the test does not create the objects under test and must swap bindings in the real graph.

Setup:
- Dependencies: `com.google.dagger:hilt-android-testing`, plus `hilt-android-compiler` on `kspTest` (Robolectric) or `kspAndroidTest` (instrumented). Add the processors of any other Hilt Jetpack integration the code under test uses.
- Application: instrumented tests use a custom `AndroidJUnitRunner` whose `newApplication` passes `HiltTestApplication::class.java.name`, set as `testInstrumentationRunner`. Robolectric tests set `application = dagger.hilt.android.testing.HiltTestApplication` in `robolectric.properties` or `@Config(application = HiltTestApplication::class)`.
- If the app needs a custom base `Application`, use `@CustomTestApplication(BaseApplication::class)`.
- Compose tests host content in an empty `@AndroidEntryPoint` activity (`HiltTestActivity`) in the `androidTest` source set.

Replacing bindings, in order of preference:

| Tool | Scope | Notes |
|---|---|---|
| `@TestInstallIn(components = [...], replaces = [ProdModule::class])` | Every test in the source set | Preferred; no per-class component generation |
| `@UninstallModules(ProdModule::class)` + nested `@InstallIn` module | One test class | Generates a component per class; slows builds |
| `@BindValue @JvmField val x: Type = Fake()` | One test class | Binds a field directly; `@BindValueIntoSet` / `@BindValueIntoMap` for multibindings |

`@UninstallModules` removes only `@InstallIn` modules, never `@TestInstallIn` ones.

```kotlin
@Module
@TestInstallIn(components = [SingletonComponent::class], replaces = [OrdersDataModule::class])
interface FakeOrdersDataModule {
    @Binds
    fun bindOrdersRepository(fake: FakeOrdersRepository): OrdersRepository
}

@Singleton
class FakeOrdersRepository @Inject constructor() : OrdersRepository {
    private val orders = MutableStateFlow<List<Order>>(emptyList())
    fun setOrders(value: List<Order>) { orders.value = value }
    override fun observeOrders(): Flow<List<Order>> = orders
}

@HiltAndroidTest
class OrderHistoryScreenTest {

    @get:Rule(order = 0)
    val hiltRule = HiltAndroidRule(this)

    @get:Rule(order = 1)
    val composeRule = createAndroidComposeRule<HiltTestActivity>()

    @Inject
    lateinit var ordersRepository: FakeOrdersRepository

    @Before
    fun injectFakes() {
        hiltRule.inject()
    }

    @Test
    fun orderHistory_listsOrdersFromRepository() {
        ordersRepository.setOrders(listOf(Order(id = "A-17", title = "Running shoes")))

        composeRule.setContent { OrderHistoryRoute() }

        composeRule.onNodeWithText("Running shoes").assertIsDisplayed()
    }
}
```

- `HiltAndroidRule` must run before every other rule: give it `order = 0` or make it the outer rule of a `RuleChain`.
- Call `hiltRule.inject()` before using `@Inject` fields.
- Because the screen gets its ViewModel from Hilt, replacing the repository binding is enough; the composable picks up the fake.

## 8. Screenshot tests

Google recommends screenshot tests for verifying the visual attributes of Compose UI. A screenshot test renders UI, compares it with an approved reference image, and on a difference produces a report you either fix or approve as the new reference.

- Screenshot stateless screen or component composables with fixed `UiState` values, never a composable that creates a ViewModel.
- Capture only combinations that give distinct feedback. A button's long-label behavior does not depend on theme, so test long labels in one theme only.
- Commit reference images, keep their count low, and move to Git LFS or a service only if the repository suffers.
- Rendering differs across macOS, Linux and Windows. Record references on CI (or one fixed environment), or configure a small comparison tolerance.

### Choosing a tool

| | Compose Preview Screenshot Testing | Roborazzi |
|---|---|---|
| Owner | Google (Android Gradle Plugin), experimental alpha | Third party, on Robolectric |
| Renderer | Layoutlib, like Android Studio previews | Robolectric Native Graphics |
| Tests are | `@PreviewTest` `@Preview` functions in a screenshot source set | JUnit tests calling `captureRoboImage()` in `src/test` |
| Good for | Static component and screen states, `@Preview` parameters (`uiMode`, `fontScale`), multi-previews | Views and Compose, interactions before capture (clicks, scrolling, dialogs), Activities, Robolectric qualifiers |
| Limits | Android-only; not for non-Android KMP targets; no interaction | Lower fidelity than a device; needs Robolectric setup |

- Default to Compose Preview Screenshot Testing for static Compose states when the project's AGP supports it.
- Choose Roborazzi when a capture needs interaction or Views, when the project already runs Robolectric UI tests, or when AGP cannot be upgraded.
- Use device tests for pixel-critical output and system UI (edge-to-edge, picture-in-picture) or features Robolectric lacks, such as `WebView`.

### Compose Preview Screenshot Testing

From AGP 9.5.0-alpha03 with screenshot engine 0.0.1-alpha16, configure it as an AGP test suite. The standalone `com.android.compose.screenshot` plugin is deprecated.

`gradle.properties`:

```properties
android.experimental.enableScreenshotTest=true
android.experimental.testSuiteSupport=true
```

Module `build.gradle.kts`:

```kotlin
android {
    testOptions {
        screenshotTests.create("screenshotTest") {
            engineVersion = libs.versions.composeScreenshot.get()
            targetVariants.add("debug")
            dependencies {
                implementation(libs.androidx.compose.ui.tooling)
                implementation(libs.screenshot.validation.api)
            }
        }
    }
}
```

`src/screenshotTest/kotlin/.../CartSummaryScreenshots.kt`:

```kotlin
@PreviewTest
@PreviewLightDark
@Composable
fun CartSummaryWithPromoPreview() {
    ShopTheme {
        CartSummary(state = CartUiState(itemCount = 3, totalLabel = "$42.00", promoApplied = true))
    }
}
```

| Task | Effect |
|---|---|
| `./gradlew update<Suite><Target><Variant>TestSuite` (for example `updateScreenshotTestDefaultDebugTestSuite`) | Renders previews and writes references to `src/<suite><Target><Variant>/reference/` |
| `./gradlew test<Suite><Target><Variant>TestSuite` | Renders again and compares; report in `build/reports/tests/<taskName>/index.html` |

- Projects still on the deprecated plugin use `updateDebugScreenshotTest` and `validateDebugScreenshotTest`; migrate them to test suites.
- Renaming a `@PreviewTest` function orphans its reference images; regenerate them.
- If the test JVM runs out of memory, raise `android.compose.screenshot.maxHeapSize` in `gradle.properties`.

### Roborazzi

Setup:
- Robolectric, following Robolectric's getting-started page: `org.robolectric:robolectric` and `testOptions.unitTests.isIncludeAndroidResources = true`.
- The `io.github.takahirom.roborazzi` Gradle plugin, plus `io.github.takahirom.roborazzi:roborazzi` and `roborazzi-compose` (and `roborazzi-junit-rule` for `RoborazziRule`) on `testImplementation`.
- The Compose test rule artifacts from `compose-testing`.
- Reference images default to `build/outputs/roborazzi`, which `clean` deletes. Set `roborazzi { outputDir.set(file("src/test/screenshots")) }` and commit that directory.

```kotlin
@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class CartSummaryScreenshotTest {

    @get:Rule
    val composeRule = createComposeRule()

    private val filledCart = CartUiState(itemCount = 3, totalLabel = "$42.00", promoApplied = true)

    @Test
    fun cartSummary_filled() {
        composeRule.setContent { ShopTheme { CartSummary(state = filledCart) } }
        composeRule.onNodeWithTag("cartSummary").captureRoboImage()
    }

    @Test
    @Config(qualifiers = "+night")
    fun cartSummary_filled_dark() {
        composeRule.setContent { ShopTheme { CartSummary(state = filledCart) } }
        composeRule.onNodeWithTag("cartSummary").captureRoboImage()
    }

    @Test
    fun cartSummary_afterRemovingPromo() {
        composeRule.setContent { ShopTheme { CartSummaryRoute(initialState = filledCart) } }
        composeRule.onNodeWithText("Remove promo").performClick()
        composeRule.onRoot().captureRoboImage()
    }
}
```

- Roborazzi needs Robolectric Native Graphics, so every screenshot class carries `@GraphicsMode(GraphicsMode.Mode.NATIVE)`.
- Without a file name, `captureRoboImage()` names the image after the test class and method.
- Change the device with `@Config(qualifiers = ...)` on a class or method: `RobolectricDeviceQualifiers.MediumTablet` and other presets, `"+night"`, or a locale such as `"+ar"`.
- `captureScreenRoboImage()` (experimental) includes dialogs and other windows.

| Task | Effect |
|---|---|
| `./gradlew recordRoborazziDebug` | Writes new reference images |
| `./gradlew compareRoborazziDebug` | Writes `*_compare.png` diff images without failing |
| `./gradlew verifyRoborazziDebug` | Fails the build when an image differs |
| `./gradlew verifyAndRecordRoborazziDebug` | Verifies, then records the new baseline where images differ |

Each task also works as `./gradlew testDebugUnitTest -Proborazzi.test.<record|compare|verify>=true`. Reports are in `build/reports/roborazzi/index.html`.

## 9. Running tests

| Command | Runs |
|---|---|
| `./gradlew testDebugUnitTest` | Local JVM and Robolectric tests in `src/test` for one variant (`test` runs every variant) |
| `./gradlew connectedDebugAndroidTest` | Instrumented tests in `src/androidTest`, including Room DAO and Hilt device tests, on connected devices |
| `./gradlew :module:testDebugUnitTest --tests "*BookmarkDaoTest"` | One class; filters also apply to `connected...AndroidTest` via `-Pandroid.testInstrumentationRunnerArguments.class=...` |

Screenshot tasks are listed in section 8. For emulators and Gradle Managed Devices see `android-emulator`.

## 10. Checklist

- [ ] Every ViewModel, repository and data source has unit tests; navigation flows have UI tests.
- [ ] Fakes are preferred; mocks verify meaningful interactions when appropriate.
- [ ] ViewModel tests use `MainDispatcherRule` and assert on `StateFlow.value`; `WhileSubscribed` flows have a `backgroundScope` collector.
- [ ] One test scheduler per test.
- [ ] DAO tests run on a device (or a Room KMP JVM target) against a fresh in-memory database closed after each test, without Hilt or Robolectric.
- [ ] Unit tests construct classes directly; Hilt tests replace bindings with `@TestInstallIn` first and run `HiltAndroidRule` before other rules.
- [ ] Screenshot tests render stateless UI from fixed state, avoid redundant combinations, and have committed references recorded in one environment.
- [ ] Critical journeys run on a minified release candidate before release.
