"""Set up local secrets and administrator login without committing them to source control."""
from getpass import getpass
import hashlib
import os
from pathlib import Path
import secrets

out = Path(__file__).resolve().parent / '.env'
if out.exists():
    raise SystemExit('.env zaten mevcut. Mevcut anahtarları korumak için üzerine yazılmadı.')
name = input('Uzman kullanıcı adı [uzman]: ').strip() or 'uzman'
password = getpass('Uzman parolası (en az 12 karakter): ')
if len(password) < 12:
    raise SystemExit('Parola en az 12 karakter olmalıdır.')
salt = secrets.token_bytes(16)
digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 400_000)
password_hash = f'{salt.hex()}:{digest.hex()}'
secret = secrets.token_urlsafe(48)
rows = {
    'SESSION_SECRET': secret,
    'ADMIN_USERNAME': name,
    'ADMIN_PASSWORD_HASH': password_hash,
    'OPENAI_API_KEY': '',
    'OPENAI_MODEL': 'gpt-5-mini',
    'COOKIE_SECURE': 'false',
}
# Quote to avoid .env parsing issues.
out.write_text(''.join(f'{k}="{v}"\n' for k, v in rows.items()), encoding='utf-8')
try:
    os.chmod(out, 0o600)
except OSError:
    pass
print('Kurulum tamamlandı. .env dosyası oluşturuldu. API anahtarını isterseniz buraya ekleyin.')
