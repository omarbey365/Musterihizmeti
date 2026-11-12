from pathlib import Path
from getpass import getpass
import hashlib
import secrets

env_path = Path(__file__).resolve().parent / ".env"

if not env_path.exists():
    raise SystemExit(".env dosyası bulunamadı!")

password = getpass("Yeni uzman parolası (en az 12 karakter): ")

if len(password) < 12:
    raise SystemExit("Parola en az 12 karakter olmalıdır.")

salt = secrets.token_bytes(16)

digest = hashlib.pbkdf2_hmac(
    "sha256",
    password.encode(),
    salt,
    400_000
)

password_hash = f"{salt.hex()}:{digest.hex()}"

lines = env_path.read_text(encoding="utf-8").splitlines()

updated = False

for i, line in enumerate(lines):
    if line.startswith("ADMIN_PASSWORD_HASH="):
        lines[i] = f'ADMIN_PASSWORD_HASH="{password_hash}"'
        updated = True
        break

if not updated:
    raise SystemExit("ADMIN_PASSWORD_HASH bulunamadı!")

env_path.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print("Uzman parolası başarıyla değiştirildi!")