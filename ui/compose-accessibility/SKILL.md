---
name: compose-accessibility
description: "Compose accessibility per Google's docs: API defaults, touch targets, labels, semantics properties (headings, live regions, errors, state), merging and clearing, custom actions, traversal order, text scaling, contrast, debugging, automated checks. Use for TalkBack or Switch Access support and accessibility audits."
---

# Accessible Compose UI

Sources of truth: [Accessibility in Jetpack Compose](https://developer.android.com/develop/ui/compose/accessibility), [API defaults](https://developer.android.com/develop/ui/compose/accessibility/api-defaults), [Semantics](https://developer.android.com/develop/ui/compose/accessibility/semantics), [Merging and clearing](https://developer.android.com/develop/ui/compose/accessibility/merging-clearing), [Modify traversal order](https://developer.android.com/develop/ui/compose/accessibility/traversal), [Support user-scalable content](https://developer.android.com/develop/ui/compose/accessibility/scalable-content), [Inspect and debug](https://developer.android.com/develop/ui/compose/accessibility/inspect-debug), [Testing](https://developer.android.com/develop/ui/compose/accessibility/testing), [Make apps more accessible](https://developer.android.com/guide/topics/ui/accessibility/apps), [Principles for improving app accessibility](https://developer.android.com/guide/topics/ui/accessibility/principles), [Non-linear font scaling to 200%](https://developer.android.com/about/versions/14/features#non-linear-font-scaling).

Related skills: `compose-ui` (color roles, typography), `compose-testing`, `compose-images`, `compose-lists`.

Accessibility services read the semantics tree, a parallel description of the UI that Compose builds next to the composition. Foundation and Material APIs fill it in for you; most work is choosing the API meant for the job, checking its defaults, and supplying what custom components leave out.

## 1. Start from the API defaults

- `Button`, `IconButton`, `ListItem`, `Checkbox`, `Switch`, `RadioButton`, `Slider` and `Surface`, and the Foundation modifiers `clickable`, `combinedClickable`, `toggleable`, `selectable` and `triStateToggleable`, already publish role, state, actions and merging.
- Building a custom control: open the Material implementation of the closest component and reproduce its accessibility behavior. A custom checkbox, for example, needs `triStateToggleable`.
- `Layout`, `Canvas` and `Modifier.pointerInput` publish nothing. Everything a user needs to know about such UI (a hand-drawn calendar, a chart) has to be added through `Modifier.semantics`.
- For a row with a label and a selection control, make the whole row the interactive element and pass `null` as the control's callback. Wrap radio button rows in `Modifier.selectableGroup()`.

```kotlin
@Composable
fun NotificationSetting(
    label: String,
    enabled: Boolean,
    onEnabledChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .toggleable(value = enabled, role = Role.Switch, onValueChange = onEnabledChange)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, Modifier.weight(1f))
        Switch(checked = enabled, onCheckedChange = null)
    }
}
```

## 2. Touch targets

- Anything a finger can activate needs a touch area of at least 48 x 48dp. Only precise pointers (mouse, trackpad) may use smaller targets.
- Material controls add that space only while interactive: `Checkbox(onCheckedChange = null)` has no extra padding, which is correct when its parent row handles the click.
- When a clickable element is smaller, Compose extends its touch area past its bounds, and neighboring targets can then overlap. Give custom clickables a real minimum size instead: `Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp)` before `clickable`, or Material 3's `Modifier.minimumInteractiveComponentSize()`, which reserves 48dp only when the element would measure smaller.
- **(stricter than Google)** Do not provide `LocalMinimumInteractiveComponentSize` as `0.dp` to disable Material's enforcement.

```kotlin
Box(
    modifier = Modifier
        .sizeIn(minWidth = 48.dp, minHeight = 48.dp)
        .clickable(onClickLabel = stringResource(R.string.remove_filter, filter.name), onClick = onRemove),
    contentAlignment = Alignment.Center,
) {
    Icon(painterResource(R.drawable.ic_close), contentDescription = null, modifier = Modifier.size(16.dp))
}
```

Prefer `IconButton` when the design allows it; it already handles size, role and ripple.

## 3. Labels

- `Image` and `Icon` get `contentDescription = stringResource(...)`. The text is spoken and must be translated.
- A label says what the element is for or what happens when used. It does not describe how it looks. Google's examples: a camera glyph means "Take a photo", and a button that submits a form is "Submit", not "Submit button". The element type comes from its `Role`, so never append "button", "icon" or "image".
- Use `contentDescription = null` for decoration and for icons whose meaning a sibling `Text` in the same merged element already carries. Hide other decorative elements (a separator glyph, a watermark) with `Modifier.semantics { hideFromAccessibility() }`.
- `Text` needs no description; its text is announced.
- Labels inside a collection must differ from each other and reflect the item's own content ("Lisbon", "Porto"), so users notice when focus lands on something already visited.
- Text fields: the `label` slot supplies the accessible name. A placeholder can show an example of valid input.
- Action wording: `clickable(onClickLabel = ...)` and `combinedClickable(onClickLabel = ..., onLongClickLabel = ...)` turn TalkBack's generic "Double tap to activate" into "Double tap to open article". If the `clickable` is buried inside a component you cannot change, add `Modifier.semantics { onClick(label = ...) { true } }` on the outside; the merged node keeps the inner action and takes the outer label.

## 4. Semantics for content types

| Content | Semantics |
|---|---|
| Section title on a text-heavy screen | `heading()`. Screen readers offer heading-to-heading navigation, so users can skip whole sections |
| Alert, snackbar-like message, content that changes while focus is elsewhere | `liveRegion = LiveRegionMode.Polite`. `Assertive` only for urgent, time-sensitive content. Never on content that updates constantly, such as a countdown |
| Custom sheet, dialog or panel | `paneTitle = "..."` so pane changes are announced |
| Invalid input in a custom field | `error("What is wrong and how to fix it")` |
| Custom progress indicator | `progressBarRangeInfo = ProgressBarRangeInfo(current = progress, range = 0f..1f)` |
| Custom list or grid not built on lazy layouts | `collectionInfo = CollectionInfo(rowCount, columnCount)` on the container, `collectionItemInfo` on each item |
| State wording beyond the default "On"/"Checked" | `stateDescription = stringResource(R.string.subscribed)` |
| Kind of control | `role = Role.Button`, `Role.Switch`, `Role.Checkbox`, `Role.RadioButton`, `Role.Tab`, `Role.Image`, via `clickable`/`toggleable`/`selectable` or `semantics` |

The full list lives in `SemanticsProperties` and `SemanticsActions`.

```kotlin
@Composable
fun SectionHeader(title: String, modifier: Modifier = Modifier) {
    Text(
        text = title,
        style = MaterialTheme.typography.titleLarge,
        modifier = modifier.semantics { heading() },
    )
}
```

## 5. Merging, clearing and hiding

Focus stops should match how a sighted user reads the screen: not one stop per low-level composable, and not so few that unrelated content runs together.

| Situation | API |
|---|---|
| Several children form one logical item (avatar, name and timestamp) | `Modifier.semantics(mergeDescendants = true) {}` on the parent |
| A custom component needs semantics that replace its children's | `Modifier.clearAndSetSemantics { role = ...; stateDescription = ... }` |
| A subtree must disappear for every consumer, tests and autofill included | `Modifier.clearAndSetSemantics {}` with an empty lambda |
| Decorative or redundant content that tests still need | `Modifier.semantics { hideFromAccessibility() }` |

```kotlin
@Composable
fun ReviewHeader(review: Review, modifier: Modifier = Modifier) {
    Row(modifier.semantics(mergeDescendants = true) {}) {
        Avatar(review.author, contentDescription = null)
        Column {
            Text(review.author.displayName)
            Text(pluralStringResource(R.plurals.stars, review.stars, review.stars))
        }
    }
}
```

- `clickable`, `toggleable`, `Button` and `ListItem` merge their children already.
- A child that merges itself (its own `clickable`, a nested `IconButton`) is not absorbed by the parent and stays a separate focus stop. That is usually intended; to collapse it, use custom actions (section 6).
- `clearAndSetSemantics` clears everything that follows it in the modifier chain, whatever the merge settings. Use it sparingly: TalkBack, autofill, tests and AI agents all lose that information.
- Each semantics property merges by its own policy; content descriptions of merged children are collected into a list.

## 6. Custom actions

Gestures such as swipe to dismiss or drag to reorder are hard or impossible for many users. Expose each one as a `CustomAccessibilityAction`; TalkBack lists them in its actions menu and Switch Access in its menu.

List rows with several small buttons are another case: moving the secondary actions onto the row saves switch and voice users from stepping through every button of every row. Clear the moved children's semantics so each action exists once.

```kotlin
@Composable
fun MessageRow(
    message: Message,
    onOpen: () -> Unit,
    onArchive: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val openLabel = stringResource(R.string.open_message)
    val archiveLabel = stringResource(R.string.archive_message)
    Row(
        modifier = modifier
            .clickable(onClickLabel = openLabel, onClick = onOpen)
            .semantics {
                customActions = listOf(CustomAccessibilityAction(archiveLabel) { onArchive(); true })
            },
    ) {
        MessagePreview(message, Modifier.weight(1f))
        IconButton(onClick = onArchive, modifier = Modifier.clearAndSetSemantics {}) {
            Icon(painterResource(R.drawable.ic_archive), contentDescription = null)
        }
    }
}
```

The action lambda returns `true` when it handled the action.

## 7. Traversal order

Screen readers visit elements in reading order (start to end, then top to bottom). Change it only when the layout's visual grouping differs from that order: columns of cards, a circular clock face, overlapping content.

- `isTraversalGroup = true` goes on the parent container (a `Row`, `Column` or `Box`, which need not be focusable itself). All of its children are read before anything outside it.
- `traversalIndex` goes on elements that accessibility services actually focus (text, buttons). Lower values come first, negative values are allowed, and the default is `0f`. On a non-focusable container it does nothing unless that container is also a traversal group.
- Indices are relative to the enclosing traversal group. Without a group around them, indexed elements are sorted against every other `0f` element on the screen and can end up read last.
- Scroll containers such as `LazyColumn` and Material surfaces are traversal groups by default. `isTraversalGroup = false` removes that boundary when it breaks the intended order.
- Elements on different `zIndex` levels, and unnecessary merging, both change which nodes the ordering applies to. Verify every change with TalkBack.

```kotlin
@Composable
fun ComparisonColumns(left: Plan, right: Plan) {
    Row {
        PlanColumn(left, Modifier.weight(1f).semantics { isTraversalGroup = true })
        PlanColumn(right, Modifier.weight(1f).semantics { isTraversalGroup = true })
    }
}
```

## 8. Text size and scaling

- Text sizes come from theme typography in `sp`. Since Android 14, users can scale fonts up to 200%, and the system applies a nonlinear curve so large text grows less than small text. Consequences: never derive layout sizes by adding `sp` values (4sp + 20sp is not necessarily 24sp), and do not use `sp` for padding.
- Containers holding text must grow: no fixed `height` on them (use `heightIn(min = ...)`), allow wrapping, and make sure content reflows without horizontal panning at the largest font and display sizes.
- Check with `@PreviewFontScales`, `DeviceConfigurationOverride.FontScale(2f)` in tests (see `compose-testing`), and a device set to maximum font size and display size.
- Reading-heavy or dense visual screens can add in-app pinch-to-zoom. `Modifier.transformable` only detects the gesture; apply the scale by providing a modified `LocalDensity` to the content. Scaling `density` enlarges everything and suits feeds and grids; scaling `fontScale` enlarges only text and suits articles. Google's samples clamp the factor to roughly 0.75x to 3.5x. Persist the choice (DataStore) and offer a non-gesture control to adjust or reset it.

## 9. Color and contrast

- Text contrast against its background: at least 4.5:1 when the text is smaller than 18sp, or bold and smaller than 14sp; at least 3:1 for all other text. Measure with Accessibility Scanner or a contrast checker.
- Material color roles used in their pairs (`onSurface` on `surface`, `onPrimaryContainer` on `primaryContainer`) and dynamic color are designed to meet contrast. Mismatched roles are the common source of failures; see `compose-ui`.
- Color must never be the only signal. Add a shape, text, icon, pattern or haptic feedback, and expose custom states through `stateDescription`.

## 10. Inspect, debug and test

### Manual
- Walk every changed screen with TalkBack and Switch Access (Android Accessibility Suite, which also includes Select to Speak and the Accessibility Menu). This is the most direct view of what users experience.
- Run Accessibility Scanner on the running app.
- Inspect semantics in Layout Inspector, which can show the merged and unmerged trees, or with TalkBack's TreeDebug developer setting.
- Accessibility services read the unmerged tree and apply their own merging; tests use the merged tree by default. Print both with `onRoot().printToLog("A11Y")` and `onRoot(useUnmergedTree = true).printToLog("A11Y")`.
- Reading symptoms: an element TalkBack never focuses often carries `hideFromAccessibility` or sits under a decorative overlay; an element with no action announced is missing `onClick` semantics (no `clickable`).

### Automated
Compose 1.8 added Accessibility Test Framework checks, the engine behind Accessibility Scanner, to Compose UI tests. They report missing labels, small touch targets, low contrast and traversal problems.

- Dependency: `androidx.compose.ui:ui-test-junit4-accessibility`.
- `enableAccessibilityChecks()` on the `AndroidComposeTestRule` requires API 34 or higher on the test device.
- Once enabled, every test action (`performClick`, `performTextInput`) runs the checks; `tryPerformAccessibilityChecks()` runs them explicitly.
- Pass an `AccessibilityValidator` to change which result types fail the test. The default validator runs checks from the root view; keep `setRunChecksFromRootView(true)` when replacing it.

```kotlin
@SdkSuppress(minSdkVersion = 34)
class PaymentStepAccessibilityTest {

    @get:Rule
    val rule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun paymentStep_hasNoWarnings() {
        rule.enableAccessibilityChecks(
            AccessibilityValidator()
                .setRunChecksFromRootView(true)
                .setThrowExceptionFor(AccessibilityCheckResult.AccessibilityCheckResultType.WARNING),
        )
        rule.setContent { AppTheme { PaymentStep(uiState = PaymentUiState.Sample, onPay = {}) } }

        rule.onNodeWithText("Pay").performClick()
        rule.onRoot().tryPerformAccessibilityChecks()
    }
}
```

Android Lint also flags images without a `contentDescription`. Semantics assertions (`assertContentDescriptionEquals`, `SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Switch)`): see `compose-testing`.

## 11. Audit checklist

- [ ] Standard Material and Foundation APIs are used where they fit; custom controls copy the matching component's semantics.
- [ ] Every touch target is 48 x 48dp or larger, without overlapping neighbors.
- [ ] Images and icons have translated, purpose-based, unique labels, or `null` when decorative.
- [ ] Custom controls expose role, state and action labels.
- [ ] Section titles are headings; alerts, errors, panes and progress are announced.
- [ ] Focus stops match logical items; nested actions are reachable, via custom actions where rows repeat them.
- [ ] Reading order matches the visual grouping.
- [ ] Layouts survive 200% font scale and the largest display size without clipping or panning.
- [ ] Text contrast meets 4.5:1 or 3:1 as applicable; color is never the only cue.
- [ ] TalkBack and Switch Access pass done; accessibility checks run in UI tests.
