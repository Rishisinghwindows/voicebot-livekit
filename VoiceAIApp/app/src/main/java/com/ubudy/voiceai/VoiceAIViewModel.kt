package com.ubudy.voiceai

import android.app.Application
import android.media.AudioManager
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.livekit.android.LiveKit
import io.livekit.android.room.Room
import io.livekit.android.events.RoomEvent
import io.livekit.android.room.track.AudioTrack
import io.livekit.android.room.track.LocalAudioTrack
import io.livekit.android.room.track.Track
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
    private val userMicAnalyzer = AudioAnalyzer()
    private var timerJob: Job? = null
    private var userMicMonitorJob: Job? = null
    private var eventCollectionJob: Job? = null
    private var audioLevelJob: Job? = null
    private var speakingHoldFrames = 0

    fun toggle() {
        Log.i(TAG, "toggle() called, current state: ${_state.value}")
        if (_state.value == ConnectionState.CONNECTING) {
            Log.w(TAG, "Already connecting, ignoring tap")
            return
        }
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
                    Log.i(TAG, "=== Connection attempt $attempt/$maxRetries ===")
                    Log.i(TAG, "Fetching token with userInfo: name='${userInfo.name}', subject='${userInfo.subject}', grade='${userInfo.grade}', language='${userInfo.language}'")

                    val tokenResponse = TokenClient.service.getToken(
                        name = userInfo.name,
                        subject = userInfo.subject,
                        grade = userInfo.grade,
                        language = userInfo.language,
                        type = userInfo.type
                    )
                    Log.i(TAG, "Token received (${tokenResponse.token.length} chars), url: ${tokenResponse.url}")

                    // Route audio to speakerphone
                    val audioManager = getApplication<Application>().getSystemService(android.content.Context.AUDIO_SERVICE) as AudioManager
                    audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
                    audioManager.isSpeakerphoneOn = true
                    Log.i(TAG, "Audio routed to speaker")

                    Log.i(TAG, "Creating LiveKit room...")
                    val newRoom = LiveKit.create(getApplication())
                    room = newRoom

                    // Collect events
                    eventCollectionJob = viewModelScope.launch {
                        Log.i(TAG, "Event collection started")
                        newRoom.events.events.collect { event: RoomEvent ->
                            handleEvent(event)
                        }
                    }

                    Log.i(TAG, "Connecting to $livekitUrl ...")
                    newRoom.connect(livekitUrl, tokenResponse.token)
                    Log.i(TAG, "Room connected! Room name: ${newRoom.name}, SID: ${newRoom.sid}")

                    Log.i(TAG, "Enabling microphone...")
                    newRoom.localParticipant.setMicrophoneEnabled(true)
                    Log.i(TAG, "Mic enabled. Local participant: ${newRoom.localParticipant.identity}")

                    // Monitor user mic audio to verify it's capturing
                    val localAudioTrack = newRoom.localParticipant.trackPublications.values
                        .firstOrNull { it.kind == Track.Kind.AUDIO }?.track as? AudioTrack
                    if (localAudioTrack != null) {
                        Log.i(TAG, "Attaching user mic analyzer to local audio track")
                        userMicAnalyzer.attachToTrack(localAudioTrack)
                        userMicMonitorJob = viewModelScope.launch {
                            var logCount = 0
                            userMicAnalyzer.level.collect { level ->
                                logCount++
                                if (logCount <= 5 || (logCount % 200 == 0) || (level > 0.05f && logCount % 50 == 0)) {
                                    Log.i(TAG, "[USER-MIC] level=${"%.4f".format(level)} (sample #$logCount)")
                                }
                            }
                        }
                    } else {
                        Log.w(TAG, "Could not find local audio track to monitor mic!")
                        newRoom.localParticipant.trackPublications.forEach { (_, pub) ->
                            Log.w(TAG, "  Local pub: kind=${pub.kind}, track=${pub.track?.javaClass?.simpleName}")
                        }
                    }

                    Log.i(TAG, "Remote participants: ${newRoom.remoteParticipants.size}")
                    newRoom.remoteParticipants.forEach { (id, p) ->
                        Log.i(TAG, "  Remote: ${p.identity} (sid=$id), tracks=${p.trackPublications.size}")
                        p.trackPublications.forEach { (_, pub) ->
                            Log.i(TAG, "    Track: kind=${pub.kind}, subscribed=${pub.subscribed}, track=${pub.track?.javaClass?.simpleName}")
                        }
                    }

                    _state.value = ConnectionState.LISTENING
                    startTimer()
                    Log.i(TAG, "=== Connected successfully ===")
                    return@launch
                } catch (e: Exception) {
                    Log.e(TAG, "Attempt $attempt failed: ${e.message}", e)
                    cleanUp()
                    if (attempt < maxRetries) {
                        Log.i(TAG, "Retrying in 1 second...")
                        delay(1000)
                    }
                }
            }

            Log.e(TAG, "All $maxRetries attempts failed")
            _state.value = ConnectionState.DISCONNECTED
        }
    }

    private fun handleEvent(event: RoomEvent) {
        Log.d(TAG, "Event: ${event.javaClass.simpleName}")
        when (event) {
            is RoomEvent.TrackSubscribed -> {
                Log.i(TAG, "TrackSubscribed: kind=${event.track.kind}, type=${event.track.javaClass.simpleName}")
                Log.i(TAG, "  from participant: ${event.participant.identity}")
                if (event.track is AudioTrack) {
                    Log.i(TAG, "  -> Attaching audio analyzer to agent track")
                    agentAudioAnalyzer.attachToTrack(event.track as AudioTrack)
                    startAudioLevelMonitoring()
                } else {
                    Log.w(TAG, "  -> Not an AudioTrack, skipping")
                }
            }
            is RoomEvent.TrackPublished -> {
                Log.i(TAG, "TrackPublished: kind=${event.publication.kind}, from ${event.participant.identity}")
            }
            is RoomEvent.TrackUnsubscribed -> {
                Log.i(TAG, "TrackUnsubscribed: ${event.track.kind} from ${event.participant.identity}")
            }
            is RoomEvent.Disconnected -> {
                Log.i(TAG, "Room disconnected")
                cleanUp()
                _state.value = ConnectionState.DISCONNECTED
            }
            is RoomEvent.ParticipantConnected -> {
                Log.i(TAG, "Participant joined: ${event.participant.identity}, metadata: ${event.participant.metadata}")
            }
            is RoomEvent.ParticipantDisconnected -> {
                Log.i(TAG, "Participant left: ${event.participant.identity}")
            }
            is RoomEvent.Reconnecting -> {
                Log.w(TAG, "Reconnecting...")
            }
            is RoomEvent.Reconnected -> {
                Log.i(TAG, "Reconnected!")
            }
            is RoomEvent.ActiveSpeakersChanged -> {
                val agentSpeaking = event.speakers.any {
                    it.identity?.value?.startsWith("agent-") == true
                }
                if (_state.value != ConnectionState.CONNECTING && _state.value != ConnectionState.IDLE && _state.value != ConnectionState.DISCONNECTED) {
                    if (agentSpeaking) {
                        speakingHoldFrames = 25
                        if (_state.value != ConnectionState.SPEAKING) {
                            Log.i(TAG, "Agent speaking (via ActiveSpeakers)")
                            _state.value = ConnectionState.SPEAKING
                            _audioLevel.value = 0.5f
                        }
                    } else if (speakingHoldFrames > 0) {
                        speakingHoldFrames--
                    } else if (_state.value != ConnectionState.LISTENING) {
                        Log.i(TAG, "Agent stopped speaking (via ActiveSpeakers)")
                        _state.value = ConnectionState.LISTENING
                        _audioLevel.value = 0f
                    }
                }
            }
            is RoomEvent.ConnectionQualityChanged -> {
                Log.d(TAG, "Connection quality: ${event.quality} for ${event.participant.identity}")
            }
            else -> {}
        }
    }

    private fun startAudioLevelMonitoring() {
        audioLevelJob?.cancel()
        Log.i(TAG, "Starting audio level monitoring")
        var stateChangeCount = 0
        audioLevelJob = viewModelScope.launch {
            agentAudioAnalyzer.level.collect { level ->
                _audioLevel.value = level

                if (_state.value != ConnectionState.CONNECTING) {
                    val prevState = _state.value
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
                    if (prevState != _state.value) {
                        stateChangeCount++
                        Log.i(TAG, "State: $prevState -> ${_state.value} (level=${"%.3f".format(level)}, holdFrames=$speakingHoldFrames, changes=$stateChangeCount)")
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
        Log.i(TAG, "disconnect() called")
        viewModelScope.launch {
            cleanUp()
            _state.value = ConnectionState.IDLE
        }
    }

    private fun cleanUp() {
        Log.i(TAG, "cleanUp()")
        timerJob?.cancel()
        timerJob = null
        eventCollectionJob?.cancel()
        eventCollectionJob = null
        audioLevelJob?.cancel()
        audioLevelJob = null
        agentAudioAnalyzer.detach()
        userMicAnalyzer.detach()
        userMicMonitorJob?.cancel()
        userMicMonitorJob = null
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
