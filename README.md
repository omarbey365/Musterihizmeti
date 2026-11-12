Destek Merkezi
Destek Merkezi, Python ve FastAPI ile geliştirilmiş, SSS tabanlı otomatik yanıtları uzman destek görüşmeleriyle birleştiren bir müşteri hizmetleri uygulamasıdır.

Sistem, tanımlı sık sorulan soruları otomatik yanıtlar. Uygun yanıt bulunamadığında bir destek görüşmesi açar. Uzmanlar müşteriyle mesajlaşabilir, görüşmeleri sonlandırabilir ve genel kullanıma uygun bilgileri onaylayarak bilgi bankasına ekleyebilir.
Not: Bu sürümdeki "yapay zekâ" bileşeni, kurallı soru eşleştirme ve onaylı bilgi bankasında metin benzerliği aramasına dayanır. Bir dil modeli kendi kendine yeniden eğitilmez.

Özellikler
- Türkçe büyük/küçük harf ve karakter farklılıklarına duyarlı olmayan soru normalleştirme
- sss.json üzerinden otomatik SSS yanıtları
- Yanıtlanamayan sorular için uzman görüşmesi oluşturma
- Müşteri–uzman arasında çok mesajlı görüşmeler ve konuşma geçmişi
- Açık görüşmelerde yaklaşık 12 saniyede bir yeni mesaj kontrolü
- Görüşme durumları: Yeni, İnceleniyor, Çözüldü
- Görüşme sonlandırılırken uzmanın bilgi bankasına ekle / ekleme kararı vermesi
- Onaylı genel soru-cevapların SQLite bilgi bankasında tutulması
- Kapatılmış görüşmeleri müşteriye salt okunur gösterme; sunucu tarafında yeni mesajı reddetme
- Uzman panelinde kaydırılabilir görüşme ve geçmiş soru listeleri
- Uzman panelinde yerleşik kullanım kılavuzu
- Oturum tabanlı uzman girişi ve CSRF kontrolü
Kullanılan teknolojiler
- Backend: Python, FastAPI, Uvicorn
- Veritabanı: SQLite
- Arayüz: HTML, CSS, JavaScript, Jinja2
- Yapılandırma: python-dotenv
Proje yapısı
destek_portali/
├── app.py                  # API, oturum, görüşmeler ve bilgi bankası
├── local_ai.py             # SSS soru eşleştirme kuralları
├── text_normalizer.py      # Türkçe metin normalleştirme (kullanılıyorsa)
├── setup.py                # İlk yönetici yapılandırması
├── sss.json                # Başlangıç soru-cevapları
├── templates/
│   ├── index.html          # Müşteri ekranı
│   ├── expert.html         # Uzman ana paneli ve kullanım kılavuzu
│   ├── conversation.html   # Uzman görüşme ekranı
│   └── login.html          # Uzman giriş ekranı
└── static/
    ├── style.css           # Müşteri arayüzü
    ├── expert.css          # Uzman arayüzü
    └── main.js             # Müşteri mesajlaşması
destek.db ve .env çalışma sırasında yerel ortamda kullanılır; GitHub'a yüklenmemelidir.
Kurulum
Gereksinim: Python 3.10 veya üzeri önerilir.
1. Depoyu klonlayın:
   git clone https://github.com/KULLANICI_ADI/DEPO_ADI.git
   cd DEPO_ADI
2. Sanal ortam oluşturup etkinleştirin:
   Windows (PowerShell):
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   Linux/macOS:
   python3 -m venv .venv
   source .venv/bin/activate
3. Bağımlılıkları yükleyin:
   pip install fastapi uvicorn jinja2 python-multipart python-dotenv itsdangerous
   Projede bir requirements.txt varsa tercih edilen yöntem pip install -r requirements.txt komutudur.
4. Yönetici hesabını ve ortam ayarlarını hazırlayın:
   python setup.py
   setup.py ilk kurulum için .env oluşturuyorsa ekrandaki yönlendirmeleri izleyin. Mevcut kurulumda kullanılan .env dosyasını gereksiz yere yeniden oluşturmayın.
5. Uygulamayı başlatın:
   uvicorn app:app --reload
6. Tarayıcıda açın:
   - Müşteri ekranı: http://127.0.0.1:8000/
   - Uzman girişi: http://127.0.0.1:8000/uzman
--reload geliştirme içindir; üretim ortamında kullanılmamalıdır.
Kullanım akışı
1. Müşteri sorusunu destek asistanına gönderir.
2. Sistem önce SSS kayıtlarını, ardından aktif ve uzman onaylı bilgi bankasını kontrol eder.
3. Uygun yanıt bulunamazsa yeni bir destek görüşmesi açılır.
4. Uzman giriş yapar, görüşmeyi açar ve müşteriyle mesajlaşır.
5. Sorun çözüldüğünde Görüşmeyi Sonlandır seçeneğine basar.
6. Uzman, konuşmadan elde edilen genel bilginin tekrar kullanılmasına izin verip vermeyeceğini seçer. Öğret seçeneğinde soru ve cevabı kontrol ederek onaylar.
7. Sonlandırılan görüşme müşteri tarafından görüntülenebilir ancak aynı görüşmeye yeni mesaj gönderilemez.
Bilgi bankası nasıl çalışır?
Onaylanan soru-cevaplar knowledge_base tablosuna kaydedilir. Yeni sorular bu kayıtlarla karşılaştırılır. Bu yaklaşım, otomatik yanıt kapsamını zaman içinde artırabilir; ancak anlamsal olarak eşdeğer her soruyu bulacağı garanti değildir. Yanlış, eski veya kişisel bilgi içeren cevaplar bilgi bankasına eklenmemelidir.
Güvenlik ve gizlilik
- .env dosyasını, destek.db veritabanını, yedekleri ve gerçek müşteri verilerini GitHub'a eklemeyin.
- Kullanıcıya özel destek erişim anahtarları tarayıcıda tutulduğu için ortak cihazlarda gizlilik riski oluşabilir.
- Bu proje geliştirme/demonstrasyon amaçlıdır. İnternete açılmadan önce HTTPS, yetkilendirme, gizlilik ve veri saklama politikaları, denetim kayıtları ve güvenlik testleri değerlendirilmelidir.
- Uzman onayı, kaydedilen bilginin otomatik olarak doğru veya kişisel verilerden arındırılmış olduğu anlamına gelmez.
Önerilen .gitignore:
.env
.venv/
__pycache__/
*.py[cod]
*.db
*.db-shm
*.db-wal
*.sqlite
*.sqlite3
*.log
.pytest_cache/
.vscode/
Geliştirme notları
- Daha güçlü anlam eşleştirme için ileride anlamsal arama (semantic search) eklenebilir.
- Bilgi bankası kayıtlarının listelenmesi, düzenlenmesi ve pasifleştirilmesi için ayrı bir yönetim ekranı oluşturulabilir.
- Çok kullanıcılı üretim ortamları için ayrı uzman hesapları, rol bazlı erişim ve merkezi oturum yönetimi gerekecektir.
