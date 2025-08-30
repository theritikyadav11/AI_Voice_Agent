class RecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._chunks = [];
    this._targetSamples = 2048; // send in batches
  }

  process(inputs) {
    const input = inputs[0]; // input from mic
    if (!input || input.length === 0) return true;

    const channelData = input[0]; // mono channel
    if (!channelData) return true;

    const len = channelData.length;
    const int16 = new Int16Array(len);

    for (let i = 0; i < len; i++) {
      let s = channelData[i];
      // clamp to [-1, 1]
      if (s > 1) s = 1;
      else if (s < -1) s = -1;

      // float32 -> int16
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }

    this._chunks.push(int16);

    let total = 0;
    for (const c of this._chunks) total += c.length;

    if (total >= this._targetSamples) {
      const out = new Int16Array(total);
      let offset = 0;
      for (const c of this._chunks) {
        out.set(c, offset);
        offset += c.length;
      }

      this._chunks = [];
      this.port.postMessage(out.buffer, [out.buffer]);
    }

    return true;
  }
}

registerProcessor("recorder-worklet", RecorderProcessor);
