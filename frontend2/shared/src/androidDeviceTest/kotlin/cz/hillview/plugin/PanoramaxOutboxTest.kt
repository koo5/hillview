package cz.hillview.plugin

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.util.Base64
import androidx.test.platform.app.InstrumentationRegistry
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Real Room revisions and the actual PATCH request, with an in-process HTTP interceptor. */
class PanoramaxOutboxTest {
    private val context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
        override fun getApplicationContext(): Context = this
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
            super.getSharedPreferences("panoramax-test-$name", mode)
    }
    private val id = "panoramax-outbox-test"
    private val db get() = PhotoDatabase.getDatabase(context)
    private val outbox get() = PhotoOutbox(context)
    private val sent = mutableListOf<Pair<String, String>>()
    private var duringPush: (() -> Unit)? = null
    private val client = OkHttpClient.Builder().addInterceptor { chain ->
        val request = chain.request()
        assertEquals("PATCH", request.method)
        assertTrue(request.header("Authorization")!!.startsWith("Bearer "))
        val body = okio.Buffer().also { request.body!!.writeTo(it) }.readUtf8()
        sent += request.url.encodedPath to body
        duringPush?.also { duringPush = null }?.invoke()
        Response.Builder().request(request).protocol(Protocol.HTTP_1_1)
            .code(200).message("OK").body("{}".toResponseBody()).build()
    }.build()
    private val pusher get() = PhotoOutboxPusher(context, client, AuthenticationManager(context))

    @Before
    fun prepare() {
        val payload = Base64.encodeToString("""{"sub":"panoramax-test-user"}""".toByteArray(),
            Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        context.getSharedPreferences("hillview_auth", Context.MODE_PRIVATE).edit()
            .putString("auth_token", "header.$payload.signature").commit()
        db.photoDao().deletePhoto(id)
        db.photoDao().insertPhoto(PhotoEntity(
            id = id, filename = "share.jpg", path = "/tmp/share.jpg", latitude = null,
            longitude = null, capturedAt = 1, accuracy = 0.0, width = 4, height = 4,
            fileSize = 16, createdAt = 1,
        ))
    }

    @After
    fun cleanup() {
        db.photoDao().deletePhoto(id)
        context.getSharedPreferences("hillview_auth", Context.MODE_PRIVATE).edit().clear().commit()
    }

    @Test
    fun beforeUploadChoicePersistsAndAfterUploadPushesIt() {
        outbox.setPanoramaxShare(id, true)
        assertTrue(db.photoDao().getPhotoById(id)!!.panoramaxShare)
        assertEquals(true, PhotoOutbox(context).forPhotos(listOf(id))[id]!!.panoramaxShare)
        assertEquals(0, outbox.pushablePendingCount())
        assertEquals(0, pusher.pushAll("http://localhost/api"))
        assertTrue(sent.isEmpty())
        db.photoDao().updateServerPhotoId(id, "server-id")
        assertEquals(1, outbox.pushablePendingCount())
        pusher.afterUpload(id, "http://localhost/api")
        assertEquals(listOf("/api/photos/server-id" to """{"panoramax_share":true}"""), sent)
        assertEquals(0, outbox.pendingCount())
        assertEquals(0, pusher.pushAll("http://localhost/api"))
    }

    @Test
    fun editMadeDuringPushStaysPendingAndSendsTheNewValue() {
        db.photoDao().updateServerPhotoId(id, "server-id")
        outbox.setPanoramaxShare(id, true)
        duringPush = { outbox.setPanoramaxShare(id, false) }
        assertEquals(1, pusher.pushAll("http://localhost/api"))
        assertEquals(1, outbox.pendingCount())
        assertFalse(db.photoDao().getPhotoById(id)!!.panoramaxShare)
        assertEquals(false, outbox.panoramaxShareOf(id))
        assertEquals(1, pusher.pushAll("http://localhost/api"))
        assertEquals("""{"panoramax_share":false}""", sent.last().second)
        assertEquals(0, outbox.pendingCount())
    }
}
