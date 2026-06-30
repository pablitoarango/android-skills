---
name: migrate-xml-to-compose
description: "Views to Compose migration per Google's strategy: incremental order, ComposeView and AndroidView interop, layout and widget mappings, navigation and theming during migration. Use when converting XML layouts or View screens to Compose."
---

# XML to Compose Migration

Sources of truth: [Migration strategy](https://developer.android.com/develop/ui/compose/migrate/strategy), [Compose in Views](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/compose-in-views), [Views in Compose](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/views-in-compose), [Other considerations](https://developer.android.com/develop/ui/compose/migrate/other-considerations), [RecyclerView migration](https://developer.android.com/develop/ui/compose/migrate/migration-scenarios/recycler-view), [CoordinatorLayout migration](https://developer.android.com/develop/ui/compose/migrate/migration-scenarios/coordinator-layout), [Navigation migration](https://developer.android.com/develop/ui/compose/migrate/migration-scenarios/navigation), [XML themes to Material 3](https://developer.android.com/develop/ui/compose/designsystems/views-to-compose), [Interoperability testing](https://developer.android.com/develop/ui/compose/testing/interoperability).

## 1. Migration strategy

Migrate **incrementally**; Compose and Views coexist until the app is fully Compose.

1. **Build new features in Compose.** New screens are Compose, hosted by the existing navigation (for example a Fragment with a `ComposeView`).
2. **Build a shared component library** as you go: common composables and the theme in a shared UI module, so every migrated screen reuses them.
3. **Replace existing screens, simplest first** (static screens such as welcome, confirmation, settings).
4. **Mixed screens migrate bottom-up**: replace leaf elements one at a time until the whole screen is Compose.
5. **Remove Fragments and move navigation** only when every destination is a screen-level composable. The end state is a single Activity with Compose navigation.

## 2. Migrating one screen

### Prepare

- **Protect behavior first.** Google relies on UI tests to catch migration regressions. If the screen has none, write them against the View version before changing it; Espresso tests keep working when run with `createAndroidComposeRule` (section 6).
- **Move to unidirectional data flow.** Compose works with UDF; an MVP presenter or Fragment code calling setters on views should become a ViewModel exposing UI state, before or during the migration (`android-viewmodel`).

### Inventory the screen

Go through the layout and its Fragment or Activity and record:

- **Displayed state and who sets it.** For every value a View shows (text, checked, enabled, visibility, list items), find where it changes today: a binding expression, an observer calling setters, or the View's own internal state. A View owns such fields; a composable receives them. Each becomes a UI state field or hoisted state.
- **User input.** Every listener, watcher and adapter callback becomes an event lambda passed up to the route composable.
- **Values shared with Views that stay.** Decide which side owns them (section 5).
- **Styling inputs.** Explicit `style` attributes, theme attribute references, text appearances, color state lists and shape overlays. They move into the Compose theme, not into literals (section 7).
- **Views that stay Views.** SDK Views with no Compose version (`AdView`, `WebView`, `SurfaceView` players) stay behind `AndroidView`. Rewrite custom Views in Compose, simplest first. For Google Maps, prefer [Maps Compose](https://developers.google.com/maps/documentation/android-sdk/maps-compose), which provides `GoogleMap` and manages its map lifecycle.
- **Structure defined by resources.** Reused or lazily inflated layout files, size-qualified layout folders, embedded Fragments, binding adapters. [`mappings.md`](mappings.md) covers each.
- **Scroll and inset coordination.** `CoordinatorLayout` behaviors, scrolling parents that will contain a `ComposeView`, `fitsSystemWindows`. These need scroll behaviors, nested scroll interop or explicit inset consumption (section 4).
- **Navigation coupling.** `findNavController()` calls and arguments. Arguments carrying complex objects should become IDs loaded from the data layer.

### Convert

- Map containers, widgets and attributes with [`mappings.md`](mappings.md).
- Split into a route composable (gets the ViewModel, collects state) and a stateless screen composable (`compose-ui`).
- Replace `visibility` toggles with conditional composition: a composable is either in the composition or not.
- Keep the Fragment as a thin `ComposeView` host while Fragment navigation remains.

### Check the result

- The UI tests written before the change pass against the Compose version.
- Rendering matches the View version for the same data, compared with screenshot tests (`android-testing`) or previews in light and dark theme, large font scale and every supported window size.
- Every theme value matches the old XML theme; no value was invented or hardcoded.
- `rememberSaveable` state and ViewModel state survive rotation and process recreation (`StateRestorationTester`, see `compose-testing`).
- TalkBack labels, merged rows, touch targets and traversal order are correct (`compose-accessibility`).
- Where Views and Compose share the hierarchy, insets are consumed once and nested scrolling hands over between them.
- The ViewModel keeps the same owner and scope as before.
- Dead code is gone: the layout file, adapters and ViewHolders, binding adapters, styles and dimensions nothing references, and the view binding or data binding build features once no layout needs them.

## 3. Mapping layouts, widgets and attributes

When converting a layout, read [`mappings.md`](mappings.md). It follows the structure of the Compose docs: layout containers; scrolling, lists and paging; text and input; images; Material components; attributes to modifiers; resources and layout reuse.

## 4. Interop

### Compose inside Views

In a Fragment, always set the composition strategy so the composition follows the Fragment's view lifecycle:

```kotlin
class ArticleFragment : Fragment() {
    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ): View = ComposeView(requireContext()).apply {
        setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
        setContent {
            AppTheme {
                ArticleRoute()
            }
        }
    }
}
```

| Where the `ComposeView` lives | `ViewCompositionStrategy` |
|---|---|
| A Fragment's view | `DisposeOnViewTreeLifecycleDestroyed`, or `DisposeOnLifecycleDestroyed(viewLifecycleOwner)` |
| A View whose lifecycle owner is not known yet | `DisposeOnViewTreeLifecycleDestroyed` |
| An Activity layout, or a `RecyclerView` item | `DisposeOnDetachedFromWindowOrReleasedFromPool` (the default); it replaces `DisposeOnDetachedFromWindow` |

- Give every `ComposeView` on a screen a **unique ID** (define IDs in `res/values/ids.xml` for programmatic views) so saved state works.
- Preview a composable inside the XML Layout Editor with `tools:composableName` on the `ComposeView`.
- **Insets:** each `ComposeView` consumes all insets by default. Consume them on the side that owns the outermost layout: with a View root, set `consumeWindowInsets = false` on the `ComposeView`; with a Compose root, consume in Compose and pad `AndroidView`s.
- **Nested scrolling:** a `ComposeView` inside a cooperating View parent such as `CoordinatorLayout` needs `Modifier.nestedScroll(rememberNestedScrollInteropConnection())` on its content. `RecyclerView` and `ViewPager2` do not implement `NestedScrollingParent3`, so continuous scrolling from a Compose child into them is not possible. See [nested scrolling interop](https://developer.android.com/develop/ui/compose/touch-input/pointer-input/nested-scroll#nested-scrolling-interop).
- **Shared components:** wrap a composable used from XML layouts in an `AbstractComposeView` subclass that exposes its inputs as `mutableStateOf` properties and wraps `Content()` in the app theme.
- When a `ComposeView` lives inside a `RecyclerView`, use RecyclerView 1.3.0 or newer.

### Views inside Compose

```kotlin
@Composable
fun WebContent(url: String, modifier: Modifier = Modifier) {
    AndroidView(
        factory = { context -> WebView(context) },
        update = { webView ->
            if (webView.url != url) webView.loadUrl(url)
        },
        onRelease = { webView -> webView.destroy() },
        modifier = modifier,
    )
}
```

The [WebView API](https://developer.android.com/reference/android/webkit/WebView) example shows creation, input updates and cleanup; configure navigation and other browser behavior for the app's requirements.

- `factory` runs once, on the UI thread: create the View and set constant properties there. Never hold a View in `remember` outside `AndroidView`.
- `update` runs right after `factory` and again whenever state it reads changes.
- By default, Views are discarded and recreated inside lazy layouts. Pass a non-null `onReset = { view -> ... }` to opt in to reuse; it runs before the View is reused and should clear transient state. `onRelease` runs once when the View leaves the composition for good.
- `AndroidView` does not clip its View to its bounds; call `View.setClipToOutline` where needed (common for `SurfaceView`).
- Use `AndroidViewBinding` (`androidx.compose.ui:ui-viewbinding`) only for small legacy XML layouts during migration, not full screens.
- Use `AndroidFragment<MyFragment>()` only as a temporary step while a screen still depends on a Fragment. In a pager, cap offscreen pages with its `maxLifecycle` parameter (Fragment 1.9.0 or newer).
- Framework objects stay reachable through `LocalContext`, `LocalConfiguration` and `LocalView`.

## 5. State and navigation during migration

- **ViewModel**: obtain it only in the route composable; collect with `collectAsStateWithLifecycle()` (or `observeAsState()` for `LiveData` not yet converted to `StateFlow`). Never pass it to child composables. `viewModel()` returns the same instance for every composable under one Activity or Fragment, unless the composable is a navigation destination.
- **Click listeners** become event lambdas.
- **Shared state between Views and Compose**: prefer a ViewModel both read. When state is tied to a UI element, the side closer to the root owns it: if Compose owns it, publish to View code with `SideEffect`; if a View owns it, hold it in `mutableStateOf` so Compose observes changes.
- **Navigation**: one navigation setup cannot mix Fragment and composable destinations. Keep Fragment-based Navigation while any destination is still a Fragment. Once every destination is a screen composable, move to a single Activity with Navigation 3 (see `compose-navigation`) and delete the Fragments, their layouts and navigation XML.

## 6. Testing

- Use `createAndroidComposeRule<YourActivity>()` for screens mixing Views and Compose. In the same test, Espresso's `onView` finds Views and the rule's finders locate composables (`compose-testing`).
- For a composable inside a `RecyclerView` row or a `ViewPager` page, locate the container with Espresso first, then scope the Compose assertion to it.
- UiAutomator sees composables by resource ID only after setting `testTagsAsResourceId = true` in semantics near the root.
- Add UI tests before migrating a screen when none exist, so the migration is covered.

## 7. Theming

- Wrap all Compose content in the app's theme before any Material composable; Material components behave in undefined ways without a `MaterialTheme`. Target Material 3 when the design system allows it.
- During migration the XML theme and the Compose theme are two sources of truth; change both until the XML theme can be deleted.
- **Colors** map by role, not by hex name: `colorPrimary` → `primary`, `colorOnPrimary` → `onPrimary`, `colorSurface` → `surface`, `colorOnSurface` → `onSurface`, `colorError` → `error`. Legacy `colorPrimaryVariant` / `colorPrimaryDark` and `colorAccent` need a decision (`primaryContainer`, `secondary` or `tertiary`). Migrate light and dark schemes; Material Theme Builder can generate them.
- **Typography**: `TextAppearance.Material3.BodyMedium` becomes `MaterialTheme.typography.bodyMedium`, and so on for each role; custom text appearances become a `Typography` object.
- **Shapes**: `ShapeAppearance` overlays become a `Shapes` object passed to `MaterialTheme`.
- **Styles** have no Compose equivalent. Translate a component style into that component's parameters (`ButtonDefaults.buttonColors(...)`, `shape`, `contentPadding`), or into a named composable such as `PrimaryActionButton` when the style is reused.
- `colorResource` works for static colors only; it flattens color state lists.
- Copy values from the existing XML theme. Do not invent new ones or hardcode them in composables.

## 8. Checklist

- [ ] The screen was picked by the migration order and covered by UI tests before it changed.
- [ ] Every displayed value comes from UI state or hoisted state; no View-style setters or binding code remain in the migrated part.
- [ ] Route composable plus stateless screen composable; ViewModel only in the route; state collected with `collectAsStateWithLifecycle()`.
- [ ] Colors, typography and shapes come from the Compose theme and match the XML theme.
- [ ] Interop is configured: composition strategy per host, unique `ComposeView` IDs, insets consumed once, nested scroll interop where Views and Compose scroll together.
- [ ] `AndroidView` only for Views without a Compose equivalent, with `onReset` in lazy layouts and cleanup in `onRelease`.
- [ ] Fragment-based navigation stays until every destination is a composable.
- [ ] UI tests, visual comparison, state restoration and accessibility checks pass.
- [ ] Layouts, adapters, binding code and resources made unused by the migration are deleted.
