from __future__ import annotations

import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main() -> None:
    config_path = pathlib.Path.home() / ".aliyun" / "config.json"
    data = json.loads(config_path.read_text())
    profile_name = os.environ.get("ALIYUN_PROFILE", "OAuthProfile")
    profile = next(
        (item for item in data.get("profiles", []) if item.get("name") == profile_name),
        None,
    )
    if profile is None:
        raise SystemExit(f"找不到阿里云 profile：{profile_name}")
    key_id = profile.get("access_key_id", "")
    key_secret = profile.get("access_key_secret", "")
    token = profile.get("sts_token", "")
    if not key_id or not key_secret or not token:
        raise SystemExit("该 profile 不是 STS/OAuth 凭证，缺少 access_key 或 sts_token")

    env_path = ROOT / ".env"
    text = env_path.read_text()
    for key, value in {
        "OSS_ACCESS_KEY_ID": key_id,
        "OSS_ACCESS_KEY_SECRET": key_secret,
        "OSS_SECURITY_TOKEN": token,
    }.items():
        if re.search(rf"^{key}=.*$", text, re.MULTILINE):
            text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.MULTILINE)
        else:
            text += f"\n{key}={value}\n"
    env_path.write_text(text)
    print(f"已刷新 {env_path} 中的 OSS STS 凭证（profile={profile_name}）")


if __name__ == "__main__":
    main()
