import os
from fastapi import FastAPI, Request
from fastapi.responses import Response

import tools
import tts_engine
import uvicorn

app = FastAPI()

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

    # Choose voice based on request or default to hf_alpha (Hindi Female).
    requested_voice_id = (
        (payload.get("voice") or {}).get("id")
        or payload.get("voice_id")
        or payload.get("voiceId")
        or (message.get("voice") if isinstance(message, dict) else None)
        or "hf_alpha"
    )

    # Kokoro v0.19 commonly ships with `hf_alpha` (Hindi Female) and `hm_psi` (Hindi Male).
    # VAPI may pass ElevenLabs voice ids here; guard against unknown voice ids.
    allowed_voice_ids = {"hf_alpha", "hm_psi"}
    voice_id = requested_voice_id if requested_voice_id in allowed_voice_ids else "hf_alpha"

    try:
        audio_content = tts_engine.generate_speech_wav(text, voice_id=voice_id)
        return Response(content=audio_content, media_type="audio/wav")
    except Exception:
        # Last-resort fallback to a known voice id so the call doesn't hang.
        audio_content = tts_engine.generate_speech_wav(text, voice_id="hf_alpha")
        return Response(content=audio_content, media_type="audio/wav")
    except FileNotFoundError as e:
        # Provide a helpful message if model assets haven't been uploaded to `/models` yet.
        return Response(
            content=f"Model assets missing: {e}".encode("utf-8"),
            media_type="text/plain",
            status_code=500,
        )

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
