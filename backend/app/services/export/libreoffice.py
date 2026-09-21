"""LibreOffice Headless 封装：DOCX -> PDF。

依赖缺失时抛出 ``EXPORT_DEPENDENCY_MISSING``（503），
转换失败时抛出 ``EXPORT_FAILED``（500），两者都会被记录到导出记录中。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError, ErrorCode

WINDOWS_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)
POSIX_CANDIDATES = (
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


def find_soffice() -> str | None:
    override = (settings.libreoffice_bin or "").strip()
    if override:
        candidate = Path(override)
        if candidate.exists():
            return str(candidate)
        return shutil.which(override)

    for name in ("soffice", "soffice.exe", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found

    for candidate in (*WINDOWS_CANDIDATES, *POSIX_CANDIDATES):
        if Path(candidate).exists():
            return candidate
    return None


def is_available() -> bool:
    return find_soffice() is not None


def convert_to_pdf(docx_path: Path, output_dir: Path, *, timeout: int | None = None) -> Path:
    binary = find_soffice()
    if binary is None:
        raise AppError(
            ErrorCode.EXPORT_DEPENDENCY_MISSING,
            "未找到 LibreOffice（soffice），无法生成 PDF。",
            details={"hint": "安装 LibreOffice 后重启后端，或在 .env 中设置 LIBREOFFICE_BIN。"},
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = settings.storage_dir / "libreoffice-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    command = [
        binary,
        "--headless",
        "--norestore",
        "--nolockcheck",
        f"-env:UserInstallation={profile_dir.as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(docx_path),
    ]
    effective_timeout = timeout or settings.libreoffice_timeout_seconds
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            ErrorCode.EXPORT_FAILED,
            "PDF 转换超时。",
            details={"timeoutSeconds": effective_timeout},
        ) from exc
    except OSError as exc:
        raise AppError(
            ErrorCode.EXPORT_DEPENDENCY_MISSING,
            "无法启动 LibreOffice。",
            details={"reason": str(exc)},
        ) from exc

    if completed.returncode != 0:
        raise AppError(
            ErrorCode.EXPORT_FAILED,
            "LibreOffice 转换失败。",
            details={"returncode": completed.returncode, "stderr": completed.stderr[-500:]},
        )

    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    if not pdf_path.exists():
        raise AppError(
            ErrorCode.EXPORT_FAILED,
            "LibreOffice 未生成 PDF 文件。",
            details={"stdout": completed.stdout[-500:]},
        )
    return pdf_path
