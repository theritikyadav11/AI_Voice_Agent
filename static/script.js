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
