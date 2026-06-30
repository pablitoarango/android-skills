# View to Compose mappings

Part of `migrate-xml-to-compose`. Sources: [Layout basics](https://developer.android.com/develop/ui/compose/layouts/basics), [Lists and grids](https://developer.android.com/develop/ui/compose/lists), [Pager](https://developer.android.com/develop/ui/compose/layouts/pager), [Text](https://developer.android.com/develop/ui/compose/text), [Material components](https://developer.android.com/develop/ui/compose/components), [Modifiers list](https://developer.android.com/develop/ui/compose/modifiers-list), [Resources](https://developer.android.com/develop/ui/compose/resources), [RecyclerView migration](https://developer.android.com/develop/ui/compose/migrate/migration-scenarios/recycler-view), [CoordinatorLayout migration](https://developer.android.com/develop/ui/compose/migrate/migration-scenarios/coordinator-layout).

Material rows assume Compose Material 3. Mark experimental APIs with `@OptIn` and check each component page before use.

## Layout containers

| Views | Compose | What changes |
|---|---|---|
| `ConstraintLayout` | Nested `Row` / `Column` / `Box` first | Flat hierarchies were a View performance concern; nesting is not a problem in Compose. Use Compose `ConstraintLayout` (`androidx.constraintlayout:constraintlayout-compose`, versioned separately) only when relations are genuinely two-dimensional; it supports `createRefs` / `constrainAs`, guidelines, barriers, chains, and a `ConstraintSet` to swap constraints |
| `LinearLayout` with `orientation="vertical"` | `Column` | Main-axis gravity and spacing go to `verticalArrangement`, cross-axis gravity to `horizontalAlignment` |
| `LinearLayout` with `orientation="horizontal"` | `Row` | `horizontalArrangement` and `verticalAlignment` |
| Children with `layout_weight` | `Modifier.weight(f)` | Only available in `RowScope` and `ColumnScope` |
| `FrameLayout` | `Box` | Later children draw over earlier ones. Position with `contentAlignment` or a child's `Modifier.align`; `Modifier.matchParentSize()` sizes a child to the `Box` without affecting the `Box` size |
| `RelativeLayout` | `Box`, `Row` and `Column` combined | Rewrite "toEndOf / below" rules as nesting |
| `FlexboxLayout`, wrapping `ChipGroup` | `FlowRow` / `FlowColumn` | `maxItemsInEachRow` / `maxItemsInEachColumn` limit items per line |
| Static `GridLayout` / `TableLayout` | `Column` of `Row`s with weights | Data-driven grids use `LazyVerticalGrid` |
| Custom `ViewGroup` measuring its children | `Layout` composable, or `BoxWithConstraints` when content depends on available space | |
| `CoordinatorLayout` + `AppBarLayout` | `Scaffold` with `topBar` and a `TopAppBarScrollBehavior` | `TopAppBarDefaults.enterAlwaysScrollBehavior()` (or `exitUntilCollapsedScrollBehavior()`, `pinnedScrollBehavior()`); add `Modifier.nestedScroll(scrollBehavior.nestedScrollConnection)` to the `Scaffold` and apply its `PaddingValues` to the body |
| `DrawerLayout` + `NavigationView` | `ModalNavigationDrawer` with `ModalDrawerSheet` and `NavigationDrawerItem` | |
| `Space` | `Spacer` with a size modifier | Uniform gaps are simpler as `Arrangement.spacedBy` |

## Scrolling, lists and paging

| Views | Compose | What changes |
|---|---|---|
| `RecyclerView` + `LinearLayoutManager` | `LazyColumn` / `LazyRow` with `items()` | One item composable replaces `onCreateViewHolder` and `onBindViewHolder`. Pass `key` so scroll position survives data changes and `contentType` where the adapter had view types |
| `GridLayoutManager` | `LazyVerticalGrid` / `LazyHorizontalGrid` | `GridCells.Fixed(n)` or `GridCells.Adaptive(minSize)` |
| `StaggeredGridLayoutManager` | `LazyVerticalStaggeredGrid` / `LazyHorizontalStaggeredGrid` | |
| `ScrollView` / `NestedScrollView` | `Column(Modifier.verticalScroll(rememberScrollState()))` | Composes every child up front; switch to `LazyColumn` for long or data-driven content |
| `HorizontalScrollView` | `Row(Modifier.horizontalScroll(rememberScrollState()))` | |
| `ItemDecoration` | Decoration drawn inside the list content | There is no decoration concept; add `HorizontalDivider` between items, `contentPadding` and `Arrangement.spacedBy` for spacing |
| `ItemAnimator` | `Modifier.animateItem()` on the item's root | Needs stable keys. The RecyclerView migration page still names `animateItemPlacement`; the Lists guide uses `animateItem` |
| Section header adapters | `stickyHeader { }` | |
| `PagingDataAdapter` | `collectAsLazyPagingItems()` | See `compose-lists` |
| `ViewPager2` | `HorizontalPager` / `VerticalPager` with `rememberPagerState(pageCount = { n })` | Pages compose lazily; `beyondViewportPageCount` keeps extra pages composed. Read `currentPage` / `settledPage`, and observe changes with `snapshotFlow` |
| `TabLayout` + `TabLayoutMediator` | `PrimaryTabRow` / `SecondaryTabRow` with `Tab` | Drive `selectedTabIndex` from the pager state; `animateScrollToPage` on click |
| `SwipeRefreshLayout` | `PullToRefreshBox(isRefreshing, onRefresh)` | `isRefreshing` comes from UI state |
| Swipe with `ItemTouchHelper` | `SwipeToDismissBox` | |
| A list inside a same-direction scroll container | One lazy list with several item types | A `LazyColumn` without a fixed height inside `verticalScroll` throws `IllegalStateException` |

## Text and input

| Views | Compose | What changes |
|---|---|---|
| `TextView` | `Text` | `textAppearance` becomes `style = MaterialTheme.typography.<role>`; text from `stringResource` |
| `maxLines` + `ellipsize="end"` | `maxLines` + `overflow = TextOverflow.Ellipsis` | |
| `ellipsize="marquee"` | `Modifier.basicMarquee()` | |
| `textIsSelectable` | Wrap in `SelectionContainer` | Exclude parts with `DisableSelection` |
| Spannables, `autoLink`, `ClickableSpan` | `buildAnnotatedString` with `SpanStyle`, and `LinkAnnotation.Url` for links | |
| `fontFamily="@font/..."` | `FontFamily(Font(R.font.name, FontWeight.Normal))` in `Typography` | |
| `EditText` / `TextInputLayout` | `TextField` / `OutlinedTextField` with `state = rememberTextFieldState()` | Google recommends the state-based overloads: `TextFieldState` replaces `onValueChange` and may live in the ViewModel. Hint and error text become `label`, `placeholder`, `supportingText` and `isError` |
| `singleLine` / `maxLines` / `minLines` | `lineLimits = TextFieldLineLimits.SingleLine` or `MultiLine(...)` | |
| `inputType` / `imeOptions` + `OnEditorActionListener` | `keyboardOptions = KeyboardOptions(keyboardType = ..., imeAction = ...)` and `onKeyboardAction` | |
| `inputType="textPassword"` | `SecureTextField` / `OutlinedSecureTextField` | |
| `InputFilter`, formatting `TextWatcher` | `inputTransformation` (edits input) / `outputTransformation` (display only) | |
| `autofillHints` | `Modifier.semantics { contentType = ContentType.Username }` | |
| `Spinner`, `AutoCompleteTextView`, exposed dropdown menu | `ExposedDropdownMenuBox` + `ExposedDropdownMenu` + `DropdownMenuItem` | The field takes `Modifier.menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable)`, or `PrimaryEditable` when typing filters options |
| `SearchView` | `SearchBar` with `SearchBarDefaults.InputField` | Experimental |

## Images and drawing

| Views | Compose | What changes |
|---|---|---|
| `ImageView` with a drawable | `Image(painterResource(R.drawable.x), contentDescription)` | `painterResource` loads vector, bitmap and color drawables |
| `ImageView` filled by Glide or Picasso | `AsyncImage` from Coil | See `compose-images` |
| `scaleType` | `contentScale` | `centerCrop` → `ContentScale.Crop`, `fitCenter` → `Fit` (the default), `fitXY` → `FillBounds`, `centerInside` → `Inside`, `center` → `None` |
| `tint` | `Icon(tint = ...)`, or `Image(colorFilter = ColorFilter.tint(color))` | |
| `ShapeableImageView`, outline clipping | `Modifier.clip(shape)` | |
| `ImageButton` | `IconButton { Icon(...) }` | |
| `AnimatedVectorDrawable` | `AnimatedImageVector.animatedVectorResource` + `rememberAnimatedVectorPainter(atEnd)` | |
| `onDraw` override | `Canvas`, `Modifier.drawBehind`, `Modifier.drawWithContent` | |
| `WebView`, `AdView`, `SurfaceView` players, `MapView` | `AndroidView`, or Maps Compose for Google Maps | See `SKILL.md` section 4 |

## Material components

### Actions and selection

| Views | Compose | What changes |
|---|---|---|
| `MaterialButton` styles | `Button`, `FilledTonalButton`, `OutlinedButton`, `ElevatedButton`, `TextButton` | Pick by the `Widget.Material3.Button.*` style in use |
| `MaterialButtonToggleGroup` | `SingleChoiceSegmentedButtonRow` / `MultiChoiceSegmentedButtonRow` with `SegmentedButton` | |
| `FloatingActionButton`, `ExtendedFloatingActionButton` | Same names, plus `SmallFloatingActionButton` / `LargeFloatingActionButton` | Pass to `Scaffold(floatingActionButton = ...)` |
| `Chip` | `AssistChip`, `FilterChip`, `InputChip`, `SuggestionChip`; `Elevated*` variants | `FilterChip` needs `selected` from state |
| `CheckBox` | `Checkbox(checked, onCheckedChange)` | Parent checkboxes use `TriStateCheckbox` with `ToggleableState` |
| `SwitchMaterial` / `MaterialSwitch` | `Switch(checked, onCheckedChange)` | |
| `RadioGroup` of `RadioButton`s | `Column(Modifier.selectableGroup())` with rows using `Modifier.selectable(selected, onClick, role = Role.RadioButton)` | Set the inner `RadioButton(onClick = null)` so the row is the single touch target |
| A row that toggles a checkbox or switch | `Modifier.toggleable(value, onValueChange, role = ...)` on the row | The inner control gets `onCheckedChange = null` |
| `SeekBar` / `Slider` | `Slider(value, onValueChange, valueRange, steps)`; `RangeSlider` for two thumbs | |

### Feedback, containers and overlays

| Views | Compose | What changes |
|---|---|---|
| `ProgressBar`, `LinearProgressIndicator`, `CircularProgressIndicator` | `LinearProgressIndicator` / `CircularProgressIndicator` | Pass `progress = { value }` for determinate; omit it for indeterminate |
| `Snackbar.make(...)` | `SnackbarHostState.showSnackbar()` in a coroutine, with `Scaffold(snackbarHost = { SnackbarHost(state) })` | The message itself belongs in UI state (`android-viewmodel`) |
| `Toast` | `Toast.makeText(LocalContext.current, ...)` | Unchanged API |
| `TooltipCompat` | `TooltipBox` with `PlainTooltip` or `RichTooltip` | |
| `CardView` / `MaterialCardView` | `Card`, `ElevatedCard`, `OutlinedCard` | Use the `onClick` overload for clickable cards |
| `AlertDialog`, `DialogFragment` | `AlertDialog(onDismissRequest, confirmButton, ...)`, or `Dialog` for custom content | Shown while a state flag is true |
| `BottomSheetDialogFragment` | `ModalBottomSheet` with `rememberModalBottomSheetState()` | Persistent sheets use `BottomSheetScaffold` |
| `MaterialDatePicker` | `DatePickerDialog` containing `DatePicker(rememberDatePickerState())`; `TimePicker` | Experimental |
| `PopupMenu`, overflow menus | `DropdownMenu` + `DropdownMenuItem` | Place the menu and its trigger in the same `Box` |
| Two-line list row layouts | `ListItem(headlineContent, supportingContent, leadingContent, trailingContent)` | |
| Divider views, `MaterialDivider` | `HorizontalDivider` / `VerticalDivider` | A `VerticalDivider` in a `Row` needs a bounded height, for example `Modifier.height(IntrinsicSize.Min)` on the `Row` |

### App structure

| Views | Compose | What changes |
|---|---|---|
| `Toolbar`, `MaterialToolbar`, action bar | `TopAppBar`, `CenterAlignedTopAppBar`, `MediumTopAppBar`, `LargeTopAppBar` in `Scaffold(topBar = ...)` | Menu items become `actions`; the up arrow becomes `navigationIcon` |
| `BottomAppBar` | `BottomAppBar` | |
| `BottomNavigationView` | `NavigationBar` + `NavigationBarItem`, or `NavigationSuiteScaffold` to adapt to larger windows | See `compose-adaptive-layouts` |
| `NavigationRailView` | `NavigationRail` | |

## Attributes to modifiers and parameters

Modifier order matters: each modifier wraps the ones after it, so `padding` before `background` leaves the padding unpainted, and `padding` before `clickable` shrinks the touch area.

### Size

| XML | Compose |
|---|---|
| Fixed `dp` size | `Modifier.width()`, `height()`, `size()`; `requiredSize()` ignores the parent's constraints |
| `wrap_content` | Nothing; composables wrap their content by default |
| `match_parent` | `fillMaxWidth()`, `fillMaxHeight()`, `fillMaxSize()` |
| `0dp` + `layout_weight` | `Modifier.weight()` |
| `minWidth` / `minHeight` / `maxWidth` / `maxHeight` | `widthIn(min, max)` / `heightIn(min, max)` |
| `layout_constraintDimensionRatio` | `Modifier.aspectRatio(ratio)` |

### Placement and spacing

| XML | Compose |
|---|---|
| `gravity` on a parent | `Arrangement` on the main axis, `Alignment` on the cross axis, `contentAlignment` on `Box` |
| `layout_gravity` on a child | `Modifier.align()` inside `Box`, `Row` or `Column` |
| `padding` | `Modifier.padding()`, or the component's `contentPadding` |
| `layout_margin` | No margins: padding placed earlier in the chain, or parent `Arrangement.spacedBy` / `contentPadding` |
| `translationX` / `translationY` | `Modifier.offset { IntOffset(x, y) }` |
| Draw order among siblings (`translationZ`, `elevation`) | `Modifier.zIndex()` |
| `fitsSystemWindows` | `Scaffold` content padding, `Modifier.safeDrawingPadding()` or `windowInsetsPadding(...)` |

### Appearance

| XML | Compose |
|---|---|
| `background` color or shape drawable | `Modifier.background(color, shape)` with a theme color |
| Shape `<stroke>` | `Modifier.border(width, color, shape)` or a component's `border` parameter |
| `elevation` | The component's `elevation` / `shadowElevation` / `tonalElevation`, or `Modifier.shadow(elevation, shape)` |
| `alpha` | `Modifier.alpha()`; `graphicsLayer { alpha = ... }` when animated |
| `rotation`, `scaleX` / `scaleY` | `Modifier.rotate()`, `Modifier.scale()`, or `graphicsLayer` |
| `animateLayoutChanges` | `Modifier.animateContentSize()` for size changes; `AnimatedVisibility` / `AnimatedContent` for appearing or swapped content |

### State and interaction

| XML | Compose |
|---|---|
| `visibility="gone"` | Skip the call: `if (visible) { ... }`; `AnimatedVisibility` to animate it |
| `visibility="invisible"` | The slot must keep its size, so keep the composable but draw nothing (`Modifier.alpha(0f)`), and also remove it from semantics and input; alpha alone leaves it focusable and clickable |
| `enabled` | The component's `enabled` parameter |
| `OnClickListener`, `?selectableItemBackground` | The component's `onClick`, or `Modifier.clickable { }`, which also draws the default indication |
| `OnLongClickListener` | `Modifier.combinedClickable(onClick = ..., onLongClick = ...)` |
| `focusable` | `Modifier.focusable()` |
| `contentDescription` | `Image` / `Icon` `contentDescription` (`null` when decorative), or `Modifier.semantics { contentDescription = ... }` |
| `importantForAccessibility="no"` | `Modifier.clearAndSetSemantics { }` |
| `accessibilityHeading` | `Modifier.semantics { heading() }` |
| `screenReaderFocusable` on a group | `Modifier.semantics(mergeDescendants = true) { }` |
| `android:id` used by tests | `Modifier.testTag()`; set `testTagsAsResourceId = true` for UiAutomator |

## Resources, styles and layout reuse

| XML | Compose |
|---|---|
| `@string`, `<plurals>` | `stringResource()`, `pluralStringResource()` |
| `@dimen` | `dimensionResource()` |
| `@color`, color state lists | `MaterialTheme.colorScheme` roles; `colorResource()` only for static colors, because it flattens state lists |
| `?attr/colorPrimary`, `?attr/textAppearanceBodyMedium` | `MaterialTheme.colorScheme.primary`, `MaterialTheme.typography.bodyMedium` |
| `style="@style/PrimaryAction"` | A named composable (`PrimaryActionButton(...)`) or the component's `*Defaults` colors, shapes and elevation |
| A layout file reused with `<include>` / `<merge>` | A composable function with parameters, called at each former include site |
| `ViewStub` inflated on demand | Conditional composition; nothing composes until the branch runs |
| `<fragment>` / `FragmentContainerView` child | A composable; `AndroidFragment<T>()` only while the Fragment still exists |
| Data binding `@{...}` | Reads of UI state fields; two-way `@={...}` becomes state plus an event lambda, or `TextFieldState` |
| `@BindingAdapter` | A composable parameter or a `Modifier` extension |
| `layout-sw600dp` and other size qualifiers | Window size classes in code (`compose-adaptive-layouts`) |
