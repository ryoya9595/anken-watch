#!/usr/bin/env python3
"""
LINE Messaging API でメッセージを push する。

使い方:
  python3 send_line.py --to Uxxxxxxxx --text "本文"
  python3 send_line.py --to Uxxxxxxxx --file message.txt
  cat message.txt | python3 send_line.py --to Uxxxxxxxx
  python3 send_line.py --self-test          （送らずに認証だけ確認）

環境変数:
  LINE_TO_USER_ID              --to を省略したときの宛先
  LINE_CHANNEL_ACCESS_TOKEN    あれば Authorization: Bearer で送る。
                               無ければヘッダを付けない（cloud 環境の API credentials に
                               api.line.me を登録してあれば、プロキシが付けてくれる）

5000文字を超える本文は自動で分割して複数通にする（LINEの上限）。
標準ライブラリのみ。
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

API = "https://api.line.me/v2/bot/message/push"
INFO = "https://api.line.me/v2/bot/info"
MAX_LEN = 4900


def _ssl_context():
    ctx = ssl.create_default_context()
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if ca and os.path.exists(ca):
        try:
            ctx.load_verify_locations(ca)
        except Exception:
            pass
    return ctx


def _request(url, method, payload=None, token=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
            body = r.read().decode("utf-8")
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def split_text(text, n=MAX_LEN):
    """行単位で n 文字以下のかたまりに分ける。1行が n を超える場合はその行も強制的に割る
    （割らないと LINE の文字数上限を超えて 400 で弾かれる）。"""
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > n:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:n])
            line = line[n:]
        if len(cur) + len(line) + 1 > n and cur:
            chunks.append(cur)
            cur = ""
        cur = (cur + "\n" + line) if cur else line
    if cur:
        chunks.append(cur)
    return chunks or [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default=os.environ.get("LINE_TO_USER_ID", ""))
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or None

    if args.self_test:
        code, body = _request(INFO, "GET", None, token)
        print(json.dumps({"ok": code == 200, "status": code, "body": body[:300]}, ensure_ascii=False))
        sys.exit(0 if code == 200 else 2)

    if not args.to:
        print(json.dumps({"ok": False, "error": "宛先がありません（--to か LINE_TO_USER_ID）"}, ensure_ascii=False))
        sys.exit(2)

    if args.text is not None:
        text = args.text
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()
    text = text.strip()
    if not text:
        print(json.dumps({"ok": False, "error": "本文が空です"}, ensure_ascii=False))
        sys.exit(2)

    chunks = split_text(text)
    # 1リクエスト最大5通。それ以上は分けて送る
    sent = 0
    for i in range(0, len(chunks), 5):
        payload = {"to": args.to, "messages": [{"type": "text", "text": c} for c in chunks[i:i + 5]]}
        code, body = _request(API, "POST", payload, token)
        if code != 200:
            print(json.dumps({"ok": False, "status": code, "body": body[:500], "sent": sent}, ensure_ascii=False))
            sys.exit(3)
        sent += len(payload["messages"])
    print(json.dumps({"ok": True, "sent": sent}, ensure_ascii=False))


if __name__ == "__main__":
    main()
