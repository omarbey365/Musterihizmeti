# Müşteri Destek Portalı — Başlangıç Sürümü

Türkçe, Python/FastAPI tabanlı müşteri hizmetleri platformu.

## Yapabildikleri

- SSS sorusunun aynısını doğrudan cevaplar.
- API anahtarı gerektirmeyen **yerel, kural tabanlı Türkçe niyet tanıyıcı** ile SSS sorularının farklı söylenişlerini eşleştirir. Bu sistem üretken bir dil modeli değildir ve kapsam dışındaki soruları uzmana yönlendirir.
- SSS kapsamında güvenilir şekilde yanıtlanamayan soruları otomatik olarak uzman talebine dönüştürür.
- **Her müşteri sorusunu ve otomatik yanıtını** SQLite `messages` tablosuna kaydeder; uzmana aktarılanlar için talep numarası oluşturur. **Her uzman yanıtı ve durum değişikliği** `expert_history` tablosuna eklenir.
- Korunan `/uzman` ekranından uzman girişi, talep takibi, durum değiştirme ve yanıt yazma.
- Müşteri, aynı tarayıcıdan talebini ve uzman yanıtını takip eder.
- Şifre hash'i, imzalı oturum, CSRF kontrolü ve geliştirme ortamı istek sınırlaması vardır.

## Kurulum

Python 3.10+ kurulu olmalı. Terminalde proje klasörüne geçin:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
python setup.py
```

`setup.py` kullanıcı adı ve uzman parolası ister; `.env` dosyasını oluşturur. Uzman parolası kaynak koduna yazılmaz.

Yerel soru sınıflandırıcısı doğrudan çalışır, **API anahtarı gerekmez**. Model `local_ai.py` içindeki SSS niyet kurallarını kullanır.

Ardından:

```bash
uvicorn app:app --reload
```

- Müşteri: http://127.0.0.1:8000/
- Uzman: http://127.0.0.1:8000/uzman

## SSS ekleme

`sss.json` UTF-8 dosyasında soru/cevap girdileri bulunsun:

```json
[
  {"soru": "İade süresi kaç gündür?", "cevap": "İade süresi 14 gündür."},
  {"soru": "Destek ekibine nasıl ulaşırım?", "cevap": "Bu sohbet üzerinden mesaj gönderebilirsiniz."}
]
```

Bunlar *örnektir*, gerçek kurum politikasını temsil etmez. Dosyada başlangıçta örnek politika yoktur. SSS dosyasını değiştirmek için sunucuyu yeniden başlatmaya gerek yoktur.

## Önemli notlar / yayına alma

- Bu bir **çalışan ilk sürümdür (MVP)**, internete doğrudan açılmaya hazır üretim ürünü değildir.
- `COOKIE_SECURE=true` yapın, **HTTPS** kullanın, ters proxy ve güvenli güvenlik başlıkları ekleyin.
- İnternet ortamında merkezi (örn. Redis) rate limiting, CAPTCHA/anti-spam, audit log, düzenli yedekleme, izleme, gizlilik/aydınlatma metinleri ve KVKK kapsamına uygun saklama-silme süreçleri gerekir.
- SQLite yerel/geliştirme için uygundur. Eş zamanlı kullanım yüksekse PostgreSQL'e geçin.
- `/uzman` adresinin varlığını saklamak güvenlik değildir. Güvenliği parola, yetkilendirme ve oturum kontrolleri sağlar.
- Yerel niyet sınıflandırması hatasız değildir: yüksek riskli taleplerde insan denetimi ve otomatik testler gerekir.
- Şu an müşteri kimlik hesabı, e-posta bildirimi, dosya yükleme, SSS düzenleme paneli ve kapsamlı sohbet geçmişi YOKTUR; sonraki sürümlerde eklenebilir.
- Uzman talebine ilişkin gizli takip anahtarı müşterinin tarayıcısında (`localStorage`) tutulur. Tarayıcı verisi silinirse müşteri o anahtarı yitirir.
- Altı SSS girdisi önceden eklenmiştir. Yeni SSS eklenirse, `local_ai.py` niyet kuralları da genişletilmelidir. Uzman yanıtları saklanır, güvenlik nedeniyle otomatik olarak bilgi bankasına alınmaz.
