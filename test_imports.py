"""Quick import test to verify module structure (no external deps needed)."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

print("Testing imports...")

try:
    # Core modules that don't need external deps
    from infrastructure.common.circuit_breaker import CircuitBreaker, CircuitState
    print("✅ Circuit breaker imported")

    from infrastructure.common.deduplicator import QuoteDeduplicator
    print("✅ Deduplicator imported")

    from infrastructure.common.shutdown import GracefulShutdown
    print("✅ Shutdown handler imported")

    # Config (needs dotenv but should have fallback)
    try:
        from config import SETTINGS
        print("✅ Config imported")
    except Exception as e:
        print(f"⚠️  Config import warning (expected if deps not installed): {e}")

    print("\n" + "="*50)
    print("Core module structure is valid!")
    print("Install dependencies to test full functionality:")
    print("  pip install -r requirements.txt")
    print("="*50)

except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
