import os
import re
from fastapi import FastAPI, Request
from fastapi.responses import Response

import tools
import tts_engine
import uvicorn

app = FastAPI()

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def _is_probably_hindi(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text))


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
    except Exception:
        # If assets are missing, the endpoint will report it on first use.
        pass

@app.get("/")
async def root():
    return {"status": "Automotive AI Receptionist is Online"}

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

    # Choose voice based on request or default to a soft female voice.
    default_voice = os.getenv("KOKORO_VOICE_ID", "af_bella")
    requested_voice_id = (
        (payload.get("voice") or {}).get("id")
        or payload.get("voice_id")
        or payload.get("voiceId")
        or (message.get("voice") if isinstance(message, dict) else None)
        or default_voice
    )

    # VAPI may pass ElevenLabs voice ids here; only accept ids that look like Kokoro voice ids.
    voice_id = requested_voice_id if _looks_like_kokoro_voice_id(requested_voice_id) else default_voice
    # Force female voice unless caller explicitly requests a non-male Kokoro voice id.
    if _is_male_kokoro_voice_id(voice_id):
        voice_id = default_voice

    # Language: default English, but auto-detect Hindi script.
    lang = os.getenv("KOKORO_LANG", "en-us")
    if _is_probably_hindi(text):
        lang = os.getenv("KOKORO_LANG_HI", "hi")

    try:
        audio_content = tts_engine.generate_speech_wav(text, voice_id=voice_id, lang=lang)
        return Response(content=audio_content, media_type="audio/wav")
    except FileNotFoundError as e:
        # Provide a helpful message if model assets haven't been uploaded to `/models` yet.
        return Response(
            content=f"Model assets missing: {e}".encode("utf-8"),
            media_type="text/plain",
            status_code=500,
        )
    except Exception:
        # Last-resort fallback to a known voice id/lang so the call doesn't hang.
        fallback_lang = os.getenv("KOKORO_LANG", "en-us")
        audio_content = tts_engine.generate_speech_wav(text, voice_id=default_voice, lang=fallback_lang)
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
