"""Claude Code のセッションに伝言して返事をもらう（session-bridge mod の外側）。

声の聞き役やチャットボットなど、同じPCの中のプログラムから使う。置き場はこのPCの中だけ。
  python bridge.py list
  python bridge.py send ぽーたる "今どこまで進んだ？" --from 声 --wait 300
ライブラリとしては sessions() / find(name) / send(name, text, frm, wait) を使う。
"""
import argparse
import json
import os
import pathlib
import random
import re
import sys
import time

DIR = pathlib.Path(os.environ.get("USERPROFILE") or pathlib.Path.home()) / ".claude" / "session-dash" / "bridge"
ALIVE_S = 15


def _read(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def sessions():
    """今動いているセッション（新しく動いた順）。"""
    now = time.time() * 1000
    out = []
    for f in (DIR / "sessions").glob("*.json"):
        s = _read(f)
        if s and not s.get("isEnded") and now - s.get("at", 0) < ALIVE_S * 1000:
            out.append(s)
    return sorted(out, key=lambda s: -s["at"])


def _norm(s):
    return re.sub(r"\s+", "", s or "").lower()


def find(want):
    """名前がそのまま合う → id の頭 → 名前に含む、の順で1つ。無ければ None。"""
    alive, w = sessions(), _norm(want)
    for test in (lambda s: _norm(s.get("name")) == w,
                 lambda s: s["id"].startswith(w.lstrip("#")),
                 lambda s: s.get("name") and w in _norm(s["name"])):
        hit = [s for s in alive if test(s)]
        if hit:
            return hit[0]
    return None


PROJECTS = DIR.parent.parent / "projects"
_titles = {}


def title(sid):
    """アプリに出ているセッションの題名。会話の記録（projects/*/<id>.jsonl）の最後の custom-title から読む。"""
    for f in PROJECTS.glob(f"*/{sid}.jsonl"):
        m = f.stat().st_mtime
        hit = _titles.get(sid)
        if hit and hit[0] == m:
            return hit[1]
        t = ""
        try:
            size = f.stat().st_size
            with open(f, "rb") as fh:
                fh.seek(max(0, size - 2_000_000))  # 題名は何度も書かれるので、終わりの方だけ見れば足りる
                found = re.findall(rb'"type":"custom-title","customTitle":"((?:[^"\\]|\\.)*)"', fh.read())
            t = json.loads(b'"' + found[-1] + b'"') if found else ""
        except Exception:
            pass
        _titles[sid] = (m, t)
        return t
    return ""


def label(s):
    return s.get("name") or title(s["id"]) or "#" + s["id"][:4]


def _kana(s):
    """カタカナをひらがなにそろえる（声の聞き取りは片方に寄らないので）。"""
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in _norm(s))


# 題名の英語を声で言うときの読み（Vosk は「ギットハブ」のように仮名で書く）
YOMI = {"github": "ぎっとはぶ", "git": "ぎっと", "claude": "くろーど", "pr": "ぴーあーる", "api": "えーぴーあい",
        "ai": "えーあい", "mod": "もっど", "vm": "ぶいえむ", "zoom": "ずーむ", "gsc": "じーえすしー", "seo": "えすいーおー", "geo": "じーいーおー", "css": "しーえすえす", "ui": "ゆーあい",
        "dots": "どっつ", "python": "ぱいそん", "twitch": "ついっち", "obs": "おーびーえす",
        "line": "らいん", "mc": "えむしー", "oss": "おーえすえす"}


def _yomi(s):
    import unicodedata
    s = unicodedata.normalize("NFKC", s or "").lower()
    return _kana(re.sub(r"[a-z]+", lambda m: YOMI.get(m[0], m[0]), s))


def _score(heard, target):
    """聞き取った言葉が target（名前か題名）にどれだけ合うか。題名は一部だけ言っても当たる。"""
    import difflib
    h, t = _yomi(heard), _yomi(target)
    if not h or not t:
        return 0.0
    if h == t:
        return 1.0
    if len(h) >= 2 and (h in t or t in h):
        return 0.9
    n = len(h)
    best = max(difflib.SequenceMatcher(None, h, t[i:i + n]).ratio() for i in range(max(1, len(t) - n + 1)))
    return best * 0.95


def candidates(heard, cutoff=0.6):
    """(点, セッション) を点の高い順に。名前を題名より少しだけ先に。"""
    out = []
    for s in sessions():
        sc = max(_score(heard, s.get("name", "")), _score(heard, title(s["id"])) * 0.98)
        if sc >= cutoff:
            out.append((sc, s))
    return sorted(out, key=lambda x: -x[0])


def pick(heard):
    """(セッション, None) か、迷ったら (None, [候補の名前…])、無ければ (None, [])。"""
    c = candidates(heard)
    if not c:
        return None, []
    if len(c) >= 2 and c[0][0] - c[1][0] < 0.05:
        return None, [label(s) for _, s in c[:3]]
    return c[0][1], None


def guess(heard, cutoff=0.6):
    s, _ = pick(heard)
    return s


def named():
    """外のプログラムから呼べるもの（名前か題名のあるセッション）。"""
    return [label(s) for s in sessions() if s.get("name") or title(s["id"])]


def post(s, text, frm="外", mode="ask", kind=None):
    """セッション s の受け箱に伝言を置く。mode="ask" は読むだけで答えさせる（書き換え・コマンドは mod が止める）。
    kind="voice" は会話ボタンの声：画面の前の本人の言葉として入る。msgid を返す。"""
    mid = f"{int(time.time() * 1000)}-{random.randrange(16**6):06x}"
    box = DIR / "inbox" / s["id"]
    box.mkdir(parents=True, exist_ok=True)
    tmp = box / f"{mid}.tmp"
    letter = {"id": mid, "from": frm, "text": text, "mode": mode, "at": time.time() * 1000}
    if kind:
        letter["kind"] = kind
    tmp.write_text(json.dumps(letter, ensure_ascii=False), encoding="utf-8")
    tmp.replace(box / f"{mid}.json")
    return mid


def result(s, mid):
    """返事が来ていれば文を返して受け箱を片づける。まだなら None。"""
    r = _read(DIR / "outbox" / f"{mid}.json")
    if not r:
        return None
    (DIR / "inbox" / s["id"] / f"{mid}.json").unlink(missing_ok=True)
    return r.get("answer") or ("（途中で止められた）" if r.get("isAborted") else "")


def wait_for(s, mid, wait):
    end = time.time() + wait
    while time.time() < end:
        ans = result(s, mid)
        if ans is not None:
            return ans
        time.sleep(0.5)
    return None


def send(want, text, frm="外", wait=300, mode="ask"):
    """伝言して返事を待つ。返り値は (相手の名前, 返事の文 or None)。相手がいなければ LookupError。"""
    s = find(want)
    if not s:
        raise LookupError(f"「{want}」というセッションが見つからない")
    mid = post(s, text, frm, mode)
    return label(s), (wait_for(s, mid, wait) if wait else None)


SESSION_WORD = re.compile(r"セッション|せっしょん|接しょん|せっしょ|節損|セッシ?ョ")


def parse(text):
    """「ぽーたるのセッションに〇〇」「セッションぽーたるに〇〇」を (名前の聞き取り, 伝言) に分ける。セッション宛てでなければ None。"""
    s = _norm(text)
    m = SESSION_WORD.search(s)
    if not m:
        return None
    before, after = s[:m.start()], s[m.end():]
    before = re.sub(r"(の|に|へ)$", "", before)
    if before:
        name, msg = before, re.sub(r"^(に|へ|で|、|,)+", "", after)
    else:
        mm = re.match(r"(.+?)(に|へ)(.+)", after)
        if not mm:
            return None
        name, msg = mm[1], mm[3]
    msg = re.sub(r"^(、|,)+", "", msg)
    return (name, msg) if name and msg else None


def for_speech(answer, sentences=3, limit=220):
    """読み上げ用に：コードの囲み・表・URL・記号を外して、頭の数文だけ。"""
    t = re.sub(r"```.*?```", "", answer or "", flags=re.S)
    t = "\n".join(l for l in t.splitlines() if not l.strip().startswith("|"))
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*#`>_]|^\s*[-・]\s*", "", t, flags=re.M)
    parts = [p.strip() for p in re.split(r"(?<=[。！!？?\n])", t) if p.strip()]
    out = "".join(parts[:sentences])
    return out[:limit] if out else "返事は文字だけだったのだ。画面で見てほしいのだ"


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sp = sub.add_parser("send")
    sp.add_argument("to")
    sp.add_argument("text")
    sp.add_argument("--from", dest="frm", default="外")
    sp.add_argument("--wait", type=int, default=300)
    sp.add_argument("--do", action="store_true", help="読むだけでなく作業もさせる（既定は読むだけ）")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "list":
        for s in sessions():
            print(f"{'🟡' if s.get('busy') else '🟢'} {label(s):12} {s['id'][:8]}  {s.get('prompt', '')}")
        return
    try:
        who, ans = send(a.to, a.text, a.frm, a.wait, "do" if a.do else "ask")
    except LookupError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    print(f"{who}：{ans}" if ans is not None else f"{who}：（{a.wait}秒待っても返事が無い）")


if __name__ == "__main__":
    main()
