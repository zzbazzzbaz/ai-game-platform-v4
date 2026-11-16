from __future__ import annotations

from pydantic import BaseModel, Field


class FileEntryOut(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None


class FileListOut(BaseModel):
    root: str = ""
    path: str = ""
    sandbox: str | None = None
    entries: list[FileEntryOut] = Field(default_factory=list)


class UploadOut(BaseModel):
    path: str
    size: int


class PreviewOut(BaseModel):
    url: str
