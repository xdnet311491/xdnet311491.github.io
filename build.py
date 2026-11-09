"""
自作サイトの書き出しスクリプト (GitHub Pages用・JavaScriptなし)

構成:
  build.py
  channels.json   ... チャンネルコーナーの内容
  fukyou.txt      ... 布教部屋の中身 (部屋 → 項目 → 詳細ページ)。書き方は先頭の注釈を見る
  pages/          ... お遊びコーナーに並べるHTMLを置く場所。.html を置くと一覧に自動で入る
  siryou/         ... 壁紙 (wallpaper.mp4) と 入場画面のアニメ (op.mp4) などを置く場所
  (音楽) siryou/op1.mp3 などのオープニング曲と、siryou/sound.mp3 (メイン画面の曲) を置く。曲の一覧は OP_SONGS で編集
  make_op.py      ... siryou/logo.png から siryou/op.mp4 (入場アニメ) を作る。必要なときだけ実行
  index.html      ← build.py が自動で作る(手で編集しない)
  version.json    ← build.py が自動で作る。「サイトが更新されました」の判定に使う

使い方:
  python build.py
  → index.html ができる。フォルダごとGitHubに上げれば公開される
  (標準ライブラリだけで動くので pip install は不要)
"""

import hashlib
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

BASE = Path(__file__).resolve().parent
PAGES_DIR = BASE / "pages"
CHANNELS_FILE = BASE / "channels.json"
OUTPUT = BASE / "index.html"
VERSION_FILE = BASE / "version.json"

SITE_TITLE = "xdnet311491/internet archive☆"
COLS, ROWS = 22, 40  # (JSなしモード用) エフェクト用マス目の数

# True : ブルアカ風のタップ/なぞりエフェクト。書き出すindex.htmlの中にJavaScriptが入る
#        (あなたが触るのは build.py だけ。JSファイルを別に用意する必要はない)
# False: JSなし。CSSだけのマス目エフェクト(タッチのなぞりは出にくい)
ENABLE_JS_EFFECT = True

# ---------- 壁紙 ----------
# index.html と同じ階層の siryou フォルダに壁紙を置く。
#   動画 (.mp4 / .webm) ... 動く壁紙。自動でループ再生・無音
#   画像 (.gif / .webp / .apng / .png / .jpg) ... gif・webpなら動く壁紙にもできる
# WALLPAPER にファイル名を入れるとそのファイルを使う (例: "haikei.mp4")。
# 空のままなら、siryou の中から「wallpaper」か「壁紙」という名前のファイルを自動で探す。
SIRYOU_DIR = BASE / "siryou"
WALLPAPER = ""
# ※ 下の WALLPAPERS / MAIN_SONGS / OP_SONGS / OP_MOTIONS は「初回用の初期値」。2回目以降は site_data.json が使われます
# ★ 壁紙の一覧。「画面設定」→「壁紙」に並んで、タップで切り替えられる。書き方は OP_SONGS と同じ:
#   ("画面に出る名前", "siryouの中のファイル名", "名前の下に出る小さい説明")  ※説明は省略OK
#   ・まだ選んでいないときは、ファイルがある壁紙の一番上が使われる (WALLPAPER に名前を書いた場合はそれが先)
#   ・動画は通信量が大きいので、各行に大きさ(MB)を出している
WALLPAPERS = [
    ("1. mimori", "wallpaper.mp4", "最初の壁紙"),
    ("2. serina", "wallpaper2.mp4", ""),
    ("3. kei1", "wallpaper3.mp4", ""),
    ("4. kei2", "wallpaper4.mp4", ""),
    ("5. mary", "wallpaper5.mp4", ""),
    ("6. jyunko", "wallpaper6.mp4", ""),
    ("7. chise", "wallpaper7.mp4", ""),
    ("8. shigure", "wallpaper8.mp4", ""),
    ("9. miyako", "wallpaper9.mp4", ""),
    ("10. azusa", "wallpaper10.mp4", ""),
]
VIDEO_EXT = {".mp4", ".webm", ".m4v", ".mov"}
IMAGE_EXT = {".gif", ".webp", ".apng", ".png", ".jpg", ".jpeg", ".avif", ".svg"}
WALL_SHADE = 0.35  # 壁紙の上にかぶせる暗さ (0〜1)。文字が読みにくいときは上げる

# ---------- 左端の影 (左端が黒く、右へ向かってだんだん透明になる) ----------
# EDGE_DARK  : 左端の黒の濃さ (0〜1)。0.5前後で控えめ。強すぎると感じたら下げる。0 で影なし
# EDGE_WIDTH : 影が届く幅 (画面の横幅に対する%)。大きいほど右の方まで薄く広がる
EDGE_DARK = 1
EDGE_WIDTH = 70

# ---------- 音楽 ----------
# True : 最初に暗い画面で「音楽の再生を許可しますか？」(はい/いいえ) を出す。
#        「はい」→ ロード画面で音楽が流れる → 入場するとその曲が小さくなって消え、メイン画面の曲に交代。
#        メイン画面に「サウンド設定」タブが増え、音楽のON/OFFと、オープニング曲の変更ができる。
#        (JavaScriptが入る。曲のファイルは siryou フォルダに置く)
# False: 今まで通り (許可画面もサウンド設定も出ない)
ENABLE_SOUND = True

# メイン画面で流れる曲 (siryou の中のファイル名)。無いときは、メイン画面では曲を流さないだけ
# ★ メイン画面の曲の一覧。書き方は OP_SONGS と同じ。サウンド設定の「メイン画面」タブに並ぶ。
#   選ぶと、いま流れているメイン画面の曲がすぐ切り替わる。まだ選んでいないときは、ファイルがある曲の一番上が流れる。
MAIN_SONGS = [
    ("1. Unwelcome School(8bit remix)", "sound.mp3", "最初に流れる曲"),
    ("2. Step by Step", "sound2.mp3", ""),
    ("3. Romantic Smile", "sound3.mp3", ""),
    ("4. Midsummer Cat", "sound4.mp3", ""),
    ("5. Walktrought", "sound5.mp3", ""),
]

# ★ オープニング曲の一覧。ここを書き換えるだけで、サウンド設定の曲の並びが変わる。
#   1行が1曲:  ("画面に出る曲名", "siryouの中のファイル名", "曲名の下に出る小さい説明")
#   ・説明がいらなければ省略してOK:  ("曲名", "ファイル名")
#   ・曲を増やすときは、1行コピーして貼り付けるだけ
#   ・まだ選んでいないときは、ファイルがある曲の一番上が流れる
#   ・siryou にファイルが無い曲は「ファイルなし」と出て、選べない
#   ・ファイル名を変えると、その曲を選んでいた人は選び直しになる
OP_SONGS = [
    ("1. Aoharu Band Arrange", "op1.mp3", "最初に流れる曲"),
    ("諸事情により削除済", "op2.mp3", ""),
    ("3. Rolling Beat", "op3.mp3", ""),
    ("4. ユメ先輩(身内ノリでは牛込柳町パーククリニック)のテーマ", "op4.mp3", ""),
    ("5. OperationD", "op5.mp3", ""),
    ("6. Dreaming Trip", "op6.mp3", ""),
    ("7. Welcome School", "op7.mp3",""),
    ("8. Our Oath", "op8.mp3", ""),
    ("9. Alkaline tears", "op9.mp3", ""),
    ("10. ﾕｳｶの絆ダイアローグ", "op10.mp3", ""),
    ("11. 彩りキャンバス", "op11.mp3", ""),
]

# 音量 (0〜1) と、切り替えの長さ (秒)
OP_VOLUME = 0.7      # ロード画面の曲の音量
MAIN_VOLUME = 0.6    # メイン画面の曲の音量
OP_FADE_IN = 0.8     # 「はい」を押してから、ロード画面の曲が大きくなるまで
OP_FADE_OUT = 2.0    # 入場してから、ロード画面の曲が消えるまで
MAIN_FADE_IN = 2.5   # 入場してから、メイン画面の曲が大きくなるまで (OP_FADE_OUT と重なって交代する)

# ---------- ボタン類 (画面設定「ボタン」/ サウンド設定「カーソル効果音」) ----------
# ボタン・カードなど「当たり判定のある部分」の背景の濃さ。0 = 透明 〜 100 = 完全不透明。
# 画面設定のスライダーで、見ている人が自分で変えられる (これは何も選んでいないときの初期値)
BTN_ALPHA_DEFAULT = 25
# カーソルをボタンに合わせたときに鳴らす音 (siryou の中のファイル名)。無ければ鳴らさないだけ
CURSOR_SOUND = "cursol.mp3"
CURSOR_VOLUME = 0.5   # その音量 (0〜1)

# ---------- 読み込み待ちの入場画面 ----------
# True : 壁紙などの読み込みが完全に終わるまで、入場画面に「ぐるぐる」を出してクリックできなくする。
#        終わったら「Click to enter」が出てクリックできるようになる。
#        壁紙の動画は、ファイルを全部ダウンロードしてから再生するので、再生中に止まりにくい。
#        (JavaScriptが入る。JSが動かない環境では、最初からクリックできる)
ENABLE_LOADING_GATE = True

# ---------- 「サイトが更新されました」のお知らせ ----------
# True : ページを開いたままの人に、新しい版が公開されたら「サイトが更新されました」を出す。
#        (60秒ごとに version.json を見に行く。JavaScriptが入る)
ENABLE_UPDATE_NOTICE = True

# ---------- 入場(OP)画面 ----------
# siryou の中の「op」という名前の動画 (op.mp4 など) を、入場画面で1回だけ再生する。
# 動画は make_op.py で作れる (siryou/logo.png → siryou/op.mp4)。
# OP_VIDEO にファイル名を入れるとそのファイルを使う。空なら op / オープニング を自動で探す。
# 動画が見つからないときは、これまで通りの文字だけの入場画面になる。
OP_VIDEO = ""
# 動画が再生できない環境 (省電力モードなど) や「動きを減らす」設定のときに出す静止画。
# 空なら「logo」「ロゴ」という名前の画像を自動で探す。
OP_STILL = ""

# ---------- 特殊モーション (OP画面の背景で動画を流す) ----------
# 「画面設定」タブ → 「オープニング画面」 の「特殊モーション」ON/OFFで切り替えられる。
# ここに「曲 → 背景動画」を書いた曲だけ、その曲が選ばれているときにOP画面の背景で動画が流れる。
# 書いていない曲は今まで通り白い背景のまま。
#   書き方:  "曲のファイル名 (OP_SONGSと同じ)": "siryouの中の動画ファイル名"
#   例:      "op1.mp3": "motion1.mp4",
#   ・動画は siryou に置く (.mp4 / .webm など)。音は出ない・ループ再生
#   ・動画が siryou に無いときは、その曲は特殊モーションなし (白背景) になる
#   ・スマホでも軽く動くよう、1280x720 くらいに小さくしておくのがおすすめ
OP_MOTIONS = {
     "op4.mp3": "motion4.mp4",
     "op10.mp3": "motion10.mp4",
     "op11.mp3": "motion11.mp4",
}
OP_MOTION_BLUR = 6     # 背景動画のぼかし (px)。0 でぼかしなし。大きいほどぼける
OP_MOTION_VEIL = 0.25  # 動画の上にかぶせる白さ (0〜1)。ロゴや文字が見にくいときは上げる

# ======================================================================
# ★ 曲・壁紙・特殊モーションの一覧は「site_data.json」に分けてあります
# ----------------------------------------------------------------------
#  ・上の WALLPAPERS / MAIN_SONGS / OP_SONGS / OP_MOTIONS は「最初の1回だけ使う初期値」です。
#    初回のビルドで site_data.json が自動で作られ、2回目以降はそのファイルが使われます。
#  ・曲や壁紙を増やす・変えるときは site_data.json を編集してください。
#    → build.py を丸ごと差し替えても (AIが直した版に置き換えても)、一覧は消えません。
#  ・ホーム画面の文章は home.txt、開発者機能のパスワードは dev_password.txt に分けてあります。
# ======================================================================
SITE_DATA_FILE = BASE / "site_data.json"
HOME_FILE = BASE / "home.txt"
DEV_PASSWORD_FILE = BASE / "dev_password.txt"   # .gitignore に入る = GitHubには上がらない

HOME_DEFAULT = (
    "ここは全部自作のサイトです。画面をなぞる・タップすると光が出ます。\n\n"
    "上のタブから、お遊びコーナー(回線テスト・強震モニターなど)とチャンネルを見られます。\n"
)


def _guess_namespace() -> str:
    """閲覧者数カウンターの名前。git の送り先 (origin) から決める。分からなければ固定の名前"""
    try:
        cfg = (BASE / ".git" / "config").read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?\s*$", cfg, re.M)
        if m:
            return re.sub(r"[^A-Za-z0-9_-]", "-", f"{m.group(1)}-{m.group(2)}")[:60]
    except OSError:
        pass
    return "osaito-site"


# 合計閲覧者数 (ホーム画面)。GitHub Pages は自分のサーバーが無いので、無料の外部カウンターに数えてもらう。
#   {ns} {key} は自動で置き換わる。サービスが止まったときは、ここの URL を別のサービスに変えるだけでよい
#   (返事は {"value": 数字} か {"count": 数字} の形なら使える)
VISITOR_COUNTER_DEFAULT = {
    "enabled": True,
    "namespace": _guess_namespace(),
    "key": "visitors",
    "hit_url": "https://abacus.jasoncameron.dev/hit/{ns}/{key}",
    "get_url": "https://abacus.jasoncameron.dev/get/{ns}/{key}",
}


def _seed_site_data_text() -> str:
    def rows(items):
        return "[\n" + ",\n".join(
            "    " + json.dumps([str(x) for x in r], ensure_ascii=False) for r in items) + "\n  ]"

    mot = ",\n".join(
        f"    {json.dumps(str(k), ensure_ascii=False)}: {json.dumps(str(v), ensure_ascii=False)}"
        for k, v in OP_MOTIONS.items())
    vc = json.dumps(VISITOR_COUNTER_DEFAULT, ensure_ascii=False, indent=4).replace("\n", "\n  ")
    memo = ("曲・壁紙・特殊モーションの一覧です。build.py を丸ごと差し替えてもこのファイルは消えません。"
            "1行が1件で、[\"画面に出る名前\", \"siryouの中のファイル名\", \"小さい説明(空でもOK)\"] の形です。"
            "増やすときは1行コピーして書き換えます。行の最後のカンマ、引用符(\")、かっこを消さないでください。"
            "op_motions は \"曲のファイル名\": \"動画のファイル名\" の形です。")
    return (
        "{\n"
        f'  "_メモ": {json.dumps(memo, ensure_ascii=False)},\n'
        f'  "wallpapers": {rows(WALLPAPERS)},\n'
        f'  "main_songs": {rows(MAIN_SONGS)},\n'
        f'  "op_songs": {rows(OP_SONGS)},\n'
        f'  "op_motions": {{\n{mot}\n  }},\n'
        f'  "visitor_counter": {vc}\n'
        "}\n"
    )


def _site_rows(raw: dict, key: str):
    v = raw.get(key)
    if v is None:
        return None
    if not isinstance(v, list):
        sys.exit(f'site_data.json の "{key}" が一覧 [ ... ] になっていません。GitHubには送りません。')
    out = []
    for n, item in enumerate(v, 1):
        ok = (isinstance(item, (list, tuple)) and 2 <= len(item) <= 3
              and all(isinstance(x, (str, int, float)) for x in item))
        if not ok:
            sys.exit(f'site_data.json の "{key}" の {n} 件目が ["名前", "ファイル名", "説明"] の形ではありません: {item!r}')
        out.append(tuple(str(x) for x in item) + ("",) * (3 - len(item)))
    return out


def _load_site_data() -> None:
    """site_data.json があればそれを使う。無ければ、いまの初期値から作る (あとは触らない)"""
    global WALLPAPERS, MAIN_SONGS, OP_SONGS, OP_MOTIONS, VISITOR_COUNTER
    VISITOR_COUNTER = dict(VISITOR_COUNTER_DEFAULT)
    if not SITE_DATA_FILE.is_file():
        SITE_DATA_FILE.write_text(_seed_site_data_text(), encoding="utf-8")
        print("site_data.json を新しく作りました (曲・壁紙の一覧はこれからここで編集します)")
        return
    try:
        raw = json.loads(SITE_DATA_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"site_data.json の {e.lineno} 行目 {e.colno} 文字目あたりに書き間違いがあります: {e.msg}\n"
                 "  (カンマ・引用符・かっこの閉じ忘れを確認してください。GitHubには送りません)")
    if not isinstance(raw, dict):
        sys.exit("site_data.json の中身が { ... } になっていません。GitHubには送りません。")
    for key, name in (("wallpapers", "WALLPAPERS"), ("main_songs", "MAIN_SONGS"), ("op_songs", "OP_SONGS")):
        rows = _site_rows(raw, key)
        if rows is not None:
            globals()[name] = rows
    mot = raw.get("op_motions")
    if mot is not None:
        if not isinstance(mot, dict):
            sys.exit('site_data.json の "op_motions" が { "曲": "動画" } の形になっていません。')
        OP_MOTIONS = {str(k): str(v) for k, v in mot.items()}
    vc = raw.get("visitor_counter")
    if isinstance(vc, dict):
        VISITOR_COUNTER.update(vc)


_load_site_data()

CSS = """
:root{--bg:#0a0e2a;--bg2:#141a45;--ink:#eef0ff;--dim:#9aa3d6;--line:#2b3470;--glow:#7df3ff;--gold:#ffe27a;color-scheme:dark}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg)}
body{background:radial-gradient(120% 90% at 50% 0%,var(--bg2),var(--bg) 70%) fixed;color:var(--ink);
  font-family:"Hiragino Sans","Yu Gothic","Meiryo",sans-serif;line-height:1.7;
  -webkit-tap-highlight-color:transparent;-webkit-user-select:none;user-select:none}
.sr{position:fixed;opacity:0;pointer-events:none}

/* ---------- 入場画面 ---------- */
.gate{position:fixed;inset:0;z-index:50;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:1rem;cursor:pointer;
  transition:opacity .7s ease,transform .7s ease,visibility 0s}
.gt{font-size:clamp(2.4rem,10vw,5.5rem);font-weight:900;letter-spacing:.04em;
  text-shadow:0 0 24px var(--glow),0 0 60px rgba(125,243,255,.35);animation:breathe 2.8s ease-in-out infinite}
.gs{color:var(--dim);font-size:.95rem}
.tap{display:none}
@media (pointer:coarse){.tap{display:inline}.click{display:none}}
@keyframes breathe{0%,100%{opacity:.75}50%{opacity:1}}
#enter:checked ~ .gate{opacity:0;transform:scale(1.08);visibility:hidden;pointer-events:none;
  transition:opacity .7s ease,transform .7s ease,visibility 0s .7s}
#enter:focus-visible ~ .gate{outline:2px solid var(--gold);outline-offset:-8px}

/* ---------- エフェクト用マス目 ---------- */
.grid{position:fixed;inset:0;z-index:1;display:grid;
  grid-template-columns:repeat(var(--cols),1fr);grid-template-rows:repeat(var(--rows),1fr)}
.grid i{display:block;--h:190;position:relative}
.grid i:nth-child(5n+1){--h:200}
.grid i:nth-child(5n+2){--h:212}
.grid i:nth-child(5n+3){--h:190}
.grid i:nth-child(5n+4){--h:222}
.grid i:nth-child(5n){--h:205}
.grid i::before{content:"";position:absolute;inset:18%;border-radius:50%;
  background:hsl(var(--h) 100% 72%);box-shadow:0 0 14px hsl(var(--h) 100% 70%);
  transform:scale(0);opacity:0;transition:transform .9s ease-out,opacity .9s ease-out}
/* 触れた瞬間はすぐ光り、離れるとゆっくり消える = 軌跡になる */
.grid i:hover::before{transform:scale(1.7);opacity:.95;transition-duration:0s}
.grid i:hover + i::before{transform:scale(1);opacity:.6;transition-duration:0s}
/* タップ/クリック中は大きく弾ける */
.grid i:active::before{transform:scale(6);opacity:1;transition-duration:0s}

/* ---------- 本体 ---------- */
main{position:relative;z-index:10;max-width:760px;margin:0;padding:1.2rem;padding-left:clamp(1.2rem,5vw,4rem);
  padding-top:max(1.2rem,env(safe-area-inset-top));opacity:0;transition:opacity .9s ease .2s;
  pointer-events:none}
#enter:checked ~ main{opacity:1}
main a,main label{pointer-events:auto}
h1{margin:0 0 .8rem;font-size:1.7rem;font-weight:900;letter-spacing:.03em}
.tabs{display:flex;gap:.4rem;border-bottom:1px solid var(--line)}
.tabs label{padding:.6rem 1rem;color:var(--dim);font-weight:700;cursor:pointer;
  border-bottom:3px solid transparent;margin-bottom:-1px}
#t-home:checked ~ main label[for=t-home],
#t-pages:checked ~ main label[for=t-pages],
#t-channels:checked ~ main label[for=t-channels]{color:var(--ink);border-bottom-color:var(--glow)}
.panel{display:none;padding:1.4rem .2rem 2rem}
#t-home:checked ~ main .p-home,
#t-pages:checked ~ main .p-pages,
#t-channels:checked ~ main .p-channels{display:block}
.lead{font-size:1.2rem;margin-top:0}
.list{list-style:none;margin:0;padding:0;display:grid;gap:.8rem}
.list a{display:block;padding:1rem 1.1rem;border:1px solid var(--line);border-radius:14px;
  background:rgba(20,26,69,.82);color:var(--ink);text-decoration:none;transition:border-color .2s,background .2s}
.list a:hover{border-color:var(--glow)}
.list a:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
.name{font-weight:700;font-size:1.05rem}
.desc{display:block;color:var(--dim);font-size:.9rem;margin-top:.15rem}
.empty{color:var(--dim)}
@media (prefers-reduced-motion:reduce){.gt{animation:none}.grid i::before{transition:none}
  .gate,main{transition:none}}
"""


# ---------- JSモード用: CSSの追加分 ----------
JS_CSS = """
html,body{height:100%;overflow:hidden;touch-action:none}
#fx{position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:100}
main{height:100vh;height:100dvh;display:flex;flex-direction:column;
  padding-bottom:max(1.2rem,env(safe-area-inset-bottom))}
.panel{flex:1;min-height:0;overflow-y:auto;touch-action:pan-y;pointer-events:auto}
"""

# ---------- JSモード用: タップ/なぞりエフェクト ----------
# タップ: 白い点 → 青い円 → 輪(欠けながら回る) + 周りの小さな三角 → 消える
# なぞり: 水色の細い尾(先が太く、後ろが細く消える) + 散らばる小さな三角
EFFECT_JS = r"""
(() => {
  const cv = document.getElementById('fx');
  const ctx = cv.getContext('2d');
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const TAU = Math.PI * 2;
  const TAP_MS = 900;     // タップ演出の長さ
  const TRAIL_MS = 380;   // 尾が消えるまでの時間
  let W = 0, H = 0;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener('resize', resize);

  const lerp = (a, b, t) => a + (b - a) * Math.min(1, Math.max(0, t));
  const taps = [], pts = [], tris = [];
  const held = new Set();
  let last = null, acc = 0, newStroke = true;

  function tri(x, y, s, rot) {
    ctx.beginPath();
    for (let i = 0; i < 3; i++) {
      const a = rot + (i * TAU) / 3;
      ctx.lineTo(x + Math.cos(a) * s, y + Math.sin(a) * s);
    }
    ctx.closePath();
    ctx.fill();
  }

  function spawnTri(x, y, now) {
    tris.push({
      x: x + (Math.random() - 0.5) * 22, y: y + (Math.random() - 0.5) * 22,
      vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4 - 0.1,
      t: now, life: 500 + Math.random() * 300,
      rot: Math.random() * TAU, s: 3 + Math.random() * 3,
      white: Math.random() < 0.5,
    });
  }

  window.addEventListener('pointerdown', (e) => {
    held.add(e.pointerId);
    last = { x: e.clientX, y: e.clientY };
    newStroke = true;
    taps.push({ x: e.clientX, y: e.clientY, t: performance.now(), rot: Math.random() * TAU });
  });

  window.addEventListener('pointermove', (e) => {
    // マウスは動かすだけで尾が出る。タッチ/ペンは触れている間だけ
    if (e.pointerType !== 'mouse' && !held.has(e.pointerId)) return;
    const now = performance.now();
    const x = e.clientX, y = e.clientY;
    if (last) {
      acc += Math.hypot(x - last.x, y - last.y);
      if (acc > 34) { acc = 0; spawnTri(x, y, now); }
    }
    pts.push({ x, y, t: now, b: newStroke });
    newStroke = false;
    last = { x, y };
  });

  const release = (e) => { held.delete(e.pointerId); last = null; newStroke = true; };
  window.addEventListener('pointerup', release);
  window.addEventListener('pointercancel', release);

  function drawTap(tp, now) {
    const p = (now - tp.t) / TAP_MS;
    if (p >= 1) return false;
    const { x, y } = tp;

    let r;
    if (p < 0.12) r = lerp(3, 9, p / 0.12);
    else if (p < 0.35) r = lerp(9, 22, (p - 0.12) / 0.23);
    else r = lerp(22, 31, (p - 0.35) / 0.65);

    const fillA = p < 0.35 ? 1 : 1 - Math.min(1, (p - 0.35) / 0.2);
    const fade = p < 0.55 ? 1 : 1 - (p - 0.55) / 0.45;

    ctx.shadowColor = 'rgba(70,140,255,.95)';
    ctx.shadowBlur = 18;

    if (fillA > 0) {
      ctx.globalAlpha = fillA;
      ctx.fillStyle = p < 0.12 ? '#cfe0ff' : '#5b9bff';
      ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill();
    }

    if (p >= 0.08) {
      ctx.globalAlpha = Math.max(0, fade);
      ctx.lineWidth = 2;
      ctx.strokeStyle = p < 0.5 ? '#ffffff' : '#8fdcff';
      if (p < 0.35) {
        ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.stroke();
      } else {
        // 輪が3つの弧に割れて、すきまが広がりながら回る
        const gap = lerp(0, 1.0, (p - 0.35) / 0.3);
        const seg = TAU / 3;
        for (let i = 0; i < 3; i++) {
          const a0 = tp.rot + p * 3 + i * seg + gap / 2;
          ctx.beginPath(); ctx.arc(x, y, r, a0, a0 + seg - gap); ctx.stroke();
        }
      }
    }

    if (p > 0.1) {
      ctx.globalAlpha = Math.max(0, 1 - (p - 0.15) / 0.75);
      ctx.fillStyle = '#ffffff';
      const d = r + 9 + p * 16, sz = lerp(4.5, 2.5, p);
      for (let k = 0; k < 4; k++) {
        const ang = tp.rot - p * 2.5 + (k * TAU) / 4;
        tri(x + Math.cos(ang) * d, y + Math.sin(ang) * d, sz, ang);
      }
    }

    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;
    return true;
  }

  function drawTrail(now) {
    while (pts.length && now - pts[0].t > TRAIL_MS) pts.shift();
    ctx.lineCap = 'round';
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i], b = pts[i - 1];
      if (a.b) continue;                       // 別のなぞりとはつなげない
      const k = 1 - (now - a.t) / TRAIL_MS;    // 新しいほど1、古いほど0
      if (k <= 0) continue;
      const w = 1 + k * 4.5;
      ctx.shadowColor = 'rgba(0,150,255,.9)';
      ctx.shadowBlur = 14;
      ctx.strokeStyle = 'rgba(20,170,255,' + k + ')';
      ctx.lineWidth = w;
      ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(a.x, a.y); ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = 'rgba(210,242,255,' + k * 0.85 + ')';  // 中心の白っぽい芯
      ctx.lineWidth = w * 0.35;
      ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(a.x, a.y); ctx.stroke();
    }
  }

  function drawTris(now) {
    for (let i = tris.length - 1; i >= 0; i--) {
      const t = tris[i];
      const k = 1 - (now - t.t) / t.life;
      if (k <= 0) { tris.splice(i, 1); continue; }
      t.x += t.vx; t.y += t.vy; t.rot += 0.04;
      ctx.globalAlpha = k;
      ctx.fillStyle = t.white ? '#ffffff' : '#7fd0ff';
      tri(t.x, t.y, t.s * (0.5 + k * 0.5), t.rot);
    }
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    ctx.clearRect(0, 0, W, H);
    drawTrail(now);
    drawTris(now);
    for (let i = taps.length - 1; i >= 0; i--) {
      if (!drawTap(taps[i], now)) taps.splice(i, 1);
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
"""


WALL_CSS = """
.wall{position:fixed;inset:0;width:100%;height:100%;object-fit:cover;z-index:0;pointer-events:none}
.wall-shade{position:fixed;inset:0;z-index:0;pointer-events:none;background:rgba(10,14,42,var(--shade,.35))}
@media (prefers-reduced-motion:reduce){video.wall{display:none}}
"""


def edge_css() -> str:
    """左端→右へ、黒がなめらかに薄くなるグラデーション (入場後に表示)"""
    if EDGE_DARK <= 0:
        return ""
    stops = []
    for t in (0, 0.15, 0.3, 0.5, 0.75, 1.0):
        a = EDGE_DARK * (1 - t) ** 2.2  # 端は濃く、離れるほど急に薄く (境目が見えにくい)
        stops.append(f"rgba(0,0,0,{a:.3f}) {EDGE_WIDTH * t:.1f}%")
    return (
        ".edge{position:fixed;inset:0;z-index:1;pointer-events:none;opacity:0;"
        f"background:linear-gradient(to right,{','.join(stops)});"
        "transition:opacity .9s ease .2s}"
        "#enter:checked ~ .edge{opacity:1}"
        "@media (prefers-reduced-motion:reduce){.edge{transition:none}}"
    )


UPDATE_CSS = """
.upd{position:fixed;left:50%;bottom:max(1.2rem,env(safe-area-inset-bottom));transform:translateX(-50%);
  z-index:200;display:flex;align-items:center;gap:.8rem;max-width:92vw;
  padding:.7rem .9rem .7rem 1.2rem;background:rgba(10,14,42,.94);color:var(--ink);
  border:1px solid var(--glow);border-radius:999px;box-shadow:0 0 24px rgba(125,243,255,.35);
  font-weight:700;pointer-events:auto;animation:upd-in .5s ease both}
.upd button{font:inherit;cursor:pointer;border:0;border-radius:999px;padding:.35rem .9rem;
  background:var(--glow);color:#0a0e2a;font-weight:900}
.upd .x{background:none;color:var(--dim);padding:.2rem .5rem;font-size:1.1rem}
.upd button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@keyframes upd-in{from{opacity:0;transform:translate(-50%,12px)}}
@media (prefers-reduced-motion:reduce){.upd{animation:none}}
"""

# 公開された version.json の build が、開いているページの build と違えば「更新された」と出す
UPDATE_JS = r"""
(() => {
  const m = document.querySelector('meta[name="build-id"]');
  if (!m) return;
  const mine = m.content;
  let timer = null, shown = false;

  async function check() {
    if (shown) return;
    try {
      const r = await fetch('version.json?t=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) return;
      const j = await r.json();
      if (j.build && j.build !== mine) show(j.build);
    } catch (e) { /* ネットワークが無いときなどは何もしない */ }
  }

  function show(next) {
    shown = true;
    clearInterval(timer);
    const box = document.createElement('div');
    box.className = 'upd';
    box.setAttribute('role', 'status');
    const msg = document.createElement('span');
    msg.textContent = 'サイトが更新されました';
    const go = document.createElement('button');
    go.type = 'button';
    go.textContent = '再読み込み';
    // ?u= を付けるのは、古いキャッシュを読み直してしまわないようにするため
    go.onclick = () => location.replace(location.pathname + '?u=' + next);
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'x';
    x.setAttribute('aria-label', '閉じる');
    x.textContent = '×';
    x.onclick = () => box.remove();
    box.append(msg, go, x);
    document.body.append(box);
  }

  timer = setInterval(check, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
})();
"""

OP_CSS = """
.gate.has-op{background:#fff;gap:1.6rem}
.op{display:block;width:min(92vw,1100px)}
.op-video,.op-still{display:block;width:100%;height:auto}
.op-still{display:none}
.has-op .gt{font-size:clamp(1.1rem,3.4vw,1.6rem);letter-spacing:.18em;color:#2a2a2e;
  text-shadow:0 0 18px rgba(26,140,255,.35)}
.has-op .gs{color:#6b7399}
#enter:focus-visible ~ .gate.has-op{outline-color:#1a8cff}
.op-fallback .op-video{display:none}
.op-fallback .op-still{display:block}
@media (prefers-reduced-motion:reduce){.op-video{display:none}.op-still{display:block}}
"""

# 入場画面の「読み込み中 (ぐるぐる)」と「Click to enter」の切り替え
# html に loading クラスが付いている間 = 読み込み中。クリックはできない。
LOAD_CSS = """
.hint{display:grid;justify-items:center;align-items:center}
.load,.ready{grid-area:1/1;display:flex;flex-direction:column;align-items:center;gap:.5rem}
.load{opacity:0;pointer-events:none;color:var(--dim);font-size:.95rem;letter-spacing:.12em;
  transition:opacity .3s ease}
.ready{transition:opacity .6s ease}
.spin{width:2.6rem;height:2.6rem;border-radius:50%;border:3px solid rgba(125,243,255,.25);
  border-top-color:var(--glow);animation:spin .9s linear infinite}
.has-op .load{color:#6b7399}
.has-op .spin{border-color:rgba(26,140,255,.18);border-top-color:#1a8cff}
html.loading .load{opacity:1}
html.loading .ready{opacity:0}
html.loading .gate{pointer-events:none;cursor:progress}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation:none}.load,.ready{transition:none}}
"""

# 読み込み完了の判定 (ページ全体 + 壁紙動画 + OPアニメが終わるくらいの最低待ち時間)
LOAD_JS = r"""
(() => {
  const root = document.documentElement;
  const enter = document.getElementById('enter');
  const pct = document.querySelector('.pct');
  const wall = document.querySelector('video.wall[data-src]');
  const MIN_MS = 1700;     // OPアニメが終わるまでは、最低でもこの時間は待つ
  const STALL_MS = 15000;  // この間まったくデータが届かなければ、あきらめて普通の読み込みに切り替える
  const MAX_MS = 120000;   // 何があってもこれ以上は待たせない
  let finished = false;
  const permP = window.__perm || Promise.resolve();  // 音楽の許可画面が終わるまで待つ
  if (enter) enter.disabled = true;  // キーボード(Tab+Space)でも入れないようにする

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const once = (el, ev) => new Promise((r) => el.addEventListener(ev, r, { once: true }));
  const play = () => {
    if (wall && wall.src) { const p = wall.play(); if (p && p.catch) p.catch(() => {}); }
  };

  // 壁紙は全部ダウンロードしてから再生する (再生中に通信待ちで止まらない)
  async function loadWall() {
    if (!wall || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const src = wall.dataset.src;
    try {
      const ctl = new AbortController();
      let timer = setTimeout(() => ctl.abort(), STALL_MS);
      const res = await fetch(src, { signal: ctl.signal });
      if (!res.ok || !res.body) throw new Error('bad response');
      const total = Number(res.headers.get('content-length')) || 0;
      const reader = res.body.getReader();
      const parts = [];
      let got = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parts.push(value);
        got += value.length;
        clearTimeout(timer);
        timer = setTimeout(() => ctl.abort(), STALL_MS);
        if (pct && total) pct.textContent = '読み込み中 ' + Math.min(99, Math.floor((got / total) * 100)) + '%';
      }
      clearTimeout(timer);
      const ready = Promise.race([once(wall, 'canplay'), once(wall, 'error'), sleep(8000)]);
      wall.src = URL.createObjectURL(new Blob(parts, { type: res.headers.get('content-type') || 'video/mp4' }));
      await ready;
      play();
    } catch (e) {
      wall.src = src;  // うまくいかなければ普通に読み込ませて、先へ進む
      play();
    }
  }

  function finish() {
    if (finished) return;
    finished = true;
    root.classList.remove('loading');
    if (enter) enter.disabled = false;
    play();
  }

  const pageLoaded = document.readyState === 'complete' ? Promise.resolve() : once(window, 'load');
  // 音楽の許可画面のあいだは、何も読み込まない (壁紙のダウンロードも、選んだあとに始める)
  // 特殊モーションの背景動画 (window.__motionReady) の準備も待つ。無ければ待たない
  const motionP = permP.then(() => window.__motionReady || null).catch(() => {});
  Promise.all([pageLoaded, permP.then(() => sleep(MIN_MS)), permP.then(loadWall), motionP]).then(finish, finish);
  permP.then(() => setTimeout(finish, MAX_MS));

  // 壁紙が止まってしまったとき(タブを切り替えた/省電力モード等)に再生し直す
  const resume = () => { if (wall && wall.src && wall.paused && !document.hidden) play(); };
  document.addEventListener('visibilitychange', resume);
  window.addEventListener('pageshow', resume);
  window.addEventListener('pointerdown', resume, { passive: true });
  if (wall) wall.addEventListener('pause', () => setTimeout(resume, 300));
})();
"""

# 動画が自動再生できない/読み込めないときは、静止画に切り替える
OP_JS = r"""
(() => {
  const v = document.querySelector('.op-video');
  if (!v) return;
  const fb = () => document.body.classList.add('op-fallback');
  v.addEventListener('error', fb);
  const start = () => { const p = v.play(); if (p && p.catch) p.catch(fb); };
  if (window.__perm) window.__perm.then(start); else start();

  // 「オープニング画面に戻る」で入場がやり直しになったら、OPアニメをもう一度流す
  const enter = document.getElementById('enter');
  if (enter) enter.addEventListener('change', () => {
    if (enter.checked) return;
    try { v.currentTime = 0; } catch (e) { /* まだ読み込み中 */ }
    start();
  });
})();
"""


SOUND_CSS = """
.sub[hidden]{display:none!important}
/* ---------- タブが4つになるので、はみ出したら横にスクロールできるようにする ---------- */
.tabs{overflow-x:auto;touch-action:pan-x;pointer-events:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs label{white-space:nowrap;padding:.6rem .8rem}
main button{pointer-events:auto}
#t-sound:checked ~ main label[for=t-sound]{color:var(--ink);border-bottom-color:var(--glow)}
#t-sound:checked ~ main .p-sound{display:block}
#t-screen:checked ~ main label[for=t-screen]{color:var(--ink);border-bottom-color:var(--glow)}
#t-screen:checked ~ main .p-screen{display:block}

/* ---------- 最初の「音楽の再生を許可しますか？」画面 ---------- */
.perm{display:none;position:fixed;inset:0;z-index:90;align-items:center;justify-content:center;
  text-align:center;padding:1.5rem;opacity:1;transition:opacity .5s ease;
  background:radial-gradient(90% 70% at 50% 38%,#0c1233 0%,#050711 58%,#020308 100%)}
html.perm-on .perm{display:flex}
.perm.gone{opacity:0;pointer-events:none}
.perm::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(255,255,255,.03) 0 1px,transparent 1px 4px)}
.perm::after{content:"";position:absolute;left:0;right:0;top:0;height:30%;pointer-events:none;
  background:linear-gradient(180deg,transparent,rgba(125,243,255,.06),transparent);
  animation:perm-scan 5s linear infinite}
@keyframes perm-scan{from{transform:translateY(-100%)}to{transform:translateY(420%)}}
.pc{position:absolute;width:30px;height:30px;border:2px solid rgba(125,243,255,.55)}
.pc.tl{top:max(18px,env(safe-area-inset-top));left:18px;border-right:0;border-bottom:0}
.pc.tr{top:max(18px,env(safe-area-inset-top));right:18px;border-left:0;border-bottom:0}
.pc.bl{bottom:max(18px,env(safe-area-inset-bottom));left:18px;border-right:0;border-top:0}
.pc.br{bottom:max(18px,env(safe-area-inset-bottom));right:18px;border-left:0;border-top:0}
.perm-in{position:relative;z-index:1;max-width:34rem}
.perm-in > *{opacity:0;transform:translateY(10px);animation:perm-rise .7s ease forwards}
.perm-in > :nth-child(2){animation-delay:.12s}
.perm-in > :nth-child(3){animation-delay:.24s}
.perm-in > :nth-child(4){animation-delay:.36s}
.perm-in > :nth-child(5){animation-delay:.5s}
@keyframes perm-rise{to{opacity:1;transform:none}}
.eq{display:flex;gap:5px;align-items:flex-end;justify-content:center;height:34px;margin-bottom:1.1rem}
.eq i{display:block;width:4px;height:100%;background:var(--glow);box-shadow:0 0 10px var(--glow);
  transform-origin:bottom;transform:scaleY(.2);animation:perm-eq 1.1s ease-in-out infinite}
.eq i:nth-child(2){animation-duration:.8s;animation-delay:-.3s}
.eq i:nth-child(3){animation-duration:1.3s;animation-delay:-.6s}
.eq i:nth-child(4){animation-duration:.9s;animation-delay:-.15s}
.eq i:nth-child(5){animation-duration:1.2s;animation-delay:-.45s}
@keyframes perm-eq{0%,100%{transform:scaleY(.2)}50%{transform:scaleY(1)}}
.perm-k{margin:0 0 .5rem;color:var(--glow);font-size:.8rem;font-weight:700;letter-spacing:.5em;padding-left:.5em}
.perm-t{margin:0;font-size:clamp(1.1rem,5.3vw,2.3rem);font-weight:900;letter-spacing:.04em;line-height:1.4;text-wrap:balance;
  text-shadow:0 0 22px rgba(125,243,255,.4)}
.perm-s{margin:.7rem 0 0;color:var(--dim);font-size:1rem;letter-spacing:.08em}
.perm-btns{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-top:2.3rem}
.pb{appearance:none;border:0;font:inherit;cursor:pointer;min-width:9.5rem;padding:.8rem 1.8rem;
  display:flex;flex-direction:column;align-items:center;line-height:1.25;
  clip-path:polygon(14px 0,100% 0,calc(100% - 14px) 100%,0 100%);
  transition:filter .2s,transform .2s,background .2s,color .2s}
.pb span{font-weight:900;font-size:1.15rem;letter-spacing:.25em;padding-left:.25em}
.pb small{font-size:.62rem;letter-spacing:.35em;opacity:.75}
.pb.yes{background:linear-gradient(135deg,#7df3ff,#1a8cff);color:#04101f}
.pb.no{background:rgba(154,163,214,.16);color:var(--dim)}
.pb:hover{filter:brightness(1.18);transform:translateY(-2px)}
.pb:active{transform:translateY(0) scale(.97)}
.pb:focus-visible{box-shadow:inset 0 0 0 2px #fff}
@media (prefers-reduced-motion:reduce){
  .perm::after,.eq i{animation:none}
  .eq i{transform:scaleY(.6)}
  .perm-in > *{animation:none;opacity:1;transform:none}
  .perm{transition:none}
}

/* ---------- サウンド設定タブ ---------- */
.sw{display:flex;align-items:center;justify-content:space-between;padding:.8rem 1.1rem;margin-bottom:1rem;
  border:1px solid var(--line);border-radius:14px;background:rgba(20,26,69,.82)}
.sw-t{font-weight:700}
.tgl{font:inherit;cursor:pointer;border:1px solid var(--line);border-radius:999px;padding:.25rem 1.1rem;
  background:transparent;color:var(--dim);font-weight:900;letter-spacing:.1em}
.tgl[aria-pressed=true]{background:var(--glow);border-color:var(--glow);color:#0a0e2a}
.subtabs{display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:1rem}
.subtabs button{font:inherit;cursor:pointer;border:1px solid var(--line);border-radius:999px;
  padding:.35rem .95rem;background:rgba(20,26,69,.6);color:var(--dim);font-weight:700}
.subtabs button[aria-selected=true]{color:var(--ink);border-color:var(--glow)}
.sub[hidden]{display:none}
.sub h2{margin:.2rem 0 .3rem;font-size:1.05rem}
.s-hint{margin:0 0 .9rem;color:#c3caf0;font-size:.85rem;text-shadow:0 1px 6px rgba(10,14,42,.95)}
.songs{list-style:none;margin:0;padding:0;display:grid;gap:.6rem}
.songs li{display:flex;gap:.5rem}
.song{flex:1;min-width:0;display:flex;align-items:center;gap:.8rem;text-align:left;font:inherit;cursor:pointer;
  padding:.8rem 1rem;border:1px solid var(--line);border-radius:14px;background:rgba(20,26,69,.82);
  color:var(--ink);transition:border-color .2s,box-shadow .2s}
.song:hover{border-color:var(--glow)}
.song[aria-pressed=true]{border-color:var(--glow);box-shadow:0 0 16px rgba(125,243,255,.25)}
.song[disabled],.pv[disabled]{opacity:.45;cursor:not-allowed}
.song:focus-visible,.pv:focus-visible,.tgl:focus-visible,.subtabs button:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
.s-main{flex:1;min-width:0}
.s-title{display:block;font-weight:700}
.s-note{display:block;color:var(--dim);font-size:.85rem}
.s-badge{display:none;flex:none;padding:.1rem .6rem;border-radius:999px;font-size:.75rem;font-weight:700;
  background:var(--glow);color:#0a0e2a}
.s-badge.off{display:inline-block;background:transparent;border:1px solid var(--line);color:var(--dim)}
.song[aria-pressed=true] .s-badge:not(.off){display:inline-block}
.pv{flex:none;width:3.2rem;font:inherit;cursor:pointer;border:1px solid var(--line);border-radius:14px;
  background:rgba(20,26,69,.82);color:var(--ink)}
.pv:hover{border-color:var(--glow)}
.pv[aria-pressed=true]{background:var(--glow);border-color:var(--glow);color:#0a0e2a}
.s-msg{min-height:1.5em;margin:.8rem 0 0;color:var(--glow);font-size:.9rem;text-shadow:0 1px 6px rgba(10,14,42,.95)}
.vols{display:grid;gap:.5rem;margin-bottom:1rem;padding:.8rem 1.1rem;border:1px solid var(--line);border-radius:14px;background:rgba(20,26,69,.82)}
.vol{display:grid;grid-template-columns:minmax(6.5rem,9.5rem) 1fr 3rem;align-items:center;gap:.8rem}
.vol-t{font-weight:700;font-size:.9rem}
.vol output{text-align:right;color:var(--dim);font-size:.85rem;font-variant-numeric:tabular-nums}
.vol input[type=range]{width:100%;min-width:0;accent-color:var(--glow);cursor:pointer;pointer-events:auto;margin:0;height:1.6rem}
.vol input[type=range]:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
.s-tag{display:inline-block;margin-top:.3rem;padding:.05rem .55rem;border:1px solid var(--glow);border-radius:999px;
  color:var(--glow);font-size:.7rem;font-weight:700;letter-spacing:.05em}
"""

# OP画面の背景に動画を敷く部分。
# op.mp4 は背景が不透明な白で書き出されているので、ロゴ側を「乗算」で重ねて白を透かす
# (白 × 動画 = 動画のまま / 黒い文字 × 動画 = 黒いまま)。
# .gate に has-motion が付いている間だけ動画が見える。付いていなければ今まで通りの白背景。
MOTION_CSS = """
.gate{overflow:hidden}
.gate > .op,.gate > .hint{position:relative;z-index:1}
.op-motion{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;z-index:0;
  pointer-events:none;opacity:0;transition:opacity .8s ease;
  transform:scale(1.1);filter:blur(__BLUR__px)}
.op-veil{position:absolute;inset:0;z-index:0;pointer-events:none;opacity:0;
  background:rgba(255,255,255,__VEIL__);transition:opacity .8s ease}
.gate.has-motion .op-motion,.gate.has-motion .op-veil{opacity:1}
.gate.has-motion .op{mix-blend-mode:multiply}
@media (prefers-reduced-motion:reduce){.op-motion,.op-veil{display:none}.gate.has-motion .op{mix-blend-mode:normal}}
"""



# 壁紙の切り替え: 起動時に保存した壁紙へ差し替え (読み込み待ちより前) + 画面設定の「壁紙」の操作
WALL_JS = r"""
(() => {
  let cfg = null;
  try { cfg = JSON.parse(document.getElementById('wall-cfg').textContent); } catch (e) { return; }
  const list = cfg.list || [];
  if (!list.length) return;
  const KEY = 'osaito-wall';
  const find = (id) => list.find((w) => w.id === id) || null;
  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { /* 保存できない環境 */ }
  let cur = find(saved) || find(cfg.def) || list[0];
  const el = () => document.querySelector('.wall');

  function make(w, lazy) {
    if (w.kind === 'video') {
      const v = document.createElement('video');
      v.className = 'wall';
      v.muted = true; v.loop = true;
      v.setAttribute('playsinline', ''); v.setAttribute('disablepictureinpicture', ''); v.setAttribute('aria-hidden', 'true');
      if (lazy) { v.dataset.src = w.src; v.preload = 'none'; }   // 読み込み待ち画面が、全部ダウンロードしてから再生する
      else { v.preload = 'auto'; v.src = w.src; v.autoplay = true; }
      return v;
    }
    const i = document.createElement('img');
    i.className = 'wall'; i.alt = ''; i.setAttribute('aria-hidden', 'true'); i.src = w.src;
    return i;
  }
  function drop(old) {
    if (old && old.tagName === 'VIDEO') { old.removeAttribute('src'); old.load(); }   // 古い動画の再生と通信を止める
    if (old) old.remove();
  }

  // 起動時: 最初の壁紙と違う壁紙が選ばれていたら、読み込みが始まる前に差し替える
  if (cur.id !== cfg.def) {
    const old = el();
    if (old) { old.replaceWith(make(cur, !!cfg.gate)); }
  }

  // 切り替え (新しい壁紙が表示できるようになってから、ふわっと入れ替える)
  function apply(w, done) {
    const old = el();
    const n = make(w, false);
    n.style.opacity = '0';
    n.style.transition = 'opacity .6s ease';
    let fin = false;
    const show = (ok) => {
      if (fin) return; fin = true;
      if (!ok) { drop(n.tagName === 'VIDEO' ? n : null); done(false); return; }
      if (old) old.after(n); else document.body.prepend(n);
      requestAnimationFrame(() => requestAnimationFrame(() => { n.style.opacity = '1'; }));
      if (n.tagName === 'VIDEO') { const p = n.play(); if (p && p.catch) p.catch(() => {}); }
      setTimeout(() => drop(old), 700);
      done(true);
    };
    n.addEventListener(n.tagName === 'VIDEO' ? 'canplay' : 'load', () => show(true), { once: true });
    n.addEventListener('error', () => show(false), { once: true });
    setTimeout(() => show(true), 20000);   // 遅いときは、待たずに出す
  }

  // 止まった動画を再生し直す (タブの切り替え・省電力モード対策)
  const resume = () => {
    const v = el();
    if (v && v.tagName === 'VIDEO' && v.src && v.paused && !document.hidden) { const p = v.play(); if (p && p.catch) p.catch(() => {}); }
  };
  document.addEventListener('visibilitychange', resume);
  window.addEventListener('pageshow', resume);
  window.addEventListener('pointerdown', resume, { passive: true });

  function ui() {
    const btns = [...document.querySelectorAll('.song[data-kind="wall"]')];
    const msg = document.querySelector('.w-msg');
    const mark = () => btns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.id === cur.id)));
    mark();
    btns.forEach((b) => b.addEventListener('click', () => {
      if (b.disabled) return;
      const w = find(b.dataset.id);
      if (!w) return;
      const title = b.querySelector('.s-title').textContent;
      if (w.id === cur.id) { if (msg) msg.textContent = '「' + title + '」はいま使っている壁紙です。'; return; }
      if (msg) msg.textContent = '「' + title + '」を読み込んでいます…';
      apply(w, (ok) => {
        if (!msg) return;
        if (!ok) { msg.textContent = '「' + title + '」を読み込めませんでした。元の壁紙のままです。'; return; }
        cur = w;
        let kept = true;
        try { localStorage.setItem(KEY, w.id); } catch (e) { kept = false; }
        mark();
        msg.textContent = '「' + title + '」に切り替えました。' + (kept ? '次にサイトを開いたときも、この壁紙になります。' : '(この端末では保存できないため、ページを閉じると元に戻ります)');
      });
    }));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ui); else ui();
})();
"""


def motion_css() -> str:
    return (MOTION_CSS
            .replace("__BLUR__", f"{max(0.0, float(OP_MOTION_BLUR)):g}")
            .replace("__VEIL__", f"{min(1.0, max(0.0, float(OP_MOTION_VEIL))):g}"))

PERM_HTML = """<div class="perm" role="dialog" aria-modal="true" aria-labelledby="perm-t">
  <span class="pc tl"></span><span class="pc tr"></span><span class="pc bl"></span><span class="pc br"></span>
  <div class="perm-in">
    <div class="eq" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
    <p class="perm-k">SOUND</p>
    <h2 class="perm-t" id="perm-t">このサイトでは音楽が流れます</h2>
    <p class="perm-s">音楽の再生を許可しますか？</p>
    <div class="perm-btns">
      <button type="button" class="pb yes" data-perm="yes"><span>はい</span><small>YES</small></button>
      <button type="button" class="pb no" data-perm="no"><span>いいえ</span><small>NO</small></button>
    </div>
  </div>
</div>"""

# 許可画面 → ロード画面の曲 → (入場) → メイン画面の曲 の流れと、サウンド設定の動き
SOUND_JS = r"""
(() => {
  const root = document.documentElement;
  const unlock = () => {
    root.classList.remove('perm-on');
    if (window.__permResolve) window.__permResolve();
  };
  try {
    const cfg = JSON.parse(document.getElementById('sound-cfg').textContent);
    const perm = document.querySelector('.perm');
    const enter = document.getElementById('enter');
    const toggle = document.getElementById('music-toggle');
    const songBtns = [...document.querySelectorAll('.song[data-kind="op"]')];
    const mainBtns = [...document.querySelectorAll('.song[data-kind="main"]')];
    const pvBtns = [...document.querySelectorAll('.pv')];
    const KEY = 'osaito-op-song', MKEY_SONG = 'osaito-main-song', UKEY = 'osaito-unify';
    // ---- 音量 (サウンド設定のスライダー。端末に覚えておく) ----
    const VKEY_OP = 'osaito-vol-op', VKEY_MAIN = 'osaito-vol-main';
    const clamp01 = (n) => Math.max(0, Math.min(1, n));
    const loadVol = (k, def) => {
      try { const v = parseFloat(localStorage.getItem(k)); if (isFinite(v)) return clamp01(v); } catch (e) { /* 保存できない環境 */ }
      return def;
    };
    let opVol = loadVol(VKEY_OP, cfg.opVolume);
    let mainVol = loadVol(VKEY_MAIN, cfg.mainVolume);

    // iPhone は audio.volume を無視するので、音量の変化は WebAudio で行う。
    // (index.html を file:// で直接開いたときは WebAudio が無音になるので、その場合だけ volume を使う)
    const AC = window.AudioContext || window.webkitAudioContext;
    const useWebAudio = !!AC && location.protocol !== 'file:';
    let ctx = null, musicOn = false, decided = false;
    let opTrack = null, mainTrack = null, prev = null;
    const previews = new Map();

    function ensureCtx() {
      if (!useWebAudio) return;
      if (!ctx) { try { ctx = new AC(); } catch (e) { ctx = null; } }
      if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
    }

    function makeTrack(src, loop) {
      const el = new Audio();
      el.preload = 'auto';
      el.loop = loop;
      el.src = src;
      const t = { el, gain: null, level: 0, timer: 0, doneTimer: 0 };
      if (ctx) {
        try {
          const node = ctx.createMediaElementSource(el);
          t.gain = ctx.createGain();
          t.gain.gain.value = 0;
          node.connect(t.gain);
          t.gain.connect(ctx.destination);
        } catch (e) { t.gain = null; }
      }
      if (!t.gain) el.volume = 0;
      return t;
    }

    // 音量を sec 秒かけて to (0〜1) にする。終わったら done を呼ぶ
    function fade(t, to, sec, done) {
      clearInterval(t.timer);
      clearTimeout(t.doneTimer);
      const from = t.level;
      t.level = to;
      if (t.gain) {
        const g = t.gain.gain, now = ctx.currentTime;
        g.cancelScheduledValues(now);
        g.setValueAtTime(g.value, now);
        g.linearRampToValueAtTime(to, now + Math.max(sec, 0.01));
      } else {
        const t0 = performance.now();
        t.timer = setInterval(() => {
          const k = sec <= 0 ? 1 : Math.min(1, (performance.now() - t0) / (sec * 1000));
          t.el.volume = Math.max(0, Math.min(1, from + (to - from) * k));
          if (k >= 1) clearInterval(t.timer);
        }, 40);
      }
      if (done) t.doneTimer = setTimeout(done, sec * 1000);
    }

    function start(t, vol, sec) {
      const p = t.el.play();
      if (p && p.catch) p.catch(() => {});
      fade(t, vol, sec);
    }
    function stop(t, sec) { fade(t, 0, sec, () => t.el.pause()); }

    // iPhone 対策: 「はい」を押した瞬間に一度だけ再生して止めておくと、あとで自動で鳴らせる
    function prime(t) {
      const p = t.el.play();
      if (p && p.then) p.then(() => { t.el.pause(); t.el.currentTime = 0; }).catch(() => {});
    }

    // ---- オープニング曲の選択 (選んだ曲は端末に覚えておく) ----
    const songs = songBtns.filter((b) => !b.disabled).map((b) => ({ id: b.dataset.id, src: b.dataset.src }));
    let chosen = null;
    try { chosen = localStorage.getItem(KEY); } catch (e) { /* 保存できない環境 */ }
    const pick = () => songs.find((s) => s.id === chosen) || songs[0] || null;
    const markSelected = () => {
      const cur = pick();
      songBtns.forEach((b) => b.setAttribute('aria-pressed', String(!!cur && b.dataset.id === cur.id)));
    };
    const say = (btn, text) => {
      const sub = btn.closest('.sub');
      const m = sub ? sub.querySelector('.s-msg') : null;
      if (m) m.textContent = text;
    };

    // ---- メイン画面の曲の選択 / オープニングとの一体化 (どちらも端末に覚えておく) ----
    const mainSongs = mainBtns.filter((b) => !b.disabled).map((b) => ({ id: b.dataset.id, src: b.dataset.src }));
    let mainChosen = null;
    try { mainChosen = localStorage.getItem(MKEY_SONG); } catch (e) { /* 保存できない環境 */ }
    const pickMain = () => mainSongs.find((s) => s.id === mainChosen) || mainSongs[0] || null;
    const markMain = () => {
      const cur = pickMain();
      mainBtns.forEach((b) => b.setAttribute('aria-pressed', String(!!cur && b.dataset.id === cur.id)));
    };
    let unified = false;
    try { unified = localStorage.getItem(UKEY) === 'on'; } catch (e) { /* 保存できない環境 */ }
    const uToggle = document.getElementById('unify-toggle');
    const syncUnify = () => {
      if (!uToggle) return;
      uToggle.setAttribute('aria-pressed', String(unified));
      uToggle.textContent = unified ? 'ON' : 'OFF';
    };
    // 入場後のメイン画面で流れる曲。一体化のときは、オープニング曲がそのまま続く
    const bgm = () => (unified && opTrack) ? opTrack : mainTrack;

    // ---- 特殊モーション: 選ばれている曲に動画が設定されていたら、OP画面の背景で流す ----
    const gate = document.querySelector('.gate');
    const mVid = document.querySelector('.op-motion');
    const mToggle = document.getElementById('motion-toggle');
    const mMsg = document.querySelector('.m-msg');
    const MKEY = 'osaito-op-motion';
    const motions = cfg.motions || {};
    const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let motionOn = true;  // 初期はON
    try { if (localStorage.getItem(MKEY) === 'off') motionOn = false; } catch (e) { /* 保存できない環境 */ }

    function syncMotionToggle() {
      if (!mToggle) return;
      mToggle.setAttribute('aria-pressed', String(motionOn));
      mToggle.textContent = motionOn ? 'ON' : 'OFF';
    }

    // いま選ばれている曲に合わせて、背景動画を出す/消す。動画が再生できる状態になったら解決する Promise を返す
    function applyMotion() {
      if (!gate || !mVid) return Promise.resolve();
      const cur = pick();
      const src = motionOn && !reduceMotion && cur ? (motions[cur.id] || '') : '';
      if (!src) {
        gate.classList.remove('has-motion');  // 白背景に戻る (消えきってから動画を止める)
        setTimeout(() => { if (!gate.classList.contains('has-motion')) mVid.pause(); }, 900);
        return Promise.resolve();
      }
      return new Promise((resolve) => {
        let fin = false;
        const ok = () => { if (fin) return; fin = true; clearTimeout(tm); resolve(); };
        const tm = setTimeout(ok, 12000);  // 重すぎるときは、待たずに先へ進む
        const go = () => {
          try { mVid.currentTime = 0; } catch (e) { /* まだ読み込み中 */ }
          const p = mVid.play();
          const show = () => { gate.classList.add('has-motion'); ok(); };
          if (p && p.then) p.then(show, ok); else show();
        };
        if (mVid.dataset.cur === src && mVid.readyState >= 3) { go(); return; }
        if (mVid.dataset.cur !== src) { mVid.dataset.cur = src; mVid.src = src; mVid.load(); }
        mVid.addEventListener('canplay', go, { once: true });
        mVid.addEventListener('error', ok, { once: true });
      });
    }

    if (enter) {
      enter.addEventListener('change', () => {
        if (enter.checked) {
          // 入場したら、見えなくなってから動画を止める (電池と通信の節約)
          setTimeout(() => { if (enter.checked && mVid) mVid.pause(); }, 900);
        } else {
          applyMotion();  // OP画面に戻ったら、いま選んでいる曲に合わせて出し直す
        }
      });
    }
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && mVid && gate && gate.classList.contains('has-motion') && enter && !enter.checked && mVid.paused) {
        const p = mVid.play(); if (p && p.catch) p.catch(() => {});
      }
    });

    if (mToggle) {
      mToggle.addEventListener('click', () => {
        motionOn = !motionOn;
        let saved = true;
        try { localStorage.setItem(MKEY, motionOn ? 'on' : 'off'); } catch (e) { saved = false; }
        syncMotionToggle();
        if (mMsg) {
          mMsg.textContent = (motionOn
            ? '特殊モーションをONにしました。特殊モーション付きの曲を選んでいると、オープニング画面の背景で動画が流れます。'
            : '特殊モーションをOFFにしました。オープニング画面は白い背景になります。')
            + (saved ? '' : '(この端末では保存できないため、ページを閉じると元に戻ります)');
        }
      });
    }

    function initTracks(withPrime) {
      ensureCtx();
      if (!opTrack) {
        const s = pick();
        if (s) { opTrack = makeTrack(s.src, true); opTrack.id = s.id; }
      }
      const m = pickMain();
      if (!mainTrack && m) {
        mainTrack = makeTrack(m.src, true);
        mainTrack.id = m.id;
        if (withPrime) prime(mainTrack);
      }
    }

    function syncToggle() {
      if (!toggle) return;
      toggle.setAttribute('aria-pressed', String(musicOn));
      toggle.textContent = musicOn ? 'ON' : 'OFF';
    }

    // ---- 最初の許可画面 ----
    function decide(on) {
      if (decided) return;
      decided = true;
      musicOn = on;
      window.__motionReady = applyMotion();
      if (on) {
        initTracks(true);
        if (opTrack) start(opTrack, opVol, cfg.opFadeIn);
      }
      syncToggle();
      perm.classList.add('gone');
      setTimeout(unlock, 520);  // 暗い画面が消えてから、OPアニメと読み込み待ちが始まる
    }

    // ---- 入場: ロード画面の曲を減衰させて、メイン画面の曲に交代 ----
    // 「オープニング画面に戻る」を押したときは逆に、メイン画面の曲を消して、オープニング曲をもう一度流す
    function restartOp() {
      const s = pick();  // サウンド設定で選び直した曲があれば、それを流す
      if (opTrack && (!s || opTrack.id !== s.id)) { opTrack.el.pause(); opTrack = null; }
      if (!opTrack && s) { opTrack = makeTrack(s.src, true); opTrack.id = s.id; }
      if (!opTrack) return;
      try { opTrack.el.currentTime = 0; } catch (e) { /* まだ読み込み中 */ }
      start(opTrack, opVol, cfg.opFadeIn);
    }
    if (enter) {
      enter.addEventListener('change', () => {
        if (!musicOn) return;
        if (enter.checked) {
          // 一体化: 曲はそのまま、音量だけメイン画面用に変える
          if (unified && opTrack) { start(opTrack, mainVol, cfg.mainFadeIn); return; }
          if (opTrack) stop(opTrack, cfg.opFadeOut);
          if (mainTrack) start(mainTrack, mainVol, cfg.mainFadeIn);
        } else {
          stopPreview(false);
          if (unified && opTrack) { start(opTrack, opVol, cfg.opFadeIn); return; }
          if (mainTrack) {
            fade(mainTrack, 0, cfg.opFadeOut, () => {
              mainTrack.el.pause();
              try { mainTrack.el.currentTime = 0; } catch (e) { /* まだ読み込み中 */ }
            });
          }
          restartOp();
        }
      });
    }

    // ---- サウンド設定: 音楽 ON/OFF ----
    if (toggle) {
      toggle.addEventListener('click', () => {
        if (musicOn) {
          musicOn = false;
          stopPreview(false);
          [opTrack, mainTrack].forEach((t) => { if (t) stop(t, 0.6); });
        } else {
          musicOn = true;
          initTracks(false);
          if (enter && enter.checked) { const b = bgm(); if (b) start(b, mainVol, 1.2); }
          else if (opTrack) start(opTrack, opVol, cfg.opFadeIn);
        }
        syncToggle();
      });
    }

    // ---- サウンド設定: 項目タブ (いまは「オープニング画面」だけ。増やしてもそのまま動く) ----
    const subBtns = [...document.querySelectorAll('.subtabs [data-sub]')];
    subBtns.forEach((b) => b.addEventListener('click', () => {
      const scope = b.closest('.panel') || document;  // サウンド設定と画面設定で、項目タブが混ざらないようにする
      scope.querySelectorAll('.subtabs [data-sub]').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
      scope.querySelectorAll('[data-sub-panel]').forEach((p) => { p.hidden = p.dataset.subPanel !== b.dataset.sub; });
    }));

    // ---- サウンド設定: 曲を選ぶ ----
    songBtns.forEach((b) => b.addEventListener('click', () => {
      if (b.disabled) return;
      chosen = b.dataset.id;
      let saved = true;
      try { localStorage.setItem(KEY, chosen); } catch (e) { saved = false; }
      markSelected();
      const title = b.querySelector('.s-title').textContent;
      const mo = motions[b.dataset.id] ? '(特殊モーション付き)' : '';
      say(b, saved
        ? '「' + title + '」を選びました' + mo + '。次にサイトを開いたとき、オープニングで流れます。'
        : '「' + title + '」を選びましたが、この端末では保存できないため、ページを閉じると元に戻ります。');
    }));

    // ---- サウンド設定: メイン画面の曲を選ぶ (いま流れている曲は、すぐ切り替わる) ----
    function swapMain() {
      const m = pickMain();
      if (mainTrack && (!m || mainTrack.id !== m.id)) {
        const old = mainTrack;
        mainTrack = null;
        fade(old, 0, 1.2, () => old.el.pause());
      }
      if (musicOn && !mainTrack && m) { ensureCtx(); mainTrack = makeTrack(m.src, true); mainTrack.id = m.id; }
    }
    mainBtns.forEach((b) => b.addEventListener('click', () => {
      if (b.disabled) return;
      mainChosen = b.dataset.id;
      let saved = true;
      try { localStorage.setItem(MKEY_SONG, mainChosen); } catch (e) { saved = false; }
      markMain();
      swapMain();
      const nowPlaying = musicOn && enter && enter.checked && !unified && !prev;
      if (nowPlaying && mainTrack) start(mainTrack, mainVol, 1.2);
      const title = b.querySelector('.s-title').textContent;
      say(b, '「' + title + '」を選びました。'
        + (unified ? '(いまはオープニングと一体化中なので、一体化をOFFにすると流れます)' : (nowPlaying ? 'メイン画面の曲を切り替えました。' : ''))
        + (saved ? '' : '(この端末では保存できないため、ページを閉じると元に戻ります)'));
    }));

    // ---- サウンド設定: オープニングとの一体化 ----
    if (uToggle) uToggle.addEventListener('click', () => {
      unified = !unified;
      let saved = true;
      try { localStorage.setItem(UKEY, unified ? 'on' : 'off'); } catch (e) { saved = false; }
      syncUnify();
      if (musicOn && enter && enter.checked && !prev) {  // メイン画面で曲が流れていたら、すぐ切り替える
        initTracks(false);
        const mt = mainTrack;
        if (unified && opTrack) {
          if (mt) fade(mt, 0, 1.2, () => mt.el.pause());
          start(opTrack, mainVol, 1.2);
        } else {
          if (opTrack) stop(opTrack, 1.2);
          swapMain();
          if (mainTrack) start(mainTrack, mainVol, 1.2);
        }
      }
      const um = document.querySelector('.u-msg');
      if (um) {
        um.textContent = (unified
          ? '一体化をONにしました。オープニングの曲が、メイン画面でもそのまま流れます。'
          : '一体化をOFFにしました。メイン画面では「メイン画面」で選んだ曲が流れます。')
          + (saved ? '' : '(この端末では保存できないため、ページを閉じると元に戻ります)');
      }
    });

    // ---- サウンド設定: 試し聴き (聴いている間はメイン画面の曲を止める) ----
    function stopPreview(restore) {
      if (!prev) return;
      const { t, btn } = prev;  // (prev.kind: 'op' | 'main')
      prev = null;
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = '▶';
      fade(t, 0, 0.3, () => { t.el.pause(); try { t.el.currentTime = 0; } catch (e) { /* まだ読み込み中 */ } });
      const b = bgm();
      if (restore && musicOn && b && enter && enter.checked) start(b, mainVol, 0.6);
    }
    pvBtns.forEach((btn) => btn.addEventListener('click', () => {
      if (btn.disabled) return;
      if (prev && prev.btn === btn) { stopPreview(true); return; }
      stopPreview(false);
      ensureCtx();
      let t = previews.get(btn.dataset.id);
      if (!t) {
        t = makeTrack(btn.dataset.src, false);
        previews.set(btn.dataset.id, t);
        t.el.addEventListener('ended', () => { if (prev && prev.t === t) stopPreview(true); });
      }
      try { t.el.currentTime = 0; } catch (e) { /* まだ読み込み中 */ }
      const kind = btn.dataset.kind === 'main' ? 'main' : 'op';
      prev = { t, btn, kind };
      btn.setAttribute('aria-pressed', 'true');
      btn.textContent = '■';
      const cur = bgm();
      if (cur) fade(cur, 0, 0.4, () => cur.el.pause());
      start(t, kind === 'main' ? mainVol : opVol, 0.4);
    }));

    // ---- サウンド設定: 音量スライダー (鳴っている曲には、動かしている間すぐ反映する) ----
    const volOp = document.getElementById('vol-op');
    const volMain = document.getElementById('vol-main');
    function bindVol(el, get, set, key, live) {
      if (!el) return;
      const out = el.parentElement.querySelector('output');
      const show = () => { if (out) out.textContent = Math.round(get() * 100) + '%'; };
      el.value = String(Math.round(get() * 100));
      show();
      el.addEventListener('input', () => {
        set(clamp01(Number(el.value) / 100));
        show();
        live();
      });
      el.addEventListener('change', () => {
        try { localStorage.setItem(key, String(get())); } catch (e) { /* 保存できない環境 */ }
      });
    }
    bindVol(volOp, () => opVol, (v) => { opVol = v; }, VKEY_OP, () => {
      // 鳴っているのは、オープニング曲か、試し聴き (入場後のオープニング曲は消えているので触らない)
      if (prev) { if (prev.kind !== 'main') fade(prev.t, opVol, 0.05); }
      else if (opTrack && !opTrack.el.paused && musicOn && !(enter && enter.checked)) fade(opTrack, opVol, 0.05);
    });
    bindVol(volMain, () => mainVol, (v) => { mainVol = v; }, VKEY_MAIN, () => {
      const b = bgm();
      if (prev) { if (prev.kind === 'main') fade(prev.t, mainVol, 0.05); }
      else if (b && !b.el.paused && musicOn && enter && enter.checked) fade(b, mainVol, 0.05);
    });

    // ---- 起動 ----
    syncToggle();
    syncMotionToggle();
    markSelected();
    markMain();
    syncUnify();
    if (!perm) { window.__motionReady = applyMotion(); unlock(); return; }
    const yes = perm.querySelector('[data-perm="yes"]');
    const no = perm.querySelector('[data-perm="no"]');
    if (yes) yes.addEventListener('click', () => decide(true));
    if (no) no.addEventListener('click', () => decide(false));
    if (yes) yes.focus({ preventScroll: true });
  } catch (e) {
    unlock();  // 何かあっても、サイトが見られなくなることはないようにする
  }
})();
"""


# ---------- ボタンの透明度 + ホバー演出 (右端から暗くなる・少し大きくなる) + カーソル効果音 ----------
def btn_css() -> str:
    a = min(100, max(0, int(BTN_ALPHA_DEFAULT))) / 100
    alpha_sel = ".list a,.song,.pv,.back,.vback,.subtabs button,.tabs label"   # 透明度スライダーの対象
    fx_sel = ".list a,.song,.pv,.back,.vback"   # 暗くなる・大きくなる演出は「画面の中のボタン」だけ (上のタブなどは対象外)
    return (
        f":root{{--btn-a:{a:g}}}"
        f"{alpha_sel}{{background-color:rgba(20,26,69,var(--btn-a))}}"
        f"{fx_sel}{{"
        # 右端から暗くなる影 (ホーム画面の左端の影と逆向き)。ふだんは幅0で見えない
        "background-image:linear-gradient(to left,rgba(0,0,0,.8),rgba(0,0,0,.4) 55%,rgba(0,0,0,0));"
        "background-repeat:no-repeat;background-position:right center;background-size:0% 100%;"
        "transition:background-size .45s ease,transform .25s ease,border-color .2s,box-shadow .2s}"
        ".sw,.vols{background-color:rgba(20,26,69,var(--btn-a))}"
        # 透明にしても文字が読めるように、うっすら影をつける
        ".list a,.song,.pv,.back,.vback,.subtabs button,.tabs label,.sw,.vols{text-shadow:0 1px 6px rgba(10,14,42,.9)}"
        ".tabs label{border-radius:10px 10px 0 0}"
        "@media (hover:hover){"
        ".list a:hover,.song:not(:disabled):hover,.pv:not(:disabled):hover,.back:hover,.vback:hover{"
        "background-size:100% 100%;transform:scale(1.03);border-color:var(--glow);position:relative;z-index:2}"
        ".tgl:not(:disabled):hover{transform:scale(1.06)}"
        ".tabs label:hover{color:var(--ink)}"
        ".subtabs button:hover{color:var(--ink);border-color:var(--glow)}}"
        ".list a:focus-visible,.song:focus-visible,.pv:focus-visible,.back:focus-visible,.vback:focus-visible{background-size:100% 100%}"
        ".tgl{transition:transform .25s ease,background .2s,border-color .2s}"
        # scale で大きくなっても左右が欠けないように、パネルの左右に余白を足す
        ".panel{padding-left:.7rem;padding-right:.7rem}"
        "@media (prefers-reduced-motion:reduce){"
        f"{fx_sel},.tgl{{transition:none}}"
        ".list a:hover,.song:hover,.pv:hover,.back:hover,.vback:hover,.tgl:hover{transform:none}}"
    )


# 画面設定「ボタン」のスライダー。--btn-a を書き換えて、端末(localStorage)に覚えておく
BTN_ALPHA_JS = r"""
(() => {
  const KEY = 'osaito-btn-alpha', DEF = __DEF__;
  const root = document.documentElement;
  const clamp = (n) => Math.min(100, Math.max(0, Math.round(n)));
  let v = DEF;
  try {
    const s = localStorage.getItem(KEY);
    if (s !== null) { const n = parseFloat(s); if (isFinite(n)) v = clamp(n); }
  } catch (e) { /* 保存できない環境 */ }
  const apply = (n) => root.style.setProperty('--btn-a', String(n / 100));
  apply(v);
  function ui() {
    const r = document.getElementById('btn-alpha');
    if (!r) return;
    const out = document.querySelector('output[for="btn-alpha"]');
    const rst = document.getElementById('btn-alpha-reset');
    const show = () => { r.value = String(v); if (out) out.textContent = v + '%'; };
    show();
    r.addEventListener('input', () => {
      v = clamp(parseFloat(r.value));
      apply(v);
      if (out) out.textContent = v + '%';
      try { localStorage.setItem(KEY, String(v)); } catch (e) { /* 保存できない環境 */ }
    });
    if (rst) rst.addEventListener('click', () => {
      v = DEF; apply(v); show();
      try { localStorage.removeItem(KEY); } catch (e) { /* 保存できない環境 */ }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ui); else ui();
})();
"""

# カーソルがボタンに乗ったときの効果音 (サウンド設定でON/OFF)。マウスのときだけ鳴らす
CURSOR_JS = r"""
(() => {
  let cfg = null;
  try { cfg = JSON.parse(document.getElementById('sound-cfg').textContent); } catch (e) { return; }
  const src = cfg.cursorSrc || '';
  const vol = typeof cfg.cursorVolume === 'number' ? Math.min(1, Math.max(0, cfg.cursorVolume)) : 0.5;
  const KEY = 'osaito-cursor-snd';
  let on = true;
  try { if (localStorage.getItem(KEY) === 'off') on = false; } catch (e) { /* 保存できない環境 */ }
  const tg = document.getElementById('cursor-toggle');
  const sync = () => {
    if (!tg) return;
    tg.setAttribute('aria-pressed', String(on && !!src));
    tg.textContent = (on && src) ? 'ON' : 'OFF';
  };
  sync();
  if (!src) { if (tg) tg.disabled = true; return; }   // cursol.mp3 が無いときは何もしない

  const POOL = 4, pool = [];
  let idx = 0, last = 0;
  for (let i = 0; i < POOL; i++) { const a = new Audio(src); a.preload = 'auto'; a.volume = vol; pool.push(a); }
  function ping() {
    const a = pool[idx++ % POOL];   // 素早く動かしても重なって鳴るように、何個か交代で使う
    try { a.currentTime = 0; const p = a.play(); if (p && p.catch) p.catch(() => {}); } catch (e) { /* 再生できない */ }
  }
  if (tg) tg.addEventListener('click', () => {
    on = !on; sync();
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch (e) { /* 保存できない環境 */ }
    if (on) ping();
  });

  const SEL = '.list a,.song,.pv,.back,.vback,.subtabs button,.tabs label,.tgl';
  const enter = document.getElementById('enter');
  document.addEventListener('pointerover', (e) => {
    if (!on || e.pointerType !== 'mouse') return;
    if (enter && !enter.checked) return;   // 入場前は鳴らさない
    const t = e.target && e.target.closest ? e.target.closest(SEL) : null;
    if (!t || t.disabled) return;
    if (e.relatedTarget && t.contains(e.relatedTarget)) return;   // ボタンの中で動いただけなら鳴らさない
    const now = performance.now();
    if (now - last < 50) return;
    last = now;
    ping();
  }, { passive: true });
})();
"""


def cursor_src() -> str:
    f = SIRYOU_DIR / CURSOR_SOUND
    return f"{SIRYOU_DIR.name}/{quote(CURSOR_SOUND)}" if CURSOR_SOUND and f.is_file() else ""


def cursor_row_html() -> str:
    miss = ""
    if not cursor_src():
        miss = (f'<p class="s-hint">siryou に {html.escape(CURSOR_SOUND)} を置くと使えるようになります。</p>')
    return (
        '<div class="sw"><span class="sw-t">カーソル効果音</span>'
        '<button type="button" class="tgl" id="cursor-toggle" aria-pressed="false">OFF</button></div>'
        '<p class="s-hint">ボタンにカーソルを合わせたときの音です(マウスのときだけ鳴ります)。</p>' + miss
    )


# ---------- ホームの文章 (home.txt) : Discord と同じ書き方が使える ----------
# home.txt に Discord のメッセージと同じ書き方で書くと、そのまま見た目になる。
#   # 大見出し / ## 中見出し / ### 小見出し / -# 小さい文字
#   **太字** *斜体* _斜体_ __下線__ ~~取り消し線~~ ||ネタバレ|| (組み合わせもOK: ***太字+斜体*** __**下線+太字**__)
#   `コード` / ```コードブロック``` (``` のあとに言語名を書いてもOK。色分けはしない)
#   > 引用 / >>> ここから最後まで全部引用
#   - 箇条書き / * 箇条書き / 1. 番号つき (先頭に半角スペース2つで1段ずつ深くなる)
#   [文字](https://...) / <https://...> / そのまま書いたURLもリンクになる
#   <t:UNIX秒:R> のような時刻表示 (:t :T :d :D :f :F :R。見ている人の時刻で出る)
#   <:名前:数字> / <a:名前:数字> のDiscordカスタム絵文字
#   \ を前につけると記号をそのまま表示 (例: \# あ  \*あ\*)
# ※ @メンション・#チャンネルの自動リンク・コードの色分けは、Discord側の仕組みなので再現できません
# 先頭の段落だけ大きく表示する今までの見た目を保つなら True、Discordと同じ大きさにするなら False
HOME_LEAD_FIRST = True

DMD_CSS = """
.dm{overflow-wrap:anywhere}
.dm p,.dm-t{margin:0}
.dm-gap{height:1em}
.dm-h1,.dm-h2,.dm-h3{font-weight:800;line-height:1.3;margin:.5em 0 .15em}
.dm-h1{font-size:1.75em}.dm-h2{font-size:1.4em}.dm-h3{font-size:1.15em}
.dm-sub{font-size:.8em;color:var(--dim);margin:.1em 0}
.dm-q{margin:.25em 0;padding:.05em 0 .05em .9em;border-left:4px solid rgba(154,163,214,.55)}
.dm-l{margin:.2em 0;padding-left:1.6em}
.dm-l .dm-l{margin:0}
.dm-l li{margin:.05em 0}
.dm-cb{margin:.35em 0;padding:.7em .9em;background:rgba(0,0,0,.5);border:1px solid var(--line);border-radius:8px;
  overflow-x:auto;white-space:pre;font:.9em/1.5 ui-monospace,Consolas,'Courier New',monospace;
  -webkit-user-select:text;user-select:text;pointer-events:auto}
.dm-cb code{font:inherit}
.dm-ic{padding:.1em .35em;background:rgba(0,0,0,.5);border:1px solid var(--line);border-radius:5px;
  font:.9em ui-monospace,Consolas,'Courier New',monospace;-webkit-user-select:text;user-select:text}
.dm a{color:var(--glow);text-decoration:none;pointer-events:auto}
.dm a:hover{text-decoration:underline}
.dm-sp{background:#1b2150;border-radius:4px;cursor:pointer;pointer-events:auto}
.dm-sp:not(.on),.dm-sp:not(.on) *{color:transparent!important;text-shadow:none!important;text-decoration-color:transparent!important}
.dm-sp:not(.on) img{opacity:0}
.dm-sp:not(.on) a{pointer-events:none}
.dm-sp.on{background:rgba(255,255,255,.12)}
.dm-ts{padding:0 .3em;background:rgba(255,255,255,.1);border-radius:4px}
.dm-emoji{width:1.4em;height:1.4em;vertical-align:-.3em;object-fit:contain}
"""

# ネタバレ (||...||) のクリックで表示 / 時刻 (<t:...>) を見ている人の時刻で表示
DMD_JS = r"""
(() => {
  const reveal = (e) => {
    const s = e.target.closest && e.target.closest('.dm-sp');
    if (s && !s.classList.contains('on')) { e.preventDefault(); e.stopPropagation(); s.classList.add('on'); return true; }
    return false;
  };
  document.addEventListener('click', reveal, true);
  document.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && reveal(e)) return;
  }, true);

  const L = 'ja-JP';
  const FMT = {
    t: { hour: '2-digit', minute: '2-digit' },
    T: { hour: '2-digit', minute: '2-digit', second: '2-digit' },
    d: { year: 'numeric', month: '2-digit', day: '2-digit' },
    D: { year: 'numeric', month: 'long', day: 'numeric' },
    f: { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' },
    F: { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long', hour: '2-digit', minute: '2-digit' },
  };
  const rel = (d) => {
    const sec = Math.round((d.getTime() - Date.now()) / 1000), a = Math.abs(sec);
    const r = new Intl.RelativeTimeFormat(L, { numeric: 'auto' });
    if (a < 60) return r.format(sec, 'second');
    if (a < 3600) return r.format(Math.round(sec / 60), 'minute');
    if (a < 86400) return r.format(Math.round(sec / 3600), 'hour');
    if (a < 2592000) return r.format(Math.round(sec / 86400), 'day');
    if (a < 31536000) return r.format(Math.round(sec / 2592000), 'month');
    return r.format(Math.round(sec / 31536000), 'year');
  };
  const els = [...document.querySelectorAll('.dm-ts')];
  const paint = () => {
    els.forEach((el) => {
      try {
        const d = new Date(parseInt(el.dataset.ts, 10) * 1000), st = el.dataset.st || 'f';
        if (isNaN(d.getTime())) return;
        el.title = d.toLocaleString(L, FMT.F);
        el.textContent = st === 'R' ? rel(d) : d.toLocaleString(L, FMT[st] || FMT.f);
      } catch (e) { /* 表示できない環境 */ }
    });
  };
  if (els.length) { paint(); if (els.some((e) => e.dataset.st === 'R')) setInterval(paint, 30000); }
})();
"""

# --- Discord記法 → HTML (書いた文字は必ずエスケープする。リンクは http(s) だけ) ---
_DM_ESC = re.compile(r"\\([^0-9A-Za-z\s])")
_DM_CODE = re.compile(r"(`+)([\s\S]*?[^`])\1(?!`)")
_DM_SPOILER = re.compile(r"\|\|([\s\S]+?)\|\|")
_DM_BOLD = re.compile(r"\*\*((?:\\[\s\S]|[^\\])+?)\*\*(?!\*)")
_DM_UNDER = re.compile(r"__((?:\\[\s\S]|[^\\])+?)__(?!_)")
_DM_STRIKE = re.compile(r"~~((?:\\[\s\S]|[^\\])+?)~~")
_DM_EM_AST = re.compile(r"\*(?=\S)((?:\*\*|\\[\s\S]|\s+(?:\\[\s\S]|[^\s\*\\]|\*\*)|[^\s\*\\])+?)\*(?!\*)")
_DM_EM_UND = re.compile(r"_((?:__|\\[\s\S]|[^\\_])+?)_\b", re.ASCII)   # Discordと同じく英数字の中の _ は斜体にしない
_DM_LINK = re.compile(r"\[((?:\[[^\]]*\]|[^\[\]])+)\]\(\s*<?(https?://[^\s<>)]+)>?(?:\s+\"([^\"]*)\")?\s*\)")
_DM_AUTO = re.compile(r"<(https?://[^\s<>]+)>")
_DM_URL = re.compile(r"https?://[^\s<>]*[^\s<>.,:;\"'!?)\]}、。」』）]")
_DM_TS = re.compile(r"<t:(-?\d{1,13})(?::([tTdDfFR]))?>")
_DM_EMOJI = re.compile(r"<(a?):([A-Za-z0-9_]{2,32}):(\d{15,25})>")
_DM_FENCE = re.compile(r"```(?:([A-Za-z0-9_+\-.#]+)\n)?\n*([\s\S]+?)\n*```")
_DM_HEAD = re.compile(r"(#{1,3}) (\S.*)$")
_DM_SUB = re.compile(r"-# (\S.*)$")
_DM_LIST = re.compile(r"( *)([-*]|\d{1,9}\.) +(\S.*)$")


def _dm_link(url: str, inner: str, title: str = "") -> str:
    t = f' title="{html.escape(title, quote=True)}"' if title else ""
    return f'<a href="{html.escape(url, quote=True)}"{t} target="_blank" rel="noopener noreferrer">{inner}</a>'


def _dm_inline(s: str, in_link: bool = False) -> str:
    out, buf, i, n = [], [], 0, len(s)

    def flush():
        if buf:
            out.append(html.escape("".join(buf)))
            buf.clear()

    while i < n:
        c, m, h = s[i], None, None
        if c == "\\":
            m = _DM_ESC.match(s, i)
            if m:
                buf.append(m.group(1))
                i = m.end()
                continue
        elif c == "`":
            m = _DM_CODE.match(s, i)
            if m:
                h = f'<code class="dm-ic">{html.escape(m.group(2))}</code>'
        elif c == "|":
            m = _DM_SPOILER.match(s, i)
            if m:
                h = f'<span class="dm-sp" tabindex="0" role="button" aria-label="ネタバレ (押すと表示)">{_dm_inline(m.group(1), in_link)}</span>'
        elif c == "*":
            m = _DM_BOLD.match(s, i)
            if m:
                h = f"<strong>{_dm_inline(m.group(1), in_link)}</strong>"
            else:
                m = _DM_EM_AST.match(s, i)
                if m:
                    h = f"<em>{_dm_inline(m.group(1), in_link)}</em>"
        elif c == "_":
            m = _DM_UNDER.match(s, i)
            if m:
                h = f"<u>{_dm_inline(m.group(1), in_link)}</u>"
            else:
                m = _DM_EM_UND.match(s, i)
                if m:
                    h = f"<em>{_dm_inline(m.group(1), in_link)}</em>"
        elif c == "~":
            m = _DM_STRIKE.match(s, i)
            if m:
                h = f"<s>{_dm_inline(m.group(1), in_link)}</s>"
        elif c == "[" and not in_link:
            m = _DM_LINK.match(s, i)
            if m:
                h = _dm_link(m.group(2), _dm_inline(m.group(1), True), m.group(3) or "")
        elif c == "<":
            m = _DM_AUTO.match(s, i)
            if m and not in_link:
                h = _dm_link(m.group(1), html.escape(m.group(1)))
            elif not m:
                m = _DM_TS.match(s, i)
                if m:
                    h = (f'<time class="dm-ts" data-ts="{m.group(1)}" data-st="{m.group(2) or "f"}">'
                         f'{html.escape(m.group(0))}</time>')
                else:
                    m = _DM_EMOJI.match(s, i)
                    if m:
                        ext = "gif" if m.group(1) else "png"
                        h = (f'<img class="dm-emoji" alt=":{html.escape(m.group(2))}:" loading="lazy" '
                             f'src="https://cdn.discordapp.com/emojis/{m.group(3)}.{ext}?size=64">')
        elif c == "h" and not in_link:
            m = _DM_URL.match(s, i)
            if m:
                h = _dm_link(m.group(0), html.escape(m.group(0)))
        elif c == "\n":
            flush()
            out.append("<br>")
            i += 1
            continue
        if h is not None:
            flush()
            out.append(h)
            i = m.end()
        else:
            buf.append(c)
            i += 1
    flush()
    return "".join(out)


def _dm_list(items) -> str:
    out, stack = [], []
    for indent, tag, num, text in items:
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if stack and indent == stack[-1][0]:
            out.append("</li>")
        else:
            start = f' start="{num}"' if tag == "ol" and num != 1 else ""
            out.append(f'<{tag} class="dm-l"{start}>')
            stack.append((indent, tag))
        out.append("<li>" + _dm_inline(text))
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out)


def _dm_text(src: str, lead: bool = False):
    """コードブロックを含まない文章を HTML にする。 >>> があれば (html, 引用に入る残りの文章) を返す"""
    lines = src.split("\n")
    out, para, i = [], [], 0

    def flush():
        nonlocal lead
        if para:
            tag = '<p class="lead dm-t">' if (lead and not out) else '<div class="dm-t">'
            out.append(tag + _dm_inline("\n".join(para)) + ("</p>" if tag.startswith("<p") else "</div>"))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        m = None
        if ln.strip() == "":
            flush()
            out.append('<div class="dm-gap"></div>')
        elif ln.startswith(">>> "):
            flush()
            return "".join(out), "\n".join([ln[4:]] + lines[i + 1:])
        elif ln.startswith("> "):
            flush()
            inner = []
            while i < len(lines) and lines[i].startswith("> "):
                inner.append(lines[i][2:])
                i += 1
            out.append('<blockquote class="dm-q">' + _dm_text("\n".join(inner))[0] + "</blockquote>")
            continue
        elif (m := _DM_HEAD.match(ln)):
            flush()
            k = len(m.group(1))
            out.append(f'<div class="dm-h{k}" role="heading" aria-level="{k + 1}">{_dm_inline(m.group(2))}</div>')
        elif (m := _DM_SUB.match(ln)):
            flush()
            out.append(f'<div class="dm-sub">{_dm_inline(m.group(1))}</div>')
        elif _DM_LIST.match(ln):
            flush()
            items = []
            while i < len(lines) and (m := _DM_LIST.match(lines[i])):
                mark = m.group(2)
                ordered = mark[0].isdigit()
                items.append((len(m.group(1)), "ol" if ordered else "ul", int(mark[:-1]) if ordered else 1, m.group(3)))
                i += 1
            out.append(_dm_list(items))
            continue
        else:
            para.append(ln.rstrip())
        i += 1
    flush()
    return "".join(out), None


def discord_md(text: str, lead: bool = False) -> str:
    """Discord のメッセージと同じ書き方の文章を HTML にする"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    parts, pos = [], 0
    for m in _DM_FENCE.finditer(text):
        parts.append(("t", text[pos:m.start()], None))
        parts.append(("c", m.group(0), m))
        pos = m.end()
    parts.append(("t", text[pos:], None))
    out = []
    for idx, (kind, src, m) in enumerate(parts):
        if kind == "c":
            lang = html.escape(m.group(1) or "", quote=True)
            out.append(f'<pre class="dm-cb" data-lang="{lang}"><code>{html.escape(m.group(2))}</code></pre>')
            continue
        # コードブロックの前後の「行末の改行」は空行ではないので取り除く
        if idx > 0 and src.startswith("\n"):
            src = src[1:]
        if idx < len(parts) - 1 and src.endswith("\n"):
            src = src[:-1]
        if src == "":
            continue
        h, rest = _dm_text(src, lead and not out)
        out.append(h)
        if rest is not None:   # >>> : ここから最後まで全部が引用になる
            full = rest + "".join(p[1] for p in parts[idx + 1:])
            out.append('<blockquote class="dm-q">' + discord_md(full) + "</blockquote>")
            break
    return "".join(out)


def home_html() -> str:
    """home.txt を読んで、Discord と同じ書き方で表示する。ファイルが無いときは、いまの文章で作る"""
    if not HOME_FILE.is_file():
        HOME_FILE.write_text(HOME_DEFAULT, encoding="utf-8")
        print("home.txt を新しく作りました (ホーム画面の文章はこのファイルを編集します)")
    text = HOME_FILE.read_text(encoding="utf-8-sig")
    return '<div class="dm">' + discord_md(text, HOME_LEAD_FIRST) + "</div>"


# ---------- 布教部屋 (fukyou.txt) ----------
# 「布教部屋」タブ → 1段目の一覧 (部屋) → 2段目の一覧 (項目) → 詳細ページ (左に画像・下に文字)。
# 内容は全部 fukyou.txt に書く (build.py は触らなくてよい)。書き方は fukyou.txt の先頭の注釈を見る。
# カードにカーソルを合わせると、siryou に置いた画像がじわっと出てくる。
FUKYOU_FILE = BASE / "fukyou.txt"

FUKYOU_DEFAULT = """// ===== 布教部屋の中身はこのファイルだけで編集します (保存すると自動で公開サイトに反映) =====
// ・// で始まる行は画面に出ません (メモ用)。最初の「@部屋」より上の行も出ません
// ・画像は siryou フォルダに置いて、ファイル名だけ書きます (.png .jpg .gif .webp など)
// ・画像と小さい説明は省略OK。説明だけ書きたいときは「名前 | | 説明」のように、画像のところを空けておく
// ・並べ替え・削除は、「@」で始まる行から次の「@」の手前までを、まるごと動かす / 消すだけ
//
// 1段目のタブ  : @部屋 名前 | 画像ファイル名 | 小さい説明
//                その下に書いた文章 = その部屋の紹介文 (省略OK)
// 2段目のタブ  : @項目 名前 | 画像ファイル名 | 小さい説明 | 詳細ページ用の画像 (省略OK。省略すると左の画像を使う)
//                その下に書いた文章 = 詳細ページの文章 (Discordと同じ書き方が使えます)
// 区切りの | は、全角の ｜ でもOK

@部屋 サンプル部屋1 | logo.png | ここに説明を書く
この部屋の紹介文です。**Discordの書き方**が使えます。

@項目 サンプル作品A | logo.png | 小さい説明
# 見出し
詳細ページの文章です。画像は左に、文字はその下に出ます。

- おすすめポイント1
- おすすめポイント2

@項目 サンプル作品B | logo.png |
説明なしの項目です。

@部屋 サンプル部屋2 | logo.png | 2つ目の部屋

@項目 サンプル作品C | logo.png | 小さい説明
ここに文章を書く。
"""

_FK_CACHE = None


def _fk_img(name: str, missing: list):
    """siryou の中の画像ファイル名 → ページから見えるURL。無ければ None (missing に覚えておく)"""
    name = name.strip().replace("\\", "/")
    if not name:
        return None
    p = SIRYOU_DIR / name
    if ".." in name or not p.is_file() or p.suffix.lower() not in IMAGE_EXT:
        if name not in missing:
            missing.append(name)
        return None
    return "siryou/" + quote(name)


def _fk_rooms():
    """fukyou.txt を読んで [{name, desc, img, lines, items:[{name, desc, img, img2, lines}]}] にする"""
    global _FK_CACHE
    if _FK_CACHE is not None:
        return _FK_CACHE
    if not FUKYOU_FILE.is_file():
        FUKYOU_FILE.write_text(FUKYOU_DEFAULT, encoding="utf-8")
        print("fukyou.txt を新しく作りました (布教部屋の中身はこのファイルを編集します)")
    text = FUKYOU_FILE.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    missing, rooms, room, target = [], [], None, None
    head = re.compile(r"^[\s\ufeff\u200b]*[@＠][ \t　]*(部屋|項目)[ \t　]*[:：]?[ \t　]*(.*)$")
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip()
        if line.lstrip().startswith("//"):
            continue
        m = head.match(line)
        if not m:
            if target is not None:
                target.append(line)
            continue
        f = [x.strip() for x in re.split(r"[|｜]", m.group(2))] + ["", "", "", ""]
        name = f[0] or "(名前なし)"
        if m.group(1) == "部屋":
            room = {"name": name, "img": _fk_img(f[1], missing), "desc": f[2], "lines": [], "items": []}
            rooms.append(room)
            target = room["lines"]
        else:
            if room is None:
                sys.exit(f"fukyou.txt の {n} 行目: 「@項目」の前に「@部屋」がありません。\n"
                         f"  その行: {line.strip()[:60]}\n"
                         "  (「@項目」より上に「@部屋 名前 | 画像 | 説明」の行が必要です。部屋の行を消したり、"
                         "// を付けたりしていないか確認してください。GitHubには送りません)")
            img = _fk_img(f[1], missing)
            item = {"name": name, "img": img, "desc": f[2], "lines": [],
                    "img2": _fk_img(f[3], missing) or img}
            room["items"].append(item)
            target = item["lines"]
    _FK_CACHE = (rooms, missing)
    return _FK_CACHE


TABS_CSS = """
.tabs{overflow-x:auto;overflow-y:hidden;pointer-events:auto;touch-action:pan-x;-webkit-overflow-scrolling:touch;
  scrollbar-width:thin;scrollbar-color:rgba(125,243,255,.45) transparent}
.tabs::-webkit-scrollbar{display:block;height:6px}
.tabs::-webkit-scrollbar-track{background:transparent}
.tabs::-webkit-scrollbar-thumb{background:rgba(125,243,255,.4);border-radius:3px}
.tabs label{flex:none;white-space:nowrap}
.tabs.dragging{cursor:grabbing;-webkit-user-select:none;user-select:none}
.tabs.dragging label{cursor:grabbing}
"""

# 上段のタブが画面からはみ出したとき: ホイールで横に動く / マウスでつかんで動かす / 選んだタブが見える位置へ
TABS_JS = r"""
(() => {
  const bar = document.querySelector('.tabs');
  if (!bar) return;
  bar.addEventListener('wheel', (e) => {
    if (bar.scrollWidth <= bar.clientWidth) return;
    const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    if (!d) return;
    e.preventDefault();
    bar.scrollLeft += d;
  }, { passive: false });
  let down = false, moved = false, sx = 0, sl = 0;
  bar.addEventListener('pointerdown', (e) => {
    if (e.pointerType !== 'mouse' || e.button !== 0) return;
    down = true; moved = false; sx = e.clientX; sl = bar.scrollLeft;
  });
  window.addEventListener('pointermove', (e) => {
    if (!down) return;
    const dx = e.clientX - sx;
    if (!moved && Math.abs(dx) > 5) { moved = true; bar.classList.add('dragging'); }
    if (moved) bar.scrollLeft = sl - dx;
  });
  window.addEventListener('pointerup', () => { down = false; bar.classList.remove('dragging'); });
  bar.addEventListener('click', (e) => {   // ドラッグしたあとのクリックで、タブが切り替わらないように
    if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; }
  }, true);
  document.addEventListener('change', (e) => {
    if (!e.target || e.target.name !== 'tab') return;
    const l = bar.querySelector('label[for="' + e.target.id + '"]');
    if (l) l.scrollIntoView({ inline: 'nearest', block: 'nearest', behavior: 'smooth' });
  });
})();
"""

FUKYOU_CSS = """
#t-fukyou:checked ~ main label[for=t-fukyou]{color:var(--ink);border-bottom-color:var(--glow)}
#t-fukyou:checked ~ main .p-fukyou{display:block}
.fk-view[hidden]{display:none!important}
.fk-view:not([hidden]){animation:fk-in .35s ease}
@keyframes fk-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.fk-view .vbar{margin-bottom:1rem}
.fk-intro{margin:0 0 1rem;color:var(--dim)}
.fk-card{position:relative;overflow:hidden;isolation:isolate}
.fk-card .name,.fk-card .desc{position:relative;z-index:1}
.fk-card.has-img::before{content:'';position:absolute;inset:0;z-index:0;opacity:0;transition:opacity 1.1s ease;
  background:linear-gradient(to right,rgba(10,14,42,.9) 0%,rgba(10,14,42,.4) 55%,rgba(10,14,42,.05) 100%),
    var(--img) center/cover no-repeat}
.fk-card.has-img:focus-visible::before,.fk-card.has-img:active::before{opacity:1}
@media (hover:hover){.fk-card.has-img:hover::before{opacity:1}}
.fk-detail{display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:1.1rem;
  min-height:calc(100vh - 14rem);min-height:calc(100dvh - 14rem)}
.fk-img{display:block;width:auto;height:auto;max-width:min(100%,420px);max-height:50vh;border-radius:14px;
  border:1px solid var(--line);box-shadow:0 8px 28px rgba(0,0,0,.45)}
.fk-body{width:100%;max-width:100%}
@media (prefers-reduced-motion:reduce){.fk-view:not([hidden]){animation:none}.fk-card.has-img::before{transition:none}}
"""

FUKYOU_JS = r"""
(() => {
  const sec = document.querySelector('.p-fukyou');
  if (!sec) return;
  const show = (id) => {
    const v = document.getElementById(id);
    if (!v) return;
    sec.querySelectorAll('.fk-view').forEach((x) => { x.hidden = (x !== v); });
    sec.scrollTop = 0;
  };
  // カード・戻るボタンの data-go に書いた id の画面へ切り替える
  document.addEventListener('click', (e) => {
    const t = e.target.closest ? e.target : e.target.parentElement;
    const b = t && t.closest('.p-fukyou [data-go]');
    if (!b) return;
    e.preventDefault();
    e.stopPropagation();   // 「戻る」を、お遊びコーナーの戻る処理に渡さない
    show(b.dataset.go);
  }, true);
})();
"""


def _fk_card(go: str, name: str, desc: str, img) -> str:
    st = f' style="--img:url({html.escape(img, quote=True)})"' if img else ""
    cls = "fk-card has-img" if img else "fk-card"
    d = f'<span class="desc">{html.escape(desc)}</span>' if desc else ""
    return (f'<li><a href="#" class="{cls}" data-go="{go}"{st}>'
            f'<span class="name">{html.escape(name)}</span>{d}</a></li>')


def _fk_bar(go: str, title: str) -> str:
    return (f'<div class="vbar"><button type="button" class="vback fk-back" data-go="{go}">← 戻る</button>'
            f'<span class="vtitle">{html.escape(title)}</span></div>')


def fukyou_html() -> str:
    rooms, _ = _fk_rooms()
    if not rooms:
        return ('<div class="fk-view" id="fk-root"><ul class="list"><li class="empty">'
                'fukyou.txt に「@部屋 名前 | 画像 | 説明」を書くと、ここに表示されます。</li></ul></div>')
    views = ['<div class="fk-view" id="fk-root"><ul class="list">'
             + "".join(_fk_card(f"fk-r{ri}", r["name"], r["desc"], r["img"]) for ri, r in enumerate(rooms))
             + "</ul></div>"]
    for ri, r in enumerate(rooms):
        intro = "\n".join(r["lines"]).strip()
        body = f'<div class="dm fk-intro">{discord_md(intro)}</div>' if intro else ""
        if r["items"]:
            lst = ('<ul class="list">' + "".join(
                _fk_card(f"fk-i{ri}-{ii}", it["name"], it["desc"], it["img"])
                for ii, it in enumerate(r["items"])) + "</ul>")
        else:
            lst = '<ul class="list"><li class="empty">まだ項目がありません。</li></ul>'
        views.append(f'<div class="fk-view" id="fk-r{ri}" hidden>{_fk_bar("fk-root", r["name"])}{body}{lst}</div>')
        for ii, it in enumerate(r["items"]):
            fig = (f'<img class="fk-img" src="{html.escape(it["img2"], quote=True)}" '
                   f'alt="{html.escape(it["name"], quote=True)}" loading="lazy">') if it["img2"] else ""
            text = "\n".join(it["lines"]).strip()
            views.append(
                f'<div class="fk-view" id="fk-i{ri}-{ii}" hidden>{_fk_bar(f"fk-r{ri}", r["name"] + " › " + it["name"])}'
                f'<div class="fk-detail">{fig}<div class="dm fk-body">'
                f'<div class="dm-h2" role="heading" aria-level="2">{html.escape(it["name"])}</div>'
                f'{discord_md(text) if text else ""}</div></div></div>')
    return "\n    ".join(views)


def report_fukyou() -> None:
    rooms, missing = _fk_rooms()
    n = sum(len(r["items"]) for r in rooms)
    print(f"布教部屋: {len(rooms)}部屋 / {n}項目 ({FUKYOU_FILE.name} から読み込みました)")
    for r in rooms:
        if not r["items"]:
            print(f"  ⚠ 「{r['name']}」に @項目 がありません")
    for name in missing:
        print(f"  ⚠ 画像 {name} が siryou に無い (または画像ではない) ので、その画像は出ません")


# ---------- 合計閲覧者数 (ホーム画面) ----------
VISITS_CSS = """
.visits{margin:1.1rem 0 0;color:var(--dim);font-size:.95rem;text-shadow:0 1px 6px rgba(10,14,42,.95)}
.visits[hidden]{display:none}
.visits b{color:var(--ink);font-size:1.15rem;font-variant-numeric:tabular-nums;margin:0 .15rem}
"""

# 1つのブラウザにつき1回だけ数える (開くたびには増えない)。数えたあとは、数字を見るだけ
VISITS_JS = r"""
(() => {
  let cfg = null;
  try { cfg = JSON.parse(document.getElementById('visits-cfg').textContent); } catch (e) { return; }
  const box = document.getElementById('visits'), num = document.getElementById('visits-n');
  if (!cfg || !cfg.enabled || !box || !num) return;
  const KEY = 'osaito-counted';
  let counted = false;
  try { counted = localStorage.getItem(KEY) === '1'; } catch (e) { /* 保存できない環境 */ }
  const fill = (u) => String(u).replace('{ns}', encodeURIComponent(cfg.namespace)).replace('{key}', encodeURIComponent(cfg.key));
  fetch(fill(counted ? cfg.get_url : cfg.hit_url), { cache: 'no-store' })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((j) => {
      const v = typeof j.value === 'number' ? j.value : j.count;
      if (typeof v !== 'number') throw new Error('bad');
      num.textContent = v.toLocaleString('ja-JP');
      box.hidden = false;
      if (!counted) { try { localStorage.setItem(KEY, '1'); } catch (e) { /* 保存できない環境 */ } }
    })
    .catch(() => { num.textContent = '—'; box.hidden = false; });   // 数えられなかったときも、サイトは普通に使える
})();
"""


def visits_html() -> str:
    if not VISITOR_COUNTER.get("enabled"):
        return ""
    return '<p class="visits" id="visits" hidden>合計閲覧者数 <b id="visits-n">…</b> 人</p>'


def visits_tag() -> str:
    if not VISITOR_COUNTER.get("enabled"):
        return ""
    cfg = {k: VISITOR_COUNTER.get(k) for k in ("enabled", "namespace", "key", "hit_url", "get_url")}
    j = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/json" id="visits-cfg">{j}</script>\n<script>{VISITS_JS}</script>'


# ---------- 開発者機能 (パスワード付き・タブはいちばん右に固定) ----------
# パスワードは dev_password.txt の1行目に書く (GitHubには上げない)。ページには「鍵」の情報 (PBKDF2のハッシュ) だけが入る。
# ※ これは「入口の鍵」です。画面の中身はHTMLに入っているので、ページのソースを見られたら見えてしまいます。
#    本当に秘密にしたい情報 (APIキー・個人情報など) は、このサイトには置かないでください。
DEV_ITER = 200000
DEV_SALT = "osaito-dev-v1"


def dev_cfg():
    try:
        pw = DEV_PASSWORD_FILE.read_text(encoding="utf-8-sig").splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    if not pw:
        return None
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), DEV_SALT.encode("utf-8"), DEV_ITER, dklen=32).hex()
    return {"salt": DEV_SALT, "iter": DEV_ITER, "hash": h}


DEV_CSS = """
input{-webkit-user-select:text;user-select:text}
main input[type=password]{pointer-events:auto}
#t-dev:checked ~ main label[for=t-dev]{color:var(--ink);border-bottom-color:var(--glow)}
#t-dev:checked ~ main .p-dev{display:block}
.tabs .t-dev{margin-left:auto;flex:none}
.dev-lock[hidden],.dev-body[hidden]{display:none!important}
.dev-row{display:flex;gap:.6rem;align-items:center;max-width:28rem;margin:.4rem 0}
.dev-pw{flex:1;min-width:0;font:inherit;font-size:1rem;padding:.6rem .9rem;color:var(--ink);
  border:1px solid var(--line);border-radius:12px;background:rgba(10,14,42,.85)}
.dev-pw:focus{outline:2px solid var(--gold);outline-offset:2px}
.dev-code{font-family:ui-monospace,Consolas,monospace;color:var(--glow);font-size:.9rem}
.dev-body h2{margin:.2rem 0 .8rem;font-size:1.05rem}
"""

DEV_JS = r"""
(() => {
  const lock = document.getElementById('dev-lock'), body = document.getElementById('dev-body');
  if (!lock || !body) return;
  const meta = document.querySelector('meta[name="build-id"]');
  const bid = document.getElementById('dev-build');
  if (bid && meta) bid.textContent = meta.content;

  const cfgEl = document.getElementById('dev-cfg');
  let cfg = null;
  try { cfg = JSON.parse(cfgEl.textContent); } catch (e) { /* パスワード未設定 */ }
  const pw = document.getElementById('dev-pw'), go = document.getElementById('dev-go');
  const msg = document.getElementById('dev-msg'), msg2 = document.getElementById('dev-msg2');
  if (!cfg || !pw || !go) return;   // 未設定のときは、ずっとロックのまま
  const SKEY = 'osaito-dev-ok';
  const open = (on) => { lock.hidden = on; body.hidden = !on; };

  // このタブを開いている間だけ、開いたままにする (パスワードを変えたら、またロックされる)
  try { if (sessionStorage.getItem(SKEY) === cfg.hash) open(true); } catch (e) { /* 保存できない環境 */ }

  const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
  async function derive(p) {
    const enc = new TextEncoder();
    const k = await crypto.subtle.importKey('raw', enc.encode(p), 'PBKDF2', false, ['deriveBits']);
    return hex(await crypto.subtle.deriveBits(
      { name: 'PBKDF2', salt: enc.encode(cfg.salt), iterations: cfg.iter, hash: 'SHA-256' }, k, 256));
  }
  let busy = false, fails = 0;
  async function tryIn() {
    if (busy) return;
    if (!pw.value) { msg.textContent = 'パスワードを入力してください。'; return; }
    if (!(window.crypto && crypto.subtle)) { msg.textContent = 'この環境では使えません (https で開いてください)。'; return; }
    busy = true; msg.textContent = '確認しています…';
    try {
      const h = await derive(pw.value);
      if (h === cfg.hash) {
        pw.value = ''; msg.textContent = ''; fails = 0;
        try { sessionStorage.setItem(SKEY, cfg.hash); } catch (e) { /* 保存できない環境 */ }
        open(true);
      } else {
        fails++;
        await new Promise((r) => setTimeout(r, Math.min(3000, 500 * fails)));   // 連打して試せないように、少し待たせる
        msg.textContent = 'パスワードが違います。';
      }
    } catch (e) { msg.textContent = '確認できませんでした。'; }
    busy = false;
  }
  go.addEventListener('click', tryIn);
  pw.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); tryIn(); } });

  const on = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
  on('dev-relock', () => { try { sessionStorage.removeItem(SKEY); } catch (e) { /* ok */ } if (msg2) msg2.textContent = ''; open(false); });
  on('dev-recount', () => {
    try { localStorage.removeItem('osaito-counted'); } catch (e) { /* ok */ }
    if (msg2) msg2.textContent = '「カウント済み」を解除しました。ページを読み込み直すと、もう一度数えられます。';
  });
  on('dev-reset', () => {
    if (!window.confirm('この端末に保存した設定 (曲・壁紙・透明度・音量など) をすべて消します。よろしいですか?')) return;
    try {
      Object.keys(localStorage).filter((k) => k.indexOf('osaito-') === 0).forEach((k) => localStorage.removeItem(k));
    } catch (e) { /* ok */ }
    if (msg2) msg2.textContent = '消しました。ページを読み込み直してください。';
  });
})();
"""


def dev_panel_html() -> str:
    if dev_cfg():
        lock_inner = (
            '<p class="s-hint">パスワードを入力してください。</p>'
            '<div class="dev-row"><input type="password" id="dev-pw" class="dev-pw" autocomplete="off" '
            'autocapitalize="off" spellcheck="false" aria-label="パスワード">'
            '<button type="button" class="tgl" id="dev-go">入る</button></div>'
            '<p class="s-msg" id="dev-msg" role="status"></p>'
        )
    else:
        lock_inner = '<p class="s-hint">いまは入れません。</p>'
    return (
        '<section class="panel p-dev">'
        f'<div class="dev-lock" id="dev-lock">{lock_inner}</div>'
        '<div class="dev-body" id="dev-body" hidden><h2>開発者機能</h2>'
        '<div class="sw"><span class="sw-t">この版のID</span><code class="dev-code" id="dev-build">-</code></div>'
        '<div class="sw"><span class="sw-t">閲覧者数の「カウント済み」を解除</span>'
        '<button type="button" class="tgl" id="dev-recount">解除</button></div>'
        '<div class="sw"><span class="sw-t">保存した設定をすべて消す</span>'
        '<button type="button" class="tgl" id="dev-reset">消す</button></div>'
        '<div class="sw"><span class="sw-t">ロックする</span>'
        '<button type="button" class="tgl" id="dev-relock">ロック</button></div>'
        '<p class="s-msg" id="dev-msg2" role="status"></p></div>'
        '</section>'
    )


def dev_tag() -> str:
    c = dev_cfg()
    j = json.dumps(c, ensure_ascii=False) if c else "null"
    return f'<script type="application/json" id="dev-cfg">{j}</script>\n<script>{DEV_JS}</script>'


def ensure_gitignore() -> None:
    """dev_password.txt と env.txt が GitHub に上がらないよう、.gitignore に入れておく (改行のしかたは元のファイルに合わせる)"""
    p = BASE / ".gitignore"
    try:
        raw = p.read_bytes() if p.is_file() else b""
        nl = b"\r\n" if b"\r\n" in raw else b"\n"
        cur = raw
        for name in (b"dev_password.txt", b"env.txt"):
            if name in cur:
                continue
            if cur and not cur.endswith(b"\n"):
                cur += nl
            cur += name + nl
        if cur != raw:
            p.write_bytes(cur)
    except OSError:
        pass


def report_site() -> None:
    print(f"一覧: {SITE_DATA_FILE.name} から読み込みました / ホームの文章: {HOME_FILE.name}")
    if VISITOR_COUNTER.get("enabled"):
        print(f"合計閲覧者数: 有効 (名前: {VISITOR_COUNTER.get('namespace')})")
    else:
        print("合計閲覧者数: 無効 (site_data.json の visitor_counter の enabled で切り替え)")
    if dev_cfg():
        print("開発者機能: パスワードあり (dev_password.txt)")
    else:
        print("開発者機能: パスワード未設定のため入れません。dev_password.txt を作って1行目にパスワードを書くと使えます")


def _rows(items) -> list:
    rows = []
    for item in items:
        title, fname, note = (tuple(item) + ("", ""))[:3]
        rows.append((str(title), str(fname), str(note)))
    return rows


def song_rows() -> list:
    """OP_SONGS を (曲名, ファイル名, 説明) にそろえる。説明は省略してもよい"""
    return _rows(OP_SONGS)


def main_rows() -> list:
    """MAIN_SONGS を (曲名, ファイル名, 説明) にそろえる"""
    return _rows(MAIN_SONGS)


def songs_html(kind: str = "op") -> str:
    out = []
    for title, fname, note in (song_rows() if kind == "op" else main_rows()):
        ok = (SIRYOU_DIR / fname).is_file()
        src = f"{SIRYOU_DIR.name}/{quote(fname)}"
        sid = html.escape(fname, quote=True)
        dis = "" if ok else " disabled"
        n = f'<span class="s-note">{html.escape(note)}</span>' if note else ""
        badge = '<span class="s-badge">選択中</span>' if ok else '<span class="s-badge off">ファイルなし</span>'
        if kind == "op" and fname in motion_map():
            n += '<span class="s-tag">特殊モーション</span>'
        out.append(
            f'<li><button type="button" class="song" data-kind="{kind}" data-id="{sid}" data-src="{html.escape(src, quote=True)}" '
            f'aria-pressed="false"{dis}><span class="s-main"><span class="s-title">{html.escape(title)}</span>{n}</span>'
            f'{badge}</button>'
            f'<button type="button" class="pv" data-kind="{kind}" data-id="{sid}" data-src="{html.escape(src, quote=True)}" '
            f'aria-pressed="false" aria-label="{html.escape(title, quote=True)}を試し聴き"{dis}>▶</button></li>'
        )
    return "".join(out)


def volume_html() -> str:
    """サウンド設定の音量スライダー (初期値は OP_VOLUME / MAIN_VOLUME。JSが端末に保存した値で上書きする)"""
    def row(sid, title, v):
        pct = round(min(1.0, max(0.0, float(v))) * 100)
        return (
            f'<div class="vol"><label class="vol-t" for="{sid}">{title}</label>'
            f'<input type="range" id="{sid}" min="0" max="100" step="1" value="{pct}">'
            f'<output for="{sid}">{pct}%</output></div>'
        )
    return (
        '<div class="vols" role="group" aria-label="音量">'
        + row("vol-op", "オープニング曲", OP_VOLUME)
        + row("vol-main", "メイン画面の曲", MAIN_VOLUME)
        + '</div>'
    )


def sound_panel_html() -> str:
    return (
        '<section class="panel p-sound">'
        '<div class="sw"><span class="sw-t">音楽</span>'
        '<button type="button" class="tgl" id="music-toggle" aria-pressed="false">OFF</button></div>'
        '<div class="sw"><span class="sw-t">オープニングと一体化</span>'
        '<button type="button" class="tgl" id="unify-toggle" aria-pressed="false">OFF</button></div>'
        '<p class="s-hint">ONにすると、オープニングの曲が入場しても切り替わらず、そのままメイン画面でも流れ続けます'
        '(音量だけメイン画面用になります)。このあいだ「メイン画面」の曲は使われません。</p>'
        '<p class="s-msg u-msg" role="status"></p>'
        + cursor_row_html()
        + volume_html() +
        '<nav class="subtabs" aria-label="サウンド設定の項目">'
        '<button type="button" data-sub="op" aria-selected="true">オープニング画面</button>'
        '<button type="button" data-sub="main" aria-selected="false">メイン画面</button></nav>'
        '<div class="sub" data-sub-panel="op"><h2>オープニング曲の変更</h2>'
        '<p class="s-hint">選んだ曲は、次にサイトを開いたときのオープニング画面で流れます。▶ で試し聴きできます。</p>'
        f'<ul class="songs">{songs_html("op")}</ul><p class="s-msg" role="status"></p></div>'
        '<div class="sub" data-sub-panel="main" hidden><h2>メイン画面の曲の変更</h2>'
        '<p class="s-hint">選ぶと、いま流れているメイン画面の曲がすぐ切り替わります。▶ で試し聴きできます。</p>'
        f'<ul class="songs">{songs_html("main")}</ul><p class="s-msg" role="status"></p></div>'
        '</section>'
    )


def motion_map() -> dict:
    """OP_MOTIONS のうち、動画ファイルが siryou に実在するものだけを {曲のファイル名: 動画のパス} にする"""
    out = {}
    for song, vid in OP_MOTIONS.items():
        f = SIRYOU_DIR / str(vid)
        if f.is_file() and f.suffix.lower() in VIDEO_EXT:
            out[str(song)] = f"{SIRYOU_DIR.name}/{quote(f.name)}"
    return out


def motion_html() -> str:
    """OP画面の背景に敷く動画 (src はJSが、曲に合わせて入れる)。特殊モーションが1つも無ければ何も出さない"""
    if not (ENABLE_SOUND and motion_map()):
        return ""
    return (
        '<video class="op-motion" muted loop playsinline disablepictureinpicture aria-hidden="true"></video>'
        '<span class="op-veil" aria-hidden="true"></span>'
    )


def walls_html() -> str:
    out = []
    for title, fname, note in _rows(WALLPAPERS):
        f = SIRYOU_DIR / fname
        ok = f.is_file() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT
        sid = html.escape(fname, quote=True)
        dis = "" if ok else " disabled"
        n = f'<span class="s-note">{html.escape(note)}</span>' if note else ""
        if ok:
            kind = "動画" if f.suffix.lower() in VIDEO_EXT else "画像"
            n += f'<span class="s-tag">{kind} {f.stat().st_size / 1048576:.1f}MB</span>'
        badge = '<span class="s-badge">選択中</span>' if ok else '<span class="s-badge off">ファイルなし</span>'
        src = f"{SIRYOU_DIR.name}/{quote(fname)}"
        out.append(
            f'<li><button type="button" class="song" data-kind="wall" data-id="{sid}" '
            f'data-src="{html.escape(src, quote=True)}" aria-pressed="false"{dis}>'
            f'<span class="s-main"><span class="s-title">{html.escape(title)}</span>{n}</span>{badge}</button></li>'
        )
    return "".join(out)


def wall_cfg_json() -> str:
    items = {}
    for _t, fname, _n, f in wallpaper_items():
        items[fname] = f
    d = find_wallpaper()
    if d is not None:
        items.setdefault(d.name, d)
    lst = [{"id": name, "src": f"{SIRYOU_DIR.name}/{quote(f.name)}",
            "kind": "video" if f.suffix.lower() in VIDEO_EXT else "image"} for name, f in items.items()]
    cfg = {"def": d.name if d is not None else "", "gate": bool(ENABLE_LOADING_GATE), "list": lst}
    return json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")


def screen_panel_html() -> str:
    mm = motion_map()
    titles = [t for t, f, _ in song_rows() if f in mm]
    if titles:
        hint = "特殊モーションが付いている曲: " + "、".join(titles) + "。これらの曲を選んでいるときだけ、背景で動画が流れます。"
    else:
        hint = "いま特殊モーションが設定されている曲はありません。(build.py の OP_MOTIONS に曲と動画を書くと使えます)"
    return (
        '<section class="panel p-screen">'
        '<nav class="subtabs" aria-label="画面設定の項目">'
        '<button type="button" data-sub="op" aria-selected="true">オープニング画面</button>'
        '<button type="button" data-sub="wall" aria-selected="false">壁紙</button>'
        '<button type="button" data-sub="btn" aria-selected="false">ボタン</button></nav>'
        '<div class="sub" data-sub-panel="op">'
        '<div class="sw"><span class="sw-t">特殊モーション</span>'
        '<button type="button" class="tgl" id="motion-toggle" aria-pressed="true">ON</button></div>'
        f'<p class="s-hint">{html.escape(hint)}</p>'
        '<p class="s-hint">設定のない曲は、これまで通り白い背景のオープニング画面になります。</p>'
        '<p class="s-msg m-msg" role="status"></p></div>'
        '<div class="sub" data-sub-panel="wall" hidden><h2>壁紙の変更</h2>'
        '<p class="s-hint">選ぶと、その場で壁紙が切り替わります。動画はデータ通信量が大きいので、モバイル回線のときは大きさ(MB)に注意してください。</p>'
        f'<ul class="songs">{walls_html()}</ul><p class="s-msg w-msg" role="status"></p></div>'
        '<div class="sub" data-sub-panel="btn" hidden><h2>ボタンの透明度</h2>'
        '<p class="s-hint">ボタンやカードなど、押せる部分の背景の濃さを変えます。左いっぱい = 透明、右いっぱい = 完全不透明です。'
        f'初めは {int(BTN_ALPHA_DEFAULT)}% です。選んだ値は、次にサイトを開いたときも使われます。</p>'
        '<div class="vols" role="group" aria-label="ボタンの透明度"><div class="vol">'
        '<label class="vol-t" for="btn-alpha">ボタンの濃さ</label>'
        f'<input type="range" id="btn-alpha" min="0" max="100" step="1" value="{int(BTN_ALPHA_DEFAULT)}">'
        f'<output for="btn-alpha">{int(BTN_ALPHA_DEFAULT)}%</output></div></div>'
        '<div class="sw"><span class="sw-t">初期値に戻す</span>'
        '<button type="button" class="tgl" id="btn-alpha-reset">リセット</button></div>'
        '<p class="s-hint">ボタンにカーソルを合わせると、右端から暗くなって、少し大きくなります。</p></div>'
        '</section>'
    )


def sound_cfg_json() -> str:
    cfg = {
        "opVolume": OP_VOLUME,
        "mainVolume": MAIN_VOLUME,
        "opFadeIn": OP_FADE_IN,
        "opFadeOut": OP_FADE_OUT,
        "mainFadeIn": MAIN_FADE_IN,
        "cursorSrc": cursor_src(),
        "cursorVolume": CURSOR_VOLUME,
        "motions": motion_map(),
    }
    return json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")


def report_sound() -> None:
    """音楽ファイルが見つかったか、ターミナルに表示する"""
    if not ENABLE_SOUND:
        return
    print("音楽: 有効 (許可画面 → ロード画面の曲 → メイン画面の曲)")
    if cursor_src():
        print(f"カーソル効果音: {CURSOR_SOUND} を使います")
    else:
        print(f"カーソル効果音: siryou に {CURSOR_SOUND} が無いので鳴りません (置くと自動で使われます)")
    for title, fname, _ in song_rows():
        mark = "あり" if (SIRYOU_DIR / fname).is_file() else "なし ⚠ siryou に置くと選べるようになります"
        print(f"  オープニング曲「{title}」 {fname}: {mark}")
    for title, fname, _ in main_rows():
        mark = "あり" if (SIRYOU_DIR / fname).is_file() else "なし ⚠ siryou に置くと選べるようになります"
        print(f"  メイン画面の曲「{title}」 {fname}: {mark}")
    for title, fname, _ in _rows(WALLPAPERS):
        mark = "あり" if (SIRYOU_DIR / fname).is_file() else "なし ⚠ siryou に置くと選べるようになります"
        print(f"  壁紙「{title}」 {fname}: {mark}")


def report_motion() -> None:
    """特殊モーションの設定が効いているか、ターミナルに表示する"""
    if not ENABLE_SOUND:
        return
    mm = motion_map()
    if not OP_MOTIONS:
        print("特殊モーション: 設定なし (OP_MOTIONS が空なので、OP画面は全部白背景です)")
        return
    print(f"特殊モーション: {len(mm)}曲に設定 (ぼかし {OP_MOTION_BLUR}px)")
    for song, vid in OP_MOTIONS.items():
        if str(song) in mm:
            print(f"  {song} → {vid}: あり")
        else:
            print(f"  {song} → {vid}: ⚠ siryou に動画が無い (.mp4/.webm) ので、この曲は白背景のままです")
    known = {f for _, f, _ in song_rows()}
    for song in OP_MOTIONS:
        if str(song) not in known:
            print(f"  ⚠ {song} は OP_SONGS にありません。曲のファイル名を確認してください")


BACK_CSS = """
.back{display:block;margin-top:1.4rem;padding:1rem 1.1rem;border:1px solid var(--line);border-radius:14px;
  background:rgba(20,26,69,.82);color:var(--ink);font-weight:700;cursor:pointer;
  transition:border-color .2s,background .2s}
.back::before{content:"\\21A9";margin-right:.6rem;color:var(--glow)}
.back:hover{border-color:var(--glow)}
.back:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
"""

# 「オープニング画面に戻る」をキーボード (Enter / Space) でも押せるようにする
BACK_JS = r"""
(() => {
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const b = e.target.closest && e.target.closest('.back');
    if (!b) return;
    e.preventDefault();
    b.click();
  });
})();
"""


# ---------- お遊びコーナー: 一覧からタップしたページを、この画面の中にそのまま表示する ----------
VIEW_CSS = """
.viewer{display:none}
.p-pages.open .list{display:none}
.p-pages.open{overflow:hidden;padding-bottom:.4rem}
.p-pages.open .viewer{display:flex;flex-direction:column;gap:.6rem;height:100%;min-height:70vh}
.vbar{display:flex;align-items:center;gap:.8rem}
.vback{font:inherit;font-weight:700;padding:.5rem 1rem;border:1px solid var(--line);border-radius:999px;
  background:rgba(20,26,69,.82);color:var(--ink);cursor:pointer;pointer-events:auto}
.vback:hover{border-color:var(--glow)}
.vback:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
.vtitle{color:var(--dim);font-size:.9rem}
.viewer iframe{flex:1;min-height:0;width:100%;border:1px solid var(--line);border-radius:14px;background:#0a0e2a;pointer-events:auto}
"""

VIEW_JS = r"""
(() => {
  const sec = () => document.querySelector('.p-pages');
  function openPage(a) {
    const s = sec(); if (!s) return;
    const n = a.querySelector('.name');
    s.querySelector('.vtitle').textContent = n ? n.textContent : '';
    s.querySelector('.viewer iframe').src = a.getAttribute('href');
    s.classList.add('open');
    s.scrollTop = 0;
  }
  function closePage() {
    const s = sec(); if (!s) return;
    s.classList.remove('open');
    s.querySelector('.viewer iframe').src = 'about:blank';   // 閉じたら通信も止める
  }
  document.addEventListener('click', (e) => {
    const t = e.target.closest ? e.target : e.target.parentElement;
    if (!t) return;
    const a = t.closest('.p-pages .list a');
    if (a) { e.preventDefault(); openPage(a); return; }
    if (t.closest('.vback')) closePage();
  });
  // 別のタブに移ったら閉じる
  document.addEventListener('change', (e) => {
    if (e.target && e.target.name === 'tab' && e.target.id !== 't-pages') closePage();
  });
})();
"""


# ---------- スマホ・小さい画面向け (PCの見た目はそのまま、狭いときだけ調整する) ----------
MOBILE_CSS = """
h1{overflow-wrap:anywhere}
main{padding-left:max(clamp(1.2rem,5vw,4rem),env(safe-area-inset-left))}
.op-video,.op-still{max-height:calc(100vh - 8rem);max-height:calc(100dvh - 8rem);object-fit:contain}
@media (max-width:820px){
  main{padding-right:max(.9rem,env(safe-area-inset-right))}
  h1{font-size:clamp(1.15rem,5.4vw,1.7rem)}
  .tabs label{font-size:.92rem}
  .panel{padding-top:1rem}
}
@media (max-width:480px){
  .lead{font-size:1.05rem}
  .list a{padding:.8rem .9rem}
  .vol{grid-template-columns:1fr 3rem}
  .vol-t{grid-column:1/-1}
}
@media (orientation:portrait){.wall{object-position:72% 50%}}
@media (max-height:520px){
  main{padding-top:max(.5rem,env(safe-area-inset-top));padding-bottom:.4rem}
  h1{font-size:1.1rem;margin-bottom:.3rem}
  .tabs label{padding:.35rem .7rem}
  .panel{padding:.7rem .2rem 1rem}
  .lead{font-size:1rem}
  .gt{font-size:clamp(1.6rem,8vh,2.4rem)}
}
.rot{display:none;margin-top:.5rem;color:var(--dim);font-size:.8rem;letter-spacing:.05em}
.has-op .rot{color:#6b7399}
@media (orientation:portrait) and (max-width:820px){.rot{display:block}}
html:not(.loading) .rot{animation:rotfade 9s ease forwards}
@keyframes rotfade{0%,75%{opacity:1}100%{opacity:0}}
@media (prefers-reduced-motion:reduce){html:not(.loading) .rot{animation:none}}
"""


def wallpaper_items() -> list:
    """WALLPAPERS のうち、ファイルが実在するものを (名前, ファイル名, 説明, Path) にする"""
    out = []
    for title, fname, note in _rows(WALLPAPERS):
        f = SIRYOU_DIR / fname
        if f.is_file() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT:
            out.append((title, fname, note, f))
    return out


def find_wallpaper():
    """siryou の中から、最初に使う壁紙ファイルを探す。なければ None。"""
    if not SIRYOU_DIR.is_dir():
        return None
    if WALLPAPER:
        p = SIRYOU_DIR / WALLPAPER
        return p if p.is_file() else None
    items = wallpaper_items()
    if items:
        return items[0][3]
    for f in sorted(SIRYOU_DIR.iterdir()):
        if f.is_file() and f.stem.lower() in ("wallpaper", "壁紙") \
                and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT:
            return f
    return None


def wallpaper_html() -> str:
    f = find_wallpaper()
    if f is None:
        return ""
    # 相対パス + URLエンコード (日本語のファイル名でも動く)
    src = f"{SIRYOU_DIR.name}/{quote(f.name)}"
    if f.suffix.lower() in VIDEO_EXT:
        # スマホで自動再生するには muted + playsinline が必須
        plain = (
            f'<video class="wall" src="{src}" autoplay muted loop playsinline '
            f'preload="auto" disablepictureinpicture aria-hidden="true"></video>'
        )
        if ENABLE_LOADING_GATE:
            # JSが全部ダウンロードしてから src に入れる (二重に読み込まないよう、ここでは src を書かない)。
            # JSが使えない環境では noscript の方が使われる
            tag = (
                f'<video class="wall" data-src="{src}" muted loop playsinline '
                f'preload="none" disablepictureinpicture aria-hidden="true"></video>'
                f"<noscript>{plain}</noscript>"
            )
        else:
            tag = plain
    else:
        tag = f'<img class="wall" src="{src}" alt="" aria-hidden="true">'
    return tag + f'<div class="wall-shade" style="--shade:{WALL_SHADE}"></div>'


def find_op():
    """入場画面の動画と静止画を探す。(動画, 静止画) どちらも無ければ None。"""
    if not SIRYOU_DIR.is_dir():
        return None, None

    def pick(name, stems, exts):
        if name:
            p = SIRYOU_DIR / name
            return p if p.is_file() else None
        for f in sorted(SIRYOU_DIR.iterdir()):
            if f.is_file() and f.stem.lower() in stems and f.suffix.lower() in exts:
                return f
        return None

    video = pick(OP_VIDEO, ("op", "オープニング"), VIDEO_EXT)
    still = pick(OP_STILL, ("logo", "ロゴ"), IMAGE_EXT)
    return video, still


def op_html() -> str:
    video, still = find_op()
    if video is None:
        return ""
    src = f"{SIRYOU_DIR.name}/{quote(video.name)}"
    # 音楽が有効なときは、許可画面が終わってから JS が再生する (許可画面の裏で先に再生が進まないように)
    autoplay = "" if ENABLE_SOUND else " autoplay"
    preload = "none" if ENABLE_SOUND else "auto"  # 許可画面のあいだは読み込まない
    tags = (
        f'<video class="op-video" src="{src}"{autoplay} muted playsinline '
        f'preload="{preload}" disablepictureinpicture aria-hidden="true"></video>'
    )
    if still is not None:
        tags += f'<img class="op-still" src="{SIRYOU_DIR.name}/{quote(still.name)}" alt="" aria-hidden="true" loading="lazy">'
    return f'<span class="op">{tags}</span>'


def page_title(path: Path) -> str:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        m = re.search(r"<title>(.*?)</title>", head, re.I | re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    except OSError:
        pass
    return path.stem


def page_desc(path: Path) -> str:
    """<meta name="description"> があればその文、なければファイル名"""
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        m = re.search(r'<meta\s+name="description"\s+content="(.*?)"', head, re.I | re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    except OSError:
        pass
    return path.name


def link_item(href: str, name: str, desc: str, external: bool) -> str:
    attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
    d = f'<span class="desc">{html.escape(desc)}</span>' if desc else ""
    return (
        f'<li><a href="{html.escape(href, quote=True)}"{attrs}>'
        f'<span class="name">{html.escape(name)}</span>{d}</a></li>'
    )


def pages_html() -> str:
    PAGES_DIR.mkdir(exist_ok=True)
    items = [
        # 相対パスにしておくと、ユーザーサイトでもプロジェクトサイトでも動く
        link_item(f"pages/{p.name}", page_title(p), page_desc(p), False)
        for p in sorted(PAGES_DIR.glob("*.html"))
    ]
    if not items:
        return '<li class="empty">pages フォルダに .html を置いて build.py を実行すると、お遊びコーナーに並びます。</li>'
    return "".join(items)


def channels_html() -> str:
    try:
        data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = []
    items = []
    for c in data:
        url = str(c.get("url", ""))
        if not url.startswith(("http://", "https://")):
            continue  # javascript: などを弾く
        items.append(link_item(url, str(c.get("name", url)), str(c.get("description", "")), True))
    if not items:
        return '<li class="empty">channels.json にチャンネルを追加して build.py を実行すると、ここに表示されます。</li>'
    return "".join(items)


# 入場画面の下に出る部分: 読み込み中 (ぐるぐる) と、読み込み完了後の「Click to enter」
HINT_HTML = (
    '<span class="hint">'
    '<span class="load" role="status"><span class="spin" aria-hidden="true"></span>'
    '<span class="pct">読み込み中…</span></span>'
    '<span class="ready">'
    '<span class="gt"><span class="click">Click to enter</span><span class="tap">Tap to enter</span></span>'
    '<span class="gs">画面をクリック / タップ</span>'
    '<span class="rot">横画面にすることをお勧めします</span>'
    '</span></span>'
)


def build_page() -> str:
    t = html.escape(SITE_TITLE)
    op = op_html()
    if ENABLE_JS_EFFECT:
        extra_css = JS_CSS + WALL_CSS
        fx_html = f'<canvas id="fx" aria-hidden="true"></canvas>\n<script>{EFFECT_JS}</script>'
    else:
        extra_css = WALL_CSS + '.viewer iframe{min-height:70vh}'
        fx_html = '<div class="grid" aria-hidden="true">' + "<i></i>" * (COLS * ROWS) + "</div>"
    if op and (ENABLE_JS_EFFECT or ENABLE_SOUND):
        fx_html += f"\n<script>{OP_JS}</script>"
    if ENABLE_JS_EFFECT or ENABLE_SOUND:
        fx_html += f"\n<script>{BACK_JS}</script>"
    extra_css += LOAD_CSS + edge_css() + BACK_CSS + VIEW_CSS
    fx_html += f"\n<script>{VIEW_JS}</script>"
    fx_html += "\n<script>" + BTN_ALPHA_JS.replace("__DEF__", str(min(100, max(0, int(BTN_ALPHA_DEFAULT))))) + "</script>"
    if ENABLE_SOUND:
        extra_css += SOUND_CSS
        if motion_map():
            extra_css += motion_css()
    if wallpaper_items() or find_wallpaper() is not None:
        # 壁紙の切り替え。読み込み待ち (LOAD_JS) より前に動いて、選んだ壁紙に差し替える
        fx_html += f'\n<script type="application/json" id="wall-cfg">{wall_cfg_json()}</script>\n<script>{WALL_JS}</script>'
    if ENABLE_LOADING_GATE:
        fx_html += f"\n<script>{LOAD_JS}</script>"
    if ENABLE_UPDATE_NOTICE:
        extra_css += UPDATE_CSS
        fx_html += f"\n<script>{UPDATE_JS}</script>"
    if op:
        extra_css += OP_CSS
        gate = f'<label class="gate has-op" for="enter">\n  {motion_html()}\n  {op}\n  {HINT_HTML}\n</label>'
    else:
        gate = f'<label class="gate" for="enter">\n  {motion_html()}\n  {HINT_HTML}\n</label>'
    loading_boot = (
        "<script>document.documentElement.classList.add('loading');"
        "(window.__perm||Promise.resolve()).then(function(){setTimeout(function(){"
        "document.documentElement.classList.remove('loading')},120000)})</script>\n"
        if ENABLE_LOADING_GATE else ""
    )
    if ENABLE_SOUND:
        sound_boot = (
            "<script>document.documentElement.classList.add('perm-on');"
            "window.__perm=new Promise(function(r){window.__permResolve=r})</script>\n"
        )
        perm_html = PERM_HTML
        sound_radio = (
            '<input type="radio" name="tab" id="t-screen" class="sr">'
            '<input type="radio" name="tab" id="t-sound" class="sr">'
        )
        sound_label = '<label for="t-screen">画面設定</label><label for="t-sound">サウンド設定</label>'
        sound_panel = screen_panel_html() + sound_panel_html()
        sound_js_tag = (
            f'<script type="application/json" id="sound-cfg">{sound_cfg_json()}</script>\n'
            f"<script>{SOUND_JS}</script>\n"
            f"<script>{CURSOR_JS}</script>"
        )
    else:
        sound_boot = perm_html = sound_radio = sound_label = sound_panel = sound_js_tag = ""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{t}</title>
<meta name="build-id" content="__BUILD_ID__">
<style>{CSS}{extra_css}{MOBILE_CSS}{btn_css()}{VISITS_CSS}{DMD_CSS}{FUKYOU_CSS}{TABS_CSS}{DEV_CSS}</style>
{sound_boot}{loading_boot}</head>
<body style="--cols:{COLS};--rows:{ROWS}">
<input type="checkbox" id="enter" class="sr" aria-label="サイトに入る">
<input type="radio" name="tab" id="t-home" class="sr" checked>
<input type="radio" name="tab" id="t-pages" class="sr">
<input type="radio" name="tab" id="t-channels" class="sr">
<input type="radio" name="tab" id="t-fukyou" class="sr">
{sound_radio}
<input type="radio" name="tab" id="t-dev" class="sr">

{gate}

{perm_html}

{wallpaper_html()}
{'<div class="edge" aria-hidden="true"></div>' if EDGE_DARK > 0 else ''}
{fx_html}

<main>
  <h1>{t}</h1>
  <nav class="tabs">
    <label for="t-home">ホーム</label>
    <label for="t-pages">お遊びコーナー</label>
    <label for="t-channels">チャンネル</label>
    <label for="t-fukyou">布教部屋</label>
    {sound_label}
    <!-- 新しいタブを増やすときは、この「開発者機能」より上に足す (開発者機能はいつもいちばん右) -->
    <label for="t-dev" class="t-dev">開発者機能</label>
  </nav>
  <section class="panel p-home">
    {home_html()}
    {visits_html()}
    <label class="back" for="enter" role="button" tabindex="0">オープニング画面に戻る</label>
  </section>
  <section class="panel p-pages"><ul class="list">{pages_html()}</ul>
    <div class="viewer"><div class="vbar"><button type="button" class="vback">← 一覧に戻る</button><span class="vtitle"></span></div>
    <iframe title="お遊びコーナー"></iframe></div></section>
  <section class="panel p-channels"><ul class="list">{channels_html()}</ul></section>
  <section class="panel p-fukyou">{fukyou_html()}</section>
  {sound_panel}
  {dev_panel_html()}
</main>
{sound_js_tag}
{visits_tag()}
{dev_tag()}
<script>{DMD_JS}</script>
<script>{FUKYOU_JS}</script>
<script>{TABS_JS}</script>
</body>
</html>
"""


def report_wallpaper() -> None:
    """壁紙が見つかったか、ターミナルに表示する (見つからない原因の手がかり)"""
    f = find_wallpaper()
    if f is not None:
        mb = f.stat().st_size / 1_000_000
        print(f"壁紙: {f.name} を使います ({mb:.1f}MB)")
        if mb > 90:
            print("  ⚠ 90MBを超えています。GitHubは1ファイル100MBまでなので、圧縮してください。")
        return
    print("壁紙: 見つかりませんでした。")
    if not SIRYOU_DIR.is_dir():
        print(f"  ⚠ フォルダがありません: {SIRYOU_DIR}")
        return
    names = [x.name for x in sorted(SIRYOU_DIR.iterdir()) if x.is_file()]
    print(f"  siryou の中身: {names if names else '(空)'}")
    if WALLPAPER:
        print(f'  WALLPAPER = "{WALLPAPER}" と同じ名前のファイルがありません (大文字小文字も区別します)')
    else:
        print('  WALLPAPER が空です。ファイル名を wallpaper.mp4 にするか、WALLPAPER に名前を書いてください')


def compute_build_id(page_html: str) -> str:
    """ページの中身・pages・siryou の全ファイルから、この版の識別子を作る。
    中身が同じなら何度ビルドしても同じ値になる (無駄なコミットが増えない)。"""
    h = hashlib.sha256(page_html.encode("utf-8"))
    for d in (PAGES_DIR, SIRYOU_DIR):
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file():
                h.update(f.relative_to(BASE).as_posix().encode("utf-8"))
                with f.open("rb") as fp:
                    for chunk in iter(lambda: fp.read(1 << 20), b""):
                        h.update(chunk)
    return h.hexdigest()[:12]


def report_op() -> None:
    """入場アニメが見つかったか、ターミナルに表示する"""
    video, still = find_op()
    if video is None:
        print("入場アニメ: siryou に op.mp4 が無いので、文字だけの入場画面にします。")
        print("  (作るには  python make_op.py  を実行)")
        return
    print(f"入場アニメ: {video.name} を使います ({video.stat().st_size / 1000:.0f}KB)")
    if still is None:
        print("  ⚠ 静止画 (siryou/logo.png) が無いので、動画が再生できない環境では空白になります。")


if __name__ == "__main__":
    ensure_gitignore()
    # Windowsのコンソール(cp932)で出せない文字 (⚠ など) があっても、落ちずに ? に置き換えて表示する
    for _st in (sys.stdout, sys.stderr):
        try:
            _st.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    page = build_page()
    build_id = compute_build_id(page)
    OUTPUT.write_text(page.replace("__BUILD_ID__", build_id), encoding="utf-8")
    VERSION_FILE.write_text(json.dumps({"build": build_id}) + "\n", encoding="utf-8")
    print(f"書き出しました: {OUTPUT} (版: {build_id})")
    report_wallpaper()
    report_op()
    report_sound()
    report_motion()
    report_site()
    report_fukyou()
