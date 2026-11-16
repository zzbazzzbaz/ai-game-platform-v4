from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.runtime.sandboxes.snapshots import SnapshotStore

ROOT = Path(__file__).resolve().parents[2]
SANDBOX_DIR = ROOT / "sandbox"
BUILD_DIR = ROOT / ".build-template"

TEAM_ID = settings.fcsandbox_team_id
REGION = settings.aliyun_region
BASE_IMAGE = (
    f"fc-e2b-registry.{REGION}.cr.aliyuncs.com/runtime-v2/base:v0.0.53"
)


def _tar_dir(src: Path, dest: Path, excludes: set[str]) -> Path:
    with tarfile.open(dest, "w:gz") as archive:
        for child in src.iterdir():
            if child.name in excludes:
                continue
            archive.add(child, arcname=child.name)
    return dest


def _tar_scripts(dest: Path) -> Path:
    with tarfile.open(dest, "w:gz") as archive:
        for script in (
            "start-services.sh",
            "prepare-workspace.sh",
            "browser-kiosk.sh",
            "ready.sh",
        ):
            archive.add(SANDBOX_DIR / script, arcname=script)
    return dest


async def _upload(prefix: str, files: dict[str, Path]) -> dict[str, str]:
    store = SnapshotStore()
    for filename, path in files.items():
        await store.put_file(f"{prefix}/{filename}", str(path))
    return {
        "game": await store.presign_get(f"{prefix}/game-template.tar.gz", expires=600),
        "skills": await store.presign_get(f"{prefix}/skills.tar.gz", expires=600),
        "scripts": await store.presign_get(f"{prefix}/scripts.tar.gz", expires=600),
    }


def _aliyun(*args: str) -> dict[str, Any]:
    command = [
        "aliyun",
        "fcsandbox",
        *args,
        "--region",
        REGION,
        "--version",
        "2026-05-09",
        "--force",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.stdout or result.stderr or "aliyun 命令失败")
    return json.loads(result.stdout)


def _build_steps(urls: dict[str, str]) -> list[dict[str, Any]]:
    game = shlex.quote(urls["game"])
    skills = shlex.quote(urls["skills"])
    scripts = shlex.quote(urls["scripts"])
    return [
        {
            "type": "RUN",
            "args": [
                (
                    "sudo apt-get update && "
                    "sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "
                    "--no-install-recommends ca-certificates curl git less procps psmisc "
                    "tar unzip xz-utils xvfb x11vnc novnc websockify "
                    "fonts-noto-cjk fonts-noto-color-emoji && "
                    "sudo rm -rf /var/lib/apt/lists/*"
                )
            ],
        },
        {
            "type": "RUN",
            "args": [
                (
                    "npm config set registry https://registry.npmjs.org && "
                    'sudo env "PATH=$PATH" npm install -g playwright@1.60.0 && '
                    'sudo env "PATH=$PATH" playwright install --with-deps chromium && '
                    "npm cache clean --force"
                )
            ],
        },
        {
            "type": "RUN",
            "args": [
                (
                    "sudo mkdir -p /opt/game-template /opt/skills /opt/sandbox && "
                    "sudo chown -R user:user /opt/game-template /opt/skills /opt/sandbox && "
                    f"curl -fsSL {game} -o /tmp/game-template.tar.gz && "
                    "tar -xzf /tmp/game-template.tar.gz -C /opt/game-template && "
                    f"curl -fsSL {skills} -o /tmp/skills.tar.gz && "
                    "tar -xzf /tmp/skills.tar.gz -C /opt/skills && "
                    f"curl -fsSL {scripts} -o /tmp/scripts.tar.gz && "
                    "tar -xzf /tmp/scripts.tar.gz -C /opt/sandbox && "
                    "cd /opt/game-template && npm ci --no-audit --no-fund && "
                    "npm cache clean --force"
                )
            ],
        },
        {
            "type": "RUN",
            "args": [
                (
                    "sudo chmod +x /opt/sandbox/*.sh && "
                    "sudo mkdir -p /home/user/workspace /home/user/input "
                    "/home/user/.cache /tmp/.X11-unix && "
                    "sudo chmod 1777 /tmp/.X11-unix && "
                    "sudo chown -R user:user /home/user/workspace /home/user/input "
                    "/home/user/.cache /opt/game-template && "
                    "ln -sfn /opt/ms-playwright /home/user/.cache/ms-playwright"
                )
            ],
        },
    ]


def main() -> None:
    name = os.environ.get("SANDBOX_TEMPLATE_NAME", "").strip()
    if not name:
        name = f"ai-game-platform-sbx-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    print(f"构建模板：{name}")
    print("规格：1 vCPU / 1024 MB")
    print(f"基础镜像：{BASE_IMAGE}")

    BUILD_DIR.mkdir(exist_ok=True)
    game_tar = _tar_dir(
        SANDBOX_DIR / "game-template",
        BUILD_DIR / "game-template.tar.gz",
        {"node_modules", ".runtime", "dist", ".git"},
    )
    skills_tar = _tar_dir(
        SANDBOX_DIR / "assets" / "skills",
        BUILD_DIR / "skills.tar.gz",
        set(),
    )
    scripts_tar = _tar_scripts(BUILD_DIR / "scripts.tar.gz")

    prefix = f"{settings.oss_prefix.strip('/')}/build/{name}"
    try:
        urls = asyncio.run(
            _upload(
                prefix,
                {
                    "game-template.tar.gz": game_tar,
                    "skills.tar.gz": skills_tar,
                    "scripts.tar.gz": scripts_tar,
                },
            )
        )
        print("构建文件已上传 OSS")

        body = {
            "name": name,
            "teamID": TEAM_ID,
            "runtimeConfig": {
                "cpu": 1.0,
                "memorySize": 1024,
                "diskSize": 15360,
                "internetAccess": True,
                "sandboxConfig": {
                    "generation": 2,
                    "image": BASE_IMAGE,
                    "steps": _build_steps(urls),
                },
            },
        }
        created = _aliyun("CreateTemplate", "--body", json.dumps(body))
        template_id = created.get("templateID")
        if not template_id:
            raise SystemExit(f"创建模板失败：{created}")
        print(f"templateID={template_id}，等待构建...")

        deadline = time.time() + 1800
        while True:
            got = _aliyun(
                "GetTemplate",
                "--teamID",
                TEAM_ID,
                "--templateID",
                template_id,
            )
            status = got.get("status", {})
            state = status.get("state")
            print(f"{datetime.now(UTC).strftime('%H:%M:%S')} {state}")
            if state == "ready":
                break
            if state == "error":
                reason = status.get("reason", {})
                raise SystemExit(f"模板构建失败：{reason.get('message', reason)}")
            if time.time() > deadline:
                raise SystemExit("模板构建超时")
            time.sleep(10)

        print("模板构建完成")
        print(f"TEMPLATE_ID={template_id}")
        print("把 TEMPLATE_ID 写入 .env 的 E2B_TEMPLATE。")
    finally:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
