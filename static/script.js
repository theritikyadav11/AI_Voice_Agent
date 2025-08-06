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

// Echo Bot logic

const record = document.querySelector(".record");
const stop = document.querySelector(".stop");
const soundClips = document.querySelector(".sound-clips");
const canvas = document.querySelector(".visualizer");
const mainSection = document.querySelector(".main-controls");
const flashMessage = document.getElementById("flash-message");

stop.disabled = true;

let audioCtx;
const canvasCtx = canvas.getContext("2d");

if (navigator.mediaDevices.getUserMedia) {
  const constraints = { audio: true };
  let chunks = [];

  let onSuccess = function (stream) {
    const mediaRecorder = new MediaRecorder(stream);
    visualize(stream);

    record.onclick = function () {
      mediaRecorder.start();
      record.style.background = "red";
      stop.disabled = false;
      record.disabled = true;
    };

    stop.onclick = function () {
      mediaRecorder.stop();
      record.style.background = "";
      stop.disabled = true;
      record.disabled = false;
    };

    mediaRecorder.onstop = function () {
      const clipName = prompt(
        "Enter a name for your sound clip?",
        "My unnamed clip"
      );

      const clipContainer = document.createElement("article");
      const clipLabel = document.createElement("p");
      const audio = document.createElement("audio");
      const deleteButton = document.createElement("button");
      const uploadButton = document.createElement("button");

      clipContainer.classList.add("clip");
      audio.setAttribute("controls", "");
      deleteButton.textContent = "Delete";
      uploadButton.textContent = "Upload";
      deleteButton.className = "delete";
      uploadButton.className = "upload";

      clipLabel.textContent = clipName || "My unnamed clip";

      clipContainer.appendChild(audio);
      clipContainer.appendChild(clipLabel);
      clipContainer.appendChild(deleteButton);
      clipContainer.appendChild(uploadButton);
      soundClips.appendChild(clipContainer);

      audio.controls = true;
      const blob = new Blob(chunks, { type: mediaRecorder.mimeType });
      chunks = [];
      const audioURL = window.URL.createObjectURL(blob);
      audio.src = audioURL;

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

        fetch("http://127.0.0.1:8000/upload-audio/", {
          method: "POST",
          body: formData,
        })
          .then((response) => response.json())
          .then((data) => {
            const fileSizeKB = (data.size / 1024).toFixed(2);
            showFlashMessage(
              `${data.filename} (${fileSizeKB} KB) uploaded successfully`
            );
            console.log("Upload successful", data);
          })
          .catch((error) => {
            showFlashMessage("Upload failed.", true);
            console.error("Upload error:", error);
          });
      };
    };

    mediaRecorder.ondataavailable = function (e) {
      chunks.push(e.data);
    };
  };

  let onError = function (err) {
    console.log("The following error occurred: " + err);
  };

  navigator.mediaDevices.getUserMedia(constraints).then(onSuccess, onError);
} else {
  console.log("MediaDevices.getUserMedia() not supported on your browser!");
}

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

    canvasCtx.fillStyle = "rgb(200, 200, 200)";
    canvasCtx.fillRect(0, 0, WIDTH, HEIGHT);
    canvasCtx.lineWidth = 2;
    canvasCtx.strokeStyle = "rgb(0, 0, 0)";
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
