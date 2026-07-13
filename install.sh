#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$HOME/.codex/skills" "$HOME/.claude/skills"

ln -sfn "$ROOT_DIR/skills/ashare-company-research" "$HOME/.codex/skills/ashare-company-research"
ln -sfn "$ROOT_DIR/skills/ashare-news-investment-targets" "$HOME/.codex/skills/ashare-news-investment-targets"

ln -sfn "$ROOT_DIR/skills/ashare-company-research" "$HOME/.claude/skills/ashare-company-research"
ln -sfn "$ROOT_DIR/skills/ashare-news-investment-targets" "$HOME/.claude/skills/ashare-news-investment-targets"

echo "已安装："
echo "- $HOME/.codex/skills/ashare-company-research"
echo "- $HOME/.codex/skills/ashare-news-investment-targets"
echo "- $HOME/.claude/skills/ashare-company-research"
echo "- $HOME/.claude/skills/ashare-news-investment-targets"
