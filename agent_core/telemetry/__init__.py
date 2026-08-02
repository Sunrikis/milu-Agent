"""遥测与用量记录的公开入口。
Public entry point for telemetry and usage accounting.
"""

from .token_usage import TokenUsageRecorder

__all__ = ["TokenUsageRecorder"]
