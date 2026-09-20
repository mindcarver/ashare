"""读者版旁路证据门禁；缺证据的补充项降级，不把快照文件名当观察日。"""
import copy
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from evidence import validate_source
from schema import ReviewError, parse_date, parse_datetime


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def breadth_distribution(rows):
    """互斥且穷尽；平盘严格为0，±5/±9边界只计一次。"""
    labels = ['≤−9%', '−9%～−5%（含）', '−5%～0%', '平盘', '0%～5%', '5%～9%', '≥9%']
    counts = [0] * 7
    seen = set()
    for row in rows:
        code = str(row.get('f12') or '')
        if not code or code in seen:
            raise ReviewError('宽度样本证券代码缺失或重复')
        seen.add(code)
        v = row.get('f3')
        if not number(v):
            continue
        i = 0 if v <= -9 else 1 if v <= -5 else 2 if v < 0 else 3 if v == 0 else 4 if v < 5 else 5 if v < 9 else 6
        counts[i] += 1
    return {'labels': labels, 'counts': counts, 'total': sum(counts),
            'advancers': sum(counts[4:]), 'decliners': sum(counts[:3]), 'unchanged': counts[3]}


def exact_series(rows, market_date):
    """裁掉未来记录，缺目标日时不退回最后一条。"""
    dated = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get('date'):
            raise ReviewError('日序列必须逐行声明日期')
        d = parse_date(row['date'], 'date').isoformat()
        if d in dated:
            raise ReviewError('日序列存在重复日期')
        if d <= market_date:
            dated[d] = row
    return [dated[d] for d in sorted(dated)] if market_date in dated else []


def metadata_valid(meta, market, observed):
    if not isinstance(meta, dict):
        raise ReviewError('缺少补充证据元数据')
    if parse_date(meta.get('observed_at'), 'observed_at').isoformat() != observed:
        raise ReviewError('补充快照观察日不符')
    published = parse_date(meta.get('published_at'), 'published_at')
    fetched = parse_datetime(meta.get('fetched_at'), 'fetched_at')
    cutoff = parse_datetime(market['snapshot']['cutoff_at'], 'cutoff_at')
    if meta.get('publication_basis') == 'known_by_fetch' and published != fetched.astimezone(ZoneInfo('Asia/Shanghai')).date():
        raise ReviewError('保守可见日期必须等于抓取日，不能回填交易日')
    if published > parse_date(market['as_of'], 'as_of') or fetched > cutoff or published > fetched.date():
        raise ReviewError('补充证据超出截止时间或发布日期晚于抓取')
    validate_source(meta.get('source'), 'supplement')
    if meta.get('method_category') not in {'provider_model', 'exchange_fact', 'derived', 'activity_proxy'}:
        raise ReviewError('补充证据缺少方法类别')


def stock_observations(sections, deep):
    lookup = {}
    for sector in sections['sectors'].get('items', []):
        for row in sector.get('leaders', []):
            lookup[row['code']] = {'name': row['name'], 'change': (row.get('change_pct') or {}).get('value'),
                                   'flow': (row.get('fund_flow') or {}).get('value')}
    for row in (deep.get('security_details') or {}).get('items', []):
        lookup[row['code']] = {'name': row['name'], 'change': row.get('change_pct'),
                              'flow': row.get('fund_flow_windows_cny', {}).get(1),
                              'seal_amount': (row.get('seal_structure') or {}).get('sealed_order_amount_cny')}
    return lookup


def checked_extra(raw, market, observations):
    """现有无日期旁路保留在原文件；逐块拒用并记录原因，绝不自动补日期。"""
    raw = copy.deepcopy(raw)
    accepted, exclusions = {}, []
    meta = raw.get('evidence') or {}
    for key in ('stock_inflow', 'stock_outflow', 'volume_scan', 'zt_pool', 'previous_zt_pool',
                'stock_windows', 'breadth_rows', 'etf_klines', 'index_klines', 'lhb_rows', 'board_history'):
        value = raw.get(key)
        if value is None or (not value and key not in ('zt_pool', 'previous_zt_pool')):
            continue
        try:
            expected = market['market_date']
            if key == 'previous_zt_pool':
                expected = market['sections']['prev_pool_performance']['previous_market_date']
            metadata_valid(meta.get(key), market, expected)
            rows = list(value.values()) if isinstance(value, dict) else value
            if key == 'breadth_rows':
                for row in rows:
                    stamp = row.get('f124')
                    if not number(stamp) or datetime.fromtimestamp(stamp, ZoneInfo('Asia/Shanghai')).date().isoformat() != expected:
                        raise ReviewError('宽度逐行时间戳缺失或错日')
            if key in ('stock_inflow', 'stock_outflow', 'volume_scan', 'stock_windows'):
                seen = set()
                archival = meta[key].get('retrieval_mode') == 'historical_archive'
                matches = {r.get('f12'): r for r in meta[key].get('quote_crosscheck', [])}
                if archival and (not matches or meta[key].get('publication_basis') != 'known_by_fetch'):
                    raise ReviewError('历史存档须有独立同日报价交叉核验和保守可见日期')
                for row in rows:
                    code = str(row.get('f12') or '')
                    if not code or code in seen:
                        raise ReviewError('个股代码缺失或重复')
                    seen.add(code)
                    if archival:
                        quote = matches.get(code, {})
                        stamp = quote.get('f124')
                        if not number(stamp) or datetime.fromtimestamp(stamp, ZoneInfo('Asia/Shanghai')).date().isoformat() != expected:
                            raise ReviewError('历史存档匹配行情缺少同日时间戳')
                        if any(not number(row.get(f)) or not number(quote.get(f)) or abs(row[f]-quote[f]) > 0.005 for f in ('f2', 'f3')):
                            raise ReviewError('历史存档价格涨跌与独立同日报价不一致')
                    stamp = row.get('f124')
                    if stamp is not None:
                        day = datetime.fromtimestamp(stamp, ZoneInfo('Asia/Shanghai')).date().isoformat()
                        if day != expected:
                            raise ReviewError('行情行日期与报告不符')
                    for field in ('f3', 'f62', 'f6', 'f8', 'f10'):
                        if field in row and not number(row[field]):
                            row[field] = None
                    known = observations.get(code, {})
                    for field, metric in (('f3', 'change'), ('f62', 'flow')):
                        a, b = row.get(field), known.get(metric)
                        if b is not None and number(a):
                            tolerance = 0.03 if field == 'f3' else max(1, abs(b) * 0.005)
                            if abs(a - b) > tolerance:
                                raise ReviewError('补充个股与基础证据冲突')
                if key == 'volume_scan':
                    window = meta[key].get('window') or {}
                    if window.get('trading_days') != 5 or window.get('end_at') != expected:
                        raise ReviewError('量比窗口不明确')
            if key == 'board_history':
                boards = {row['id']: row for row in market['sections']['sectors'].get('items', [])}
                for board_id, info in value.get('boards', {}).items():
                    baseline = boards.get(board_id)
                    if baseline is None:
                        raise ReviewError('历史板块ID未在主输入声明')
                    series = {}
                    for raw_row in info.get('rows', []):
                        day, amount = raw_row.split(',')
                        parse_date(day, 'board_date')
                        if day in series:
                            raise ReviewError('板块历史存在重复日期')
                        amount = float(amount)
                        if not number(amount):
                            raise ReviewError('板块历史金额非有限数')
                        series[day] = amount
                    today = series.get(expected)
                    base = (baseline.get('fund_flow') or {}).get('value')
                    if not number(today) or not number(base) or abs(today-base) > max(1, abs(base)*0.005):
                        raise ReviewError('板块历史当日净额与主输入冲突或缺失')
                    info['name'] = baseline['name']
                    info['rows'] = [f'{day},{series[day]}' for day in sorted(series) if day <= expected]
            if key in ('etf_klines', 'index_klines'):
                value = {code: exact_series(series, expected) for code, series in value.items()}
                value = {code: series for code, series in value.items() if series}
            if key == 'lhb_rows':
                if any(str(row.get('TRADE_DATE', ''))[:10] != expected for row in value):
                    raise ReviewError('龙虎榜交易日不符')
                if any(not number(row.get('BILLBOARD_NET_AMT')) for row in value):
                    raise ReviewError('龙虎榜净额缺失')
            if key in ('zt_pool', 'previous_zt_pool'):
                if not isinstance(value, list):
                    raise ReviewError('涨停池必须为数组，已确认零家时使用空数组')
                codes = [row.get('c') for row in value]
                if not all(codes) or len(set(codes)) != len(codes):
                    raise ReviewError('涨停池成员重复或缺代码')
                if any(row.get('lbc', 0) < 1 for row in value):
                    raise ReviewError('涨停池板数无效')
                if key == 'zt_pool':
                    for row in value:
                        known = observations.get(row['c'], {}).get('seal_amount')
                        if number(known) and number(row.get('fund')) and abs(row['fund']-known) > max(1, abs(known)*0.005):
                            raise ReviewError('补充封单与主输入快照冲突，须统一修订后再发布')
            accepted[key] = copy.deepcopy(value)
        except (ReviewError, ValueError, TypeError, KeyError) as exc:
            exclusions.append({'component': key, 'reason': str(exc)})
    # 自由洞见不能因挂了股票名就被认证；只接受结构化假设与精确代码锚。
    for item in raw.get('insights') or []:
        anchors = item.get('anchors') or []
        if (item.get('causal_status') != 'hypothesis' or not item.get('counter_evidence')
                or not item.get('verification') or not anchors
                or any(code not in observations for code in anchors)):
            exclusions.append({'component': 'insights', 'reason': '缺少结构化假设、反证、验证或代码锚'})
        else:
            accepted.setdefault('insights', []).append(copy.deepcopy(item))
    for key in ('news', 'calendar', 'chain_map', 'zt_amounts', 'zt_pool_0915'):
        if raw.get(key):
            exclusions.append({'component': key, 'reason': '请纳入已校验主输入，不从旧旁路直接发布'})
    return accepted, exclusions


def check_breadth(rows, section):
    universe = section.get('universe') or {}
    if not universe.get('includes_st', False) and any('ST' in str(r.get('f14', '')).upper() for r in rows if number(r.get('f3'))):
        raise ReviewError('宽度样本含ST，与声明的非ST股票池冲突')
    stats = breadth_distribution(rows)
    for field in ('advancers', 'decliners', 'unchanged'):
        expected = (section.get('metrics', {}).get(field) or {}).get('value')
        if expected is None or expected != stats[field]:
            raise ReviewError('宽度样本与主输入上涨/下跌/平盘统计不一致')
    return stats


def legacy_breadth(workdir, market):
    """旧原始快照只用逐行时间戳自证日期；发现口径冲突后隔离，不静默覆盖主输入。"""
    for filename in ('raw_full.json', f"raw_{market['market_date'][5:].replace('-', '')}_full.json"):
        path = Path(workdir) / filename
        if not path.exists():
            continue
        raw = json.loads(path.read_text())
        rows = [row for key, page in raw.items() if key.startswith('breadth_p')
                for row in (page.get('data') or {}).get('diff', [])]
        for row in rows:
            stamp = row.get('f124')
            if not number(stamp) or datetime.fromtimestamp(stamp, ZoneInfo('Asia/Shanghai')).date().isoformat() != market['market_date']:
                raise ReviewError('旧宽度样本缺少同日逐行时间戳')
        return rows
    return None
