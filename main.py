
import os
import logging
import json
import re
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx
import websockets
import assemblyai as aai
import google.generativeai as genai
from collections import defaultdict
import asyncio
import time
from tavily import TavilyClient

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Load Secrets ---
load_dotenv()
MURF_API_KEY = os.getenv("MURF_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
MURF_CONTEXT_ID = os.getenv("MURF_CONTEXT_ID", "murf_context_global_1")
MURF_WS_URL = os.getenv("MURF_WS_URL", "wss://api.murf.ai/v1/speech/stream-input")
AGENT_PERSONA = os.getenv(
    "AGENT_PERSONA",
    "a friendly Buddy who speaks casually and positively like a close friend; keep replies warm, supportive, and concise, avoid markdown, and use light slang when natural"
)

# --- Weather API Configuration ---
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# Weather-related keywords and patterns
WEATHER_KEYWORDS = [
    "weather", "temperature", "forecast", "climate", "hot", "cold", "sunny", 
    "rainy", "snow", "wind", "humidity", "degrees", "celsius", "fahrenheit"
]

WEATHER_PATTERNS = [
    r"what'?s?\s+(?:the\s+)?weather\s+(?:like\s+)?(?:in|at|for)\s+([^?]+)",
    r"weather\s+(?:in|at|for)\s+([^?]+)",
    r"temperature\s+(?:in|at|for)\s+([^?]+)",
    r"how\s+(?:hot|cold)\s+(?:is\s+it\s+)?(?:in|at)\s+([^?]+)",
    r"forecast\s+(?:for|in)\s+([^?]+)",
    r"climate\s+(?:in|at)\s+([^?]+)"
]

if ASSEMBLYAI_API_KEY:
    aai.settings.api_key = ASSEMBLYAI_API_KEY
else:
    logging.warning("ASSEMBLYAI_API_KEY not set.")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logging.warning("GEMINI_API_KEY not set.")

# --- Tavily Client ---
try:
    tavily_client: TavilyClient | None = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None
    if tavily_client is None:
        logging.warning("TAVILY_API_KEY not set. Web search disabled.")
except Exception as e:
    tavily_client = None
    logging.error(f"Failed to initialize Tavily client: {e}")

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

chat_history = defaultdict(list)


# --- Weather Skill Functions ---
async def get_coordinates(city_name: str) -> tuple[float, float] | None:
    """Get latitude and longitude for a city using Open-Meteo Geocoding API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"name": city_name.strip(), "count": 1, "language": "en", "format": "json"}
            response = await client.get(GEOCODING_API_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                logging.warning(f"No coordinates found for city: {city_name}")
                return None
            
            location = results[0]
            lat = location.get("latitude")
            lon = location.get("longitude")
            
            if lat is None or lon is None:
                logging.warning(f"Invalid coordinates for city: {city_name}")
                return None
            
            logging.info(f"Found coordinates for {city_name}: {lat}, {lon}")
            return float(lat), float(lon)
            
    except Exception as e:
        logging.error(f"Error getting coordinates for {city_name}: {e}")
        return None


async def get_weather(lat: float, lon: float) -> dict | None:
    """Get current weather data using Open-Meteo Weather API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
            }
            response = await client.get(WEATHER_API_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            current_weather = data.get("current_weather", {})
            hourly_data = data.get("hourly", {})
            
            if not current_weather:
                logging.warning("No current weather data received")
                return None
            
            # Get current hour index
            current_time = current_weather.get("time")
            if current_time and hourly_data.get("time"):
                try:
                    current_hour_idx = hourly_data["time"].index(current_time)
                except ValueError:
                    current_hour_idx = 0
            else:
                current_hour_idx = 0
            
            # Weather code descriptions
            weather_descriptions = {
                0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Foggy", 48: "Depositing rime fog", 51: "Light drizzle",
                53: "Moderate drizzle", 55: "Dense drizzle", 56: "Light freezing drizzle",
                57: "Dense freezing drizzle", 61: "Slight rain", 63: "Moderate rain",
                65: "Heavy rain", 66: "Light freezing rain", 67: "Heavy freezing rain",
                71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
                77: "Snow grains", 80: "Slight rain showers", 81: "Moderate rain showers",
                82: "Violent rain showers", 85: "Slight snow showers", 86: "Heavy snow showers",
                95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
            }
            
            weather_code = current_weather.get("weathercode", 0)
            description = weather_descriptions.get(weather_code, "Unknown")
            
            # Get additional data from hourly if available
            humidity = None
            if hourly_data.get("relative_humidity_2m") and len(hourly_data["relative_humidity_2m"]) > current_hour_idx:
                humidity = hourly_data["relative_humidity_2m"][current_hour_idx]
            
            wind_speed = current_weather.get("windspeed")
            if wind_speed is None and hourly_data.get("wind_speed_10m") and len(hourly_data["wind_speed_10m"]) > current_hour_idx:
                wind_speed = hourly_data["wind_speed_10m"][current_hour_idx]
            
            weather_data = {
                "temperature": current_weather.get("temperature"),
                "wind_speed": wind_speed,
                "description": description,
                "weather_code": weather_code,
                "humidity": humidity
            }
            
            logging.info(f"Weather data retrieved: {weather_data}")
            return weather_data
            
    except Exception as e:
        logging.error(f"Error getting weather data: {e}")
        return None


async def weather_skill(city_name: str) -> dict | None:
    """Complete weather skill: get coordinates and weather data for a city."""
    try:
        # Get coordinates
        coords = await get_coordinates(city_name)
        if not coords:
            return {
                "error": f"Sorry, I couldn't find the city '{city_name}'. Could you check the spelling or try a different city?"
            }
        
        lat, lon = coords
        
        # Get weather data
        weather_data = await get_weather(lat, lon)
        if not weather_data:
            return {
                "error": f"I'm having trouble getting the weather for {city_name} right now. Please try again later."
            }
        
        # Format the response
        response = {
            "city": city_name.strip(),
            "temperature": weather_data["temperature"],
            "wind_speed": weather_data["wind_speed"],
            "description": weather_data["description"],
            "humidity": weather_data.get("humidity")
        }
        
        logging.info(f"Weather skill response: {response}")
        return response
        
    except Exception as e:
        logging.error(f"Weather skill error: {e}")
        return {
            "error": "Sorry, I'm having trouble with the weather service right now."
        }


def is_weather_query(text: str) -> tuple[bool, str | None]:
    """Check if the user query is about weather and extract city name."""
    text_lower = text.lower().strip()
    
    # Check for weather keywords
    has_weather_keyword = any(keyword in text_lower for keyword in WEATHER_KEYWORDS)
    
    if not has_weather_keyword:
        return False, None
    
    # Extract city name using patterns
    for pattern in WEATHER_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            city_name = match.group(1).strip()
            # Clean up the city name
            city_name = re.sub(r'\?|\.|!|,', '', city_name).strip()
            if city_name:
                return True, city_name
    
    # If we have weather keywords but no city pattern match, try to extract city
    # This handles cases like "weather Paris" or "temperature in London"
    words = text_lower.split()
    for i, word in enumerate(words):
        if word in WEATHER_KEYWORDS and i + 1 < len(words):
            potential_city = words[i + 1]
            # Skip common words that aren't cities
            if potential_city not in ['in', 'at', 'for', 'the', 'is', 'like', 'today', 'now']:
                return True, potential_city
    
    return False, None


def format_weather_response(weather_data: dict) -> str:
    """Format weather data into a natural language response."""
    if "error" in weather_data:
        return weather_data["error"]
    
    city = weather_data["city"]
    temp = weather_data["temperature"]
    wind = weather_data["wind_speed"]
    desc = weather_data["description"]
    humidity = weather_data.get("humidity")
    
    # Format temperature
    temp_str = f"{temp:.1f}°C"
    
    # Format wind speed
    wind_str = f"{wind:.1f} km/h"
    
    # Build response
    response_parts = [f"Here's the weather in {city}:"]
    response_parts.append(f"It's currently {temp_str} with {desc.lower()}.")
    
    if wind and wind > 0:
        response_parts.append(f"The wind is blowing at {wind_str}.")
    
    if humidity:
        response_parts.append(f"Humidity is at {humidity}%.")
    
    return " ".join(response_parts)


# --- Web Search Helper (Tavily) ---
def webSearch(query: str, api_key: str | None = None) -> str:
    """Run a Tavily web search and return a clean, formatted summary with sources.

    Uses API key from .env via dotenv. Returns human-readable text.
    """
    # Prefer override key if provided
    client = None
    try:
        if api_key:
            client = TavilyClient(api_key=api_key)
        else:
            client = tavily_client
    except Exception:
        client = None

    if not client:
        return "Web search is unavailable: missing or invalid TAVILY_API_KEY."

    try:
        response = client.search(
            query=query,
            search_depth="advanced",
            include_images=False,
            include_answer=True,
            max_results=8,
        )

        answer = (response.get("answer") or "").strip()
        results = response.get("results", []) or []

        if answer:
            return answer

        # Fallback: use the first result content without including sources
        if results:
            content = (results[0].get("content") or "").strip()
            # Return a concise snippet
            return content[:1200] if content else "No summary available."

        return "No summary available."
    except Exception as e:
        logging.error(f"Tavily search error: {e}")
        return "Sorry, web search failed. Please try again later."


# --- Web Query Detection ---
def is_web_query(text: str) -> bool:
    """Heuristic: detect queries better answered via web search (news, prices, winners, latest)."""
    t = (text or "").lower()
    keywords = [
        "who won", "winner", "latest", "breaking", "news", "today",
        "price", "prices", "cost", "how much", "release date", "2024", "2025", "2026",
        "score", "result", "final", "vs ", "schedule", "fixtures",
    ]
    # If it's a weather query, exclude here (weather handled separately)
    is_weather, _ = is_weather_query(t)
    if is_weather:
        return False
    return any(k in t for k in keywords)


# --- Audio Streamer Class ---
class AudioStreamer:
    def __init__(self):
        self.active_sessions = {}
        self.streaming_clients = {}
        self.session_websockets = {}
        self.pending_transcriptions = {}
        self.final_transcripts = {}
        self.session_keys = {}

    def set_session_keys(self, session_id: str, keys: dict):
        safe = {}
        for k, v in (keys or {}).items():
            if isinstance(v, str) and v.strip():
                safe[k.strip().upper()] = v.strip()
        self.session_keys[session_id] = safe

    def get_session_key(self, session_id: str, name: str) -> str | None:
        return (self.session_keys.get(session_id, {}) or {}).get(name.upper())

    async def start_streaming(self, session_id: str, websocket=None):
        self.session_websockets[session_id] = websocket
        
        try:
            session_assembly_key = self.get_session_key(session_id, "ASSEMBLYAI_API_KEY")
            effective_assembly_key = session_assembly_key or ASSEMBLYAI_API_KEY
            if effective_assembly_key:
                from assemblyai.streaming.v3 import (
                    BeginEvent,
                    StreamingClient,
                    StreamingClientOptions,
                    StreamingError,
                    StreamingEvents,
                    StreamingParameters,
                    TerminationEvent,
                    TurnEvent,
                )

                def on_begin(client_instance, event: BeginEvent):
                    logging.info(f"AssemblyAI session started: {event.id}")

                def on_turn(client_instance, event: TurnEvent):
                    if event.transcript:
                        logging.info(f"AssemblyAI transcription turn received: {event.transcript}")
                        if session_id not in self.pending_transcriptions:
                            self.pending_transcriptions[session_id] = []
                        message = {
                            "type": "transcription",
                            "transcript": event.transcript,
                            "end_of_turn": event.end_of_turn,
                            "turn_is_formatted": event.turn_is_formatted,
                            "turn_order": event.turn_order
                        }
                        self.pending_transcriptions[session_id].append(message)
                        
                        if event.end_of_turn and event.turn_is_formatted:
                            self.final_transcripts[session_id] = event.transcript

                def on_terminated(client_instance, event: TerminationEvent):
                    logging.info(f"AssemblyAI session terminated: {event.audio_duration_seconds} seconds")

                def on_error(client_instance, error: StreamingError):
                    logging.error(f"AssemblyAI error: {error}")

                client = StreamingClient(
                    StreamingClientOptions(
                        api_key=effective_assembly_key,
                        api_host="streaming.assemblyai.com",
                    )
                )

                client.on(StreamingEvents.Begin, on_begin)
                client.on(StreamingEvents.Turn, on_turn)
                client.on(StreamingEvents.Termination, on_terminated)
                client.on(StreamingEvents.Error, on_error)

                client.connect(
                    StreamingParameters(
                        sample_rate=16000,
                        format_turns=True,
                    )
                )
                self.streaming_clients[session_id] = client
                logging.info(f"AssemblyAI Universal Streaming client started for session: {session_id}")
            else:
                logging.warning("AssemblyAI API key not set. Transcription disabled.")
                self.streaming_clients[session_id] = None
        except Exception as e:
            logging.error(f"Failed to initialize AssemblyAI client: {e}")
            self.streaming_clients[session_id] = None
        
        self.active_sessions[session_id] = {'start_time': time.time()}
        logging.info(f"Started streaming session {session_id}")
        return session_id

    async def stream_audio_data(self, session_id: str, audio_data: bytes):
        if session_id not in self.active_sessions:
            logging.warning(f"Received audio data for unknown session: {session_id}")
            return
        
        logging.info(f"Received audio data for session {session_id}, size {len(audio_data)} bytes")

        if session_id in self.streaming_clients and self.streaming_clients[session_id]:
            try:
                self.streaming_clients[session_id].stream(audio_data)
            except Exception as e:
                logging.error(f"Error streaming audio to AssemblyAI: {e}")

        session_websocket = self.session_websockets.get(session_id)
        if session_websocket and session_id in self.pending_transcriptions:
            pending_messages = self.pending_transcriptions[session_id]
            if pending_messages:
                try:
                    for message in pending_messages:
                        logging.info(f"Sending transcription to client: {message['transcript']}")
                        await session_websocket.send_text(json.dumps(message))
                    self.pending_transcriptions[session_id] = []
                except Exception as e:
                    logging.error(f"Error sending transcriptions: {e}")

        if session_id in self.final_transcripts:
            final_transcript = self.final_transcripts[session_id]
            asyncio.create_task(self.stream_llm_response(session_id, final_transcript, session_websocket))
            del self.final_transcripts[session_id]

    async def stop_streaming(self, session_id: str):
        if session_id not in self.active_sessions:
            logging.warning(f"Attempted to stop unknown streaming session: {session_id}")
            return None
        
        if session_id in self.streaming_clients and self.streaming_clients[session_id]:
            try:
                self.streaming_clients[session_id].disconnect(terminate=True)
                logging.info("AssemblyAI Streaming client disconnected")
            except Exception as e:
                logging.error(f"Error disconnecting AssemblyAI client: {e}")
            del self.streaming_clients[session_id]

        duration = time.time() - self.active_sessions[session_id]['start_time']
        logging.info(f"Stopped streaming session {session_id} duration: {duration:.2f}s")

        del self.active_sessions[session_id]
        self.session_websockets.pop(session_id, None)
        self.pending_transcriptions.pop(session_id, None)
        self.final_transcripts.pop(session_id, None)
        return session_id

    async def stream_llm_response(self, session_id: str, user_text: str, websocket):
        session_gemini_key = self.get_session_key(session_id, "GEMINI_API_KEY")
        effective_gemini_key = session_gemini_key or GEMINI_API_KEY
        if not effective_gemini_key:
            logging.error("Gemini API key not set")
            return

        try:
            logging.info(f"Starting LLM streaming for session {session_id}")
            if session_id not in chat_history:
                chat_history[session_id] = []
            chat_history[session_id].append({"role": "user", "parts": [user_text]})

            # Check if this is a weather query
            is_weather, city_name = is_weather_query(user_text)
            
            if is_weather and city_name:
                logging.info(f"Weather query detected for city: {city_name}")
                await websocket.send_text(json.dumps({"type": "llm_start", "transcript": user_text}))
                
                # Get weather data
                weather_data = await weather_skill(city_name)
                weather_response = format_weather_response(weather_data)
                
                # Stream the weather response
                await websocket.send_text(json.dumps({
                    "type": "llm_chunk",
                    "text": weather_response,
                    "is_complete": True
                }))
                
                await websocket.send_text(json.dumps({
                    "type": "llm_complete",
                    "full_response": weather_response,
                    "is_complete": True
                }))
                
                # Add to chat history
                chat_history[session_id].append({"role": "model", "parts": [weather_response]})
                
                # Stream TTS for weather response
                if MURF_API_KEY or self.get_session_key(session_id, "MURF_API_KEY"):
                    asyncio.create_task(self.stream_tts(weather_response, websocket, session_id))
                
                return

            # Web search route if detected
            if is_web_query(user_text):
                logging.info("Web query detected; performing Tavily search")
                await websocket.send_text(json.dumps({"type": "llm_start", "transcript": user_text}))
                web_text = webSearch(user_text)

                # Start Murf TTS streaming for web search response as well
                if MURF_API_KEY or self.get_session_key(session_id, "MURF_API_KEY"):
                    asyncio.create_task(self.stream_tts(web_text, websocket, session_id))

                await websocket.send_text(json.dumps({
                    "type": "llm_chunk",
                    "text": web_text,
                    "is_complete": True
                }))
                await websocket.send_text(json.dumps({
                    "type": "llm_complete",
                    "full_response": web_text,
                    "is_complete": True
                }))
                chat_history[session_id].append({"role": "model", "parts": [web_text]})
                return

            # Fallback to normal Gemini response
            genai.configure(api_key=effective_gemini_key)
            model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=f"You are {AGENT_PERSONA}. Keep responses brief, natural, and easy to speak aloud. Avoid markdown unless necessary.")

            await websocket.send_text(json.dumps({"type": "llm_start", "transcript": user_text}))

            loop = asyncio.get_running_loop()
            full_response_ref = {"text": ""}

            async def murf_streamer(text_stream_queue: asyncio.Queue):
                if not MURF_API_KEY:
                    logging.warning("MURF_API_KEY not set; skipping TTS streaming")
                    return
                uri = f"{MURF_WS_URL}?api-key={MURF_API_KEY}&sample_rate=44100&channel_type=MONO&format=WAV"
                try:
                    async with websockets.connect(uri) as murf_ws:
                        voice_config_msg = {
                            "voice_config": {
                                "voiceId": "en-US-amara",
                                "style": "Conversational",
                                "rate": 0,
                                "pitch": 0,
                                "variation": 1
                            },
                            "context_id": MURF_CONTEXT_ID
                        }
                        await murf_ws.send(json.dumps(voice_config_msg))

                        async def receiver():
                            async for msg in murf_ws:
                                try:
                                    data = json.loads(msg)
                                except Exception:
                                    continue
                                if "audio" in data:
                                    audio_b64 = data.get("audio")
                                    if audio_b64:
                                        await websocket.send_text(json.dumps({
                                            "type": "murf_audio_chunk",
                                            "audio": audio_b64
                                        }))
                                if data.get("final"):
                                    # Signal to the frontend that Murf has finished sending audio for this response
                                    try:
                                        await websocket.send_text(json.dumps({"type": "murf_audio_final"}))
                                    except Exception:
                                        pass
                                    break
                        recv_task = asyncio.create_task(receiver())

                        chunk_id = 0
                        while True:
                            chunk = await text_stream_queue.get()
                            if chunk is None:
                                break
                            await murf_ws.send(json.dumps({
                                "text": chunk,
                                "context_id": MURF_CONTEXT_ID
                            }))
                            chunk_id += 1

                        await murf_ws.send(json.dumps({"text": "", "end": True, "context_id": MURF_CONTEXT_ID}))
                        try:
                            await asyncio.wait_for(recv_task, timeout=2.0)
                        except asyncio.TimeoutError:
                            recv_task.cancel()
                except Exception as ex:
                    logging.error(f"Murf websocket error: {ex}")

            text_queue: asyncio.Queue[str | None] = asyncio.Queue()
            murf_task = asyncio.create_task(murf_streamer(text_queue))

            def stream_sync():
                try:
                    stream = model.generate_content(
                        user_text,
                        stream=True,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.7,
                            top_p=0.8,
                            top_k=40,
                            max_output_tokens=2048,
                        )
                    )
                    for chunk in stream:
                        text_chunk = getattr(chunk, "text", "") or ""
                        if text_chunk:
                            full_response_ref["text"] += text_chunk
                            msg = json.dumps({
                                "type": "llm_chunk",
                                "text": text_chunk,
                                "is_complete": False
                            })
                            loop.call_soon_threadsafe(asyncio.create_task, websocket.send_text(msg))
                            loop.call_soon_threadsafe(asyncio.create_task, text_queue.put(text_chunk))
                    try:
                        stream.resolve()
                    except Exception:
                        pass
                    complete_msg = json.dumps({
                        "type": "llm_complete",
                        "full_response": full_response_ref["text"],
                        "is_complete": True
                    })
                    loop.call_soon_threadsafe(asyncio.create_task, websocket.send_text(complete_msg))
                    loop.call_soon_threadsafe(asyncio.create_task, text_queue.put(None))
                    logging.info(f"LLM streaming completed")
                except Exception as ex:
                    err_msg = json.dumps({"type": "llm_error", "error": str(ex)})
                    loop.call_soon_threadsafe(asyncio.create_task, websocket.send_text(err_msg))

            await asyncio.to_thread(stream_sync)
            try:
                await asyncio.wait_for(murf_task, timeout=5.0)
            except asyncio.TimeoutError:
                murf_task.cancel()

            if full_response_ref["text"]:
                chat_history[session_id].append({"role": "model", "parts": [full_response_ref["text"]]})

        except Exception as e:
            logging.error(f"LLM streaming error: {e}")
            try:
                await websocket.send_text(json.dumps({"type": "llm_error", "error": str(e)}))
            except:
                pass

    async def stream_tts(self, text: str, websocket, session_id: str):
        """Stream TTS for responses using Murf (per-session key if provided)."""
        session_murf_key = self.get_session_key(session_id, "MURF_API_KEY")
        session_ws_url = self.get_session_key(session_id, "MURF_WS_URL")
        session_ctx_id = self.get_session_key(session_id, "MURF_CONTEXT_ID")

        effective_murf_key = session_murf_key or MURF_API_KEY
        effective_ws_url = session_ws_url or MURF_WS_URL
        effective_ctx_id = session_ctx_id or MURF_CONTEXT_ID

        if not effective_murf_key:
            return

        uri = f"{effective_ws_url}?api-key={effective_murf_key}&sample_rate=44100&channel_type=MONO&format=WAV"
        try:
            async with websockets.connect(uri) as murf_ws:
                voice_config_msg = {
                    "voice_config": {
                        "voiceId": "en-US-amara",
                        "style": "Conversational",
                        "rate": 0,
                        "pitch": 0,
                        "variation": 1
                    },
                    "context_id": effective_ctx_id
                }
                await murf_ws.send(json.dumps(voice_config_msg))

                async def receiver():
                    async for msg in murf_ws:
                        try:
                            data = json.loads(msg)
                        except Exception:
                            continue
                        if "audio" in data:
                            audio_b64 = data.get("audio")
                            if audio_b64:
                                await websocket.send_text(json.dumps({
                                    "type": "murf_audio_chunk",
                                    "audio": audio_b64
                                }))
                        if data.get("final"):
                            try:
                                await websocket.send_text(json.dumps({"type": "murf_audio_final"}))
                            except Exception:
                                pass
                            break
                
                recv_task = asyncio.create_task(receiver())
                
                # Send the weather text
                await murf_ws.send(json.dumps({
                    "text": text,
                    "context_id": effective_ctx_id
                }))
                
                await murf_ws.send(json.dumps({"text": "", "end": True, "context_id": effective_ctx_id}))
                
                try:
                    await asyncio.wait_for(recv_task, timeout=5.0)
                except asyncio.TimeoutError:
                    recv_task.cancel()
                    
        except Exception as ex:
            logging.error(f"TTS error: {ex}")


audio_streamer = AudioStreamer()


@app.websocket("/ws/audio/{session_id}")
async def websocket_audio_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logging.info(f"WebSocket connection established for session: {session_id}")

    await audio_streamer.start_streaming(session_id, websocket)
    await websocket.send_text(f"Streaming started: {session_id}")

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                await audio_streamer.stream_audio_data(session_id, message["bytes"])
            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"]) if message["text"].strip().startswith("{") else None
                except Exception:
                    payload = None
                if isinstance(payload, dict) and payload.get("type") == "set_keys":
                    audio_streamer.set_session_keys(session_id, payload.get("keys") or {})
                    await websocket.send_text(json.dumps({"type": "keys_ack", "ok": True}))

    except WebSocketDisconnect:
        logging.info(f"WebSocket disconnected for session: {session_id}")
        await audio_streamer.stop_streaming(session_id)
    except Exception as e:
        logging.error(f"WebSocket error for session {session_id}: {e}")
        await audio_streamer.stop_streaming(session_id)


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


@app.get("/proxy-audio/")
async def proxy_audio(url: str):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            return StreamingResponse(
                iter([r.content]),
                media_type="audio/mpeg",
                headers={"Access-Control-Allow-Origin": "*"}
            )
        except httpx.RequestError as e:
            logging.error(f"Audio proxy failed: {e.request.url} - {e}")
            raise HTTPException(status_code=502, detail="Could not fetch audio.")


@app.post("/tts")
async def generate_tts(text: str):
    if not MURF_API_KEY:
        logging.error("TTS endpoint called but MURF_API_KEY missing.")
        raise HTTPException(status_code=500, detail="TTS service not configured.")
    headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
    payload = {"text": text, "voiceId": "en-US-natalie"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post("https://api.murf.ai/v1/speech/generate", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            audio_url = data.get("audioFile")
            if not audio_url:
                logging.error("Murf API succeeded but no audioFile.")
                raise HTTPException(status_code=502, detail="TTS API error: no audio.")
            return {"audio_url": audio_url}
    except Exception as e:
        logging.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail="TTS internal error.")


async def generate_fallback_audio(msg="I'm sorry, I'm having trouble connecting right now. Please try again later."):
    if not MURF_API_KEY:
        return None
    headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
    payload = {"text": msg, "voiceId": "en-US-marcus"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            murf_resp = await client.post("https://api.murf.ai/v1/speech/generate", headers=headers, json=payload)
            murf_resp.raise_for_status()
            return murf_resp.json().get("audioFile")
    except Exception as e:
        logging.error(f"Fallback audio error: {e}")
        return None


@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    try:
        if not ASSEMBLYAI_API_KEY:
            raise ValueError("AssemblyAI API key not set.")
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(file.file)
        if transcript.error:
            raise RuntimeError(f"Transcription Error: {transcript.error}")
        user_text = (transcript.text or "").strip()
        if not user_text:
            return JSONResponse(status_code=400, content={"error": "No speech detected. Please speak clearly."})
    except Exception as e:
        logging.error(f"Transcription error: {e}")
        fallback_audio_url = await generate_fallback_audio()
        if fallback_audio_url:
            return JSONResponse(status_code=503, content={"error": "Could not process your audio.", "audio_url": fallback_audio_url})
        return JSONResponse(status_code=503, content={"error": "Speech-to-text unavailable."})

    chat_history[session_id].append({"role": "user", "parts": [user_text]})

    # Check if this is a weather query
    is_weather, city_name = is_weather_query(user_text)
    
    if is_weather and city_name:
        logging.info(f"Weather query detected for city: {city_name}")
        
        # Get weather data
        weather_data = await weather_skill(city_name)
        weather_response = format_weather_response(weather_data)
        
        # Add to chat history
        chat_history[session_id].append({"role": "model", "parts": [weather_response]})
        
        # Generate TTS for weather response
        try:
            if not MURF_API_KEY:
                raise ValueError("Murf API key not set.")
            murf_text = weather_response[:2900]
            headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
            payload = {"text": murf_text, "voiceId": "en-US-marcus"}
            async with httpx.AsyncClient(timeout=90) as client:
                murf_resp = await client.post("https://api.murf.ai/v1/speech/generate", headers=headers, json=payload)
                murf_resp.raise_for_status()
                audio_url = murf_resp.json().get("audioFile")
                if not audio_url:
                    raise RuntimeError("Murf API no audio URL.")
        except Exception as e:
            logging.error(f"TTS error for weather response: {e}")
            return JSONResponse(status_code=503, content={"error": "Voice generation unavailable.", "transcription": user_text, "llm_response": weather_response})

        return {
            "audio_url": audio_url,
            "transcription": user_text,
            "llm_response": weather_response,
            "weather_data": weather_data if "error" not in weather_data else None
        }

    # Web search route if detected
    if is_web_query(user_text):
        logging.info("Web query detected; performing Tavily search (HTTP)")
        web_text = webSearch(user_text)
        # Optionally TTS for web_text
        try:
            if not MURF_API_KEY:
                raise ValueError("Murf API key not set.")
            murf_text = web_text[:2900]
            headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
            payload = {"text": murf_text, "voiceId": "en-US-marcus"}
            async with httpx.AsyncClient(timeout=90) as client:
                murf_resp = await client.post("https://api.murf.ai/v1/speech/generate", headers=headers, json=payload)
                murf_resp.raise_for_status()
                audio_url = murf_resp.json().get("audioFile")
                if not audio_url:
                    raise RuntimeError("Murf API no audio URL.")
        except Exception as e:
            logging.error(f"TTS error for web search response: {e}")
            audio_url = None

        return {
            "audio_url": audio_url,
            "transcription": user_text,
            "llm_response": web_text,
            "web_search": True
        }

    # Fallback to normal Gemini response
    try:
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key not set.")
        model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=f"You are {AGENT_PERSONA}. Keep responses brief, natural, and easy to speak aloud. Avoid markdown unless necessary.")
        conversation = model.start_chat(history=chat_history[session_id][:-1])
        llm_response = conversation.send_message(user_text)
        llm_text = (llm_response.text or "").strip()
        if not llm_text:
            raise RuntimeError("LLM returned empty response.")
    except Exception as e:
        logging.error(f"LLM error: {e}")
        chat_history[session_id].pop()
        fallback_audio_url = await generate_fallback_audio("The AI model is currently unavailable.")
        if fallback_audio_url:
            return JSONResponse(status_code=503, content={"error": "AI Model unavailable.", "audio_url": fallback_audio_url, "transcription": user_text})
        return JSONResponse(status_code=503, content={"error": "AI Model unavailable."})

    chat_history[session_id].append({"role": "model", "parts": [llm_text]})

    try:
        if not MURF_API_KEY:
            raise ValueError("Murf API key not set.")
        murf_text = llm_text[:2900]
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        payload = {"text": murf_text, "voiceId": "en-US-marcus"}
        async with httpx.AsyncClient(timeout=90) as client:
            murf_resp = await client.post("https://api.murf.ai/v1/speech/generate", headers=headers, json=payload)
            murf_resp.raise_for_status()
            audio_url = murf_resp.json().get("audioFile")
            if not audio_url:
                raise RuntimeError("Murf API no audio URL.")
    except Exception as e:
        logging.error(f"TTS error: {e}")
        return JSONResponse(status_code=503, content={"error": "Voice generation unavailable.", "transcription": user_text, "llm_response": llm_text})

    return {
        "audio_url": audio_url,
        "transcription": user_text,
        "llm_response": llm_text
    }


if __name__ == "__main__":
    try:
        demo_query = "latest AI trends 2025"
        print("\n[Tavily Demo] Query:", demo_query)
        print("[Tavily Demo] Results:\n")
        print(webSearch(demo_query))
    except Exception as demo_ex:
        logging.error(f"Demo run failed: {demo_ex}")
