package cz.hillview.plugin

/**
 * The ONE place the log-tag prefix exists.
 *
 * Every tag in both apps is `hv-<something>`, which makes `logcat` filterable to
 * this project's own output. That was a convention held by 49 copies of the
 * string `"hv-"`, and conventions held by copies drift: three instrumented tests
 * had already lost it (`"UploadCoalescing"` beside app code logging under
 * `"hv-UploadCoalescing"`), and nothing would have said so.
 *
 * Verifying it afterwards is the part that does not scale. It took a source
 * regex (which over-counted, matching commented-out code and a string inside a
 * test), then an AST query, to answer "are they all prefixed?" with confidence.
 * A function makes the question unaskable instead: there is one prefix, and a
 * new tag either goes through here or fails `LogTagConventionTest`.
 *
 * NOT `const`, deliberately, and the cost is understood: `const val TAG` is
 * inlined into each of ~600 call sites, while this is one static field read per
 * call. That is not measurable, and it buys a single definition. If the prefix
 * ever has to change, or tags ever need truncating (see below), this is the only
 * edit.
 *
 * ON LENGTH, corrected 2026-10-15 — the earlier wording here claimed the 23-character
 * cap was "gone on the API levels these apps target", and that is FALSE.
 *
 * Where the cap actually lives: `Log.isLoggable` throws `IllegalArgumentException` for a
 * tag longer than 23 characters on **API 25 and below** (the platform's own doc for that
 * method states the boundary). Ordinary `Log.d/i/w/e` never throw on a long tag at any
 * API level — they are not affected, which is the whole reason this has cost nothing.
 *
 * And both apps DO target affected devices: frontend2 is minSdk 24 and the Tauri
 * plugin is minSdk 21, so the API 21–25 range is in scope for both. Six tags are over
 * the cap — `hv-AuthenticationManager` 24, `hv-PanoramaxMarkerSource` 24,
 * `hv-PhotoUploadForeground` 24, `hv-PreciseLocationService` 25,
 * `hv-DeviceOrientationProvider` 28, `hv-MyDeviceOrientationSensor` 28.
 *
 * Why that is still safe: NOTHING in either app calls `Log.isLoggable`, and
 * `LogTagConventionTest` fails the build if anything starts to. So the hazard is not
 * "long tags exist" but "a long tag reaches `isLoggable`", and the test is what keeps
 * those apart. A caller that genuinely needs the API must pass a tag it has bounded
 * itself — these are not safe for it.
 *
 * Deliberately still NOT truncated: a silently shortened tag is worse than a long one,
 * it would change six tags and every `logcat` filter and grep that matches them, and
 * if a minSdk ever makes it matter, truncating belongs here rather than in 49 places.
 */
fun hvTag(name: String): String = HV_LOG_PREFIX + name

/** The prefix itself, for the rare caller that needs to match on it. */
const val HV_LOG_PREFIX = "hv-"
