---
name: compose-images
description: "Images in Compose per Google's image docs and Coil 3: painterResource vs AsyncImage, dependencies, sizing and downsampling, lists, painter state, the ImageLoader with OkHttp and caching, previews, tests. Use when loading network, file or resource images, and when URLs never load, images use too much memory, lists jump as images arrive, or previews show no image."
---

# Loading Images in Compose

Sources of truth: [Loading images](https://developer.android.com/develop/ui/compose/graphics/images/loading), [Optimizing bitmap images](https://developer.android.com/develop/ui/compose/graphics/images/optimization), [Lists and grids](https://developer.android.com/develop/ui/compose/lists), and Coil's [Getting started](https://coil-kt.github.io/coil/getting_started/), [Compose](https://coil-kt.github.io/coil/compose/), [Image loaders](https://coil-kt.github.io/coil/image_loaders/), [Network images](https://coil-kt.github.io/coil/network/), [Testing](https://coil-kt.github.io/coil/testing/) and [Upgrading to Coil 3](https://coil-kt.github.io/coil/upgrading_to_coil3/) pages.

Related skills: `compose-lists`, `compose-performance`, `compose-accessibility`, `compose-testing`, `android-retrofit` (the shared OkHttp client).

## 1. Pick the API

| Image source | API |
|---|---|
| App resource: vector drawable, PNG, JPEG, WebP | `Image(painter = painterResource(R.drawable.x), contentDescription = ...)`, or `Icon(...)` for tinted icons |
| URL, file, content URI, anything that must be fetched or decoded off the main thread | An image loading library. Google names Coil for Kotlin-first projects and Glide for Java projects; this skill uses Coil 3 |

Image libraries cache in memory and on disk, downsample to the target size, and cancel work that leaves the screen. Do not decode bitmaps by hand in composables.

## 2. Dependencies

Coil 3 lives under the `io.coil-kt.coil3` group and the `coil3` package. A Compose app on Android needs the Compose artifact plus exactly one network artifact:

```toml
[libraries]
coil-bom = { module = "io.coil-kt.coil3:coil-bom", version.ref = "coil" }
coil-compose = { module = "io.coil-kt.coil3:coil-compose" }
coil-network-okhttp = { module = "io.coil-kt.coil3:coil-network-okhttp" }
```

- Without a network artifact, Coil 3 cannot load `http(s)` URLs; requests fail. Use `coil-network-okhttp` on Android (Ktor variants exist for multiplatform).
- Coil 2 (`io.coil-kt`, package `coil`) is the previous major version. Do not mix it with Coil 3 in new code. Migrating: `ImageLoaderFactory` became `SingletonImageLoader.Factory`, `AsyncImagePainter.state` became a `StateFlow`, and `android.resource://` URIs using resource names no longer load (pass `R.drawable.x`).
- Since 3.2.0, `coil-compose` requires Java 11 bytecode.
- Other artifacts: `coil-svg`, `coil-gif`, `coil-video`, `coil-network-cache-control`, `coil-test`. `coil-core` and `coil-compose-core` omit the singleton for apps or libraries that manage their own `ImageLoader`.
- Current versions: [Coil changelog](https://coil-kt.github.io/coil/changelog/).

## 3. AsyncImage

`AsyncImage` accepts the same arguments as `Image`, plus `placeholder`, `error` and `fallback` painters and `onLoading`/`onSuccess`/`onError` callbacks. `model` is either the data (URL string, `Uri`, `File`, resource ID) or a full `ImageRequest`.

```kotlin
@Composable
fun AuthorAvatar(author: Author, modifier: Modifier = Modifier) {
    AsyncImage(
        model = author.avatarUrl,
        contentDescription = stringResource(R.string.author_avatar, author.name),
        modifier = modifier
            .size(40.dp)
            .clip(CircleShape),
        contentScale = ContentScale.Crop,
        fallback = painterResource(R.drawable.avatar_default),
    )
}
```

- `placeholder` shows while loading, `error` when the request fails, and `fallback` when the data is `null`. `fallback` defaults to the `error` painter.
- Build an `ImageRequest` only when you need request options: `ImageRequest.Builder(LocalPlatformContext.current).data(url).crossfade(true).build()`.
- `AsyncImage` resolves the load size from its layout constraints and `contentScale`. It is the right default because it downsamples correctly.
- Pass the URL or resource ID into your own image composables, not a `Painter`. `Painter` is not a stable type, so the receiving composable cannot skip recomposition.

## 4. Size and memory

Decoded bitmaps are far larger than the compressed files. Google's optimization guide asks for:

- **Bounded size before the request starts.** Give remote image composables a size (`Modifier.size`, `fillMaxWidth().aspectRatio(16f / 9f)`, a fixed height). With `wrapContentSize` or otherwise unconstrained dimensions the loader cannot infer a target and falls back to the full original image.
- **Server-side resizing where the backend supports it.** Request the dimensions you display; with Coil this is done by an interceptor that rewrites the URL with the target size.
- **A lighter pixel format when transparency is not needed.** `ImageRequest.Builder.bitmapConfig(Bitmap.Config.RGB_565)` or `allowRgb565(true)` halves memory compared with `ARGB_8888`.
- **No padding baked into the image.** Pad the container composable instead.
- **Vectors for geometric art** and density-specific resources for bundled bitmaps. Keep large images out of the APK; download them when needed.

Coil 3 caps decoded images at 4096 x 4096 by default to prevent accidental OOMs (`maxBitmapSize` changes it).

## 5. Lists and grids

- Items whose images arrive asynchronously must already have their final size. A 0-pixel item makes the lazy layout compose far too many items on the first pass, then drop them and jump when the images land. Use a fixed size or aspect ratio, and keep it identical before and after loading.
- `AsyncImage` with `placeholder`/`error` painters is the list default. `SubcomposeAsyncImage` uses subcomposition, which Coil documents as slower and possibly unsuitable for `LazyList`s; measure before using it in scrolling content.
- Images whose modifiers are the same for every item can share a chain stored outside the item composable (see `compose-performance`).
- In staggered grids, Google's sample bounds only the width (`fillMaxWidth().wrapContentHeight()`), which is enough for downsampling. Items still grow when the image arrives; if the API provides image dimensions, set `aspectRatio` from them so items keep their size.

## 6. When you need the load state or a Painter

| Need | API |
|---|---|
| Standard image with placeholder or error painters | `AsyncImage` |
| A `Painter` for `Canvas`, `Icon` or a custom layout; observing `AsyncImagePainter.state`; calling `restart()` | `rememberAsyncImagePainter` |
| Composable slots for loading, success and error, with a correct state on the very first frame | `SubcomposeAsyncImage` |

`rememberAsyncImagePainter` knows nothing about where the painter is drawn and loads the original image size unless you give it a size resolver. Its state is also `Empty` in the first composition, even for a memory-cache hit. Pair it with `rememberConstraintsSizeResolver()` applied to the layout that draws it:

```kotlin
@Composable
fun HeroBanner(url: String, modifier: Modifier = Modifier) {
    val sizeResolver = rememberConstraintsSizeResolver()
    val painter = rememberAsyncImagePainter(
        ImageRequest.Builder(LocalPlatformContext.current)
            .data(url)
            .size(sizeResolver)
            .build(),
    )
    val state by painter.state.collectAsState()

    Box(modifier.aspectRatio(16f / 9f).then(sizeResolver)) {
        Image(painter, contentDescription = null, modifier = Modifier.matchParentSize(), contentScale = ContentScale.Crop)
        if (state is AsyncImagePainter.State.Loading) {
            CircularProgressIndicator(Modifier.align(Alignment.Center))
        }
    }
}
```

- `crossfade(true)` is the only built-in transition that works in Compose. For custom animations, observe `painter.state` and animate on `State.Success`, skipping the animation when `result.dataSource` is `DataSource.MEMORY_CACHE`.

## 7. The ImageLoader

An `ImageLoader` owns the memory cache, the disk cache and the HTTP client, so an app should have exactly one. `coil-compose` overloads use Coil's lazily created singleton. Configure it once, as early as possible, in one of these ways:

- Android apps: implement `SingletonImageLoader.Factory` on the `Application` (shown below).
- `SingletonImageLoader.setSafe { }` in `Application.onCreate`, or `setSingletonImageLoaderFactory { }` at the root composable (best for Compose Multiplatform).
- Never build an `ImageLoader` inside a composable or per screen. Libraries must not set the singleton; they create their own loader on `coil-core`.

```kotlin
@HiltAndroidApp
class App : Application(), SingletonImageLoader.Factory {
    @Inject lateinit var okHttpClient: dagger.Lazy<OkHttpClient>

    override fun newImageLoader(context: PlatformContext): ImageLoader =
        ImageLoader.Builder(context)
            .components {
                add(OkHttpNetworkFetcherFactory(callFactory = { okHttpClient.get() }))
            }
            .crossfade(true)
            .build()
}
```

- Reusing the app's `OkHttpClient` shares its connection pool, dispatcher and auth interceptors. Derive image-specific clients with `newBuilder()`.
- Caches: `memoryCache { MemoryCache.Builder().maxSizePercent(context, 0.25).build() }` and `diskCache { DiskCache.Builder().directory(context.cacheDir.resolve("image_cache")).maxSizePercent(0.02).build() }` tune the defaults.
- Coil 3 ignores `Cache-Control` response headers and always writes to the disk cache. Add `coil-network-cache-control` and pass `cacheStrategy = { CacheControlCacheStrategy() }` to `OkHttpNetworkFetcherFactory` when the server's headers must be respected.
- Per-request headers: `ImageRequest.Builder.httpHeaders(NetworkHeaders.Builder().set(...).build())`; headers for every request go in an OkHttp interceptor.
- Preload: `SingletonImageLoader.get(context).enqueue(ImageRequest.Builder(context).data(url).build())` writes the image to the memory and disk caches without displaying it.
- Logging: `logger(DebugLogger())` on the builder, in debug builds only.

## 8. Previews and tests

- Previews have no network access, so remote URLs always fail there. Provide `LocalAsyncImagePreviewHandler` with an `AsyncImagePreviewHandler { ColorImage(Color.Gray.toArgb()) }` (or a bundled sample image) around the preview content. The same handler applies to Compose Preview Screenshot Testing.
- Tests must not hit the network. Add `coil-test` and register a `FakeImageLoaderEngine` that maps models to `ColorImage` results; it makes loads synchronous and deterministic.

```kotlin
val engine = FakeImageLoaderEngine.Builder()
    .intercept({ it is String && it.contains("/avatars/") }, ColorImage(Color.Magenta.toArgb()))
    .default(ColorImage(Color.LightGray.toArgb()))
    .build()
SingletonImageLoader.setUnsafe(
    ImageLoader.Builder(context).components { add(engine) }.build(),
)
```

`setUnsafe` is meant for tests only; each call replaces the singleton. For screenshot tests see `android-testing`.

## 9. Accessibility

- Meaningful images get a `contentDescription` loaded with `stringResource`, written to make sense when read aloud and translated.
- Decorative images, and images whose meaning is already in adjacent text, use `contentDescription = null`.
- Details: `compose-accessibility`.

## 10. Checklist

- [ ] Resources through `painterResource`; remote or file images through Coil 3 with one network artifact.
- [ ] One app-wide `ImageLoader`, configured at startup and sharing the app's `OkHttpClient`.
- [ ] `AsyncImage` by default; any `rememberAsyncImagePainter` has a size resolver.
- [ ] Every remote image has bounded dimensions before loading, and list items keep their size after loading.
- [ ] Image composables take URLs or IDs, not `Painter`s.
- [ ] `SubcomposeAsyncImage` in scrolling content is justified and measured.
- [ ] Descriptions are string resources, or `null` for decorative images.
- [ ] Previews use a preview handler; tests use `FakeImageLoaderEngine`.
