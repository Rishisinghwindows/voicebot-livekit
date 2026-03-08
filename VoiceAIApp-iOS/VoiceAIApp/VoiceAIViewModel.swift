import Foundation
import LiveKit
import Combine

enum ConnectionState {
    case idle, connecting, listening, speaking, disconnected
}

@MainActor
class VoiceAIViewModel: ObservableObject {
    @Published var state: ConnectionState = .idle
    @Published var audioLevel: Float = 0
    @Published var elapsedSeconds: Int = 0

    var userInfo = UserInfo()

    private var room: Room?
    private let agentAudioAnalyzer = AudioAnalyzer()
    private var timerTask: Task<Void, Never>?
    private var audioLevelTask: Task<Void, Never>?
    private var speakingHoldFrames = 0

    func toggle() {
        if state == .connecting { return } // prevent double tap
        if state == .idle || state == .disconnected {
            connect()
        } else {
            disconnect()
        }
    }

    private func connect() {
        Task {
            state = .connecting
            let livekitUrl = "wss://apiadvancedvoiceagent.xappy.io"
            let maxRetries = 3

            for attempt in 1...maxRetries {
                do {
                    let tokenResponse = try await TokenService.fetchToken(userInfo: userInfo)

                    let connectOptions = ConnectOptions(
                        autoSubscribe: true,
                        primaryTransportConnectTimeout: 30,
                        publisherTransportConnectTimeout: 30
                    )

                    let newRoom = Room(delegate: self)
                    room = newRoom

                    print("[VoiceAI] Connecting (attempt \(attempt)/\(maxRetries))...")
                    try await newRoom.connect(url: livekitUrl, token: tokenResponse.token, connectOptions: connectOptions)
                    print("[VoiceAI] Connected! Enabling mic...")
                    try await newRoom.localParticipant.setMicrophone(enabled: true)
                    print("[VoiceAI] Mic enabled. Participants: \(newRoom.remoteParticipants.count)")

                    state = .listening
                    startTimer()
                    return // success
                } catch {
                    print("[VoiceAI] Attempt \(attempt) failed: \(error.localizedDescription)")
                    cleanUp()
                    if attempt < maxRetries {
                        try? await Task.sleep(nanoseconds: 1_000_000_000)
                    }
                }
            }

            print("[VoiceAI] All \(maxRetries) attempts failed")
            state = .disconnected
        }
    }

    func disconnect() {
        cleanUp()
        state = .idle
    }

    private func startAudioLevelMonitoring() {
        audioLevelTask?.cancel()
        audioLevelTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 33_000_000) // ~30fps
                let level = agentAudioAnalyzer.level
                handleAudioLevel(level)
            }
        }
    }

    private func handleAudioLevel(_ level: Float) {
        audioLevel = level

        guard state != .connecting else { return }

        if level > 0.06 {
            speakingHoldFrames = 25
            if state != .speaking {
                state = .speaking
            }
        } else if speakingHoldFrames > 0 {
            speakingHoldFrames -= 1
        } else if state != .listening {
            state = .listening
        }
    }

    private func startTimer() {
        elapsedSeconds = 0
        timerTask?.cancel()
        timerTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                if !Task.isCancelled {
                    elapsedSeconds += 1
                }
            }
        }
    }

    private func cleanUp() {
        timerTask?.cancel()
        timerTask = nil
        audioLevelTask?.cancel()
        audioLevelTask = nil
        agentAudioAnalyzer.detach()
        speakingHoldFrames = 0
        audioLevel = 0
        let roomToDisconnect = room
        room = nil
        Task {
            await roomToDisconnect?.disconnect()
        }
    }

    deinit {
        timerTask?.cancel()
        audioLevelTask?.cancel()
    }
}

extension VoiceAIViewModel: RoomDelegate {
    nonisolated func room(_ room: Room, participant: RemoteParticipant, didSubscribeTrack publication: RemoteTrackPublication) {
        print("[VoiceAI] Track subscribed: \(publication.kind), from: \(participant.identity)")
        if let audioTrack = publication.track as? RemoteAudioTrack {
            print("[VoiceAI] Attaching audio analyzer to agent track")
            Task { @MainActor in
                agentAudioAnalyzer.attachToTrack(audioTrack)
                startAudioLevelMonitoring()
            }
        }
    }

    nonisolated func room(_ room: Room, participant: RemoteParticipant, didPublishTrack publication: RemoteTrackPublication) {
        print("[VoiceAI] Remote participant published track: \(publication.kind)")
    }

    nonisolated func room(_ room: Room, participantDidConnect participant: RemoteParticipant) {
        print("[VoiceAI] Participant joined: \(participant.identity)")
    }

    nonisolated func room(_ room: Room, didDisconnectWithError error: LiveKitError?) {
        print("[VoiceAI] Disconnected: \(String(describing: error))")
        Task { @MainActor in
            cleanUp()
            state = .disconnected
        }
    }
}
