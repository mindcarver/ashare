#!/usr/bin/env bash
#
# 把仓库里的技能挂载到各 AI 工具的 skills 目录（软链，不复制）。
#
# 技能列表自动发现：skills/ 下任何含 SKILL.md 的目录都会被挂载。
# 新增技能只需建目录，不需要改本脚本；skills/_shared 是共享层不是技能，自动跳过。
#
# 用法：
#   ./install.sh            挂载全部
#   ./install.sh --dry-run  只打印将要执行的动作

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$ROOT_DIR/skills"
SHARED_SRC="$SKILLS_SRC/_shared"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# 需要挂载到的目标目录（不存在的会被创建）
TARGETS=(
  "$HOME/.workbuddy/skills"
  "$HOME/.codex/skills"
  "$HOME/.claude/skills"
)

if [[ ! -d "$SKILLS_SRC" ]]; then
  echo "[ERROR] 找不到 $SKILLS_SRC" >&2
  exit 1
fi

if [[ ! -f "$SHARED_SRC/ashare_shared.py" ]]; then
  echo "[ERROR] 共享层缺失：$SHARED_SRC/ashare_shared.py" >&2
  echo "        各技能脚本依赖它读取禁词表与设计令牌，缺少时生成器会直接报错。" >&2
  exit 1
fi

# 自动发现技能：有 SKILL.md 才算技能（_shared 没有 SKILL.md，天然被排除）
discovered=()
for src in "$SKILLS_SRC"/*/; do
  [[ -f "${src}SKILL.md" ]] || continue
  discovered+=("$(basename "$src")")
done

if (( ${#discovered[@]} == 0 )); then
  echo "[ERROR] skills/ 下没有发现任何含 SKILL.md 的技能目录" >&2
  exit 1
fi

for target in "${TARGETS[@]}"; do
  if (( DRY_RUN )); then
    echo "[dry-run] mkdir -p $target"
  else
    mkdir -p "$target"
  fi
done

linked=0
for target in "${TARGETS[@]}"; do
  for skill in "${discovered[@]}"; do
    src="$SKILLS_SRC/$skill"
    if (( DRY_RUN )); then
      echo "[dry-run] ln -sfn $src $target/$skill"
    else
      ln -sfn "$src" "$target/$skill"
    fi
    linked=$((linked + 1))
  done
done

# 清掉可能随目录同步过去的字节码缓存
find "$SKILLS_SRC" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo
echo "已发现 ${#discovered[@]} 个技能：${discovered[*]}"
echo "目标目录 ${#TARGETS[@]} 个：${TARGETS[*]}"
if (( DRY_RUN )); then
  echo "（dry-run，未做任何修改）"
else
  echo "完成，共建立 $linked 条软链。"
  echo "验证：make test   或   python3 tools/audit_shared_layer.py"
fi
