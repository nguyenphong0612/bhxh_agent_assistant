"""
Model provider — hỗ trợ chuyển đổi giữa Ollama (local), Groq và Gemini (online).
Tất cả provider đều có method generate(prompt) → str.
"""
import os
import requests


class OllamaModel:
    """Gọi Ollama local API."""

    def __init__(self, url, model):
        self.url = url
        self.model = model

    def generate(self, prompt):
        response = requests.post(
            self.url,
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=300,
        )
        data = response.json()
        if "response" not in data:
            raise ValueError(f"Ollama error: {data}")
        return data["response"]


class GroqModel:
    """Gọi Groq cloud API (OpenAI-compatible)."""

    def __init__(self, api_key, model="llama-3.1-8b-instant"):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def generate(self, prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        response = requests.post(
            self.url, headers=headers, json=payload, timeout=120
        )
        data = response.json()
        if "choices" not in data:
            raise ValueError(f"Groq error: {data}")
        return data["choices"][0]["message"]["content"]


class GeminiModel:
    """Gọi Google Gemini API."""

    def __init__(self, api_key, model="gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def generate(self, prompt):
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        }
        response = requests.post(
            f"{self.url}?key={self.api_key}",
            headers=headers,
            json=payload,
            timeout=120,
        )
        data = response.json()
        if "candidates" not in data:
            raise ValueError(f"Gemini error: {data}")
        return data["candidates"][0]["content"]["parts"][0]["text"]


def create_model(provider=None):
    """Factory: tạo model theo LLM_PROVIDER trong setting.
    Returns model instance với method .generate(prompt) → str.
    """
    from Config.setting import (
        LLM_PROVIDER, OLLAMA_URL, OLLAMA_MODEL,
        GROQ_API_KEY, GROQ_MODEL,
        GEMINI_API_KEY, GEMINI_MODEL,
    )

    provider = provider or LLM_PROVIDER

    if provider == "gemini":
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY chưa được set. "
                "Chạy: setx GEMINI_API_KEY \"AIza...\" rồi khởi động lại terminal."
            )
        return GeminiModel(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)

    elif provider == "groq":
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY chưa được set. "
                "Chạy: setx GROQ_API_KEY \"gsk_xxxxx\" rồi khởi động lại terminal."
            )
        return GroqModel(api_key=GROQ_API_KEY, model=GROQ_MODEL)

    elif provider == "ollama":
        return OllamaModel(url=OLLAMA_URL, model=OLLAMA_MODEL)

    else:
        raise ValueError(f"Provider không hỗ trợ: {provider}. Chọn 'gemini', 'groq' hoặc 'ollama'.")
