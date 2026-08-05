package cz.hillview.clockvideo

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.Typeface
import com.google.zxing.qrcode.encoder.Encoder
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel

/**
 * Draws the phone-time QR panel onto a frame canvas.
 *
 * The geometry replicates drawQrPanel() in the old ClockVideoRecorder.svelte
 * so panel_rect semantics stay identical for video_time_correction.py: a white
 * panel at a fixed (16,16) position, QR with a 2-module quiet zone, and the
 * raw ms number as a human-readable line below. Deliberately no HH:MM:SS
 * rendering, so the pipeline's clock-digit OCR can never mistake our overlay
 * for the camera's clock.
 *
 * All frames of a session encode a 13-digit number, so the QR version — and
 * with it the module count and panel geometry — is constant; compute once per
 * frame size.
 */
class QrTimePanel(frameWidth: Int, frameHeight: Int) {
    private companion object {
        const val QUIET_MODULES = 2
        const val PANEL_X = 16
        const val PANEL_Y = 16
    }

    // Encoder.encode returns the raw module matrix with no margin; the quiet
    // zone is drawn by us as part of the white panel.
    private val moduleCount: Int =
        Encoder.encode(sampleStamp(), ErrorCorrectionLevel.M).matrix.width

    private val moduleSize: Int
    private val qrPx: Int
    private val pad: Int
    private val fontPx: Int
    val rect: Rect

    private val whitePaint = Paint().apply { color = Color.WHITE }
    private val blackPaint = Paint().apply { color = Color.BLACK }
    private val textPaint = Paint().apply {
        color = Color.BLACK
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
        isAntiAlias = true
    }

    init {
        val qrSizeTarget = (minOf(frameWidth, frameHeight) * 0.3).toInt()
        moduleSize = qrSizeTarget / (moduleCount + 2 * QUIET_MODULES)
        qrPx = moduleSize * (moduleCount + 2 * QUIET_MODULES)
        pad = moduleSize
        fontPx = maxOf(12, qrPx / 9)
        textPaint.textSize = fontPx.toFloat()
        val panelW = qrPx + 2 * pad
        val panelH = qrPx + fontPx + 3 * pad
        rect = Rect(PANEL_X, PANEL_Y, PANEL_X + panelW, PANEL_Y + panelH)
    }

    private fun sampleStamp(): String = System.currentTimeMillis().toString()

    fun draw(canvas: Canvas, stampMs: Long) {
        val payload = stampMs.toString()
        val matrix = Encoder.encode(payload, ErrorCorrectionLevel.M).matrix

        canvas.drawRect(rect, whitePaint)

        val ox = rect.left + pad + QUIET_MODULES * moduleSize
        val oy = rect.top + pad + QUIET_MODULES * moduleSize
        val n = matrix.width
        for (r in 0 until n) {
            for (c in 0 until n) {
                if (matrix.get(c, r).toInt() == 1) {
                    canvas.drawRect(
                        (ox + c * moduleSize).toFloat(),
                        (oy + r * moduleSize).toFloat(),
                        (ox + (c + 1) * moduleSize).toFloat(),
                        (oy + (r + 1) * moduleSize).toFloat(),
                        blackPaint,
                    )
                }
            }
        }

        // drawText's y is the baseline; the JS canvas used textBaseline=top at
        // y = panelTop + qrPx + 2*pad — convert with the font's ascent.
        val textTop = (rect.top + qrPx + 2 * pad).toFloat()
        canvas.drawText(payload, (rect.left + pad).toFloat(), textTop - textPaint.fontMetrics.ascent, textPaint)
    }
}
