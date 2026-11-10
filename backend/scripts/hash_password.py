"""CLI: print an Argon2id hash for ADMIN_PASSWORD_HASH. Usage: python -m scripts.hash_password <password>"""
import sys

from app.security.auth import hash_password

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m scripts.hash_password <password>", file=sys.stderr)
        sys.exit(1)
    print(hash_password(sys.argv[1]))
