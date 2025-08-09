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

@app.post("/tts")
async def generate_tts(request: TTSRequest):
    if not MURF_API_KEY:
        return JSONResponse(status_code=500, content={"error": "MURF_API_KEY not set in .env"})

    headers = {
        "api-key": MURF_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "text": request.text,
        "voiceId": request.voiceId,
        "pronunciationDictionary": {
            "2010": {
                "pronunciation": "two thousand and ten",
                "type": "SAY_AS"
            },
            "live": {
                "pronunciation": "laɪv",
                "type": "IPA"
            }
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.murf.ai/v1/speech/generate",
                headers=headers,
                json=payload
            )
        response.raise_for_status()
        data = response.json()
        return {
            "audio_url": data.get("audioFile", "No audio URL returned."),
            "length_seconds": data.get("audioLengthInSeconds"),
            "word_timings": data.get("wordDurations")
        }
    except httpx.HTTPStatusError as e:
        return JSONResponse(status_code=e.response.status_code, content={"error": e.response.text})
    except Exception as ex:
        return JSONResponse(status_code=500, content={"error": str(ex)})
    

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload-audio/")
async def upload_audio(file: UploadFile = File(...)):
    file_location = f"{UPLOAD_DIR}/{file.filename}"
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": os.path.getsize(file_location)
    }


# Initialize Transcriber
transcriber = aai.Transcriber()

# Define config with SLAM-1 model
config = aai.TranscriptionConfig(
    speech_model=aai.SpeechModel.slam_1
)

@app.post("/transcribe/file")
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        # Run the blocking transcription in a thread
        transcript = await run_in_threadpool(transcriber.transcribe, tmp_path, config=config)

        # Remove temp file
        os.remove(tmp_path)

        # Return response
        return {"transcription": transcript.text}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    

@app.post("/tts/echo")
async def echo_with_murf(file: UploadFile = File(...)):
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        # Transcribe the audio
        transcript = await run_in_threadpool(transcriber.transcribe, tmp_path, config=config)

        # Clean up the temporary file
        os.remove(tmp_path)

        transcribed_text = transcript.text

        if not MURF_API_KEY:
            return JSONResponse(status_code=500, content={"error": "MURF_API_KEY not set"})

        # Prepare Murf API call
        headers = {
            "api-key": MURF_API_KEY,
            "Content-Type": "application/json"
        }

        payload = {
            "text": transcribed_text,
            "voiceId": "en-US-natalie",  # or any Murf voice ID
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.murf.ai/v1/speech/generate",
                headers=headers,
                json=payload
            )

        response.raise_for_status()
        murf_data = response.json()

        # Return the audio URL back to frontend
        return {
            "transcription": transcribed_text,
            "audio_url": murf_data.get("audioFile")
        }

    except httpx.HTTPStatusError as e:
        return JSONResponse(status_code=e.response.status_code, content={"error": e.response.text})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# Integrating a Large Language Model

class QueryRequest(BaseModel):
    text: str
    model: str = "gemini-2.5-flash"
    temperature: float = 0.7
    max_tokens: int = 1024


# object of genai
client = genai.Client()

@app.post("/llm/query")
async def query_llm(query: QueryRequest):
    try:
        # Call Gemini API
        response = client.models.generate_content(
            model=query.model,
            contents=[query.text],
            config=types.GenerateContentConfig(
                temperature=query.temperature,
                max_output_tokens=query.max_tokens
            )
        )
        
        return {"response": response.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))