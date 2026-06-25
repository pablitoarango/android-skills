---
name: android-retrofit
description: "Retrofit and OkHttp networking per the Retrofit docs and Google's data layer guide: service declarations, suspend return types, remote data sources, network models, Hilt and OkHttp setup, interceptors, auth, logging, errors, R8, MockWebServer tests. Use when adding or changing HTTP API calls, interceptors, or network error handling."
---

# Retrofit and OkHttp in the Data Layer

Sources of truth: [Data layer](https://developer.android.com/topic/architecture/data-layer), [Connect to the network](https://developer.android.com/develop/connectivity/network-ops/connecting), [Network security configuration](https://developer.android.com/privacy-and-security/security-config), [Retrofit documentation](https://lysine.dev/retrofit/), [Retrofit repository](https://github.com/lysine-dev/retrofit), [OkHttp logging interceptor](https://github.com/lysine-dev/okhttp/tree/main/okhttp-logging-interceptor), [OkHttp documentation](https://lysine.dev/okhttp/), [MockWebServer](https://github.com/lysine-dev/okhttp/tree/main/mockwebserver).

Read versions from [Retrofit releases](https://github.com/lysine-dev/retrofit/releases), the [OkHttp changelog](https://github.com/lysine-dev/okhttp/blob/main/CHANGELOG.md) and [kotlinx.serialization releases](https://github.com/Kotlin/kotlinx.serialization/releases). Never hardcode them in code samples.

## 1. Where Retrofit sits

```
ViewModel / use case
  └── NewsRepository            public; the only entry point
        └── NewsRemoteDataSource internal; wraps the API
              └── NewsApi        internal Retrofit interface
```

- **Only a remote data source injects a Retrofit interface.** Repositories, use cases, ViewModels and composables never do (`android-data-layer`).
- **Name by role.** The Retrofit interface is `<Type>Api` (`NewsApi`) and the class wrapping it is `<Type>RemoteDataSource`, following Google's data layer guide. Never name a class after the library (`NewsRetrofitDataSource`).
- **The Retrofit interface is the swappable seam.** Google's guide: the `NewsApi` interface hides whether Retrofit or another client backs it. Unit tests pass a fake `NewsApi` to the real data source.
- **Network models are separate (stricter than Google).** Google requires a new model whenever the source shape differs from what the app needs. Here every service returns `@Serializable` models named `Network<Model>` (`NetworkArticle`), and the repository maps them with `NetworkArticle.asExternalModel()` or `asEntity()`. Network models never leave the data layer.
- **Keep it internal.** APIs, network models, data sources and the network Hilt module are `internal` when co-located with the repository. A separate network module exposes only what repositories need (`android-architecture`).
- **One-shot calls are `suspend`.** Retrofit has no streaming `Flow` return type; a `Flow` of network data comes from the repository (usually backed by Room, see `android-data-layer`).

```kotlin
internal interface NewsApi {
    @GET("news/latest")
    suspend fun fetchLatestNews(@Query("limit") limit: Int): NetworkNewsResponse
}

@Serializable
internal data class NetworkNewsResponse(val data: List<NetworkArticle>)

internal class NewsRemoteDataSource @Inject constructor(
    private val newsApi: NewsApi,
) {
    suspend fun fetchLatestNews(limit: Int = 20): List<NetworkArticle> =
        newsApi.fetchLatestNews(limit).data
}
```

### Main-safety

Google requires data sources and repositories to be main-safe. Retrofit `suspend` functions enqueue the call on OkHttp's dispatcher and parse the response there, so they are already main-safe: **do not wrap them in `withContext(ioDispatcher)`**. Google's `withContext` example applies to a blocking API; use an injected dispatcher only for blocking work such as `Call.execute()`, reading a `@Streaming` body, or writing a download to disk (`android-coroutines`).

Cancelling the calling coroutine cancels the HTTP call.

## 2. Dependencies

| Artifact | Purpose |
|---|---|
| `com.squareup.retrofit2:retrofit-bom` | Aligns Retrofit artifacts |
| `com.squareup.retrofit2:retrofit` | Core |
| `com.squareup.retrofit2:converter-kotlinx-serialization` | JSON through kotlinx.serialization |
| `com.squareup.okhttp3:okhttp-bom` | Aligns OkHttp artifacts |
| `com.squareup.okhttp3:logging-interceptor` | Debug HTTP logging |
| `org.jetbrains.kotlinx:kotlinx-serialization-json` | JSON format |
| Plugin `org.jetbrains.kotlin.plugin.serialization` | Generates serializers for `@Serializable` |
| `com.squareup.okhttp3:mockwebserver3` | Tests; no JUnit dependency |
| `com.squareup.okhttp3:mockwebserver3-junit4` / `-junit5` | `MockWebServerRule` / `@StartStop` |

```kotlin
plugins {
    alias(libs.plugins.kotlin.serialization)
}

dependencies {
    implementation(platform(libs.retrofit.bom))
    implementation(libs.retrofit.core)
    implementation(libs.retrofit.kotlin.serialization)
    implementation(platform(libs.okhttp.bom))
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.serialization.json)
    testImplementation(libs.okhttp.mockwebserver3.junit4)
}
```

- Declare these in the version catalog (`gradle-build-logic`).
- Retrofit 3 requires Android API 21+ and depends on OkHttp (3.0.0 moved from OkHttp 3.14 to 4.12, so Retrofit now pulls in Kotlin transitively). Check the Retrofit changelog for the OkHttp version it requires before choosing a different OkHttp BOM.
- The kotlinx.serialization converter is a first-party Retrofit module since 2.10.0 (`retrofit2.converter.kotlinx.serialization.asConverterFactory`). The older `com.jakewharton.retrofit` artifact is superseded; replace it.
- Moshi, Gson, Jackson, Protobuf, Wire and Scalars converters also exist. For Kotlin apps prefer kotlinx.serialization, which Google's samples use.
- Declare `<uses-permission android:name="android.permission.INTERNET" />`. It is a normal permission granted at install.

## 3. Hilt setup

Provide one `Json`, one `OkHttpClient`, one `Retrofit` per base URL, and each API interface, all app-wide.

```kotlin
@Module
@InstallIn(SingletonComponent::class)
internal object NetworkModule {

    @Provides
    @Singleton
    fun providesNetworkJson(): Json = Json {
        ignoreUnknownKeys = true
    }

    @Provides
    @Singleton
    fun providesOkHttpClient(
        authInterceptor: AuthInterceptor,
    ): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
        .apply {
            if (BuildConfig.DEBUG) {
                addInterceptor(
                    HttpLoggingInterceptor().apply {
                        level = HttpLoggingInterceptor.Level.BODY
                        redactHeader("Authorization")
                        redactHeader("Cookie")
                    },
                )
            }
        }
        .build()

    @Provides
    @Singleton
    fun providesRetrofit(
        networkJson: Json,
        okHttpClient: dagger.Lazy<OkHttpClient>,
    ): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.BACKEND_URL)
        .callFactory { request -> okHttpClient.get().newCall(request) }
        .addConverterFactory(networkJson.asConverterFactory("application/json".toMediaType()))
        .build()

    @Provides
    @Singleton
    fun providesNewsApi(retrofit: Retrofit): NewsApi = retrofit.create()
}
```

- **Share one `OkHttpClient`.** Each client owns its connection pool and threads. For different timeouts or interceptors derive a client with `okHttpClient.newBuilder()`, which shares the pool. Share the same client with Coil (`compose-images`).
- **Defer building OkHttp.** `dagger.Lazy` plus `callFactory { }` creates the client on the first request instead of while the dependency graph is built, as the Now in Android sample does.
- **`ignoreUnknownKeys = true`** lets the server add fields without breaking installed app versions.
- **The kotlinx.serialization converter claims every type.** Add it last, after any other converter (for example Scalars).
- **Use `retrofit.create<T>()`**, the reified Kotlin extension in `retrofit2`.
- **Several backends** get a qualifier (`@Named` or a custom `@Qualifier`) per `Retrofit` instance.

### Base URLs

Endpoint paths resolve against the base URL like links on a web page:

| Base URL | Endpoint | Result |
|---|---|---|
| `https://example.com/api/` | `news/latest` | `https://example.com/api/news/latest` |
| `https://example.com/api/` | `/news/latest` | `https://example.com/news/latest` (base path dropped) |
| `https://example.com/api/` | `https://cdn.example.com/a` | `https://cdn.example.com/a` |

- End base URLs with `/` (Retrofit enforces it) and write endpoints **without** a leading `/`.
- Take the base URL from build configuration (`buildConfigField` per build type or flavor), not string literals in classes.
- Use `@Url` for server-provided absolute URLs, such as pagination `next` links.

## 4. Declaring endpoints

| Annotation | Rules |
|---|---|
| `@GET` `@POST` `@PUT` `@PATCH` `@DELETE` `@HEAD` `@OPTIONS` | Relative URL in the annotation; static query allowed (`"users?sort=desc"`). `HEAD` returns `Unit` |
| `@HTTP(method, path, hasBody)` | Custom methods, or `DELETE` with a body |
| `@Path("id")` | Fills `{id}`; URL encoded unless `encoded = true`; never `null` |
| `@Query("key")` | `null` omits the parameter; a `List` repeats it |
| `@QueryMap` / `@QueryName` | Dynamic parameter sets / valueless parameters |
| `@Url` | Full or relative URL replacing the annotation URL (use `@GET` with no path) |
| `@Body` | Serialized by the converter; never `null` |
| `@FormUrlEncoded` + `@Field` / `@FieldMap` | `application/x-www-form-urlencoded`; `null` fields omitted |
| `@Multipart` + `@Part` / `@PartMap` | `@Part("name") RequestBody`, or unnamed `@Part MultipartBody.Part` |
| `@Headers("K: V")` | Static; same-name headers are all sent, never overwritten |
| `@Header("K")` / `@HeaderMap` | Dynamic; `null` omits the header |
| `@Tag` | Attaches a value to the OkHttp request for interceptors |
| `@Streaming` | Do not buffer a `ResponseBody` in memory |

A recipe service using each kind of parameter:

```kotlin
internal interface RecipeApi {
    @GET("recipes/{recipeId}")
    suspend fun fetchRecipe(@Path("recipeId") recipeId: Long): NetworkRecipe

    @GET("recipes")
    suspend fun fetchRecipes(
        @Query("cuisine") cuisine: String?,
        @Query("tag") tags: List<String>,
        @Query("page_token") pageToken: String?,
    ): NetworkRecipePage

    @POST("recipes")
    suspend fun publishRecipe(@Body draft: NetworkRecipeDraft): NetworkRecipe

    @FormUrlEncoded
    @PATCH("recipes/{recipeId}")
    suspend fun rateRecipe(
        @Path("recipeId") recipeId: Long,
        @Field("stars") stars: Int,
    ): NetworkRecipe

    @Multipart
    @POST("recipes/{recipeId}/images")
    suspend fun attachImage(
        @Path("recipeId") recipeId: Long,
        @Part("caption") caption: RequestBody,
        @Part image: MultipartBody.Part,
    ): NetworkRecipeImage

    @DELETE("recipes/{recipeId}")
    suspend fun deleteRecipe(@Path("recipeId") recipeId: Long): Response<Unit>

    @GET
    suspend fun fetchRecipesPage(@Url nextPageUrl: String): NetworkRecipePage

    @Streaming
    @GET("recipes/{recipeId}/video")
    suspend fun streamVideo(@Path("recipeId") recipeId: Long): ResponseBody
}
```

- `fetchRecipes(cuisine = null, tags = listOf("vegan", "quick"), pageToken = null)` requests `recipes?tag=vegan&tag=quick`.
- Retrofit encodes `@Path`, `@Query` and `@Field` values. Assembling paths or query strings by hand skips that encoding and breaks on reserved characters.
- Credentials, locale and app-version headers go in one OkHttp interceptor (section 6), as the Retrofit docs advise for headers every request needs.
- Create parts in the data source, not in callers: `MultipartBody.Part.createFormData("image", file.name, file.asRequestBody("image/jpeg".toMediaType()))` and `caption.toRequestBody("text/plain".toMediaType())`.
- Read a `@Streaming` body inside `withContext(ioDispatcher)` and close it with `use { }`.

## 5. Return types

Every method is a `suspend fun`. Do not declare `Call<T>` or RxJava types in new code (`migrate-rxjava-to-coroutines`).

What a `suspend` method does for each declared type, from Retrofit's `KotlinExtensions`:

| Declared type | Status outside 200-299 | Success with no body (204, 205) |
|---|---|---|
| `T` | `HttpException` | **`KotlinNullPointerException`** |
| `T?` | `HttpException` | `null` |
| `Unit` | `HttpException` | Completes; any body is discarded unread |
| `ResponseBody` | `HttpException` | **`KotlinNullPointerException`** (Retrofit returns a null body for 204 and 205) |
| `Response<T>` | Nothing is thrown; check `isSuccessful` and read `errorBody()` | `body()` returns `null` |

Transport failures (`IOException`) and converter failures are thrown for every type, including `Response<T>`.

- Return `T` by default.
- Return `Unit` for endpoints that answer with no content.
- Return `Response<T>` only when the caller needs status codes, headers (pagination, ETag) or a structured error body.
- Retrofit buffers error bodies in memory, so `errorBody()?.string()` does not block, but it can be read only once.

## 6. OkHttp configuration

### Interceptors

Interceptors run in the order they are added.

| | Application (`addInterceptor`) | Network (`addNetworkInterceptor`) |
|---|---|---|
| Runs | Once per call, even for cached responses | Per network request, including redirects; skipped for cache hits |
| Can | Short-circuit, retry, change call timeouts | Inspect the `Connection` and bytes on the wire |
| Use for | Auth headers, common headers, logging | Rare; network-level inspection |

```kotlin
internal class AuthInterceptor @Inject constructor(
    private val tokenStore: TokenStore,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = tokenStore.currentAccessToken() ?: return chain.proceed(chain.request())
        val request = chain.request().newBuilder()
            .header("Authorization", "Bearer $token")
            .build()
        return chain.proceed(request)
    }
}
```

- Interceptors run on OkHttp threads, not the main thread. Read tokens from an in-memory holder that the data layer keeps current, not from disk on every request.
- Use `header()` to replace a value and `addHeader()` to append one.
- To act on specific methods, read `chain.request().tag(Invocation::class.java)` for the Retrofit method and arguments, or pass a value with `@Tag`.
- If `chain.proceed()` is called more than once, close earlier response bodies.

### Refreshing credentials on 401

Use an OkHttp `Authenticator`, not an interceptor. OkHttp calls it on a `401` to supply a new request; returning `null` gives up.

```kotlin
internal class TokenAuthenticator @Inject constructor(
    private val tokenStore: TokenStore,
    private val tokenRefresher: TokenRefresher,
) : Authenticator {
    override fun authenticate(route: Route?, response: Response): Request? {
        if (response.responseCount >= 3) return null
        val newToken = tokenRefresher.refreshBlocking(staleToken = tokenStore.currentAccessToken())
            ?: return null
        return response.request.newBuilder()
            .header("Authorization", "Bearer $newToken")
            .build()
    }

    private val Response.responseCount: Int
        get() = generateSequence(this) { it.priorResponse }.count()
}
```

- Register it with `OkHttpClient.Builder().authenticator(tokenAuthenticator)`.
- Always cap retries (`responseCount`, or give up when the same credentials already failed), or a rejected token loops forever.
- Make refresh single-flight: concurrent 401s must trigger one refresh, and callers whose token is already replaced reuse the new one.
- Perform the refresh with a separate client (`newBuilder()` without the authenticator) so the refresh call cannot recurse into itself.
- When refresh fails, clear the session and surface a `UserNotAuthenticatedException` from the repository.

### Logging

- Add `HttpLoggingInterceptor` **only in debug builds**. `HEADERS` and `BODY` levels leak `Authorization` and `Cookie` headers and body contents, so the OkHttp docs restrict them to controlled, non-production environments.
- Even in debug, `redactHeader("Authorization")`, `redactHeader("Cookie")` and `redactQueryParams(...)` for secrets in URLs.
- Add it **after** interceptors that add headers, so the log shows the final request.
- Levels: `NONE`, `BASIC` (request and response lines), `HEADERS`, `BODY`.
- Route output to your logger with the constructor: `HttpLoggingInterceptor { message -> Timber.tag("OkHttp").d(message) }`.
- The log format is not stable; never parse it.

### Timeouts, caching, retries

- OkHttp defaults: 10 s connect, read and write timeouts, no call timeout. Change them only for a concrete need, on a `newBuilder()` client for the endpoints that need it (large uploads, long polling).
- The HTTP cache is off by default. Enable it once on the shared client with `Cache(File(context.cacheDir, "http_cache"), maxSize)`. Never point two clients' caches at the same directory. The server's `Cache-Control` headers decide what is cached.
- OkHttp already retries failed connections on other routes. Do not add retry interceptors for non-idempotent requests (`POST`). Retry user-visible failures from the UI, and work that must finish from WorkManager (`android-data-layer`).

## 7. Errors

| Exception | Cause |
|---|---|
| `IOException` | No connectivity, DNS, TLS, timeouts, connection reset |
| `HttpException` | Non-2xx status with a body return type; `code()`, `response()?.errorBody()` |
| `SerializationException` | Malformed or unexpected JSON; **not** an `IOException` |
| `KotlinNullPointerException` | Empty 2xx body with a non-null return type |

Follow Google's data layer guide:

- **Data sources throw.** They may parse structured error bodies into network error models.
- **The repository** lets exceptions propagate, translates them into meaningful custom exceptions (`UserNotAuthenticatedException`), or returns `Result<T>`. Pick one style per repository.
- **Catch specific types** (`IOException`, `HttpException`, `SerializationException`). A broad `catch (e: Exception)` must rethrow `CancellationException` first.
- **Never use the standard `runCatching`** around suspending calls: it swallows `CancellationException`. Use `suspendRunCatching` from `android-coroutines`.
- **The ViewModel** turns failures into UI state (`android-viewmodel`). Flows handle errors with `catch`.

```kotlin
@Serializable
internal data class NetworkApiError(val code: String, val message: String)

internal class RecipeRemoteDataSource @Inject constructor(
    private val recipeApi: RecipeApi,
    private val networkJson: Json,
) {
    suspend fun deleteRecipe(recipeId: Long) {
        val response = recipeApi.deleteRecipe(recipeId)
        if (response.isSuccessful) return
        val apiError = response.errorBody()?.string()?.let { body ->
            try {
                networkJson.decodeFromString<NetworkApiError>(body)
            } catch (e: SerializationException) {
                null
            }
        }
        throw ApiException(status = response.code(), apiCode = apiError?.code)
    }
}

internal class DefaultRecipeRepository @Inject constructor(
    private val remoteDataSource: RecipeRemoteDataSource,
) : RecipeRepository {

    override suspend fun deleteRecipe(recipeId: Long) {
        try {
            remoteDataSource.deleteRecipe(recipeId)
        } catch (e: ApiException) {
            if (e.status == 401) throw UserNotAuthenticatedException(e)
            throw e
        }
    }
}
```

## 8. Security

- Send all traffic over HTTPS and minimize the personal data sent (Google's networking guide).
- Cleartext HTTP is blocked by default when targeting API 28+. Do not set `cleartextTrafficPermitted="true"` globally. If a local development server needs HTTP, allow only its domain, in a debug-only network security config.
- Trust debug-only certificate authorities (proxies, local servers) with `<debug-overrides>` in the network security configuration, not code that disables TLS checks.
- Never ship a custom `TrustManager` or `HostnameVerifier` that accepts everything.
- If you pin certificates, always include a backup pin, and understand the trade-off of an expiration date.
- Never put API secrets in `BuildConfig` or code and assume they stay secret; ship only what the server treats as public.

## 9. R8

- Retrofit and OkHttp ship their R8 rules in their JARs; you add nothing for R8. ProGuard-only builds must copy `retrofit2.pro` and OkHttp's rules.
- R8 can strip a type used **only** as a service method's generic return type (`NetworkResponse<NetworkUser>`) and fail at runtime. If that happens, add Retrofit's `response-type-keeper` annotation processor, or keep the models explicitly.
- Test a minified release build against the real API before shipping.

## 10. Testing

Google: prefer fakes to mocks, unit test repositories and data sources, and use MockWebServer for network integration tests (`android-testing`).

**Unit tests** fake the Retrofit interface and exercise the real data source and repository:

```kotlin
internal class FakeNewsApi : NewsApi {
    var articles: List<NetworkArticle> = emptyList()
    var failure: Exception? = null

    override suspend fun fetchLatestNews(limit: Int): NetworkNewsResponse {
        failure?.let { throw it }
        return NetworkNewsResponse(articles.take(limit))
    }
}
```

**Integration tests** run the real Retrofit, converter and data source against `MockWebServer` to check request shape, parsing and error mapping:

```kotlin
class NewsRemoteDataSourceTest {

    @JvmField
    @Rule
    val serverRule = MockWebServerRule()

    private lateinit var dataSource: NewsRemoteDataSource

    @Before
    fun setUp() {
        val json = Json { ignoreUnknownKeys = true }
        val api = Retrofit.Builder()
            .baseUrl(serverRule.server.url("/"))
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create<NewsApi>()
        dataSource = NewsRemoteDataSource(api)
    }

    @Test
    fun fetchLatestNews_parsesArticles() = runTest {
        serverRule.server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body("""{"data":[{"id":"1","title":"Hello"}]}""")
                .build(),
        )

        val articles = dataSource.fetchLatestNews(limit = 5)

        assertEquals("1", articles.single().id)
        val request = serverRule.server.takeRequest()
        assertEquals("/news/latest", request.url.encodedPath)
        assertEquals("5", request.url.queryParameter("limit"))
    }

    @Test
    fun fetchLatestNews_serverError_throwsHttpException() = runTest {
        serverRule.server.enqueue(MockResponse.Builder().code(500).build())

        val error = assertFailsWith<HttpException> { dataSource.fetchLatestNews() }

        assertEquals(500, error.code())
    }
}
```

- Use the `mockwebserver3` package (`MockResponse.Builder`, immutable `MockResponse`). OkHttp 5 marks the old `com.squareup.okhttp3:mockwebserver` artifact (package `okhttp3.mockwebserver`, depends on JUnit 4) obsolete; do not add it to new tests.
- `MockWebServerRule` comes from `mockwebserver3-junit4`. With JUnit 5 use `mockwebserver3-junit5` and annotate the property: `@StartStop val server = MockWebServer()`.
- Without either integration, call `server.start()` before `server.url(...)` (OkHttp 5 no longer starts the server from accessors) and `server.close()` afterwards.
- Use a new server per test; instances cannot be restarted.
- For several endpoints in one test, set `server.dispatcher` to a `Dispatcher` that answers by `request.url.encodedPath` instead of relying on enqueue order.
- Cover empty bodies, malformed JSON, 401 handling and slow responses (`throttleBody`) for code that depends on them.
- Use the same `Json` configuration as production.

## 11. Checklist

Layering
- [ ] A `<Type>RemoteDataSource` is the only injector of a `<Type>Api`; the API, `Network*` models and data source stay `internal` to the data module.
- [ ] `Network*` models never cross the repository boundary.

Declarations
- [ ] Methods are `suspend fun`; no `Call<T>` or Rx return types in new code.
- [ ] The declared type matches the endpoint: nullable or `Unit` where a 2xx can be empty, `Response<T>` where the caller reads headers or error bodies.
- [ ] Endpoints are relative (no leading `/`), the base URL ends with `/` and comes from build configuration.

Client
- [ ] One app-wide `OkHttpClient`; per-endpoint variants come from `newBuilder()`.
- [ ] The kotlinx.serialization converter is registered after any narrower converter, with the production `Json`.
- [ ] Shared headers come from one interceptor; 401 recovery is an `Authenticator` with a retry cap and one refresh at a time.
- [ ] Logging is added only in debug builds, after header-adding interceptors, with credentials redacted.
- [ ] No `withContext` wraps Retrofit calls; only blocking body reads switch to an injected dispatcher.

Failures and security
- [ ] Failures are handled by type (`IOException`, `HttpException`, `SerializationException`), `CancellationException` is never swallowed, and each repository uses one error style.
- [ ] Traffic is HTTPS; cleartext and extra trust anchors exist only in debug network security config.

Verification
- [ ] MockWebServer tests cover request shape, parsing and each mapped error.
- [ ] A minified release build has been run against the real API.
