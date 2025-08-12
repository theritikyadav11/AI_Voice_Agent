function generateAudio() {
  const text = document.getElementById("textInput").value.trim();
  const loader = document.getElementById("loader");
  const audioContainer = document.getElementById("audioContainer");
  const audioPlayer = document.getElementById("audioPlayer");

  if (!text) {
    alert("Please enter some text.");
    return;
  }

  loader.style.display = "block";
  audioContainer.style.display = "none";

  fetch("/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text }),
  })
    .then((response) => response.json())
    .then((data) => {
      loader.style.display = "none";
      if (data.audio_url) {
        audioPlayer.src = data.audio_url;
        audioContainer.style.display = "block";
      } else {
        alert("Audio generation failed.");
      }
    })
    .catch((error) => {
      loader.style.display = "none";
      console.error("Error:", error);
      alert("Something went wrong. Please try again.");
    });
}

// Echo bot logic

const record = document.querySelector(".record");
const stop = document.querySelector(".stop");
const soundClips = document.querySelector(".sound-clips");
const canvas = document.querySelector(".visualizer");
const mainSection = document.querySelector(".main-controls");
const flashMessage = document.getElementById("flash-message");

stop.disabled = true;

let audioCtx;
let lastRecordedBlob = null;
const canvasCtx = canvas.getContext("2d");

// Add Murf Voice button and audio player
const getMurfBtn = document.createElement("button");
getMurfBtn.textContent = "Get Murf Voice";
getMurfBtn.className = "get-murf";
getMurfBtn.disabled = true;

const murfAudioContainer = document.createElement("div");
const murfAudioLabel = document.createElement("div");
murfAudioLabel.textContent = "Murf Voice:";
murfAudioLabel.style.margin = "10px 0 4px";
murfAudioLabel.style.fontWeight = "bold";
murfAudioLabel.style.color = "#ffffff";
murfAudioLabel.style.display = "none";

const murfAudioPlayer = document.createElement("audio");
murfAudioPlayer.setAttribute("controls", "");
murfAudioPlayer.style.display = "none";

murfAudioContainer.appendChild(murfAudioLabel);
murfAudioContainer.appendChild(murfAudioPlayer);

mainSection.appendChild(getMurfBtn);
mainSection.appendChild(murfAudioContainer);

if (navigator.mediaDevices.getUserMedia) {
  const constraints = { audio: true };
  let chunks = [];

  const onSuccess = function (stream) {
    const mediaRecorder = new MediaRecorder(stream);
    visualize(stream);

    record.onclick = function () {
      mediaRecorder.start();
      record.style.background = "red";
      stop.disabled = false;
      record.disabled = true;
      showFlashMessage("Recording started...");
    };

    stop.onclick = function () {
      mediaRecorder.stop();
      record.style.background = "";
      stop.disabled = true;
      record.disabled = false;
      showFlashMessage("Recording stopped.");
    };

    mediaRecorder.onstop = function () {
      const clipName = prompt(
        "Enter a name for your sound clip?",
        "My unnamed clip"
      );

      const clipContainer = document.createElement("article");

      // USER VOICE LABEL
      const userVoiceLabel = document.createElement("div");
      userVoiceLabel.textContent = "User Voice:";
      userVoiceLabel.style.marginBottom = "4px";
      userVoiceLabel.style.fontWeight = "bold";
      userVoiceLabel.style.color = "#ffffff";
      clipContainer.appendChild(userVoiceLabel);

      const clipLabel = document.createElement("p");
      const audio = document.createElement("audio");
      const deleteButton = document.createElement("button");
      const uploadButton = document.createElement("button");

      clipContainer.classList.add("clip");
      audio.setAttribute("controls", "");
      deleteButton.textContent = "Delete";
      uploadButton.textContent = "Transcribe";
      deleteButton.className = "delete";
      uploadButton.className = "upload";

      clipLabel.textContent = clipName || "My unnamed clip";

      clipContainer.appendChild(audio);
      clipContainer.appendChild(clipLabel);
      clipContainer.appendChild(deleteButton);
      clipContainer.appendChild(uploadButton);
      soundClips.appendChild(clipContainer);

      const blob = new Blob(chunks, { type: mediaRecorder.mimeType });
      lastRecordedBlob = blob;
      chunks = [];

      const audioURL = window.URL.createObjectURL(blob);
      audio.src = audioURL;

      // Enable Murf Button
      getMurfBtn.disabled = false;

      deleteButton.onclick = function (e) {
        e.target.closest(".clip").remove();
      };

      clipLabel.onclick = function () {
        const existingName = clipLabel.textContent;
        const newClipName = prompt("Enter a new name for your sound clip?");
        clipLabel.textContent = newClipName || existingName;
      };

      uploadButton.onclick = function () {
        const fileName = `${clipName || "recording"}.webm`;
        const formData = new FormData();
        formData.append("file", blob, fileName);

        fetch("http://127.0.0.1:8000/transcribe/file", {
          method: "POST",
          body: formData,
        })
          .then((res) => res.json())
          .then((data) => {
            const resultDiv = document.getElementById("transcription-result");
            if (data.transcription) {
              resultDiv.textContent = `Transcription: ${data.transcription}`;
              resultDiv.style.color = "white";
              showFlashMessage("✅ Transcription successful");
            } else {
              resultDiv.textContent = "❌ Transcription failed.";
              resultDiv.style.color = "red";
              showFlashMessage("❌ Transcription failed", true);
            }
          })
          .catch((err) => {
            console.error("Transcription error:", err);
            const resultDiv = document.getElementById("transcription-result");
            resultDiv.textContent = "Transcription error.";
            resultDiv.style.color = "red";
            showFlashMessage("❌ Transcription error", true);
          });
      };
    };

    mediaRecorder.ondataavailable = function (e) {
      chunks.push(e.data);
    };
  };

  const onError = function (err) {
    console.log("The following error occurred: " + err);
  };

  navigator.mediaDevices.getUserMedia(constraints).then(onSuccess, onError);
} else {
  console.log("MediaDevices.getUserMedia() not supported on your browser!");
}

getMurfBtn.onclick = function () {
  if (!lastRecordedBlob) {
    alert("No audio recorded yet.");
    return;
  }

  const formData = new FormData();
  formData.append("file", lastRecordedBlob, "recording.webm");

  getMurfBtn.textContent = "Generating Murf Voice... ⏳";
  getMurfBtn.disabled = true;

  fetch("http://127.0.0.1:8000/tts/echo", {
    method: "POST",
    body: formData,
  })
    .then((res) => res.json())
    .then((data) => {
      getMurfBtn.textContent = "Get Murf Voice";
      getMurfBtn.disabled = false;

      if (data.audio_url) {
        murfAudioLabel.style.display = "block";
        murfAudioPlayer.src = data.audio_url;
        murfAudioPlayer.style.display = "block";
        murfAudioPlayer.play();

        const resultDiv = document.getElementById("transcription-result");
        resultDiv.textContent = `Murf Transcription: ${data.transcription}`;
        resultDiv.style.color = "lightgreen";

        showFlashMessage("✅ Murf voice generated!");
      } else {
        showFlashMessage("❌ Murf generation failed", true);
      }
    })
    .catch((err) => {
      console.error("Error generating Murf voice:", err);
      getMurfBtn.textContent = "Get Murf Voice";
      getMurfBtn.disabled = false;
      showFlashMessage("❌ Murf generation error", true);
    });
};

function showFlashMessage(message, isError = false) {
  flashMessage.textContent = message;
  flashMessage.style.backgroundColor = isError ? "#f44336" : "#4caf50";
  flashMessage.style.display = "block";
  flashMessage.style.position = "fixed";
  flashMessage.style.top = "20px";
  flashMessage.style.right = "20px";
  flashMessage.style.padding = "10px 20px";
  flashMessage.style.borderRadius = "5px";
  flashMessage.style.color = "#fff";
  flashMessage.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";
  setTimeout(() => {
    flashMessage.style.display = "none";
  }, 3000);
}

function visualize(stream) {
  if (!audioCtx) {
    audioCtx = new AudioContext();
  }

  const source = audioCtx.createMediaStreamSource(stream);
  const bufferLength = 2048;
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = bufferLength;
  const dataArray = new Uint8Array(bufferLength);

  source.connect(analyser);

  draw();

  function draw() {
    const WIDTH = canvas.width;
    const HEIGHT = canvas.height;

    requestAnimationFrame(draw);
    analyser.getByteTimeDomainData(dataArray);

    canvasCtx.fillStyle = "rgb(30, 30, 30)";
    canvasCtx.fillRect(0, 0, WIDTH, HEIGHT);
    canvasCtx.lineWidth = 2;
    canvasCtx.strokeStyle = "rgb(0, 255, 0)";
    canvasCtx.beginPath();

    let sliceWidth = (WIDTH * 1.0) / bufferLength;
    let x = 0;

    for (let i = 0; i < bufferLength; i++) {
      let v = dataArray[i] / 128.0;
      let y = (v * HEIGHT) / 2;

      if (i === 0) {
        canvasCtx.moveTo(x, y);
      } else {
        canvasCtx.lineTo(x, y);
      }
      x += sliceWidth;
    }

    canvasCtx.lineTo(canvas.width, canvas.height / 2);
    canvasCtx.stroke();
  }
}

window.onresize = function () {
  canvas.width = mainSection.offsetWidth;
};
window.onresize();

// Voice chat-bot

// ========================
// Get or Create Session ID
// ========================
function getSessionId() {
  const params = new URLSearchParams(window.location.search);
  let sessionId = params.get("session_id");
  if (!sessionId) {
    sessionId = crypto.randomUUID(); // Generate unique session
    params.set("session_id", sessionId);
    window.location.search = params.toString(); // Reload with session_id
  }
  return sessionId;
}

const sessionId = getSessionId();

// ========================
// DOM Elements
// ========================
let mediaRecorder;
let audioChunks = [];
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const responseText = document.getElementById("responseText");
const responseAudio = document.getElementById("responseAudio");
const chatHistoryDiv = document.getElementById("chatHistory");
const sessionIdDisplay = document.getElementById("sessionIdDisplay");
const deleteSessionBtn = document.getElementById("deleteSessionBtn");

// Display current session ID in UI
sessionIdDisplay.textContent = sessionId;

// ========================
// Render Chat History
// ========================
function renderChatHistory(history) {
  chatHistoryDiv.innerHTML = "";
  if (!history || history.length === 0) {
    chatHistoryDiv.innerHTML = `<p class="empty">No messages yet...</p>`;
    return;
  }
  history.forEach((msg) => {
    const div = document.createElement("div");
    div.textContent = `${msg.role}: ${msg.text}`;
    chatHistoryDiv.appendChild(div);
  });
}

// ========================
// Start Recording
// ========================
startBtn.addEventListener("click", async () => {
  audioChunks = [];
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) audioChunks.push(event.data);
  };
  mediaRecorder.start();
  startBtn.disabled = true;
  stopBtn.disabled = false;
  responseText.textContent = "Recording...";
});

// ========================
// Stop Recording and Send to API
// ========================
stopBtn.addEventListener("click", () => {
  mediaRecorder.stop();
  startBtn.disabled = false;
  stopBtn.disabled = true;

  mediaRecorder.onstop = async () => {
    const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
    const formData = new FormData();
    formData.append("file", audioBlob, "recording.webm");

    responseText.textContent = "Processing...";

    try {
      const res = await fetch(`/agent/chat/${sessionId}`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      const data = await res.json();

      // Display transcription
      responseText.textContent = `You said: "${data.transcription}"`;

      // Render chat history
      if (data.history) {
        renderChatHistory(data.history);
      }

      // Play bot response audio
      if (data.audio_url) {
        responseAudio.src = data.audio_url;
        responseAudio.play();
      }
    } catch (err) {
      console.error(err);
      responseText.textContent = "I'm having trouble connecting right now.";
      // Use fallback audio
      responseAudio.src = "/static/tts_fallback.wav";
      responseAudio.play();
    }
  };
});

// ========================
// Delete Session Handler
// ========================
deleteSessionBtn.addEventListener("click", async () => {
  if (!confirm("Are you sure you want to delete this session?")) return;

  try {
    const res = await fetch(`/agent/chat/${sessionId}`, {
      method: "DELETE",
    });

    if (!res.ok) throw new Error(`Server error: ${res.status}`);

    // Clear chat history in UI
    renderChatHistory([]);

    alert("Session deleted successfully!");
  } catch (err) {
    console.error(err);
    alert("Error deleting session.");
  }
});
