import io
import json
import os
from abc import ABC, abstractmethod

import requests
from PIL import Image

# Gorsel uretimi bazen 60 saniyeyi asabiliyor; indirme cok daha kisa surer.
GENERATION_TIMEOUT = 180
DOWNLOAD_TIMEOUT = 60


class ImageGeneratorStrategy(ABC):
    """Gorsel uretim saglayicilarinin ortak arayuzu."""

    @abstractmethod
    def generate(self, prompt: str, size: str = "1024x1024") -> Image.Image:
        pass


class HuggingFaceGenerator(ImageGeneratorStrategy):
    def __init__(self, model_id: str = None):
        self.api_key = os.getenv("HF_API_KEY")
        model_id = model_id or os.getenv("HF_MODEL_ID", "black-forest-labs/FLUX.1-dev")
        base_url = os.getenv("HF_API_URL", "https://api-inference.huggingface.co/models")
        self.api_url = f"{base_url.rstrip('/')}/{model_id}"

    def generate(self, prompt: str, size: str = "1024x1024") -> Image.Image:
        # size parametresi arayuz butunlugu icin var; bu API cozunurluk kabul etmiyor.
        if not self.api_key:
            raise ValueError(
                "HF_API_KEY tanimli degil. .env dosyasina Hugging Face anahtarinizi ekleyin "
                "veya model olarak OpenAI DALL-E 3'u secin."
            )

        try:
            response = requests.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"inputs": prompt},
                timeout=GENERATION_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Hugging Face baglanti hatasi: {e}") from e

        if response.status_code != 200:
            raise RuntimeError(
                f"Hugging Face hatasi ({response.status_code}): {_extract_error(response)}"
            )

        try:
            return Image.open(io.BytesIO(response.content))
        except Exception as e:
            raise RuntimeError(
                f"Gelen veri gorsel olarak acilamadi ({len(response.content)} byte)."
            ) from e


class OpenAIGenerator(ImageGeneratorStrategy):
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.url = "https://api.openai.com/v1/images/generations"

    def generate(self, prompt: str, size: str = "1024x1024") -> Image.Image:
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY tanimli degil. .env.example dosyasini .env olarak "
                "kopyalayip anahtarinizi girin."
            )

        try:
            response = requests.post(
                self.url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={"model": "dall-e-3", "prompt": prompt, "n": 1, "size": size},
                timeout=GENERATION_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"OpenAI baglanti hatasi: {e}") from e

        if response.status_code != 200:
            raise RuntimeError(f"OpenAI hatasi: {_extract_error(response)}")

        try:
            image_url = response.json()["data"][0]["url"]
        except (ValueError, KeyError, IndexError) as e:
            raise RuntimeError("OpenAI cevabi beklenmedik formatta.") from e

        try:
            img_response = requests.get(image_url, timeout=DOWNLOAD_TIMEOUT)
            img_response.raise_for_status()
            return Image.open(io.BytesIO(img_response.content))
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Uretilen gorsel indirilemedi: {e}") from e


def _extract_error(response: requests.Response) -> str:
    """API hata govdesinden okunabilir bir mesaj cikarir."""
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return response.text[:200] or "Bilinmeyen hata"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("message", "Bilinmeyen hata")
        if isinstance(error, str):
            return error
    return str(payload)[:200]
