"""Local cache module to replace Redis

Uses diskcache as backend, provides Redis-compatible API.
Supports persistent storage and TTL expiration.
"""

import json
import os
from typing import Any, Optional
from threading import Lock

try:
    from diskcache import Cache
    HAS_DISKCACHE = True
except ImportError:
    HAS_DISKCACHE = False


class LocalCache:
    """
    Local cache implementation with Redis-compatible API.
    Uses diskcache as backend, supports persistence and TTL.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls, cache_dir: Optional[str] = None):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, cache_dir: Optional[str] = None):
        if getattr(self, '_initialized', False):
            return

        if not HAS_DISKCACHE:
            raise ImportError(
                "diskcache not installed. Run: pip install diskcache"
            )

        if cache_dir is None:
            cache_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                ".cache",
                "local_redis"
            )

        os.makedirs(cache_dir, exist_ok=True)
        self._cache = Cache(cache_dir)
        self._initialized = True

    def set(self, name: str, value: Any, ex: Optional[int] = None) -> bool:
        """
        Set key-value pair

        Args:
            name: Key name
            value: Value (auto-serialize dict/list)
            ex: Expiration time (seconds)

        Returns:
            bool: Success status
        """
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        self._cache.set(name, value, expire=ex)
        return True

    def get(self, name: str) -> Optional[str]:
        """Get value"""
        return self._cache.get(name)

    def delete(self, name: str) -> int:
        """Delete key, returns number of deleted items"""
        return 1 if self._cache.delete(name) else 0

    def exists(self, name: str) -> bool:
        """Check if key exists"""
        return name in self._cache

    def keys(self, pattern: str = "*") -> list:
        """
        Get list of matching keys
        Note: Simplified implementation, only supports prefix and full matching
        """
        if pattern == "*":
            return list(self._cache.iterkeys())

        prefix = pattern.rstrip("*")
        return [k for k in self._cache.iterkeys() if k.startswith(prefix)]

    def expire(self, name: str, seconds: int) -> bool:
        """Set key expiration time"""
        value = self._cache.get(name)
        if value is not None:
            self._cache.set(name, value, expire=seconds)
            return True
        return False

    def ttl(self, name: str) -> int:
        """
        Get remaining time to live (seconds)
        Note: diskcache does not directly support TTL queries
        """
        if name in self._cache:
            return -1  # Exists but TTL unknown
        return -2  # Key does not exist

    def close(self):
        """Close cache connection"""
        if hasattr(self, '_cache'):
            self._cache.close()


def get_local_cache(cache_dir: Optional[str] = None) -> LocalCache:
    """Get or create the global :class:`LocalCache` singleton.

    Thread safety is handled by ``LocalCache.__new__`` which uses
    double-checked locking via ``cls._lock``, so no additional
    module-level lock is needed here.

    Note:
        The ``cache_dir`` is only used on first initialization.  Subsequent
        calls return the existing singleton regardless of the ``cache_dir``
        argument.
    """
    return LocalCache(cache_dir)
