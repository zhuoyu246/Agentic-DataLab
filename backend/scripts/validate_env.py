#!/usr/bin/env python3
"""
Validate environment variables before starting the application.
Ensures all required configuration is present.
"""
import sys
from pathlib import Path

def validate_env():
    """Validate required environment variables."""
    errors = []

    env_file = Path('.env')
    if not env_file.exists():
        print("⚠️  Warning: .env file not found. Using defaults.")
        return True

    required_vars = {
        'JWT_SECRET_KEY': 'Must be set to a secure random key (min 32 chars)',
    }

    env_content = env_file.read_text()

    for var, description in required_vars.items():
        if var not in env_content:
            errors.append(f"Missing {var}: {description}")
        elif f"{var}=your-secret-key" in env_content or f"{var}=change-this" in env_content:
            errors.append(f"{var} uses default insecure value: {description}")

    if errors:
        print("❌ Environment validation failed:\n")
        for error in errors:
            print(f"  • {error}")
        print("\nRun: python backend/scripts/generate_secret.py")
        return False

    print("✅ Environment validation passed")
    return True


if __name__ == '__main__':
    sys.exit(0 if validate_env() else 1)
