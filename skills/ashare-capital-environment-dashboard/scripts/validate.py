#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入读取、契约校验与点时筛选（拆分自 gen_dashboard.py，审计 P2-5）。

设计要点：
- `load_records` 返回 `(records, sector_advice)`，不再通过全局变量传板块建议层，
  消除"导入即改状态"的副作用。
- `select_cells` 只用 `publishedAt <= as_of` 的记录；没有合格记录时诚实降级为未知，
  绝不用未来数据回填。
"""
import json

from schema import AVAILABILITIES, DEFAULT_CELLS_PATH, EXPECTED_KEYS, parse_date


def load_records(path):
    """读取 cells JSON。支持两种顶层结构：
    1) 28 个 market|dimension 键（原有）；
    2) 含 "cells" 与/或 "sectorAdvice" 的包装对象。

    返回 (records, sector_advice)。sectorAdvice（板块倾向建议层）不参与 28 格校验。
    path 为 None 时读取 DEFAULT_CELLS_PATH（examples/sample-cells.json 演示样例）。
    """
    if path is None:
        path = DEFAULT_CELLS_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 cells JSON：{path}") from exc
    sector_advice = payload.get("sectorAdvice") or {} if isinstance(payload, dict) else {}
    if isinstance(payload, dict) and "cells" in payload:
        records = payload["cells"]
    elif isinstance(payload, dict):
        records = {k: v for k, v in payload.items() if k != "sectorAdvice"}
    else:
        records = None
    if not isinstance(records, dict):
        raise ValueError("cells JSON 必须是对象，或包含对象字段 cells")
    return records, sector_advice


def unknown_cell(as_of):
    return {
        "type": "unknown",
        "availability": "unknown",
        "reason": f"截至 {as_of} 无已发布的可验证数据",
    }


def _require_grid(records):
    """校验键集恰好是 4×7。select_cells 与 validate_record_catalog 共用，报错文案一致。"""
    missing = EXPECTED_KEYS - records.keys()
    extra = records.keys() - EXPECTED_KEYS
    if missing or extra:
        detail = []
        if missing:
            detail.append("缺少 " + ", ".join(sorted(missing)))
        if extra:
            detail.append("未知键 " + ", ".join(sorted(extra)))
        raise ValueError("cells 必须恰好包含 4×7 网格：" + "；".join(detail))


def _as_candidates(key, record_or_records):
    candidates = [record_or_records] if isinstance(record_or_records, dict) else record_or_records
    if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
        raise ValueError(f"{key} 必须是记录对象或记录对象数组")
    return candidates


def select_cells(records, as_of):
    _require_grid(records)

    selected = {}
    for key in sorted(EXPECTED_KEYS):
        candidates = _as_candidates(key, records[key])
        eligible = [item for item in candidates if item.get("publishedAt") and parse_date(item["publishedAt"], f"{key}.publishedAt") <= as_of]
        selected[key] = max(eligible, key=lambda item: item["publishedAt"]) if eligible else unknown_cell(as_of)
    return selected


def has_observable_value(cfg):
    if "value" in cfg:
        return cfg["value"] not in (None, 0)
    values = cfg.get("values")
    return isinstance(values, list) and any(value not in (None, 0) for value in values)


def validate_record_catalog(records):
    """在筛选前拒绝坏记录，避免 malformed 的未来记录被悄悄当成未知。"""
    _require_grid(records)
    for key, records_for_key in records.items():
        for cfg in _as_candidates(key, records_for_key):
            availability = cfg.get("availability")
            if availability not in AVAILABILITIES:
                raise ValueError(f"{key}.availability 非法：{availability!r}")
            if availability in {"available", "partial", "pending_review"}:
                required = ("source", "observedAt", "publishedAt", "processingVersion")
                absent = [field for field in required if not cfg.get(field)]
                if absent:
                    raise ValueError(f"{key} 有值却缺少证据字段：{', '.join(absent)}")
                if not has_observable_value(cfg):
                    raise ValueError(f"{key} 标为 {availability} 却没有非零观测值")
            if cfg.get("publishedAt"):
                parse_date(cfg["publishedAt"], f"{key}.publishedAt")


def validate_cells(cells, as_of):
    for key, cfg in cells.items():
        availability = cfg.get("availability")
        if availability not in AVAILABILITIES:
            raise ValueError(f"{key}.availability 非法：{availability!r}")
        if availability in {"available", "partial", "pending_review"}:
            required = ("source", "observedAt", "publishedAt", "processingVersion")
            absent = [field for field in required if not cfg.get(field)]
            if absent:
                raise ValueError(f"{key} 有值却缺少证据字段：{', '.join(absent)}")
            if not has_observable_value(cfg):
                raise ValueError(f"{key} 标为 {availability} 却没有非零观测值")
        published_at = cfg.get("publishedAt")
        if published_at and parse_date(published_at, f"{key}.publishedAt") > as_of:
            raise ValueError(f"{key} 引入了晚于回放日的数据：{published_at} > {as_of}")
