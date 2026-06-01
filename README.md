# RFQ Radar — Bulut (GitHub Actions + Pages)

Her gün TED + CanadaBuys + SAM.gov'dan talaşlı/döküm RFQ'larını otomatik çeker,
tek sayfada (GitHub Pages) gösterir. Sen sadece bir bookmark açarsın — Mac kapalı olsa bile günceldir.

## Dosyalar
- `fetch_all.py` — çekici (TED + CanadaBuys + SAM.gov), çıktı `site/rfq.json`
- `site/index.html` — gösterim sayfası (rfq.json'u okur + manuel ekleme + durum takibi)
- `.github/workflows/daily.yml` — günlük çalıştırma + Pages'e yayın

## Kurulum (tek seferlik)
1. GitHub'da yeni bir repo aç (örn. `rfq-radar`), **Public** seç (Pages ücretsiz için en kolayı).
2. Bu klasördeki tüm dosyaları repoya yükle (yapıyı koru: `.github/workflows/daily.yml`, `site/index.html`, `fetch_all.py`).
   - Web'den: "Add file → Upload files" ile sürükle. Klasör yapısını korumak için
     dosya adını `.github/workflows/daily.yml` şeklinde yazman yeterli.
3. **Settings → Pages → Build and deployment → Source: GitHub Actions** seç.
4. (Opsiyonel ama önerilir) SAM.gov için: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `SAM_API_KEY`  Value: SAM.gov hesabından aldığın ücretsiz anahtar
   - Anahtar yoksa SAM atlanır; TED + CanadaBuys yine çalışır.
5. **Actions** sekmesi → "RFQ fetch & publish" → **Run workflow** (ilk çalıştırma).
6. Bitince **Settings → Pages**'teki adres senin sayfan: `https://<kullanıcı>.github.io/rfq-radar/`
   Onu bookmark'la. Her gün 06:00 UTC'de otomatik tazelenir.

## Ayarlar (fetch_all.py en üstü)
- `DAYS_BACK` — kaç gün geriye bakılsın (az sonuçta büyüt)
- `TED_COUNTRIES` / `TED_CPV` — AB ülkeleri ve CPV ağı
- `SAM_NAICS` — 332710 talaşlı atölye, 331510/331520 dökümhane
- `KW_CASTING` / `KW_MACHINING` — pozitif anahtar kelimeler
- `KW_EXCLUDE` — tezgâh/ekipman ALIMI sinyalleri (yanlış pozitifleri eler)

## Sonraki faz
Üyelikle gelen API'leri verdiğinde her biri `fetch_all.py`'ye yeni bir fonksiyon olarak eklenir,
aynı şemayla aynı `rfq.json`'a yazar, sayfa değişmeden yeni kaynağı gösterir. Anahtarlar
GitHub secret olarak saklanır (kodda asla görünmez).
