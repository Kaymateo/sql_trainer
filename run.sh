#!/usr/bin/env bash
# SQL 训练场 · 一键启动
#   用法： ./run.sh [端口]     默认 3000
set -e
cd "$(dirname "$0")"
PORT="${1:-3000}"

if [ ! -x .venv/bin/python ]; then
  echo "首次运行：创建虚拟环境并安装依赖（duckdb / pyarrow）…"
  python3 -m venv .venv
  .venv/bin/pip -q install --upgrade pip
  .venv/bin/pip -q install -r requirements.txt
fi

if [ ! -f data/flashcards.json ]; then
  echo "生成理论卡片…"
  .venv/bin/python tools/build_flashcards.py || true
fi

echo "启动中… 浏览器打开 http://localhost:${PORT}"
exec .venv/bin/python app.py "$PORT"
