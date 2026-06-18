import pytest
from core.security import validate_password_strength, hash_password, verify_password


def test_password_validation_length():
    is_valid, msg = validate_password_strength("Short1!")
    assert not is_valid
    assert "12 characters" in msg


def test_password_validation_uppercase():
    is_valid, msg = validate_password_strength("lowercase123!")
    assert not is_valid
    assert "uppercase" in msg


def test_password_validation_lowercase():
    is_valid, msg = validate_password_strength("UPPERCASE123!")
    assert not is_valid
    assert "lowercase" in msg


def test_password_validation_digit():
    is_valid, msg = validate_password_strength("NoDigits!@#$")
    assert not is_valid
    assert "digit" in msg


def test_password_validation_special():
    is_valid, msg = validate_password_strength("NoSpecial123")
    assert not is_valid
    assert "special character" in msg


def test_password_validation_weak():
    is_valid, msg = validate_password_strength("Password123!")
    assert not is_valid
    assert "common" in msg


def test_password_validation_strong():
    is_valid, msg = validate_password_strength("MySecure123!Pass")
    assert is_valid
    assert msg == ""


def test_password_hashing():
    password = "TestPass123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPass123!", hashed)
