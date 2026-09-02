"""generators.py için birim testleri.

Ağa çıkmaz, arayüz açmaz: requests katmanı sahte nesnelerle değiştirilir.
Çalıştırmak için:  python -m unittest -v
"""

import io
import os
import unittest
from unittest import mock

import requests
from PIL import Image

import generators
from generators import HuggingFaceGenerator, OpenAIGenerator, _extract_error


def png_bytes(size=(8, 8), color=(255, 0, 0)):
    """Testlerde API'den dönmüş gibi kullanılacak geçerli bir PNG üretir."""
    tampon = io.BytesIO()
    Image.new("RGB", size, color).save(tampon, format="PNG")
    return tampon.getvalue()


class SahteCevap:
    """requests.Response yerine geçen küçük sahte nesne."""

    def __init__(self, status_code=200, json_data=None, content=b"", text=""):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("govde JSON degil")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


def anahtarsiz_ortam():
    """API anahtarı hiç tanımlı değilmiş gibi davranan ortam."""
    return mock.patch.dict(os.environ, {}, clear=True)


class OpenAIGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-anahtar"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_anahtar_yoksa_deger_hatasi(self):
        with anahtarsiz_ortam():
            uretici = OpenAIGenerator()
        with self.assertRaises(ValueError) as ctx:
            uretici.generate("kedi")
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    def test_basarili_uretim_gorsel_dondurur(self):
        post_cevap = SahteCevap(200, {"data": [{"url": "https://ornek/gorsel.png"}]})
        get_cevap = SahteCevap(200, content=png_bytes((16, 16)))

        with mock.patch.object(generators.requests, "post", return_value=post_cevap), \
             mock.patch.object(generators.requests, "get", return_value=get_cevap):
            gorsel = OpenAIGenerator().generate("kedi", "1024x1024")

        self.assertIsInstance(gorsel, Image.Image)
        self.assertEqual(gorsel.size, (16, 16))

    def test_istek_govdesi_ve_zaman_asimi_dogru(self):
        post_cevap = SahteCevap(200, {"data": [{"url": "https://ornek/gorsel.png"}]})
        get_cevap = SahteCevap(200, content=png_bytes())

        with mock.patch.object(generators.requests, "post", return_value=post_cevap) as post, \
             mock.patch.object(generators.requests, "get", return_value=get_cevap) as get:
            OpenAIGenerator().generate("kedi", "1792x1024")

        govde = post.call_args.kwargs["json"]
        self.assertEqual(govde["model"], "dall-e-3")
        self.assertEqual(govde["prompt"], "kedi")
        self.assertEqual(govde["size"], "1792x1024")
        self.assertEqual(govde["n"], 1)

        # Zaman aşımı olmadan uygulama sonsuza kadar donabiliyordu.
        self.assertEqual(post.call_args.kwargs["timeout"], generators.GENERATION_TIMEOUT)
        self.assertEqual(get.call_args.kwargs["timeout"], generators.DOWNLOAD_TIMEOUT)

    def test_api_hatasi_mesaji_aktarilir(self):
        cevap = SahteCevap(400, {"error": {"message": "içerik politikası ihlali"}})
        with mock.patch.object(generators.requests, "post", return_value=cevap):
            with self.assertRaises(RuntimeError) as ctx:
                OpenAIGenerator().generate("kedi")
        self.assertIn("içerik politikası ihlali", str(ctx.exception))

    def test_beklenmedik_cevap_formati(self):
        cevap = SahteCevap(200, {"beklenmeyen": "yapı"})
        with mock.patch.object(generators.requests, "post", return_value=cevap):
            with self.assertRaises(RuntimeError):
                OpenAIGenerator().generate("kedi")

    def test_baglanti_hatasi_sarmalanir(self):
        with mock.patch.object(generators.requests, "post",
                               side_effect=requests.exceptions.ConnectTimeout("zaman aşımı")):
            with self.assertRaises(ConnectionError):
                OpenAIGenerator().generate("kedi")

    def test_gorsel_indirilemezse_baglanti_hatasi(self):
        post_cevap = SahteCevap(200, {"data": [{"url": "https://ornek/gorsel.png"}]})
        with mock.patch.object(generators.requests, "post", return_value=post_cevap), \
             mock.patch.object(generators.requests, "get", return_value=SahteCevap(500)):
            with self.assertRaises(ConnectionError):
                OpenAIGenerator().generate("kedi")


class HuggingFaceGeneratorTest(unittest.TestCase):
    def test_anahtar_yoksa_deger_hatasi(self):
        with anahtarsiz_ortam():
            uretici = HuggingFaceGenerator()
            with self.assertRaises(ValueError) as ctx:
                uretici.generate("kedi")
        self.assertIn("HF_API_KEY", str(ctx.exception))

    def test_varsayilan_adres_router(self):
        # api-inference.huggingface.co kapandı; eski adrese geri dönülmesin diye.
        with anahtarsiz_ortam():
            uretici = HuggingFaceGenerator()
        self.assertTrue(uretici.api_url.startswith("https://router.huggingface.co/"))
        self.assertNotIn("api-inference.huggingface.co", uretici.api_url)

    def test_model_ve_adres_ortamdan_okunur(self):
        ortam = {"HF_API_KEY": "x", "HF_API_URL": "https://ornek/uc/", "HF_MODEL_ID": "bir/model"}
        with mock.patch.dict(os.environ, ortam, clear=True):
            uretici = HuggingFaceGenerator()
        self.assertEqual(uretici.api_url, "https://ornek/uc/bir/model")

    def test_basarili_uretim_gorsel_dondurur(self):
        cevap = SahteCevap(200, content=png_bytes((32, 32)))
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             mock.patch.object(generators.requests, "post", return_value=cevap):
            gorsel = HuggingFaceGenerator().generate("kedi")
        self.assertEqual(gorsel.size, (32, 32))

    def test_hata_kodunda_calisma_zamani_hatasi(self):
        cevap = SahteCevap(503, json_data={"error": "model yükleniyor"})
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             mock.patch.object(generators.requests, "post", return_value=cevap):
            with self.assertRaises(RuntimeError) as ctx:
                HuggingFaceGenerator().generate("kedi")
        self.assertIn("model yükleniyor", str(ctx.exception))

    def test_bozuk_govde_anlasilir_hata(self):
        cevap = SahteCevap(200, content=b"bu bir gorsel degil")
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             mock.patch.object(generators.requests, "post", return_value=cevap):
            with self.assertRaises(RuntimeError) as ctx:
                HuggingFaceGenerator().generate("kedi")
        self.assertIn("byte", str(ctx.exception))


class ExtractErrorTest(unittest.TestCase):
    def test_ic_ice_hata_sozlugu(self):
        cevap = SahteCevap(400, {"error": {"message": "geçersiz istek"}})
        self.assertEqual(_extract_error(cevap), "geçersiz istek")

    def test_duz_metin_hata(self):
        cevap = SahteCevap(503, {"error": "meşgul"})
        self.assertEqual(_extract_error(cevap), "meşgul")

    def test_html_cevabi_anlasilir_mesaja_cevrilir(self):
        cevap = SahteCevap(401, text="<!DOCTYPE html><html><body>giriş</body></html>")
        mesaj = _extract_error(cevap)
        self.assertIn("401", mesaj)
        self.assertIn("HTML", mesaj)

    def test_json_olmayan_govde_kirpilir(self):
        cevap = SahteCevap(500, text="x" * 500)
        self.assertEqual(len(_extract_error(cevap)), 200)

    def test_bos_govde(self):
        self.assertEqual(_extract_error(SahteCevap(500, text="")), "Bilinmeyen hata")


if __name__ == "__main__":
    unittest.main()
