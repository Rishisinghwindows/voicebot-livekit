import SwiftUI
import AVFoundation

private let bgColor = Color(red: 0x0A/255.0, green: 0x0A/255.0, blue: 0x0F/255.0)
private let textSubtle = Color.white.opacity(0.25)
private let textDimmed = Color.white.opacity(0.1)
private let purpleAccent = Color(red: 0.655, green: 0.545, blue: 0.980).opacity(0.8)
private let tealAccent = Color(red: 0.078, green: 0.945, blue: 0.584).opacity(0.8)
private let fieldBg = Color.white.opacity(0.06)
private let fieldBorder = Color.white.opacity(0.1)

struct ContentView: View {
    @StateObject private var viewModel = VoiceAIViewModel()
    @State private var hasPermission = false
    @State private var showForm = true

    @State private var nameField = ""
    @State private var subjectField = ""
    @State private var gradeField = ""
    @State private var languageField = "English"

    private let languages = ["English", "Hindi", "Hinglish"]

    var body: some View {
        ZStack {
            bgColor.ignoresSafeArea()

            if showForm && (viewModel.state == .idle || viewModel.state == .disconnected) {
                formView
                    .transition(.opacity)
            } else {
                sessionView
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: showForm)
        .onAppear { checkMicPermission() }
    }

    // MARK: - Form View

    private var formView: some View {
        GeometryReader { geo in
            ScrollView {
                VStack(spacing: 20) {
                    Spacer().frame(height: 0)

                    Text("Voice AI Assistant")
                        .font(.system(size: 28, weight: .semibold, design: .rounded))
                        .tracking(-0.5)
                        .foregroundStyle(
                            LinearGradient(
                                colors: [
                                    Color(red: 0.655, green: 0.545, blue: 0.980),
                                    Color(red: 0.388, green: 0.400, blue: 0.945),
                                ],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )

                    Text("Tell us about yourself to get started")
                        .font(.system(size: 14, weight: .light))
                        .foregroundColor(textSubtle)

                    VStack(spacing: 14) {
                        formField(icon: "person.fill", placeholder: "Your Name", text: $nameField)
                        formField(icon: "book.fill", placeholder: "Subject (e.g. Math, Science)", text: $subjectField)
                        formField(icon: "graduationcap.fill", placeholder: "Grade / Class", text: $gradeField)

                        HStack(spacing: 10) {
                            Image(systemName: "globe")
                                .foregroundColor(purpleAccent)
                                .frame(width: 20)

                            Picker("Language", selection: $languageField) {
                                ForEach(languages, id: \.self) { lang in
                                    Text(lang).tag(lang)
                                }
                            }
                            .pickerStyle(.segmented)
                            .colorMultiply(Color(red: 0.655, green: 0.545, blue: 0.980))
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .background(fieldBg)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(fieldBorder, lineWidth: 1)
                        )
                    }
                    .padding(.horizontal, 32)

                    Button(action: { startSession() }) {
                        HStack(spacing: 8) {
                            Image(systemName: "mic.fill")
                            Text("Start Conversation")
                                .font(.system(size: 16, weight: .semibold))
                        }
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(
                            LinearGradient(
                                colors: [
                                    Color(red: 0.545, green: 0.361, blue: 0.965),
                                    Color(red: 0.388, green: 0.400, blue: 0.945),
                                ],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .cornerRadius(14)
                    }
                    .padding(.horizontal, 32)
                    .padding(.top, 4)

                    Text("Ask anything \u{2014} available 24/7 in English and Hindi")
                        .font(.system(size: 12, weight: .light))
                        .tracking(0.3)
                        .foregroundColor(textDimmed)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)
                        .padding(.top, 4)

                    Spacer().frame(height: 0)
                }
                .frame(maxWidth: .infinity)
                .frame(minHeight: geo.size.height)
            }
            .scrollDismissesKeyboard(.interactively)
        }
    }

    private func formField(icon: String, placeholder: String, text: Binding<String>) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .foregroundColor(purpleAccent)
                .frame(width: 20)

            TextField("", text: text, prompt: Text(placeholder).foregroundColor(textSubtle))
                .foregroundColor(.white)
                .font(.system(size: 15))
                .autocorrectionDisabled()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(fieldBg)
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(fieldBorder, lineWidth: 1)
        )
    }

    // MARK: - Session View (orb centered)

    private var sessionView: some View {
        VStack(spacing: 0) {
            // Top section: title
            VStack(spacing: 6) {
                Text("Voice AI Assistant")
                    .font(.system(size: 28, weight: .semibold, design: .rounded))
                    .tracking(-0.5)
                    .foregroundStyle(
                        LinearGradient(
                            colors: [
                                Color(red: 0.655, green: 0.545, blue: 0.980),
                                Color(red: 0.388, green: 0.400, blue: 0.945),
                            ],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )

                Text("Powered by real-time voice intelligence")
                    .font(.system(size: 13, weight: .light))
                    .tracking(0.3)
                    .foregroundColor(textSubtle)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 60)

            // Center: orb takes all available space
            Spacer()

            VStack(spacing: 0) {
                OrbView(state: viewModel.state, audioLevel: viewModel.audioLevel)
                    .onTapGesture { handleTap() }
                    .frame(maxWidth: .infinity)

                Spacer().frame(height: 28)

                Text(statusText)
                    .font(.system(size: 15, weight: .medium))
                    .tracking(0.5)
                    .foregroundColor(statusColor)
                    .animation(.easeInOut(duration: 0.4), value: viewModel.state)
                    .frame(maxWidth: .infinity)

                if viewModel.state == .listening || viewModel.state == .speaking {
                    let m = viewModel.elapsedSeconds / 60
                    let s = viewModel.elapsedSeconds % 60
                    Text(String(format: "%02d:%02d", m, s))
                        .font(.system(size: 12, weight: .light).monospacedDigit())
                        .foregroundColor(textDimmed)
                        .padding(.top, 8)
                        .transition(.opacity)
                        .frame(maxWidth: .infinity)
                }
            }

            Spacer()

            // Bottom section: footer
            VStack(spacing: 4) {
                if !nameField.isEmpty {
                    Text("Talking as \(nameField)")
                        .font(.system(size: 12, weight: .light))
                        .foregroundColor(textSubtle)
                }

                Text("Ask anything \u{2014} available 24/7 in English and Hindi")
                    .font(.system(size: 12, weight: .light))
                    .tracking(0.3)
                    .foregroundColor(textDimmed)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }
            .frame(maxWidth: .infinity)
            .padding(.bottom, 30)
        }
    }

    // MARK: - State

    private var statusText: String {
        switch viewModel.state {
        case .idle: return "Tap the orb to start talking"
        case .connecting: return "Connecting..."
        case .listening: return "Listening..."
        case .speaking: return "Speaking..."
        case .disconnected: return "Tap to reconnect"
        }
    }

    private var statusColor: Color {
        switch viewModel.state {
        case .speaking: return tealAccent
        case .listening: return purpleAccent
        case .connecting: return Color.white.opacity(0.4)
        default: return textSubtle
        }
    }

    private func startSession() {
        viewModel.userInfo = UserInfo(
            name: nameField,
            subject: subjectField,
            grade: gradeField,
            language: languageField
        )
        showForm = false
        if !hasPermission {
            requestMicPermission()
        } else {
            viewModel.toggle()
        }
    }

    private func handleTap() {
        if viewModel.state == .idle || viewModel.state == .disconnected {
            if !hasPermission {
                requestMicPermission()
            } else {
                viewModel.toggle()
            }
        } else {
            viewModel.toggle()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                if viewModel.state == .idle {
                    showForm = true
                }
            }
        }
    }

    private func checkMicPermission() {
        hasPermission = AVAudioSession.sharedInstance().recordPermission == .granted
    }

    private func requestMicPermission() {
        AVAudioSession.sharedInstance().requestRecordPermission { granted in
            DispatchQueue.main.async {
                hasPermission = granted
                if granted { viewModel.toggle() }
            }
        }
    }
}
