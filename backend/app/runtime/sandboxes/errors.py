from __future__ import annotations

from pydantic_ai.workspaces import WorkspaceUnavailableError


class SandboxUnavailable(RuntimeError):
    """沙箱创建或连接失败。"""


class LockBusy(Exception):
    """工作区锁被其他操作占用。"""


class SandboxMissingError(Exception):
    """会话还没有活跃沙箱。"""


class SandboxPathError(Exception):
    """目标路径超出沙箱工作目录。"""


class SandboxFileTooLargeError(Exception):
    """文件超过接口允许的大小。"""


class SandboxTargetIsDirectoryError(Exception):
    """读取目标是目录。"""


class SandboxReadError(Exception):
    """读取文件或目录失败。"""


class SandboxWriteError(Exception):
    """写入文件失败。"""


def is_workspace_unavailable(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, WorkspaceUnavailableError):
            return True
        current = current.__cause__
    return False
