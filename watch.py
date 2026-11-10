"""
自動デプロイ用の見張り番 (Pythonだけ・標準ライブラリだけ)

VSCodeで build.py / channels.json / pages/ の中身を保存すると、
  1. python build.py を実行して index.html を作り直す
  2. git add → git commit
  3. git push  → GitHub Pages が自動で更新される
  4. 公開サイトに新しい版が出たのを確認したら「サイトが更新されました」と表示する
を自動でやる。

さらに、GitHub 側もずっと見張る:
  ・起動したとき、GitHub と手元を比べて、違いがあれば自動で合わせる
      - GitHub側に新しい変更 (別のPCや GitHub の画面での編集)  → 取り込む。必要なら index.html も作り直す
      - 手元だけにある変更 (まだ送っていない保存・記録)       → GitHub に送る
      - 違いがなければ「差はありません」と出して、何もしない
  ・動いている間も REMOTE_EVERY 秒ごとに GitHub 側を見に行き、変わっていたら同じように取り込む
  ・同じファイルの同じ場所を両方で変えて食い違ったときは、手元の内容を優先する
    (どうしても合わせられないときは、元の状態に戻して理由を表示する。手元のファイルは消えない)
  ・起動時に、公開サイトの版も手元と同じか確認する

使い方 (VSCodeのターミナルで):
  python watch.py          ... 見張りを始める。止めるときは Ctrl+C
  python watch.py --now    ... 起動直後に、変更がなくても1回 index.html を作り直して反映してから見張る

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
# GIT_TERMINAL_PROMPT=0: パスワード入力待ちで見張り番が止まらないようにする
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "GIT_TERMINAL_PROMPT": "0"}

# 見張る対象 (index.html は build.py が作る側なので見張らない)
WATCH = ["build.py", "channels.json", "site_data.json", "home.txt", "fukyou.txt", "dev_password.txt", "env.txt", "pages", "siryou"]

INTERVAL = 1.0  # 変更を調べる間隔 (秒)
QUIET = 2.0     # 最後の変更からこの秒数おとなしくなったら反映する

REMOTE_EVERY = 30  # GitHub側に新しい変更がないか見に行く間隔 (秒)

# GitHub側から取り込んだファイルのうち、これらが変わったときは index.html を作り直して確かめる
SOURCE_NAMES = ("build.py", "channels.json", "site_data.json", "home.txt", "fukyou.txt")
SOURCE_DIRS = ("pages/", "siryou/")

# 公開サイトのURL。空なら git の送り先 (origin) から自動で決める
# (例: https://github.com/xdnet311491/xdnet311491.github.io.git → https://xdnet311491.github.io/)
SITE_URL = ""
LIVE_EVERY = 5      # 公開サイトを見に行く間隔 (秒)
LIVE_TIMEOUT = 600  # この秒数まで待っても更新されなければあきらめる

_latest_build = None  # いま反映を待っている版 (新しいpushが始まったら古い待ちは終わる)
_offline = False      # GitHubに接続できない状態か (メッセージを何度も出さないための印)


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


def run(cmd, timeout=None):
    try:
        return subprocess.run(
            cmd, cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=CHILD_ENV, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "時間切れ (通信が遅い可能性)")


def out(r) -> str:
    return r.stderr.strip() or r.stdout.strip()


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


def live_build_id(base_url: str):
    """公開サイトの version.json の版を調べる。調べられなければ None"""
    try:
        req = urllib.request.Request(
            f"{base_url}version.json?t={int(time.time() * 1000)}",
            headers={"Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8")).get("build")
    except (urllib.error.URLError, ValueError, OSError):
        return None


def wait_until_live(build: str, base_url: str) -> None:
    """公開サイトの version.json が、いま送った版になるまで待つ (別スレッドで動く)"""
    deadline = time.time() + LIVE_TIMEOUT
    while time.time() < deadline:
        if _latest_build != build:
            return  # もっと新しい版を送ったので、この待ちは終わり
        if live_build_id(base_url) == build:
            log(f"✅ サイトが更新されました: {base_url}")
            return
        time.sleep(LIVE_EVERY)
    if _latest_build == build:
        log("公開サイトの更新をまだ確認できません (反映に時間がかかっているか、URLが違うかもしれません)。")


def watch_live() -> None:
    """いま手元にある版が公開サイトに出るまで、裏で待って知らせる"""
    global _latest_build
    build, base = local_build_id(), site_url()
    if build and base:
        _latest_build = build
        threading.Thread(target=wait_until_live, args=(build, base), daemon=True).start()


def startup_live_check(build: str, base: str) -> None:
    """起動時に1回、公開サイトの版が手元と同じか確かめる (別スレッドで動く)"""
    if live_build_id(base) == build:
        log("公開サイトも手元と同じ版です。")
        return
    log("公開サイトの版が手元と違います (GitHub Pages の反映待ちかもしれません)。反映を待ちます...")
    wait_until_live(build, base)


# ---------- git の小さな道具 ----------
def current_branch():
    b = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    return None if (not b or b == "HEAD") else b


def head_rev(ref: str = "HEAD"):
    r = run(["git", "rev-parse", "--verify", "-q", ref])
    return r.stdout.strip() if r.returncode == 0 else None


def is_dirty() -> bool:
    return bool(run(["git", "status", "--porcelain"]).stdout.strip())


def ahead_behind(branch: str):
    """(手元だけにある記録の数, GitHub側だけにある記録の数)。GitHub側にまだ無いブランチなら None"""
    r = run(["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"])
    if r.returncode != 0:
        return None
    try:
        a, b = r.stdout.split()
        return int(a), int(b)
    except ValueError:
        return None


def remote_changed(branch: str):
    """GitHub側のブランチが、手元が知っている状態から進んだか。通信できなければ None (中身は取り込まず、先頭の印だけ比べる)"""
    r = run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], timeout=30)
    if r.returncode != 0:
        return None
    parts = r.stdout.split()
    if not parts:
        return False
    return parts[0] != head_rev(f"origin/{branch}")


def needs_rebuild(names) -> bool:
    return any(n in SOURCE_NAMES or n.startswith(SOURCE_DIRS) for n in names)


def push_branch(branch: str) -> bool:
    # -u: 初回でも送り先 (upstream) を自動で設定して push する
    r = run(["git", "push", "-u", "origin", branch])
    if r.returncode != 0:
        log("push に失敗。GitHub側の変更を取り込んでもう一度試します...")
        # index.html はbuild.pyが作るものなので、ぶつかったらこちらの内容を優先する
        pr = run(["git", "pull", "--rebase", "-X", "theirs", "origin", branch])
        if pr.returncode != 0:
            run(["git", "rebase", "--abort"])  # 中途半端な状態を残さず元に戻す
            log("自動では取り込めませんでした。元の状態に戻してあります:")
            print(out(pr))
            return False
        r = run(["git", "push", "-u", "origin", branch])
        if r.returncode != 0:
            log("push できませんでした:")
            print(out(r))
            return False
    return True


def pull_remote(branch: str):
    """手元に保存していない変更がない状態で、GitHub側の新しい変更を取り込む。
    成功なら「変わったファイル名のリスト」、失敗なら None (失敗したときは元の状態に戻す)"""
    old = head_rev()
    pr = run(["git", "pull", "--rebase", "-X", "theirs", "origin", branch], timeout=180)
    if pr.returncode != 0:
        run(["git", "rebase", "--abort"])
        log("GitHub側の変更を自動では取り込めませんでした。元の状態に戻してあります:")
        print(out(pr))
        return None
    new = head_rev()
    if not old or not new or old == new:
        return []
    d = run(["git", "diff", "--name-only", old, new])
    return [x for x in d.stdout.splitlines() if x]


# ---------- 自動デプロイ (手元の保存 → GitHub) ----------
def deploy() -> bool:
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

    branch = current_branch()
    if not branch:
        log("Gitが「ブランチに乗っていない状態」です (rebase の途中など)。")
        log("ターミナルで  git rebase --abort  を実行してから、もう一度保存してください。")
        return False

    if not push_branch(branch):
        return False

    log("GitHubに反映しました。公開サイトの更新を待っています...")
    watch_live()
    return True


# ---------- GitHub側との比べ合わせ (起動時 + 見張り中) ----------
def sync(branch: str, first: bool = False) -> None:
    """GitHub と手元を比べて、違いがあれば自動で合わせる。違いがなければ何もしない"""
    r = run(["git", "fetch", "origin", branch], timeout=120)
    if r.returncode != 0:
        log("GitHubに接続できないので、差の確認はあとでやり直します:")
        print(out(r))
        return
    ab = ahead_behind(branch)
    if ab is None:
        if first:
            log("GitHub側にこのブランチがまだありません (初回の送信が必要です)。")
        ab = (0, 0)
    ahead, behind = ab
    dirty = is_dirty()

    if not (ahead or behind or dirty):
        if first:
            log("GitHubと手元に差はありません。")
        return

    if dirty:
        log("手元に、まだGitHubへ送っていない変更があります。送ります" + (f" (GitHub側にも新しい変更が {behind} 件あります)" if behind else "") + "...")
        deploy()   # 保存 → commit → push。GitHub側が先に進んでいたら、取り込んでからやり直す
        if behind:
            log("GitHub側の変更を取り込んだので、念のため index.html を作り直して確かめます...")
            deploy()
        return

    if behind:
        log(f"GitHub側に新しい変更が {behind} 件あります。取り込みます...")
        names = pull_remote(branch)
        if names is None:
            return
        if names:
            log(f"取り込みました ({len(names)} ファイル):")
            for n in names[:8]:
                print(f"    {n}")
            if len(names) > 8:
                print(f"    ... ほか {len(names) - 8} ファイル")
        if needs_rebuild(names):
            log("取り込んだ内容で index.html を作り直して確かめます...")
            deploy()   # 同じ内容なら「送る変更はありません」で終わる

    ab = ahead_behind(branch)
    if ab and ab[0] > 0:
        log(f"手元だけにある記録が {ab[0]} 件あります。GitHubに送ります...")
        if push_branch(branch):
            log("GitHubに反映しました。公開サイトの更新を待っています...")
            watch_live()


def check_remote() -> bool:
    """見張り中の定期確認。GitHub側に新しい変更があれば取り込んで True を返す"""
    global _offline
    branch = current_branch()
    if not branch:
        return False
    changed = remote_changed(branch)
    if changed is None:
        if not _offline:
            _offline = True
            log("GitHubに接続できません。つながるまで、手元の保存だけ見張ります。")
        return False
    if _offline:
        _offline = False
        log("GitHubにつながりました。")
    if changed:
        sync(branch)
        return True
    return False


def main() -> None:
    global _latest_build
    if shutil.which("git") is None:
        sys.exit("git が見つかりません。Gitをインストールしてください。")
    if not (BASE / ".git").exists():
        sys.exit("このフォルダはGitリポジトリではありません。先に git init と最初のpushをしてください。")

    git_dir = BASE / ".git"
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        sys.exit("Gitがrebaseの途中で止まっています。  git rebase --abort  を実行してからやり直してください。")

    branch = current_branch()
    if not branch:
        sys.exit("Gitが「ブランチに乗っていない状態」です。  git switch main  などでブランチに戻ってから、もう一度起動してください。")

    log("起動しました。GitHubと手元を比べています...")
    sync(branch, first=True)

    if "--now" in sys.argv:
        deploy()

    build, base = local_build_id(), site_url()
    if build and base:
        _latest_build = build
        threading.Thread(target=startup_live_check, args=(build, base), daemon=True).start()

    prev = snapshot()
    changed_at = None
    last_remote = time.time()
    log(f"見張り開始。保存すると自動でGitHubに反映します。GitHub側の変更も {REMOTE_EVERY} 秒ごとに確認します (Ctrl+Cで終了)")

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
                continue
            # 手元に「保存したてで、まだ反映していない変更」がないときだけ、GitHub側を見に行く
            if changed_at is None and time.time() - last_remote >= REMOTE_EVERY:
                last_remote = time.time()
                if check_remote():
                    prev = snapshot()   # 取り込みで変わったファイルを、自分の保存と勘違いしない
    except KeyboardInterrupt:
        log("終了します。")


if __name__ == "__main__":
    main()
