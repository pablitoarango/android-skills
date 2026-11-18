---
name: compose-lists
description: "Lazy lists, grids and pagers per Google's docs: keys, contentType, item animations, Paging, scroll state, list pitfalls. Use for scrolling lists, grids, carousels, pagers, or RecyclerView and ViewPager replacements, and when items jump or swap state, scroll position resets, or nested scrolling crashes with infinity maximum height constraints."
---

# Compose Lists, Grids and Pagers

Sources of truth: [Lists and grids](https://developer.android.com/develop/ui/compose/lists), [Pager](https://developer.android.com/develop/ui/compose/layouts/pager), [Carousel](https://developer.android.com/develop/ui/compose/components/carousel), [Load and display paged data](https://developer.android.com/topic/libraries/architecture/paging/v3-paged-data), [Performance best practices](https://developer.android.com/develop/ui/compose/performance/bestpractices).

## 1. Pick the container

| Content | Composable |
|---|---|
| Vertical / horizontal list | `LazyColumn` / `LazyRow` |
| Uniform grid | `LazyVerticalGrid` / `LazyHorizontalGrid` with `GridCells.Fixed(n)` or `GridCells.Adaptive(minSize)` |
| Items of different sizes | `LazyVerticalStaggeredGrid` / `LazyHorizontalStaggeredGrid` |
| One full page at a time | `HorizontalPager` / `VerticalPager` (Compose Foundation) |
| Browsable row of visual items (photos, thumbnails) | `HorizontalMultiBrowseCarousel` / `HorizontalUncontainedCarousel` (Material 3) |
| A few items that always fit | `Column` / `Row`, with `verticalScroll` / `horizontalScroll` if needed |

Lazy containers compose only visible items; use them for anything that can grow.

## 2. Items

Always pass a **stable, unique `key`**, and a `contentType` when the list mixes item kinds.

```kotlin
LazyColumn(
    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
    verticalArrangement = Arrangement.spacedBy(8.dp),
) {
    item(key = "header", contentType = "header") { FeedHeader() }
    items(
        items = feedItems,
        key = { it.id },
        contentType = { it.type },
    ) { item ->
        FeedItemRow(item = item, onClick = { onItemClick(item.id) }, modifier = Modifier.animateItem())
    }
}
```

- **Keys** keep item state (including `rememberSaveable`) attached to the right item when the list changes, preserve scroll position, and enable `animateItem()`. Keys must be types that can be saved in a `Bundle` (primitives, `String`, enums, `Parcelable`). Never use the list index or `hashCode()` as a key.
- **`contentType`** lets Compose reuse compositions only between items of the same kind.
- **Spacing**: use `contentPadding` for padding around the content and `Arrangement.spacedBy` between items, not padding on each item.
- **Animations**: `Modifier.animateItem()` on the item root animates insertions, removals and moves. It requires keys.
- **Dividers**: put the `HorizontalDivider` inside the item it follows so it does not shift scroll indexes; there is no item decoration API.
- **Sticky headers**: use `stickyHeader { }` in a `LazyColumn`. Group the data in the ViewModel, then emit one `stickyHeader` followed by its `items` per group.

## 3. Pitfalls

- **Work in items**: sort, filter and map in the ViewModel. At most `remember(items) { ... }` for purely presentational transforms.
- **Index lookups**: use `itemsIndexed` when an item needs its position. Calling `list.indexOf(item)` inside `items` makes layout quadratic.
- **Shared reads**: collect shared flows and read `CompositionLocal`s such as `LocalContext.current` once above the lazy layout and pass the values down, not in every item.
- **0-pixel items**: give asynchronously loaded content (images) a fixed or placeholder size, or the list composes far more items than are visible and then jumps.
- **Nested scrolling in the same direction**: never put a `LazyColumn` inside a `Column` with `verticalScroll`, or a `LazyColumn` inside a `LazyColumn`, without a fixed height. Use one lazy container with `item { }` blocks for headers and footers. Nesting different directions (a `LazyRow` inside a `LazyColumn`) is fine.
- **Several elements in one `item`**: they compose and scroll as a unit and interfere with `scrollToItem`. Put each logical element in its own `item`; a divider inside the item it follows is the exception.
- **Frequently changing item state**: pass lambdas or use lambda-based modifiers so scrolling does not recompose items (see `compose-performance`).
- **Large items**: lazy layouts prefetch through a `LazyLayoutCacheWindow` whose ahead window defaults to 10-50% of the viewport. If items taller than half the viewport (full-bleed cards, media posts) appear late while scrolling, pass a larger `LazyLayoutCacheWindow(aheadFraction = ...)`. In the current stable release that goes through `rememberLazyListState(cacheWindow = ...)`, which is `@ExperimentalFoundationApi`. Do not use the deprecated `LazyListPrefetchStrategy`.

## 4. Scroll state

```kotlin
val listState = rememberLazyListState()
val scope = rememberCoroutineScope()
val showScrollToTop by remember { derivedStateOf { listState.firstVisibleItemIndex > 0 } }

Box {
    LazyColumn(state = listState) { /* items */ }
    AnimatedVisibility(visible = showScrollToTop) {
        ScrollToTopButton(onClick = { scope.launch { listState.animateScrollToItem(0) } })
    }
}
```

- Read scroll position through `derivedStateOf` or `snapshotFlow`, never directly in composition (see `compose-side-effects`).
- Hoist `LazyListState` to the lowest composable that needs to read or drive it.

## 5. Paging

Build the `Pager` in the ViewModel and expose its flow with `cachedIn(viewModelScope)`. Without `cachedIn` the `PagingData` cannot be collected again, for example after a configuration change. Keep the flow as its own ViewModel property, outside the UI state class (stricter than Google).

```kotlin
val messages: Flow<PagingData<Message>> = Pager(PagingConfig(pageSize = 20)) { messagePagingSource() }
    .flow
    .cachedIn(viewModelScope)
```

```kotlin
@Composable
fun MessageList(messages: Flow<PagingData<Message>>) {
    val lazyPagingItems = messages.collectAsLazyPagingItems()
    LazyColumn {
        items(
            count = lazyPagingItems.itemCount,
            key = lazyPagingItems.itemKey { it.id },
            contentType = lazyPagingItems.itemContentType { "message" },
        ) { index ->
            val message = lazyPagingItems[index]
            if (message != null) MessageRow(message) else MessagePlaceholder()
        }
    }
}
```

- Size `MessagePlaceholder()` like a loaded row. With a `RemoteMediator`, small or missing placeholders keep the screen from ever filling, and Paging keeps fetching pages.

## 6. Pager

```kotlin
val pagerState = rememberPagerState(pageCount = { pages.size })
HorizontalPager(
    state = pagerState,
    key = { pages[it].id },
    contentPadding = PaddingValues(horizontal = 32.dp),
) { page ->
    PageContent(pages[page])
}
```

- Use `HorizontalPager` / `VerticalPager` from `androidx.compose.foundation.pager`. The Accompanist pager is deprecated and removed.
- Pages are composed lazily. To keep more pages composed offscreen, set `beyondViewportPageCount` above 0.
- Change pages from a coroutine: `scope.launch { pagerState.animateScrollToPage(n) }`.
- Observe page changes with `snapshotFlow { pagerState.currentPage }`; use `settledPage` when you only care about where the user stopped.
- Build indicators from `pagerState.pageCount` and `pagerState.currentPage`.

## 7. Carousel

For a Material browsing row of visual items, use the Material 3 carousels rather than a hand-built `LazyRow` or pager.

```kotlin
HorizontalMultiBrowseCarousel(
    state = rememberCarouselState { photos.size },
    preferredItemWidth = 186.dp,
    itemSpacing = 8.dp,
    contentPadding = PaddingValues(horizontal = 16.dp),
) { index ->
    PhotoImage(photos[index], Modifier.height(205.dp).maskClip(MaterialTheme.shapes.extraLarge))
}
```

- `HorizontalMultiBrowseCarousel` mixes item sizes around `preferredItemWidth`. `HorizontalUncontainedCarousel` gives every item the same `itemWidth` and lets the last one run past the edge.
- Clip items with `Modifier.maskClip` so their shape follows the size the carousel gives them.

## 8. Migrating from RecyclerView and ViewPager

| View system | Compose |
|---|---|
| `RecyclerView` + `LinearLayoutManager` | `LazyColumn` / `LazyRow` |
| `GridLayoutManager` | `LazyVerticalGrid` |
| `StaggeredGridLayoutManager` | `LazyVerticalStaggeredGrid` |
| `ViewHolder` + `onBindViewHolder` | Item composable taking item data |
| `DiffUtil` | Not needed; use `key` |
| `ItemDecoration` | Dividers and `Arrangement.spacedBy` |
| `ItemAnimator` | `Modifier.animateItem()` |
| `ViewPager2` | `HorizontalPager` |

## 9. Checklist

- [ ] Every `items` call has a stable, Bundle-savable `key` that is not an index or `hashCode()`.
- [ ] Mixed item kinds declare `contentType`.
- [ ] No sorting, filtering or `indexOf` inside items.
- [ ] Async content and Paging placeholders have a size before they load.
- [ ] Same-direction nested scrolling has a fixed-size child; otherwise flatten it into one lazy container.
- [ ] Scroll-derived values use `derivedStateOf` or `snapshotFlow`.
- [ ] Paging flows use `cachedIn(viewModelScope)`.
- [ ] Pagers come from Compose Foundation.
