#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 ashare-stock-personality 的输入档案：个股「股性」所需的观测事实。

分工原则（机器能取的自动取，需要研究判断的显式声明）：

  自动抓取
    股票池与行业/市值    东财 push2delay clist（全A 分页，含成交额/换手率/流通市值/行业）
    交易日历            腾讯 上证指数日K
    个股日线（价格/量）  腾讯前复权日K（1 请求/股，带磁盘缓存与断点续跑）
    龙虎榜              东财 datacenter-web，自带 D1/D2/D5/D10 复权涨跌幅

  显式声明（写入输出 JSON 的 thresholds，缺省即不猜）
    各板块涨跌幅限制 / 异动幅度 / 埋人回撤阈值与窗口 / 评分权重 / 原型切点

口径与已知限制（写进 references/data-pitfalls.md，这里留摘要）
  - 历史成交额优先用东财 push2his 的 f57；该接口限流时回退到「日均换手率」口径，
    并在输出里把 capacity_metric 标成 turnover_avg_pct（流动性的相对口径）。
  - 涨跌幅由前复权序列的相邻收盘价算出：除权日会失真（真实涨停可能被低估），
    属已知边角，不靠估算修补。
  - 龙虎榜的 D1/D2/D5/D10 是事后字段；观察窗未满的事件不下发，避免前视偏差。

用法：
  python3 tools/fetch_personality_archive.py --as-of 2026-09-15 --out research/stock-personality/personality_input.json
  python3 tools/fetch_personality_archive.py --as-of 2026-09-15 --lhb-months 12 --max-stocks 800 --cache-dir .cache/personality
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

CLIST_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
LHB_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EM_KLINE_HOSTS = ["push2his.eastmoney.com"] + [f"{i}.push2his.eastmoney.com" for i in range(1, 12)]

ALL_A_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
CLIST_FIELDS = "f12,f14,f2,f6,f8,f21,f100"

# 显式阈值：全部写进输出 JSON，派生层只读声明值，不设隐藏默认。
DEFAULT_THRESHOLDS: dict[str, Any] = {
    "limit_up_pct": {"main": 9.8, "gem": 19.5, "star": 19.5, "bse": 29.0, "st": 4.8},
    "spike_pct": 7.0,
    "dump_drawdown_pct": -8.0,
    "dump_window_days": 3,
    "lhb_net_min_cny": 0,
    "score_weights": {"d1": 0.22, "d2": 0.24, "d3": 0.18, "d4": 0.10, "d5": 0.12, "d6": 0.14},
    "archetype": {
        "high": 70.0,
        "mid": 55.0,
        "low": 40.0,
        # 连板阈值按 12 个月窗口标定：实测本池 max_streak≥3 的占比 68%、≥6 约 15%、
        # ≥7 约 10%。取 3 会让「连板妖股型」吞掉三分之二样本、使原型失去区分度，
        # 因此取 6（约前 15%）。注意该门槛与板块无关，ST/北交所 5% 涨跌幅更易连板，
        # 高连板样本会偏向 ST，解释时必须说明。
        "legend_streak": 6,
        "capacity_high": 70.0,
        "elastic_high": 70.0,
        "trend_high": 70.0,
    },
}

SOURCES = [
    {
        "name": "东财全A快照（push2delay clist）",
        "url": f"{CLIST_URL}?fs={ALL_A_FS}&fields={CLIST_FIELDS}",
    },
    {
        "name": "腾讯前复权日K（fqkline qfq）",
        "url": f"{TENCENT_KLINE_URL}?param=<code>,day,<start>,<end>,<n>,qfq",
    },
    {
        "name": "东财龙虎榜明细（datacenter-web）",
        "url": f"{LHB_URL}?reportName=RPT_DAILYBILLBOARD_DETAILSNEW&filter=(TRADE_DATE='<date>')",
    },
]


class FetchError(RuntimeError):
    pass


def http_json(url: str, headers: dict[str, str] | None = None, tries: int = 4, pause: float = 1.2):
    """带指数退避的 JSON 抓取。全部源都返回 application/json。"""
    merged = dict(UA)
    if headers:
        merged.update(headers)
    last: Exception | None = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers=merged)
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
            if not payload:
                raise FetchError("空响应")
            return json.loads(payload.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 逐源重试是刻意的
            last = exc
            if attempt < tries - 1:
                time.sleep(pause * (2**attempt))
    raise FetchError(f"抓取失败：{last}")


def tencent_symbol(code: str) -> str:
    if is_bse(code):
        return "bj" + code
    if code[0] in ("6", "9"):
        return "sh" + code
    return "sz" + code


# 北交所代码前缀：老代码 43/83/87/88，2023 年起新发代码统一为 920。
# 注意 920xxx 以 "9" 开头，若只按 "9→sh" 映射会拼成 sh920xxx。
BSE_PREFIXES = ("43", "83", "87", "88", "920")


def is_bse(code: str) -> bool:
    return code.startswith(BSE_PREFIXES)


def board_of(code: str, name: str) -> str:
    if is_bse(code):
        return "bse"
    if "ST" in name.upper():
        return "st"
    if code.startswith("68"):
        return "star"
    if code.startswith("30"):
        return "gem"
    return "main"


# --- 股票池 -----------------------------------------------------------------


def fetch_universe(page_size: int = 100) -> tuple[dict[str, dict[str, Any]], int]:
    """全A快照：代码、名称、现价、成交额、换手率、流通市值、行业。"""
    out: dict[str, dict[str, Any]] = {}
    page = 1
    total = None
    while True:
        url = (
            f"{CLIST_URL}?pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2&fid=f12"
            f"&fs={ALL_A_FS}&fields={CLIST_FIELDS}"
        )
        payload = http_json(url)
        data = payload.get("data") or {}
        if total is None:
            total = int(data.get("total") or 0)
        # fltt=2&invt=2 时 diff 是数组；不带这些参数时是以下标为键的对象。两种都收。
        raw_diff = data.get("diff") or []
        rows = list(raw_diff.values()) if isinstance(raw_diff, dict) else list(raw_diff)
        if not rows:
            break
        for row in rows:
            code = str(row.get("f12") or "")
            if not code:
                continue
            out[code] = {
                "code": code,
                "name": str(row.get("f14") or ""),
                "price_cny": row.get("f2") if isinstance(row.get("f2"), (int, float)) else None,
                "amount_cny": row.get("f6") if isinstance(row.get("f6"), (int, float)) else None,
                "turnover_pct": row.get("f8") if isinstance(row.get("f8"), (int, float)) else None,
                "float_cap_cny": row.get("f21") if isinstance(row.get("f21"), (int, float)) else None,
                "sector": str(row.get("f100") or "") or None,
            }
        print(f"  股票池 第 {page} 页，累计 {len(out)}/{total}", file=sys.stderr)
        if total and len(out) >= total:
            break
        page += 1
        time.sleep(0.15)
    if not out:
        raise FetchError("股票池为空：东财 clist 快照未返回任何股票")
    return out, int(total or len(out))


def fetch_trading_days(start: _date, end: _date) -> list[str]:
    """用上证指数日K取窗口内的真实交易日，避免用自然日猜交易日。"""
    span = (end - start).days + 20
    url = (
        f"{TENCENT_KLINE_URL}?param=sh000001,day,{start.isoformat()},{end.isoformat()},{span},qfq"
    )
    payload = http_json(url)
    block = ((payload.get("data") or {}).get("sh000001") or {})
    rows = block.get("qfqday") or block.get("day") or []
    days = [row[0] for row in rows if row and row[0] >= start.isoformat()]
    if not days:
        raise FetchError("交易日历为空：腾讯上证指数日K未返回数据")
    return days


def trading_days_from_cache(cache_dir: Path | None, start: str, end: str) -> list[str]:
    """腾讯日K不可得时的兜底：用池内已有日线的日期并集重建交易日历。

    样本足够多时（几百只），日期并集等于窗口内的全部交易日——停牌个股的缺口会被
    其它个股补上。这是**降级口径**，调用方必须把 calendar_source 标成 cache。
    样本太少（< 20 个交易日）说明缓存不完整，直接失败而不是给出稀疏日历。
    """
    if not cache_dir or not cache_dir.is_dir():
        return []
    seen: set[str] = set()
    for path in cache_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for bar in payload.get("bars") or []:
            stamp = str(bar.get("date") or "")
            if start <= stamp <= end:
                seen.add(stamp)
    days = sorted(seen)
    if len(days) < 20:
        return []
    return days


# --- 龙虎榜 -----------------------------------------------------------------


def fetch_lhb(days: list[str]) -> dict[str, list[dict[str, Any]]]:
    """按交易日拉龙虎榜明细，自带 D1/D2/D5/D10 复权涨跌幅。"""
    by_code: dict[str, list[dict[str, Any]]] = {}
    for index, day in enumerate(days, 1):
        url = (
            f"{LHB_URL}?reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL"
            f"&pageNumber=1&pageSize=500&sortColumns=SECURITY_CODE&sortTypes=1"
            f"&filter=(TRADE_DATE%3D%27{day}%27)"
        )
        try:
            payload = http_json(url, tries=3)
        except FetchError as exc:
            print(f"  龙虎榜 {day} 抓取失败，跳过：{exc}", file=sys.stderr)
            continue
        rows = ((payload.get("result") or {}).get("data")) or []
        for row in rows:
            code = str(row.get("SECURITY_CODE") or "")
            if not code:
                continue
            record = {
                "date": str(row.get("TRADE_DATE") or "")[:10],
                "net_amt_cny": _num(row.get("BILLBOARD_NET_AMT")),
                "explanation": str(row.get("EXPLANATION") or "") or None,
            }
            for horizon in (1, 2, 5, 10):
                record[f"d{horizon}_pct"] = _num(row.get(f"D{horizon}_CLOSE_ADJCHRATE"))
            by_code.setdefault(code, []).append(record)
        if index % 20 == 0 or index == len(days):
            print(f"  龙虎榜 {index}/{len(days)} 个交易日，命中 {len(by_code)} 只", file=sys.stderr)
        time.sleep(0.12)
    if not by_code:
        raise FetchError("龙虎榜为空：全部交易日均未取到数据")
    return by_code


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# --- 个股日线 ---------------------------------------------------------------


def fetch_bars(code: str, start: str, end: str, cache_dir: Path | None) -> list[dict[str, Any]]:
    """腾讯前复权日K。命中缓存直接复用，便于断点续跑与避免重复请求。"""
    cache_path = cache_dir / f"{code}.json" if cache_dir else None
    if cache_path and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("start") == start and cached.get("end") == end:
                return cached["bars"]
        except (OSError, ValueError):
            pass
    symbol = tencent_symbol(code)
    url = f"{TENCENT_KLINE_URL}?param={symbol},day,{start},{end},400,qfq"
    payload = http_json(url, tries=3)
    block = ((payload.get("data") or {}).get(symbol) or {})
    rows = block.get("qfqday") or block.get("day") or []
    bars: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < 6:
            continue
        close = _num(row[2])
        high = _num(row[3])
        low = _num(row[4])
        volume = _num(row[5])
        if close is None or volume is None:
            continue
        bars.append(
            {
                "date": str(row[0]),
                "close_cny": close,
                "high_cny": high if high is not None else close,
                "low_cny": low if low is not None else close,
                "volume_lot": volume,
            }
        )
    if cache_path and bars:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"code": code, "start": start, "end": end, "bars": bars}, ensure_ascii=False),
            encoding="utf-8",
        )
    return bars


def fetch_amount_kline(code: str, start: str, end: str) -> list[tuple[str, float]] | None:
    """东财日K的成交额（f57）。接口限流时返回 None，由调用方回退口径。"""
    secid = ("1." if code[0] in ("6", "9") else "0.") + code
    template = (
        f"{EM_KLINE_URL}?secid={secid}&fields1=f1,f2,f3&fields2=f51,f57"
        f"&klt=101&fqt=1&beg={start.replace('-', '')}&end={end.replace('-', '')}"
    )
    for host in EM_KLINE_HOSTS[:4]:
        try:
            payload = http_json(template.replace(EM_KLINE_URL, f"https://{host}"), tries=1, pause=0.5)
        except FetchError:
            continue
        rows = ((payload.get("data") or {}).get("klines")) or []
        out = [(row.split(",")[0], _num(row.split(",")[1])) for row in rows if "," in row]
        cleaned = [(day, amount) for day, amount in out if amount is not None]
        if cleaned:
            return cleaned
    return None


# --- 事件计算 ---------------------------------------------------------------


def build_stock(
    code: str,
    meta: dict[str, Any],
    bars: list[dict[str, Any]],
    lhb: list[dict[str, Any]],
    thresholds: dict[str, Any],
    calendar: list[str] | None = None,
) -> dict[str, Any]:
    board = board_of(code, meta["name"])
    limit_pct = float(thresholds["limit_up_pct"][board])
    spike_pct = float(thresholds["spike_pct"])
    dump_pct = float(thresholds["dump_drawdown_pct"])
    dump_window = int(thresholds["dump_window_days"])

    closes = [bar["close_cny"] for bar in bars]
    changes: list[float | None] = [None]
    for index in range(1, len(bars)):
        previous = closes[index - 1]
        changes.append(None if not previous else (closes[index] / previous - 1) * 100)

    # 交易日序号：用于判断相邻两根 K 线之间是否夹着停牌。
    # 停牌会中断连板链（交易所层面连板不等于连续自然日涨停），若不重置会把
    # 「停牌前后各若干板」拼成一条长链，系统性高估最高连板。
    calendar_index = {day: position for position, day in enumerate(calendar)} if calendar else {}

    spikes: list[dict[str, Any]] = []
    streak = 0
    for index, bar in enumerate(bars):
        change = changes[index]
        if change is None:
            streak = 0
            continue
        if index > 0:
            previous_day = bars[index - 1]["date"]
            here = calendar_index.get(bar["date"])
            there = calendar_index.get(previous_day)
            if here is not None and there is not None and here != there + 1:
                streak = 0  # 中间夹着停牌/缺失交易日，连板链断
        is_limit = change >= limit_pct - 0.3
        streak = streak + 1 if is_limit else 0
        if change < spike_pct and not is_limit:
            continue
        event: dict[str, Any] = {
            "date": bar["date"],
            "change_pct": round(change, 4),
            "limit_up": is_limit,
            "streak": streak if is_limit else 0,
        }
        forward = bars[index + 1: index + 1 + dump_window]
        if index + 1 < len(bars):
            event["next_day_pct"] = round(changes[index + 1], 4)  # type: ignore[arg-type]
            lows = [item["low_cny"] for item in forward if item.get("low_cny")]
            if lows:
                event["drawdown_nd_pct"] = round((min(lows) / bar["close_cny"] - 1) * 100, 4)
        spikes.append(event)

    windows = [window for window in (5, 20, 60) if len(closes) > window]
    returns = {
        f"ret_{window}d_pct": round((closes[-1] / closes[-1 - window] - 1) * 100, 4)
        for window in windows
    }
    daily = [value for value in changes if value is not None]
    volatility = None
    if len(daily) > 20:
        mean = sum(daily) / len(daily)
        variance = sum((value - mean) ** 2 for value in daily) / (len(daily) - 1)
        volatility = round((variance**0.5) * (243**0.5), 4)

    stock: dict[str, Any] = {
        "code": code,
        "name": meta["name"],
        "board": board,
        "sector": meta.get("sector"),
        "bars": len(bars),
        "first_bar": bars[0]["date"] if bars else None,
        "last_bar": bars[-1]["date"] if bars else None,
        "spikes": spikes,
        "lhb": sorted(lhb, key=lambda item: item["date"]),
    }
    if volatility is not None:
        stock["volatility_ann_pct"] = volatility
    stock.update(returns)
    if meta.get("float_cap_cny"):
        stock["float_cap_cny"] = float(meta["float_cap_cny"])
    if meta.get("price_cny"):
        # 透明计算：日均换手率 = 日均成交量(手)×100 ÷ 流通股本；流通股本取快照日。
        float_shares = float(meta["float_cap_cny"]) / float(meta["price_cny"])
        lots = [bar["volume_lot"] for bar in bars]
        if float_shares > 0 and lots:
            stock["turnover_avg_pct"] = round(
                (sum(lots) / len(lots)) * 100 / float_shares * 100, 4
            )
    if meta.get("amount_cny"):
        stock["snapshot_amount_cny"] = float(meta["amount_cny"])
    return stock


def attach_amounts(stocks: list[dict[str, Any]], start: str, end: str, limit: int | None) -> int:
    """尝试用东财日K补真实的日均成交额；整体不可得时保持缺口（不估算）。"""
    if not stocks:
        return 0
    probe = fetch_amount_kline(stocks[0]["code"], start, end)
    if probe is None:
        print("  东财日K不可得（限流），直接回退换手率口径，不逐只重试", file=sys.stderr)
        return 0
    amounts = [amount for _, amount in probe]
    stocks[0]["amount_avg_cny"] = round(sum(amounts) / len(amounts), 2)
    filled = 1
    targets = stocks[1 : limit] if limit else stocks[1:]
    for index, stock in enumerate(targets, 1):
        rows = fetch_amount_kline(stock["code"], start, end)
        if rows:
            values = [amount for _, amount in rows]
            stock["amount_avg_cny"] = round(sum(values) / len(values), 2)
            filled += 1
        if index % 25 == 0:
            print(f"  成交额补数 {index}/{len(targets)}，成功 {filled}", file=sys.stderr)
        time.sleep(0.35)
    return filled


# --- 主流程 -----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建个股股性分析输入档案")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/personality"))
    parser.add_argument("--lhb-months", type=int, default=12)
    parser.add_argument("--max-stocks", type=int, default=600, help="按龙虎榜命中次数取前 N 只")
    parser.add_argument("--min-bars", type=int, default=60, help="入档所需最少日线根数")
    parser.add_argument("--skip-amount", action="store_true", help="跳过东财成交额补数（接口常限流）")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    start = (as_of - timedelta(days=int(args.lhb_months * 30.5))).isoformat()

    print(f"[1/5] 股票池（东财 clist 全A快照）", file=sys.stderr)
    universe, total = fetch_universe()

    print(f"[2/5] 交易日历（腾讯上证指数日K）", file=sys.stderr)
    calendar_source = "tencent_index"
    try:
        days = fetch_trading_days(_date.fromisoformat(start), as_of)
    except FetchError as exc:
        days = trading_days_from_cache(args.cache_dir, start, as_of.isoformat())
        if not days:
            raise FetchError(
                f"交易日历不可得（{exc}），且缓存中的日线不足以重建日历"
            ) from exc
        calendar_source = "cache_union"
        print(
            f"  腾讯日K不可得（{exc}），降级为「池内已缓存日线的日期并集」重建日历",
            file=sys.stderr,
        )
    print(f"  窗口 {days[0]} ~ {days[-1]}，共 {len(days)} 个交易日（{calendar_source}）", file=sys.stderr)

    print(f"[3/5] 龙虎榜（{len(days)} 个交易日）", file=sys.stderr)
    lhb = fetch_lhb(days)

    ranked = sorted(lhb.items(), key=lambda item: (-len(item[1]), item[0]))
    eligible = [(code, rows) for code, rows in ranked if code in universe]
    bse_skipped = [code for code, _ in eligible if board_of(code, universe[code]["name"]) == "bse"]
    selected = [
        code
        for code, _ in eligible
        if board_of(code, universe[code]["name"]) != "bse"
    ][: args.max_stocks]
    missing = [code for code, _ in ranked if code not in universe]
    print(
        f"  龙虎榜命中 {len(lhb)} 只，其中 {len(lhb) - len(missing)} 只在股票池内；"
        f"跳过北交所 {len(bse_skipped)} 只（腾讯日K不覆盖，不猜）；"
        f"按命中次数取前 {len(selected)} 只",
        file=sys.stderr,
    )
    if not selected:
        raise FetchError("选中股票为空：龙虎榜命中与股票池无交集")

    print(f"[4/5] 个股日线（腾讯前复权，{len(selected)} 只）", file=sys.stderr)
    stocks: list[dict[str, Any]] = []
    failed: list[str] = []
    skipped_after_breaker = 0
    consecutive = 0
    # 断路线：日K源被 WAF 拦或整体不可用时，连续失败到阈值就停，不把剩余几百只逐只耗死。
    for index, code in enumerate(selected, 1):
        meta = universe[code]
        try:
            bars = fetch_bars(code, start, as_of.isoformat(), args.cache_dir)
            consecutive = 0
        except FetchError as exc:
            failed.append(code)
            consecutive += 1
            print(f"  {code} 日线抓取失败：{exc}", file=sys.stderr)
            if consecutive >= 5:
                skipped_after_breaker = len(selected) - index
                print(
                    f"  日线源连续 {consecutive} 次失败，判定源不可用："
                    f"跳过剩余 {skipped_after_breaker} 只，不逐只重试",
                    file=sys.stderr,
                )
                break
            continue
        if len(bars) < args.min_bars:
            failed.append(code)
            print(
                f"  {code} 日线不足（{len(bars)} < {args.min_bars} 根），剔除",
                file=sys.stderr,
            )
            continue
        stock = build_stock(code, meta, bars, lhb.get(code, []), DEFAULT_THRESHOLDS, days)
        stocks.append(stock)
        if index % 25 == 0 or index == len(selected):
            print(f"  日线 {index}/{len(selected)}，入档 {len(stocks)}", file=sys.stderr)
        time.sleep(0.12)

    if args.skip_amount:
        amount_filled = 0
    else:
        print(f"[4b/5] 尝试补真实日均成交额（东财日K f57）", file=sys.stderr)
        amount_filled = attach_amounts(stocks, start, as_of.isoformat(), None)

    # 容量口径按证据等级从高到低挑：真实成交额 > 流通市值（快照直披露）> 换手率（透明计算）。
    # 换手率的计算依赖流通市值与价格，覆盖率必然 ≤ 流通市值，所以「覆盖率不低于」即判定优先用流通市值；
    # 用 all() 会因个别停牌股的 f21 为空而整体退化到最低证据等级，这里按覆盖率比较。
    if amount_filled:
        capacity_metric = "amount_avg_cny"
    else:
        float_covered = sum(1 for stock in stocks if stock.get("float_cap_cny") is not None)
        turnover_covered = sum(1 for stock in stocks if stock.get("turnover_avg_pct") is not None)
        capacity_metric = "float_cap_cny" if float_covered >= turnover_covered else "turnover_avg_pct"
    covered = [stock for stock in stocks if stock.get(capacity_metric) is not None]
    if not covered:
        raise FetchError(f"流动性口径 {capacity_metric} 在所有股票上均缺失")

    payload = {
        "schema_version": "1.0",
        "as_of": as_of.isoformat(),
        "window": {
            "start": days[0],
            "end": days[-1],
            "trading_days": len(days),
            "lookback_months": args.lhb_months,
        },
        "universe": {
            "name": f"lhb-{args.lhb_months}m-top{len(stocks)}",
            "description": (
                f"近 {args.lhb_months} 个月登上东财龙虎榜的股票，按上榜次数降序取前 {len(stocks)} 只；"
                f"东财全A快照共 {total} 只，龙虎榜命中 {len(lhb)} 只。"
                f"北交所 {len(bse_skipped)} 只因日K源不覆盖而排除，日线不足 {len(failed)} 只被剔除"
                + (f"（其中 {skipped_after_breaker} 只因日K源中断未尝试）。" if skipped_after_breaker else "。")
                + f"交易日历来源：{'腾讯上证指数日K' if calendar_source == 'tencent_index' else '池内日线日期并集（腾讯日K不可得时的降级口径）'}。"
            ),
            "count": len(stocks),
            "selection_rule": f"龙虎榜命中次数降序 + 日线不少于 {args.min_bars} 根",
            "excluded_count": len(failed),
        },
        "capacity_metric": capacity_metric,
        "thresholds": DEFAULT_THRESHOLDS,
        "stocks": stocks,
        "sources": SOURCES,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"[5/5] 已写出 {args.out}：{len(stocks)} 只，流动性口径 {capacity_metric}，"
        f"补到真实成交额 {amount_filled} 只，剔除 {len(failed)} 只",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FetchError, OSError) as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(2)
