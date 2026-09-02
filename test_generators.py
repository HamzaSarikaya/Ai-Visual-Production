"""generators.py için birim testleri.

Ağa çıkmaz, arayüz açmaz: requests.Session katmanı sahte nesnelerle değiştirilir.
Çalıştırmak için:  python -m unittest -v
"""

import base64
import io
import json
import os
import threading
import unittest
from unittest import mock

import requests
from PIL import Image

import generators
from generators import (
    GenerationCancelled,
    HuggingFaceGenerator,
    OpenAIGenerator,
    _boyut_ayikla,
    _extract_error,
)


def png_bytes(size=(8, 8), color=(255, 0, 0)):
    """Testlerde API'den dönmüş gibi kullanılacak geçerli bir PNG üretir."""
    tampon = io.BytesIO()
    Image.new("RGB", size, color).save(tampon, format="PNG")
    return tampon.getvalue()


class SahteCevap:
    """requests.Response yerine geçen küçük sahte nesne."""

    def __init__(self, status_code=200, json_data=None, content=None, text=None):
        self.status_code = status_code
        self._json = json_data

        if content is None:
            if json_data is not None:
                content = json.dumps(json_data).encode("utf-8")
            elif text is not None:
                content = text.encode("utf-8")
            else:
                content = b""
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", errors="replace")

    def json(self):
        if self._json is None:
            raise ValueError("govde JSON degil")
        return self._json

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


class SahteOturum:
    """requests.Session yerine geçer; çağrıları kaydeder."""

    def __init__(self, post_cevap=None, get_cevap=None, post_hata=None, get_hata=None):
        self.post_cevap = post_cevap
        self.get_cevap = get_cevap
        self.post_hata = post_hata
        self.get_hata = get_hata
        self.post_cagri = None
        self.get_cagri = None
        self.kapatildi = False

    def post(self, *args, **kwargs):
        self.post_cagri = (args, kwargs)
        if self.post_hata:
            raise self.post_hata
        return self.post_cevap

    def get(self, *args, **kwargs):
        self.get_cagri = (args, kwargs)
        if self.get_hata:
            raise self.get_hata
        return self.get_cevap

    def close(self):
        self.kapatildi = True

    # requests.Session bir context manager; kod "with" ile kullanıyor.
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def oturum_yamasi(oturum):
    """generators içindeki requests.Session çağrısını sahte oturumla değiştirir."""
    return mock.patch.object(generators.requests, "Session", return_value=oturum)


def anahtarsiz_ortam():
    return mock.patch.dict(os.environ, {}, clear=True)


class BoyutAyiklaTest(unittest.TestCase):
    def test_gecerli_boyut(self):
        self.assertEqual(_boyut_ayikla("1792x1024"), (1792, 1024))

    def test_buyuk_harf(self):
        self.assertEqual(_boyut_ayikla("1024X1792"), (1024, 1792))

    def test_bozuk_boyut(self):
        self.assertEqual(_boyut_ayikla("kare"), (None, None))
        self.assertEqual(_boyut_ayikla(None), (None, None))


class OpenAIGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-anahtar"})
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def _b64_cevap(size=(8, 8)):
        """gpt-image ailesinin döndürdüğü biçim: gövde base64 olarak gelir."""
        b64 = base64.b64encode(png_bytes(size)).decode("ascii")
        return SahteCevap(200, {"data": [{"b64_json": b64}]})

    @staticmethod
    def _url_cevap():
        """Eski dall-e sürümlerinin döndürdüğü biçim: indirilecek bir URL."""
        return SahteCevap(200, {"data": [{"url": "https://ornek/g.png"}]})

    def _oturum(self, **kwargs):
        kwargs.setdefault("post_cevap", self._b64_cevap())
        kwargs.setdefault("get_cevap", SahteCevap(200, content=png_bytes()))
        return SahteOturum(**kwargs)

    def test_anahtar_yoksa_deger_hatasi(self):
        with anahtarsiz_ortam():
            uretici = OpenAIGenerator()
        with self.assertRaises(ValueError) as ctx:
            uretici.generate("kedi")
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    def test_base64_cevaptan_gorsel_olusturuluyor(self):
        oturum = self._oturum(post_cevap=self._b64_cevap((16, 16)))
        with oturum_yamasi(oturum):
            gorsel = OpenAIGenerator().generate("kedi", "1024x1024")
        self.assertIsInstance(gorsel, Image.Image)
        self.assertEqual(gorsel.size, (16, 16))
        # base64 geldiğinde ayrıca indirme yapılmamalı
        self.assertIsNone(oturum.get_cagri)

    def test_url_cevabi_da_destekleniyor(self):
        # Eski dall-e sürümleri URL dönüyordu; geriye dönük uyumluluk.
        oturum = self._oturum(post_cevap=self._url_cevap(),
                              get_cevap=SahteCevap(200, content=png_bytes((24, 24))))
        with oturum_yamasi(oturum):
            gorsel = OpenAIGenerator().generate("kedi")
        self.assertEqual(gorsel.size, (24, 24))
        self.assertIsNotNone(oturum.get_cagri)

    def test_ne_b64_ne_url_varsa_anlasilir_hata(self):
        oturum = self._oturum(post_cevap=SahteCevap(200, {"data": [{"beklenmeyen": 1}]}))
        with oturum_yamasi(oturum):
            with self.assertRaises(RuntimeError) as ctx:
                OpenAIGenerator().generate("kedi")
        self.assertIn("b64_json", str(ctx.exception))

    def test_istek_govdesi_ve_zaman_asimi_dogru(self):
        oturum = self._oturum()
        with oturum_yamasi(oturum):
            OpenAIGenerator().generate("kedi", "1536x1024")

        govde = oturum.post_cagri[1]["json"]
        # dall-e-3 kaldirildi; varsayilan artik gpt-image ailesinden.
        self.assertEqual(govde["model"], generators.DEFAULT_OPENAI_MODEL)
        self.assertNotEqual(govde["model"], "dall-e-3")
        self.assertEqual(govde["prompt"], "kedi")
        self.assertEqual(govde["size"], "1536x1024")
        self.assertEqual(govde["n"], 1)

        # Zaman aşımı olmadan uygulama sonsuza kadar donabiliyordu.
        self.assertEqual(oturum.post_cagri[1]["timeout"], generators.GENERATION_TIMEOUT)

    def test_model_ve_kalite_ortamdan_okunuyor(self):
        ortam = {"OPENAI_API_KEY": "x", "OPENAI_MODEL": "gpt-image-1-mini",
                 "OPENAI_IMAGE_QUALITY": "low"}
        oturum = self._oturum()
        with mock.patch.dict(os.environ, ortam, clear=True), oturum_yamasi(oturum):
            OpenAIGenerator().generate("kedi")

        govde = oturum.post_cagri[1]["json"]
        self.assertEqual(govde["model"], "gpt-image-1-mini")
        self.assertEqual(govde["quality"], "low")

    def test_oturum_her_durumda_kapatiliyor(self):
        oturum = self._oturum()
        with oturum_yamasi(oturum):
            OpenAIGenerator().generate("kedi")
        self.assertTrue(oturum.kapatildi)

    def test_hata_durumunda_da_oturum_kapatiliyor(self):
        oturum = self._oturum(post_cevap=SahteCevap(400, {"error": {"message": "olmadi"}}))
        with oturum_yamasi(oturum):
            with self.assertRaises(RuntimeError):
                OpenAIGenerator().generate("kedi")
        self.assertTrue(oturum.kapatildi)

    def test_api_hatasi_mesaji_aktarilir(self):
        oturum = self._oturum(post_cevap=SahteCevap(400, {"error": {"message": "içerik politikası ihlali"}}))
        with oturum_yamasi(oturum):
            with self.assertRaises(RuntimeError) as ctx:
                OpenAIGenerator().generate("kedi")
        self.assertIn("içerik politikası ihlali", str(ctx.exception))

    def test_beklenmedik_cevap_formati(self):
        oturum = self._oturum(post_cevap=SahteCevap(200, {"beklenmeyen": "yapı"}))
        with oturum_yamasi(oturum):
            with self.assertRaises(RuntimeError):
                OpenAIGenerator().generate("kedi")

    def test_baglanti_hatasi_sarmalanir(self):
        oturum = self._oturum(post_hata=requests.exceptions.ConnectTimeout("zaman aşımı"))
        with oturum_yamasi(oturum):
            with self.assertRaises(ConnectionError):
                OpenAIGenerator().generate("kedi")

    def test_gorsel_indirilemezse_baglanti_hatasi(self):
        oturum = self._oturum(post_cevap=self._url_cevap(), get_cevap=SahteCevap(500))
        with oturum_yamasi(oturum):
            with self.assertRaises(ConnectionError):
                OpenAIGenerator().generate("kedi")

    def test_bastan_iptal_edilmisse_istek_gonderilmiyor(self):
        bayrak = threading.Event()
        bayrak.set()
        oturum = self._oturum()
        with oturum_yamasi(oturum):
            with self.assertRaises(GenerationCancelled):
                OpenAIGenerator().generate("kedi", "1024x1024", bayrak)
        self.assertIsNone(oturum.post_cagri)

    def test_indirme_sirasinda_iptal(self):
        bayrak = threading.Event()

        class IptalTetikleyen(SahteCevap):
            def iter_content(self, chunk_size=1):
                yield self.content[:10]
                bayrak.set()          # indirme sürerken kullanıcı iptal etti
                yield self.content[10:]

        oturum = self._oturum(post_cevap=self._url_cevap(),
                              get_cevap=IptalTetikleyen(200, content=png_bytes((64, 64))))
        with oturum_yamasi(oturum):
            with self.assertRaises(GenerationCancelled):
                OpenAIGenerator().generate("kedi", "1024x1024", bayrak)

    def test_indirme_stream_modunda_yapiliyor(self):
        # Parca parca okuyabilmek icin stream=True sart; olmazsa iptal edilemez.
        oturum = self._oturum(post_cevap=self._url_cevap())
        with oturum_yamasi(oturum):
            OpenAIGenerator().generate("kedi")
        self.assertTrue(oturum.get_cagri[1]["stream"])
        self.assertEqual(oturum.get_cagri[1]["timeout"], generators.DOWNLOAD_TIMEOUT)


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
        oturum = SahteOturum(post_cevap=SahteCevap(200, content=png_bytes((32, 32))))
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             oturum_yamasi(oturum):
            gorsel = HuggingFaceGenerator().generate("kedi")
        self.assertEqual(gorsel.size, (32, 32))

    def test_boyut_parametre_olarak_gonderiliyor(self):
        oturum = SahteOturum(post_cevap=SahteCevap(200, content=png_bytes()))
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             oturum_yamasi(oturum):
            HuggingFaceGenerator().generate("kedi", "1792x1024")

        govde = oturum.post_cagri[1]["json"]
        self.assertEqual(govde["inputs"], "kedi")
        self.assertEqual(govde["parameters"], {"width": 1792, "height": 1024})

    def test_bozuk_boyutta_parametre_gonderilmiyor(self):
        oturum = SahteOturum(post_cevap=SahteCevap(200, content=png_bytes()))
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             oturum_yamasi(oturum):
            HuggingFaceGenerator().generate("kedi", "bozuk")
        self.assertNotIn("parameters", oturum.post_cagri[1]["json"])

    def test_hata_kodunda_calisma_zamani_hatasi(self):
        oturum = SahteOturum(post_cevap=SahteCevap(503, json_data={"error": "model yükleniyor"}))
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             oturum_yamasi(oturum):
            with self.assertRaises(RuntimeError) as ctx:
                HuggingFaceGenerator().generate("kedi")
        self.assertIn("model yükleniyor", str(ctx.exception))

    def test_html_hata_govdesi_anlasilir_mesaja_cevriliyor(self):
        oturum = SahteOturum(post_cevap=SahteCevap(401, text="<!DOCTYPE html><html>giriş</html>"))
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             oturum_yamasi(oturum):
            with self.assertRaises(RuntimeError) as ctx:
                HuggingFaceGenerator().generate("kedi")
        self.assertIn("HTML", str(ctx.exception))

    def test_bozuk_govde_anlasilir_hata(self):
        oturum = SahteOturum(post_cevap=SahteCevap(200, content=b"bu bir gorsel degil"))
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             oturum_yamasi(oturum):
            with self.assertRaises(RuntimeError) as ctx:
                HuggingFaceGenerator().generate("kedi")
        self.assertIn("byte", str(ctx.exception))

    def test_bastan_iptal_edilmisse_istek_gonderilmiyor(self):
        bayrak = threading.Event()
        bayrak.set()
        oturum = SahteOturum(post_cevap=SahteCevap(200, content=png_bytes()))
        with mock.patch.dict(os.environ, {"HF_API_KEY": "test"}, clear=True), \
             oturum_yamasi(oturum):
            with self.assertRaises(GenerationCancelled):
                HuggingFaceGenerator().generate("kedi", "1024x1024", bayrak)
        self.assertIsNone(oturum.post_cagri)


class ExtractErrorTest(unittest.TestCase):
    def test_ic_ice_hata_sozlugu(self):
        self.assertEqual(_extract_error(SahteCevap(400, {"error": {"message": "geçersiz istek"}})),
                         "geçersiz istek")

    def test_duz_metin_hata(self):
        self.assertEqual(_extract_error(SahteCevap(503, {"error": "meşgul"})), "meşgul")

    def test_html_cevabi_anlasilir_mesaja_cevrilir(self):
        mesaj = _extract_error(SahteCevap(401, text="<!DOCTYPE html><html><body>giriş</body></html>"))
        self.assertIn("401", mesaj)
        self.assertIn("HTML", mesaj)

    def test_json_olmayan_govde_kirpilir(self):
        self.assertEqual(len(_extract_error(SahteCevap(500, text="x" * 500))), 200)

    def test_bos_govde(self):
        self.assertEqual(_extract_error(SahteCevap(500, text="")), "Bilinmeyen hata")

    def test_bayt_govdesinden_okuma(self):
        cevap = SahteCevap(500, text="")
        icerik = json.dumps({"error": "bayttan geldi"}).encode("utf-8")
        self.assertEqual(_extract_error(cevap, icerik), "bayttan geldi")


if __name__ == "__main__":
    unittest.main()
