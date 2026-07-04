from __future__ import annotations


def main() -> int:
    try:
        from .app import main as run
    except ImportError:
        from app import main as run
    return run()

__all__ = ["main"]
