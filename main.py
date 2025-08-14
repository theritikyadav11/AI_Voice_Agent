from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx
import assemblyai as aai
import tempfile
from fastapi.concurrency import run_in_threadpool
from google import genai
from google.genai import types

# Load Murf API key from .env
load_dotenv()
MURF_API_KEY = os.getenv("MURF_API_KEY")
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
print("AssemblyAI API Key:", os.getenv("ASSEMBLYAI_API_KEY"))  # For debug, remove later


app = FastAPI()

# Allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (your HTML & JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

# Define the expected request body for TTS
class TTSRequest(BaseModel):
    text: str
    voiceId: str = "en-US-natalie"  # default voice

# @app.post("/tts")
# async def generate_tts(request: TTSRequest):
#     if not MURF_API_KEY:
#         return JSONResponse(status_code=500, content={"error": "MURF_API_KEY not set in .env"})

#     headers = {
#         "api-key": MURF_API_KEY,
#         "Content-Type": "application/json"
#     }

#     payload = {
#         "text": request.text,
#         "voiceId": request.voiceId,
#         "pronunciationDictionary": {
#             "2010": {
#                 "pronunciation": "two thousand and ten",
#                 "type": "SAY_AS"
#             },
#             "live": {
#                 "pronunciation": "laɪv",
#                 "type": "IPA"
#             }
#         }
#     }

#     try:
#         async with httpx.AsyncClient() as client:
#             response = await client.post(
#                 "https://api.murf.ai/v1/speech/generate",
#                 headers=headers,
#                 json=payload
#             )
#         response.raise_for_status()
#         data = response.json()
#         return {
#             "audio_url": data.get("audioFile", "No audio URL returned."),
#             "length_seconds": data.get("audioLengthInSeconds"),
#             "word_timings": data.get("wordDurations")
#         }
#     except httpx.HTTPStatusError as e:
#         return JSONResponse(status_code=e.response.status_code, content={"error": e.response.text})
#     except Exception as ex:
#         return JSONResponse(status_code=500, content={"error": str(ex)})
    

# UPLOAD_DIR = "uploads"
# os.makedirs(UPLOAD_DIR, exist_ok=True)

# @app.post("/upload-audio/")
# async def upload_audio(file: UploadFile = File(...)):
#     file_location = f"{UPLOAD_DIR}/{file.filename}"
#     with open(file_location, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)

#     return {
#         "filename": file.filename,
#         "content_type": file.content_type,
#         "size": os.path.getsize(file_location)
#     }

# # Initialize Transcriber
# transcriber = aai.Transcriber()

# # Define config with SLAM-1 model
# config = aai.TranscriptionConfig(
#     speech_model=aai.SpeechModel.slam_1
# )

# @app.post("/transcribe/file")
# async def transcribe_audio(file: UploadFile = File(...)):
#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
#             contents = await file.read()
#             tmp.write(contents)
#             tmp_path = tmp.name

#         transcript = await run_in_threadpool(transcriber.transcribe, tmp_path, config=config)

#         os.remove(tmp_path)

#         return {"transcription": transcript.text}

#     except Exception as e:
#         return JSONResponse(status_code=500, content={"error": str(e)})
    

# @app.post("/tts/echo")
# async def echo_with_murf(file: UploadFile = File(...)):
#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
#             contents = await file.read()
#             tmp.write(contents)
#             tmp_path = tmp.name

#         transcript = await run_in_threadpool(transcriber.transcribe, tmp_path, config=config)

#         os.remove(tmp_path)

#         transcribed_text = transcript.text

#         if not MURF_API_KEY:
#             return JSONResponse(status_code=500, content={"error": "MURF_API_KEY not set"})

#         headers = {
#             "api-key": MURF_API_KEY,
#             "Content-Type": "application/json"
#         }

#         payload = {
#             "text": transcribed_text,
#             "voiceId": "en-US-natalie",
#         }

#         async with httpx.AsyncClient() as client:
#             response = await client.post(
#                 "https://api.murf.ai/v1/speech/generate",
#                 headers=headers,
#                 json=payload
#             )

#         response.raise_for_status()
#         murf_data = response.json()

#         return {
#             "transcription": transcribed_text,
#             "audio_url": murf_data.get("audioFile")
#         }

#     except httpx.HTTPStatusError as e:
#         return JSONResponse(status_code=e.response.status_code, content={"error": e.response.text})
#     except Exception as e:
#         return JSONResponse(status_code=500, content={"error": str(e)})


# # Integrating a Large Language Model
# class QueryRequest(BaseModel):
#     text: str
#     model: str = "gemini-2.5-flash"
#     temperature: float = 0.7
#     max_tokens: int = 1024

# client = genai.Client()

# @app.post("/llm/query-text")
# async def query_llm(query: QueryRequest):
#     try:
#         response = client.models.generate_content(
#             model=query.model,
#             contents=[query.text],
#             config=types.GenerateContentConfig(
#                 temperature=query.temperature,
#                 max_output_tokens=query.max_tokens
#             )
#         )
        
#         return {"response": response.text}

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # Simple in-memory chat history store
# chat_history = {}  # {session_id: [{"role": "user", "text": ...}, {"role": "assistant", "text": ...}]}


# # NEW ROUTE: /llm/query (Audio → Text → LLM → Murf → Audio)
# @app.post("/llm/query")
# async def llm_query_audio(file: UploadFile = File(...)):
#     try:
#         # Save uploaded audio temporarily
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
#             contents = await file.read()
#             tmp.write(contents)
#             tmp_path = tmp.name

#         # Step 1: Transcribe audio
#         transcript = await run_in_threadpool(transcriber.transcribe, tmp_path, config=config)
#         os.remove(tmp_path)
#         transcribed_text = transcript.text

#         if not transcribed_text.strip():
#             return JSONResponse(status_code=400, content={"error": "No speech detected."})

#         # Step 2: Get LLM response
#         llm_response = client.models.generate_content(
#             model="gemini-2.5-flash",
#             contents=[transcribed_text],
#             config=types.GenerateContentConfig(
#                 temperature=0.7,
#                 max_output_tokens=1024
#             )
#         )
#         generated_text = llm_response.text

#         # Step 3: Convert LLM text to audio via Murf
#         if not MURF_API_KEY:
#             return JSONResponse(status_code=500, content={"error": "MURF_API_KEY not set"})

#         headers = {
#             "api-key": MURF_API_KEY,
#             "Content-Type": "application/json"
#         }
#         payload = {
#             "text": generated_text,
#             "voiceId": "en-US-natalie"
#         }

#         async with httpx.AsyncClient() as client_http:
#             murf_res = await client_http.post(
#                 "https://api.murf.ai/v1/speech/generate",
#                 headers=headers,
#                 json=payload
#             )
#         murf_res.raise_for_status()
#         murf_data = murf_res.json()

#         return {
#             "transcription": transcribed_text,
#             "llm_text": generated_text,
#             "audio_url": murf_data.get("audioFile")
#         }

#     except httpx.HTTPStatusError as e:
#         return JSONResponse(status_code=e.response.status_code, content={"error": e.response.text})
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))



# Simple in-memory chat history store
chat_history = {}  # {session_id: [{"role": "user", "text": ...}, {"role": "assistant", "text": ...}]}


# Initialize Transcriber
transcriber = aai.Transcriber()

# Define config with SLAM-1 model
config = aai.TranscriptionConfig(
    speech_model=aai.SpeechModel.slam_1
)


class QueryRequest(BaseModel):
    text: str
    model: str = "gemini-2.5-flash"
    temperature: float = 0.7
    max_tokens: int = 1024

client = genai.Client()

@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    try:
        # Step 1: Transcribe audio (STT)
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
                contents = await file.read()
                tmp.write(contents)
                tmp_path = tmp.name
            transcript = await run_in_threadpool(transcriber.transcribe, tmp_path, config=config)
            os.remove(tmp_path)
            user_message = transcript.text.strip()
            if not user_message:
                return JSONResponse(status_code=400, content={"error": "No speech detected."})
        except Exception as e:
            print("STT Error:", e)
            user_message = ""
            bot_reply = "I'm having trouble understanding you right now."

        # Step 2: Add user message to history
        if session_id not in chat_history:
            chat_history[session_id] = []
        chat_history[session_id].append({"role": "user", "text": user_message})

        # Step 3: LLM Generation
        if user_message:
            try:
                full_conversation = "\n".join([f"{m['role']}: {m['text']}" for m in chat_history[session_id]])
                llm_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[full_conversation],
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=1024
                    )
                )
                bot_reply = llm_response.text
            except Exception as e:
                print("LLM Error:", e)
                bot_reply = "I'm having trouble connecting right now."
        else:
            bot_reply = "I'm having trouble understanding you right now."

        chat_history[session_id].append({"role": "assistant", "text": bot_reply})

        # Step 4: Text-to-Speech
        try:
            headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
            payload = {"text": bot_reply, "voiceId": "en-US-natalie"}
            async with httpx.AsyncClient() as client_http:
                murf_res = await client_http.post(
                    "https://api.murf.ai/v1/speech/generate",
                    headers=headers,
                    json=payload
                )
            murf_res.raise_for_status()
            murf_data = murf_res.json()
            audio_url = murf_data.get("audioFile")
        except Exception as e:
            print("TTS Error:", e)
            # Use a fallback audio file URL (pre-generated, e.g., S3 bucket/static)
            audio_url = "/static/tts_fallback.wav"

        return {
            "session_id": session_id,
            "transcription": user_message,
            "llm_text": bot_reply,
            "audio_url": audio_url,
            "history": chat_history[session_id]
        }

    except Exception as e:
        print("General Error:", e)
        # Final Catch-All fallback
        return {
            "session_id": session_id,
            "transcription": "",
            "llm_text": "I'm having trouble connecting right now.",
            "audio_url": "/static/tts_fallback.wav",
            "history": chat_history.get(session_id, [])
        }



@app.delete("/agent/chat/{session_id}")
async def delete_chat_session(session_id: str):
    if session_id in chat_history:
        del chat_history[session_id]
        return {"message": "Session deleted successfully"}
    return {"message": "Session not found"}
