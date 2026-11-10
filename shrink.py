"""
siryou の中の「全部のファイル」を軽くするスクリプト (リポジトリのサイズを減らすため)

  壁紙の動画 (WALLPAPERS / WALLPAPER に書いたもの) ... 高さ 1080px までに縮小して、音声を取り、再エンコード
  特殊モーション動画 (OP_MOTIONS に書いたもの)     ... 背景でぼかして出すので、強めに圧縮する (高さ 720px まで)
  ほかの動画 (.mp4 .webm .m4v .mov)                 ... 壁紙と同じ設定で軽くする
  音楽 (.mp3 .m4a .ogg .opus)                       ... 128kbps で再エンコード (もともと軽い曲はそのまま)
  画像 (.jpg .jpeg .png)                            ... 長い辺が 1920px までに縮小して再エンコード (小さい画像はそのまま)

触らないもの:
  ・入場アニメ (op.mp4) とロゴ (logo.png)
  ・下の KEEP に書いたファイル
  ・軽くなる量が 10% 未満だったファイル (むしろ劣化するだけなので)
  ・拡張子が変わってしまう形式 (.wav .flac など) と、動く画像 (.gif .webp .apng)、.svg
    → 軽くしたいときは、mp3 / mp4 などに自分で変換して、build.py のファイル名も直してください

固まりにくくするための工夫:
  ・もう軽いファイルは、重い変換をする前に調べて飛ばす (中身を見るだけなので一瞬)
  ・いちど確認したファイルは .shrink_done.json に覚えて、次回から二度と調べない (2回目以降はほぼ一瞬)
      「軽くなった」「ほとんど軽くならない」「変換に失敗した・時間切れ」のどれでも覚える。
      1ファイル終わるたびに保存するので、途中で止めても (Ctrl+C) ここまでの結果は消えない。
      判定は「ファイル名 + サイズ」だけ (更新日時は見ない)。同じ名前で中身を差し替えたらサイズが変わるので、自動で調べ直す。
  ・音楽と画像は、いくつか同時に処理する。動画は1本ずつ、進み具合(%)を表示しながら処理する
  ・ffmpeg は「PCの動作が重くならない優先度」で動かし、CPU を1つ空けておく。止まったままにならないよう時間切れもある
  ・動画の変換は preset medium (slow より数倍速い。サイズはほとんど変わらない)

元のファイルは siryou_original/ にコピーしてから置き換える (何度実行しても、最初の元ファイルは上書きしない)。
siryou_original/ は .gitignore に自動で追加するので、GitHub には上がらない。

使い方 (必要なもの: ffmpeg。ターミナルで ffmpeg -version が動くこと):
  python shrink.py            ... 軽くする
  python shrink.py --dry      ... 実際には何も変えず、どのファイルをどう扱うかだけ表示する
  python shrink.py --force    ... 前回確認したファイルも、もう一度調べ直す
  python shrink.py --restore  ... 元のファイルに戻す

★ 実行する前に python watch.py を止めておく (途中で自動デプロイされないように)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.dont_write_bytecode = True  # build.py を読むときに __pycache__ を作らない (git に入ってしまうため)
import build  # noqa: E402  (設定を読むだけ。index.html は書き出さない)

BASE = Path(__file__).resolve().parent
SIRYOU = BASE / "siryou"
BACKUP = BASE / "siryou_original"
TMP = BASE / ".shrink_tmp"
CACHE = BASE / ".shrink_done.json"

MP3_KBPS = 128         # 曲のビットレート
MP3_SKIP_BELOW = 140   # これ以下 (kbps) の曲は、もう軽いので触らない
WALL_MAX_H = 1080      # 壁紙の高さの上限 (px)
WALL_CRF = 24          # 壁紙の画質 (小さいほど高画質で重い。24 前後が目安)
# 特殊モーション動画は、ぼかして背景に出すだけなので強めに圧縮する。
# build.py の OP_MOTION_BLUR を 0 (ぼかしなし) にしている場合は、下の値を壁紙と同じにすると安心
MOTION_MAX_H = 720
MOTION_CRF = 27
WALL_SKIP_KBPS = 2000    # 高さが上限以内・音声なしで、これ以下 (kbps) の壁紙動画は、もう軽いので触らない
MOTION_SKIP_KBPS = 1200  # 特殊モーション動画の場合
IMG_MAX_SIDE = 1920      # 画像の長い辺の上限 (px)
IMG_SKIP_BELOW = 200_000 # これ以下 (バイト) の画像は、もう軽いので触らない
MIN_GAIN = 0.10          # この割合以上 軽くならなかったら、元のままにする
VIDEO_TIMEOUT = 1800     # 動画1本の変換が、この秒数を超えたらあきらめる
SMALL_TIMEOUT = 300      # 音楽・画像1つの変換の時間切れ (秒)

# 絶対に触らないファイル名を足したいときはここに書く (例: KEEP = ["op1.mp3"])
KEEP = []

IGNORE_LINES = ["siryou_original/", ".shrink_tmp/", ".shrink_done.json", "__pycache__/"]

AUDIO_CODEC = {".mp3": "libmp3lame", ".m4a": "aac", ".ogg": "libvorbis", ".opus": "libopus"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}

CPU = os.cpu_count() or 2
THREADS = max(1, CPU - 1)                 # 1つ空けておくと、PCの他の操作が固まりにくい
POOL = max(1, min(4, CPU // 2))           # 音楽・画像を同時に処理する数
LOW_PRIO = 0x00004000 if os.name == "nt" else 0   # Windows: 通常より低い優先度で動かす
FF = ["ffmpeg", "-nostdin", "-v", "error", "-y"]  # -nostdin: 入力待ちで止まらないようにする

_print_lock = None


def mb(n: int) -> str:
    return f"{n / 1_000_000:.2f}MB"


def run(cmd, timeout=None):
    """コマンドを実行して結果を返す。時間切れや起動失敗なら None"""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL, creationflags=LOW_PRIO, timeout=timeout)
    except Exception:
        return None


def probe(path: Path):
    """中身を調べる (一瞬で終わる)。読めなければ None"""
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=bit_rate,duration:stream=codec_type,height",
             "-of", "json", str(path)], timeout=60)
    if r is None or r.returncode != 0:
        return None
    try:
        d = json.loads(r.stdout)
        fmt = d.get("format", {})
        dur = float(fmt.get("duration") or 0)
        kbps = int(float(fmt.get("bit_rate") or 0)) // 1000
        if not kbps and dur > 0:
            kbps = int(path.stat().st_size * 8 / dur / 1000)
        streams = d.get("streams", [])
        height = max([int(s.get("height") or 0) for s in streams if s.get("codec_type") == "video"] or [0])
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        if not kbps:
            return None
        return {"kbps": kbps, "dur": dur, "height": height, "audio": has_audio}
    except (ValueError, TypeError):
        return None


def protected_names() -> set:
    names = set(KEEP)
    video, still = build.find_op()         # 入場アニメとロゴ
    for f in (video, still):
        if f is not None:
            names.add(f.name)
    return names


def ensure_gitignore() -> None:
    gi = BASE / ".gitignore"
    have = gi.read_text(encoding="utf-8").splitlines() if gi.is_file() else []
    add = [x for x in IGNORE_LINES if x not in have]
    if add:
        gi.write_text("\n".join(have + add) + "\n", encoding="utf-8")
        print(f".gitignore に追加しました: {', '.join(add)}")


# ---------- 「前回確認したファイル」の記録 ----------
def settings_sig() -> str:
    return f"{MP3_KBPS}/{MP3_SKIP_BELOW}/{WALL_MAX_H}/{WALL_CRF}/{MOTION_MAX_H}/{MOTION_CRF}/{IMG_MAX_SIDE}/{MIN_GAIN}"


def load_cache() -> dict:
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        if d.get("sig") == settings_sig():
            return d.get("files", {})
    except (OSError, ValueError):
        pass
    return {}


def save_cache(files: dict) -> None:
    try:
        CACHE.write_text(json.dumps({"sig": settings_sig(), "files": files}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def stamp(f: Path, kind: str) -> list:
    st = f.stat()
    return [st.st_size, st.st_mtime_ns, kind]


def is_done(rec, f: Path) -> bool:
    """いちど確認したファイルか? 名前とサイズだけで決める (更新日時や種類の判定が変わっても、もう調べ直さない)"""
    try:
        return bool(rec) and rec[0] == f.stat().st_size
    except (OSError, TypeError, IndexError):
        return False


# ---------- 変換 ----------
def encode_audio(src: Path, dst: Path) -> bool:
    """音楽を MP3_KBPS で再エンコードする (拡張子・形式はそのまま)"""
    r = run(FF + ["-i", str(src), "-map", "0:a:0", "-map_metadata", "0",
                  "-c:a", AUDIO_CODEC[src.suffix.lower()], "-b:a", f"{MP3_KBPS}k", str(dst)], timeout=SMALL_TIMEOUT)
    return r is not None and r.returncode == 0 and dst.is_file()


def encode_image(src: Path, dst: Path) -> bool:
    """画像を、長い辺が IMG_MAX_SIDE までに縮小して再エンコードする (拡張子はそのまま)"""
    scale = f"scale='min({IMG_MAX_SIDE},iw)':'min({IMG_MAX_SIDE},ih)':force_original_aspect_ratio=decrease"
    codec = ["-compression_level", "9"] if src.suffix.lower() == ".png" else ["-q:v", "4"]
    r = run(FF + ["-i", str(src), "-vf", scale, "-frames:v", "1", *codec, str(dst)], timeout=SMALL_TIMEOUT)
    return r is not None and r.returncode == 0 and dst.is_file()


def encode_video(src: Path, dst: Path, max_h: int, crf: int, dur: float, name: str) -> bool:
    """動画を、高さ max_h までに縮小して音声なしで再エンコードする (拡張子はそのまま)。進み具合を表示する"""
    if src.suffix.lower() == ".webm":
        codec = ["-c:v", "libvpx-vp9", "-crf", str(crf + 8), "-b:v", "0", "-row-mt", "1",
                 "-cpu-used", "4", "-threads", str(THREADS)]
    else:
        codec = ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p",
                 "-threads", str(THREADS), "-movflags", "+faststart"]
    cmd = FF + ["-progress", "pipe:1", "-nostats", "-i", str(src), "-an",
                "-vf", f"scale=-2:'min({max_h},ih)'", *codec, str(dst)]
    t0 = time.time()
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             text=True, encoding="utf-8", errors="replace", creationflags=LOW_PRIO)
    except OSError:
        return False
    last = -1
    for line in p.stdout:
        if line.startswith("out_time_us=") and dur > 0:
            try:
                pct = min(99, int(int(line.split("=")[1]) / 1e6 / dur * 100))
            except ValueError:
                continue
            if pct != last:
                last = pct
                print(f"\r  {name}  変換中 {pct}%  ({int(time.time() - t0)}秒)   ", end="", flush=True)
        if time.time() - t0 > VIDEO_TIMEOUT:
            p.kill()
            break
    p.wait()
    print("\r" + " " * 70 + "\r", end="", flush=True)
    return p.returncode == 0 and dst.is_file()


def restore() -> None:
    if not BACKUP.is_dir():
        sys.exit("siryou_original がありません。戻すものがありません。")
    n = 0
    for f in sorted(BACKUP.iterdir()):
        if f.is_file():
            shutil.copy2(f, SIRYOU / f.name)
            n += 1
    try:
        CACHE.unlink()   # 戻したので、次回はもう一度調べ直す
    except OSError:
        pass
    print(f"{n} 個のファイルを元に戻しました。")


def classify(f: Path, wall_names: set, motion_names: set) -> str:
    """ファイルの種類を決める: wall / motion / video / audio / image / other"""
    ext = f.suffix.lower()
    if ext in build.VIDEO_EXT:
        if f.name in motion_names:
            return "motion"
        return "wall" if f.name in wall_names else "video"
    if ext in AUDIO_CODEC:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    return "other"


LABEL = {"wall": "壁紙動画", "motion": "特殊モーション", "video": "動画", "audio": "音楽", "image": "画像", "other": "その他"}


def row(name, kind, size, after, note) -> None:
    print(f"{name:<22}{LABEL[kind]:<10}{mb(size):>10}{'→':>3}{mb(after):>10}   {note}", flush=True)


def work(f: Path, kind: str, info) -> tuple:
    """1ファイルを実際に変換して、置き換える。(元のサイズ, 変換後のサイズ, 結果の文, 記録してよいか) を返す"""
    size = f.stat().st_size
    out = TMP / f.name
    if kind == "audio":
        ok = encode_audio(f, out)
    elif kind == "image":
        ok = encode_image(f, out)
    elif kind == "motion":
        ok = encode_video(f, out, MOTION_MAX_H, MOTION_CRF, (info or {}).get("dur", 0), f.name)
    else:
        ok = encode_video(f, out, WALL_MAX_H, WALL_CRF, (info or {}).get("dur", 0), f.name)
    if not ok:
        out.unlink(missing_ok=True)
        return size, size, "⚠ 変換できなかった (時間切れなど) ので触らない。今後は飛ばします", True
    if out.stat().st_size > size * (1 - MIN_GAIN):
        out.unlink(missing_ok=True)
        return size, size, "ほとんど軽くならないので触らない", True
    if not (BACKUP / f.name).exists():
        shutil.copy2(f, BACKUP / f.name)
    after = out.stat().st_size
    shutil.move(str(out), str(f))
    return size, after, f"軽くしました (-{(1 - after / size) * 100:.0f}%)", True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true", help="元のファイルに戻す")
    ap.add_argument("--dry", action="store_true", help="何も変えず、扱いだけ表示する")
    ap.add_argument("--force", action="store_true", help="前回確認したファイルも調べ直す")
    args = ap.parse_args()

    if args.restore:
        restore()
        return
    if not args.dry and (shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None):
        sys.exit("ffmpeg / ffprobe が見つかりません。ffmpeg をインストールしてください。")
    if not SIRYOU.is_dir():
        sys.exit(f"フォルダがありません: {SIRYOU}")

    if not args.dry:
        ensure_gitignore()
        BACKUP.mkdir(exist_ok=True)
        TMP.mkdir(exist_ok=True)
    started = time.time()
    protect = protected_names()
    wall = build.find_wallpaper()
    wall_names = {str(fname) for _t, fname, _n in build._rows(build.WALLPAPERS)}
    if wall is not None:
        wall_names.add(wall.name)
    motion_names = {str(v) for v in build.OP_MOTIONS.values()}
    cache = {} if args.force else load_cache()
    new_cache = dict(cache)

    files = [f for f in sorted(SIRYOU.iterdir()) if f.is_file() and not f.name.startswith(".")]
    before = after = 0
    todo = []  # (ファイル, 種類, 中身の情報)

    print(f"{'ファイル':<22}{'種類':<10}{'元':>10}{'→':>3}{'後':>10}   結果")
    # ---- 1. まず全部を軽く調べて、変換が要らないものを先に飛ばす (ここは一瞬) ----
    for f in files:
        kind = classify(f, wall_names, motion_names)
        size = f.stat().st_size
        before += size
        note = None
        info = None
        if f.name in protect:
            note = "触らない (保護)"
        elif kind == "other":
            note = "対応していない形式なので触らない"
        elif is_done(cache.get(f.name), f):
            note = "前回確認済みなので飛ばす"
        elif kind == "image" and size <= IMG_SKIP_BELOW:
            note = "もう軽いので触らない"
        elif kind in ("audio", "wall", "motion", "video"):
            info = probe(f) if shutil.which("ffprobe") else None
            if info is None and not args.dry:
                note = "⚠ 読めないので触らない (壊れている? 中身が空?)"
            elif info is not None and kind == "audio" and info["kbps"] <= MP3_SKIP_BELOW:
                note = f"もう軽い ({info['kbps']}kbps) ので触らない"
            elif info is not None and kind != "audio":
                max_h, lim = (MOTION_MAX_H, MOTION_SKIP_KBPS) if kind == "motion" else (WALL_MAX_H, WALL_SKIP_KBPS)
                if 0 < info["height"] <= max_h and not info["audio"] and info["kbps"] <= lim:
                    note = f"もう軽い ({info['kbps']}kbps) ので触らない"
        if note is None and args.dry:
            note = "軽くする対象"
        if note is not None:
            if not args.dry and note.startswith("もう軽い"):
                new_cache[f.name] = stamp(f, kind)   # 次回から飛ばす
            after += size
            row(f.name, kind, size, size, note)
        else:
            todo.append((f, kind, info))

    if not args.dry:
        save_cache(new_cache)   # 「もう軽い」と分かったぶんは、重い変換の前に保存しておく

    # ---- 2. 変換が要るものを処理する。音楽・画像は同時に、動画は1本ずつ進み具合を出しながら ----
    if todo and not args.dry:
        small = [t for t in todo if t[1] in ("audio", "image")]
        videos = [t for t in todo if t[1] not in ("audio", "image")]
        print(f"\n変換するファイル: 動画 {len(videos)} / 音楽・画像 {len(small)}  (動画は時間がかかります。進み具合を出します)\n", flush=True)

        results = {}

        def remember(f, kind, res):   # 1ファイル終わるたびに記録して保存する
            if res[3]:
                new_cache[f.name] = stamp(f, kind)
                save_cache(new_cache)

        def safe(f, kind, info):
            try:
                return work(f, kind, info)
            except Exception as e:  # 1つ失敗しても、ほかは続ける
                size = f.stat().st_size
                return size, size, f"⚠ エラーで触らない ({e})。今後は飛ばします", True

        if small:
            with ThreadPoolExecutor(max_workers=POOL) as ex:
                futs = {ex.submit(safe, f, kind, info): (f, kind) for f, kind, info in small}
                for fu in as_completed(futs):
                    f, kind = futs[fu]
                    results[f.name] = fu.result()
                    row(f.name, kind, results[f.name][0], results[f.name][1], results[f.name][2])
                    remember(f, kind, results[f.name])
        for f, kind, info in videos:
            results[f.name] = safe(f, kind, info)
            row(f.name, kind, results[f.name][0], results[f.name][1], results[f.name][2])
            remember(f, kind, results[f.name])
        for f, kind, _info in todo:
            after += results[f.name][1]
    elif todo:
        for f, kind, _info in todo:
            after += f.stat().st_size

    shutil.rmtree(TMP, ignore_errors=True)
    if args.dry:
        print("\n(--dry なので、ファイルは何も変えていません)")
        return
    save_cache(new_cache)
    print(f"\n合計: {mb(before)} → {mb(after)}   ({int(time.time() - started)}秒)")
    print("元のファイルは siryou_original/ にあります。戻すときは  python shrink.py --restore")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        shutil.rmtree(TMP, ignore_errors=True)   # 途中の一時ファイルを片付ける
        print("\n中断しました。ここまでに終わったファイルの結果は記録済みです (次回は続きから)。")
