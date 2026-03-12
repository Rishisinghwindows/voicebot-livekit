# VoiceAI App — iOS

A native SwiftUI voice assistant app powered by [LiveKit](https://livekit.io) with a 12-layer audio-reactive animated orb, multi-agent support, and dynamic theming.

<p align="center">
  <img src="docs/screenshots/form.png" width="250" alt="Form Screen" />
  <img src="docs/screenshots/session.png" width="250" alt="Session Screen" />
  <img src="docs/screenshots/legal.png" width="250" alt="Legal Theme" />
</p>

## Features

- **Real-time voice conversations** — WebRTC-powered via LiveKit
- **12-layer animated orb** — Audio-reactive visualization with organic blobs, glow layers, floating particles, glass highlights, and a connecting spinner
- **Multi-agent support** — Mental Health (Maya), Legal Adviser (Indian law), Finance Guru
- **Dynamic theming** — Purple/teal default, amber/gold for legal — switches instantly when agent type changes
- **Typewriter taglines** — Rotating animated phrases with blinking cursor
- **Staggered fade-in** — Sequential element animations on session start (0ms → 800ms)
- **Deep linking** — `voiceai://open?type=legalAdviser` opens directly into an agent
- **Multilingual** — English, Hindi, Hinglish
- **Session timer** — Live elapsed time display during conversations
- **Auto retry** — 3 automatic reconnection attempts on failure

## Requirements

| Requirement | Version |
|---|---|
| iOS | 16.0+ |
| Xcode | 15.0+ |
| Swift | 5.9+ |

## Architecture

```
VoiceAIApp-iOS/
│
├── project.yml                     # XcodeGen project definition
├── VoiceAIApp.xcodeproj/           # Generated Xcode project
│
└── VoiceAIApp/
    ├── VoiceAIAppApp.swift         # @main entry point, audio session, deep links
    ├── ContentView.swift           # Form + Session UI, theming, TypewriterText
    ├── OrbView.swift               # 12-layer Canvas-based animated orb
    ├── VoiceAIViewModel.swift      # LiveKit room management, state machine
    ├── AudioAnalyzer.swift         # Real-time RMS audio level analysis
    ├── TokenService.swift          # Backend token fetcher + UserInfo model
    ├── Info.plist                   # URL scheme, mic permission, orientations
    └── Assets.xcassets/            # App icon and color assets
```

### Layer Diagram

```
┌─────────────────────────────────────────────────────┐
│                    VoiceAIAppApp                     │
│              (Entry Point + Deep Links)              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                    ContentView                       │
│     ┌──────────────┐    ┌────────────────────┐      │
│     │   Form View  │───▶│   Session View     │      │
│     │ (name, lang, │    │ (orb, status,      │      │
│     │  type picker) │    │  timer, footer)    │      │
│     └──────────────┘    └────────────────────┘      │
│           │                      │                   │
│           │              ┌───────▼───────┐           │
│           │              │   OrbView     │           │
│           │              │ (12 Canvas    │           │
│           │              │  layers)      │           │
│           │              └───────────────┘           │
│           │              ┌───────────────┐           │
│           │              │TypewriterText │           │
│           │              └───────────────┘           │
└───────────┼──────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────┐
│                VoiceAIViewModel                       │
│            (@MainActor ObservableObject)              │
│                                                       │
│  ┌────────┐  ┌──────────┐  ┌───────────────┐        │
│  │ State  │  │  Timer   │  │ Audio Monitor │        │
│  │Machine │  │  Task    │  │    Task       │        │
│  └────┬───┘  └──────────┘  └───────┬───────┘        │
│       │                            │                  │
│  ┌────▼────────────┐    ┌──────────▼──────────┐      │
│  │   LiveKit Room  │    │   AudioAnalyzer    │      │
│  │   (RoomDelegate)│    │   (AudioRenderer)  │      │
│  └────┬────────────┘    └─────────────────────┘      │
└───────┼──────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────┐
│                  TokenService                         │
│         GET /token?name=&subject=&type=              │
│                                                       │
│  Backend ──▶ JWT Token ──▶ LiveKit WebSocket         │
└──────────────────────────────────────────────────────┘
```

### State Machine

```
            ┌──────────┐
            │   idle   │◀──── disconnect()
            └────┬─────┘
                 │ toggle()
            ┌────▼─────┐
            │connecting│──── retry (up to 3x)
            └────┬─────┘
                 │ success
            ┌────▼─────┐
     ┌─────▶│listening │◀────┐
     │      └────┬─────┘     │
     │           │ audio     │ audio
     │           │ > 0.06    │ ≤ 0.06
     │      ┌────▼─────┐     │
     │      │ speaking │─────┘
     │      └──────────┘
     │
     │      ┌────────────┐
     └──────│disconnected│◀── room error / all retries failed
            └────────────┘
```

### Orb Rendering Layers

The `OrbView` renders 12 layers using SwiftUI `Canvas` at 60fps:

| Layer | Description | Audio Reactive |
|-------|---|:---:|
| 1 | Deep ambient glow | - |
| 2 | Mid glow gradient | - |
| 3 | Inner glow halo | - |
| 4 | Rotating conic ring | Yes |
| 5 | Orb body (dark base) | - |
| 6 | 7 organic blobs (compound oscillation) | Yes |
| 7 | Energy waves (3 concentric) | Yes |
| 8 | Glass highlight (top-left) | - |
| 9 | Edge vignette | - |
| 10 | Rim light | Yes |
| 11 | 12 floating particles | Yes |
| 12 | 8-dot connecting spinner | - |

### Theming

| Property | Default (Purple/Teal) | Legal (Amber/Gold) |
|---|---|---|
| Background | `#0A0A0F` | `#1A120A` |
| Accent | Purple `#A78BFA` | Gold `#DAA520` |
| Speaking | Teal `#14F195` | Bright Gold `#F5C850` |
| Idle blobs | Purple tones | Amber tones |
| Active blobs | Teal/cyan tones | Bright gold tones |
| Ring | Purple → Teal | Amber → Bright Gold |

## Setup

### 1. Clone & Generate Project

```bash
git clone git@github.com:Rishisinghwindows/voicebot-livekit.git
cd voicebot-livekit/VoiceAIApp-iOS

# Generate Xcode project (requires XcodeGen)
brew install xcodegen
xcodegen generate
```

### 2. Open in Xcode

```bash
open VoiceAIApp.xcodeproj
```

Xcode will automatically resolve the LiveKit Swift Package dependency.

### 3. Configure

Update the backend URLs in the source files:

| File | Constant | Default |
|---|---|---|
| `TokenService.swift` | `baseURL` | `https://advancedvoiceagent.xappy.io` |
| `VoiceAIViewModel.swift` | `livekitUrl` | `wss://apiadvancedvoiceagent.xappy.io` |

### 4. Build & Run

- Select your target device or simulator
- Set your Development Team in Signing & Capabilities
- Build and run (Cmd+R)

## Deep Linking

The app registers the `voiceai://` URL scheme. Open a specific agent type directly:

```
voiceai://open?type=legalAdviser
voiceai://open?type=MentalHealth
voiceai://open?type=FinanceGuru
```

Test from terminal:
```bash
xcrun simctl openurl booted "voiceai://open?type=legalAdviser"
```

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| [LiveKit Client SDK](https://github.com/livekit/client-sdk-swift) | 2.0.0+ | WebRTC voice connection |
| LiveKit WebRTC | 137.7151.x | WebRTC framework |
| Swift Protobuf | 1.35.x | Protocol buffer serialization |
| Swift Collections | 1.2.x | LiveKit internal dependency |

## Token Flow

```
App                     Backend                  LiveKit
 │                        │                        │
 │  GET /token?name=...   │                        │
 │───────────────────────▶│                        │
 │  { token, url }        │                        │
 │◀───────────────────────│                        │
 │                        │                        │
 │  WSS connect(token)    │                        │
 │─────────────────────────────────────────────────▶
 │                        │                        │
 │  Mic audio stream ────────────────────────────▶ │
 │  Agent audio stream ◀────────────────────────────
 │                        │                        │
```

## SPM Package

Looking for a reusable drop-in component? Check out [VoiceAIKit](https://github.com/Rishisinghwindows/VoiceAIKit) — the same voice agent packaged as a Swift Package Manager library that can be added to any iOS app with one line of code.

## License

MIT
