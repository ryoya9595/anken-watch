"""通知済み管理の検証（納品物ではない）。

    python3 dev/test_seen.py

LINEにもネットにも接続しない。seen.py を直したら必ず実行する。
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 開発中は kit/scripts/、Zipを解いた後やリポジトリ配置後は scripts/ にある
SEEN = ROOT / "kit" / "scripts" / "seen.py"
if not SEEN.exists():
    SEEN = ROOT / "scripts" / "seen.py"

sys.path.insert(0, str(SEEN.parent))
import seen as mod  # noqa: E402

NG = 0


def ok(label, actual, expected):
    global NG
    if actual == expected:
        print(f"  ok   {label}")
    else:
        NG += 1
        print(f"  NG   {label}\n       期待 {expected!r}\n       実際 {actual!r}")


def run(state, *args, stdin=None):
    p = subprocess.run(
        [sys.executable, str(SEEN), "--state", str(state), *args],
        input=stdin, capture_output=True, text=True,
    )
    return p.stdout.strip().splitlines(), p.stderr.strip()


print("\n■ URLの正規化（同じ案件を別URLで見ても1つとみなす）")
ok("クラウドワークス", mod.normalize("https://crowdworks.jp/public/jobs/1234567"), "cw:1234567")
ok("クエリつき", mod.normalize("https://crowdworks.jp/public/jobs/1234567?ref=search"), "cw:1234567")
ok("末尾スラッシュ", mod.normalize("https://crowdworks.jp/public/jobs/1234567/"), "cw:1234567")
ok("アンカーつき", mod.normalize("https://crowdworks.jp/public/jobs/1234567#detail"), "cw:1234567")
ok("httpでも同じ", mod.normalize("http://crowdworks.jp/public/jobs/1234567"), "cw:1234567")
ok("ランサーズ", mod.normalize("https://www.lancers.jp/work/detail/9876543"), "lancers:9876543")
ok("ココナラ", mod.normalize("https://coconala.com/requests/555111"), "coconala:555111")
ok("知らないサイトはURLのまま", mod.normalize("https://example.com/job/1?a=b"), "https://example.com/job/1")
ok("空はから文字", mod.normalize(""), "")

print("\n■ 2段階の確定（filter → commit）")
with tempfile.TemporaryDirectory() as tmp:
    state = Path(tmp) / "seen.json"
    urls = "\n".join([
        "https://crowdworks.jp/public/jobs/111",
        "https://crowdworks.jp/public/jobs/222",
        "https://crowdworks.jp/public/jobs/333",
    ])

    out, _ = run(state, "--filter", "-", stdin=urls)
    ok("初回は全部が新しい", len(out), 3)

    # まだ commit していないので、もう一度聞いても全部新しいまま
    out, _ = run(state, "--filter", "-", stdin=urls)
    ok("commit前はまだ通知済みにならない", len(out), 3)

    run(state, "--commit")
    out, _ = run(state, "--filter", "-", stdin=urls)
    ok("commit後は全部が通知済み", len(out), 0)

    # 1件だけ新しいものを混ぜる
    out, _ = run(state, "--filter", "-", stdin=urls + "\nhttps://crowdworks.jp/public/jobs/444")
    ok("新しい1件だけ返る", out, ["https://crowdworks.jp/public/jobs/444"])

    # 同じ案件がクエリ違いで来ても重複しない
    run(state, "--commit")
    out, _ = run(state, "--filter", "-", stdin="https://crowdworks.jp/public/jobs/444?ref=mail")
    ok("クエリ違いは重複扱い", len(out), 0)

    # 同じ実行の中に重複があっても1件にまとまる
    out, _ = run(state, "--filter", "-", stdin="https://crowdworks.jp/public/jobs/555\nhttps://crowdworks.jp/public/jobs/555?x=1")
    ok("同じ回の重複も1件に", len(out), 1)

print("\n■ 空・こわれた入力でも落ちない")
with tempfile.TemporaryDirectory() as tmp:
    state = Path(tmp) / "seen.json"
    out, _ = run(state, "--filter", "-", stdin="")
    ok("空の入力", out, [])

    out, _ = run(state, "--filter", "-", stdin="\n\n# コメント行\n  \n")
    ok("空行とコメントは無視", out, [])

    state.write_text("こわれたJSON", encoding="utf-8")
    out, _ = run(state, "--filter", "-", stdin="https://crowdworks.jp/public/jobs/999")
    ok("壊れた記録でも止まらない", len(out), 1)

print("\n■ 古い記録の間引き")
with tempfile.TemporaryDirectory() as tmp:
    from datetime import datetime, timedelta
    state = Path(tmp) / "seen.json"
    now = datetime.now(mod.JST)
    data = {
        "seen": {
            "cw:old": (now - timedelta(days=mod.KEEP_DAYS + 10)).strftime("%Y-%m-%d"),
            "cw:new": now.strftime("%Y-%m-%d"),
        },
        "pending": ["cw:x"],
    }
    mod.save(state, data)
    run(state, "--commit")
    after = mod.load(state)
    ok("古いものは消える", "cw:old" in after["seen"], False)
    ok("新しいものは残る", "cw:new" in after["seen"], True)
    ok("確定分が入る", "cw:x" in after["seen"], True)

print("\n✅ すべて通りました\n" if NG == 0 else f"\n❌ {NG}件 失敗しています\n")
sys.exit(0 if NG == 0 else 1)
