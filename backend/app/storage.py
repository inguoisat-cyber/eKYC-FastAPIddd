import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from .config import settings

_DIR = settings.DATA_DIR / "files"
_DIR.mkdir(exist_ok=True)


def _key() -> bytes:
    if settings.ENCRYPTION_KEY:
        return settings.ENCRYPTION_KEY.encode()
    f = settings.DATA_DIR / "fernet.key"
    try:
        with open(f, "xb") as fh:
            fh.write(Fernet.generate_key())
        f.chmod(0o600)
    except FileExistsError:
        pass
    return f.read_bytes()


_fernet = Fernet(_key())


def save(data: bytes) -> str:
    name = f"{uuid.uuid4().hex}.enc"
    (_DIR / name).write_bytes(_fernet.encrypt(data))
    return name


def load(name: str) -> bytes:
    return _fernet.decrypt((_DIR / Path(name).name).read_bytes())


def remove(*names: str | None) -> None:
    for n in names:
        if n:
            (_DIR / Path(n).name).unlink(missing_ok=True)
