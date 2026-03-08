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
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

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

# Airtable configuration for call logging
AIRTABLE_PAT = os.getenv("AIRTABLE_PAT")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = "call_logs"


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
# SYSTEM PROMPT - Flora's AI Assistant Identity and Knowledge
# =============================================================================

SYSTEM_PROMPT = """
You are Maya, a compassionate and empathetic AI mental health companion for UBudy.

Your personality: Warm, gentle, calm, non-judgmental, patient, and deeply empathetic.
You speak naturally and softly like a caring friend. Use a soothing tone.

LANGUAGE: You are bilingual. Respond in the SAME language the user speaks.
- If the user speaks Hindi, respond entirely in Hindi (use Romanized Hindi or Devanagari based on what feels natural for speech).
- If the user speaks English, respond in English.
- If the user mixes Hindi and English (Hinglish), feel free to respond in Hinglish.
- Always match the user's language preference naturally.

IMPORTANT: When the conversation starts, greet warmly and briefly:
"Hi, welcome to UBudy. I'm Maya. How are you feeling today?"
Keep the greeting SHORT - just one or two sentences.

WHAT YOU DO:
- Provide a safe, non-judgmental space for people to talk about their feelings
- Practice active listening - reflect back what you hear
- Help users identify and name their emotions
- Offer grounding techniques, breathing exercises, and coping strategies
- Gently encourage professional help when appropriate
- Support with stress, anxiety, loneliness, sadness, overwhelm, grief, and daily struggles

TECHNIQUES YOU CAN USE:
- Deep breathing exercises (guide them through it step by step)
- Grounding (5-4-3-2-1 senses technique)
- Cognitive reframing (help see situations differently)
- Mindfulness and body scan relaxation
- Journaling prompts and self-reflection questions
- Positive affirmations

GUIDELINES:
1. ALWAYS listen first before offering advice. Ask open-ended questions.
2. NEVER diagnose conditions or prescribe medication.
3. NEVER dismiss or minimize someone's feelings. Validate everything.
4. If someone mentions self-harm, suicide, or harming others, take it seriously:
   - Express care and concern
   - Encourage them to call a crisis helpline:
     * India: iCall (9152987821), Vandrevala Foundation (1860-2662-345)
     * US: 988 Suicide & Crisis Lifeline (call/text 988)
   - Stay calm and supportive
5. Keep responses SHORT and conversational - this is a voice call, not a therapy essay.
6. Use the person's name if they share it.
7. End sessions warmly, reminding them they're not alone and can always come back.
8. Regularly check in: "How does that feel?" or "Kya aap thoda better feel kar rahe hain?"
"""


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

    logger.info(f"New incoming call - Job ID: {ctx.job.id}")

    # Connect to the LiveKit room
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Extract caller info from participant metadata
    user_metadata = {}
    for participant in ctx.room.remote_participants.values():
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
            break

    # Build dynamic system prompt with user context
    dynamic_prompt = SYSTEM_PROMPT
    if user_metadata.get("name") or user_metadata.get("subject"):
        context_parts = []
        if user_metadata.get("name"):
            context_parts.append(f"The student's name is {user_metadata['name']}.")
        if user_metadata.get("grade"):
            context_parts.append(f"They are in grade/class {user_metadata['grade']}.")
        if user_metadata.get("subject"):
            context_parts.append(f"They want to discuss: {user_metadata['subject']}.")
        if user_metadata.get("language"):
            context_parts.append(f"Their preferred language is {user_metadata['language']}.")

        context_block = "\n".join(context_parts)
        dynamic_prompt = SYSTEM_PROMPT + f"""

STUDENT CONTEXT:
{context_block}

IMPORTANT: Use this context to personalize the conversation.
When you greet, address the student by their name immediately. For example: "Hi {user_metadata.get('name', '')}! Welcome to UBudy. I'm Maya."
If they specified a subject, mention that subject in your greeting and start discussing it right away.
Adapt your language to their preference.
"""
        logger.info(f"Dynamic prompt includes student context: {context_block}")

    # Get preloaded VAD
    vad = ctx.proc.userdata["vad"]

    # Configure STT - Deepgram (multi-language: Hindi + English)
    stt = deepgram.STT(
        model="nova-2",
        language="hi",
        interim_results=True,
        smart_format=True,
        punctuate=True,
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )

    # Configure LLM - OpenAI
    llm_instance = openai.LLM(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # Configure TTS - OpenAI
    tts = openai.TTS(
        model="tts-1",
        voice="nova",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # Create the Agent with dynamic prompt
    agent = Agent(instructions=dynamic_prompt)

    # Create session with all pipeline components
    session = AgentSession(
        stt=stt,
        llm=llm_instance,
        tts=tts,
        vad=vad,
        allow_interruptions=True,
    )

    # Event handler for user speech
    @session.on("user_input_transcribed")
    def on_user_speech(event):
        if hasattr(event, 'transcript') and event.transcript:
            transcript_entries.append(f"Caller: {event.transcript}")
            logger.info(f"User said: {event.transcript}")

    # Event handler for agent speech
    @session.on("agent_speech_committed")
    def on_agent_speech(event):
        if hasattr(event, 'content') and event.content:
            transcript_entries.append(f"Agent: {event.content}")
            logger.info(f"Agent said: {event.content}")

    logger.info("Starting agent session...")

    await session.start(
        agent=agent,
        room=ctx.room,
    )
    logger.info("Agent session started - generating initial greeting...")

    # Trigger the agent to greet immediately without waiting for user speech
    await session.generate_reply()

    # Wait for disconnect or timeout
    try:
        while ctx.room.isconnected():
            elapsed = (datetime.now(timezone.utc) - call_start_time).total_seconds()
            if elapsed >= MAX_CALL_DURATION_SECONDS:
                logger.warning(f"Call exceeded {MAX_CALL_DURATION_SECONDS}s limit")
                break
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Session error: {e}")
    finally:
        await session.aclose()
        logger.info("Session closed")

    # Log to Airtable
    duration_seconds = int((datetime.now(timezone.utc) - call_start_time).total_seconds())
    logger.info(f"Call ended - Duration: {duration_seconds} seconds")
    await log_call_to_airtable(
        caller_number=caller_number or "Unknown",
        duration_seconds=duration_seconds,
        transcript="\n".join(transcript_entries)
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
