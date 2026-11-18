---
name: compose-adaptive-layouts
description: "Adaptive Compose layouts per Google's docs: window size classes, list-detail and supporting panes, NavigationSuiteScaffold, state across resizing. Use when UI must work on tablets, foldables, desktop windows, or rotation, and when layouts stretch on large screens, code checks isTablet or locks orientation, or state is lost on resize or fold."
---

# Compose Adaptive Layouts

Sources of truth: [Adaptive apps](https://developer.android.com/develop/ui/compose/layouts/adaptive), [Build adaptive navigation](https://developer.android.com/develop/ui/compose/layouts/adaptive/build-adaptive-navigation), [Canonical layouts](https://developer.android.com/develop/adaptive-apps/guides/canonical-layouts), [Use window size classes](https://developer.android.com/develop/ui/compose/layouts/adaptive/use-window-size-classes), [List-detail](https://developer.android.com/develop/ui/compose/layouts/adaptive/list-detail), [App orientation, aspect ratio, and resizability](https://developer.android.com/develop/ui/compose/layouts/adaptive/app-orientation-aspect-ratio-resizability), [Material 3 Adaptive releases](https://developer.android.com/jetpack/androidx/releases/compose-material3-adaptive).

## 1. Adapt to the window, not the device

- Decide layout from the **app window size**, which changes with multi-window, desktop windowing, folding and rotation.
- Do not check device type (`isTablet`), physical screen size, or orientation, and do not lock orientation.
- For apps targeting API 36+, the system ignores `screenOrientation`, `resizeableActivity`, `minAspectRatio`, `maxAspectRatio` and `setRequestedOrientation()` on displays with smallest width >= 600dp. `PROPERTY_COMPAT_ALLOW_RESTRICTED_RESIZABILITY` is only a temporary opt-out and stops working when targeting API 37.
- Make screens scroll so every control stays reachable in short landscape windows.
- Keep one adaptive code path instead of separate phone and tablet screens.

Use `currentWindowAdaptiveInfoV2()`: `currentWindowAdaptiveInfo()` is deprecated in Material 3 Adaptive 1.3.0, and only V2 reports the large (1200dp) and extra-large (1600dp) width classes by default. Some guide pages still show the old function.

```kotlin
val windowSizeClass = currentWindowAdaptiveInfoV2().windowSizeClass

val isExpanded = windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_EXPANDED_LOWER_BOUND)
val isMediumOrLarger = windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_MEDIUM_LOWER_BOUND)
```

| Width class | Typical window | Typical layout |
|---|---|---|
| Compact | Phone portrait | Single pane, navigation bar |
| Medium | Phone landscape, small tablet, unfolded foldable | Single pane or two panes, navigation rail |
| Expanded and larger | Tablet landscape, desktop window | Two or more panes, navigation rail or drawer |

- Read the size class once near the top (the app or screen root), and pass layout decisions down as parameters or through a UI state holder (`compose-ui`).
- Width drives most decisions. Check height for cases like phones in landscape (medium width, compact height), where two panes do not fit. Read foldable posture, such as tabletop, from `windowPosture`.

## 2. Canonical layouts

| Layout | Use for | Compose API |
|---|---|---|
| List-detail | Master list with a detail view (inbox, settings) | With Navigation 3: `ListDetailSceneStrategy` (see `compose-navigation`). Otherwise: `NavigableListDetailPaneScaffold` |
| Supporting pane | Main content with secondary content (document + comments) | With Navigation 3: `SupportingPaneSceneStrategy`. Otherwise: `NavigableSupportingPaneScaffold` |
| Feed | Grid of equivalent items | `LazyVerticalGrid(GridCells.Adaptive(minSize))` (see `compose-lists`) |

Navigation 3 scene strategies come from `androidx.compose.material3.adaptive:adaptive-navigation3`; the navigable scaffolds come from `adaptive-navigation`.

List-detail without Navigation 3. `NavigableListDetailPaneScaffold` wraps `ListDetailPaneScaffold` and handles back and predictive back itself, so do not add a `BackHandler`:

```kotlin
@OptIn(ExperimentalMaterial3AdaptiveApi::class)
@Composable
fun ConversationsListDetail(conversations: List<Conversation>) {
    val navigator = rememberListDetailPaneScaffoldNavigator<String>()
    val scope = rememberCoroutineScope()

    NavigableListDetailPaneScaffold(
        navigator = navigator,
        listPane = {
            AnimatedPane {
                ConversationList(
                    conversations = conversations,
                    selectedId = navigator.currentDestination?.contentKey,
                    onConversationClick = { id ->
                        scope.launch { navigator.navigateTo(ListDetailPaneScaffoldRole.Detail, id) }
                    },
                )
            }
        },
        detailPane = {
            AnimatedPane {
                navigator.currentDestination?.contentKey?.let { id -> ConversationDetail(id) }
                    ?: SelectConversationPlaceholder()
            }
        },
    )
}
```

- The content key must be saveable (a `String`, or a `Parcelable` class) so the selection survives configuration changes.
- Back defaults to `BackNavigationBehavior.PopUntilScaffoldValueChange`; pass `defaultBackBehavior` to change it.

## 3. Adaptive navigation

Use `NavigationSuiteScaffold` (`androidx.compose.material3:material3-adaptive-navigation-suite`) for top-level destinations. Use the overload that takes `navigationItems` with `NavigationSuiteItem`; the API reference recommends it over the older `navigationSuiteItems` overload that the guide still shows. Its default type comes from `NavigationSuiteScaffoldDefaults.navigationSuiteType(...)`, which picks a navigation bar or rail variant from the window size class and posture.

```kotlin
NavigationSuiteScaffold(
    navigationItems = {
        TopLevelDestination.entries.forEach { destination ->
            NavigationSuiteItem(
                selected = destination == currentDestination,
                onClick = { onDestinationClick(destination) },
                icon = { Icon(destination.icon, contentDescription = null) },
                label = { Text(stringResource(destination.label)) },
            )
        }
    },
) {
    AppContent()
}
```

Override the default only when the design requires it, and pass the same type to `NavigationSuiteScaffold(navigationSuiteType = ...)` and to each `NavigationSuiteItem`:

```kotlin
val adaptiveInfo = currentWindowAdaptiveInfoV2()
val navigationSuiteType = if (adaptiveInfo.windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_EXPANDED_LOWER_BOUND)) {
    NavigationSuiteType.NavigationDrawer
} else {
    NavigationSuiteScaffoldDefaults.navigationSuiteType(adaptiveInfo)
}
```

## 4. Preserve state across window changes

- Window size changes are configuration changes. Keep screen state in the ViewModel and UI element state in `rememberSaveable`, so resizing, folding or rotating never loses input, scroll position or selection.
- When a layout switches between one and two panes, keep the selected item in state that both layouts read, so the detail stays selected.

## 5. Content that adapts

- Let content fill available width with constraints (`fillMaxWidth`, `widthIn(max = ...)` for readable text) instead of fixed widths.
- Use `BoxWithConstraints` or custom layouts only for component-level decisions that depend on the space a component receives, not on the window.
- Use `GridCells.Adaptive(minSize)` so grids gain columns as space grows.

## 6. Input beyond touch

- Large screens often have a keyboard, mouse, trackpad or stylus. Compose supports tab navigation and mouse or trackpad click, select and scroll by default; keep custom components focusable and publish keyboard shortcuts through `onProvideKeyboardShortcuts()`.

## 7. Test on several sizes

- Previews: `@PreviewScreenSizes`, or several `@Preview(widthDp = ..., heightDp = ...)` annotations.
- Tests: `DeviceConfigurationOverride.ForcedSize(DpSize(...))` (see `compose-testing`).
- Manual: the resizable emulator, a foldable emulator, and desktop windowing.

## 8. Checklist

- [ ] Layout decisions come from `currentWindowAdaptiveInfoV2().windowSizeClass`, not device type or orientation.
- [ ] Orientation is not locked.
- [ ] Top-level navigation uses `NavigationSuiteScaffold` (or equivalent adaptive behavior).
- [ ] List-detail screens show two panes on large windows.
- [ ] State survives resizing and folding.
- [ ] Compact, medium and expanded widths are previewed or tested.
