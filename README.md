# Flora Voice Agent

An AI-powered inbound voice agent for Flora, a flower boutique. Built with LiveKit Agents framework for real-time voice conversations over phone calls.

## Overview

This voice agent:
- Answers inbound phone calls via Twilio SIP trunk
- Has natural conversations using AI (OpenAI GPT-4o-mini)
- Converts speech to text in real-time (Deepgram)
- Generates natural-sounding voice responses (ElevenLabs)
- Logs every call to Airtable (caller number, duration, transcript)

The entire pipeline is **streaming** for minimal latency - the agent starts speaking as soon as the first tokens arrive from the LLM.

## Architecture

```
Phone Call → Twilio → SIP Trunk → LiveKit Cloud → This Agent
                                                      ↓
                                         ┌────────────┴────────────┐
                                         ↓            ↓            ↓
                                       Silero      Deepgram     OpenAI
                                        (VAD)       (STT)        (LLM)
                                                      ↓            ↓
                                                ElevenLabs ← ← ← ←
                                                   (TTS)
                                                      ↓
                                                   Voice
                                                  Response
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

### Required Variables

| Variable | Description | Where to Get It |
|----------|-------------|-----------------|
| `LIVEKIT_URL` | Your LiveKit Cloud WebSocket URL | [LiveKit Cloud Dashboard](https://cloud.livekit.io) → Your project URL (starts with `wss://`) |
| `LIVEKIT_API_KEY` | LiveKit API Key | LiveKit Cloud Dashboard → Settings → Keys |
| `LIVEKIT_API_SECRET` | LiveKit API Secret | LiveKit Cloud Dashboard → Settings → Keys |
| `DEEPGRAM_API_KEY` | Deepgram API key for speech-to-text | [Deepgram Console](https://console.deepgram.com) → Create API Key |
| `OPENAI_API_KEY` | OpenAI API key for the LLM | [OpenAI Platform](https://platform.openai.com/api-keys) |
| `ELEVENLABS_API_KEY` | ElevenLabs API key for text-to-speech | [ElevenLabs Settings](https://elevenlabs.io/settings/api-keys) |
| `AIRTABLE_PAT` | Airtable Personal Access Token | [Airtable Tokens](https://airtable.com/create/tokens) → Create token with `data.records:write` scope |
| `AIRTABLE_BASE_ID` | Your Airtable Base ID | [Airtable API](https://airtable.com/api) → Click your base → ID starts with `app` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | [Twilio Console](https://console.twilio.com) → Dashboard |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | [Twilio Console](https://console.twilio.com) → Dashboard |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice to use | `EXAVITQu4vr4xnSDxMaL` (Sarah - warm, friendly) |
| `MAX_CALL_DURATION_SECONDS` | Maximum call duration before auto-disconnect (cost protection) | `600` (10 minutes) |

## Airtable Setup

Create a table called `call_logs` with these fields:

| Field Name | Field Type |
|------------|------------|
| `caller_number` | Single line text |
| `duration_seconds` | Number |
| `transcript` | Long text |
| `created_at` | Date (with time) |

## Local Development

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Installation

```bash
# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your actual values
```

### Running Locally

```bash
python agent.py dev
```

The `dev` flag enables development mode with hot-reloading.

## VPS Deployment

The agent runs as a persistent long-running process using systemd.

### Deployment Steps

1. **SSH into your VPS**

2. **Create a non-root user** (for security):
   ```bash
   adduser floraagent
   usermod -aG sudo floraagent
   ```

3. **Install Python**:
   ```bash
   apt update
   apt install python3 python3-pip python3-venv -y
   ```

4. **Set up the project**:
   ```bash
   mkdir -p /opt/flora-agent
   cd /opt/flora-agent
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **Create `.env` file** with your actual values:
   ```bash
   nano /opt/flora-agent/.env
   ```

6. **Create systemd service** at `/etc/systemd/system/flora-agent.service`:
   ```ini
   [Unit]
   Description=Flora Voice Agent
   After=network.target

   [Service]
   Type=simple
   User=floraagent
   WorkingDirectory=/opt/flora-agent
   ExecStart=/opt/flora-agent/venv/bin/python agent.py start
   Restart=always
   RestartSec=10
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```

7. **Enable and start the service**:
   ```bash
   systemctl daemon-reload
   systemctl enable flora-agent
   systemctl start flora-agent
   ```

### Management Commands

```bash
# Check if running
systemctl status flora-agent

# View live logs
journalctl -u flora-agent -f

# Restart the agent
systemctl restart flora-agent

# Stop the agent
systemctl stop flora-agent
```

The agent will automatically restart if it crashes and will start on system reboot.

## LiveKit + Twilio SIP Setup

### LiveKit Cloud

1. Create an account at [LiveKit Cloud](https://cloud.livekit.io)
2. Create a new project
3. Go to Settings → Keys and create API credentials
4. Go to Settings → SIP and configure a SIP trunk

### Twilio SIP Trunk

1. Log into [Twilio Console](https://console.twilio.com)
2. Go to **Elastic SIP Trunking** → **Trunks**
3. Create a new SIP trunk
4. Configure **Origination** with your LiveKit SIP URI (provided by LiveKit)
5. Configure **Termination** credentials
6. Buy a phone number and assign it to this trunk

### Important: SIP Security

The connection between Twilio and LiveKit is secured at the SIP trunk level:
- Twilio authenticates with LiveKit using SIP credentials you configure
- LiveKit validates the SIP trunk configuration before accepting calls
- IP whitelisting can be configured in LiveKit Cloud for additional security
- The agent receives calls only from authenticated LiveKit connections
- No HTTP webhook validation is needed because calls come via SIP protocol, not HTTP

**Note:** Unlike Twilio webhooks (which require signature validation), SIP trunk security
is handled by the SIP credential exchange between Twilio and LiveKit Cloud. Your agent
code doesn't need to validate requests because LiveKit has already authenticated the call.

## VAD Tuning Guide

Voice Activity Detection (VAD) settings control how the agent detects when someone starts and stops speaking. You can tune these in `agent.py`:

| Parameter | What It Does | Too Low | Too High |
|-----------|--------------|---------|----------|
| `min_speech_duration` | Minimum time to count as speech | Triggers on noise | Misses quick "yes/no" |
| `min_silence_duration` | Silence needed before responding | Cuts people off | Feels sluggish |
| `padding_duration` | Extra audio around speech | Clips beginnings/endings | Adds dead air |
| `activation_threshold` | Confidence to detect speech | False triggers | Misses quiet speakers |

**Recommended starting values for phone calls:**
- `min_speech_duration`: 0.05s
- `min_silence_duration`: 0.4s
- `padding_duration`: 0.1s
- `activation_threshold`: 0.5

## Troubleshooting

### Agent won't start

- Check all required environment variables are set
- Verify API keys are valid
- Check logs: `journalctl -u flora-agent -n 50`

### Caller's speech not recognized

- Check Deepgram API key is valid
- Verify the audio stream is being received (check logs)
- Try adjusting VAD sensitivity

### Agent responds slowly

- Ensure streaming is enabled (it is by default)
- Check your network latency to API providers
- Consider using a VPS geographically closer to your users

### Airtable logging fails

- Verify PAT has `data.records:write` permission
- Check Base ID is correct (starts with `app`)
- Ensure table name is exactly `call_logs`
- Verify field names match exactly

### Calls cut off unexpectedly

- Check `MAX_CALL_DURATION_SECONDS` setting
- Look for errors in the logs

## Cost Considerations

| Service | Cost Model |
|---------|------------|
| LiveKit Cloud | Per-minute participant time |
| Deepgram | Per-minute audio processed |
| OpenAI | Per-token (input and output) |
| ElevenLabs | Per-character synthesized |
| Twilio | Per-minute call time + phone number |
| Airtable | Free tier available, paid for higher usage |

The `MAX_CALL_DURATION_SECONDS` setting protects against runaway costs from stuck calls.

## Files

```
flora-voice-agent/
├── agent.py           # Main agent code
├── .env.example       # Example environment variables
├── .env               # Your actual config (not in git!)
├── .gitignore         # Git ignore rules
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## License

Private - All rights reserved.
