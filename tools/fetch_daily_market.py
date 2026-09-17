#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取单个交易日的 A 股盘面数据，组装成 ashare-daily-market-review 的 1.4 输入 market.json。

分工原则（机器能取的自动取，需要研究判断的显式声明）：

  自动抓取（东财一手接口）：
    indices           东财 push2delay ulist.np
    breadth           东财 push2delay clist（全A逐只，pz=100 翻页）
    short_term_sentiment  东财 push2ex 涨停池/跌停池/炸板池
    turnover          东财 push2his 上证+深证指数日K线
    sectors           东财 push2delay clist（m:90 t:2，f62 主力净额）
    funds             东财数据中心交易所两融（T+1）
    style             由同日指数涨跌幅相减得到

  需 --context 显式声明（缺省即留空/unknown，不猜）：
    mainline_matrix / prev_pool_performance / events / verification_points
    以及 short_term_sentiment.health_thresholds / short_term_sentiment.previous_metrics
  个股颗粒度（1.2 追加，同样缺省即省略）：
    streak_distribution / high_boards → short_term_sentiment
    concept_view → sectors.concept_view（第二套分类，须区别于行业层）
    sector_leaders → 以板块代码键控，落到 sectors.items[].leaders
  深度分析（1.4）：
    analysis_mode → 默认deep；只有显式core才走轻量路径
    deep_analysis → 缺少的六组件补为显式unknown，再由生成器严格校验、派生与渲染

组装后会调用技能的生成器做一次契约校验（--validate，默认开），通过才落盘。

用法：
  python3 tools/fetch_daily_market.py --date 2026-09-14 --out market.json
  python3 tools/fetch_daily_market.py --date 2026-09-14 --context ctx.json --raw-out raw.json
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request

from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

PUSH2DELAY = "https://push2delay.eastmoney.com/api/qt"
PUSH2EX = "https://push2ex.eastmoney.com"
CLIST = f"{PUSH2DELAY}/clist/get"
INDEX_URL = f"{PUSH2DELAY}/ulist.np/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
MARGIN_URL = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_RZRQ_LSHJ"
    "&columns=ALL&pageNumber=1&pageSize=8&sortColumns=DIM_DATE&sortTypes=-1"
)

# push2his 密集请求会整体限流（含编号备用主机），按避坑清单做主机轮换。
KLINE_HOSTS = ["push2his.eastmoney.com"] + [
    f"{i}.push2his.eastmoney.com" for i in range(1, 12)
]

# 全A（沪深京）非ST普通股口径
FS_BREADTH = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
FS_BOARD = "m:90+t:2"

UT = "7eea3edcaed734bea9cbfc24409ed989"

SECIDS = (
    "1.000001,0.399001,1.000300,1.000016,1.000688,0.399006,"
    "1.000905,1.000852,0.399303,0.899050,1.000922"
)
INDEX_NAMES = {
    "000001": "上证指数", "399001": "深证成指", "000300": "沪深300",
    "000016": "上证50", "000688": "科创50", "399006": "创业板指",
    "000905": "中证500", "000852": "中证1000", "399303": "国证2000",
    "899050": "北证50", "000922": "中证红利",
}

DEFAULT_CATEGORY = "东财行业板块（m:90 t:2 口径，申万二级/三级混合层级）"

DEEP_COMPONENT_NAMES = (
    "security_details",
    "liquidity_regime",
    "sentiment_cycle",
    "capital_co_movement",
    "catalyst_chains",
    "lhb_structure",
)

UNIVERSE = {
    "id": "all-a-non-st",
    "label": "全A非ST普通股",
    "population_rule": "沪深京A股，排除ST、退市整理与停牌",
    "includes_st": False,
    "includes_bse": True,
    "exclusions": ["ST", "退市整理", "停牌"],
}


def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_json(url, raw, key=None, hosts=None, tries=8):
    """带主机轮换 + 指数退避的抓取。hosts 非空时对 push2his 做编号主机轮换。"""
    candidates = [url]
    if hosts:
        host0 = hosts[0]
        candidates = [url.replace(host0, host) for host in hosts]
    last = None
    for attempt in range(tries):
        target = candidates[attempt % len(candidates)]
        try:
            data = http_json(target)
            if data.get("data") is None and "push2his" in target:
                raise RuntimeError("空响应")
            if key:
                raw[key] = data
            return data
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(min(1.5 + attempt * 1.5, 10))
    raise RuntimeError(f"{url}: {last}")


# ---------- 取证构造器 ----------

def make_source(ident, name, url=None):
    src = {"id": ident, "name": name}
    if url:
        src["url"] = url
    return src


def analysis_mode_from_context(ctx):
    """显式模式优先；未声明时默认deep。"""
    mode = ctx.get("analysis_mode")
    if mode is not None:
        if mode not in {"core", "deep"}:
            raise SystemExit("context.analysis_mode 必须是core或deep")
        return mode
    return "deep"


def deep_analysis_from_context(ctx, mode):
    """为默认deep交付补齐六组件；缺证保留unknown，不退回core。"""
    supplied = ctx.get("deep_analysis")
    if mode == "core":
        if supplied is None:
            return None
        if not isinstance(supplied, dict):
            raise SystemExit("context.deep_analysis 必须是object")
        return supplied
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict):
        raise SystemExit("context.deep_analysis 必须是object")
    completed = dict(supplied)
    for name in DEEP_COMPONENT_NAMES:
        if name in completed and completed[name] is None:
            raise SystemExit(f"context.deep_analysis.{name} 不能是null")
        completed.setdefault(
            name,
            {
                "availability": "unknown",
                "status_reason": f"context未提供{name}证据；默认深度复盘保留unknown，未退回core",
            },
        )
    return completed


def evidence(value, unit, observed_at, fetched_at, source, published_at=None):
    return {
        "value": value,
        "unit": unit,
        "observed_at": observed_at,
        "published_at": published_at or observed_at,
        "fetched_at": fetched_at,
        "source": source,
    }


# ---------- 各章节抓取 ----------

def session_stamp_date(ts):
    """f124 是行情更新时间戳；据此判断抓到的快照属于哪个交易日。"""
    if not isinstance(ts, (int, float)) or ts <= 0:
        return None
    return datetime.fromtimestamp(ts, CST).date().isoformat()


def fetch_breadth(raw, fetched_at):
    counts = {"advancers": 0, "decliners": 0, "unchanged": 0}
    quoted = 0
    page = 1
    stamps = []
    while page < 70:
        url = (
            f"{CLIST}?pn={page}&pz=100&po=1&np=1&fltt=2&invt=2"
            f"&fid=f3&fs={FS_BREADTH}&fields=f2,f3,f12,f14,f124"
        )
        payload = fetch_json(url, raw, key=f"breadth_p{page}").get("data") or {}
        rows = payload.get("diff") or []
        if not rows:
            break
        for row in rows:
            stamp = session_stamp_date(row.get("f124"))
            if stamp:
                stamps.append(stamp)
            change = row.get("f3")
            if not isinstance(change, (int, float)):
                continue  # 无报价（停牌/退市）不计入分母
            quoted += 1
            if change > 0:
                counts["advancers"] += 1
            elif change < 0:
                counts["decliners"] += 1
            else:
                counts["unchanged"] += 1
        if quoted >= (payload.get("total") or 0):
            break
        page += 1
    observed = max(set(stamps), key=stamps.count) if stamps else None
    return counts, quoted, observed


def fetch_pools(raw, date_str):
    compact = date_str.replace("-", "")
    zt = fetch_json(
        f"{PUSH2EX}/getTopicZTPool?ut={UT}&dpt=wz.ztzt&Pageindex=0"
        f"&pagesize=800&sort=fbt%3Aasc&date={compact}",
        raw, key="ztpool",
    ).get("data") or {}
    dt = fetch_json(
        f"{PUSH2EX}/getTopicDTPool?ut={UT}&dpt=wz.ztzt&Pageindex=0"
        f"&pagesize=800&sort=fund%3Aasc&date={compact}",
        raw, key="dtpool",
    ).get("data") or {}
    zb = fetch_json(
        f"{PUSH2EX}/getTopicZBPool?ut={UT}&dpt=wz.ztzt&Pageindex=0"
        f"&pagesize=800&sort=fbt%3Aasc&date={compact}",
        raw, key="zbpool",
    ).get("data") or {}
    pool = zt.get("pool") or []
    streaks = [row.get("lbc") for row in pool if isinstance(row.get("lbc"), (int, float))]
    return {
        "limit_up": len(pool),
        "limit_down": len(dt.get("pool") or []),
        "open_board_failed": len(zb.get("pool") or []),
        "highest_streak": max(streaks) if streaks else 0,
    }


def fetch_indices(raw):
    url = f"{INDEX_URL}?secids={SECIDS}&fields=f12,f14,f2,f3,f124&fltt=2&invt=2"
    rows = fetch_json(url, raw, key="indices").get("data", {}).get("diff") or []
    stamps = [session_stamp_date(row.get("f124")) for row in rows]
    stamps = [s for s in stamps if s]
    observed = max(set(stamps), key=stamps.count) if stamps else None
    return {row["f12"]: row for row in rows}, observed


def fetch_boards(raw, top):
    """行业板块涨跌幅与主力净额；降序+升序各取两页，覆盖两端。以 f12（板块代码）为键。"""
    boards = {}
    for order, page_no in (("desc", 1), ("desc", 2), ("asc", 1), ("asc", 2), ("asc", 3)):
        url = (
            f"{CLIST}?pn={page_no}&pz=100&po={'1' if order == 'desc' else '0'}"
            f"&np=1&fltt=2&invt=2&fid=f62&fs={FS_BOARD}&fields=f12,f14,f3,f62,f6"
        )
        payload = fetch_json(url, raw, key=f"board_{order}{page_no}").get("data") or {}
        for row in payload.get("diff") or []:
            boards.setdefault(row["f12"], row)
    ranked = sorted(boards.values(), key=lambda r: -(r["f62"] or 0))
    extremes = [row["f12"] for row in ranked[:top]] + [row["f12"] for row in ranked[-top:]]
    return boards, extremes


def fetch_margin(raw, market_date):
    rows = (fetch_json(MARGIN_URL, raw, key="margin").get("result") or {}).get("data") or []
    available = [r for r in rows if r["DIM_DATE"][:10] <= market_date]
    if not available:
        return None, None
    day = max(r["DIM_DATE"][:10] for r in available)
    return {r["DIM_DATE"][:10]: r for r in available}, day


def fetch_turnover(raw, market_date, kline_cache_path):
    """上证+深证指数日K线 amount 加总。push2his 限流时回退到本地缓存。"""
    cache_path = Path(kline_cache_path) if kline_cache_path else None
    cached = None
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    try:
        begin = (_date.fromisoformat(market_date) - timedelta(days=150)).strftime("%Y%m%d")
        series = {}
        for secid, label in (("1.000001", "上海"), ("0.399001", "深圳")):
            url = (
                f"{KLINE_URL}?secid={secid}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57"
                f"&klt=101&fqt=1&beg={begin}&end=20500101"
            )
            data = fetch_json(url, raw, key=f"kline_{label}", hosts=KLINE_HOSTS, tries=4)
            rows = (data.get("data") or {}).get("klines") or []
            by_day = {}
            for line in rows:
                parts = line.split(",")
                by_day[parts[0]] = float(parts[6])  # f57 = amount
            series[label] = by_day
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(series, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except Exception as exc:  # noqa: BLE001
        if cached is None:
            raise RuntimeError(f"K线抓取失败且无缓存：{exc}") from exc
        series = cached
        raw["kline_cache_used"] = True
    merged = {}
    for label in ("上海", "深圳"):
        for day, amount in series.get(label, {}).items():
            merged[day] = merged.get(day, 0.0) + amount
    return merged


def window_average(merged, days):
    days_sorted = sorted(merged)
    values = [merged[d] for d in days_sorted[-days:]]
    return sum(values) / len(values)


# ---------- 组装 ----------

def build_input(date_str, as_of, fetched_at, snapshot_type, cutoff_at, raw, ctx, top,
                allow_mismatch=False):
    counts, quoted, breadth_date = fetch_breadth(raw, fetched_at)
    pools = fetch_pools(raw, date_str)
    index_by_code, index_date = fetch_indices(raw)
    boards, extremes = fetch_boards(raw, top)

    # 宽度/指数/板块是「最新快照」接口，没有 date 参数；用 f124 判断快照属于哪一天，
    # 与声明的交易日不符时默认拒绝（避免把别日的盘面挂到今天的标签下）。
    observed = sorted({d for d in (breadth_date, index_date) if d})
    mismatch_note = None
    if observed and date_str not in observed:
        detail = "、".join(observed)
        if not allow_mismatch:
            raise SystemExit(
                f"行情快照日期为 {detail}，与 --date {date_str} 不一致。"
                "宽度/指数/板块为「最新快照」接口，无法回填历史交易日；"
                "请用当天日期重跑，或加 --allow-date-mismatch 强制继续（相关章节会标记 partial）。"
            )
        mismatch_note = (
            f"注意：抓到的行情快照日期为 {detail}，与本输入声明的交易日 {date_str} 不一致"
            "（宽度/指数/板块为最新快照接口）；相关章节按 partial 处理。"
        )
    prefix = (mismatch_note + " ") if mismatch_note else ""

    classification = (
        (ctx.get("mainline_matrix") or {}).get("classification") or DEFAULT_CATEGORY
    )

    # 主题引用的板块（用板块代码 f12 引用）必须进 sectors，否则 mainline_matrix 会引用悬空。
    referenced = sorted(
        {
            board_id
            for theme in (ctx.get("mainline_matrix") or {}).get("themes", [])
            for board_id in theme.get("boards", [])
        }
    )
    selected = sorted(set(referenced) | set(extremes))
    missing_boards = sorted(board_id for board_id in referenced if board_id not in boards)

    def board_evidence(board_id, field):
        row = boards[board_id]
        unit = "percent" if field == "f3" else "CNY"
        return evidence(
            float(row[field]), unit, date_str, fetched_at,
            make_source("em-board", "东财行业板块接口 push2delay", f"{CLIST}?fs={FS_BOARD}&fid=f62"),
        )

    sector_items = []
    for board_id in selected:
        row = boards[board_id]
        sector_items.append(
            {
                "id": board_id,
                "name": row["f14"],
                "change_pct": board_evidence(board_id, "f3"),
                "fund_flow": board_evidence(board_id, "f62"),
                "fund_flow_method_category": "provider_model",
            }
        )
    sector_items.sort(key=lambda item: -float(item["change_pct"]["value"]))

    em_index_src = make_source("em-index", "东财指数行情接口 push2delay", INDEX_URL)
    index_items = []
    for code, label in INDEX_NAMES.items():
        row = index_by_code.get(code)
        if row is None or row.get("f2") in (None, "-") or row.get("f3") in (None, "-"):
            continue
        index_items.append(
            {
                "id": f"{'sh' if code.startswith(('000', '899')) else 'sz'}{code}",
                "name": label,
                "primary": code == "000001",
                "close": evidence(float(row["f2"]), "index_points", date_str, fetched_at, em_index_src),
                "change_pct": evidence(float(row["f3"]), "percent", date_str, fetched_at, em_index_src),
            }
        )

    sections = {
        "indices": {
            "availability": ("partial" if mismatch_note else "available") if index_items else "unknown",
            "status_reason": prefix + (
                f"{len(index_items)}个主要指数收盘价与涨跌幅来自东财 push2delay ulist.np。"
                if index_items
                else "指数行情接口未返回有效数据。"
            ),
            "items": index_items,
        },
        "breadth": {
            "availability": "partial" if mismatch_note else "available",
            "status_reason": prefix + (
                f"非ST全A（沪深京）逐只统计：有报价样本{quoted}只（无报价的停牌/退市股不计入分母）。"
                "涨跌停取东财涨停池/跌停池，与宽度同股票池。"
            ),
            "universe": dict(UNIVERSE),
            "metrics": {
                name: evidence(count, "count", date_str, fetched_at,
                               make_source("em-full-a", "东财 push2delay 行情接口", f"{CLIST}?fs={FS_BREADTH}"))
                for name, count in counts.items()
            }
            | {
                "limit_up": evidence(pools["limit_up"], "count", date_str, fetched_at,
                                     make_source("em-ztpool", "东财涨停板行情接口 push2ex", f"{PUSH2EX}/getTopicZTPool")),
                "limit_down": evidence(pools["limit_down"], "count", date_str, fetched_at,
                                       make_source("em-dtpool", "东财跌停池接口 push2ex", f"{PUSH2EX}/getTopicDTPool")),
            },
        },
        "short_term_sentiment": {
            "availability": "partial" if mismatch_note else "available",
            "status_reason": prefix + (
                "东财涨停池/炸板池/跌停池按 date 参数精确取当日收盘口径（与快照日期无关）；"
                "股票池与非ST全A宽度一致。"
            ),
            "universe": dict(UNIVERSE),
            "methodology": (
                "limit_up/limit_down 取东财涨停池与跌停池；open_board_failed 取炸板池；"
                "limit_attempts = limit_up + open_board_failed；highest_streak 取涨停池 lbc 最大值。"
                "全部为东财收盘后口径。"
            ),
            "metrics": {
                "open_board_failed": evidence(pools["open_board_failed"], "count", date_str, fetched_at,
                                              make_source("em-zbpool", "东财炸板池接口 push2ex", f"{PUSH2EX}/getTopicZBPool")),
                "limit_attempts": evidence(pools["limit_up"] + pools["open_board_failed"], "count", date_str, fetched_at,
                                           make_source("em-ztpool", "东财涨停板行情接口 push2ex", f"{PUSH2EX}/getTopicZTPool")),
                "highest_streak": evidence(pools["highest_streak"], "count", date_str, fetched_at,
                                           make_source("em-ztpool", "东财涨停板行情接口 push2ex", f"{PUSH2EX}/getTopicZTPool")),
            },
        },
        "sectors": {
            "availability": "partial" if mismatch_note else "available",
            "status_reason": prefix + (
                f"采用{classification}，板块当日涨跌幅与主力净流入(f62)齐全。"
                f"为控制篇幅，items 收录同一体系下的受控子集：主题引用板块 + 主力净流入两端各{top}个，"
                f"共{len(sector_items)}个，并非全量。主力净流入为供应商模型口径，不等同交易所事实。"
            ),
            "classification": classification,
            "caveat": (
                "板块列表同时含二级与三级板块，个别三级板块与所属二级板块数值重复；"
                "主题归组时凡引用即只取其一，不做重复求和。items 为受控子集，未收录的板块不代表资金流为零。"
            ),
            "items": sector_items,
        },
        "style": {
            "availability": "partial" if (mismatch_note or len(index_by_code) < 11) else "available",
            "status_reason": prefix + (
                "三条相对结构均由同日指数收盘涨跌幅相减得到，窗口为当日1个交易日；"
                "仅描述当日相对强弱，不含估值含义。"
            ),
            "items": [
                {
                    "name": "小盘相对大盘（国证2000 − 上证50）",
                    "interpretation": "正值表示本样本内小盘相对大盘走强",
                    "window": {"trading_days": 1, "end_at": date_str},
                    "metric": evidence(float(index_by_code["399303"]["f3"]) - float(index_by_code["000016"]["f3"]),
                                       "percent", date_str, fetched_at, em_index_src),
                },
                {
                    "name": "成长相对价值（创业板指 − 沪深300）",
                    "interpretation": "正值表示本样本内成长风格相对大盘价值占优",
                    "window": {"trading_days": 1, "end_at": date_str},
                    "metric": evidence(float(index_by_code["399006"]["f3"]) - float(index_by_code["000300"]["f3"]),
                                       "percent", date_str, fetched_at, em_index_src),
                },
                {
                    "name": "红利相对全市场（中证红利 − 沪深300）",
                    "interpretation": "正值表示本样本内高股息红利风格相对大盘占优",
                    "window": {"trading_days": 1, "end_at": date_str},
                    "metric": evidence(float(index_by_code["000922"]["f3"]) - float(index_by_code["000300"]["f3"]),
                                       "percent", date_str, fetched_at, em_index_src),
                },
            ],
        },
    }

    # 成交与流动性
    try:
        merged = fetch_turnover(raw, date_str, ctx.get("kline_cache_path"))
        days = sorted(merged)
        if date_str not in merged:
            raise RuntimeError(f"K线序列不含 {date_str}")
        prior = [d for d in days if d < date_str]
        kline_src = make_source("em-kline-hs", "东财指数日K线接口 push2his", KLINE_URL)
        amount = merged[date_str]
        metrics = {
            "amount": evidence(amount, "CNY", date_str, fetched_at, kline_src),
            "avg_5d_amount": evidence(window_average(merged, 5), "CNY", date_str, fetched_at, kline_src)
            | {"window": {"trading_days": 5, "end_at": date_str}},
            "avg_20d_amount": evidence(window_average(merged, 20), "CNY", date_str, fetched_at, kline_src)
            | {"window": {"trading_days": 20, "end_at": date_str}},
        }
        if prior:
            metrics["previous_amount"] = evidence(merged[prior[-1]], "CNY", prior[-1], fetched_at, kline_src)
        sections["turnover"] = {
            "availability": "available",
            "status_reason": "沪深两市成交额由上证指数与深证成指日K线 amount 加总（不含北交所），前一交易日、5日/20日均值同口径。",
            "metrics": metrics,
        }
    except Exception as exc:  # noqa: BLE001
        sections["turnover"] = {
            "availability": "unknown",
            "status_reason": f"成交额未取得：{exc}。push2his 密集请求会被限流，可用 --kline-cache 复用已落盘K线，或稍后重试。",
            "metrics": {},
        }

    # 资金证据（交易所两融，T+1）
    margin, margin_day = fetch_margin(raw, date_str)
    if margin:
        margin_src = make_source("em-margin-lshj", "东财数据中心（交易所两融披露）", MARGIN_URL)
        sections["funds"] = {
            "availability": "partial",
            "status_reason": (
                f"交易所两融为T+1披露，本次采集时点（{date_str}）最新可得观察日为{margin_day}；"
                f"{date_str}两融尚未发布，属T+1而非数据缺失。其余资金口径未纳入，故本章节维持partial。"
                "板块级主力净流入已在 sectors 章按 provider_model 口径披露。"
            ),
            "items": [
                {
                    "name": "融资净流入（沪深两市）",
                    "methodology": "交易所披露的全市场融资买入额减融资偿还额，属法定披露事实，不等同于“主力资金”",
                    "method_category": "exchange_fact",
                    "metric": evidence(margin[margin_day]["RZJME"], "CNY", margin_day, fetched_at, margin_src),
                },
                {
                    "name": "融资余额（沪深两市）",
                    "methodology": "交易所披露的全市场融资余额期末值",
                    "method_category": "exchange_fact",
                    "metric": evidence(margin[margin_day]["RZYE"], "CNY", margin_day, fetched_at, margin_src),
                },
                {
                    "name": "融券余额（沪深两市）",
                    "methodology": "交易所披露的全市场融券余额期末值",
                    "method_category": "exchange_fact",
                    "metric": evidence(margin[margin_day]["RQYE"], "CNY", margin_day, fetched_at, margin_src),
                },
            ],
        }
    else:
        sections["funds"] = {
            "availability": "unknown",
            "status_reason": "交易所两融接口未返回不晚于交易日的披露记录。",
            "items": [],
        }

    # 需人工判断的章节：由 --context 显式声明，缺省即不注入（按 unknown 处理）。
    if ctx.get("health_thresholds"):
        sections["short_term_sentiment"]["health_thresholds"] = ctx["health_thresholds"]
    # 前一可比交易日情绪指标：只有整组同口径时才会被生成器用于「修复」评估。
    if ctx.get("previous_metrics"):
        sections["short_term_sentiment"]["previous_metrics"] = ctx["previous_metrics"]
    if ctx.get("events"):
        sections["events"] = ctx["events"]
    mainline = ctx.get("mainline_matrix")
    if mainline:
        mainline.setdefault("classification", classification)
        if missing_boards:
            raise SystemExit(
                "context.mainline_matrix 引用了板块列表中不存在的板块："
                + "、".join(missing_boards)
            )
        sections["mainline_matrix"] = mainline
    prev_pool = ctx.get("prev_pool")
    if prev_pool:
        prev_pool.setdefault("universe", dict(UNIVERSE))
        sections["prev_pool_performance"] = prev_pool
    # 1.2 发布后追加的个股颗粒度结构，同样是「声明才注入」。
    for key in ("streak_distribution", "high_boards"):
        if ctx.get(key):
            sections["short_term_sentiment"][key] = ctx[key]
    if ctx.get("concept_view"):
        sections["sectors"]["concept_view"] = ctx["concept_view"]
    # 板块内个股：context 以板块代码（f12）键控，落到对应 sector item 的 leaders。
    leaders_by_board = ctx.get("sector_leaders") or {}
    if leaders_by_board:
        board_index = {
            item["id"]: item for item in sections["sectors"].get("items", [])
        }
        for board_id, leaders in leaders_by_board.items():
            target = board_index.get(board_id)
            if target is None:
                raise SystemExit(
                    f"context.sector_leaders 引用了板块列表中不存在的板块：{board_id}"
                )
            target["leaders"] = leaders

    analysis_mode = analysis_mode_from_context(ctx)
    market = {
        "schema_version": "1.4",
        "analysis_mode": analysis_mode,
        "market_date": date_str,
        "as_of": as_of,
        "snapshot": {
            "type": snapshot_type,
            "revision": int(ctx.get("revision", 1)),
            "cutoff_at": cutoff_at,
            "raw_evidence_sha256": hashlib.sha256(
                json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
            "supersedes_sha256": ctx.get("supersedes_sha256"),
        },
        "sections": sections,
        "verification_points": ctx.get("verification_points", []),
    }
    deep_analysis = deep_analysis_from_context(ctx, analysis_mode)
    if deep_analysis is not None:
        market["deep_analysis"] = deep_analysis
    return market, {"quoted": quoted, "pools": pools, "boards": len(boards),
                    "selected_sectors": len(sector_items), "missing_boards": missing_boards,
                    "observed_session_dates": observed, "date_mismatch": bool(mismatch_note)}


def validate_output(path, as_of):
    """调用技能生成器做一次契约校验（写临时文件，失败给出 stderr）。"""
    import subprocess
    import tempfile

    skill = Path(__file__).resolve().parent.parent / "skills" / "ashare-daily-market-review"
    cli = skill / "scripts" / "generate_daily_review.py"
    if not cli.exists():
        return None, "未找到技能生成器，跳过校验"
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [
                sys.executable, str(cli),
                "--input", str(path),
                "--as-of", as_of,
                "--output", str(Path(tmp) / "r.md"),
                "--summary-out", str(Path(tmp) / "r.json"),
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    return proc.returncode == 0, (proc.stderr.strip() or proc.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description="抓取并组装 ashare-daily-market-review 的 1.4 输入")
    parser.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--out", type=Path, default=Path("market.json"))
    parser.add_argument("--as-of", help="默认同 --date")
    parser.add_argument("--fetched-at", help="抓取时间，带时区；默认取当前北京时间")
    parser.add_argument("--snapshot-type", default="post_close",
                        choices=["close", "post_close", "weekend_update"])
    parser.add_argument("--cutoff-at", help="快照截止时间；默认 {date}T20:45:00+08:00")
    parser.add_argument("--context", type=Path, help="研究判断章节的 JSON（themes/prev_pool/events/…）")
    parser.add_argument("--raw-out", type=Path, help="可选：把原始接口响应落盘以便复算")
    parser.add_argument("--kline-cache", type=Path, help="K线缓存文件（读写），用于 push2his 限流时回退")
    parser.add_argument("--sector-top", type=int, default=15, help="行业资金两端各收录多少个（默认15）")
    parser.add_argument("--allow-date-mismatch", action="store_true",
                        help="快照日期与 --date 不一致时仍继续（相关章节标记 partial）")
    parser.add_argument("--no-validate", action="store_true", help="跳过组装后的契约校验")
    args = parser.parse_args()

    _date.fromisoformat(args.date)  # 提前校验格式
    as_of = args.as_of or args.date
    fetched_at = args.fetched_at or datetime.now(CST).replace(microsecond=0).isoformat()
    cutoff_at = args.cutoff_at or f"{args.date}T20:45:00+08:00"

    ctx = {}
    if args.context:
        ctx = json.loads(Path(args.context).read_text(encoding="utf-8"))
    if args.kline_cache:
        ctx["kline_cache_path"] = str(args.kline_cache)

    raw = {}
    market, stats = build_input(
        args.date, as_of, fetched_at, args.snapshot_type, cutoff_at, raw, ctx,
        args.sector_top, allow_mismatch=args.allow_date_mismatch,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.raw_out:
        args.raw_out.parent.mkdir(parents=True, exist_ok=True)
        args.raw_out.write_text(
            json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8"
        )

    result = {"market": str(args.out), "stats": stats}
    if not args.no_validate:
        ok, message = validate_output(args.out, as_of)
        result["validation"] = "passed" if ok else "failed"
        if ok is False:
            print(f"契约校验失败：{message}", file=sys.stderr)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 2
        if ok is None:
            result["validation_note"] = message
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
