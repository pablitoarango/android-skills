---
name: compose-lists
description: "Lazy lists, grids and pagers per Google's docs: keys, contentType, item animations, Paging, scroll state, list pitfalls. Use for scrolling lists, grids, carousels, pagers, or RecyclerView and ViewPager replacements, and when items jump or swap state, scroll position resets, or nested scrolling crashes with infinity maximum height constraints."
---

# Compose Lists, Grids and Pagers

Sources of truth: [Lists and grids](https://developer.android.com/develop/ui/compose/lists), [Pager](https://developer.android.com/develop/ui/compose/layouts/pager), [Performance best practices](https://developer.android.com/develop/ui/compose/performance/bestpractices).

## 1. Pick the container

| Content | Composable |
|---|---|
| Vertical / horizontal list | `LazyColumn` / `LazyRow` |
| Uniform grid | `LazyVerticalGrid` / `LazyHorizontalGrid` with `GridCells.Fixed(n)` or `GridCells.Adaptive(minSize)` |
| Items of different sizes | `LazyVerticalStaggeredGrid` / `LazyHorizontalStaggeredGrid` |
| One full page at a time | `HorizontalPager` / `VerticalPager` (Compose Foundation) |
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

- **Keys** keep item state (including `rememberSaveable`) attached to the right item when the list changes, preserve scroll position, and enable `animateItem()`. Keys must be types that can be saved in a `Bundle` (primitives, `String`, enums, `Parcelable`).
- **`contentType`** lets Compose reuse compositions only between items of the same kind.
- **Spacing**: use `contentPadding` for padding around the content and `Arrangement.spacedBy` between items, not padding on each item.
- **Animations**: `Modifier.animateItem()` on the item root animates insertions, removals and moves. It requires keys.
- **Dividers**: add a `HorizontalDivider` inside the item or as its own `item`; there is no item decoration API.

## 3. Pitfalls

- **Work in items**: sort, filter and map in the ViewModel. At most `remember(items) { ... }` for purely presentational transforms.
- **0-pixel items**: give asynchronously loaded content (images) a fixed or placeholder size, or the list composes far more items than are visible and then jumps.
- **Nested scrolling in the same direction**: never put a `LazyColumn` inside a `Column` with `verticalScroll`, or a `LazyColumn` inside a `LazyColumn`, without a fixed height. Use one lazy container with `item { }` blocks for headers and footers. Nesting different directions (a `LazyRow` inside a `LazyColumn`) is fine.
- **Several elements in one `item`**: they compose and scroll as a unit and break `scrollToItem`. Put each logical element in its own `item`; a small divider alongside an item is the exception.
- **Frequently changing item state**: pass lambdas or use lambda-based modifiers so scrolling does not recompose items (see `compose-performance`).

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

Expose `Flow<PagingData<T>>` from the ViewModel as its own property (not inside UI state) and collect it in the UI.

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

- Use `HorizontalPager` / `VerticalPager` from `androidx.compose.foundation.pager`. The Accompanist pager is deprecated.
- Pages are composed lazily; increase the off-screen page count only when measured jank requires it.
- Change pages from a coroutine: `scope.launch { pagerState.animateScrollToPage(n) }`.
- Observe page changes with `snapshotFlow { pagerState.currentPage }`; use `settledPage` when you only care about where the user stopped.
- Build indicators from `pagerState.pageCount` and `pagerState.currentPage`.

## 7. Migrating from RecyclerView and ViewPager

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

## 8. Checklist

- [ ] Every `items` call has a stable, Bundle-savable `key`.
- [ ] Mixed item kinds declare `contentType`.
- [ ] No sorting or filtering inside items.
- [ ] Async content has a size before it loads.
- [ ] Same-direction nested scrolling has a fixed-size child; otherwise flatten it into one lazy container.
- [ ] Scroll-derived values use `derivedStateOf` or `snapshotFlow`.
- [ ] Pagers come from Compose Foundation.
