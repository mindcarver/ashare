#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 skills/_shared 挂到 sys.path 的唯一入口。

生成器已拆分为多个同目录模块（审计 P2-5），凡是需要 `ashare_shared` 的模块都先
`import _paths`，这样就不必依赖模块间的导入顺序，也不重复写路径拼接。

注意：本文件必须能被入口脚本以 `python3 scripts/gen_dashboard.py …` 的方式直接
import，因此运行时 scripts/ 目录天然在 sys.path[0] 上。
"""
import sys
from pathlib import Path

SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"

if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
