package com.ubudy.voiceai

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.livekit.android.LiveKit
import io.livekit.android.room.Room
import io.livekit.android.events.RoomEvent
import io.livekit.android.room.track.AudioTrack
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class ConnectionState {
    IDLE, CONNECTING, LISTENING, SPEAKING, DISCONNECTED
}

class VoiceAIViewModel(application: Application) : AndroidViewModel(application) {
    private val _state = MutableStateFlow(ConnectionState.IDLE)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    private val _audioLevel = MutableStateFlow(0f)
    val audioLevel: StateFlow<Float> = _audioLevel.asStateFlow()

    private val _elapsedSeconds = MutableStateFlow(0)
    val elapsedSeconds: StateFlow<Int> = _elapsedSeconds.asStateFlow()

    var userInfo = UserInfo()

    private var room: Room? = null
    private val agentAudioAnalyzer = AudioAnalyzer()
    private var timerJob: Job? = null
    private var eventCollectionJob: Job? = null
    private var audioLevelJob: Job? = null
    private var speakingHoldFrames = 0

    fun toggle() {
        if (_state.value == ConnectionState.CONNECTING) return
        if (_state.value == ConnectionState.IDLE || _state.value == ConnectionState.DISCONNECTED) {
            connect()
        } else {
            disconnect()
        }
    }

    private fun connect() {
        viewModelScope.launch {
            _state.value = ConnectionState.CONNECTING
            val livekitUrl = "wss://apiadvancedvoiceagent.xappy.io"
            val maxRetries = 3

            for (attempt in 1..maxRetries) {
                try {
                    Log.i(TAG, "Connecting (attempt $attempt/$maxRetries)...")
                    val tokenResponse = TokenClient.service.getToken(
                        name = userInfo.name,
                        subject = userInfo.subject,
                        grade = userInfo.grade,
                        language = userInfo.language
                    )

                    val newRoom = LiveKit.create(getApplication())
                    room = newRoom

                    eventCollectionJob = viewModelScope.launch {
                        newRoom.events.events.collect { event: RoomEvent ->
                            handleEvent(event)
                        }
                    }

                    newRoom.connect(livekitUrl, tokenResponse.token)
                    newRoom.localParticipant.setMicrophoneEnabled(true)
                    Log.i(TAG, "Connected! Mic enabled. Participants: ${newRoom.remoteParticipants.size}")

                    _state.value = ConnectionState.LISTENING
                    startTimer()
                    return@launch // success
                } catch (e: Exception) {
                    Log.e(TAG, "Attempt $attempt failed: ${e.message}")
                    cleanUp()
                    if (attempt < maxRetries) {
                        delay(1000)
                    }
                }
            }

            Log.e(TAG, "All $maxRetries attempts failed")
            _state.value = ConnectionState.DISCONNECTED
        }
    }

    private fun handleEvent(event: RoomEvent) {
        when (event) {
            is RoomEvent.TrackSubscribed -> {
                val track = event.track
                if (track is AudioTrack) {
                    Log.i(TAG, "Agent audio track subscribed")
                    agentAudioAnalyzer.attachToTrack(track)
                    startAudioLevelMonitoring()
                }
            }
            is RoomEvent.Disconnected -> {
                Log.i(TAG, "Disconnected")
                cleanUp()
                _state.value = ConnectionState.DISCONNECTED
            }
            is RoomEvent.ParticipantConnected -> {
                Log.i(TAG, "Participant joined: ${event.participant.identity}")
            }
            else -> {}
        }
    }

    private fun startAudioLevelMonitoring() {
        audioLevelJob?.cancel()
        audioLevelJob = viewModelScope.launch {
            agentAudioAnalyzer.level.collect { level ->
                _audioLevel.value = level

                if (_state.value != ConnectionState.CONNECTING) {
                    if (level > 0.06f) {
                        speakingHoldFrames = 25
                        if (_state.value != ConnectionState.SPEAKING) {
                            _state.value = ConnectionState.SPEAKING
                        }
                    } else if (speakingHoldFrames > 0) {
                        speakingHoldFrames--
                    } else if (_state.value != ConnectionState.LISTENING) {
                        _state.value = ConnectionState.LISTENING
                    }
                }
            }
        }
    }

    private fun startTimer() {
        _elapsedSeconds.value = 0
        timerJob?.cancel()
        timerJob = viewModelScope.launch {
            while (true) {
                delay(1000)
                _elapsedSeconds.value += 1
            }
        }
    }

    fun disconnect() {
        viewModelScope.launch {
            cleanUp()
            _state.value = ConnectionState.IDLE
        }
    }

    private fun cleanUp() {
        timerJob?.cancel()
        timerJob = null
        eventCollectionJob?.cancel()
        eventCollectionJob = null
        audioLevelJob?.cancel()
        audioLevelJob = null
        agentAudioAnalyzer.detach()
        speakingHoldFrames = 0
        _audioLevel.value = 0f
        room?.disconnect()
        room = null
    }

    override fun onCleared() {
        super.onCleared()
        cleanUp()
    }

    companion object {
        private const val TAG = "VoiceAI"
    }
}
