"""
自作サイト (JavaScriptなし・このpyファイル1つだけ)

構成:
  app.py
  channels.json   ... チャンネルコーナーの内容 (なくてもOK)
  pages/          ... 自作HTMLを置く場所。.html を置くと一覧に自動表示

起動:
  pip install flask
  python app.py   → http://127.0.0.1:8000
  Cloudflare Tunnel などで 127.0.0.1:8000 を公開する

仕組み(すべてCSS):
  - Click to enter ... 隠しチェックボックス + label
  - タブ切り替え   ... 隠しラジオボタン + label
  - エフェクト     ... 画面全体の小さなマス目。触れる/タップしたマスが光って消える
"""

import html
import json
import re
from pathlib import Path

from flask import Flask, Response, send_from_directory

BASE = Path(__file__).resolve().parent
PAGES_DIR = BASE / "pages"
CHANNELS_FILE = BASE / "channels.json"
PAGES_DIR.mkdir(exist_ok=True)

HOST = "127.0.0.1"
PORT = 8000

SITE_TITLE = "マイサイト"
COLS, ROWS = 22, 40  # エフェクト用マス目の数

app = Flask(__name__)

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
  justify-content:center;gap:1rem;cursor:pointer;background:rgba(10,14,42,.0);
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
.grid i:nth-child(5n+1){--h:190}
.grid i:nth-child(5n+2){--h:320}
.grid i:nth-child(5n+3){--h:48}
.grid i:nth-child(5n+4){--h:260}
.grid i:nth-child(5n){--h:150}
.grid i::before{content:"";position:absolute;inset:18%;border-radius:50%;
  background:hsl(var(--h) 100% 72%);box-shadow:0 0 14px hsl(var(--h) 100% 70%);
  transform:scale(0);opacity:0;transition:transform .9s ease-out,opacity .9s ease-out}
/* 触れた瞬間はすぐ光り、離れるとゆっくり消える = 軌跡になる */
.grid i:hover::before{transform:scale(1.7);opacity:.95;transition-duration:0s}
.grid i:hover + i::before{transform:scale(1);opacity:.6;transition-duration:0s}
/* タップ/クリック中は大きく弾ける */
.grid i:active::before{transform:scale(6);opacity:1;transition-duration:0s}

/* ---------- 本体 ---------- */
main{position:relative;z-index:10;max-width:760px;margin:0 auto;padding:1.2rem;
  padding-top:max(1.2rem,env(safe-area-inset-top));opacity:0;transition:opacity .9s ease .2s;
  pointer-events:none} /* 空白部分は下のマス目に触れられるようにする */
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
.list a:hover{border-color:var(--glow);background:rgba(30,40,100,.9)}
.list a:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
.name{font-weight:700;font-size:1.05rem}
.desc{display:block;color:var(--dim);font-size:.9rem;margin-top:.15rem}
.empty{color:var(--dim)}
@media (prefers-reduced-motion:reduce){.gt{animation:none}.grid i::before{transition:none}
  .gate,main{transition:none}}
"""


def page_title(path: Path) -> str:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        m = re.search(r"<title>(.*?)</title>", head, re.I | re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    except OSError:
        pass
    return path.stem


def link_item(href: str, name: str, desc: str, external: bool) -> str:
    attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
    d = f'<span class="desc">{html.escape(desc)}</span>' if desc else ""
    return (
        f'<li><a href="{html.escape(href, quote=True)}"{attrs}>'
        f'<span class="name">{html.escape(name)}</span>{d}</a></li>'
    )


def pages_html() -> str:
    items = [
        link_item(f"/pages/{p.name}", page_title(p), p.name, False)
        for p in sorted(PAGES_DIR.glob("*.html"))
    ]
    if not items:
        return '<li class="empty">pages フォルダに .html を置くと、ここに表示されます。</li>'
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
        return '<li class="empty">channels.json にチャンネルを追加すると、ここに表示されます。</li>'
    return "".join(items)


def build_page() -> str:
    cells = "<i></i>" * (COLS * ROWS)
    t = html.escape(SITE_TITLE)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{t}</title>
<style>{CSS}</style>
</head>
<body style="--cols:{COLS};--rows:{ROWS}">
<input type="checkbox" id="enter" class="sr" aria-label="サイトに入る">
<input type="radio" name="tab" id="t-home" class="sr" checked>
<input type="radio" name="tab" id="t-pages" class="sr">
<input type="radio" name="tab" id="t-channels" class="sr">

<label class="gate" for="enter">
  <span class="gt"><span class="click">Click to enter</span><span class="tap">Tap to enter</span></span>
  <span class="gs">画面をクリック / タップ</span>
</label>

<div class="grid" aria-hidden="true">{cells}</div>

<main>
  <h1>{t}</h1>
  <nav class="tabs">
    <label for="t-home">ホーム</label>
    <label for="t-pages">自作HTML</label>
    <label for="t-channels">チャンネル</label>
  </nav>
  <section class="panel p-home">
    <p class="lead">ここは全部自作のサイトです。画面をなぞる・タップすると光が出ます。</p>
    <p>上のタブから、自作HTMLの置き場とチャンネルを見られます。</p>
  </section>
  <section class="panel p-pages"><ul class="list">{pages_html()}</ul></section>
  <section class="panel p-channels"><ul class="list">{channels_html()}</ul></section>
</main>
</body>
</html>"""


@app.route("/")
def index():
    return Response(build_page(), mimetype="text/html")


@app.route("/pages/<path:filename>")
def serve_page(filename):
    return send_from_directory(PAGES_DIR, filename)  # ../ などは自動で弾かれる


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
