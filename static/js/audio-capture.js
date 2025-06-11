export class AudioCapture {
  constructor({onAudioFrame, onSpeechStart, onSpeechStop, sampleRate=24000, bufferSize=4096, threshold=0.01, silenceFrames=20}) {
    this.onAudioFrame = onAudioFrame;
    this.onSpeechStart = onSpeechStart;
    this.onSpeechStop = onSpeechStop;
    this.sampleRate = sampleRate;
    this.bufferSize = bufferSize;
    this.threshold = threshold;
    this.silenceFrames = silenceFrames;
    this.audioContext = null;
    this.stream = null;
    this.processor = null;
    this.speaking = false;
    this.silentCount = 0;
  }

  async start() {
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)({sampleRate: this.sampleRate});
    this.stream = await navigator.mediaDevices.getUserMedia({audio: {sampleRate: this.sampleRate, channelCount: 1}});
    const source = this.audioContext.createMediaStreamSource(this.stream);
    this.processor = this.audioContext.createScriptProcessor(this.bufferSize, 1, 1);
    source.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
    this.processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(input.length);
      let rms = 0;
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcm[i] = s * 0x7FFF;
        rms += s*s;
      }
      rms = Math.sqrt(rms / input.length);
      if (this.onAudioFrame) this.onAudioFrame(pcm);
      if (rms > this.threshold) {
        this.silentCount = 0;
        if (!this.speaking) {
          this.speaking = true;
          if (this.onSpeechStart) this.onSpeechStart();
        }
      } else {
        this.silentCount++;
        if (this.speaking && this.silentCount > this.silenceFrames) {
          this.speaking = false;
          if (this.onSpeechStop) this.onSpeechStop();
        }
      }
    };
  }

  stop() {
    if (this.processor) {
      this.processor.disconnect();
      this.processor.onaudioprocess = null;
      this.processor = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
  }
}
