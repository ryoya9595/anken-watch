#!/bin/bash
# 配布用Zipを作り直す。
#
# ⚠️ zip コマンドは使わない。macOS の zip は日本語ファイル名に UTF-8 フラグを立てないため、
#    Windows のエクスプローラーで解凍すると文字化けする。Python の zipfile なら自動で立つ。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "▶ 検証"
python3 dev/test_seen.py > /dev/null || { echo "❌ テストが通らないのでZipを作りません"; exit 1; }
echo "  OK"

python3 - << 'PY'
import os, zipfile

NAME = 'anken-watch'
OUT = f'{NAME}-kit.zip'

DOCS = [
    'はじめにお読みください.md',
    '事前準備ガイド.md',
    '導入手順_AIに読ませる.md',
    '案件条件ヒアリングシート.md',
    '導入をサポートする人へ.md',
    'dev/test_seen.py',
]
TREES = ['kit']
SKIP_DIRS = {'node_modules', '.git', '__pycache__'}
SKIP_FILES = {'.DS_Store'}

files = list(DOCS)
for tree in TREES:
    for root, dirs, names in os.walk(tree):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in sorted(names):
            if n not in SKIP_FILES:
                files.append(os.path.join(root, n))

missing = [f for f in files if not os.path.exists(f)]
if missing:
    raise SystemExit('❌ 見つからないファイル: ' + ', '.join(missing))

with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in files:
        # kit/ の中身は anken-watch/ 直下に置かれる想定（ルーティンのパスに合わせる）
        arc = f[len('kit/'):] if f.startswith('kit/') else f
        z.write(f, f'{NAME}/{arc}')

with zipfile.ZipFile(OUT) as z:
    bad = [i.filename for i in z.infolist()
           if not i.filename.isascii() and not (i.flag_bits & 0x800)]
    if bad:
        raise SystemExit('❌ UTF-8フラグが立っていません（Windowsで文字化けします）: ' + ', '.join(bad))
    print(f'\n✅ {OUT}  （{len(z.infolist())}ファイル / {os.path.getsize(OUT):,} バイト）')
    for i in z.infolist():
        print(f'   {i.file_size:>7,}  {i.filename}')
PY
