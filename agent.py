"""
UBudy Voice Agent - AI Mental Health Companion
==================================================

This agent provides compassionate, empathetic mental health support
through voice conversations. It uses LiveKit Agents framework with:
- Deepgram for Speech-to-Text (STT)
- OpenAI for the conversational AI (LLM)
- OpenAI TTS for Text-to-Speech (TTS)
- Silero for Voice Activity Detection (VAD)
- Airtable for session logging

The entire pipeline is streaming for minimal latency.
"""

import asyncio
import fcntl
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Admin config file (written by admin panel, read at each call start)
CONFIG_FILE = Path(__file__).parent / "admin_config.json"
CRISIS_ALERTS_FILE = Path(__file__).parent / "crisis_alerts.json"


# =============================================================================
# CRISIS / SAFETY KEYWORD DETECTION (config-driven)
# =============================================================================


def _check_crisis_keywords(text: str, admin_config: dict) -> tuple[Optional[str], Optional[str]]:
    """Check text for crisis keywords from config. Returns (tier, matched_keyword) or (None, None)."""
    tier1 = admin_config.get("safety_keywords_tier1", [])
    tier2 = admin_config.get("safety_keywords_tier2", [])
    if not tier1 and not tier2:
        return (None, None)
    text_lower = text.lower()
    for kw in tier1:
        if kw.lower() in text_lower:
            return ("tier1", kw)
    for kw in tier2:
        if kw.lower() in text_lower:
            return ("tier2", kw)
    return (None, None)


def _write_crisis_alert(session_id: str, tier: str, keyword: str, text: str,
                        transcript_context: list[str]):
    """Write a crisis alert to crisis_alerts.json."""
    try:
        alerts = []
        if CRISIS_ALERTS_FILE.exists():
            try:
                alerts = json.loads(CRISIS_ALERTS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                alerts = []

        alert = {
            "id": uuid.uuid4().hex[:12],
            "session_id": session_id,
            "tier": tier,
            "matched_keyword": keyword,
            "matched_text": text,
            "transcript_context": transcript_context[-6:],
            "status": "new",
            "notes": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        alerts.append(alert)

        with open(CRISIS_ALERTS_FILE, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(alerts, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)

        logger.warning(f"CRISIS ALERT [{tier.upper()}]: keyword='{keyword}' session={session_id}")
    except Exception as e:
        logger.error(f"Failed to write crisis alert: {e}")


# =============================================================================
# PII REDACTION
# =============================================================================

PII_PATTERNS = [
    (re.compile(r'\+91[\s-]?\d{5}[\s-]?\d{5}'), '[PHONE_IN]'),      # Indian phone +91
    (re.compile(r'\+1[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}'), '[PHONE_US]'),  # US phone +1
    (re.compile(r'\b\d{10,15}\b'), '[PHONE]'),                        # Generic 10+ digit number
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '[EMAIL]'),  # Email
    (re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'), '[AADHAAR]'),   # Aadhaar 12-digit
]


def _redact_pii(text: str) -> tuple[str, bool]:
    """Redact PII from text. Returns (redacted_text, was_redacted)."""
    redacted = text
    was_redacted = False
    for pattern, replacement in PII_PATTERNS:
        new_text = pattern.sub(replacement, redacted)
        if new_text != redacted:
            was_redacted = True
            redacted = new_text
    return (redacted, was_redacted)

import aiohttp
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    RunContext,
    WorkerOptions,
    cli,
)
from livekit.agents.metrics import UsageCollector
from livekit.agents import mcp as lk_mcp
from livekit.plugins import deepgram, openai, silero, elevenlabs

# Load environment variables from .env file
load_dotenv()

# Configure logging for clear visibility into agent operations
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mindease-agent")


# =============================================================================
# CONFIGURATION - All values from environment variables for security
# =============================================================================

# Maximum call duration in seconds (cost protection)
MAX_CALL_DURATION_SECONDS = int(os.getenv("MAX_CALL_DURATION_SECONDS", "600"))

# Cost rates (USD) — update when pricing changes
DEEPGRAM_STT_COST_PER_MINUTE = 0.0058   # Nova-2 streaming PAYG
OPENAI_LLM_INPUT_COST_PER_1M = 0.15     # gpt-4o-mini input
OPENAI_LLM_OUTPUT_COST_PER_1M = 0.60    # gpt-4o-mini output
OPENAI_TTS_COST_PER_MINUTE = 0.015      # gpt-4o-mini-tts (~$0.015/min audio)
USD_TO_INR = 92.0

# Airtable configuration for call logging
AIRTABLE_PAT = os.getenv("AIRTABLE_PAT")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = "call_logs"


def _load_admin_config() -> dict:
    """Load admin config from admin_config.json, falling back to defaults."""
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read admin config: {e}")
    return {}


# =============================================================================
# SIP/TWILIO CALLER ID EXTRACTION
# =============================================================================

def extract_phone_number_from_sip(participant_identity: str, participant_metadata: Optional[str] = None) -> str:
    """
    Extract the caller's phone number from SIP participant information.
    """
    phone_number = None

    if participant_metadata:
        try:
            metadata = json.loads(participant_metadata)
            phone_number = (
                metadata.get("sip.callerNumber") or
                metadata.get("sip.from") or
                metadata.get("caller_id") or
                metadata.get("phone_number") or
                metadata.get("from")
            )
        except (json.JSONDecodeError, TypeError):
            pass

    if not phone_number and participant_identity:
        sip_match = re.search(r'sip:([+\d]+)@', participant_identity)
        if sip_match:
            phone_number = sip_match.group(1)
        else:
            tel_match = re.search(r'tel:([+\d]+)', participant_identity)
            if tel_match:
                phone_number = tel_match.group(1)
            else:
                phone_match = re.search(r'(\+?1?\d{10,15})', participant_identity)
                if phone_match:
                    phone_number = phone_match.group(1)

    return phone_number or "Unknown"


# =============================================================================
# GENERIC PROMPT BUILDER + KNOWLEDGE BASE
# =============================================================================

LANGUAGE_RULES = {
    "english": (
        "LANGUAGE RULES:\n"
        "- Respond only in English.\n"
        "- Keep sentences short and conversational."
    ),
    "hindi": (
        "LANGUAGE RULES:\n"
        "- Respond in Hinglish — Romanized Hindi mixed with common English words.\n"
        "- NEVER use Devanagari script. ALWAYS use Latin/Roman letters for Hindi words.\n"
        "- Use SIMPLE, common Hindi words. Avoid complex or literary Hindi.\n"
        "- Keep sentences SHORT — max 10-12 words per sentence.\n"
        "- Example good: \"Aap tension mein hain? It's okay. Main hoon na.\"\n"
        "- Example bad: \"Aapko chintit hone ki avashyakta nahi hai.\""
    ),
    "hinglish": (
        "LANGUAGE AND TTS RULES (VERY IMPORTANT):\n"
        "- If user speaks Hindi, respond in simple Hinglish — mix English with Romanized Hindi.\n"
        "- If user speaks English, respond in English.\n"
        "- If user mixes both, respond in Hinglish.\n"
        "- NEVER use Devanagari script. ALWAYS use Latin/Roman letters for Hindi words.\n"
        "- Keep sentences SHORT — max 10-12 words per sentence.\n"
        "- Use SIMPLE, common Hindi words. Prefer English for technical terms.\n"
        "- Add natural pauses: use \"...\" for dramatic pauses, commas between phrases."
    ),
    "auto": (
        "LANGUAGE RULES:\n"
        "- Detect the user's language and respond in the same language.\n"
        "- If Hindi detected, use Romanized Hindi (Latin script, never Devanagari).\n"
        "- Keep sentences SHORT and conversational."
    ),
}


def _load_knowledge(admin_config: dict) -> str:
    """Load knowledge from config + knowledge/ directory files."""
    parts = []
    # 1. Config-based knowledge
    kb = admin_config.get("knowledge_base", "").strip()
    if kb:
        parts.append(kb)
    # 2. File-based knowledge
    kb_dir = Path(__file__).parent / "knowledge"
    if kb_dir.exists():
        for f in sorted(kb_dir.glob("*.txt")):
            if f.name.upper() == "README.TXT":
                continue
            try:
                content = f.read_text().strip()
                if content:
                    parts.append(f"[{f.name}]\n{content}")
            except OSError:
                pass
        for f in sorted(kb_dir.glob("*.pdf")):
            text = _extract_pdf_text(f)
            if text:
                parts.append(f"[{f.name}]\n{text}")
    return "\n\n".join(parts)


def _extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF file using PyPDF2 (best-effort)."""
    try:
        import PyPDF2
        text_parts = []
        with open(path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t.strip())
        return "\n".join(text_parts)
    except ImportError:
        logger.warning("PyPDF2 not installed — skipping PDF knowledge files")
        return ""
    except Exception as e:
        logger.warning(f"Failed to extract PDF text from {path.name}: {e}")
        return ""


def build_system_prompt(admin_config: dict, user_metadata: dict = None) -> str:
    """Build the system prompt from agent_profile + knowledge, or use custom override."""
    # Power-user mode: if a custom system_prompt is set, use it directly
    custom_prompt = admin_config.get("system_prompt", "").strip()
    if custom_prompt:
        prompt = custom_prompt
    else:
        # Auto-build from agent profile
        profile = admin_config.get("agent_profile", {})
        agent_name = profile.get("agent_name", "Assistant")
        company_name = profile.get("company_name", "")
        role = profile.get("role", "AI voice assistant")
        personality = profile.get("personality", "Friendly, helpful, and professional")
        language_mode = profile.get("language_mode", "english")

        # User's language preference from query params overrides profile default
        if user_metadata and user_metadata.get("language"):
            user_lang = user_metadata["language"].lower()
            if user_lang in LANGUAGE_RULES:
                language_mode = user_lang
            elif user_lang in ("hindi", "hi"):
                language_mode = "hinglish"

        # Agent type override from query params (e.g. type=legalAdviser)
        agent_type = (user_metadata or {}).get("type", "").strip()
        user_name = (user_metadata or {}).get("name", "")

        # Type-specific overrides
        if agent_type == "legalAdviser":
            role = "legal adviser specializing in Indian law"
            personality = "Knowledgeable, clear, professional, patient, and helpful"
            if language_mode in ("hindi", "hinglish"):
                if user_name:
                    default_greeting = (
                        f"Namaste {user_name}, main {agent_name} hoon, aapki legal adviser. "
                        "Aap mujhse Indian law ya legal system ke baare mein kuch bhi pooch sakte hain."
                    )
                else:
                    default_greeting = (
                        f"Namaste, main {agent_name} hoon, aapki legal adviser. "
                        "Aap mujhse Indian law ya legal system ke baare mein kuch bhi pooch sakte hain."
                    )
            else:
                if user_name:
                    default_greeting = (
                        f"Hi {user_name}, I'm {agent_name}, your legal adviser. "
                        "Feel free to ask me anything about Indian law or the legal system."
                    )
                else:
                    default_greeting = (
                        f"Hi, I'm {agent_name}, your legal adviser. "
                        "Feel free to ask me anything about Indian law or the legal system."
                    )
            guidelines = (
                "GUIDELINES:\n"
                "- Keep responses SHORT and conversational — this is a voice call.\n"
                "- You are a legal adviser. Answer questions about Indian law, IPC, BNS, legal sections, and the legal system.\n"
                "- ALWAYS use the available legal tools to look up accurate information before answering.\n"
                "- Cite specific sections (IPC, BNS) when relevant.\n"
                "- If the user asks something outside Indian law, politely redirect them.\n"
                "- NEVER provide personal legal advice for specific cases — recommend consulting a lawyer.\n"
                "- Use the person's name if they share it."
            )
        else:
            # Default greeting for mental health companion or generic role
            if language_mode in ("hindi", "hinglish"):
                if user_name:
                    default_greeting = f"Namaste {user_name}, main {agent_name} hoon. Aap kaise feel kar rahe hain aaj?"
                else:
                    default_greeting = f"Namaste, main {agent_name} hoon. Aap kaise feel kar rahe hain aaj?"
            else:
                if user_name:
                    default_greeting = f"Hi {user_name}, I'm {agent_name}. How can I help you today?"
                else:
                    default_greeting = f"Hi, I'm {agent_name}. How can I help you today?"
            guidelines = (
                "GUIDELINES:\n"
                "- Keep responses SHORT and conversational — this is a voice call.\n"
                "- Listen first before offering advice. Ask open-ended questions.\n"
                "- Use the person's name if they share it."
            )

        greeting = profile.get("greeting", default_greeting) if not agent_type else default_greeting

        company_part = f" for {company_name}" if company_name else ""
        prompt_parts = [
            f"You are {agent_name}, a {role}{company_part}.",
            f"Your personality: {personality}.",
        ]

        # Language rules
        lang_rules = LANGUAGE_RULES.get(language_mode, LANGUAGE_RULES["english"])
        prompt_parts.append(lang_rules)

        prompt_parts.append(
            f'IMPORTANT: When the conversation starts, greet with:\n"{greeting}"\n'
            "Keep the greeting SHORT — just one or two sentences."
        )

        prompt_parts.append(guidelines)

        prompt = "\n\n".join(prompt_parts)

    # Append knowledge base
    knowledge = _load_knowledge(admin_config)
    if knowledge:
        prompt += "\n\nKNOWLEDGE BASE:\n" + knowledge

    # Append user metadata context
    if user_metadata:
        context_parts = []
        if user_metadata.get("name"):
            context_parts.append(f"The user's name is {user_metadata['name']}.")
        if user_metadata.get("grade"):
            context_parts.append(f"They are in grade/class {user_metadata['grade']}.")
        if user_metadata.get("subject"):
            context_parts.append(f"They want to discuss: {user_metadata['subject']}.")
        if user_metadata.get("language"):
            context_parts.append(f"Their preferred language is {user_metadata['language']}.")
        if context_parts:
            prompt += "\n\nUSER CONTEXT:\n" + "\n".join(context_parts)
            prompt += (
                "\n\nIMPORTANT: Use this context to personalize the conversation. "
                "Address the user by name. If they specified a topic, discuss it."
            )

    # Append MCP tools instruction if MCP servers are configured
    mcp_configs = admin_config.get("mcp_servers", [])
    enabled_mcp = [c for c in mcp_configs if c.get("enabled", True)]
    if enabled_mcp:
        mcp_names = [c.get("name", "unnamed") for c in enabled_mcp]
        prompt += (
            "\n\nTOOLS AVAILABLE:\n"
            f"You have access to external knowledge tools: {', '.join(mcp_names)}.\n"
            "IMPORTANT: When the user asks a question that these tools can answer, "
            "you MUST use the available tool functions to look up accurate information. "
            "Do NOT guess or make up answers — always call the tool first, then summarize "
            "the result conversationally for the user. Keep your response short and natural "
            "since this is a voice call."
        )

    return prompt


# =============================================================================
# AIRTABLE LOGGING
# =============================================================================

async def log_call_to_airtable(
    caller_number: str,
    duration_seconds: int,
    transcript: str
) -> bool:
    """Log call details to Airtable after a call ends."""
    if not AIRTABLE_PAT or not AIRTABLE_BASE_ID:
        logger.warning("Airtable credentials not configured - skipping call logging")
        return False

    try:
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_PAT}",
            "Content-Type": "application/json"
        }
        data = {
            "records": [{
                "fields": {
                    "caller_number": caller_number or "Unknown",
                    "duration_seconds": duration_seconds,
                    "transcript": transcript,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            }]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    logger.info(f"Successfully logged call to Airtable (duration: {duration_seconds}s)")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Airtable API error ({response.status}): {error_text}")
                    return False

    except Exception as e:
        logger.error(f"Error logging to Airtable: {e}")
        return False


# =============================================================================
# LOCAL JSON SESSION LOGGING
# =============================================================================

SESSIONS_FILE = Path(__file__).parent / "sessions.json"


def _read_sessions() -> list[dict]:
    """Read sessions from the JSON file."""
    if not SESSIONS_FILE.exists():
        return []
    try:
        return json.loads(SESSIONS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _write_sessions(sessions: list[dict]):
    """Write sessions to the JSON file with file locking."""
    with open(SESSIONS_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(sessions, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)


def log_session_start(session_id: str, name: str, subject: str, language: str):
    """Log a new session as active."""
    sessions = _read_sessions()
    sessions.append({
        "id": session_id,
        "name": name,
        "subject": subject,
        "language": language,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "duration_seconds": None,
        "status": "active",
        "pii_redacted": False,
    })
    _write_sessions(sessions)
    logger.info(f"Session logged (start): {session_id}")


def log_session_end(session_id: str, duration_seconds: int, cost_data: dict = None):
    """Update a session with end time, duration, and optional cost data."""
    sessions = _read_sessions()
    for s in sessions:
        if s["id"] == session_id:
            s["ended_at"] = datetime.now(timezone.utc).isoformat()
            s["duration_seconds"] = duration_seconds
            s["status"] = "completed"
            if cost_data:
                s["cost"] = cost_data
            break
    _write_sessions(sessions)
    logger.info(f"Session logged (end): {session_id}, duration={duration_seconds}s")


def calculate_call_cost(summary, duration_seconds: int) -> dict:
    """Calculate per-call cost from UsageSummary. Returns cost breakdown in INR."""
    stt_minutes = summary.stt_audio_duration / 60.0
    stt_cost_usd = stt_minutes * DEEPGRAM_STT_COST_PER_MINUTE

    llm_input_cost_usd = (summary.llm_prompt_tokens / 1_000_000) * OPENAI_LLM_INPUT_COST_PER_1M
    llm_output_cost_usd = (summary.llm_completion_tokens / 1_000_000) * OPENAI_LLM_OUTPUT_COST_PER_1M
    llm_cost_usd = llm_input_cost_usd + llm_output_cost_usd

    tts_minutes = summary.tts_audio_duration / 60.0
    tts_cost_usd = tts_minutes * OPENAI_TTS_COST_PER_MINUTE

    total_usd = stt_cost_usd + llm_cost_usd + tts_cost_usd

    return {
        "stt_cost_inr": round(stt_cost_usd * USD_TO_INR, 2),
        "llm_cost_inr": round(llm_cost_usd * USD_TO_INR, 2),
        "tts_cost_inr": round(tts_cost_usd * USD_TO_INR, 2),
        "total_cost_inr": round(total_usd * USD_TO_INR, 2),
        "total_cost_usd": round(total_usd, 6),
        "usage": {
            "llm_input_tokens": summary.llm_prompt_tokens,
            "llm_output_tokens": summary.llm_completion_tokens,
            "tts_characters": summary.tts_characters_count,
            "tts_audio_minutes": round(tts_minutes, 2),
            "stt_audio_minutes": round(stt_minutes, 2),
        },
    }


# =============================================================================
# MCP SERVER BUILDER
# =============================================================================


def _build_mcp_servers(admin_config: dict) -> list:
    """Build MCP server instances from admin config."""
    servers = []
    mcp_configs = admin_config.get("mcp_servers", [])
    for cfg in mcp_configs:
        if not cfg.get("enabled", True):
            continue
        try:
            if cfg.get("type") == "http":
                url = cfg.get("url", "").strip()
                if not url:
                    continue
                server = lk_mcp.MCPServerHTTP(
                    url=url,
                    headers=cfg.get("headers") or None,
                    client_session_timeout_seconds=cfg.get("timeout", 10),
                )
                servers.append(server)
                logger.info(f"MCP server configured: {cfg.get('name', 'unnamed')} (HTTP: {url})")
            elif cfg.get("type") == "stdio":
                command = cfg.get("command", "").strip()
                if not command:
                    continue
                server = lk_mcp.MCPServerStdio(
                    command=command,
                    args=cfg.get("args", []),
                    env=cfg.get("env") or None,
                )
                servers.append(server)
                logger.info(f"MCP server configured: {cfg.get('name', 'unnamed')} (stdio: {command})")
        except Exception as e:
            logger.warning(f"Failed to configure MCP server '{cfg.get('name', 'unnamed')}': {e}")
    return servers


# =============================================================================
# AGENT INITIALIZATION
# =============================================================================

def prewarm_process(proc: JobProcess):
    """Load VAD model before any calls arrive."""
    logger.info("Prewarming: Loading Silero VAD model...")
    # Lower activation_threshold for more sensitive barge-in detection
    # Lower min_speech_duration for faster interruption response
    proc.userdata["vad"] = silero.VAD.load(
        activation_threshold=0.35,  # More sensitive (default 0.5)
        min_speech_duration=0.05,   # Quick speech detection
        min_silence_duration=0.4,   # Slightly faster silence detection
    )
    logger.info("Prewarming complete - agent ready for calls")


# =============================================================================
# MAIN CALL HANDLER
# =============================================================================

async def entrypoint(ctx: JobContext):
    """Main entry point for handling an incoming phone call."""

    call_start_time = datetime.now(timezone.utc)
    transcript_entries: list[str] = []
    caller_number: Optional[str] = None

    # Load admin config (hot-reload: reads fresh config each call)
    admin_config = _load_admin_config()
    if admin_config:
        logger.info(f"Admin config loaded: {list(admin_config.keys())}")

    logger.info(f"New incoming call - Job ID: {ctx.job.id}")

    # Connect to the LiveKit room
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the remote participant to actually join before reading metadata
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant connected: {participant.identity}")

    # Extract caller info from participant metadata
    user_metadata = {}
    if participant.identity:
        caller_number = extract_phone_number_from_sip(
            participant_identity=participant.identity,
            participant_metadata=participant.metadata
        )
        logger.info(f"Caller identified: {caller_number}")
        # Parse user metadata (name, subject, grade, language)
        if participant.metadata:
            try:
                user_metadata = json.loads(participant.metadata)
                logger.info(f"User metadata: {user_metadata}")
            except (json.JSONDecodeError, TypeError):
                pass

    # Log session start to local JSON
    session_id = ctx.job.id
    log_session_start(
        session_id=session_id,
        name=user_metadata.get("name", "Unknown"),
        subject=user_metadata.get("subject", ""),
        language=user_metadata.get("language", ""),
    )

    # Build dynamic system prompt from profile + knowledge + user context
    dynamic_prompt = build_system_prompt(admin_config, user_metadata)
    logger.info(f"Using prompt starting with: {dynamic_prompt[:80]}")

    # Get preloaded VAD
    vad = ctx.proc.userdata["vad"]

    # Configure STT - Deepgram (multi-language: Hindi + English)
    stt_cfg = admin_config.get("stt", {})
    stt = deepgram.STT(
        model=stt_cfg.get("model", "nova-2"),
        language=stt_cfg.get("language", "hi"),
        interim_results=True,
        smart_format=True,
        punctuate=True,
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )

    # Configure LLM - OpenAI
    llm_cfg = admin_config.get("llm", {})
    llm_instance = openai.LLM(
        model=llm_cfg.get("model", "gpt-4o-mini"),
        temperature=llm_cfg.get("temperature", 0.7),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # Configure TTS - OpenAI (gpt-4o-mini-tts for best multilingual/Hindi support)
    tts_cfg = admin_config.get("tts", {})
    tts = openai.TTS(
        model=tts_cfg.get("model", "gpt-4o-mini-tts"),
        voice=tts_cfg.get("voice", "nova"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # Build MCP servers from config
    mcp_servers = _build_mcp_servers(admin_config)
    if mcp_servers:
        logger.info(f"MCP servers to register: {len(mcp_servers)} server(s)")
        for i, s in enumerate(mcp_servers):
            logger.info(f"  MCP server [{i}]: {s}")
    else:
        logger.info("No MCP servers configured")

    # Create the Agent with dynamic prompt and MCP servers
    agent = Agent(
        instructions=dynamic_prompt,
        mcp_servers=mcp_servers if mcp_servers else None,
    )

    # Create session with all pipeline components
    session = AgentSession(
        stt=stt,
        llm=llm_instance,
        tts=tts,
        vad=vad,
        allow_interruptions=True,
    )

    # Usage collector for cost tracking
    usage_collector = UsageCollector()

    @session.on("metrics_collected")
    def on_metrics_collected(event):
        usage_collector.collect(event.metrics)

    # Track if PII was redacted in this session
    pii_was_redacted = [False]  # mutable container for closure

    # Event handler for user speech
    @session.on("user_input_transcribed")
    def on_user_speech(event):
        if hasattr(event, 'transcript') and event.transcript:
            transcript_entries.append(f"Caller: {event.transcript}")
            logger.info(f"User said: {event.transcript}")

            # Crisis keyword detection (only if keywords configured)
            tier, keyword = _check_crisis_keywords(event.transcript, admin_config)
            if tier:
                _write_crisis_alert(
                    session_id=session_id,
                    tier=tier,
                    keyword=keyword,
                    text=event.transcript,
                    transcript_context=list(transcript_entries),
                )

    # Event handler for agent speech (conversation_item_added covers agent messages)
    @session.on("conversation_item_added")
    def on_conversation_item(event):
        item = event.item if hasattr(event, 'item') else None
        if item and hasattr(item, 'role') and item.role == 'assistant':
            content = ""
            if hasattr(item, 'text_content'):
                content = item.text_content or ""
            elif hasattr(item, 'content') and item.content:
                content = str(item.content)
            if content:
                transcript_entries.append(f"Agent: {content}")
                logger.info(f"Agent said: {content}")

    # Event handler for MCP/function tool execution
    @session.on("function_tools_executed")
    def on_tools_executed(event):
        if hasattr(event, 'function_calls'):
            for fc in event.function_calls:
                name = fc.function_info.name if hasattr(fc, 'function_info') else "unknown"
                logger.info(f"MCP TOOL CALLED: {name}")
                if hasattr(fc, 'result'):
                    result_str = str(fc.result)[:200]
                    logger.info(f"MCP TOOL RESULT: {result_str}")
        elif hasattr(event, 'items'):
            for item in event.items:
                logger.info(f"MCP TOOL EXECUTED: {item}")

    logger.info("Starting agent session...")

    await session.start(
        agent=agent,
        room=ctx.room,
    )

    # Debug: log what tools are registered after session start
    if hasattr(session, '_activity') and session._activity:
        activity_tools = session._activity.tools
        logger.info(f"Tools registered with LLM: {len(activity_tools)} tool(s)")
        for t in activity_tools:
            if hasattr(t, 'info') and t.info:
                logger.info(f"  Tool: {t.info.name}")
            elif hasattr(t, 'name'):
                logger.info(f"  Tool: {t.name}")
            else:
                logger.info(f"  Tool: {type(t).__name__}")
    else:
        logger.info("Could not access activity tools for debugging")

    logger.info("Agent session started - generating initial greeting...")

    # Trigger the agent to greet immediately without waiting for user speech
    await session.generate_reply()

    # Wait for disconnect or timeout
    max_duration = admin_config.get("max_call_duration_seconds", MAX_CALL_DURATION_SECONDS)
    disconnect_event = asyncio.Event()

    @ctx.room.on("participant_disconnected")
    def on_participant_left(participant):
        logger.info(f"Participant left: {participant.identity}")
        if len(ctx.room.remote_participants) == 0:
            disconnect_event.set()

    @ctx.room.on("disconnected")
    def on_room_disconnected(*args):
        logger.info("Room disconnected")
        disconnect_event.set()

    try:
        while not disconnect_event.is_set():
            elapsed = (datetime.now(timezone.utc) - call_start_time).total_seconds()
            if elapsed >= max_duration:
                logger.warning(f"Call exceeded {max_duration}s limit")
                break
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Session error: {e}")
    finally:
        await session.aclose()
        logger.info("Session closed")

    # Calculate cost from usage metrics
    duration_seconds = int((datetime.now(timezone.utc) - call_start_time).total_seconds())
    usage_summary = usage_collector.get_summary()
    cost_data = calculate_call_cost(usage_summary, duration_seconds)
    logger.info(f"Call cost: ₹{cost_data['total_cost_inr']} (USD ${cost_data['total_cost_usd']})")

    # Log session end to local JSON
    log_session_end(session_id, duration_seconds, cost_data=cost_data)

    # Apply PII redaction if enabled
    pii_enabled = admin_config.get("pii_redaction_enabled", True)
    transcript_for_storage = "\n".join(transcript_entries)
    if pii_enabled:
        transcript_for_storage, was_redacted = _redact_pii(transcript_for_storage)
        if was_redacted:
            pii_was_redacted[0] = True
            logger.info(f"PII redacted from transcript for session {session_id}")

    # Mark session as PII-redacted if applicable
    if pii_was_redacted[0]:
        sessions = _read_sessions()
        for s in sessions:
            if s["id"] == session_id:
                s["pii_redacted"] = True
                break
        _write_sessions(sessions)

    # Log to Airtable (with redacted transcript)
    logger.info(f"Call ended - Duration: {duration_seconds} seconds")
    await log_call_to_airtable(
        caller_number=caller_number or "Unknown",
        duration_seconds=duration_seconds,
        transcript=transcript_for_storage,
    )


# =============================================================================
# WORKER ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    required_vars = [
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "DEEPGRAM_API_KEY",
        "OPENAI_API_KEY",
        "ELEVENLABS_API_KEY",
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        exit(1)

    logger.info("Starting UBudy Voice Agent...")
    logger.info(f"Max call duration: {MAX_CALL_DURATION_SECONDS} seconds")

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm_process,
        )
    )
