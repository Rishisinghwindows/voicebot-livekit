import SwiftUI
import AVFoundation

@main
struct VoiceAIAppApp: App {
    @State private var agentType: String = ""

    init() {
        configureAudioSession()
    }

    var body: some Scene {
        WindowGroup {
            ContentView(agentType: agentType)
                .preferredColorScheme(.dark)
                .onOpenURL { url in
                    if let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
                       let typeParam = components.queryItems?.first(where: { $0.name == "type" })?.value {
                        agentType = typeParam
                    }
                }
        }
    }

    private func configureAudioSession() {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(
                .playAndRecord,
                mode: .voiceChat,
                options: [.defaultToSpeaker, .allowBluetooth]
            )
            try session.setActive(true)
        } catch {
            print("Audio session configuration failed: \(error)")
        }
    }
}
