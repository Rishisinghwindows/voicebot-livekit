package com.ubudy.voiceai

import android.app.Application
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

    private var room: Room? = null
    private val agentAudioAnalyzer = AudioAnalyzer()
    private var timerJob: Job? = null
    private var eventCollectionJob: Job? = null
    private var audioLevelJob: Job? = null
    private var speakingHoldFrames = 0

    fun toggle() {
        if (_state.value == ConnectionState.IDLE || _state.value == ConnectionState.DISCONNECTED) {
            connect()
        } else {
            disconnect()
        }
    }

    private fun connect() {
        viewModelScope.launch {
            _state.value = ConnectionState.CONNECTING

            try {
                val tokenResponse = TokenClient.service.getToken()
                // Server returns ws://localhost:7880 — override with public WSS endpoint
                val livekitUrl = "wss://apiadvancedvoiceagent.xappy.io"

                val newRoom = LiveKit.create(getApplication())
                room = newRoom

                eventCollectionJob = viewModelScope.launch {
                    newRoom.events.collect { event ->
                        when (event) {
                            is RoomEvent.TrackSubscribed -> {
                                if (event.track is AudioTrack) {
                                    agentAudioAnalyzer.attachToTrack(event.track as AudioTrack)
                                    startAudioLevelMonitoring()
                                }
                            }
                            is RoomEvent.Disconnected -> {
                                cleanUp()
                                _state.value = ConnectionState.DISCONNECTED
                            }
                            else -> {}
                        }
                    }
                }

                newRoom.connect(livekitUrl, tokenResponse.token)
                newRoom.localParticipant.setMicrophoneEnabled(true)

                _state.value = ConnectionState.LISTENING
                startTimer()
            } catch (e: Exception) {
                e.printStackTrace()
                cleanUp()
                _state.value = ConnectionState.DISCONNECTED
            }
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
}
