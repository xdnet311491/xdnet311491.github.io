"""
OP(入場)画面のロゴアニメーションを作るスクリプト

  siryou/logo.png  (ロゴ画像)  →  siryou/op.mp4  (アニメーション動画)

使い方 (最初の1回だけ pip install が必要):
  pip install numpy pillow scipy
  python make_op.py

必要なもの: ffmpeg (ターミナルで ffmpeg -version が動くこと)

できた op.mp4 は siryou に入るので、あとは build.py を実行 (watch.py が自動でやる) すれば
サイトの入場画面に出ます。タイミングを変えたいときは下の「タイミング」を触ってください。
単位は「フレーム」(30fps なので 30 = 1秒) です。

ロゴの4パーツ (色で自動的に分けています):
  青い文字 / 黒い文字 / 下のサブタイトル / 十字の線とリング
"""

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

BASE = Path(__file__).resolve().parent
SRC = BASE / "siryou" / "logo.png"
OUT = BASE / "siryou" / "op.mp4"

# ---------- 動画の設定 ----------
FPS = 30
FRAMES = 60          # 全体の長さ。60 = 2秒 (アニメは約1秒で終わり、残りは完成形で止まる)
SCALE = 1.5          # ロゴ画像に対する解像度の倍率 (大きいほど細かいが重い)
PAD_X, PAD_Y = 64, 81  # ロゴの周りの余白 (ロゴ画像のピクセル単位)

# ---------- 色 ----------
CYAN = (51, 226, 255)       # 出現直後の「青い文字」
MID_BLUE = (62, 158, 230)   # 出現直後の「黒い文字」
PALE_B = (155, 240, 250)    # 青い文字が染まる途中の淡い色
PALE_D = (145, 218, 255)    # 黒い文字が染まる途中の淡い色
LIGHT = (232, 232, 236)     # サブタイトルが出た瞬間の薄いグレー
GRAY = (110, 110, 118)      # リングが出た瞬間の色

# ---------- タイミング (フレーム) ----------
T_ENTER = 2          # 文字が帯状に出はじめる
D_ENTER = 5          # 出るのにかかる長さ
T_SWEEP = 7.5        # 黒い文字が染まりはじめる
D_SWEEP = 7          # 染まりきるまで
SWEEP_W = 300        # 染まる境目の幅 (px)
T_SUB = 12           # サブタイトルが左から出はじめる
D_SUB = 6            # 左端から右端まで出るのにかかる長さ
T_LINE1, T_LINE2, D_LINE = 12, 14, 7   # 十字の線 (浅い線 / 縦の線)
T_RING, D_RING = 17, 9                 # リング

# 文字の帯 (上・中・下) の境目と、文字の左右の端 (ロゴ画像のピクセル)
TEXT_Y0, TEXT_Y1 = 101, 170
TEXT_X0, TEXT_X1 = 24, 1501
SUB_X0, SUB_X1 = 936, 1489


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = np.clip(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def lerp(a, b, t):
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    t = np.asarray(t, dtype=np.float32)[..., None]
    return a + (b - a) * t


# ---------------------------------------------------------------- ロゴを分解
def split_layers(rgba):
    """ロゴを色と位置で 1=十字 2=リング 3=青文字 4=黒文字 5=サブタイトル に分ける"""
    a = rgba[..., 3].astype(int)
    r, b = rgba[..., 0].astype(int), rgba[..., 2].astype(int)
    solid = a > 20
    blue = solid & (b > r + 40)
    dark = solid & ~blue
    cls = np.zeros(a.shape, np.uint8)

    lab, _ = ndi.label(blue, structure=np.ones((3, 3)))
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        w = sl[1].stop - sl[1].start
        cls[lab == i] = 1 if w > 120 else 3  # 幅の広い塊 = 十字

    lab, _ = ndi.label(dark, structure=np.ones((3, 3)))
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        if y1 <= 115 and x0 >= 630 and x1 <= 820:
            k = 2      # リング
        elif y0 >= 180:
            k = 5      # サブタイトル
        else:
            k = 4      # 黒文字
        cls[lab == i] = k

    # 薄い縁(半透明)のピクセルも、いちばん近いパーツに入れる
    idx = ndi.distance_transform_edt(cls == 0, return_distances=False, return_indices=True)
    full = cls[idx[0], idx[1]]
    full[a == 0] = 0
    return full, a


def pca(pts):
    m = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - m, full_matrices=False)
    return m, vt[0]


def main():
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg が見つかりません。ffmpeg をインストールしてください。")
    if not SRC.is_file():
        sys.exit(f"ロゴ画像がありません: {SRC}")

    im = Image.open(SRC).convert("RGBA")
    rgba = np.array(im)
    lh, lw = rgba.shape[:2]
    cls, a = split_layers(rgba)

    # 最終的な色は元のロゴから拾う (完成形が元画像と一致するように)
    full_px = rgba[..., :3]
    BLUE = tuple(np.median(full_px[(cls == 3) & (a == 255)], axis=0))
    DARK = tuple(np.median(full_px[(cls == 4) & (a == 255)], axis=0))

    # ---- 十字: 2本の線に分けて、交点と向きを求める
    ys, xs = np.nonzero(cls == 1)
    P = np.stack([xs, ys], 1).astype(float)
    strong = a[ys, xs] > 128
    m1, d1 = pca(P[strong & (P[:, 1] > 115)])  # 縦の線 (下の方は縦の線だけ)
    sel = strong & (((P[:, 0] < 700) & (P[:, 1] < 70)) | ((P[:, 0] > 780) & (P[:, 1] > 85)))
    m2, d2 = pca(P[sel])  # 浅い線
    t = np.linalg.solve(np.array([d1, -d2]).T, m2 - m1)
    C = m1 + t[0] * d1

    def dist(p, m, d):
        v = p - m
        return np.abs(v[:, 0] * d[1] - v[:, 1] * d[0])

    line_id = np.where(dist(P, m1, d1) <= dist(P, m2, d2), 0, 1)
    lines = []
    for k, d in enumerate((d1, d2)):
        tt = (P[line_id == k] - C) @ d
        lines.append((d, tt.min(), tt.max()))

    # ---- リング: 描きはじめの角度と範囲
    ys, xs = np.nonzero(cls == 2)
    RC = (xs.mean(), ys.mean())
    th = np.sort(np.degrees(np.arctan2(ys - RC[1], xs - RC[0])) % 360)
    gaps = np.diff(np.r_[th, th[0] + 360])
    g = int(np.argmax(gaps))
    ring_start = th[(g + 1) % len(th)]           # 隙間のすぐ後ろ = 描きはじめ
    ring_span = (th[g] - ring_start) % 360

    # ---- 各パーツを動画サイズの透明度マップにする
    W0, H0 = lw + 2 * PAD_X, lh + 2 * PAD_Y
    Wc, Hc = int(W0 * SCALE) // 2 * 2, int(H0 * SCALE) // 2 * 2

    def to_canvas(mask_alpha):
        big = np.zeros((H0, W0), np.uint8)
        big[PAD_Y:PAD_Y + lh, PAD_X:PAD_X + lw] = mask_alpha.astype(np.uint8)
        img = Image.fromarray(big).resize((Wc, Hc), Image.LANCZOS)
        return np.asarray(img, dtype=np.float32) / 255.0

    A_blue = to_canvas(np.where(cls == 3, a, 0))
    A_dark = to_canvas(np.where(cls == 4, a, 0))
    A_sub = to_canvas(np.where(cls == 5, a, 0))
    A_ring = to_canvas(np.where(cls == 2, a, 0))
    ys, xs = np.nonzero(cls == 1)
    Pall = np.stack([xs, ys], 1).astype(float)
    lid = np.where(dist(Pall, m1, d1) <= dist(Pall, m2, d2), 0, 1)
    A_line = []
    for k in (0, 1):
        m = np.zeros(a.shape, np.uint8)
        sel = lid == k
        m[ys[sel], xs[sel]] = a[ys[sel], xs[sel]]
        A_line.append(to_canvas(m))

    # ---- 座標 (ロゴ画像のピクセル単位) の格子
    gx = ((np.arange(Wc) + 0.5) / SCALE - PAD_X).astype(np.float32)
    gy = ((np.arange(Hc) + 0.5) / SCALE - PAD_Y).astype(np.float32)
    X, Y = np.meshgrid(gx, gy)
    band = np.clip(((Y - TEXT_Y0) / ((TEXT_Y1 - TEXT_Y0) / 3)).astype(int), 0, 2)
    slant = (Y - 135) * 0.3  # 文字の斜めに合わせて境目を傾ける

    # 十字の線: 交点からの距離 (0〜1)
    line_r = []
    for d, tmin, tmax in lines:
        tl = (X - C[0]) * d[0] + (Y - C[1]) * d[1]
        line_r.append(np.where(tl >= 0, tl / tmax, tl / tmin))
    # リング: 描きはじめからの角度の割合 (0〜1)
    ring_u = ((np.degrees(np.arctan2(Y - RC[1], X - RC[0])) - ring_start) % 360) / ring_span

    X_span = TEXT_X1 - TEXT_X0 + 80

    def enter_mask(f):
        """文字が上・中・下の帯ごとにずれながら現れる"""
        out = np.zeros_like(X)
        for k in range(3):
            p = smooth((f - (T_ENTER + k * 0.8)) / D_ENTER)
            if k < 2:  # 上・中の帯は右から
                edge = TEXT_X1 + 40 - p * X_span
                v = np.clip((X - edge - slant) / 10 + 0.5, 0, 1)
            else:      # 下の帯は左から
                edge = TEXT_X0 - 40 + p * X_span
                v = np.clip((edge + slant - X) / 10 + 0.5, 0, 1)
            out = np.where(band == k, v, out)
        return out

    def sweep_q(f, lag_by_band, extra=0.0):
        """染まり具合 0(まだ) 〜 1(完了)。左から右へ境目が動く"""
        lag = np.choose(band, lag_by_band)
        s = TEXT_X0 + (TEXT_X1 - TEXT_X0 + SWEEP_W) * smooth((f - extra - lag - T_SWEEP) / D_SWEEP)
        return np.clip((s - X) / SWEEP_W, 0, 1)

    def three(c0, c1, c2, q):
        """q: 0→c0, 0.5→c1, 1→c2"""
        lo = lerp(c0, c1, np.clip(q * 2, 0, 1))
        hi = lerp(c1, c2, np.clip(q * 2 - 1, 0, 1))
        return np.where((q < 0.5)[..., None], lo, hi)

    proc = subprocess.Popen(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{Wc}x{Hc}", "-r", str(FPS), "-i", "-",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-tune", "animation",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv", "-movflags", "+faststart", "-an", str(OUT),
        ],
        stdin=subprocess.PIPE,
    )

    for f in range(FRAMES):
        img = np.full((Hc, Wc, 3), 255.0, np.float32)

        def put(alpha, color):
            nonlocal img
            al = alpha[..., None]
            img = img * (1 - al) + np.asarray(color, np.float32) * al

        vis = enter_mask(f)

        # 黒い文字: 中間の青 → 淡い水色 → 黒
        q = sweep_q(f, [0.0, 0.5, 1.0])
        put(A_dark * vis, three(MID_BLUE, PALE_D, DARK, q))
        # 青い文字: シアン → 淡い水色 → 青 (上の帯ほどゆっくり)
        q = sweep_q(f, [3.0, 1.5, 0.0], extra=1.0)
        put(A_blue * vis, three(CYAN, PALE_B, BLUE, q))

        # サブタイトル: 左から薄いグレーで出て、だんだん濃くなる
        tp = T_SUB + (X - SUB_X0) / (SUB_X1 - SUB_X0) * D_SUB
        age = f - tp
        put(A_sub * np.clip(age / 1.5, 0, 1), lerp(LIGHT, DARK, smooth(age / 8)))

        # リング: 左端から時計まわりに描かれる
        r = ease_out((f - T_RING) / D_RING) * 1.1
        put(A_ring * np.clip((r - ring_u) / 0.08, 0, 1),
            lerp(GRAY, DARK, np.full((Hc, Wc), float(smooth((f - T_RING) / 10)), np.float32)))

        # 十字の線: 交点から両端へ伸びる
        for k, t0 in ((1, T_LINE1), (0, T_LINE2)):
            r = ease_out((f - t0) / D_LINE) * 1.1
            col = lerp(CYAN, BLUE, np.full((Hc, Wc), float(smooth((f - t0) / 10)), np.float32))
            put(A_line[k] * np.clip((r - line_r[k]) / 0.1, 0, 1), col)

        proc.stdin.write(np.clip(img + 0.5, 0, 255).astype(np.uint8).tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg でエラーが出ました。")
    print(f"書き出しました: {OUT} ({OUT.stat().st_size / 1000:.0f}KB, {Wc}x{Hc}, {FRAMES / FPS:.1f}秒)")


if __name__ == "__main__":
    main()
