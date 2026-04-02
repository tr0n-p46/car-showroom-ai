import os
import re
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import Response

import tools
import tts_engine
import uvicorn

app = FastAPI()

TTS_BUILD_ID = "7a507f6"

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def _is_probably_hindi(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text))

_HINDI_LATIN_HINTS_RE = re.compile(
    r"\b(namaste|namaskar|aap|aapka|aapki|kya|kaise|hai|haan|nahi|dhanyavaad|shukriya)\b",
    re.IGNORECASE,
)


def _is_probably_hindi_latin(text: str) -> bool:
    # Lightweight Hinglish detection when user speaks Hindi in Latin script.
    return bool(_HINDI_LATIN_HINTS_RE.search(text))

def _parse_allowed_voices(value: str | None) -> set[str]:
    if not value:
        return set()
    return {v.strip() for v in value.split(",") if v.strip()}


def _looks_like_kokoro_voice_id(v: str) -> bool:
    # Kokoro voice ids are typically like "af_bella", "hf_alpha", etc.
    return isinstance(v, str) and "_" in v and "-" not in v and len(v) <= 40


def _is_male_kokoro_voice_id(v: str) -> bool:
    # Common male prefixes: am_ (American male), bm_ (British male), hm_ (Hindi male), jm_, pm_, em_, im_
    return isinstance(v, str) and v.startswith(("am_", "bm_", "hm_", "jm_", "pm_", "em_", "im_"))


@app.on_event("startup")
async def _warm_tts_engine():
    # Warm up the ONNX session so the first call isn't extremely slow.
    try:
        tts_engine.load_kokoro()
        # Do a tiny synthesis once so the first real call is fast.
        await asyncio.to_thread(tts_engine.generate_speech_wav, "Hello", "af_bella", "en-us")
    except Exception:
        # If assets are missing, the endpoint will report it on first use.
        pass

@app.get("/")
async def root():
    return {"status": "Automotive AI Receptionist is Online"}

@app.get("/debug/voices")
async def debug_voices(request: Request):
    """
    Returns available Kokoro voice IDs.
    Protected by DEBUG_KEY env var to avoid exposing internals publicly.
    """
    debug_key = os.getenv("DEBUG_KEY")
    provided = request.headers.get("x-debug-key") or request.query_params.get("key")
    if not debug_key or provided != debug_key:
        return Response(content=b"Unauthorized", status_code=401, media_type="text/plain")
    voices = tts_engine.list_voice_ids()
    return {"count": len(voices), "voices": voices}

@app.get("/debug/version")
async def debug_version(request: Request):
    debug_key = os.getenv("DEBUG_KEY")
    provided = request.headers.get("x-debug-key") or request.query_params.get("key")
    if not debug_key or provided != debug_key:
        return Response(content=b"Unauthorized", status_code=401, media_type="text/plain")
    return {"tts_build_id": TTS_BUILD_ID}

@app.post("/debug/tts-decision")
async def debug_tts_decision(request: Request):
    """
    Return the server's TTS decision (voice/lang) for a payload, without audio.
    Protected by DEBUG_KEY.
    """
    debug_key = os.getenv("DEBUG_KEY")
    provided = request.headers.get("x-debug-key") or request.query_params.get("key")
    if not debug_key or provided != debug_key:
        return Response(content=b"Unauthorized", status_code=401, media_type="text/plain")

    payload = await request.json()
    message = payload.get("message") or {}
    text = (
        (message.get("transcript") if isinstance(message, dict) else None)
        or (message.get("text") if isinstance(message, dict) else None)
        or payload.get("transcript")
        or payload.get("text")
        or (message if isinstance(message, str) else None)
        or "Hello"
    )
    if isinstance(text, str) and not text.strip():
        text = "Hello"

    default_voice_en = os.getenv("KOKORO_VOICE_ID", "af_bella")
    default_voice_hi = os.getenv("KOKORO_VOICE_ID_HI", "hf_alpha")
    requested_voice_id = (
        (payload.get("voice") or {}).get("id")
        or payload.get("voice_id")
        or payload.get("voiceId")
        or (message.get("voice") if isinstance(message, dict) else None)
        or default_voice_en
    )

    lang_en = os.getenv("KOKORO_LANG", "en-us")
    lang_hi = os.getenv("KOKORO_LANG_HI", "h")
    payload_lang = (
        payload.get("language")
        or payload.get("lang")
        or (message.get("language") if isinstance(message, dict) else None)
        or (message.get("lang") if isinstance(message, dict) else None)
    )
    is_hi = (
        (isinstance(payload_lang, str) and payload_lang.lower().startswith("hi"))
        or _is_probably_hindi(text)
        or _is_probably_hindi_latin(text)
    )
    lang = lang_hi if is_hi else lang_en

    default_voice = default_voice_hi if is_hi else default_voice_en
    allowed = _parse_allowed_voices(os.getenv("KOKORO_ALLOWED_VOICES"))
    if not allowed:
        allowed = {"af_bella", "af_nicole", "af_sarah", "af_sky", "af_heart", "hf_alpha", "hf_beta"}

    if (
        _looks_like_kokoro_voice_id(requested_voice_id)
        and requested_voice_id in allowed
        and not _is_male_kokoro_voice_id(requested_voice_id)
    ):
        voice_id = requested_voice_id
    else:
        voice_id = default_voice if default_voice in allowed else sorted(allowed)[0]

    return {
        "tts_build_id": TTS_BUILD_ID,
        "text_preview": text[:200],
        "payload_lang": payload_lang,
        "is_hi": is_hi,
        "lang": lang,
        "requested_voice_id": requested_voice_id,
        "voice_id": voice_id,
        "default_voice_en": default_voice_en,
        "default_voice_hi": default_voice_hi,
        "allowed_voices": sorted(allowed),
        "env": {
            "KOKORO_SPEED": os.getenv("KOKORO_SPEED"),
            "TTS_SAMPLE_RATE": os.getenv("TTS_SAMPLE_RATE"),
            "TTS_ENCODING": os.getenv("TTS_ENCODING"),
        },
    }

# Vapi Custom Voice Provider Endpoint
@app.post("/vapi-tts")
async def vapi_tts_handler(request: Request):
    payload = await request.json()

    # VAPI payload shape can vary; try common locations.
    message = payload.get("message") or {}
    text = (
        (message.get("transcript") if isinstance(message, dict) else None)
        or (message.get("text") if isinstance(message, dict) else None)
        or payload.get("transcript")
        or payload.get("text")
        or (message if isinstance(message, str) else None)
        or "Hello"
    )
    if isinstance(text, str) and not text.strip():
        text = "Hello"

    # Choose voice deterministically (female by default).
    default_voice_en = os.getenv("KOKORO_VOICE_ID", "af_bella")
    default_voice_hi = os.getenv("KOKORO_VOICE_ID_HI", "hf_alpha")
    requested_voice_id = (
        (payload.get("voice") or {}).get("id")
        or payload.get("voice_id")
        or payload.get("voiceId")
        or (message.get("voice") if isinstance(message, dict) else None)
        or default_voice_en
    )

    # Language: default English, but auto-detect Hindi (Devanagari or common Latin hints).
    lang_en = os.getenv("KOKORO_LANG", "en-us")
    # kokoro-onnx commonly accepts "hi" or shorthand "h"; default to "h" for safety.
    lang_hi = os.getenv("KOKORO_LANG_HI", "h")

    # VAPI may provide a language hint.
    payload_lang = (
        payload.get("language")
        or payload.get("lang")
        or (message.get("language") if isinstance(message, dict) else None)
        or (message.get("lang") if isinstance(message, dict) else None)
    )
    is_hi = (
        (isinstance(payload_lang, str) and payload_lang.lower().startswith("hi"))
        or _is_probably_hindi(text)
        or _is_probably_hindi_latin(text)
    )
    lang = lang_hi if is_hi else lang_en

    # Voice: force to an allowlist to prevent accidental male voices.
    default_voice = default_voice_hi if is_hi else default_voice_en
    allowed = _parse_allowed_voices(os.getenv("KOKORO_ALLOWED_VOICES"))
    if not allowed:
        # Safe defaults: female voices + Hindi female voices.
        allowed = {"af_bella", "af_nicole", "af_sarah", "af_sky", "af_heart", "hf_alpha", "hf_beta"}

    # Only honor requested voice if it is explicitly allowed and not male.
    if (
        _looks_like_kokoro_voice_id(requested_voice_id)
        and requested_voice_id in allowed
        and not _is_male_kokoro_voice_id(requested_voice_id)
    ):
        voice_id = requested_voice_id
    else:
        voice_id = default_voice if default_voice in allowed else sorted(allowed)[0]

    try:
        audio_content = tts_engine.generate_speech_wav(
            text,
            voice_id=voice_id,
            lang=lang,
            fallback_voice_id=default_voice,
        )
        resp = Response(content=audio_content, media_type="audio/wav")
        # Debug headers so we can verify runtime behavior from VAPI logs.
        resp.headers["x-tts-build"] = TTS_BUILD_ID
        resp.headers["x-tts-voice"] = voice_id
        resp.headers["x-tts-lang"] = lang
        resp.headers["x-tts-speed"] = os.getenv("KOKORO_SPEED", "")
        resp.headers["x-tts-sample-rate"] = os.getenv("TTS_SAMPLE_RATE", "")
        resp.headers["x-tts-encoding"] = os.getenv("TTS_ENCODING", "")
        print(f"TTS decision build={TTS_BUILD_ID} voice={voice_id} lang={lang} len={len(text)}")
        return resp
    except FileNotFoundError as e:
        # Provide a helpful message if model assets haven't been uploaded to `/models` yet.
        return Response(
            content=f"Model assets missing: {e}".encode("utf-8"),
            media_type="text/plain",
            status_code=500,
        )
    except Exception:
        # Last-resort fallback to a known voice id/lang so the call doesn't hang.
        audio_content = tts_engine.generate_speech_wav(
            text,
            voice_id=default_voice_en,
            lang=lang_en,
            fallback_voice_id=default_voice_en,
        )
        return Response(content=audio_content, media_type="audio/wav")

@app.post("/vapi-tools")
async def vapi_tool_handler(request: Request):
    payload = await request.json()
    message = payload.get("message")
    
    # Extract tool call details
    tool_call = message.get("toolCalls")[0]
    function_name = tool_call.get("function").get("name")
    args = tool_call.get("function").get("arguments")

    if function_name == "search_cars":
        result = tools.search_cars(
            budget=args.get("budget"),
            model=args.get("model"),
            fuel_type=args.get("fuel_type")
        )
    elif function_name == "create_lead":
        result = tools.create_lead(
            phone=args.get("phone"),
            intent=args.get("intent"),
            summary=args.get("summary")
        )
    else:
        result = "Error: Function not implemented."

    return {
        "results": [{
            "toolCallId": tool_call.get("id"),
            "result": result
        }]
    }

if __name__ == "__main__":
    # Get port from environment, or default to 8080
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
