#!/usr/bin/env python3
"""
JWT Secret Key Generator

Generates a cryptographically secure random key for JWT token signing.
Run this script and copy the output to your .env file.

Usage:
    python backend/scripts/generate_secret.py
"""
import secrets
import sys


def generate_secret_key(length: int = 32) -> str:
    """
    Generate a cryptographically secure random secret key.

    Args:
        length: Number of bytes for the secret (default: 32)

    Returns:
        URL-safe base64-encoded secret key
    """
    return secrets.token_urlsafe(length)


def main():
    print("=" * 70)
    print("JWT Secret Key Generator")
    print("=" * 70)
    print()

    # Generate a 32-byte (256-bit) secret key
    secret_key = generate_secret_key(32)

    print("Your new JWT secret key:")
    print()
    print(f"  {secret_key}")
    print()
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Copy the key above")
    print("2. Open your backend/.env file")
    print("3. Update the JWT_SECRET_KEY line:")
    print(f"   JWT_SECRET_KEY={secret_key}")
    print()
    print("⚠️  Keep this key secret! Never commit it to version control.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
