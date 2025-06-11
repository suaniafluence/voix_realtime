import { AudioCapture } from './audio-capture.js';

export class InterruptionController {
  constructor({onInterruption}) {
    this.onInterruption = onInterruption;
    this.capture = new AudioCapture({
      onSpeechStart: () => this.handleSpeechStart(),
      onSpeechStop: () => {},
      onAudioFrame: (pcm) => this.handleFrame(pcm)
    });
    this.isActive = false;
    this.lastFrame = Date.now();
  }

  async start() {
    await this.capture.start();
    this.isActive = true;
  }

  stop() {
    this.capture.stop();
    this.isActive = false;
  }

  handleSpeechStart() {
    if (this.onInterruption) this.onInterruption();
  }

  handleFrame() {
    this.lastFrame = Date.now();
  }
}
