import re
import unicodedata


def normalize(text):
    """
    Metni karşılaştırmaya uygun hale getirir.

    Örnek:
    SİPARİŞİMİ NASIL İPTAL EDERİM?
    siparisimi nasil iptal ederim
    """

    text = text.casefold()

    text = text.replace("ı", "i")

    text = unicodedata.normalize("NFD", text)

    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(r"[^a-z0-9\s]", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def contains_any(text, words):
    """
    Verilen kelimelerden herhangi birinin
    metinde bulunup bulunmadığını kontrol eder.
    """

    tokens = text.split()

    return any(
        token.startswith(word)
        for token in tokens
        for word in words
    )


def choose(question, faq):
    """
    Kullanıcının sorusunu analiz eder.

    SSS ile eşleşme bulunursa ilgili kaydı döndürür.

    Eşleşme bulunamazsa None döndürür.
    """

    question = normalize(question)

    if not question:
        return None

    # 1. Birebir eşleşme

    for item in faq:

        if normalize(item["soru"]) == question:
            return item

    # 2. Bilgi bankasında bulunmayan konular

    unknown_topics = [
        "fiyat",
        "ucret",
        "indirim",
        "kampanya",
        "kupon",
        "garanti",
        "stok",
        "taksit",
        "fatura",
        "kargo ucreti",
        "iade suresi",
        "para iadesi",
        "teslim tarihi",
        "takip numarasi",
        "siparis numarasi",
        "yurt disi",
    ]

    if any(
        topic in question
        for topic in unknown_topics
    ):
        return None

    # 3. Kişisel sipariş sorunları

    personal_questions = [
        "siparisim nerede",
        "siparisim neden",
        "siparisim gelmedi",
        "siparisim gecikti",
        "kargom nerede",
        "kargom gelmedi",
        "odeme neden",
        "neden iptal edildi",
        "param neden",
    ]

    if any(
        phrase in question
        for phrase in personal_questions
    ):
        return None

    # 4. SSS kategorileri

    matches = []

    # Alışveriş yapma

    if (
        contains_any(
            question,
            ["alisveris", "sepet", "satin"]
        )
        and contains_any(
            question,
            ["nasil", "yap", "ekle", "al"]
        )
    ):
        matches.append(0)

    # Sipariş oluşturma

    if (
        contains_any(question, ["siparis"])
        and contains_any(question, ["ver", "olustur"])
    ):
        matches.append(0)

    # Sipariş durumu öğrenme

    if (
        contains_any(question, ["siparis"])
        and contains_any(
            question,
            ["durum", "takip", "sorgula", "ogren"]
        )
    ):
        matches.append(1)

    # Sipariş iptal etme

    if (
        contains_any(question, ["siparis"])
        and contains_any(
            question,
            ["iptal", "vazgec"]
        )
    ):
        matches.append(2)

    # Hasarlı ürün

    if contains_any(
        question,
        ["hasar", "kirik", "bozuk", "ezik", "kusurlu"]
    ) and contains_any(
        question,
        ["urun", "siparis", "kargo", "gel", "teslim"]
    ):
        matches.append(3)

    # Teknik destek

    if (
        contains_any(
            question,
            ["teknik", "destek", "musteri"]
        )
        and contains_any(
            question,
            ["ulas", "iletis", "ara", "telefon", "nasil"]
        )
    ):
        matches.append(4)

    # Teslimat yöntemini değiştirme

    if (
        contains_any(
            question,
            ["teslimat", "kargo", "gonderim"]
        )
        and contains_any(
            question,
            ["degis", "sec", "yontem", "tercih"]
        )
    ):
        matches.append(5)

    # 5. Karar mekanizması

    matches = set(matches)

    if len(matches) != 1:
        return None

    index = matches.pop()

    # Kişiye özel iptal işlemleri uzmana gönderilir.

    if index == 2:

        if contains_any(
            question,
            ["edermisiniz", "edin", "gerceklestir"]
        ):
            return None

    if index >= len(faq):
        return None

    return faq[index]