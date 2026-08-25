#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Append new skill names here; no other changes required.
SKILLS=(
  ashare-daily-market-review
  ashare-stock-screening
  ashare-company-research
  ashare-research-journal
  ashare-news-investment-targets
  ashare-capital-environment-dashboard
)

mkdir -p "$HOME/.codex/skills" "$HOME/.claude/skills"

for skill in "${SKILLS[@]}"; do
  src="$ROOT_DIR/skills/$skill"
  if [[ ! -d "$src" ]]; then
    echo "[WARN] skip: $src not found" >&2
    continue
  fi
  ln -sfn "$src" "$HOME/.codex/skills/$skill"
  ln -sfn "$src" "$HOME/.claude/skills/$skill"
  echo "Linked: $skill -> $HOME/.codex/skills/$skill, $HOME/.claude/skills/$skill"
done
