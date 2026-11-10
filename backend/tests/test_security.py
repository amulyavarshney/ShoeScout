from app.security.secrets import decrypt_secret, encrypt_secret, mask, redact
from app.security.auth import hash_password
from argon2 import PasswordHasher


def test_encrypt_roundtrip_and_aad():
    ct, nonce = encrypt_secret("sk-abcdefghijklmnop", aad="openai")
    assert decrypt_secret(ct, nonce, aad="openai") == "sk-abcdefghijklmnop"
    try:
        decrypt_secret(ct, nonce, aad="elevenlabs")
        assert False, "AAD mismatch must fail"
    except Exception:
        pass


def test_mask_and_redact():
    assert mask("sk-abcdefghijklmnop") == "mnop"
    assert mask("short") == "****"
    assert "sk-abcdefghijklmnop" not in redact("error with sk-abcdefghijklmnop inside", ["sk-abcdefghijklmnop"])


def test_argon2id_hash():
    h = hash_password("pw")
    assert h.startswith("$argon2id$")
    assert PasswordHasher().verify(h, "pw")
