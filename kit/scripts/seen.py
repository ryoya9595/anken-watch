#!/usr/bin/env python3
"""通知済みの案件を覚えておく（同じ案件を何度も知らせないため）。

案件は毎日増えるので、記録しておかないと「昨日も見たやつ」が毎朝届く。

使い方:
  # 見つけた案件URLを渡すと、まだ通知していないものだけを返す（この時点では未確定）
  python3 seen.py --filter urls.txt
  cat urls.txt | python3 seen.py --filter -

  # LINE送信が成功したあとに呼ぶ。ここで初めて「通知済み」になる
  python3 seen.py --commit

  # いま何件覚えているか
  python3 seen.py --stats

■ なぜ2段階（filter → commit）なのか
先に通知済みにしてしまうと、LINE送信が失敗したときに**その案件が二度と通知されない**。
送信が成功したときだけ確定させる。失敗した回の案件は、次回もう一度出てくる
（まれに重複するほうが、取りこぼすよりよい）。

標準ライブラリのみ。
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
DEFAULT_STATE = Path(__file__).resolve().parent.parent / "state" / "seen.json"

#: 覚えておく日数。案件は流れていくので、これより古い記録は捨てる
KEEP_DAYS = 120


def normalize(url: str) -> str:
    """同じ案件が別のURLで来ても同一とみなせるように整える。

    - クエリ（?ref=... など）と末尾スラッシュを落とす
    - クラウドワークスは `/public/jobs/1234567` の数字だけあれば一意なので、それを鍵にする
    """
    u = (url or "").strip()
    if not u:
        return ""
    u = u.split("#")[0].split("?")[0].rstrip("/")

    m = re.search(r"crowdworks\.jp/public/jobs/(\d+)", u)
    if m:
        return f"cw:{m.group(1)}"

    m = re.search(r"lancers\.jp/work/detail/(\d+)", u)
    if m:
        return f"lancers:{m.group(1)}"

    m = re.search(r"coconala\.com/requests/(\d+)", u)
    if m:
        return f"coconala:{m.group(1)}"

    return u


def load(path: Path) -> dict:
    if not path.exists():
        return {"seen": {}, "pending": []}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[seen] 読めなかったので空から始めます: {e}", file=sys.stderr)
        return {"seen": {}, "pending": []}
    d.setdefault("seen", {})
    d.setdefault("pending", [])
    return d


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def prune(data: dict, today: datetime) -> int:
    """古い記録を捨てる。捨てた件数を返す。"""
    limit = (today - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    before = len(data["seen"])
    data["seen"] = {k: v for k, v in data["seen"].items() if v >= limit}
    return before - len(data["seen"])


def cmd_filter(args, path: Path) -> int:
    raw = sys.stdin.read() if args.filter == "-" else Path(args.filter).read_text(encoding="utf-8")

    urls = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)

    data = load(path)
    known = set(data["seen"])

    fresh, dupes, seen_now = [], 0, set()
    for u in urls:
        key = normalize(u)
        if not key:
            continue
        if key in known or key in seen_now:
            dupes += 1
            continue
        seen_now.add(key)
        fresh.append({"url": u, "key": key})

    data["pending"] = [f["key"] for f in fresh]
    save(path, data)

    for f in fresh:
        print(f["url"])

    print(
        f"[seen] 受け取った {len(urls)}件 / 新しい {len(fresh)}件 / 通知済みだった {dupes}件",
        file=sys.stderr,
    )
    return 0


def cmd_commit(args, path: Path) -> int:
    data = load(path)
    pending = data.get("pending", [])
    if not pending:
        print("[seen] 確定するものはありません", file=sys.stderr)
        return 0

    today = datetime.now(JST)
    stamp = today.strftime("%Y-%m-%d")
    for key in pending:
        data["seen"][key] = stamp
    data["pending"] = []

    dropped = prune(data, today)
    save(path, data)
    print(
        f"[seen] {len(pending)}件を通知済みにしました"
        + (f"（古い {dropped}件は削除）" if dropped else ""),
        file=sys.stderr,
    )
    return 0


def cmd_stats(args, path: Path) -> int:
    data = load(path)
    print(
        json.dumps(
            {
                "seen": len(data["seen"]),
                "pending": len(data["pending"]),
                "keep_days": KEEP_DAYS,
                "path": str(path),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="通知済みの案件を覚えておく")
    ap.add_argument("--filter", metavar="FILE", help="URLの一覧（1行1つ。`-` で標準入力）")
    ap.add_argument("--commit", action="store_true", help="LINE送信が成功したあとに呼ぶ")
    ap.add_argument("--stats", action="store_true", help="件数を表示する")
    ap.add_argument("--state", help="記録ファイルの場所")
    args = ap.parse_args()

    path = Path(args.state) if args.state else DEFAULT_STATE

    if args.filter:
        return cmd_filter(args, path)
    if args.commit:
        return cmd_commit(args, path)
    if args.stats:
        return cmd_stats(args, path)

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
