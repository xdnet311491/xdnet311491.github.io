"""
自動デプロイ用の見張り番 (Pythonだけ・標準ライブラリだけ)

VSCodeで build.py / channels.json / pages/ の中身を保存すると、
  1. python build.py を実行して index.html を作り直す
  2. git add → git commit
  3. git push  → GitHub Pages が自動で更新される
  4. 公開サイトに新しい版が出たのを確認したら「サイトが更新されました」と表示する
を自動でやる。

使い方 (VSCodeのターミナルで):
  python watch.py          ... 見張りを始める。止めるときは Ctrl+C
  python watch.py --now    ... 起動直後に1回すぐ反映してから見張る

事前準備 (最初の1回だけ):
  - このフォルダがGitリポジトリで、GitHubに push できる状態にしておく
    git init / git remote add origin ... / git push -u origin main
  - git が入っていること (git --version で確認)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent

# build.py や git の出力を UTF-8 で受け取る (Windowsで日本語のエラーが文字化けしないように)
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

# 見張る対象 (index.html は build.py が作る側なので見張らない)
WATCH = ["build.py", "channels.json", "site_data.json", "home.txt", "fukyou.txt", "dev_password.txt", "env.txt", "pages", "siryou"]

INTERVAL = 1.0  # 変更を調べる間隔 (秒)
QUIET = 2.0     # 最後の変更からこの秒数おとなしくなったら反映する

# 公開サイトのURL。空なら git の送り先 (origin) から自動で決める
# (例: https://github.com/xdnet311491/xdnet311491.github.io.git → https://xdnet311491.github.io/)
SITE_URL = ""
LIVE_EVERY = 5      # 公開サイトを見に行く間隔 (秒)
LIVE_TIMEOUT = 600  # この秒数まで待っても更新されなければあきらめる

_latest_build = None  # いま反映を待っている版 (新しいpushが始まったら古い待ちは終わる)


def snapshot() -> dict:
    snap = {}
    for name in WATCH:
        p = BASE / name
        if p.is_file():
            files = [p]
        elif p.is_dir():
            files = [f for f in p.rglob("*") if f.is_file()]
        else:
            files = []
        for f in files:
            try:
                st = f.stat()
                snap[str(f)] = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
    return snap


def run(cmd):
    return subprocess.run(
        cmd, cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace", env=CHILD_ENV
    )


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def site_url():
    if SITE_URL:
        return SITE_URL.rstrip("/") + "/"
    url = run(["git", "remote", "get-url", "origin"]).stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not m:
        return None
    user, repo = m.groups()
    if repo.lower() == f"{user}.github.io".lower():
        return f"https://{user}.github.io/"
    return f"https://{user}.github.io/{repo}/"


def local_build_id():
    try:
        return json.loads((BASE / "version.json").read_text(encoding="utf-8")).get("build")
    except (OSError, ValueError):
        return None


def wait_until_live(build: str, base_url: str) -> None:
    """公開サイトの version.json が、いま送った版になるまで待つ (別スレッドで動く)"""
    deadline = time.time() + LIVE_TIMEOUT
    while time.time() < deadline:
        if _latest_build != build:
            return  # もっと新しい版を送ったので、この待ちは終わり
        try:
            req = urllib.request.Request(
                f"{base_url}version.json?t={int(time.time() * 1000)}",
                headers={"Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                if json.loads(r.read().decode("utf-8")).get("build") == build:
                    log(f"✅ サイトが更新されました: {base_url}")
                    return
        except (urllib.error.URLError, ValueError, OSError):
            pass  # まだ反映されていない / 通信できない → もう少し待つ
        time.sleep(LIVE_EVERY)
    if _latest_build == build:
        log("公開サイトの更新をまだ確認できません (反映に時間がかかっているか、URLが違うかもしれません)。")


def deploy() -> bool:
    global _latest_build
    log("変更を検知。index.html を作り直します...")
    r = run([sys.executable, "build.py"])
    if r.returncode != 0:
        log("build.py でエラー。GitHubには送りません:")
        print(r.stderr.strip() or r.stdout.strip())
        return False

    run(["git", "add", "-A"])
    if not run(["git", "status", "--porcelain"]).stdout.strip():
        log("GitHubに送る変更はありませんでした。")
        return True

    r = run(["git", "commit", "-m", f"auto: update {datetime.now():%Y-%m-%d %H:%M:%S}"])
    if r.returncode != 0:
        log("commit に失敗:")
        print(r.stderr.strip() or r.stdout.strip())
        return False

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if not branch or branch == "HEAD":
        log("Gitが「ブランチに乗っていない状態」です (rebase の途中など)。")
        log("ターミナルで  git rebase --abort  を実行してから、もう一度保存してください。")
        return False

    # -u: 初回でも送り先 (upstream) を自動で設定して push する
    r = run(["git", "push", "-u", "origin", branch])
    if r.returncode != 0:
        log("push に失敗。GitHub側の変更を取り込んでもう一度試します...")
        # index.html はbuild.pyが作るものなので、ぶつかったらこちらの内容を優先する
        pr = run(["git", "pull", "--rebase", "-X", "theirs", "origin", branch])
        if pr.returncode != 0:
            run(["git", "rebase", "--abort"])  # 中途半端な状態を残さず元に戻す
            log("自動では取り込めませんでした。元の状態に戻してあります:")
            print(pr.stderr.strip() or pr.stdout.strip())
            return False
        r = run(["git", "push", "-u", "origin", branch])
        if r.returncode != 0:
            log("push できませんでした:")
            print(r.stderr.strip() or r.stdout.strip())
            return False

    log("GitHubに反映しました。公開サイトの更新を待っています...")
    build, base = local_build_id(), site_url()
    if build and base:
        _latest_build = build
        threading.Thread(target=wait_until_live, args=(build, base), daemon=True).start()
    return True


def main() -> None:
    if shutil.which("git") is None:
        sys.exit("git が見つかりません。Gitをインストールしてください。")
    if not (BASE / ".git").exists():
        sys.exit("このフォルダはGitリポジトリではありません。先に git init と最初のpushをしてください。")

    git_dir = BASE / ".git"
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        sys.exit("Gitがrebaseの途中で止まっています。  git rebase --abort  を実行してからやり直してください。")

    if "--now" in sys.argv:
        deploy()

    prev = snapshot()
    changed_at = None
    log("見張り開始。保存すると自動でGitHubに反映します (Ctrl+Cで終了)")

    try:
        while True:
            time.sleep(INTERVAL)
            cur = snapshot()
            if cur != prev:
                prev = cur
                changed_at = time.time()
                continue
            if changed_at is not None and time.time() - changed_at >= QUIET:
                changed_at = None
                deploy()
                prev = snapshot()
    except KeyboardInterrupt:
        log("終了します。")


if __name__ == "__main__":
    main()
