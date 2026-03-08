package com.ubudy.voiceai

import io.livekit.android.room.track.AudioTrack
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import livekit.org.webrtc.AudioTrackSink
import java.nio.ByteBuffer
import java.nio.ByteOrder

class AudioAnalyzer {
    private val _level = MutableStateFlow(0f)
    val level: StateFlow<Float> = _level.asStateFlow()

    private var smoothedLevel = 0f
    private val lerpFactor = 0.12f

    private val sink = AudioTrackSink { data, bitsPerSample, sampleRate, channels, frames, _ ->
        val rms = calculateRms(data, bitsPerSample, frames * channels)
        smoothedLevel += (rms - smoothedLevel) * lerpFactor
        _level.value = smoothedLevel
    }

    private var attachedTrack: livekit.org.webrtc.AudioTrack? = null

    fun attachToTrack(track: AudioTrack) {
        detach()
        val webrtcTrack = track.rtcTrack as? livekit.org.webrtc.AudioTrack ?: return
        webrtcTrack.addSink(sink)
        attachedTrack = webrtcTrack
    }

    fun detach() {
        attachedTrack?.removeSink(sink)
        attachedTrack = null
        smoothedLevel = 0f
        _level.value = 0f
    }

    private fun calculateRms(data: ByteBuffer, bitsPerSample: Int, sampleCount: Int): Float {
        if (sampleCount == 0) return 0f
        val buffer = data.duplicate().order(ByteOrder.LITTLE_ENDIAN)
        buffer.rewind()

        var sumSquares = 0.0
        val bytesPerSample = bitsPerSample / 8
        val count = minOf(sampleCount, buffer.remaining() / bytesPerSample)

        when (bitsPerSample) {
            16 -> {
                val shortBuffer = buffer.asShortBuffer()
                for (i in 0 until count) {
                    val sample = shortBuffer.get(i).toFloat() / Short.MAX_VALUE
                    sumSquares += sample * sample
                }
            }
            else -> return 0f
        }

        val rms = Math.sqrt(sumSquares / count).toFloat()
        return (rms * 3f).coerceIn(0f, 1f)
    }
}
