document.addEventListener("DOMContentLoaded", () => {
  const recordBtn = document.getElementById("recordBtn");
  const recordBtnText = document.getElementById("recordBtnText");
  const statusDisplay = document.getElementById("status");
  const responseAudio = document.getElementById("responseAudio");
  const audioVisualizer = document.getElementById("audioVisualizer");
  const stopAudioBtn = document.getElementById("stopAudioBtn");
  const configBtn = document.getElementById("configBtn");
  const configDialog = document.getElementById("configDialog");
  const saveConfigBtn = document.getElementById("saveConfig");
  const cancelConfigBtn = document.getElementById("cancelConfig");
  const geminiKeyEl = document.getElementById("geminiKey");
  const assemblyKeyEl = document.getElementById("assemblyKey");
  const murfKeyEl = document.getElementById("murfKey");
  const murfWsUrlEl = document.getElementById("murfWsUrl");
  const murfContextIdEl = document.getElementById("murfContextId");
  const tavilyKeyEl = document.getElementById("tavilyKey");
  const websocketStatus = document.getElementById("websocket-status");
  const transcriptionStatus = document.getElementById("transcription-status");
  const conversationLog = document.getElementById("conversation-log");

  let isRecording = false;
  let microphoneSource = null,
    animationId = null,
    websocket = null;
  let processor = null,
    workletNode = null,
    stream = null;
  let currentLLMResponse = "";

  const audioContext = new (window.AudioContext || window.webkitAudioContext)({
    sampleRate: 16000,
  });
  const micAnalyser = audioContext.createAnalyser();
  micAnalyser.fftSize = 256;

  window.onload = () => {
    const params = new URLSearchParams(window.location.search);
    const sessionId =
      params.get("session_id") ||
      `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    window.history.replaceState(
      { path: `${window.location.pathname}?session_id=${sessionId}` },
      "",
      `${window.location.pathname}?session_id=${sessionId}`
    );
    window.sessionId = sessionId;
  };

  let murfAudioChunks = [];
  let murfFinalReceived = false;

  async function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/audio/${window.sessionId}`;
    websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      console.log("WebSocket connected for audio streaming");
      websocketStatus.textContent = "WebSocket: Connected";
      websocketStatus.className = "websocket-status connected";
      transcriptionStatus.textContent = "Transcription: Active";
      transcriptionStatus.className = "transcription-status active";
      statusDisplay.textContent = "WebSocket connected. Ready to record.";
    };

    websocket.onmessage = (event) => {
      const msg = event.data;
      try {
        const data = JSON.parse(msg);
        switch (data.type) {
          case "transcription":
            handleTranscription(data);
            break;
          case "llm_start":
            handleLLMStart(data);
            break;
          case "llm_chunk":
            handleLLMChunk(data);
            break;
          case "llm_complete":
            handleLLMComplete(data);
            break;
          case "llm_error":
            handleLLMError(data);
            break;
          case "murf_audio_chunk":
            if (data.audio) murfAudioChunks.push(sanitizeBase64(data.audio));
            break;
          case "murf_audio_final":
            murfFinalReceived = true;
            // Play and reset after final signal for this turn
            playCombinedWavChunks(murfAudioChunks);
            murfAudioChunks = [];
            murfFinalReceived = false;
            break;
          default:
            console.log("Unknown message type:", data);
        }
      } catch (e) {
        console.log("Non-JSON message from server:", msg);
      }
    };

    websocket.onerror = (error) => {
      console.error("WebSocket error:", error);
      websocketStatus.textContent = "WebSocket: Error";
      websocketStatus.className = "websocket-status error";
      statusDisplay.textContent = "WebSocket connection error.";
    };

    websocket.onclose = () => {
      console.log("WebSocket disconnected");
      websocketStatus.textContent = "WebSocket: Disconnected";
      websocketStatus.className = "websocket-status";
      transcriptionStatus.textContent = "Transcription: Inactive";
      transcriptionStatus.className = "transcription-status";
      websocket = null;
    };
  }

  function disconnectWebSocket() {
    if (websocket) {
      websocket.close();
      websocket = null;
    }
  }

  recordBtn.addEventListener("click", () => {
    audioContext.resume();
    isRecording ? stopRecording() : startRecording();
  });

  const requiredKeysFilled = () =>
    geminiKeyEl.value &&
    assemblyKeyEl.value &&
    murfKeyEl.value &&
    tavilyKeyEl.value;

  const updateConfigSaveState = () => {
    if (saveConfigBtn) saveConfigBtn.disabled = !requiredKeysFilled();
  };
  [geminiKeyEl, assemblyKeyEl, murfKeyEl, tavilyKeyEl].forEach(
    (el) => el && el.addEventListener("input", updateConfigSaveState)
  );

  const setRecordEnabled = (enabled) => {
    recordBtn.disabled = !enabled;
    recordBtn.classList.toggle("disabled", !enabled);
  };
  setRecordEnabled(false);

  configBtn.addEventListener("click", () => {
    try {
      configDialog.showModal();
    } catch {
      configDialog.open = true;
    }
  });
  cancelConfigBtn.addEventListener("click", () => {
    try {
      configDialog.close();
    } catch {
      configDialog.open = false;
    }
  });
  saveConfigBtn.addEventListener("click", () => {
    if (!requiredKeysFilled()) return;
    const keys = {
      GEMINI_API_KEY: geminiKeyEl.value,
      ASSEMBLYAI_API_KEY: assemblyKeyEl.value,
      MURF_API_KEY: murfKeyEl.value,
      TAVILY_API_KEY: tavilyKeyEl.value,
    };
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({ type: "set_keys", keys }));
    }
    setRecordEnabled(true);
    try {
      configDialog.close();
    } catch {
      configDialog.open = false;
    }
  });

  stopAudioBtn.addEventListener("click", () => {
    responseAudio.pause();
    responseAudio.currentTime = 0;
    stopPulseEffect();
    stopAudioBtn.style.display = "none";
  });

  async function startRecording() {
    try {
      disconnectRecording();
      await connectWebSocket();
      clearChatHistory();

      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: { ideal: 16000 },
          channelCount: { ideal: 1 },
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      microphoneSource = audioContext.createMediaStreamSource(stream);
      microphoneSource.connect(micAnalyser);

      await audioContext.audioWorklet.addModule("/static/recorderWorklet.js");
      workletNode = new AudioWorkletNode(audioContext, "recorder-worklet");
      workletNode.port.onmessage = (e) => {
        if (websocket && websocket.readyState === WebSocket.OPEN)
          websocket.send(e.data);
      };
      microphoneSource.connect(workletNode);

      startPulseEffect("recording");
      isRecording = true;
      updateUIRecording(true);
    } catch (error) {
      console.error("Microphone access error:", error);
      statusDisplay.textContent = "Microphone access denied.";
      statusDisplay.classList.add("error");
    }
  }

  function stopRecording() {
    if (isRecording) {
      isRecording = false;
      stopPulseEffect();
      disconnectRecording();
      disconnectWebSocket();
      updateUIRecording(false);
      statusDisplay.textContent = "Streaming stopped.";
    }
  }

  function disconnectRecording() {
    if (microphoneSource) microphoneSource.disconnect();
    if (processor) processor.disconnect();
    if (workletNode) workletNode.disconnect();
    if (stream) stream.getTracks().forEach((track) => track.stop());
    microphoneSource = processor = workletNode = stream = null;
  }

  function startPulseEffect(mode = "recording") {
    audioVisualizer.style.display = "block";
    const canvasCtx = audioVisualizer.getContext("2d");
    const analyser = micAnalyser;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    function draw() {
      animationId = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);
      const avg = dataArray.reduce((a, b) => a + b, 0) / bufferLength;
      canvasCtx.clearRect(0, 0, audioVisualizer.width, audioVisualizer.height);
      const radius = 60 + avg / 4;
      canvasCtx.beginPath();
      canvasCtx.arc(
        audioVisualizer.width / 2,
        audioVisualizer.height / 2,
        radius,
        0,
        2 * Math.PI
      );
      canvasCtx.strokeStyle = "rgba(153,102,255,0.7)";
      canvasCtx.lineWidth = 6;
      canvasCtx.stroke();
    }
    draw();
  }

  function stopPulseEffect() {
    if (animationId) cancelAnimationFrame(animationId);
    animationId = null;
    const canvasCtx = audioVisualizer.getContext("2d");
    canvasCtx.clearRect(0, 0, audioVisualizer.width, audioVisualizer.height);
    audioVisualizer.style.display = "none";
  }

  let lastUserBubble = null;
  let lastAiBubble = null;
  let lastTranscriptionTurn = 0;
  const userBubblesByTurn = new Map();

  function handleTranscription(data) {
    const { transcript, end_of_turn, turn_is_formatted, turn_order } = data;

    if (!transcript || transcript.trim() === "") return;

    const incomingTurn =
      typeof turn_order === "number" ? turn_order : lastTranscriptionTurn || 1;

    // Get or create the bubble for this turn
    let bubble = userBubblesByTurn.get(incomingTurn);
    const isNewTurn = incomingTurn > lastTranscriptionTurn;

    if (!bubble) {
      // If new bubble for this turn, create and store it
      bubble = document.createElement("div");
      bubble.classList.add("chat-bubble", "user-msg");
      userBubblesByTurn.set(incomingTurn, bubble);
      conversationLog.appendChild(bubble);

      // If we are starting a new turn, reset Murf buffers to avoid carryover
      if (isNewTurn) {
        murfAudioChunks = [];
        murfFinalReceived = false;
      }
    }

    lastTranscriptionTurn = Math.max(lastTranscriptionTurn, incomingTurn);

    let displayText = transcript;
    if (turn_order && turn_order > 0)
      displayText = `<span class="turn-number">Turn ${turn_order}</span> ${transcript}`;

    if (end_of_turn) {
      bubble.innerHTML = displayText;
      bubble.classList.add("complete");
      lastUserBubble = null; // but keep entry in map so formatted final updates in-place
      statusDisplay.textContent = "Turn completed. AI is thinking...";
    } else {
      bubble.innerHTML = displayText + ' <span class="live-indicator">●</span>';
      lastUserBubble = bubble;
      statusDisplay.textContent = "Listening...";
    }

    conversationLog.scrollTop = conversationLog.scrollHeight;
  }

  function handleLLMStart(data) {
    currentLLMResponse = "";
    lastAiBubble = document.createElement("div");
    lastAiBubble.classList.add("chat-bubble", "ai-msg");
    conversationLog.appendChild(lastAiBubble);
    statusDisplay.textContent = "AI is thinking...";
    conversationLog.scrollTop = conversationLog.scrollHeight;
  }

  function handleLLMChunk(data) {
    if (data.text && lastAiBubble) {
      currentLLMResponse += data.text;
      lastAiBubble.innerHTML =
        currentLLMResponse + '<span class="typing-indicator">|</span>';
      conversationLog.scrollTop = conversationLog.scrollHeight;
    }
  }

  function handleLLMComplete(data) {
    if (lastAiBubble) {
      lastAiBubble.innerHTML = data.full_response || currentLLMResponse;
      lastAiBubble.classList.add("completed");
    }
    statusDisplay.textContent = "AI response completed. Ready for next input.";

    // If for any reason Murf final wasn't received, attempt immediate playback
    if (!murfFinalReceived && murfAudioChunks.length > 0) {
      playCombinedWavChunks(murfAudioChunks);
      murfAudioChunks = [];
    }
  }

  function handleLLMError(data) {
    console.error("LLM Error:", data.error);
    statusDisplay.textContent = "Error from LLM.";
  }

  function clearChatHistory() {
    conversationLog.innerHTML = "";
    lastUserBubble = null;
    lastAiBubble = null;
    lastTranscriptionTurn = 0;
    userBubblesByTurn.clear();
    murfAudioChunks = [];
    murfFinalReceived = false;
  }

  function updateUIRecording(isRec) {
    recordBtnText.textContent = isRec ? "Stop" : "Record";
    statusDisplay.textContent = isRec ? "Recording..." : "Ready to record";
  }

  window.responseAudio = responseAudio;
});

function sanitizeBase64(str) {
  return (str || "").replace(/[^A-Za-z0-9+/=]/g, "");
}
function padBase64(str) {
  const pad = (4 - (str.length % 4)) % 4;
  return str + "=".repeat(pad);
}
function b64ToBytes(b64) {
  const clean = padBase64(sanitizeBase64(b64));
  const bin = atob(clean);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}
function isWav(bytes) {
  return (
    bytes.length >= 12 &&
    bytes[0] === 0x52 &&
    bytes[1] === 0x49 &&
    bytes[2] === 0x46 &&
    bytes[3] === 0x46 &&
    bytes[8] === 0x57 &&
    bytes[9] === 0x41 &&
    bytes[10] === 0x56 &&
    bytes[11] === 0x45
  );
}
function parseWavHeader(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let pos = 12;
  let sampleRate = 24000,
    channels = 1,
    bits = 16,
    dataOffset = -1;
  while (pos + 8 <= bytes.length) {
    const id = String.fromCharCode(
      bytes[pos],
      bytes[pos + 1],
      bytes[pos + 2],
      bytes[pos + 3]
    );
    const size = view.getUint32(pos + 4, true);
    const next = pos + 8 + size + (size % 2);
    if (id === "fmt ") {
      channels = view.getUint16(pos + 10, true);
      sampleRate = view.getUint32(pos + 12, true);
      bits = view.getUint16(pos + 22, true);
    } else if (id === "data") {
      dataOffset = pos + 8;
      break;
    }
    pos = next;
  }
  if (dataOffset < 0) throw new Error("WAV data chunk not found");
  return { sampleRate, channels, bitDepth: bits, dataOffset };
}
function createWavHeader(dataLength, sampleRate, channels, bitDepth) {
  const blockAlign = (channels * bitDepth) >> 3;
  const byteRate = sampleRate * blockAlign;
  const buffer = new ArrayBuffer(44);
  const view = new DataView(buffer);
  function writeStr(off, s) {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  }
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeStr(36, "data");
  view.setUint32(40, dataLength, true);
  return new Uint8Array(buffer);
}

async function playCombinedWavChunks(base64Chunks) {
  if (!base64Chunks || base64Chunks.length === 0) return;

  const rawChunks = base64Chunks.map(b64ToBytes);
  let fmt = { sampleRate: 24000, channels: 1, bitDepth: 16 };
  const pcmParts = [];

  for (let i = 0; i < rawChunks.length; i++) {
    const bytes = rawChunks[i];
    if (isWav(bytes)) {
      try {
        const info = parseWavHeader(bytes);
        if (i === 0)
          fmt = {
            sampleRate: info.sampleRate,
            channels: info.channels,
            bitDepth: info.bitDepth,
          };
        pcmParts.push(bytes.subarray(info.dataOffset));
      } catch {
        pcmParts.push(bytes);
      }
    } else {
      pcmParts.push(bytes);
    }
  }

  const totalLen = pcmParts.reduce((s, x) => s + x.length, 0);
  const pcmAll = new Uint8Array(totalLen);
  let off = 0;
  for (const p of pcmParts) {
    pcmAll.set(p, off);
    off += p.length;
  }

  const header = createWavHeader(
    pcmAll.length,
    fmt.sampleRate,
    fmt.channels,
    fmt.bitDepth
  );
  const wavBytes = new Uint8Array(header.length + pcmAll.length);
  wavBytes.set(header, 0);
  wavBytes.set(pcmAll, header.length);

  const blob = new Blob([wavBytes], { type: "audio/wav" });
  const url = URL.createObjectURL(blob);

  const responseAudio = window.responseAudio;
  responseAudio.src = url;
  responseAudio.style.display = "none";
  stopAudioBtn.style.display = "inline-block";

  await responseAudio.play().catch(async (err) => {
    console.warn("HTMLAudio playback failed, trying WebAudio fallback:", err);
    await playViaWebAudio(wavBytes);
  });

  responseAudio.onended = () => {
    stopPulseEffect();
    stopAudioBtn.style.display = "none";
    statusDisplay.textContent = "Ready for your next question.";
    URL.revokeObjectURL(url);
  };
}

async function playViaWebAudio(wavBytes) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const buf = await ctx.decodeAudioData(wavBytes.buffer.slice(0));
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start(0);
  } catch (err) {
    console.error("WebAudio decode failed:", err);
  }
}
