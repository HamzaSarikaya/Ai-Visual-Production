"""main.py arayüz davranışları için testler.

Ağa çıkmaz: üretici katmanı sahte nesnelerle değiştirilir. Her test kendi
geçici kayıt klasörünü kullanır, projedeki gerçek klasöre dokunmaz.

Ekran (display) gerektirir; başsız bir ortamda testler atlanır.

Çalıştırmak için:  python -m unittest -v
"""

import glob
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

from PIL import Image


def ekran_var_mi():
    try:
        import tkinter
        kok = tkinter.Tk()
        kok.destroy()
        return True
    except Exception:
        return False


EKRAN_VAR = ekran_var_mi()


@unittest.skipUnless(EKRAN_VAR, "Arayüz testleri ekran gerektirir")
class ArayuzTestTemeli(unittest.TestCase):
    # Geçmişe alınması beklenen dosyalar (uygulamanın kendi kayıt deseni)
    GECMIS_DOSYALARI = ["img_20250101_120000.png",
                        "img_20250102_120000.png",
                        "img_20250103_120000.png"]
    # Desene uymayan, geçmişte görünmemesi gereken dosyalar
    YABANCI_DOSYALAR = ["disaridan_kopyalanan.png", "notlar.txt"]

    def setUp(self):
        self.klasor = tempfile.mkdtemp(prefix="ai_studio_test_")

        for ad in self.GECMIS_DOSYALARI:
            Image.new("RGB", (64, 32), (120, 60, 200)).save(os.path.join(self.klasor, ad))
        Image.new("RGB", (40, 40), (10, 10, 10)).save(
            os.path.join(self.klasor, "disaridan_kopyalanan.png"))
        with open(os.path.join(self.klasor, "notlar.txt"), "w", encoding="utf-8") as f:
            f.write("metin")

        self.env = mock.patch.dict(os.environ, {"OUTPUT_DIR": self.klasor})
        self.env.start()

        import main
        self.main = main
        self.app = main.AIArtApp()
        self._pompala(40)

    def tearDown(self):
        # CustomTkinter periyodik after() işleri kuruyor; pencere yok edilince
        # bunlar "invalid command name" gürültüsü üretiyor. Önce hepsini iptal et.
        try:
            for is_id in self.app.tk.eval("after info").split():
                try:
                    self.app.after_cancel(is_id)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self.app.destroy()
        except Exception:
            pass

        self.env.stop()
        shutil.rmtree(self.klasor, ignore_errors=True)

    def _pompala(self, tur=15, sn=0.02):
        """Tk olay döngüsünü elle çevirir; after() işlerinin çalışmasını sağlar."""
        for _ in range(tur):
            self.app.update()
            self.app.update_idletasks()
            time.sleep(sn)

    def _png_sayisi(self):
        return len(glob.glob(os.path.join(self.klasor, "*.png")))


class GecmisYuklemeTest(ArayuzTestTemeli):
    def test_kendi_kaydettigi_dosyalar_geri_yukleniyor(self):
        self.assertEqual(len(self.app.history_frame.winfo_children()),
                         len(self.GECMIS_DOSYALARI))

    def test_yabanci_dosyalar_gecmise_alinmiyor(self):
        # Klasörde 4 PNG var ama sadece 3'ü uygulamanın kendi deseninde.
        self.assertEqual(self._png_sayisi(), 4)
        self.assertEqual(len(self.app.history_frame.winfo_children()), 3)

    def test_yukleme_kuyrugu_bosaliyor(self):
        self.assertEqual(self.app._pending_history, [])

    def test_bozuk_dosya_uygulamayi_cokertmiyor(self):
        bozuk = os.path.join(self.klasor, "img_20250104_120000.png")
        with open(bozuk, "wb") as f:
            f.write(b"gecerli bir png degil")

        self.app._pending_history = [bozuk]
        self.app._process_history_queue()
        self._pompala(5)   # buraya gelebiliyorsa çökmemiş demektir

    def test_gecmisten_yukleme_kaydet_dugmesini_aciyor(self):
        self.app.save_btn.configure(state="disabled")
        self.app._load_from_history(os.path.join(self.klasor, self.GECMIS_DOSYALARI[0]))
        self._pompala(5)
        self.assertEqual(self.app.save_btn.cget("state"), "normal")
        self.assertEqual(self.app.status_lbl.cget("text"), "Geçmişten Yüklendi")


class KucukResimTest(ArayuzTestTemeli):
    def test_kare_olmayan_gorselin_orani_korunuyor(self):
        yol = os.path.join(self.klasor, self.GECMIS_DOSYALARI[0])
        with Image.open(yol) as im:
            asil_oran = im.width / im.height          # 64x32 -> 2.0

        dugme = self.app.history_frame.winfo_children()[0]
        genislik, yukseklik = dugme.cget("image").cget("size")

        self.assertNotEqual(genislik, yukseklik, "küçük resim kareye eziliyor")
        self.assertAlmostEqual(genislik / yukseklik, asil_oran, delta=0.05)


class PromptDogrulamaTest(ArayuzTestTemeli):
    def test_cok_uzun_prompt_reddediliyor(self):
        with mock.patch.object(self.main.messagebox, "showwarning") as uyari, \
             mock.patch.object(self.main.threading, "Thread") as thread:
            self.app.prompt_entry.delete(0, "end")
            self.app.prompt_entry.insert(0, "a" * (self.main.MAX_PROMPT_LENGTH + 1))
            self.app.style_menu.set("Standart")
            self.app._start_thread()

        self.assertTrue(uyari.called)
        self.assertFalse(thread.called, "sınırı aşan istek yine de gönderildi")

    def test_bos_prompt_reddediliyor(self):
        with mock.patch.object(self.main.messagebox, "showwarning") as uyari, \
             mock.patch.object(self.main.threading, "Thread") as thread:
            self.app.prompt_entry.delete(0, "end")
            self.app.prompt_entry.insert(0, "    ")
            self.app._start_thread()

        self.assertTrue(uyari.called)
        self.assertFalse(thread.called)

    def test_normal_prompt_kabul_ediliyor(self):
        with mock.patch.object(self.main.messagebox, "showwarning") as uyari, \
             mock.patch.object(self.main.threading, "Thread") as thread:
            self.app.prompt_entry.delete(0, "end")
            self.app.prompt_entry.insert(0, "bir kedi")
            self.app._start_thread()

        self.assertFalse(uyari.called)
        self.assertTrue(thread.called)
        self.assertEqual(self.app.generate_btn.cget("text"), "İPTAL")


class IptalTest(ArayuzTestTemeli):
    def _uretim_baslat(self):
        with mock.patch.object(self.main.threading, "Thread"):
            self.app.prompt_entry.delete(0, "end")
            self.app.prompt_entry.insert(0, "bir kedi")
            self.app._start_thread()
        return self.app._generation_id

    def test_iptal_arayuzu_serbest_birakiyor(self):
        self._uretim_baslat()
        self.app._cancel()
        self._pompala(5)

        self.assertEqual(self.app.generate_btn.cget("text"), "GÖRSEL OLUŞTUR")
        self.assertEqual(self.app.status_lbl.cget("text"), "İptal edildi")

    def test_iptal_bayragi_kalkiyor(self):
        # Üretici thread'i bu bayrağa bakarak indirmeyi yarıda bırakıyor.
        self._uretim_baslat()
        bayrak = self.app._cancel_event
        self.assertFalse(bayrak.is_set())

        self.app._cancel()
        self._pompala(3)
        self.assertTrue(bayrak.is_set(), "iptal bayrağı kaldırılmadı")

    def test_her_uretim_yeni_bayrakla_basliyor(self):
        self._uretim_baslat()
        ilk_bayrak = self.app._cancel_event
        self.app._cancel()

        self._uretim_baslat()
        self.assertIsNot(self.app._cancel_event, ilk_bayrak)
        self.assertFalse(self.app._cancel_event.is_set(),
                         "yeni üretim iptal edilmiş bayrakla başlıyor")

    def test_iptal_edilen_sonuc_kaydedilmiyor(self):
        calisan_id = self._uretim_baslat()
        onceki_gorsel = self.app.generated_image
        dosya_once = self._png_sayisi()

        self.app._cancel()
        self._pompala(3)

        # İptalden sonra sonuç geç gelirse yok sayılmalı.
        self.app._success(Image.new("RGB", (64, 64), (0, 128, 255)), calisan_id)
        self._pompala(3)

        self.assertEqual(self._png_sayisi(), dosya_once, "iptal edilen görsel diske yazıldı")
        self.assertIs(self.app.generated_image, onceki_gorsel)
        self.assertEqual(self.app.status_lbl.cget("text"), "İptal edildi")

    def test_iptal_edilen_istegin_hatasi_gosterilmiyor(self):
        calisan_id = self._uretim_baslat()
        self.app._cancel()
        self._pompala(3)

        with mock.patch.object(self.main.messagebox, "showerror") as hata:
            self.app._error("eskimiş hata", calisan_id)
        self.assertFalse(hata.called)


class BasariliUretimTest(ArayuzTestTemeli):
    def test_gecerli_sonuc_kaydedilip_gosteriliyor(self):
        dosya_once = self._png_sayisi()
        gorsel = Image.new("RGB", (48, 96), (10, 200, 10))

        self.app._success(gorsel, self.app._generation_id)
        self._pompala(5)

        self.assertEqual(self._png_sayisi(), dosya_once + 1)
        self.assertIs(self.app.generated_image, gorsel)
        self.assertEqual(self.app.status_lbl.cget("text"), "Tamamlandı")
        self.assertEqual(self.app.save_btn.cget("state"), "normal")

    def test_kaydedilen_dosya_gecmis_desenine_uyuyor(self):
        self.app._success(Image.new("RGB", (32, 32)), self.app._generation_id)
        self._pompala(5)

        yeni = sorted(glob.glob(os.path.join(self.klasor, "img_*.png")),
                      key=os.path.getmtime)[-1]
        self.assertTrue(self.main.HISTORY_FILE_PATTERN.match(os.path.basename(yeni)))


class ModelSecimiTest(ArayuzTestTemeli):
    def test_hugging_face_secilince_boyut_menusu_acik_kaliyor(self):
        self.app._change_model("Hugging Face")
        self._pompala(3)
        self.assertEqual(self.app.size_menu.cget("state"), "normal")

    def test_model_degisince_uretici_degisiyor(self):
        self.app._change_model("Hugging Face")
        self.assertIsInstance(self.app.current_generator, self.main.HuggingFaceGenerator)

        self.app._change_model("OpenAI DALL-E 3")
        self.assertIsInstance(self.app.current_generator, self.main.OpenAIGenerator)


if __name__ == "__main__":
    unittest.main()
