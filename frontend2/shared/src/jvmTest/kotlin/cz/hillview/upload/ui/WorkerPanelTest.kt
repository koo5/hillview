package cz.hillview.upload.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.settings.CertificatePin
import cz.hillview.settings.UploadSettings
import cz.hillview.settings.WorkerEndpoint
import cz.hillview.settings.WorkerStatus
import cz.hillview.settings.ago
import cz.hillview.settings.defaultUploadSettings
import cz.hillview.settings.withWorkerAdded
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The worker panel on the Uploads screen (2026-11-09; before that the Settings
 * worker dialog — user, 2026-11-05: "a little dialog to configure worker urls,
 * where each could be either accepting self-signed certs or not" … "we'll need
 * some status/logging to debug this in the UI"; 2026-11-09: "we've created a
 * total mess" … the certificate toggle "should not be a toggle if its an action").
 */
@OptIn(ExperimentalTestApi::class)
class WorkerPanelTest {

    private val pin = CertificatePin("AAAA", "AB:CD:EF", "CN=worker.lan", "Fri Nov 05 2027")
    private val now = 1_000_000L

    @Test
    fun anInvalidUrlCannotBeAdded() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api"))
        setContent { WorkerPanel(settings, { t -> settings = t(settings) }, emptyMap(), null, now, {}) }
        onNodeWithTag("worker-option-server").assertIsSelected()
        onNodeWithTag("worker-add").assertIsNotEnabled()
        onNodeWithTag("worker-new-url").performTextInput("worker.lan")
        onNodeWithTag("worker-add").assertIsNotEnabled()
        onNodeWithText("http:// or https:// and a host").assertExists()
    }

    @Test
    fun aValidUrlIsAddedAndUsed() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api"))
        setContent { WorkerPanel(settings, { t -> settings = t(settings) }, emptyMap(), null, now, {}) }
        onNodeWithTag("worker-new-url").performTextInput("https://worker.lan:8056/")
        onNodeWithTag("worker-add").assertIsEnabled().performClick()
        assertEquals(listOf(WorkerEndpoint("https://worker.lan:8056")), settings.workerEndpoints)
        onNodeWithTag("worker-option-0").assertIsSelected()
        onNodeWithTag("worker-option-server").performClick()
        assertNull(settings.workerOverrideUrl)
    }

    /**
     * Each URL shows its own newest contact, so a failure at one worker never
     * sits unlabelled beside a success at another.
     */
    @Test
    fun eachWorkerShowsItsOwnStatus() = runComposeUiTest {
        val settings = defaultUploadSettings("https://api/api")
            .withWorkerAdded("https://aux.lan:8056").withWorkerAdded("http://10.0.2.2:8056")
        val statuses = mapOf(
            "https://worker.fly.dev" to WorkerStatus("https://worker.fly.dev", now - 180_000, "uploaded a.jpg", false),
            "https://aux.lan:8056" to WorkerStatus(
                "https://aux.lan:8056", now - 4_000, "upload: SSLHandshakeException ← Trust anchor not found", true,
            ),
        )
        setContent { WorkerPanel(settings, {}, statuses, "https://worker.fly.dev", now, {}) }
        onNodeWithTag("worker-server-url").assertTextContains("https://worker.fly.dev")
        onNodeWithTag("worker-status-server").assertTextContains("✓ uploaded a.jpg · 3 min ago")
        onNodeWithTag("worker-status-0").assertTextContains("✗ upload: SSLHandshakeException", substring = true)
        onNodeWithTag("worker-status-0").assertTextContains("4 s ago", substring = true)
        onNodeWithTag("worker-status-1").assertTextContains("No contact yet.")
    }

    /** A 503 is the worker full, not failing (user, 2026-11-09: "the screens still show 503 as an error"). */
    @Test
    fun aFullWorkerIsBusyNotFailed() = runComposeUiTest {
        val settings = defaultUploadSettings("https://api/api").withWorkerAdded("https://aux.lan:8056")
        val statuses = mapOf(
            "https://aux.lan:8056" to WorkerStatus(
                "https://aux.lan:8056", now - 10_000, "ready: queue full (HTTP 503), come back in 500 s",
                failed = false, busy = true,
            ),
        )
        setContent { WorkerPanel(settings, {}, statuses, null, now, {}) }
        onNodeWithTag("worker-status-0").assertTextContains("⏳ ready: queue full (HTTP 503), come back in 500 s · 10 s ago")
    }

    @Test
    fun beforeAnyUploadTheServersWorkerIsUnknown() = runComposeUiTest {
        setContent { WorkerPanel(defaultUploadSettings("https://api/api"), {}, emptyMap(), null, now, {}) }
        onNodeWithTag("worker-server-url").assertTextContains("none yet", substring = true)
        onNodeWithTag("worker-test-server").assertDoesNotExist()
    }

    @Test
    fun pinningIsAButtonThatPinsWhatTheWorkerPresentsAndTestsThroughIt() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan"))
        val asked = mutableListOf<String>()
        val tested = mutableListOf<WorkerEndpoint>()
        var contacts = 0
        setContent {
            WorkerPanel(
                settings, { t -> settings = t(settings) }, emptyMap(), null, now, { contacts++ },
                fetchCertificate = { asked += it; pin },
                test = { tested += it },
            )
        }
        onNodeWithTag("worker-unpin-0").assertDoesNotExist()
        onNodeWithTag("worker-pin-action-0").assertTextContains("Pin certificate").performClick()
        waitForIdle()
        assertEquals(listOf("https://worker.lan"), asked)
        assertEquals(pin, settings.workerEndpoints.single().pin)
        onNodeWithTag("worker-pin-0").assertTextContains("AB:CD:EF", substring = true)
        // Pinning tests at once, THROUGH the new pin — no second press of Test.
        assertEquals(listOf(WorkerEndpoint("https://worker.lan", pin)), tested)
        assertEquals(1, contacts, "the screen is told to re-read the status")
        onNodeWithTag("worker-pin-action-0").assertTextContains("Re-pin")
        onNodeWithTag("worker-unpin-0").performClick()
        assertNull(settings.workerEndpoints.single().pin)
    }

    /** The platform records why a fetch failed as the URL's status; the panel shows it. */
    @Test
    fun aFailedFetchShowsWhyOnTheStatusLineAndPinsNothing() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan"))
        var statuses by mutableStateOf(emptyMap<String, WorkerStatus>())
        setContent {
            WorkerPanel(
                settings, { t -> settings = t(settings) }, statuses, null, now, {},
                fetchCertificate = {
                    statuses = mapOf(
                        it to WorkerStatus(it, now, "pin: could not fetch a certificate — connection refused", true),
                    )
                    throw IllegalStateException("connection refused")
                },
            )
        }
        onNodeWithTag("worker-pin-action-0").performClick()
        waitForIdle()
        onNodeWithTag("worker-status-0").assertTextContains("connection refused", substring = true)
        assertNull(settings.workerEndpoints.single().pin)
    }

    @Test
    fun aTestEndsInTheRecordedOutcomeAndAReRead() = runComposeUiTest {
        val settings = defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan")
        var statuses by mutableStateOf(emptyMap<String, WorkerStatus>())
        var contacts = 0
        setContent {
            WorkerPanel(
                settings, {}, statuses, null, now, { contacts++ },
                test = { statuses = mapOf(it.url to WorkerStatus(it.url, now, "test: Ready — HTTP 200 in 12 ms", false)) },
            )
        }
        onNodeWithTag("worker-test-0").performClick()
        waitForIdle()
        onNodeWithTag("worker-status-0").assertTextContains("✓ test: Ready — HTTP 200 in 12 ms · just now")
        assertEquals(1, contacts)
    }

    @Test
    fun httpHasNoPinButtonAndSaysItIsUnencrypted() = runComposeUiTest {
        val settings: UploadSettings = defaultUploadSettings("https://api/api").withWorkerAdded("http://10.0.2.2:8056")
        setContent { WorkerPanel(settings, {}, emptyMap(), null, now, {}) }
        onNodeWithTag("worker-pin-action-0").assertDoesNotExist()
        onNodeWithText("unencrypted", substring = true).assertExists()
    }

    @Test
    fun removingTheSelectedWorkerGoesBackToTheServer() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan"))
        setContent { WorkerPanel(settings, { t -> settings = t(settings) }, emptyMap(), null, now, {}) }
        onNodeWithTag("worker-remove-0").performClick()
        assertEquals(emptyList(), settings.workerEndpoints)
        onNodeWithTag("worker-option-server").assertIsSelected()
    }

    @Test
    fun agesReadTheSameEverywhere() {
        assertEquals("just now", ago(1_500))
        assertEquals("12 s ago", ago(12_000))
        assertEquals("4 min ago", ago(4 * 60_000L + 5_000))
        assertEquals("3 h ago", ago(3 * 3_600_000L))
        assertEquals("2 d ago", ago(2 * 86_400_000L))
    }
}
