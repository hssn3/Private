"""Push an archive to the Railway file-manager service.

This is the part that actually saves you when a drive burns: the zip on D:\\
dies with the machine, the copy in the cloud does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from .logging_setup import log

ProgressFn = Callable[[str, float], None]

CONNECT_TIMEOUT = 15
READ_TIMEOUT = 900  # a multi-gigabyte upload on a slow link needs room


@dataclass
class UploadResult:
    ok: bool
    message: str
    removed: list[str]


class _ProgressReader:
    """File wrapper that reports progress while requests streams it.

    ``__len__`` is what requests uses to set Content-Length, so the server can
    verify it received every byte.
    """

    def __init__(self, path: Path, progress: ProgressFn | None) -> None:
        self._handle = path.open("rb")
        self._total = path.stat().st_size
        self._sent = 0
        self._progress = progress
        self._name = path.name

    def __len__(self) -> int:
        return self._total

    def read(self, size: int = -1) -> bytes:
        chunk = self._handle.read(size)
        self._sent += len(chunk)
        if self._progress and self._total:
            self._progress(
                f"آپلود {self._name} ({self._sent / 1048576:.0f} از {self._total / 1048576:.0f} مگابایت)",
                self._sent / self._total,
            )
        return chunk

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "_ProgressReader":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _base(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if cleaned and not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    return cleaned


def test_connection(url: str, token: str) -> tuple[bool, str]:
    base = _base(url)
    if not base:
        return False, "آدرس سرویس وارد نشده است"
    if not token:
        return False, "توکن وارد نشده است"
    try:
        response = requests.get(
            f"{base}/api/files",
            headers={"X-Auth-Token": token},
            timeout=(CONNECT_TIMEOUT, 30),
        )
    except requests.RequestException as exc:
        return False, f"اتصال برقرار نشد: {exc.__class__.__name__}"

    if response.status_code == 401:
        return False, "توکن نادرست است"
    if response.status_code != 200:
        return False, f"پاسخ غیرمنتظره از سرور: {response.status_code}"
    try:
        data = response.json()
    except ValueError:
        return False, "پاسخ سرور معتبر نیست - آیا آدرس درست است؟"
    return True, f"متصل شد - {len(data.get('files', []))} بکاپ روی سرور"


def upload(url: str, token: str, archive: Path, progress: ProgressFn | None = None) -> UploadResult:
    base = _base(url)
    if not base or not token:
        return UploadResult(False, "مقصد ابری پیکربندی نشده است", [])
    if not archive.exists():
        return UploadResult(False, "فایل آرشیو پیدا نشد", [])

    endpoint = f"{base}/api/upload"
    try:
        with _ProgressReader(archive, progress) as reader:
            response = requests.post(
                endpoint,
                params={"name": archive.name},
                data=reader,
                headers={
                    "X-Auth-Token": token,
                    "Content-Type": "application/zip",
                },
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
    except requests.RequestException as exc:
        log.warning("upload failed: %s", exc)
        return UploadResult(False, f"آپلود ناموفق: {exc.__class__.__name__}", [])

    if response.status_code == 401:
        return UploadResult(False, "توکن نادرست است", [])
    if response.status_code != 200:
        detail = response.text[:180]
        return UploadResult(False, f"سرور خطا داد ({response.status_code}): {detail}", [])

    try:
        data = response.json()
    except ValueError:
        return UploadResult(False, "پاسخ سرور معتبر نیست", [])

    removed = data.get("removed", []) or []
    log.info("uploaded %s (%d bytes), server removed %d old", archive.name, data.get("size", 0), len(removed))
    return UploadResult(True, "روی فضای ابری آپلود شد", removed)
