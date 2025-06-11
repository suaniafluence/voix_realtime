import requests


class GPTHandler:
    """Simplified interface to OpenAI chat completions with streaming."""

    def __init__(self, api_key, model="gpt-4o-realtime-preview-2025-06-03"):
        self.api_key = api_key
        self.model = model

    def stream_chat(self, messages, abort_event=None):
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "response_format": {"type": "spoken"}
        }
        with requests.post(url, headers=headers, json=payload, stream=True) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if abort_event and abort_event.is_set():
                    break
                if not line:
                    continue
                if line.startswith(b"data: "):
                    data = line[len(b"data: "):].decode()
                    if data == "[DONE]":
                        break
                    yield data
