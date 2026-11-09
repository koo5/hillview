package cz.hillview.settings.ui

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
import cz.hillview.settings.defaultUploadSettings
import cz.hillview.settings.withWorkerAdded
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The worker dialog (user, 2026-11-05: "a little dialog to configure worker
 * urls, where each could be either accepting self-signed certs or not" …
 * "we'll need some status/logging to debug this in the UI").
 */
@OptIn(ExperimentalTestApi::class)
class WorkerUrlDialogTest {

    private val pin = CertificatePin("AAAA", "AB:CD:EF", "CN=worker.lan", "Fri Nov 05 2027")

    @Test
    fun anInvalidUrlCannotBeAdded() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api"))
        setContent {
            WorkerUrlDialog(settings, { t -> settings = t(settings) }, {}, lastContact = { null })
        }
        onNodeWithTag("worker-option-server").assertIsSelected()
        onNodeWithTag("worker-add").assertIsNotEnabled()
        onNodeWithTag("worker-new-url").performTextInput("worker.lan")
        onNodeWithTag("worker-add").assertIsNotEnabled()
        onNodeWithText("http:// or https:// and a host").assertExists()
    }

    @Test
    fun aValidUrlIsAddedAndUsed() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api"))
        setContent {
            WorkerUrlDialog(settings, { t -> settings = t(settings) }, {}, lastContact = { null })
        }
        onNodeWithTag("worker-new-url").performTextInput("https://worker.lan:8056/")
        onNodeWithTag("worker-add").assertIsEnabled().performClick()
        assertEquals(listOf(WorkerEndpoint("https://worker.lan:8056")), settings.workerEndpoints)
        onNodeWithTag("worker-option-0").assertIsSelected()
        onNodeWithTag("worker-option-server").performClick()
        assertNull(settings.workerOverrideUrl)
    }

    @Test
    fun trustingACertificatePinsWhatTheWorkerPresentsAndShowsIt() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan"))
        val asked = mutableListOf<String>()
        val tested = mutableListOf<WorkerEndpoint>()
        setContent {
            WorkerUrlDialog(
                settings, { t -> settings = t(settings) }, {},
                fetchCertificate = { asked += it; pin },
                test = { tested += it; "Ready — HTTP 200 in 5 ms" },
                lastContact = { null },
            )
        }
        onNodeWithTag("worker-self-signed-0").performClick()
        waitForIdle()
        assertEquals(listOf("https://worker.lan"), asked)
        assertEquals(pin, settings.workerEndpoints.single().pin)
        onNodeWithTag("worker-pin-0").assertTextContains("AB:CD:EF", substring = true)
        // Pinning tests at once, THROUGH the new pin — no second press of Test.
        assertEquals(listOf(WorkerEndpoint("https://worker.lan", pin)), tested)
        onNodeWithTag("worker-result-0").assertTextContains("HTTP 200", substring = true)
        onNodeWithTag("worker-self-signed-0").performClick()
        assertNull(settings.workerEndpoints.single().pin)
    }

    @Test
    fun aFailedFetchSaysWhyAndPinsNothing() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan"))
        setContent {
            WorkerUrlDialog(
                settings, { t -> settings = t(settings) }, {},
                fetchCertificate = { throw IllegalStateException("connection refused") },
                lastContact = { null },
            )
        }
        onNodeWithTag("worker-self-signed-0").performClick()
        waitForIdle()
        onNodeWithTag("worker-result-0").assertTextContains("connection refused", substring = true)
        assertNull(settings.workerEndpoints.single().pin)
    }

    @Test
    fun httpHasNoCertificateSwitchAndSaysItIsUnencrypted() = runComposeUiTest {
        val settings: UploadSettings = defaultUploadSettings("https://api/api").withWorkerAdded("http://10.0.2.2:8056")
        setContent { WorkerUrlDialog(settings, {}, {}, lastContact = { null }) }
        onNodeWithTag("worker-self-signed-0").assertDoesNotExist()
        onNodeWithText("unencrypted", substring = true).assertExists()
    }

    @Test
    fun testShowsTheResultAndTheLastContactRefreshes() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan"))
        var contact: String? = null
        setContent {
            WorkerUrlDialog(
                settings, { t -> settings = t(settings) }, {},
                test = { contact = "✓ 0s ago · ${it.url} · uploaded"; "Ready — HTTP 200 in 12 ms" },
                lastContact = { contact },
            )
        }
        onNodeWithTag("worker-last-contact").assertTextContains("none yet", substring = true)
        onNodeWithTag("worker-test-0").performClick()
        waitForIdle()
        onNodeWithTag("worker-result-0").assertTextContains("HTTP 200", substring = true)
        onNodeWithTag("worker-last-contact").assertTextContains("worker.lan", substring = true)
    }

    /**
     * The background drain keeps contacting the worker while the dialog is open;
     * the line must follow it without a press of Test (2026-11-06: it went on
     * showing a refused connection after the pin that fixed it).
     */
    @Test
    fun theLastContactFollowsTheBackgroundUploadsWithoutATest() = runComposeUiTest {
        val settings = defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan")
        var contact: String? = "✗ 3s ago · https://worker.lan · upload: ConnectException"
        mainClock.autoAdvance = false
        setContent { WorkerUrlDialog(settings, {}, {}, lastContact = { contact }) }
        mainClock.advanceTimeByFrame()
        onNodeWithTag("worker-last-contact").assertTextContains("ConnectException", substring = true)
        contact = "✓ 0s ago · https://worker.lan · uploaded"
        mainClock.advanceTimeBy(1_100)
        onNodeWithTag("worker-last-contact").assertTextContains("uploaded", substring = true)
    }

    @Test
    fun removingTheSelectedWorkerGoesBackToTheServer() = runComposeUiTest {
        var settings by mutableStateOf(defaultUploadSettings("https://api/api").withWorkerAdded("https://worker.lan"))
        setContent { WorkerUrlDialog(settings, { t -> settings = t(settings) }, {}, lastContact = { null }) }
        onNodeWithTag("worker-remove-0").performClick()
        assertEquals(emptyList(), settings.workerEndpoints)
        onNodeWithTag("worker-option-server").assertIsSelected()
    }
}
