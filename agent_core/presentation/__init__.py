"""终端输出组件的公开入口。
Public entry point for terminal presentation components.
"""

from .streaming import ConsoleStreamRenderer, configure_console_utf8

__all__ = ["ConsoleStreamRenderer", "configure_console_utf8"]
