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
 * ON LENGTH: `logcat` tags were capped at 23 characters, and
 * `Log.isLoggable` threw `IllegalArgumentException` above it. The cap is gone on
 * the API levels these apps target, and six tags here are already over it
 * (`hv-MyDeviceOrientationSensor` is 28). Deliberately NOT truncated: a
 * silently shortened tag is worse than a long one, and if a minSdk ever makes it
 * matter, truncating belongs here rather than in 49 places.
 */
fun hvTag(name: String): String = HV_LOG_PREFIX + name

/** The prefix itself, for the rare caller that needs to match on it. */
const val HV_LOG_PREFIX = "hv-"
