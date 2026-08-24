package cz.hillview.devicephotos

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// Site-wide ISO display convention (matches the web frontend's dateUtils):
// "2026-08-24" / "15:45:12", device-local zone. Locale.US only pins the
// digits/pattern — the patterns are purely numeric anyway.
actual fun formatLocalDate(epochMs: Long): String =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date(epochMs))

actual fun formatLocalTime(epochMs: Long): String =
    SimpleDateFormat("HH:mm:ss", Locale.US).format(Date(epochMs))
