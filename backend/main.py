try:
    from app import app
except ModuleNotFoundError:
    from backend.app import app

__all__ = ["app"]
