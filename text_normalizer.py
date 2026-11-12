import re
import unicodedata


TURKISH_CHARACTER_MAP = str.maketrans({
    "ı": "i",
    "ğ": "g",
    "ü": "u",
    "ş": "s",
    "ö": "o",
    "ç": "c"
})


def normalize_turkish(text: str) -> str:
    """
    Türkçe metinleri karşılaştırılabilir hâle getirir.

    - Büyük/küçük harf farklarını kaldırır.
    - Türkçe karakter farklarını giderir.
    - Noktalama işaretlerini temizler.
    - Fazla boşlukları kaldırır.
    """

    if not isinstance(text, str):
        return ""

    text = unicodedata.normalize("NFKC", text)

    # Türkçe I / İ dönüşümleri
    text = text.replace("İ", "i")
    text = text.replace("I", "ı")

    text = text.lower()

    text = text.translate(TURKISH_CHARACTER_MAP)

    text = re.sub(r"[^a-z0-9\s]", " ", text)

    return " ".join(text.split())