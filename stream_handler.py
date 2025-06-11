import json
import threading
import base64
import websocket


class OpenAIStreamHandler:
    """Handle real-time audio streaming with OpenAI via WebSocket."""

    def __init__(self, api_key, model, instructions, event_callback=None):
        self.api_key = api_key
        self.model = model
        self.instructions = instructions
        self.event_callback = event_callback
        self.ws = None
        self.connected = threading.Event()
        self.stopped = threading.Event()

    def _emit(self, event, data):
        if self.event_callback:
            self.event_callback(event, data)

    def on_open(self, ws):
        self.connected.set()
        self._emit('open', None)
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": "alloy",
                "instructions": self.instructions,
                "turn_detection": {"type": "server_vad", "threshold": 0.5},
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"}
            }
        }
        ws.send(json.dumps(config))

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
        except Exception:
            return
        self._emit('message', data)

    def on_error(self, ws, error):
        self._emit('error', str(error))

    def on_close(self, ws, status, msg):
        self.connected.clear()
        self._emit('close', status)

    def start(self):
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = [
            f"Authorization: Bearer {self.api_key}",
            "OpenAI-Beta: realtime=v1"
        ]
        self.ws = websocket.WebSocketApp(
            url,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        thread.start()
        return self.connected.wait(timeout=5)

    def send_audio(self, pcm16_bytes):
        if not self.connected.is_set():
            return False
        audio = base64.b64encode(pcm16_bytes).decode()
        msg = {"type": "input_audio_buffer.append", "audio": audio}
        self.ws.send(json.dumps(msg))
        return True

    def stop_audio(self):
        if self.connected.is_set():
            self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

    def close(self):
        if self.ws:
            self.ws.close()
            self.ws = None
        self.stopped.set()
