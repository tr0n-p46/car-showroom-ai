import os
from fastapi import FastAPI, Request
import tools
import tts_engine

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "Automotive AI Receptionist is Online"}

# Vapi Custom Voice Provider Endpoint
@app.post("/vapi-tts")
async def vapi_tts_handler(request: Request):
    payload = await request.json()
    # Vapi sends text in message -> transcript
    text = payload.get("message", {}).get("transcript", "Hello")
    
    # Choose voice based on request or default to hf_alpha (Hindi Female)
    voice_id = "hf_alpha" 
    
    audio_content = tts_engine.generate_speech_wav(text, voice_id=voice_id)
    
    return Response(content=audio_content, media_type="audio/wav")

@app.post("/upload")
async def upload(file: UploadFile):
    path = f"/app/models/{file.filename}"
    with open(path, "wb") as f:
        f.write(await file.read())
    return {"status": "uploaded"}

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
