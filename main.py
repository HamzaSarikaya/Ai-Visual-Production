import customtkinter as ctk
from tkinter import messagebox, filedialog
import threading
from PIL import Image
import os
import datetime
import random
from dotenv import load_dotenv


try:
    from generators import HuggingFaceGenerator, OpenAIGenerator
except ImportError as e:
    print(f"KRİTİK HATA: generators.py dosyası bulunamadı! {e}")
    exit()

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

        self.styles = {
            "Standart": "",
            "Gerçekçi Fotoğraf": ", photorealistic, 8k resolution, highly detailed, sharp focus, cinematic lighting, masterpiece",
            "Sinematik Sahne": ", cinematic movie scene, dramatic lighting, atmospheric, highly detailed, 8k, movie still",
            "3D Render (Oyun)": ", 3d render, unreal engine 5, intricate details, smooth textures, global illumination, 8k",
            "Anime / Çizim": ", anime style, studio Ghibli inspired, vibrant colors, high quality illustration",
            "Cyberpunk": ", cyberpunk style, neon lights, futuristic, highly detailed, digital painting"
        }

        self.sizes = {
            "Kare (1024x1024)": "1024x1024",
            "Geniş/Yatay (1792x1024)": "1792x1024",
            "Dikey/Telefon (1024x1792)": "1024x1792"
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

    def _setup_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")

        ctk.CTkLabel(self.sidebar, text="AI STUDIO", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(30,20))

        ctk.CTkLabel(self.sidebar, text="Model:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(padx=20, pady=(10, 0), anchor="w")
        self.model_menu = ctk.CTkOptionMenu(self.sidebar, values=["OpenAI DALL-E 3", "Hugging Face"], command=self._change_model)
        self.model_menu.pack(padx=20, pady=5)
        self.model_menu.set("OpenAI DALL-E 3")

        ctk.CTkLabel(self.sidebar, text="Stil:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(padx=20, pady=(15, 0), anchor="w")
        self.style_menu = ctk.CTkOptionMenu(self.sidebar, values=list(self.styles.keys()))
        self.style_menu.pack(padx=20, pady=5)
        self.style_menu.set("Gerçekçi Fotoğraf")

        ctk.CTkLabel(self.sidebar, text="Boyut:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(padx=20, pady=(15, 0), anchor="w")
        self.size_menu = ctk.CTkOptionMenu(self.sidebar, values=list(self.sizes.keys()))
        self.size_menu.pack(padx=20, pady=5)

        self.generate_btn = ctk.CTkButton(self.sidebar, text="GÖRSEL OLUŞTUR", command=self._start_thread, height=50, font=ctk.CTkFont(weight="bold"), fg_color="#1f6aa5")
        self.generate_btn.pack(padx=20, pady=30)

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
            self.size_menu.configure(state="disabled")
        else:
            self.current_generator = OpenAIGenerator()
            self.size_menu.configure(state="normal")

    def _random_prompt(self):
        prompt = random.choice(self.random_prompts)
        self.prompt_entry.delete(0, "end")
        self.prompt_entry.insert(0, prompt)

    def _start_thread(self):
        base_prompt = self.prompt_entry.get()
        if not base_prompt:
            messagebox.showwarning("Uyarı", "Lütfen bir şeyler yazın.")
            return
        
        style_suffix = self.styles.get(self.style_menu.get(), "")
        final_prompt = base_prompt + style_suffix
        
        selected_size = self.sizes.get(self.size_menu.get(), "1024x1024")

        self.generate_btn.configure(state="disabled", text="İşleniyor...")
        self.status_lbl.configure(text="Üretiliyor...", text_color="orange")
        
        threading.Thread(target=self._generate, args=(final_prompt, selected_size), daemon=True).start()

    def _generate(self, prompt, size):
        try:
            if not self.current_generator: self.current_generator = OpenAIGenerator()
            image = self.current_generator.generate(prompt, size)
            self.generated_image = image
            self.after(0, self._success)
        except Exception as e:
            self.after(0, lambda: self._error(str(e)))

    def _success(self):
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"img_{timestamp}.png"
            full_path = os.path.join(self.auto_save_path, filename)
            self.generated_image.save(full_path)
            print(f"Otomatik kaydedildi: {full_path}")
            
            self._add_to_history_ui(full_path, self.generated_image)

        except Exception as e:
            print(f"Oto-kayıt hatası: {e}")

        self._display_image(self.generated_image)
        
        self.generate_btn.configure(state="normal", text="GÖRSEL OLUŞTUR")
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

    def _add_to_history_ui(self, file_path, img_obj):
        try:
            thumb = img_obj.copy()
            thumb.thumbnail((100, 100))
            ctk_thumb = ctk.CTkImage(thumb, size=(100, 100))
            
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
            self.status_lbl.configure(text="Geçmişten Yüklendi", text_color="cyan")
        except Exception as e:
            messagebox.showerror("Hata", f"Resim açılamadı: {e}")

    def _error(self, msg):
        messagebox.showerror("Hata", msg)
        self.generate_btn.configure(state="normal", text="TEKRAR DENE")
        self.status_lbl.configure(text="Hata", text_color="red")

    def _save_as(self):
        if self.generated_image:
            path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
            if path: self.generated_image.save(path)

if __name__ == "__main__":
    app = AIArtApp()
    app.mainloop()