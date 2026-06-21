---
name: compose-adaptive-layouts
description: "Adaptive Compose layouts per Google's docs: window size classes, list-detail and supporting panes, NavigationSuiteScaffold, state across resizing. Use when UI must work on tablets, foldables, desktop windows, or rotation."
---

# Compose Adaptive Layouts

Sources of truth: [Adaptive apps](https://developer.android.com/develop/ui/compose/layouts/adaptive), [Build adaptive navigation](https://developer.android.com/develop/ui/compose/layouts/adaptive/build-adaptive-navigation), [Canonical layouts](https://developer.android.com/develop/adaptive-apps/guides/canonical-layouts).

## 1. Adapt to the window, not the device

- Decide layout from the **app window size**, which changes with multi-window, desktop windowing, folding and rotation.
- Do not check device type (`isTablet`), physical screen size, or orientation, and do not lock orientation.
- Keep one adaptive code path instead of separate phone and tablet screens.

```kotlin
val windowSizeClass = currentWindowAdaptiveInfo().windowSizeClass

val isExpanded = windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_EXPANDED_LOWER_BOUND)
val isMediumOrLarger = windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_MEDIUM_LOWER_BOUND)
```

| Width class | Typical window | Typical layout |
|---|---|---|
| Compact | Phone portrait | Single pane, navigation bar |
| Medium | Phone landscape, small tablet, unfolded foldable | Single pane or two panes, navigation rail |
| Expanded and larger | Tablet landscape, desktop window | Two or more panes, navigation rail or drawer |

- Read the size class once near the top (the app or screen root), and pass layout decisions down as parameters or through a UI state holder (`compose-ui`).
- Width drives most decisions; check height only for cases like tabletop posture or very short windows.

## 2. Canonical layouts

| Layout | Use for | Compose API |
|---|---|---|
| List-detail | Master list with a detail view (inbox, settings) | With Navigation 3: `ListDetailSceneStrategy` (see `compose-navigation`). Otherwise: `ListDetailPaneScaffold` |
| Supporting pane | Main content with secondary content (document + comments) | `SupportingPaneScaffold` |
| Feed | Grid of equivalent items | `LazyVerticalGrid(GridCells.Adaptive(minSize))` (see `compose-lists`) |

List-detail without Navigation 3:

```kotlin
@OptIn(ExperimentalMaterial3AdaptiveApi::class)
@Composable
fun ConversationsListDetail(conversations: List<Conversation>) {
    val navigator = rememberListDetailPaneScaffoldNavigator<String>()
    val scope = rememberCoroutineScope()

    BackHandler(navigator.canNavigateBack()) {
        scope.launch { navigator.navigateBack() }
    }

    ListDetailPaneScaffold(
        directive = navigator.scaffoldDirective,
        value = navigator.scaffoldValue,
        listPane = {
            AnimatedPane {
                ConversationList(
                    conversations = conversations,
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

## 3. Adaptive navigation

Use `NavigationSuiteScaffold` (`androidx.compose.material3:material3-adaptive-navigation-suite`) for top-level destinations. By default it shows a navigation bar when the window width or height is compact, or the device is in tabletop posture, and a navigation rail otherwise.

```kotlin
NavigationSuiteScaffold(
    navigationSuiteItems = {
        TopLevelDestination.entries.forEach { destination ->
            item(
                icon = { Icon(destination.icon, contentDescription = null) },
                label = { Text(stringResource(destination.label)) },
                selected = destination == currentDestination,
                onClick = { onDestinationClick(destination) },
            )
        }
    },
) {
    AppContent()
}
```

Override the default only when the design requires it:

```kotlin
val adaptiveInfo = currentWindowAdaptiveInfo()
val layoutType = if (adaptiveInfo.windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_EXPANDED_LOWER_BOUND)) {
    NavigationSuiteType.NavigationDrawer
} else {
    NavigationSuiteScaffoldDefaults.calculateFromAdaptiveInfo(adaptiveInfo)
}
```

## 4. Preserve state across window changes

- Window size changes are configuration changes. Keep screen state in the ViewModel and UI element state in `rememberSaveable`, so resizing, folding or rotating never loses input, scroll position or selection.
- When a layout switches between one and two panes, keep the selected item in state that both layouts read, so the detail stays selected.

## 5. Content that adapts

- Let content fill available width with constraints (`fillMaxWidth`, `widthIn(max = ...)` for readable text) instead of fixed widths.
- Use `BoxWithConstraints` or custom layouts only for component-level decisions that depend on the space a component receives, not on the window.
- Use `GridCells.Adaptive(minSize)` so grids gain columns as space grows.

## 6. Test on several sizes

- Previews: `@PreviewScreenSizes`, or several `@Preview(widthDp = ..., heightDp = ...)` annotations.
- Tests: `DeviceConfigurationOverride.ForcedSize(DpSize(...))` (see `compose-testing`).
- Manual: the resizable emulator, a foldable emulator, and desktop windowing.

## 7. Checklist

- [ ] Layout decisions come from `currentWindowAdaptiveInfo().windowSizeClass`, not device type or orientation.
- [ ] Orientation is not locked.
- [ ] Top-level navigation uses `NavigationSuiteScaffold` (or equivalent adaptive behavior).
- [ ] List-detail screens show two panes on large windows.
- [ ] State survives resizing and folding.
- [ ] Compact, medium and expanded widths are previewed or tested.
