# AI Görsel İstasyonu

Metin açıklamasından yapay zekâ ile görsel üreten bir masaüstü uygulaması. Kullanıcı ne çizilmesini istediğini yazıyor (OpenAI sağlayıcısı Türkçe anlıyor), hazır stil şablonlarından birini (gerçekçi fotoğraf, sinematik, 3D render, anime, cyberpunk) ve çıktı oranını seçiyor; uygulama isteği OpenAI'ın görsel API'sine gönderip dönen görseli ekranda gösteriyor, aynı anda diske kaydediyor ve üretilenleri yan paneldeki geçmiş şeridinde topluyor — bu şerit uygulama kapatılıp açıldığında da kayıt klasöründen yeniden doluyor. Görsel üretimi arka plan thread'inde çalıştığı için istek sürerken arayüz donmuyor, üretim istenirse iptal edilebiliyor. Üretici katmanı Strategy deseniyle soyutlandığından ikinci sağlayıcı (Hugging Face) tek bir sınıfla eklenmiş durumda.

## Uygulama

![Uygulama arayüzü](ornekler/uygulama-arayuzu.png)

Solda model, stil ve boyut seçimi; ortada üretilen görselin önizlemesi; sağda kayıt klasöründen yüklenen geçmiş şeridi.

## Örnek çıktılar

| | |
|---|---|
| ![3D render](ornekler/01-3d-render-robot.png) | ![Sinematik](ornekler/02-sinematik-agac-sehir.png) |
| *3D Render (Oyun)* stili — "Bir serada bitkileri sulayan sevimli bir robot" | *Sinematik Sahne* stili — "Dev bir ağacın üzerine kurulmuş fütüristik bir şehir" |

![Geniş format](ornekler/03-sinematik-genis-1536.png)

*Sinematik Sahne* stili, 1536x1024 geniş format — `gpt-image-1` ile üretildi.

![Çizim](ornekler/04-cizim-fil-karinca.png)

*Anime / Çizim* stili, 1024x1024.

![Hugging Face](ornekler/05-huggingface-agac-kasaba.png)

Aynı *Sinematik Sahne* stili, bu kez **Hugging Face** sağlayıcısıyla (Stable Diffusion 3 Medium) — sağlayıcı değişse de stil talimatı aynı şekilde uygulanıyor.

## Kullanılan teknolojiler

| Teknoloji | Sürüm | Amaç |
|---|---|---|
| Python | 3.13 | Çalışma ortamı |
| CustomTkinter | 5.2.2 | Koyu temalı masaüstü arayüzü |
| Pillow | 12.0.0 | Görsel işleme, önizleme ve kaydetme |
| Requests | 2.32.5 | HTTP istekleri |
| python-dotenv | 1.2.1 | Ortam değişkeni yönetimi |
| OpenAI Images API | `gpt-image-1` | Birincil görsel üretimi |
| Hugging Face Inference | `stable-diffusion-3-medium` | Alternatif sağlayıcı |

Mimari olarak `generators.py` içinde soyut bir `ImageGeneratorStrategy` arayüzü ve onu uygulayan iki sağlayıcı, `main.py` içinde ise arayüz ve uygulama akışı yer alır. Ağ işleri `threading` ile arka plana alınır, sonuç `after()` üzerinden ana thread'e döndürülür.

## Kurulum

Gereksinim: Python 3.10 veya üzeri (3.13 ile geliştirildi) ve geçerli bir OpenAI API anahtarı. Arayüz Tkinter kullanır; Windows ve macOS'ta Python ile birlikte gelir, Linux'ta ayrıca kurulması gerekebilir (`sudo apt install python3-tk`).

**1. Depoyu klonlayın**

```bash
git clone https://github.com/HamzaSarikaya/Ai-Visual-Production.git
cd Ai-Visual-Production
```

**2. Sanal ortam oluşturup etkinleştirin**

Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Bağımlılıkları kurun**

```bash
pip install -r requirements.txt
```

**4. Ortam değişkenlerini ayarlayın**

`.env.example` dosyasını `.env` olarak kopyalayın:

```bash
cp .env.example .env
```

Windows'ta `copy .env.example .env`. Ardından `.env` dosyasını açıp anahtarınızı girin:

| Değişken | Zorunlu | Açıklama |
|---|---|---|
| `OPENAI_API_KEY` | Evet | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) adresinden alınır. |
| `HF_API_KEY` | Hayır | Yalnızca Hugging Face sağlayıcısı seçilirse kullanılır. [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| `OUTPUT_DIR` | Hayır | Görsellerin kaydedileceği klasör. Boş bırakılırsa proje içindeki `fotolar` klasörü kullanılır. |
| `OPENAI_MODEL` | Hayır | Varsayılan `gpt-image-1`. Daha ucuz seçenek: `gpt-image-1-mini`. |
| `OPENAI_IMAGE_QUALITY` | Hayır | `low` / `medium` / `high` / `auto`. Varsayılan `medium`; `low` belirgin şekilde ucuzdur. |
| `HF_MODEL_ID` | Hayır | Varsayılan `stabilityai/stable-diffusion-3-medium-diffusers`. |
| `HF_API_URL` | Hayır | Uç noktanın kök adresi. Varsayılan `https://router.huggingface.co/hf-inference/models`. |

`.env` dosyası `.gitignore` içinde olduğu için depoya gönderilmez.

**5. Çalıştırın**

```bash
python main.py
```

OpenAI görsel üretimi ücretlidir; her görsel hesabınızdan ücretlendirilir. Maliyeti düşürmek için `OPENAI_IMAGE_QUALITY=low` veya `OPENAI_MODEL=gpt-image-1-mini` kullanabilirsiniz.

## Öne çıkan özellikler

- **Stil şablonları** — Seçilen stile göre kullanıcının yazdığı metnin sonuna hazır bir prompt eki ekleniyor, böylece kısa bir cümleden detaylı sonuç alınabiliyor.
- **Üç çıktı oranı** — Kare (1024x1024), yatay (1536x1024) ve dikey (1024x1536). Bunlar `gpt-image-1`'in kabul ettiği boyutlar.
- **İki sağlayıcı** — OpenAI ve Hugging Face arasında menüden geçiş yapılıyor; ikisi de aynı `ImageGeneratorStrategy` arayüzünü uyguluyor.
- **Donmayan arayüz** — Üretim isteği ayrı bir thread'de çalışıyor, sonuç ana thread'e `after()` ile aktarılıyor.
- **Otomatik kayıt** — Her görsel zaman damgalı bir dosya adıyla (`img_20260101_120000.png`) diske yazılıyor; ayrıca "Farklı Kaydet" ile istenen konuma kaydedilebiliyor.
- **Kalıcı geçmiş paneli** — Üretilen görsellerin küçük önizlemeleri sağ panelde listeleniyor, tıklayınca tam boyutta geri yükleniyor. Uygulama yeniden açıldığında kayıt klasöründeki son 20 görsel şeride geri yükleniyor; yükleme tek tek yapıldığı için açılış donmuyor. Yalnızca uygulamanın kendi kayıt deseni taranır, klasöre dışarıdan konan görseller şeride karışmaz.
- **İptal edilebilir üretim** — Üretim sürerken buton "İPTAL"e dönüşüyor. İki katmanlı çalışıyor: indirme sürüyorsa gövde parça parça okunduğu için indirme anında yarıda kesiliyor; sonuç yine de gelirse artan bir üretim numarası onu geçersiz kılıyor, görsel ne diske yazılıyor ne ekrana geliyor.
- **Sağlayıcı ayarları koda gömülü değil** — Model, kalite ve uç nokta adresi ortam değişkeninden okunuyor; sağlayıcı bir modeli kaldırdığında kod değiştirmek gerekmiyor.

## Testler

Toplam 61 test, iki dosyada. Hiçbiri ağa çıkmaz ve API anahtarı gerektirmez; HTTP katmanı sahte nesnelerle değiştirilir.

```bash
python -m unittest -v
```

| Dosya | Kapsam |
|---|---|
| `test_generators.py` | Üretici katmanı: istek gövdesi, zaman aşımları, base64 ve URL yanıt biçimleri, hata biçimleri, iptal davranışı, boyut parametresi |
| `test_app.py` | Arayüz: geçmiş yükleme ve filtreleme, küçük resim oranı, prompt doğrulama, iptal akışı, kayıt |

`test_app.py` gerçek bir pencere açtığı için ekran gerektirir; başsız bir ortamda (örneğin ekransız bir CI sunucusu) bu testler otomatik olarak atlanır. Her test kendi geçici kayıt klasöründe çalışır, projedeki `fotolar` klasörüne dokunmaz.

## Prompt tasarımı

Stil şablonları başta `photorealistic, 8k resolution, highly detailed, masterpiece, unreal engine 5` gibi anahtar kelime yığınlarıydı. Bu yaklaşım Stable Diffusion 1.x / Midjourney dönemine ait: o modeller CLIP ile etiket eşleştirdiği için "kalite artırıcı" kelimeler işe yarıyordu. `gpt-image-1` ve Stable Diffusion 3 ise talimatı okuyup uyguluyor; bu etiketler artık ölçülebilir bir katkı sağlamıyor, sadece prompt bütçesini yiyor.

Şablonlar bu yüzden düz İngilizce talimatlara çevrildi — ışığı, objektifi, renk paletini ve kompozisyonu açıkça tarif ediyorlar. İki somut değişiklik:

- **Pozlama açıkça dengeleniyor.** Yalnızca `cinematic, dramatic lighting, atmospheric` denince modeller sahneyi aşırı karartıyordu. Şablonlarda artık "shadows stay readable", "keep the image well exposed", "blacks that still hold detail" gibi ifadeler var.
- **Örnek promptlar yalnızca sahneyi anlatıyor.** Eskiden içlerinde `pixar tarzı`, `sinematik aydınlatma` gibi ekler vardı ve menüden seçilen stille çakışıyordu. Görünüm kararı artık tamamen stil menüsüne ait.

`test_app.py` içindeki testler eski etiketlerin geri sızmasını ve pozlama ifadesinin kaybolmasını engelliyor.

## Sağlayıcı notu

Proje ilk yazıldığında OpenAI tarafında `dall-e-3`, Hugging Face tarafında `api-inference.huggingface.co` üzerinden `FLUX.1-dev` kullanılıyordu. İkisi de artık geçerli değil:

- `dall-e-3` kaldırılmış durumda — API'nin verdiği yanıt: *"The model 'dall-e-3' does not exist."* Yerine `gpt-image-1` kullanılıyor. Bu modelin desteklediği boyutlar farklı olduğu için eski `1792x1024` / `1024x1792` seçenekleri de `1536x1024` / `1024x1536` ile değiştirildi.
- `api-inference.huggingface.co` kapandı (DNS'te hiçbir adrese çözülmüyor). Yerine `router.huggingface.co` kullanılıyor. `FLUX.1-dev` bu sağlayıcıda artık servis edilmiyor (HTTP 410); varsayılan model, `hf-inference` üzerinde çalıştığı doğrulanan Stable Diffusion 3 Medium olarak değiştirildi.

Her iki yol da canlı olarak test edildi ve görsel üretmesi doğrulandı.

## Bilinen eksikler

- **İptal, yanıt beklenirken ağ seviyesinde kesilemiyor.** İptalin indirme aşamasını gerçekten yarıda kestiği ölçüldü: yavaş yanıt veren yerel bir sunucuya karşı bağlantı, bayrak kaldırıldıktan ~1,6 saniye sonra bırakıldı. Ancak istek henüz *yanıt beklerken* iptal edilirse bu bekleme kesilemiyor — `requests` ile yapılan bloklayıcı bir çağrı başka bir thread'den güvenilir biçimde durdurulamıyor (`Session.close()` denendi, Windows'ta bloke soketi çözmedi). Bu durumda arayüz anında serbest kalıyor ve sonuç geldiğinde yok sayılıyor, ama istek arka planda sürüyor. Pratik sonucu: iptal ettiğiniz bir üretim sağlayıcı tarafında yine de ücretlendirilir. Yanıt hiç gelmezse istek 180 saniyede zaman aşımına uğrar.
- **Hugging Face sağlayıcısı Türkçe anlamıyor.** Stable Diffusion 3'ün metin kodlayıcısı Türkçe eğitilmediği için Türkçe bir açıklama sahneyle ilgisiz görsel üretiyor; aynı sahne İngilizce yazıldığında doğru sonuç geliyor. Bu ikisi yan yana test edildi. Arayüz, Hugging Face seçildiğinde model menüsünün altında uyarı gösteriyor. OpenAI sağlayıcısı Türkçe açıklamaları sorunsuz anlıyor.
- **Hugging Face tarafında yalnızca `hf-inference` sağlayıcısı destekleniyor.** FLUX gibi popüler modeller bugün `fal-ai`, `replicate` veya `wavespeed` üzerinden sunuluyor ve bu sağlayıcıların istek biçimi farklı. Adres `HF_API_URL` ile değiştirilebilir ama gövde biçimi uyarlanmadan çalışmaz.
- **Geçmişten silme yok.** Şeritteki bir görseli arayüzden kaldırmak mümkün değil; dosyayı kayıt klasöründen elle silmek gerekiyor.

## Lisans

MIT
