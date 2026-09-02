import customtkinter as ctk
from tkinter import messagebox, filedialog
import threading
from PIL import Image
import os
import re
import datetime
import random
from dotenv import load_dotenv


try:
    from generators import GenerationCancelled, HuggingFaceGenerator, OpenAIGenerator
except ImportError as e:
    print(f"KRİTİK HATA: generators.py dosyası bulunamadı! {e}")
    exit()

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Uygulama düzeyinde temkinli bir üst sınır. Sağlayıcıların kendi sınırları
# bundan yüksek, ama bu uzunlukta bir açıklama zaten kullanıcı hatasıdır.
MAX_PROMPT_LENGTH = 4000

# Açılışta geçmiş şeridine geri yüklenecek en fazla görsel sayısı.
HISTORY_LOAD_LIMIT = 20

# Geçmişe yalnızca uygulamanın kendi kaydettiği dosyalar alınıyor; klasöre
# dışarıdan kopyalanan görseller şeride karışmasın.
HISTORY_FILE_PATTERN = re.compile(r"^img_\d{8}_\d{6}\.png$", re.IGNORECASE)

class AIArtApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Görsel İstasyonu v2.0")
        self.geometry("1200x850")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.auto_save_path = os.getenv("OUTPUT_DIR") or os.path.join(BASE_DIR, "fotolar")
        try:
            os.makedirs(self.auto_save_path, exist_ok=True)
        except OSError as e:
            print(f"Kayıt klasörü oluşturulamadı: {e}")

        self.current_generator = None
        self.generated_image = None

        # Her üretime artan bir numara veriliyor; iptal edilen isteğin geç gelen
        # sonucu bu numarayı tutmadığı için yok sayılıyor.
        self._generation_id = 0
        self._cancel_event = threading.Event()
        self._pending_history = []

        self.styles = {
            "Standart": "",
            "Gerçekçi Fotoğraf": ", photorealistic, 8k resolution, highly detailed, sharp focus, cinematic lighting, masterpiece",
            "Sinematik Sahne": ", cinematic movie scene, dramatic lighting, atmospheric, highly detailed, 8k, movie still",
            "3D Render (Oyun)": ", 3d render, unreal engine 5, intricate details, smooth textures, global illumination, 8k",
            "Anime / Çizim": ", anime style, studio Ghibli inspired, vibrant colors, high quality illustration",
            "Cyberpunk": ", cyberpunk style, neon lights, futuristic, highly detailed, digital painting"
        }

        # gpt-image-1'in kabul ettiği boyutlar. Eski 1792x1024 / 1024x1792
        # değerleri DALL-E 3'e aitti ve artık reddediliyor.
        self.sizes = {
            "Kare (1024x1024)": "1024x1024",
            "Geniş/Yatay (1536x1024)": "1536x1024",
            "Dikey/Telefon (1024x1536)": "1024x1536"
        }

        self.random_prompts = [
            "Dev bir ağacın üzerine kurulmuş fütüristik bir şehir, sinematik aydınlatma",
            "İstanbul'da cyberpunk bir sokak yemeği satıcısı, neon ışıklar, gece",
            "Yüzen bir ada üzerindeki ortaçağ kalesi",
            "Bir serada bitkileri sulayan sevimli bir robot, pixar tarzı",
            "Bir ormanda gizlenmiş antik bir tapınak, mistik atmosfer"
        ]

        self._setup_ui()
        self.current_generator = OpenAIGenerator()

        # Pencere görünür olduktan sonra başlasın ki açılış donuk hissettirmesin.
        self.after(200, self._load_existing_history)

    def _setup_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")

        ctk.CTkLabel(self.sidebar, text="AI STUDIO", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(30,20))

        ctk.CTkLabel(self.sidebar, text="Model:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(padx=20, pady=(10, 0), anchor="w")
        self.model_menu = ctk.CTkOptionMenu(self.sidebar, values=["OpenAI", "Hugging Face"], command=self._change_model)
        self.model_menu.pack(padx=20, pady=5)
        self.model_menu.set("OpenAI")

        ctk.CTkLabel(self.sidebar, text="Stil:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(padx=20, pady=(15, 0), anchor="w")
        self.style_menu = ctk.CTkOptionMenu(self.sidebar, values=list(self.styles.keys()))
        self.style_menu.pack(padx=20, pady=5)
        self.style_menu.set("Gerçekçi Fotoğraf")

        ctk.CTkLabel(self.sidebar, text="Boyut:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(padx=20, pady=(15, 0), anchor="w")
        self.size_menu = ctk.CTkOptionMenu(self.sidebar, values=list(self.sizes.keys()))
        self.size_menu.pack(padx=20, pady=5)

        self.generate_btn = ctk.CTkButton(self.sidebar, text="GÖRSEL OLUŞTUR", command=self._start_thread, height=50, font=ctk.CTkFont(weight="bold"), fg_color="#1f6aa5")
        self.generate_btn.pack(padx=20, pady=30)

        # İptal modunda rengi değiştirip geri döneceğimiz için varsayılanları saklıyoruz.
        self._btn_default_fg = self.generate_btn.cget("fg_color")
        self._btn_default_hover = self.generate_btn.cget("hover_color")

        self.save_btn = ctk.CTkButton(self.sidebar, text="Farklı Kaydet...", command=self._save_as, state="disabled")
        self.save_btn.pack(padx=20, pady=10)

        self.status_lbl = ctk.CTkLabel(self.sidebar, text="Hazır", text_color="gray")
        self.status_lbl.pack(side="bottom", pady=20)

        self.history_frame = ctk.CTkScrollableFrame(self, width=150, label_text="Geçmiş")
        self.history_frame.pack(side="right", fill="y", padx=10, pady=10)

        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.pack(side="left", fill="both", expand=True, padx=20, pady=20)

        prompt_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        prompt_frame.pack(fill="x", pady=(0, 20))

        self.prompt_entry = ctk.CTkEntry(prompt_frame, placeholder_text="Ne çizelim?...", height=40)
        self.prompt_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.random_btn = ctk.CTkButton(prompt_frame, text="🎲 Fikir Ver", width=100, height=40, command=self._random_prompt, fg_color="#E67E22", hover_color="#D35400")
        self.random_btn.pack(side="right")

        self.image_display = ctk.CTkLabel(self.main_area, text="Görsel Bekleniyor...", font=ctk.CTkFont(size=16), fg_color="#1A1A1A", corner_radius=10)
        self.image_display.pack(fill="both", expand=True)

    def _change_model(self, choice):
        if choice == "Hugging Face":
            self.current_generator = HuggingFaceGenerator()
        else:
            self.current_generator = OpenAIGenerator()

    def _random_prompt(self):
        prompt = random.choice(self.random_prompts)
        self.prompt_entry.delete(0, "end")
        self.prompt_entry.insert(0, prompt)

    def _start_thread(self):
        base_prompt = self.prompt_entry.get().strip()
        if not base_prompt:
            messagebox.showwarning("Uyarı", "Lütfen bir şeyler yazın.")
            return

        style_suffix = self.styles.get(self.style_menu.get(), "")
        final_prompt = base_prompt + style_suffix

        if len(final_prompt) > MAX_PROMPT_LENGTH:
            fazla = len(final_prompt) - MAX_PROMPT_LENGTH
            messagebox.showwarning(
                "Uyarı",
                f"Açıklama çok uzun. Stil eki dahil {len(final_prompt)} karakter, "
                f"sınır {MAX_PROMPT_LENGTH}. {fazla} karakter kısaltın."
            )
            return

        selected_size = self.sizes.get(self.size_menu.get(), "1024x1024")

        self._generation_id += 1
        gen_id = self._generation_id
        self._cancel_event = threading.Event()

        self.generate_btn.configure(text="İPTAL", fg_color="#C0392B", hover_color="#A93226", command=self._cancel)
        self.status_lbl.configure(text="Üretiliyor...", text_color="orange")

        threading.Thread(target=self._generate,
                         args=(final_prompt, selected_size, gen_id, self._cancel_event),
                         daemon=True).start()

    def _cancel(self):
        # Bayrak, üretici thread'ine indirmeyi yarıda bırakmasını söylüyor.
        # Numara ise sonuç yine de gelirse onu geçersiz kılıyor.
        self._cancel_event.set()
        self._generation_id += 1

        self._reset_generate_button()
        self.status_lbl.configure(text="İptal edildi", text_color="gray")

    def _reset_generate_button(self, text="GÖRSEL OLUŞTUR"):
        self.generate_btn.configure(text=text, fg_color=self._btn_default_fg,
                                    hover_color=self._btn_default_hover,
                                    command=self._start_thread)

    def _generate(self, prompt, size, gen_id, cancel_event):
        try:
            if not self.current_generator: self.current_generator = OpenAIGenerator()
            image = self.current_generator.generate(prompt, size, cancel_event)
            self.after(0, lambda: self._success(image, gen_id))
        except GenerationCancelled:
            # Kullanıcının kendi isteği; arayüz zaten sıfırlandı, hata gösterme.
            pass
        except Exception as e:
            mesaj = str(e)
            self.after(0, lambda: self._error(mesaj, gen_id))

    def _success(self, image, gen_id):
        if gen_id != self._generation_id:
            return

        self.generated_image = image
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"img_{timestamp}.png"
            full_path = os.path.join(self.auto_save_path, filename)
            image.save(full_path)
            print(f"Otomatik kaydedildi: {full_path}")

            self._add_to_history_ui(full_path, image)

        except Exception as e:
            print(f"Oto-kayıt hatası: {e}")

        self._display_image(image)

        self._reset_generate_button()
        self.save_btn.configure(state="normal")
        self.status_lbl.configure(text="Tamamlandı", text_color="green")

    def _display_image(self, img_obj):
        w, h = img_obj.size
        scale = 0.8

        # Pencere henüz çizilmediyse winfo_* 1 döner ve görsel sıfır boyuta iner.
        max_w = max(self.main_area.winfo_width(), 400)
        max_h = max(self.main_area.winfo_height(), 400)

        ratio = min(max_w / w, max_h / h) * scale
        new_size = (max(int(w * ratio), 1), max(int(h * ratio), 1))

        ctk_img = ctk.CTkImage(img_obj, size=new_size)
        self.image_display.configure(image=ctk_img, text="")

    def _load_existing_history(self):
        """Önceki oturumlarda üretilmiş görselleri geçmiş şeridine geri yükler."""
        try:
            dosyalar = [
                os.path.join(self.auto_save_path, ad)
                for ad in os.listdir(self.auto_save_path)
                if HISTORY_FILE_PATTERN.match(ad)
            ]
        except OSError as e:
            print(f"Geçmiş klasörü okunamadı: {e}")
            return

        def _zaman(yol):
            try:
                return os.path.getmtime(yol)
            except OSError:
                return 0.0

        # En yeniler şeridin altında kalsın diye eskiden yeniye sıralıyoruz.
        dosyalar.sort(key=_zaman)
        self._pending_history = dosyalar[-HISTORY_LOAD_LIMIT:]
        self._process_history_queue()

    def _process_history_queue(self):
        """Görselleri teker teker açar; hepsini bir anda açmak arayüzü kilitliyor."""
        if not self._pending_history:
            return

        yol = self._pending_history.pop(0)
        try:
            with Image.open(yol) as img:
                self._add_to_history_ui(yol, img)
        except Exception as e:
            print(f"Geçmiş görseli atlandı ({os.path.basename(yol)}): {e}")

        self.after(10, self._process_history_queue)

    def _add_to_history_ui(self, file_path, img_obj):
        try:
            thumb = img_obj.copy()
            thumb.thumbnail((100, 100))
            # Gerçek küçük resim boyutunu veriyoruz; sabit kare vermek kare
            # olmayan görselleri eziyordu.
            ctk_thumb = ctk.CTkImage(thumb, size=thumb.size)

            btn = ctk.CTkButton(self.history_frame, text="", image=ctk_thumb, width=110, height=110,
                                command=lambda p=file_path: self._load_from_history(p))
            btn.pack(pady=5)

        except Exception as e:
            print(f"Geçmiş ekleme hatası: {e}")

    def _load_from_history(self, file_path):
        try:
            img = Image.open(file_path)
            self.generated_image = img
            self._display_image(img)
            self.save_btn.configure(state="normal")
            self.status_lbl.configure(text="Geçmişten Yüklendi", text_color="cyan")
        except Exception as e:
            messagebox.showerror("Hata", f"Resim açılamadı: {e}")

    def _error(self, msg, gen_id):
        if gen_id != self._generation_id:
            return

        messagebox.showerror("Hata", msg)
        self._reset_generate_button("TEKRAR DENE")
        self.status_lbl.configure(text="Hata", text_color="red")

    def _save_as(self):
        if self.generated_image:
            path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
            if path: self.generated_image.save(path)

if __name__ == "__main__":
    app = AIArtApp()
    app.mainloop()
