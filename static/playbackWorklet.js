// playbackWorklet.js
class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.audioBuffer = [];
    this.port.onmessage = (event) => {
      // Add incoming audio data to the buffer
      this.audioBuffer.push(event.data);
    };
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0];
    const outputChannel = output[0];

    // Check if there is audio data to play
    if (this.audioBuffer.length > 0) {
      const inputChannel = this.audioBuffer.shift();

      // Write a fixed number of samples to the output
      const samplesToWrite = Math.min(
        outputChannel.length,
        inputChannel.length
      );
      for (let i = 0; i < samplesToWrite; i++) {
        outputChannel[i] = inputChannel[i];
      }

      // If the input channel has remaining data, put it back in the buffer
      if (inputChannel.length > samplesToWrite) {
        this.audioBuffer.unshift(inputChannel.subarray(samplesToWrite));
      }
    } else {
      // If there's no data, fill the output with silence
      for (let i = 0; i < outputChannel.length; i++) {
        outputChannel[i] = 0;
      }
    }

    // Return true to keep the processor active
    return true;
  }
}

registerProcessor("playback-worklet-processor", PlaybackProcessor);
