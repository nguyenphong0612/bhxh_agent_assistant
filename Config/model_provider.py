"""
Model provider — Ollama local API.
Đơn giản, không dependency, không online/network issues.
"""
import requests


class OllamaModel:
    """Gọi Ollama local API."""

    def __init__(self, url, model):
        self.url = url
        self.model = model

    def generate(self, prompt):
        """Gọi Ollama để sinh văn bản.
        
        Args:
            prompt: string cần sinh output
            
        Returns:
            string: output từ model
        """
        try:
            response = requests.post(
                self.url,
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=600,  # 10 phút timeout cho document lớn
            )
            response.raise_for_status()
            data = response.json()
            if "response" not in data:
                raise ValueError(f"Ollama error: {data}")
            return data["response"]
        except requests.exceptions.ConnectionError:
            raise ValueError(
                f"Không kết nối được tới Ollama ({self.url}). "
                "Kiểm tra: ollama serve đã chạy chưa? "
                f"Model '{self.model}' đã pull chưa?"
            )
        except Exception as e:
            raise ValueError(f"Ollama error: {str(e)}")


def create_model(provider=None):
    """Factory: tạo Ollama model instance.
    
    Returns:
        OllamaModel: instance với method .generate(prompt) → str
    """
    from Config.setting import OLLAMA_URL, OLLAMA_MODEL
    
    return OllamaModel(url=OLLAMA_URL, model=OLLAMA_MODEL)
