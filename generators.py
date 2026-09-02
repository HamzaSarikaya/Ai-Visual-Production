import base64
import io
import json
import os
from abc import ABC, abstractmethod

import requests
from PIL import Image

# Gorsel uretimi bazen 60 saniyeyi asabiliyor; indirme cok daha kisa surer.
GENERATION_TIMEOUT = 180
DOWNLOAD_TIMEOUT = 60

# Govdeyi parca parca okuyoruz ki iptal bayragi arada kontrol edilebilsin.
CHUNK_SIZE = 64 * 1024

# OpenAI dall-e-3'u kaldirdi ("The model 'dall-e-3' does not exist"), yerine
# gpt-image ailesi geldi. Model OPENAI_MODEL ile degistirilebilir.
DEFAULT_OPENAI_MODEL = "gpt-image-1"

# hf-inference saglayicisi FLUX.1-dev'i artik servis etmiyor (HTTP 410).
# Bu model o saglayicida calisiyor ve canli olarak dogrulandi.
DEFAULT_HF_MODEL = "stabilityai/stable-diffusion-3-medium-diffusers"


class GenerationCancelled(Exception):
    """Kullanici uretimi iptal ettiginde atilir; hata kutusu gosterilmez."""


def _iptal_kontrol(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelled("Uretim iptal edildi")


def _boyut_ayikla(size):
    """'1536x1024' -> (1536, 1024). Cozumlenemezse (None, None)."""
    try:
        genislik, yukseklik = str(size).lower().split("x")
        return int(genislik), int(yukseklik)
    except (ValueError, AttributeError):
        return None, None


class ImageGeneratorStrategy(ABC):
    """Gorsel uretim saglayicilarinin ortak arayuzu."""

    @abstractmethod
    def generate(self, prompt: str, size: str = "1024x1024", cancel_event=None) -> Image.Image:
        pass

    def _govde_oku(self, response, cancel_event):
        """Yaniti parca parca okur; arada iptal edilirse indirmeyi yarida birakir."""
        parcalar = []
        for parca in response.iter_content(chunk_size=CHUNK_SIZE):
            _iptal_kontrol(cancel_event)
            if parca:
                parcalar.append(parca)
        return b"".join(parcalar)


class HuggingFaceGenerator(ImageGeneratorStrategy):
    def __init__(self, model_id: str = None):
        self.api_key = os.getenv("HF_API_KEY")
        model_id = model_id or os.getenv("HF_MODEL_ID", DEFAULT_HF_MODEL)
        base_url = os.getenv("HF_API_URL", "https://router.huggingface.co/hf-inference/models")
        self.api_url = f"{base_url.rstrip('/')}/{model_id}"

    def generate(self, prompt: str, size: str = "1024x1024", cancel_event=None) -> Image.Image:
        if not self.api_key:
            raise ValueError(
                "HF_API_KEY tanimli degil. .env dosyasina Hugging Face anahtarinizi ekleyin "
                "veya model olarak OpenAI'i secin."
            )

        _iptal_kontrol(cancel_event)

        govde = {"inputs": prompt}
        genislik, yukseklik = _boyut_ayikla(size)
        if genislik and yukseklik:
            # Saglayici desteklemiyorsa bu alanlar yok sayilir, istek yine calisir.
            govde["parameters"] = {"width": genislik, "height": yukseklik}

        with requests.Session() as oturum:
            try:
                response = oturum.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=govde,
                    timeout=GENERATION_TIMEOUT,
                    stream=True,
                )

                icerik = self._govde_oku(response, cancel_event)

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Hugging Face hatasi ({response.status_code}): "
                        f"{_extract_error(response, icerik)}"
                    )

            except requests.exceptions.RequestException as e:
                raise ConnectionError(f"Hugging Face baglanti hatasi: {e}") from e

        try:
            return Image.open(io.BytesIO(icerik))
        except Exception as e:
            raise RuntimeError(
                f"Gelen veri gorsel olarak acilamadi ({len(icerik)} byte)."
            ) from e


class OpenAIGenerator(ImageGeneratorStrategy):
    def __init__(self, model: str = None):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.quality = os.getenv("OPENAI_IMAGE_QUALITY", "medium")
        self.url = "https://api.openai.com/v1/images/generations"

    def generate(self, prompt: str, size: str = "1024x1024", cancel_event=None) -> Image.Image:
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY tanimli degil. .env.example dosyasini .env olarak "
                "kopyalayip anahtarinizi girin."
            )

        _iptal_kontrol(cancel_event)

        govde = {"model": self.model, "prompt": prompt, "n": 1, "size": size}
        if self.quality:
            govde["quality"] = self.quality

        with requests.Session() as oturum:
            try:
                response = oturum.post(
                    self.url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json=govde,
                    timeout=GENERATION_TIMEOUT,
                )

                if response.status_code != 200:
                    raise RuntimeError(f"OpenAI hatasi: {_extract_error(response)}")

                try:
                    kayit = response.json()["data"][0]
                except (ValueError, KeyError, IndexError) as e:
                    raise RuntimeError("OpenAI cevabi beklenmedik formatta.") from e

                _iptal_kontrol(cancel_event)

                # gpt-image ailesi govdeyi base64 doner; dall-e surumleri URL
                # donuyordu. Ikisi de desteklensin.
                if kayit.get("b64_json"):
                    icerik = base64.b64decode(kayit["b64_json"])
                elif kayit.get("url"):
                    img_response = oturum.get(kayit["url"], timeout=DOWNLOAD_TIMEOUT, stream=True)
                    img_response.raise_for_status()
                    icerik = self._govde_oku(img_response, cancel_event)
                else:
                    raise RuntimeError(
                        "OpenAI cevabinda ne b64_json ne url alani var."
                    )

            except requests.exceptions.RequestException as e:
                raise ConnectionError(f"Uretilen gorsel indirilemedi: {e}") from e

        return Image.open(io.BytesIO(icerik))


def _extract_error(response: requests.Response, icerik: bytes = None) -> str:
    """API hata govdesinden okunabilir bir mesaj cikarir."""
    if icerik is not None:
        metin = icerik.decode("utf-8", errors="replace")
    else:
        metin = response.text or ""
    metin = metin.strip()

    # Kimlik dogrulama hatalarinda JSON yerine HTML giris sayfasi donebiliyor.
    if metin[:9].lower().startswith(("<!doctype", "<html")):
        return (f"HTTP {response.status_code} - sunucu JSON yerine HTML dondu "
                f"(anahtar gecersiz veya eksik olabilir)")

    try:
        payload = json.loads(metin) if icerik is not None else response.json()
    except (ValueError, json.JSONDecodeError):
        return metin[:200] or "Bilinmeyen hata"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("message", "Bilinmeyen hata")
        if isinstance(error, str):
            return error
    return str(payload)[:200]
