package cz.hillview.plugin

import android.util.Log
import kotlin.math.*

/**
 * Madgwick AHRS algorithm implementation for Android
 * Based on the original C implementation by Sebastian Madgwick
 *
 * This algorithm provides more accurate orientation estimates by fusing
 * accelerometer, gyroscope, and magnetometer data.
 */
class MadgwickAHRS(
    private var sampleFreq: Float = 100f,  // Sample frequency in Hz
    private var beta: Float = 0.1f         // Algorithm gain
) {
    companion object {
        private const val TAG = "🢄MadgwickAHRS"
    }
    // Quaternion of sensor frame relative to auxiliary frame
    private var q0 = 1.0f
    private var q1 = 0.0f
    private var q2 = 0.0f
    private var q3 = 0.0f

    /**
     * Update quaternion with gyroscope and accelerometer data
     */
    fun updateIMU(gx: Float, gy: Float, gz: Float, ax: Float, ay: Float, az: Float) {
        var recipNorm: Float
        var s0: Float
        var s1: Float
        var s2: Float
        var s3: Float
        var qDot1: Float
        var qDot2: Float
        var qDot3: Float
        var qDot4: Float
        val _2q0: Float
        val _2q1: Float
        val _2q2: Float
        val _2q3: Float
        val _4q0: Float
        val _4q1: Float
        val _4q2: Float
        val _8q1: Float
        val _8q2: Float
        var q0q0: Float
        var q1q1: Float
        var q2q2: Float
        var q3q3: Float

        // Rate of change of quaternion from gyroscope
        qDot1 = 0.5f * (-q1 * gx - q2 * gy - q3 * gz)
        qDot2 = 0.5f * (q0 * gx + q2 * gz - q3 * gy)
        qDot3 = 0.5f * (q0 * gy - q1 * gz + q3 * gx)
        qDot4 = 0.5f * (q0 * gz + q1 * gy - q2 * gx)

        // Compute feedback only if accelerometer measurement valid
        if (!((ax == 0.0f) && (ay == 0.0f) && (az == 0.0f))) {
            // Normalise accelerometer measurement
            recipNorm = invSqrt(ax * ax + ay * ay + az * az)
            val axNorm = ax * recipNorm
            val ayNorm = ay * recipNorm
            val azNorm = az * recipNorm

            // Auxiliary variables to avoid repeated arithmetic
            _2q0 = 2.0f * q0
            _2q1 = 2.0f * q1
            _2q2 = 2.0f * q2
            _2q3 = 2.0f * q3
            _4q0 = 4.0f * q0
            _4q1 = 4.0f * q1
            _4q2 = 4.0f * q2
            _8q1 = 8.0f * q1
            _8q2 = 8.0f * q2
            q0q0 = q0 * q0
            q1q1 = q1 * q1
            q2q2 = q2 * q2
            q3q3 = q3 * q3

            // Gradient decent algorithm corrective step
            s0 = _4q0 * q2q2 + _2q2 * axNorm + _4q0 * q1q1 - _2q1 * ayNorm
            s1 = _4q1 * q3q3 - _2q3 * axNorm + 4.0f * q0q0 * q1 - _2q0 * ayNorm - _4q1 + _8q1 * q1q1 + _8q1 * q2q2 + _4q1 * azNorm
            s2 = 4.0f * q0q0 * q2 + _2q0 * axNorm + _4q2 * q3q3 - _2q3 * ayNorm - _4q2 + _8q2 * q1q1 + _8q2 * q2q2 + _4q2 * azNorm
            s3 = 4.0f * q1q1 * q3 - _2q1 * axNorm + 4.0f * q2q2 * q3 - _2q2 * ayNorm
            recipNorm = invSqrt(s0 * s0 + s1 * s1 + s2 * s2 + s3 * s3)
            s0 *= recipNorm
            s1 *= recipNorm
            s2 *= recipNorm
            s3 *= recipNorm

            // Apply feedback step
            qDot1 -= beta * s0
            qDot2 -= beta * s1
            qDot3 -= beta * s2
            qDot4 -= beta * s3
        }

        // Integrate rate of change of quaternion to yield quaternion
        q0 += qDot1 * (1.0f / sampleFreq)
        q1 += qDot2 * (1.0f / sampleFreq)
        q2 += qDot3 * (1.0f / sampleFreq)
        q3 += qDot4 * (1.0f / sampleFreq)

        // Normalise quaternion
        recipNorm = invSqrt(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3)
        q0 *= recipNorm
        q1 *= recipNorm
        q2 *= recipNorm
        q3 *= recipNorm

        // Log quaternion occasionally
        if (Math.random() < 0.01) {
            Log.v(TAG, "🔄 IMU quaternion: [${q0.format(3)}, ${q1.format(3)}, ${q2.format(3)}, ${q3.format(3)}]")
        }
    }

    /**
     * Update quaternion with gyroscope, accelerometer and magnetometer data
     */
    fun update(gx: Float, gy: Float, gz: Float, ax: Float, ay: Float, az: Float, mx: Float, my: Float, mz: Float) {
        var recipNorm: Float
        var s0: Float
        var s1: Float
        var s2: Float
        var s3: Float
        var qDot1: Float
        var qDot2: Float
        var qDot3: Float
        var qDot4: Float
        var hx: Float
        var hy: Float
        val _2q0mx: Float
        val _2q0my: Float
        val _2q0mz: Float
        val _2q1mx: Float
        val _2bx: Float
        val _2bz: Float
        val _4bx: Float
        val _4bz: Float
        val _2q0: Float
        val _2q1: Float
        val _2q2: Float
        val _2q3: Float
        val _2q0q2: Float
        val _2q2q3: Float
        var q0q0: Float
        var q0q1: Float
        var q0q2: Float
        var q0q3: Float
        var q1q1: Float
        var q1q2: Float
        var q1q3: Float
        var q2q2: Float
        var q2q3: Float
        var q3q3: Float

        // Rate of change of quaternion from gyroscope
        qDot1 = 0.5f * (-q1 * gx - q2 * gy - q3 * gz)
        qDot2 = 0.5f * (q0 * gx + q2 * gz - q3 * gy)
        qDot3 = 0.5f * (q0 * gy - q1 * gz + q3 * gx)
        qDot4 = 0.5f * (q0 * gz + q1 * gy - q2 * gx)

        // Compute feedback only if accelerometer measurement valid and magnetometer measurement valid
        if (!((ax == 0.0f) && (ay == 0.0f) && (az == 0.0f)) && !((mx == 0.0f) && (my == 0.0f) && (mz == 0.0f))) {
            // Normalise accelerometer measurement
            recipNorm = invSqrt(ax * ax + ay * ay + az * az)
            val axNorm = ax * recipNorm
            val ayNorm = ay * recipNorm
            val azNorm = az * recipNorm

            // Normalise magnetometer measurement
            recipNorm = invSqrt(mx * mx + my * my + mz * mz)
            val mxNorm = mx * recipNorm
            val myNorm = my * recipNorm
            val mzNorm = mz * recipNorm

            // Auxiliary variables to avoid repeated arithmetic
            _2q0mx = 2.0f * q0 * mxNorm
            _2q0my = 2.0f * q0 * myNorm
            _2q0mz = 2.0f * q0 * mzNorm
            _2q1mx = 2.0f * q1 * mxNorm
            _2q0 = 2.0f * q0
            _2q1 = 2.0f * q1
            _2q2 = 2.0f * q2
            _2q3 = 2.0f * q3
            _2q0q2 = 2.0f * q0 * q2
            _2q2q3 = 2.0f * q2 * q3
            q0q0 = q0 * q0
            q0q1 = q0 * q1
            q0q2 = q0 * q2
            q0q3 = q0 * q3
            q1q1 = q1 * q1
            q1q2 = q1 * q2
            q1q3 = q1 * q3
            q2q2 = q2 * q2
            q2q3 = q2 * q3
            q3q3 = q3 * q3

            // Reference direction of Earth's magnetic field
            hx = mxNorm * q0q0 - _2q0my * q3 + _2q0mz * q2 + mxNorm * q1q1 + _2q1 * myNorm * q2 + _2q1 * mzNorm * q3 - mxNorm * q2q2 - mxNorm * q3q3
            hy = _2q0mx * q3 + myNorm * q0q0 - _2q0mz * q1 + _2q1mx * q2 - myNorm * q1q1 + myNorm * q2q2 + _2q2 * mzNorm * q3 - myNorm * q3q3
            _2bx = sqrt(hx * hx + hy * hy)
            _2bz = -_2q0mx * q2 + _2q0my * q1 + mzNorm * q0q0 + _2q1mx * q3 - mzNorm * q1q1 + _2q2 * myNorm * q3 - mzNorm * q2q2 + mzNorm * q3q3
            _4bx = 2.0f * _2bx
            _4bz = 2.0f * _2bz

            // Gradient decent algorithm corrective step
            s0 = -_2q2 * (2.0f * q1q3 - _2q0q2 - axNorm) + _2q1 * (2.0f * q0q1 + _2q2q3 - ayNorm) - _2bz * q2 * (_2bx * (0.5f - q2q2 - q3q3) + _2bz * (q1q3 - q0q2) - mxNorm) + (-_2bx * q3 + _2bz * q1) * (_2bx * (q1q2 - q0q3) + _2bz * (q0q1 + q2q3) - myNorm) + _2bx * q2 * (_2bx * (q0q2 + q1q3) + _2bz * (0.5f - q1q1 - q2q2) - mzNorm)
            s1 = _2q3 * (2.0f * q1q3 - _2q0q2 - axNorm) + _2q0 * (2.0f * q0q1 + _2q2q3 - ayNorm) - 4.0f * q1 * (1 - 2.0f * q1q1 - 2.0f * q2q2 - azNorm) + _2bz * q3 * (_2bx * (0.5f - q2q2 - q3q3) + _2bz * (q1q3 - q0q2) - mxNorm) + (_2bx * q2 + _2bz * q0) * (_2bx * (q1q2 - q0q3) + _2bz * (q0q1 + q2q3) - myNorm) + (_2bx * q3 - _4bz * q1) * (_2bx * (q0q2 + q1q3) + _2bz * (0.5f - q1q1 - q2q2) - mzNorm)
            s2 = -_2q0 * (2.0f * q1q3 - _2q0q2 - axNorm) + _2q3 * (2.0f * q0q1 + _2q2q3 - ayNorm) - 4.0f * q2 * (1 - 2.0f * q1q1 - 2.0f * q2q2 - azNorm) + (-_4bx * q2 - _2bz * q0) * (_2bx * (0.5f - q2q2 - q3q3) + _2bz * (q1q3 - q0q2) - mxNorm) + (_2bx * q1 + _2bz * q3) * (_2bx * (q1q2 - q0q3) + _2bz * (q0q1 + q2q3) - myNorm) + (_2bx * q0 - _4bz * q2) * (_2bx * (q0q2 + q1q3) + _2bz * (0.5f - q1q1 - q2q2) - mzNorm)
            s3 = _2q1 * (2.0f * q1q3 - _2q0q2 - axNorm) + _2q2 * (2.0f * q0q1 + _2q2q3 - ayNorm) + (-_4bx * q3 + _2bz * q1) * (_2bx * (0.5f - q2q2 - q3q3) + _2bz * (q1q3 - q0q2) - mxNorm) + (-_2bx * q0 + _2bz * q2) * (_2bx * (q1q2 - q0q3) + _2bz * (q0q1 + q2q3) - myNorm) + _2bx * q1 * (_2bx * (q0q2 + q1q3) + _2bz * (0.5f - q1q1 - q2q2) - mzNorm)

            recipNorm = invSqrt(s0 * s0 + s1 * s1 + s2 * s2 + s3 * s3)
            s0 *= recipNorm
            s1 *= recipNorm
            s2 *= recipNorm
            s3 *= recipNorm

            // Apply feedback step
            qDot1 -= beta * s0
            qDot2 -= beta * s1
            qDot3 -= beta * s2
            qDot4 -= beta * s3
        }

        // Integrate rate of change of quaternion to yield quaternion
        q0 += qDot1 * (1.0f / sampleFreq)
        q1 += qDot2 * (1.0f / sampleFreq)
        q2 += qDot3 * (1.0f / sampleFreq)
        q3 += qDot4 * (1.0f / sampleFreq)

        // Normalise quaternion
        recipNorm = invSqrt(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3)
        q0 *= recipNorm
        q1 *= recipNorm
        q2 *= recipNorm
        q3 *= recipNorm

        // Log quaternion occasionally
        if (Math.random() < 0.01) {
            Log.v(TAG, "🔄 IMU quaternion: [${q0.format(3)}, ${q1.format(3)}, ${q2.format(3)}, ${q3.format(3)}]")
        }
    }

    /**
     * Get Euler angles from quaternion
     * @return Triple of (yaw, pitch, roll) in radians
     */
    fun getEulerAngles(): Triple<Float, Float, Float> {
        // Yaw (heading) - using standard aerospace convention
        val yaw = atan2(2f * (q0 * q3 + q1 * q2), 1f - 2f * (q2 * q2 + q3 * q3))

        // Pitch
        val sinp = 2f * (q0 * q2 - q3 * q1)
        val pitch = when {
            abs(sinp) >= 1 -> {
                Log.w(TAG, "⚠️ Gimbal lock detected (sinp=${sinp.format(3)})")
                (PI / 2).toFloat() * sinp.sign
            }
            else -> asin(sinp)
        }

        // Roll
        val roll = atan2(2f * (q0 * q1 + q2 * q3), 1f - 2f * (q1 * q1 + q2 * q2))

        // Log Euler angles occasionally
        if (Math.random() < 0.02) {
            val yawDeg = Math.toDegrees(yaw.toDouble()).toFloat()
            val pitchDeg = Math.toDegrees(pitch.toDouble()).toFloat()
            val rollDeg = Math.toDegrees(roll.toDouble()).toFloat()
            Log.v(TAG, "📐 Euler angles: Yaw=${yawDeg.format(1)}°, " +
                      "Pitch=${pitchDeg.format(1)}°, " +
                      "Roll=${rollDeg.format(1)}°")
        }

        return Triple(yaw, pitch, roll)
    }

    /**
     * Fast inverse square root
     */
    private fun invSqrt(x: Float): Float {
        return 1.0f / sqrt(x)
    }

    // Extension function for float formatting
    private fun Float.format(digits: Int) = "%.${digits}f".format(this)

    fun reset() {
        q0 = 1.0f
        q1 = 0.0f
        q2 = 0.0f
        q3 = 0.0f
        Log.i(TAG, "🔄 Madgwick AHRS reset - quaternion initialized to [1, 0, 0, 0]")
        Log.d(TAG, "  Sample frequency: ${sampleFreq}Hz")
        Log.d(TAG, "  Beta (gain): $beta")
    }

    fun setGain(beta: Float) {
        val oldBeta = this.beta
        this.beta = beta
        Log.i(TAG, "🎯 Beta (gain) changed: $oldBeta → $beta")
    }

    fun setSampleFrequency(freq: Float) {
        val oldFreq = this.sampleFreq
        this.sampleFreq = freq
        Log.i(TAG, "📡 Sample frequency changed: ${oldFreq}Hz → ${freq}Hz")
    }
}
