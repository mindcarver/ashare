"""读者报告的可复算分析；只消费已校验的证据。"""
from statistics import mean, median

from reader_evidence import number
from schema import ReviewError


def previous_pool_analysis(ctx):
    if not ctx.zt_prev or (not ctx.zt and not getattr(ctx, 'zt_available', False)):
        return {'groups': [], 'rows': []}
    current = {row['c'] for row in ctx.zt}
    rows = []
    for previous in ctx.zt_prev:
        code = previous['c']
        quote = ctx.windows.get(code, {})
        known = ctx.observations.get(code, {})
        change = quote.get('f3', known.get('change'))
        flow = quote.get('f62', known.get('flow'))
        rows.append({'code': code, 'name': previous['n'], 'prior_streak': previous['lbc'],
                     'change': change if number(change) else None,
                     'flow': flow if number(flow) else None, 'promoted': code in current})
    available = [row['change'] for row in rows if row['change'] is not None]
    baseline = ctx.derived.get('prev_pool_performance') or {}
    if len(available) == len(rows):
        for key, actual in (('avg_change_pct', mean(available)), ('median_change_pct', median(available))):
            if number(baseline.get(key)) and abs(baseline[key]-actual) > 0.03:
                raise ReviewError('昨日池逐股收益与主输入汇总冲突')
    groups = []
    for title, selected in [('昨日首板', [r for r in rows if r['prior_streak'] == 1]),
                            ('昨日连板', [r for r in rows if r['prior_streak'] > 1])]:
        prices = [r['change'] for r in selected if r['change'] is not None]
        flows = [r['flow'] for r in selected if r['flow'] is not None]
        groups.append({'name': title, 'count': len(selected), 'price_covered': len(prices),
                       'average': mean(prices) if prices else None, 'median': median(prices) if prices else None,
                       'flow_covered': len(flows), 'flow_total': sum(flows) if flows and len(flows) == len(selected) else None,
                       'flow_sample': sum(flows) if flows else None, 'promoted': sum(r['promoted'] for r in selected),
                       'broken': sum(not r['promoted'] for r in selected), 'declined': sum(v < 0 for v in prices),
                       'deep_declined': sum(v <= -5 for v in prices)})
    return {'groups': groups, 'rows': rows}


def seal_quality(rows):
    samples = [r['fund']/r['amount'] for r in rows if number(r.get('fund')) and r['fund'] >= 0 and number(r.get('amount')) and r['amount'] > 0]
    breaks = [r['zbc'] for r in rows if number(r.get('zbc')) and r['zbc'] >= 0]
    return {'count': len(rows), 'ratio_covered': len(samples), 'ratio_median': median(samples) if samples else None,
            'break_covered': len(breaks), 'ever_broken': sum(v > 0 for v in breaks)}


def window_comparisons(ctx):
    result = []
    for row in (ctx.deep.get('security_details') or {}).get('items', []):
        w = row['fund_flow_windows_cny']
        # 窗口是重叠累计值，只描述符号差异；不比较成资金加速度。
        if number(w.get(1)) and number(w.get(10)) and w[1]*w[10] < 0:
            result.append({'name': row['name'], 'daily': w[1], 'long': w[10],
                           'reading': '当日净额为正，10日累计为负' if w[1] > 0 else '当日净额为负，10日累计为正'})
    return result


def component_comparisons(ctx):
    result = []
    # 同一明确声明资金组内，比较实际最强/最弱样本；不猜产业链环节。
    for group in (ctx.deep.get('capital_co_movement') or {}).get('groups', []):
        rows = group.get('contributions', [])
        valid = [r for r in rows if number(r.get('fund_flow_cny'))]
        if len(valid) < 2:
            continue
        low, high = min(valid, key=lambda r:r['fund_flow_cny']), max(valid, key=lambda r:r['fund_flow_cny'])
        result.append({'name': group['name'], 'low': low, 'high': high, 'complete': group.get('contributions_complete', False),
                       'positive': sum(r['fund_flow_cny'] > 0 for r in valid), 'negative': sum(r['fund_flow_cny'] < 0 for r in valid), 'count': len(valid)})
    return result


def industry_sample_pairs(ctx):
    groups = {}
    for row in ctx.extra.get('stock_inflow', []) + ctx.extra.get('stock_outflow', []):
        if row.get('f100') and row.get('f12') and number(row.get('f62')):
            groups.setdefault(row['f100'], {})[row['f12']] = row
    pairs = []
    for label, members in groups.items():
        rows = list(members.values())
        high, low = max(rows, key=lambda r:r['f62']), min(rows, key=lambda r:r['f62'])
        if high['f62'] > 0 > low['f62']:
            pairs.append({'industry': label, 'high': high, 'low': low, 'sample_size': len(rows)})
    return sorted(pairs, key=lambda r: r['high']['f62']-r['low']['f62'], reverse=True)[:4]
