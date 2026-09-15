SHELL := /bin/bash
PYTHON ?= python3
RUNNER := $(PYTHON) tools/run_skill_tests.py

.PHONY: help test test-list audit selftest fetch-market install clean

help:
	@echo "A 股研究技能库 —— 常用命令"
	@echo ""
	@echo "  make test                     跑全部技能 + 共享层测试"
	@echo "  make test S=<技能名>          只跑某一个，如 S=ashare-daily-market-review"
	@echo "  make test-list                列出会被执行的套件"
	@echo "  make audit                    共享层漂移检查（禁词/令牌/技术面重复）"
	@echo "  make selftest                 共享层自检"
	@echo "  make fetch-market DATE=<交易日> [OUT=market.json] [CTX=ctx.json]"
	@echo "                                抓取东财一手盘面数据，组装每日复盘 1.2 输入并校验"
	@echo "  make install                  把 skills/ 挂载到各 AI 工具的 skills 目录"
	@echo "  make clean                    清理 __pycache__ 与 .pyc"
	@echo ""
	@echo "改动脚本或共享层后请至少跑一次 make test。"

test:
ifdef S
	@$(RUNNER) $(S)
else
	@$(RUNNER)
endif

test-list:
	@$(RUNNER) --list

audit:
	@$(PYTHON) tools/audit_shared_layer.py

fetch-market:
	@test -n "$(DATE)" || { echo "用法：make fetch-market DATE=2026-09-14 [OUT=market.json] [CTX=ctx.json]"; exit 2; }
	@$(PYTHON) tools/fetch_daily_market.py --date "$(DATE)" --out "$(if $(OUT),$(OUT),market.json)" $(if $(CTX),--context "$(CTX)",)

selftest:
	@$(PYTHON) skills/_shared/ashare_shared.py

install:
	@./install.sh

clean:
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "已清理 __pycache__ 与 .pyc"
