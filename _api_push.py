#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过 GitHub Contents API 推送初始提交（绕开 github.com:443 git 协议被墙、且空仓库 Git DB API 不可用的问题）。
api.github.com 可达即可。首个文件自动初始化 main 分支。
"""
import subprocess, base64, json, os

REPO = "homjanon/guzidi-bank-tracker"
ROOT = r"C:\Users\ho\WorkBuddy\guzidi-bank-tracker"
EXCLUDE_DIRS = {".git"}


def gh_api(method, path, data=None):
    cmd = ["gh", "api", "-X", method, path]
    if data is not None:
        cmd += ["--input", "-"]
        p = subprocess.run(cmd, input=json.dumps(data).encode("utf-8"),
                           capture_output=True)
    else:
        p = subprocess.run(cmd, capture_output=True)
    out = p.stdout.decode("utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"{method} {path} -> {p.returncode}: {out or p.stderr.decode()}")
    return json.loads(out) if out.strip() else {}


def main():
    files = []
    for dp, dn, fns in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in EXCLUDE_DIRS]
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            files.append((rel, full))
    print(f"待推送文件：{len(files)}")

    ok = 0
    for rel, full in files:
        with open(full, "rb") as fh:
            raw = fh.read()
        content = base64.b64encode(raw).decode("ascii")
        body = {
            "message": f"add {rel}",
            "content": content,
            "branch": "main",
        }
        try:
            gh_api("PUT", f"/repos/{REPO}/contents/{rel}", body)
            ok += 1
            print(f"  ✓ {rel}  ({len(raw)}B)")
        except RuntimeError as e:
            print(f"  ✗ {rel}: {e}")
    print(f"\n✅ 已推送 {ok}/{len(files)} 个文件 -> https://github.com/{REPO}")


if __name__ == "__main__":
    main()
