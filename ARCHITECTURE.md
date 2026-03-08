# UBudy - Architecture Document

## 1. Overview

UBudy is an AI-powered mental health voice companion that provides empathetic, real-time voice conversations. Users talk to **Maya**, an AI therapist, through a web or mobile interface. The system uses a streaming voice pipeline for low-latency, natural conversations.

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER DEVICES                             │
│                                                                 │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│   │  Web Browser  │     │ Android App  │     │  Phone Call   │   │
│   │  (HTML/JS)    │     │ (React Native│     │  (Twilio SIP) │   │
│   │              │     │  + WebView)  │     │              │   │
│   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘   │
│          │                    │                     │           │
└──────────┼────────────────────┼─────────────────────┼───────────┘
           │                    │                     │
           ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LIVEKIT CLOUD                               │
│              wss://ai-bot-6z15o00o.livekit.cloud                │
│                                                                 │
│   ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐   │
│   │  Room Mgmt   │    │ Audio Routing │    │  Agent Dispatch  │   │
│   │  & Signaling │    │  (WebRTC)    │    │  & Job Queue    │   │
│   └─────────────┘    └──────────────┘    └────────┬────────┘   │
│                                                    │            │
└────────────────────────────────────────────────────┼────────────┘
                                                     │
                                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BACKEND SERVER                              │
│                                                                 │
│   ┌──────────────────┐        ┌─────────────────────────────┐   │
│   │  web_frontend.py │        │         agent.py            │   │
│   │                  │        │                             │   │
│   │  • Serves HTML   │        │  • LiveKit Agent Worker     │   │
│   │  • Token endpoint│        │  • Voice AI Pipeline        │   │
│   │  • Port 54855    │        │  • Session Management       │   │
│   └──────────────────┘        └─────────────┬───────────────┘   │
│                                             │                   │
└─────────────────────────────────────────────┼───────────────────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         │                    │                    │
                         ▼                    ▼                    ▼
                  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
                  │  Deepgram   │    │   OpenAI      │    │   Airtable   │
                  │  (STT)      │    │  (LLM + TTS)  │    │  (Logging)   │
                  └─────────────┘    └──────────────┘    └──────────────┘
```

---

## 2. System Components

### 2.1 Web Frontend (`web_frontend.py`)

**Purpose**: Serves the web UI and generates LiveKit access tokens.

| Aspect       | Detail                                        |
|-------------|-----------------------------------------------|
| **Runtime** | Python `http.server` (stdlib)                  |
| **Port**    | 54855                                          |
| **Endpoints** | `GET /` → HTML page, `GET /token` → JWT token |
| **Deployed** | Behind Nginx reverse proxy at `voiceagent.xappy.io` |

**Token Generation Flow**:
```
Client → GET /token
         ↓
Server generates:
  • user_id:   "user-<random-8-hex>"
  • room_name: "ubudy-<random-6-hex>"
  • JWT token with grants: room_join, publish, subscribe
         ↓
Response: { "token": "<jwt>", "url": "https://ai-bot-6z15o00o.livekit.cloud" }
```

**Web UI Features**:
- Dark theme with animated gradient orbs
- Mood selector chips (Anxious, Sad, Stressed, Lonely, Overwhelmed, Just need to talk)
- Animated voice orb with pulsing rings and audio visualizer bars
- Call timer, rotating affirmations, crisis helpline footer
- Uses `livekit-client` JS SDK (loaded from CDN)

---

### 2.2 Voice Agent (`agent.py`)

**Purpose**: The AI brain — joins LiveKit rooms and conducts voice conversations.

| Aspect       | Detail                                        |
|-------------|-----------------------------------------------|
| **Framework** | LiveKit Agents SDK v1.4.4                    |
| **Identity**  | Maya — bilingual (English/Hindi) AI companion |
| **Max Duration** | 600 seconds (10 min) per call — cost protection |
| **Concurrency** | Multi-process — handles parallel calls       |

**Voice Pipeline (streaming, all components run concurrently)**:
```
User speaks
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  SILERO VAD (Voice Activity Detection)                       │
│  • Detects when user starts/stops speaking                   │
│  • activation_threshold: 0.35 (sensitive)                    │
│  • min_speech_duration: 0.05s (fast detection)               │
│  • min_silence_duration: 0.4s                                │
│  • Enables barge-in (user can interrupt Maya)                │
└──────────────────────┬───────────────────────────────────────┘
                       │ audio frames
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  DEEPGRAM STT (Speech-to-Text)                               │
│  • Model: nova-2                                             │
│  • Language: Hindi (auto-detects English too)                 │
│  • Streaming with interim_results for low latency            │
│  • smart_format + punctuate enabled                          │
└──────────────────────┬───────────────────────────────────────┘
                       │ transcript text
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  OPENAI LLM (Language Model)                                 │
│  • Model: gpt-4o-mini                                        │
│  • Temperature: 0.7                                          │
│  • System prompt: Maya's personality, guidelines, techniques │
│  • Streaming response for word-by-word TTS                   │
└──────────────────────┬───────────────────────────────────────┘
                       │ response text (streamed)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  OPENAI TTS (Text-to-Speech)                                 │
│  • Model: tts-1                                              │
│  • Voice: nova (warm, friendly female)                       │
│  • Streams audio back to user via LiveKit                    │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
                  User hears Maya
```

**Agent Lifecycle**:
```
1. Worker starts → registers with LiveKit Cloud
2. Prewarm: loads Silero VAD model into memory
3. User connects to room → LiveKit dispatches job to agent
4. Agent joins room (audio-only) → creates pipeline
5. Pipeline runs: VAD → STT → LLM → TTS (streaming loop)
6. User disconnects OR 10-min timeout → session closes
7. Call logged to Airtable (caller, duration, transcript)
```

**Event Handlers**:
- `user_input_transcribed` → logs user speech to transcript
- `agent_speech_committed` → logs Maya's responses to transcript

---

### 2.3 Android App (`UBudyApp/`)

**Purpose**: Native Android wrapper that loads the web UI in a WebView.

| Aspect       | Detail                                        |
|-------------|-----------------------------------------------|
| **Framework** | React Native 0.84.1                          |
| **Architecture** | WebView loading `https://voiceagent.xappy.io` |
| **Key Dependency** | `react-native-webview`                    |
| **Min SDK**  | 24 (Android 7.0)                               |

**Permissions**:
- `INTERNET` — network access
- `RECORD_AUDIO` — microphone for voice chat
- `MODIFY_AUDIO_SETTINGS` — audio routing

**Features**:
- Runtime microphone permission request on launch
- Loading indicator while WebView loads
- Error screen with retry button (handles 5xx / network errors)
- Android back button navigates WebView history
- Auto-grants WebView media capture permissions
- Dark status bar matching the web theme

---

## 3. External Services

| Service | Purpose | API/Protocol | Pricing Model |
|---------|---------|-------------|---------------|
| **LiveKit Cloud** | Real-time audio rooms, WebRTC signaling, agent dispatch | WebSocket (WSS) | Per-participant-minute |
| **Deepgram** | Speech-to-Text (nova-2 model) | WebSocket streaming | Per-audio-minute |
| **OpenAI** | LLM (gpt-4o-mini) + TTS (tts-1) | HTTPS REST API (streaming) | Per-token (LLM) + per-character (TTS) |
| **Airtable** | Call log storage (caller, duration, transcript) | HTTPS REST API | Free tier / per-record |
| **Twilio** | SIP trunk for phone call access (optional) | SIP protocol | Per-call-minute |
| **Nginx** | Reverse proxy for `voiceagent.xappy.io` | HTTPS | Self-hosted |

---

## 4. Data Flow — Complete Call Lifecycle

```
Step 1: User opens app/website
        ↓
Step 2: User taps the voice orb
        ↓
Step 3: Client calls GET /token
        ↓
Step 4: Server returns { token, url }
        ↓
Step 5: Client connects to LiveKit room using token
        Client publishes microphone audio track
        ↓
Step 6: LiveKit dispatches job to agent.py worker
        ↓
Step 7: Agent joins the same room
        Agent subscribes to user's audio
        ↓
Step 8: Streaming voice loop begins:
        User audio → Silero VAD → Deepgram STT → OpenAI LLM → OpenAI TTS → User
        ↓
Step 9: User taps stop OR 10-min timeout
        ↓
Step 10: Room disconnects, session closes
         Call logged to Airtable
```

---

## 5. File Structure

```
voicebot/
├── agent.py                 # Voice AI agent (LiveKit + Deepgram + OpenAI)
├── web_frontend.py          # Web server (HTML UI + token endpoint)
├── .env                     # API keys and secrets (not in git)
├── requirements.txt         # Python dependencies
├── Caddyfile                # Caddy reverse proxy config
├── generate_report.py       # Cost report generator
├── UBudy_Cost_Report.pdf    # Cost analysis document
│
└── UBudyApp/                # React Native Android app
    ├── App.tsx              # Main app (WebView + permissions + error handling)
    ├── index.js             # RN entry point
    ├── package.json         # Node dependencies
    ├── android/
    │   ├── app/
    │   │   └── src/main/
    │   │       ├── AndroidManifest.xml    # Permissions
    │   │       ├── assets/
    │   │       │   └── index.android.bundle  # Bundled JS (for APK)
    │   │       └── res/
    │   │           ├── mipmap-*/ic_launcher*.png  # App icons
    │   │           └── values/strings.xml         # App name
    │   └── build.gradle
    └── ios/                 # iOS (not configured)
```

---

## 6. Environment Variables

| Variable | Service | Purpose |
|----------|---------|---------|
| `LIVEKIT_URL` | LiveKit Cloud | WebSocket URL for room connections |
| `LIVEKIT_API_KEY` | LiveKit Cloud | API key for token generation |
| `LIVEKIT_API_SECRET` | LiveKit Cloud | Secret for signing JWT tokens |
| `DEEPGRAM_API_KEY` | Deepgram | Speech-to-Text API access |
| `OPENAI_API_KEY` | OpenAI | LLM (gpt-4o-mini) + TTS (tts-1) |
| `ELEVENLABS_API_KEY` | ElevenLabs | TTS (imported but not actively used — OpenAI TTS used instead) |
| `ELEVENLABS_VOICE_ID` | ElevenLabs | Voice selection (not active) |
| `AIRTABLE_PAT` | Airtable | Personal access token for call logging |
| `AIRTABLE_BASE_ID` | Airtable | Target base for call_logs table |
| `TWILIO_ACCOUNT_SID` | Twilio | SIP trunk for phone calls (optional) |
| `TWILIO_AUTH_TOKEN` | Twilio | SIP authentication (optional) |
| `MAX_CALL_DURATION_SECONDS` | Internal | Cost protection timeout (default: 600) |

---

## 7. Deployment

### Production (Current)
```
voiceagent.xappy.io (Nginx reverse proxy)
        ↓
web_frontend.py (port 54855) — serves HTML + tokens
agent.py dev                  — registers with LiveKit Cloud, handles calls
```

### Running Locally
```bash
# Terminal 1: Web frontend
python web_frontend.py

# Terminal 2: Voice agent
python agent.py dev

# Open: http://localhost:54855
```

### Android APK
```bash
cd UBudyApp
npx react-native bundle --platform android --dev false \
  --entry-file index.js \
  --bundle-output android/app/src/main/assets/index.android.bundle \
  --assets-dest android/app/src/main/res/
cd android && ./gradlew assembleDebug
# APK at: android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 8. Security Considerations

- All API keys stored in `.env` file (not committed to git)
- LiveKit tokens are short-lived JWTs with scoped room permissions
- Each call gets a unique room name (no room reuse)
- CORS enabled on token endpoint (`Access-Control-Allow-Origin: *`)
- 10-minute max call duration prevents runaway API costs
- Crisis detection in system prompt routes users to helplines

---

## 9. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **WebView app** (not native LiveKit SDK) | Faster development, single codebase for web + mobile, the web UI already works well |
| **OpenAI TTS over ElevenLabs** | Simpler integration via LiveKit plugin, consistent API key |
| **gpt-4o-mini over gpt-4o** | Lower cost, sufficient quality for conversational therapy, faster responses |
| **Deepgram nova-2 with Hindi** | Best Hindi + English bilingual accuracy at low latency |
| **Silero VAD with low thresholds** | Sensitive barge-in so users can naturally interrupt Maya |
| **Python stdlib HTTP server** | Minimal dependencies for a simple token+HTML server |
| **Airtable for logging** | Zero-ops database, easy dashboard for reviewing call transcripts |
