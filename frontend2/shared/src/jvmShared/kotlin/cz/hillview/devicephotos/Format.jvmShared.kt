package cz.hillview.devicephotos

import java.text.DateFormat
import java.util.Date

actual fun formatLocalDate(epochMs: Long): String =
    DateFormat.getDateInstance(DateFormat.SHORT).format(Date(epochMs))

actual fun formatLocalTime(epochMs: Long): String =
    DateFormat.getTimeInstance(DateFormat.MEDIUM).format(Date(epochMs))
