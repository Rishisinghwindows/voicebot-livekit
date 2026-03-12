package com.ubudy.voiceai

import android.util.Log
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
    private val lerpFactor = 0.15f
    private var renderCount = 0

    private val sink = AudioTrackSink { data, bitsPerSample, sampleRate, channels, frames, _ ->
        val rms = calculateRms(data, bitsPerSample, frames * channels)
        smoothedLevel += (rms - smoothedLevel) * lerpFactor
        _level.value = smoothedLevel
        renderCount++
        if (renderCount <= 5) {
            Log.i(TAG, "render #$renderCount: rms=${"%.4f".format(rms)} smoothed=${"%.4f".format(smoothedLevel)} bits=$bitsPerSample rate=$sampleRate ch=$channels frames=$frames")
        }
        if (renderCount % 100 == 0) {
            Log.d(TAG, "render #$renderCount: level=${"%.4f".format(smoothedLevel)}")
        }
    }

    private var attachedTrack: livekit.org.webrtc.AudioTrack? = null

    fun attachToTrack(track: AudioTrack) {
        detach()
        val webrtcTrack = track.rtcTrack as? livekit.org.webrtc.AudioTrack
        if (webrtcTrack == null) {
            Log.e(TAG, "Failed to cast track.rtcTrack to webrtc AudioTrack! Type: ${track.rtcTrack?.javaClass?.name}")
            return
        }
        webrtcTrack.addSink(sink)
        attachedTrack = webrtcTrack
        renderCount = 0
        Log.i(TAG, "Attached to agent audio track")
    }

    fun detach() {
        attachedTrack?.removeSink(sink)
        attachedTrack = null
        smoothedLevel = 0f
        _level.value = 0f
        Log.i(TAG, "Detached from audio track")
    }

    private fun calculateRms(data: ByteBuffer, bitsPerSample: Int, sampleCount: Int): Float {
        if (sampleCount == 0) return 0f
        val buffer = data.duplicate().order(ByteOrder.LITTLE_ENDIAN)
        buffer.rewind()

        var sumSquares = 0.0
        val bytesPerSample = bitsPerSample / 8
        val count = minOf(sampleCount, buffer.remaining() / bytesPerSample)

        if (count == 0) {
            if (renderCount <= 3) Log.w(TAG, "Empty buffer: remaining=${buffer.remaining()} bytesPerSample=$bytesPerSample sampleCount=$sampleCount")
            return 0f
        }

        when (bitsPerSample) {
            16 -> {
                val shortBuffer = buffer.asShortBuffer()
                for (i in 0 until count) {
                    val sample = shortBuffer.get(i).toFloat() / Short.MAX_VALUE
                    sumSquares += sample * sample
                }
            }
            32 -> {
                val intBuffer = buffer.asIntBuffer()
                for (i in 0 until count) {
                    val sample = intBuffer.get(i).toFloat() / Int.MAX_VALUE
                    sumSquares += sample * sample
                }
            }
            else -> {
                if (renderCount <= 3) Log.w(TAG, "Unsupported bitsPerSample: $bitsPerSample")
                return 0f
            }
        }

        val rms = Math.sqrt(sumSquares / count).toFloat()
        return (rms * 4f).coerceIn(0f, 1f)
    }

    companion object {
        private const val TAG = "VoiceAI-Audio"
    }
}
