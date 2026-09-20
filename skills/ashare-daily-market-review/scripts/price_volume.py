"""带日期日线的量价计算；成交量与成交额永不互代。"""
import math
from statistics import mean

from schema import ReviewError, parse_date


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def price_volume_metrics(rows, market_date):
    dated = {}
    for row in rows:
        day = parse_date(row.get('date'), 'daily_bars.date').isoformat()
        if day in dated:
            raise ReviewError('日线日期重复')
        dated[day] = row
    if market_date not in dated:
        raise ReviewError('日线缺少目标交易日')
    series = [dated[day] for day in sorted(dated) if day <= market_date]
    values = {}
    for field, prefix in (('volume', 'volume'), ('amount', 'amount')):
        samples = [row.get(field) for row in series]
        last6 = samples[-6:]
        valid6 = len(last6) == 6 and all(finite(v) and v >= 0 for v in last6)
        base = mean(last6[:-1]) if valid6 else 0
        values[prefix + '_ratio_5d'] = last6[-1] / base if base > 0 else None
        pair = samples[-2:]
        values[prefix + '_change_pct'] = (pair[-1] / pair[0] - 1) * 100 if len(pair) == 2 and all(finite(v) and v >= 0 for v in pair) and pair[0] > 0 else None
        history = samples[-120:]
        values[prefix + '_percentile_120d'] = sum(v <= history[-1] for v in history) / 120 * 100 if len(history) == 120 and all(finite(v) and v >= 0 for v in history) else None
    closes = [row.get('close') for row in series]
    for days in (20, 60):
        sample = closes[-days:]
        values[f'ma{days}_distance_pct'] = (sample[-1] / mean(sample) - 1) * 100 if len(sample) == days and all(finite(v) and v > 0 for v in sample) else None
    values['change_pct'] = (closes[-1] / closes[-2] - 1) * 100 if len(closes) > 1 and all(finite(v) and v > 0 for v in closes[-2:]) else None
    history = closes[-121:]
    returns = [(b/a-1)*100 for a, b in zip(history, history[1:])] if len(history) == 121 and all(finite(v) and v > 0 for v in history) else []
    values['return_percentile_120d'] = sum(v <= returns[-1] for v in returns) / 120 * 100 if returns else None
    volumes = [row.get('volume') for row in series]
    consecutive = 0
    if len(volumes) < 2 or not all(finite(v) and v >= 0 for v in volumes):
        consecutive = None
    else:
        for i in range(len(volumes)-1, 0, -1):
            if volumes[i] <= volumes[i-1]:
                break
            consecutive += 1
    values['consecutive_volume_days'] = consecutive
    return values


def validate_bar_metrics(item, market_date):
    if item.get('volume_basis', 'volume') != 'volume':
        raise ReviewError('volume_ratio_5d 必须使用成交量，成交额须单列')
    if 'daily_bars' not in item:
        return
    computed = price_volume_metrics(item['daily_bars'], market_date)
    for key, expected in computed.items():
        if key not in item:
            continue
        actual = item[key].get('value')
        if expected is None or not finite(actual) or not math.isclose(actual, expected, abs_tol=0.005, rel_tol=1e-5):
            raise ReviewError(f'{key} 与带日期日线重算不一致（成交量与成交额不能混用）')
