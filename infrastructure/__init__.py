"""Local persistence implementations; domain modules never import this package.

本地持久化实现；domain 不依赖基础设施。
"""

from infrastructure.sqlite_execution import SQLiteExecutionRepository, SQLiteAttemptClaims, VersionConflict

__all__ = ["SQLiteExecutionRepository", "SQLiteAttemptClaims", "VersionConflict"]
