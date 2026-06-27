---
name: compose-testing
description: "Compose UI tests per Google's docs: test rules, semantics finders, merged trees, synchronization, state restoration, configuration overrides, accessibility checks. Use when writing or debugging Compose UI or component tests."
---

# Compose UI Testing

Sources of truth: [Test your Compose layout](https://developer.android.com/develop/ui/compose/testing), [Testing APIs](https://developer.android.com/develop/ui/compose/testing/apis), [Synchronization](https://developer.android.com/develop/ui/compose/testing/synchronization), [Common patterns](https://developer.android.com/develop/ui/compose/testing/common-patterns), [Accessibility testing](https://developer.android.com/develop/ui/compose/accessibility/testing).

If the project defines its own UI test conventions (for example page objects or a mocked HTTP layer for instrumented tests), follow those for that kind of test. For overall test strategy, ViewModel tests and screenshot tests, see `android-testing`.

## 1. Setup

```kotlin
androidTestImplementation("androidx.compose.ui:ui-test-junit4")
androidTestImplementation("androidx.compose.ui:ui-test-junit4-accessibility")
debugImplementation("androidx.compose.ui:ui-test-manifest")
testImplementation("androidx.compose.ui:ui-test-junit4")
testImplementation("org.robolectric:robolectric")
```

- The same test code runs as a local test with Robolectric or as an instrumented test.
- `createComposeRule()`: test composables in isolation; no Activity access needed.
- `createAndroidComposeRule<ComponentActivity>()`: when you also need Activity resources (`composeTestRule.activity.getString(...)`). Use `createAndroidComposeRule<YourActivity>()` for a real screen, including mixed View and Compose screens.

## 2. Test stateless composables in isolation

Test the stateless screen composable with fixed UI state and fake callbacks, not a composable that creates a ViewModel.

```kotlin
class ArticleScreenTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun bookmarkButton_whenClicked_reportsArticleId() {
        var bookmarkedId: String? = null
        composeTestRule.setContent {
            AppTheme {
                ArticleScreen(
                    uiState = ArticleUiState.Success(sampleArticle),
                    onBookmarkClick = { bookmarkedId = it },
                )
            }
        }

        val bookmarkLabel = composeTestRule.activity.getString(R.string.bookmark)
        composeTestRule.onNodeWithContentDescription(bookmarkLabel).performClick()

        assertEquals(sampleArticle.id, bookmarkedId)
    }
}
```

## 3. Finding nodes

Compose tests query the **semantics tree**, not views.

- Prefer what users perceive: `onNodeWithText`, `onNodeWithContentDescription`, and role/state matchers. Load strings from resources rather than hardcoding them.
- Use `Modifier.testTag("...")` + `onNodeWithTag` when no user-visible property identifies the node uniquely.
- Combine matchers: `onNode(hasText("Save") and hasClickAction())`.
- Hierarchy: `hasParent`, `hasAnyAncestor`, `hasAnySibling`, `hasAnyDescendant`.
- Multiple nodes: `onAllNodes(matcher)`, `onAllNodesWithTag(...)`, then `.onFirst()`, `.filter(...)`, `.assertCountEquals(n)`, `.assertAll(...)`, `.assertAny(...)`.

### Merged vs unmerged tree

Clickable elements and `mergeDescendants` merge their children into one node, so by default a finder sees the merged node. To reach a child inside it, pass `useUnmergedTree = true`.

```kotlin
composeTestRule.onNodeWithText("World", useUnmergedTree = true).assertIsDisplayed()
```

Debug with `composeTestRule.onRoot().printToLog("TAG")` (add `useUnmergedTree = true` to see children).

## 4. Assertions and actions

- Assertions: `assertIsDisplayed()`, `assertExists()`, `assertDoesNotExist()`, `assertTextEquals(...)`, `assertIsEnabled()`, `assertIsSelected()`, `assert(matcher)`.
- Actions: `performClick()`, `performTextInput(...)`, `performTextClearance()`, `performScrollTo()`, `performScrollToIndex(n)` (lazy lists), `performTouchInput { swipeLeft() }`, `performSemanticsAction(...)`.
- Call each action separately; actions do not chain inside one `perform` call.
- Lazy lists compose only visible items: scroll to an item before asserting on it.

## 5. Synchronization

- Finders, assertions and actions wait until Compose is idle, advancing a **virtual clock** automatically. Do not add `Thread.sleep`.
- Changing state outside composition has no visible effect until the next synchronizing call.
- Work Compose cannot see (data loading, background threads) needs `waitUntil`:

```kotlin
composeTestRule.waitUntilAtLeastOneExists(hasText("Loaded"), timeoutMillis = 5_000)
composeTestRule.waitUntilDoesNotExist(hasTestTag("loading"), timeoutMillis = 5_000)
composeTestRule.waitUntilExactlyOneExists(hasTestTag("result"))
composeTestRule.waitUntilNodeCount(hasTestTag("row"), count = 3)
```

- Register long-running non-Compose work with `registerIdlingResource` / `unregisterIdlingResource`.
- Test animations frame by frame by turning off auto-advance:

```kotlin
composeTestRule.mainClock.autoAdvance = false
composeTestRule.onNodeWithText("Expand").performClick()
composeTestRule.mainClock.advanceTimeBy(150)
composeTestRule.onNodeWithTag("details").assertIsDisplayed()
```

## 6. State restoration and configurations

Verify `rememberSaveable` state survives recreation without recreating an Activity:

```kotlin
@Test
fun query_survivesRecreation() {
    val restorationTester = StateRestorationTester(composeTestRule)
    restorationTester.setContent { SearchBar() }

    composeTestRule.onNodeWithTag("query").performTextInput("yoga")
    restorationTester.emulateSavedInstanceStateRestore()

    composeTestRule.onNodeWithTag("query").assertTextEquals("yoga")
}
```

Test sizes, font scale, dark mode, locale and layout direction with `DeviceConfigurationOverride`:

```kotlin
composeTestRule.setContent {
    DeviceConfigurationOverride(
        DeviceConfigurationOverride.FontScale(2f) then
            DeviceConfigurationOverride.ForcedSize(DpSize(1280.dp, 800.dp)),
    ) {
        AppTheme { ArticleScreen(uiState = sampleUiState, onBookmarkClick = {}) }
    }
}
```

## 7. Accessibility checks

Run automated accessibility checks in instrumented UI tests with `ui-test-junit4-accessibility` and an `AndroidComposeTestRule`, such as `createAndroidComposeRule<ComponentActivity>()`. Align Compose artifacts with the project's BOM; check the [Compose UI releases](https://developer.android.com/jetpack/androidx/releases/compose-ui) for API availability. Checks flag missing labels, small touch targets, low contrast and traversal problems.

```kotlin
composeTestRule.enableAccessibilityChecks()
composeTestRule.setContent { AppTheme { ArticleScreen(uiState = sampleUiState, onBookmarkClick = {}) } }
composeTestRule.onRoot().tryPerformAccessibilityChecks()
```

Once enabled, checks also run during actions such as `performClick()`. See `compose-accessibility`.

## 8. Custom semantics

Add a custom `SemanticsPropertyKey` only for values that are hard to match otherwise (for example a date picker's selected value), and never to expose visual details such as colors or font sizes.

## 9. Interop

- Espresso and Compose test APIs work together in the same test for mixed screens.
- For UiAutomator, set `Modifier.semantics { testTagsAsResourceId = true }` near the root so test tags are exposed as resource IDs.

## 10. Checklist

- [ ] The stateless composable is tested with fixed UI state and fake lambdas.
- [ ] Nodes are found by text, content description or role first; `testTag` only when needed.
- [ ] Strings come from resources.
- [ ] No sleeps; external work uses `waitUntil*` or idling resources.
- [ ] `rememberSaveable` state is covered with `StateRestorationTester`.
- [ ] Large font scale and large screens are covered with `DeviceConfigurationOverride`.
- [ ] Accessibility checks are enabled.
