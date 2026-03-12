import SwiftUI
import AVFoundation

private let bgColor = Color(red: 0x0A/255.0, green: 0x0A/255.0, blue: 0x0F/255.0)
private let textSubtle = Color.white.opacity(0.25)
private let textDimmed = Color.white.opacity(0.1)
private let purpleAccent = Color(red: 0.655, green: 0.545, blue: 0.980).opacity(0.8)
private let tealAccent = Color(red: 0.078, green: 0.945, blue: 0.584).opacity(0.8)
private let fieldBg = Color.white.opacity(0.06)
private let fieldBorder = Color.white.opacity(0.1)

// Legal theme colors
private let legalAmber = Color(red: 0.831, green: 0.533, blue: 0.039)  // #D4880A
private let legalGold = Color(red: 0.855, green: 0.667, blue: 0.125)   // #DAA520
private let legalBright = Color(red: 0.961, green: 0.784, blue: 0.314) // #F5C850
private let legalBg = Color(red: 0.102, green: 0.071, blue: 0.039)     // #1a120a

// MARK: - Typewriter Tagline

struct TypewriterText: View {
    let phrases: [String]
    @State private var displayedText = ""
    @State private var phraseIndex = 0
    @State private var charIndex = 0
    @State private var isDeleting = false
    @State private var showCursor = true
    @State private var timer: Timer?
    @State private var cursorTimer: Timer?

    var body: some View {
        HStack(spacing: 0) {
            Text(displayedText)
                .font(.system(size: 13, weight: .light))
                .foregroundColor(.white.opacity(0.35))

            Rectangle()
                .fill(Color(red: 0.655, green: 0.545, blue: 0.980).opacity(0.5))
                .frame(width: 1, height: 14)
                .opacity(showCursor ? 1 : 0)
        }
        .frame(height: 20)
        .onAppear { startCursorBlink(); startTyping() }
        .onDisappear { timer?.invalidate(); cursorTimer?.invalidate() }
    }

    private func startCursorBlink() {
        cursorTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in
            showCursor.toggle()
        }
    }

    private func startTyping() {
        let phrase = phrases[phraseIndex]
        timer = Timer.scheduledTimer(withTimeInterval: isDeleting ? 0.02 : 0.04, repeats: true) { t in
            if isDeleting {
                if !displayedText.isEmpty {
                    displayedText.removeLast()
                } else {
                    t.invalidate()
                    isDeleting = false
                    phraseIndex = (phraseIndex + 1) % phrases.count
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { startTyping() }
                }
            } else {
                if charIndex < phrase.count {
                    displayedText.append(phrase[phrase.index(phrase.startIndex, offsetBy: charIndex)])
                    charIndex += 1
                } else {
                    t.invalidate()
                    charIndex = 0
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
                        isDeleting = true
                        startTyping()
                    }
                }
            }
        }
    }
}

struct ContentView: View {
    @StateObject private var viewModel = VoiceAIViewModel()
    @State private var hasPermission = false
    @State private var showForm = true

    @State private var nameField = ""
    @State private var subjectField = ""
    @State private var gradeField = ""
    @State private var languageField = "English"
    @State private var typeField = ""

    var agentType: String = ""

    // Staggered fade-in states
    @State private var showTitle = false
    @State private var showSubtitle = false
    @State private var showTagline = false
    @State private var showOrb = false
    @State private var showStatus = false
    @State private var showFooter = false

    private let languages = ["English", "Hindi", "Hinglish"]
    private let agentTypes = ["MentalHealth", "legalAdviser", "FinanceGuru"]

    private var activeType: String { typeField.isEmpty ? agentType : typeField }
    private var isLegal: Bool { activeType == "legalAdviser" }

    private var defaultTaglinePhrases: [String] {
        [
            "I'm Maya, your mental health companion",
            "Share how you feel, I'm here to listen",
            "Breathing exercises & coping tips available"
        ]
    }

    private var legalTaglinePhrases: [String] {
        [
            "Ask about IPC, BNS & Indian Constitution",
            "Get instant answers on legal sections",
            "Understand your rights under Indian law"
        ]
    }

    private var titleGradientColors: [Color] {
        if isLegal {
            return [legalAmber, legalGold]
        } else {
            return [
                Color(red: 0.655, green: 0.545, blue: 0.980),
                Color(red: 0.388, green: 0.400, blue: 0.945),
            ]
        }
    }

    private var titleText: String {
        isLegal ? "AI Legal Guru" : "Voice AI Assistant"
    }

    private var sessionSubtitleText: String {
        isLegal ? "Your AI guide to Indian law" : "Talk in Hindi or English \u{2014} powered by real-time AI"
    }

    private var footerText: String {
        isLegal
            ? "Ask about BNS, IPC, Constitution & more \u{2014} 24/7"
            : "Ask anything \u{2014} available 24/7 in English and Hindi"
    }

    var body: some View {
        ZStack {
            (isLegal ? legalBg : bgColor).ignoresSafeArea()

            if showForm && (viewModel.state == .idle || viewModel.state == .disconnected) {
                formView
                    .transition(.opacity)
            } else {
                sessionView
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: showForm)
        .onAppear {
            checkMicPermission()
            if typeField.isEmpty && !agentType.isEmpty {
                typeField = agentType
            }
            if typeField.isEmpty {
                typeField = agentTypes.first ?? "MentalHealth"
            }
        }
    }

    private func typeDisplayName(_ type: String) -> String {
        switch type {
        case "legalAdviser": return "Legal"
        case "MentalHealth": return "Mental Health"
        case "FinanceGuru": return "Finance"
        default: return type
        }
    }

    // MARK: - Form View

    private var formView: some View {
        GeometryReader { geo in
            ScrollView {
                VStack(spacing: 20) {
                    Spacer().frame(height: 0)

                    Text(titleText)
                        .font(.system(size: 28, weight: .semibold, design: .rounded))
                        .tracking(-0.5)
                        .foregroundStyle(
                            LinearGradient(
                                colors: titleGradientColors,
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )

                    Text("Tell us about yourself to get started")
                        .font(.system(size: 14, weight: .light))
                        .foregroundColor(textSubtle)

                    VStack(spacing: 14) {
                        formField(icon: "person.fill", placeholder: "Your Name", text: $nameField)
                        formField(icon: "bubble.left.fill", placeholder: isLegal ? "Legal topic to discuss" : "Mental health topic to discuss", text: $subjectField)

                        HStack(spacing: 10) {
                            Image(systemName: "globe")
                                .foregroundColor(isLegal ? legalGold : purpleAccent)
                                .frame(width: 20)

                            Picker("Language", selection: $languageField) {
                                ForEach(languages, id: \.self) { lang in
                                    Text(lang).tag(lang)
                                }
                            }
                            .pickerStyle(.segmented)
                            .colorMultiply(isLegal ? legalAmber : Color(red: 0.655, green: 0.545, blue: 0.980))
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .background(fieldBg)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(fieldBorder, lineWidth: 1)
                        )

                        // Type picker
                        HStack(spacing: 10) {
                            Image(systemName: "sparkles")
                                .foregroundColor(isLegal ? legalGold : purpleAccent)
                                .frame(width: 20)

                            Picker("Type", selection: $typeField) {
                                ForEach(agentTypes, id: \.self) { type in
                                    Text(typeDisplayName(type)).tag(type)
                                }
                            }
                            .pickerStyle(.segmented)
                            .colorMultiply(isLegal ? legalAmber : Color(red: 0.655, green: 0.545, blue: 0.980))
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
                                colors: isLegal
                                    ? [legalAmber, legalGold]
                                    : [
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

                    Text(footerText)
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
                .foregroundColor(isLegal ? legalGold : purpleAccent)
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
            // Top section: title + subtitle + tagline
            VStack(spacing: 6) {
                Text(titleText)
                    .font(.system(size: 28, weight: .semibold, design: .rounded))
                    .tracking(-0.5)
                    .foregroundStyle(
                        LinearGradient(
                            colors: titleGradientColors,
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .opacity(showTitle ? 1 : 0)
                    .offset(y: showTitle ? 0 : 12)
                    .animation(.easeOut(duration: 0.8), value: showTitle)

                Text(sessionSubtitleText)
                    .font(.system(size: 13, weight: .light))
                    .tracking(0.3)
                    .foregroundColor(textSubtle)
                    .opacity(showSubtitle ? 1 : 0)
                    .offset(y: showSubtitle ? 0 : 12)
                    .animation(.easeOut(duration: 0.8), value: showSubtitle)

                TypewriterText(phrases: isLegal ? legalTaglinePhrases : defaultTaglinePhrases)
                    .opacity(showTagline ? 1 : 0)
                    .offset(y: showTagline ? 0 : 12)
                    .animation(.easeOut(duration: 0.8), value: showTagline)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 60)

            // Center: orb takes all available space
            Spacer()

            VStack(spacing: 0) {
                OrbView(state: viewModel.state, audioLevel: viewModel.audioLevel, isLegal: isLegal)
                    .onTapGesture { handleTap() }
                    .frame(maxWidth: .infinity)
                    .scaleEffect(showOrb ? 1 : 0.92)
                    .opacity(showOrb ? 1 : 0)
                    .animation(.easeOut(duration: 0.8), value: showOrb)

                Spacer().frame(height: 28)

                Text(statusText)
                    .font(.system(size: 15, weight: .medium))
                    .tracking(0.5)
                    .foregroundColor(statusColor)
                    .animation(.easeInOut(duration: 0.4), value: viewModel.state)
                    .frame(maxWidth: .infinity)
                    .opacity(showStatus ? 1 : 0)
                    .offset(y: showStatus ? 0 : 12)
                    .animation(.easeOut(duration: 0.8), value: showStatus)

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

                Text(footerText)
                    .font(.system(size: 12, weight: .light))
                    .tracking(0.3)
                    .foregroundColor(textDimmed)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }
            .frame(maxWidth: .infinity)
            .padding(.bottom, 30)
            .opacity(showFooter ? 1 : 0)
            .offset(y: showFooter ? 0 : 12)
            .animation(.easeOut(duration: 0.8), value: showFooter)
        }
        .onAppear {
            // Reset states for fresh animation
            showTitle = false
            showSubtitle = false
            showTagline = false
            showOrb = false
            showStatus = false
            showFooter = false

            DispatchQueue.main.asyncAfter(deadline: .now() + 0.0) { showTitle = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { showSubtitle = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { showTagline = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { showOrb = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { showStatus = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { showFooter = true }
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
        case .speaking: return isLegal ? legalBright : tealAccent
        case .listening: return isLegal ? legalGold : purpleAccent
        case .connecting: return Color.white.opacity(0.4)
        default: return textSubtle
        }
    }

    private func startSession() {
        viewModel.userInfo = UserInfo(
            name: nameField,
            subject: subjectField,
            grade: gradeField,
            language: languageField,
            type: activeType
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
