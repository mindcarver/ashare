"""把 skills/_shared 挂到 sys.path 上。

各技能脚本按相对路径推导共享层，因此必须从技能目录内运行（或由
tools/run_skill_tests.py 在技能目录下以子进程运行）。
"""

import sys

from pathlib import Path

SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
