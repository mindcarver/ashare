#!/usr/bin/env python3
"""读者版：复用主输入的校验与派生，只负责证据选择和可读呈现。"""
import argparse
import base64
import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import load_input, validate_input
from derive import derive, load_history_entries, resolve_verification_points
from deep_analysis import derive_deep_analysis
from deep_render import markdown_security, markdown_liquidity, markdown_cycle, markdown_catalysts, markdown_lhb
from formatting import fmt_flow_cny, fmt_signed_pct, fmt_level, humanize_condition_value
from public_language import assert_public_language
from schema import ReviewError, parse_date, DEEP_COMPONENTS, SENTIMENT_STATE_LABELS, PUBLIC_METRIC_LABELS, OPERATOR_SYMBOLS, SCOPE_LABELS
from reader_evidence import number, checked_extra, stock_observations, check_breadth, legacy_breadth
from reader_depth import previous_pool_analysis, seal_quality, window_comparisons, component_comparisons, industry_sample_pairs

LABELS = {'security_details': '个股与多周期资金', 'liquidity_regime': '量价条件',
          'sentiment_cycle': '情绪周期', 'capital_co_movement': '资金共现与集中度',
          'catalyst_chains': '事件与传导假设', 'lhb_structure': '龙虎榜结构'}
READER_FORBIDDEN = ('交汇', '六轴', '象限', '审计', '验证链', '催化链', '未启用', '契约', 'schema')


def assert_reader_language(text):
    hits = [word for word in READER_FORBIDDEN if word in text]
    if hits:
        raise ReviewError('读者版不允许内部术语：' + '、'.join(hits))
    if re.search(r'https?://|file://|/Users/|/home/|push2|clist|ulist|东财|东方财富|同花顺|开盘啦|连接器|API接口|f(?:124|62|10)\b', text, re.I):
        raise ReviewError('读者版包含采集渠道或内部路径')
    if any(word in text for word in ('跌幅由浮筹决定', '第一波卖的是浮筹', '第二波才轮到机构', '单日被抽')):
        raise ReviewError('读者版含未经支持的因果或资金量措辞')


def cell(value):
    return escape(str(value), quote=False).replace('|', '／').replace('\n', ' ')


def table(headers, rows):
    rows = list(rows)
    if not rows:
        return ['证据不足，暂不列明细。', '']
    return ['| ' + ' | '.join(map(cell, headers)) + ' |', '|' + '|'.join(['---'] * len(headers)) + '|'] + [
        '| ' + ' | '.join(map(cell, row)) + ' |' for row in rows] + ['']


def metric(section, key):
    return (section.get('metrics', {}).get(key) or {}).get('value')


class Ctx:
    def __init__(self, args):
        self.market, self.input_sha = load_input(Path(args.input))
        self.md = self.market['market_date']
        if args.date != self.md:
            raise ReviewError('--date 与 market_date 不一致')
        self.sections = validate_input(self.market, parse_date(self.market['as_of'], 'as_of'))
        self.derived, self.signals = derive(self.sections)
        self.deep = derive_deep_analysis(self.market, self.sections, self.derived) or {}
        self.prev_md = self.sections['prev_pool_performance'].get('previous_market_date', '未确认')
        self.observations = stock_observations(self.sections, self.deep)
        raw = json.loads(Path(args.extra).read_text()) if args.extra else {}
        self.extra_metadata = raw.get('evidence') or {}
        self.extra, self.exclusions = checked_extra(raw, self.market, self.observations)
        if args.board_hist:
            self.exclusions.append({'component': 'board_history', 'reason': '旧独立文件未声明证据元数据，请纳入补充证据包'})
        self.breadth = None
        self.breadth_conflict = False
        try:
            rows = self.extra.get('breadth_rows') or legacy_breadth(args.workdir, self.market)
            if rows:
                self.breadth = check_breadth(rows, self.sections['breadth'])
        except ReviewError as exc:
            self.exclusions.append({'component': 'breadth_rows', 'reason': str(exc)})
            self.breadth_conflict = True
        self.klines = self.extra.get('index_klines', {})
        self.zt = self.extra.get('zt_pool', [])
        self.zt_available = 'zt_pool' in self.extra
        self.zt_prev = self.extra.get('previous_zt_pool', [])
        self.windows = self.extra.get('stock_windows', {})
        self.board_hist = self.extra.get('board_history', {})
        self._check_pools()
        histories = load_history_entries(Path(args.history_dir)) if getattr(args, 'history_dir', None) else []
        self.resolved = resolve_verification_points(histories, self.market, self.sections, self.derived)
        multi = {r['id'] for r in (self.derived.get('mainline_matrix') or {}).get('themes', []) if len(r['boards']) > 1 and not r.get('representative_board_id')}
        for item in self.resolved:
            condition, subject = item['condition'], item['subject']
            if (item['due_date'] != self.md
                    or (self.breadth_conflict and condition['metric'] == 'advancer_share_pct')
                    or (subject['scope'] == 'theme' and subject['id'] in multi and condition['metric'] == 'board_fund_flow_cny')):
                item.update(status='unknown', observed_value=None)

    def _check_pools(self):
        sent = self.sections['short_term_sentiment']
        up = metric(self.sections['breadth'], 'limit_up')
        failed, attempts = metric(sent, 'open_board_failed'), metric(sent, 'limit_attempts')
        if all(number(v) for v in (up, failed, attempts)) and up + failed != attempts:
            raise ReviewError('涨停+炸板与封板尝试分母不一致，不能发布封板率')
        if self.zt_available:
            count = metric(self.sections['breadth'], 'limit_up')
            highest = metric(self.sections['short_term_sentiment'], 'highest_streak')
            if count != len(self.zt) or highest != max((row['lbc'] for row in self.zt), default=0):
                raise ReviewError('补充涨停池与主输入家数或高度不一致')
            codes = {row['c'] for row in self.zt}
            for theme in self.sections['mainline_matrix'].get('themes', []):
                if not set(theme.get('limit_up_codes', [])) <= codes:
                    raise ReviewError('主题涨停成员不在当日涨停池')
        if self.zt_available and self.zt_prev:
            actual = len({row['c'] for row in self.zt} & {row['c'] for row in self.zt_prev})
            prev = self.derived.get('prev_pool_performance') or {}
            if prev.get('promotion_count') != actual or prev.get('pool_size') != len(self.zt_prev):
                raise ReviewError('相邻涨停池与晋级率证据不一致')

    def kline(self, key, date=None):
        return next((row for row in self.klines.get(key, []) if row['date'] == (date or self.md)), {})

    def sector_flows(self):
        return [{'id': row['id'], 'name': row['name'], 'flow': row['fund_flow']['value'],
                 'chg': row['change_pct']['value']} for row in self.sections['sectors'].get('items', [])
                if number((row.get('fund_flow') or {}).get('value'))]


def lead(ctx):
    sentiment = ctx.derived.get('short_term_sentiment') or {}
    state = SENTIMENT_STATE_LABELS.get(sentiment.get('state'), '证据不足，暂不定性')
    if sentiment.get('state') in (None, 'unknown'):
        state = '统计覆盖尚未完整确认，暂不定性'
    b = ctx.sections['breadth']
    prev = ctx.sections['short_term_sentiment'].get('previous_metrics') or {}
    up = metric(b, 'limit_up')
    old = (prev.get('limit_up') or {}).get('value')
    trend = f"涨停 {fmt_level(old, 'count')} → {fmt_level(up, 'count')}" if old is not None else f"涨停 {fmt_level(up, 'count')}"
    promotion = (ctx.derived.get('prev_pool_performance') or {}).get('promotion_rate_pct')
    rate = f'{promotion:.2f}%' if number(promotion) else '未知'
    lines = ['## 一句话', '', f"**盘面变化：{trend}，晋级率 {rate}。**", '', f"短线状态：{state}。", '']
    threshold = (ctx.derived.get('prev_pool_performance') or {}).get('health_threshold_pct')
    if number(promotion) and number(threshold):
        lines += [f"昨日涨停池的再涨停比例{'低于' if promotion < threshold else '达到'}已声明的{threshold:g}%观察线。" + ('涨停家数减少，接续比例也未达观察线，短线扩散与接续需要分开核验。' if number(old) and number(up) and up < old and promotion < threshold else ''), '']
    if ctx.breadth_conflict:
        lines += ['宽度原始样本与声明股票池存在冲突；上涨参与度及依赖它的量价判断暂不采用。']
    flows = ctx.sector_flows()
    neg = sorted((r for r in flows if r['flow'] < 0), key=lambda r: r['flow'])[:2]
    pos = sorted((r for r in flows if r['flow'] > 0), key=lambda r: -r['flow'])[:3]
    if neg or pos:
        lines.append('当日板块净额：' + '；'.join(f"{r['name']} {fmt_flow_cny(r['flow'])}" for r in neg + pos) + '。同日流出与流入并存，不能据此确认同一笔资金迁移。')
    return lines + ['']


def depth(ctx, key, renderer):
    comp = ctx.deep.get(key)
    if not comp or comp.get('availability') == 'unknown':
        return [f"### {LABELS[key]}", '', '证据不足，无法判断；缺失值未用零代替。', '']
    if key == 'liquidity_regime' and ctx.breadth_conflict:
        # 宽度冲突只使相关观察降级，不影响已校验指数量价。
        import copy
        comp = copy.deepcopy(comp)
        for check in comp.get('market_checks', []):
            if check['code'] == 'advancer_share_min_pct':
                check.update(observed=None, status='unknown')
        checks = [c for b in comp.get('benchmarks', []) for c in b['checks']] + comp.get('market_checks', [])
        comp['passed_count'] = sum(c['status'] == 'passed' for c in checks)
        comp['evaluated_count'] = sum(c['status'] != 'unknown' for c in checks)
        comp['result'] = 'unknown'
    return renderer(comp)


def indices_section(ctx):
    lines = ['## 一、指数与量能', '']
    lines += table(['指数', '收盘', '涨跌'], ([row['name'], f"{row['close']['value']:,.2f}",
               fmt_signed_pct(row['change_pct']['value'])] for row in ctx.sections['indices'].get('items', [])))
    amount = ctx.derived.get('turnover_amount')
    delta = ctx.derived.get('turnover_vs_previous_pct')
    lines += [f"当日成交额 {fmt_level(amount, 'CNY')}，较前一交易日 {fmt_signed_pct(delta)}。", '']
    etfs = []
    etf_names = {'588000.SH': '科创50ETF', '512480.SH': '半导体ETF', '159995.SZ': '芯片ETF'}
    for code, series in ctx.extra.get('etf_klines', {}).items():
        if len(series) >= 6 and all(number(r.get('volume')) for r in series[-6:]):
            volumes = [r['volume'] for r in series]
            base = sum(volumes[-6:-1]) / 5
            ratio = volumes[-1] / base if base > 0 else None
            delta = (volumes[-1] / volumes[-2] - 1) * 100 if volumes[-2] > 0 else None
            etfs.append([etf_names.get(code, code), fmt_level(ratio, 'ratio'), fmt_signed_pct(delta)])
    if etfs:
        lines += ['### ETF量能', '', '量比为当日成交量除以前5个交易日均量；日环比另列。', ''] + table(['基金', '5日量比', '成交量日环比'], etfs)
    return lines + depth(ctx, 'liquidity_regime', markdown_liquidity)


def sentiment_section(ctx):
    b, s = ctx.sections['breadth'], ctx.sections['short_term_sentiment']
    previous = s.get('previous_metrics') or {}
    lines = ['## 二、情绪与赚钱效应', '']
    rows = []
    for name, key, section in [('涨停家数', 'limit_up', b), ('跌停家数', 'limit_down', b),
                                ('炸板家数', 'open_board_failed', s), ('最高连板', 'highest_streak', s)]:
        now, old = metric(section, key), (previous.get(key) or {}).get('value')
        rows.append([name, fmt_level(old, 'count'), fmt_level(now, 'count'), fmt_level(now-old if now is not None and old is not None else None, 'count')])
    rate = (ctx.derived.get('short_term_sentiment') or {}).get('open_board_rate_pct')
    if rate is not None:
        rows.append(['封板率', '—', f'{100-rate:.2f}%', '涨停÷封板尝试；与炸板率互补'])
    lines += table(['指标', '前值', '当日', '变化或口径'], rows)
    if not ctx.breadth_conflict:
        lines += [f"上涨 {fmt_level(metric(b, 'advancers'), 'count')}、下跌 {fmt_level(metric(b, 'decliners'), 'count')}、平盘 {fmt_level(metric(b, 'unchanged'), 'count')}；上涨占比 {fmt_level(ctx.derived.get('advancer_share_pct'), 'percent')}。", '']
    if ctx.breadth:
        n = ctx.breadth['counts']
        lines += [f"同一股票池中，跌幅≥9%为 {n[0]} 只、跌幅≥5%为 {n[0]+n[1]} 只、−5%＜涨跌幅＜0%为 {n[2]:,} 只。", '']
    tiers = (ctx.derived.get('streak_distribution') or {}).get('tiers', [])
    lines += ['### 连板梯队', ''] + table(['板数', '家数'], ([t['streak'], t['count']] for t in tiers))
    p = ctx.derived.get('prev_pool_performance') or {}
    lines += ['### 昨日涨停池的延续性', '',
              f"前池 {fmt_level(p.get('pool_size'), 'count')} 家，再涨停 {fmt_level(p.get('promotion_count'), 'count')} 家，晋级率 {fmt_level(p.get('promotion_rate_pct'), 'percent')}。",
              f"平均涨跌 {fmt_signed_pct(p.get('avg_change_pct'))}；中位涨跌 {fmt_signed_pct(p.get('median_change_pct'))}。", '']
    points = (ctx.deep.get('sentiment_cycle') or {}).get('points', [])
    if points:
        lines += [f"情绪历史仅覆盖实际提供的 {len(points)} 个交易日（{points[0]['market_date']} 至 {points[-1]['market_date']}）；不足20/60日不推断完整周期或长期分位。", '']
    return lines + depth(ctx, 'sentiment_cycle', markdown_cycle)


def volume_scan_section(ctx):
    scan = ctx.extra.get('volume_scan') or {}
    if not scan:
        return ['### 活跃样本量比', '', '未获得日期与窗口均可确认的活跃样本量比，本节不作判断。', '']
    rows = [r for r in scan.values() if number(r.get('f10')) and r['f10'] >= 1.3 and number(r.get('f3'))]
    lines = ['### 活跃样本量比', '', f"活跃样本 {len(scan)} 只；按声明的5日窗口，量比≥1.3倍且涨跌可得 {len(rows)} 只。样本不代表全市场，放量不等于资金净流入或出货。", '']
    for title, selected in [('放量上涨', [r for r in rows if r['f3'] > 0]), ('放量下跌', [r for r in rows if r['f3'] < 0]), ('放量平盘', [r for r in rows if r['f3'] == 0])]:
        if selected:
            lines += [f'**{title}**', ''] + table(['个股', '量比', '涨跌'], ([r['f14'], f"{r['f10']:.2f}", fmt_signed_pct(r['f3'])] for r in sorted(selected, key=lambda r: -r['f10'])[:6]))
    return lines


def flow_changes(ctx):
    rows = []
    for board_id, info in ctx.board_hist.get('boards', {}).items():
        series = {}
        for raw in info.get('rows', []):
            date, value = raw.split(',')
            if date <= ctx.md:
                series[date] = float(value)
        today, prior = series.get(ctx.md), series.get(ctx.prev_md)
        if today is not None and prior is not None:
            rows.append({'id': board_id, 'name': info['name'], 'prior': prior, 'today': today, 'change': today-prior})
    return sorted(rows, key=lambda r: r['change'])


def mainline_section(ctx):
    lines = ['## 三、主线与资金结构', '']
    matrix = ctx.derived.get('mainline_matrix')
    if matrix:
        rules = matrix['quadrant_rules']
        lines += [f"判定采用输入声明的门槛：涨停家数≥{rules['limit_up_threshold']}，板块净额＞{fmt_flow_cny(rules['capital_threshold_cny'])}。仅描述主题结构，不代表入场条件。", '']
        names = {'dual_confirmed': '情绪与资金同向', 'capital_led': '资金先行', 'sentiment_only': '涨停活跃、资金未达标', 'sentiment_bleeding': '涨停活跃但资金流出', 'bleeding': '未达双重门槛', 'unknown': '证据不足'}
        rows = []
        for r in matrix['themes']:
            multiple = len(r['boards']) > 1 and not r.get('representative_board_id')
            rows.append([r['name'], fmt_level(r['limit_up_count'], 'count'),
                         '未确认可加总' if multiple else fmt_flow_cny(r['board_fund_flow_cny']),
                         '多板块需先去重' if multiple else names[r['quadrant']]])
        lines += table(['主题', '涨停家数', '声明板块净额', '结构'], rows)
        lines += ['主题成员由输入显式声明，不按名称相似推断归属；采用代表板块时只引用该板块净额，不代表主题全部成分的去重合计。', '']
    else:
        lines += ['主题成员或判定规则不足，无法判断是否存在双确认方向。', '']
    flows = ctx.sector_flows()
    for title, rows in [('当日净流出', sorted((r for r in flows if r['flow'] < 0), key=lambda r: r['flow'])[:10]), ('当日净流入', sorted((r for r in flows if r['flow'] > 0), key=lambda r: -r['flow'])[:10])]:
        if rows:
            lines += [f'### {title}', '', '逐项展示已声明板块口径；存在父子层级的项目不可相加。', ''] + table(['板块', '当日净额', '涨跌'], ([r['name'], fmt_flow_cny(r['flow']), fmt_signed_pct(r['chg'])] for r in rows))
    swing = flow_changes(ctx)
    if swing:
        lines += ['### 净额较前日变化', '', '变化额＝今日净额−昨日净额；改善可以仍是净流出，减少也不等于当天流出。', ''] + table(['板块', '昨日净额', '今日净额', '净额变化'], ([r['name'], fmt_flow_cny(r['prior']), fmt_flow_cny(r['today']), fmt_flow_cny(r['change'])] for r in swing))
    concepts = (ctx.derived.get('concept_flows') or {}).get('items', [])
    for title, rows in [('概念层净流入', sorted((r for r in concepts if number(r['fund_flow_cny']) and r['fund_flow_cny'] > 0), key=lambda r: -r['fund_flow_cny'])[:10]), ('概念层净流出', sorted((r for r in concepts if number(r['fund_flow_cny']) and r['fund_flow_cny'] < 0), key=lambda r: r['fund_flow_cny'])[:10])]:
        if rows:
            lines += [f'### {title}', '', '概念与行业分开观察，重叠成分不重复相加。', ''] + table(['概念', '当日净额', '涨跌'], ([r['name'], fmt_flow_cny(r['fund_flow_cny']), fmt_signed_pct(r['change_pct'])] for r in rows))
    return lines + capital_section(ctx)


def capital_section(ctx):
    comp = ctx.deep.get('capital_co_movement') or {}
    lines = ['### 资金共现与集中度', '', '同日流出、流入只提供共现证据；未追踪到同一笔资金。', '']
    if comp.get('availability', 'unknown') == 'unknown':
        return lines + ['证据不足，无法判断集中度。', '']
    lines += table(['资金组', '净额', '覆盖', '首位正流入占比', '绝对流量集中度'], ([g['name'], fmt_flow_cny(g['total_fund_flow_cny']), '全成分' if g['contributions_complete'] else f"样本 {fmt_level(g.get('sample_coverage_pct'), 'percent')}", fmt_level(g['top1_positive_share_pct'], 'percent'), fmt_level(g['absolute_hhi'], 'ratio')] for g in comp['groups']))
    lines += ['首位占比以正流入之和为分母；绝对流量集中度为个股绝对流量占比平方和，越高越集中。样本指标只解释其覆盖范围。', '']
    labels = {g['id']: g['name'] for g in comp['groups']}
    for rel in comp.get('relations', []):
        lines += [f"- 待验证假设：{labels.get(rel['from_group_id'], '流出组')}与{labels.get(rel['to_group_id'], '流入组')}：{rel['hypothesis']}。反方证据：{'；'.join(rel['counter_evidence'])}。"]
    return lines + ['']


def lhb_aggregate(rows):
    # 保留同股最大绝对净额行，不把多个上榜原因机械相加；仅代表所选榜单。
    agg = {}
    for row in rows:
        net = row.get('BILLBOARD_NET_AMT')
        if not number(net):
            continue
        code = row['SECURITY_CODE']
        if code not in agg or abs(net) > abs(agg[code]['net']):
            agg[code] = {'code': code, 'name': row['SECURITY_NAME_ABBR'], 'chg': row.get('CHANGE_RATE'), 'net': net, 'reason': row.get('EXPLANATION', '')}
    return sorted(agg.values(), key=lambda r: r['net'])


def stocks_section(ctx):
    lines = ['## 四、个股焦点', '', '不构成个股推荐 / 只作结构归因。', '']
    lines += depth(ctx, 'security_details', markdown_security)
    for group in ctx.derived.get('sector_leaders') or []:
        lines += [f"### {group['name']}：板块内个股", ''] + table(['个股', '涨跌', '当日主力净额'], ([r['name'], fmt_signed_pct(r['change_pct']), fmt_flow_cny(r['fund_flow_cny'])] for r in group['leaders']))
    for title, key in [('补充个股净流入样本', 'stock_inflow'), ('补充个股净流出样本', 'stock_outflow')]:
        rows = ctx.extra.get(key) or []
        if rows:
            lines += [f'### {title}', ''] + table(['个股', '所属行业', '涨跌', '净额'], ([r['f14'], r.get('f100') or '未分类', fmt_signed_pct(r.get('f3')), fmt_flow_cny(r.get('f62'))] for r in rows[:8]))
    for insight in ctx.extra.get('insights', []):
        lines += [f"- 待验证假设：{insight['text']}", f"  反证：{'；'.join(insight['counter_evidence'])}；后续核验：{insight['verification']}。"]
        lines += ['  对照事实：' + '；'.join(f"{ctx.observations[c]['name']} {fmt_signed_pct(ctx.observations[c]['change'])} / {fmt_flow_cny(ctx.observations[c]['flow'])}" for c in insight['anchors'])]
    rows = lhb_aggregate(ctx.extra.get('lhb_rows', []))
    if rows:
        lines += ['### 龙虎榜补充披露', '', '同股多榜单选绝对净额最大的一行，不跨日或跨榜相加。榜单席位不等同全部游资，净卖出不证明出货意图。', ''] + table(['个股', '涨跌', '所选榜单净额', '原因'], ([r['name'], fmt_signed_pct(r['chg']), fmt_flow_cny(r['net']), r['reason']] for r in rows[:5] + [r for r in rows[-5:] if r not in rows[:5]]))
    lines += depth(ctx, 'lhb_structure', markdown_lhb)
    return lines + ['主力净额是模型推导值；龙虎榜是特定披露范围。方向不同首先说明口径不同，不能自动认定资金异常。', '']


def news_section(ctx):
    return ['## 五、消息与传导', ''] + depth(ctx, 'catalyst_chains', markdown_catalysts)


def conclusion_section(ctx):
    lines = ['## 后续核验', '']
    if ctx.exclusions:
        lines += [f"补充证据有 {len(ctx.exclusions)} 项未通过日期、范围或一致性检查，已排除；对应结论保持未知。", '']
    lines += ['### 上期验证结果', '']
    if not ctx.resolved:
        lines += ['未提供可结算的历史验证记录，结果未知。', '']
    else:
        for item in ctx.resolved:
            lines += [f"- {item.get('title', '已到期条件')}：{ {'passed':'成立','failed':'未成立','unknown':'未知'}.get(item.get('status'), '未知')}。"]
    lines += ['### 观察条件与当前结算状态', '']
    for point in ctx.market.get('verification_points', []):
        condition = point.get('condition') or {}
        detail = ''
        if condition:
            detail = f"；{PUBLIC_METRIC_LABELS.get(condition['metric'], condition['metric'])} {OPERATOR_SYMBOLS.get(condition['operator'], condition['operator'])} {humanize_condition_value(condition['value'], condition['unit'])}"
        subject = point.get('subject') or {}
        due = point.get('event_date', '')
        status = '已到观察日，未引入该日同口径证据，尚未结算' if due and due <= ctx.market['as_of'] else '尚未到观察日'
        lines += [f"- {point['title']}（{due}，{subject.get('label') or SCOPE_LABELS.get(subject.get('scope'), '未明确对象')}）{detail}。{status}。"]
    return lines + ['', '口径：主力净额为模型推导，不能识别账户身份或机构意图；缺失值不填零。本文只作盘面结构归因，不构成投资建议。', '']


def theme_digest(ctx):
    lines = ['## 主线逐条看', '']
    matrix = ctx.derived.get('mainline_matrix') or {}
    boards = {r['id']: r for r in ctx.sections['sectors'].get('items', [])}
    groups = (ctx.deep.get('capital_co_movement') or {}).get('groups', [])
    events = (ctx.deep.get('catalyst_chains') or {}).get('items', [])
    changes = {r['id']: r for r in flow_changes(ctx)}
    originals = {r['id']: r for r in ctx.sections['mainline_matrix'].get('themes', [])}
    names = {'dual_confirmed': '涨停与代表板块资金同向', 'capital_led': '资金净流入，涨停数量未达声明门槛', 'sentiment_only': '涨停活跃，板块资金未达声明门槛', 'sentiment_bleeding': '涨停活跃，但板块净额为负', 'bleeding': '尚未同时满足涨停与资金门槛', 'unknown': '证据不足'}
    if not matrix:
        return lines + ['主题成员或判定依据不足，暂不能判断主线。', '']
    rules = matrix['quadrant_rules']
    lines += [f"统一条件：涨停家数≥{rules['limit_up_threshold']}，引用板块净额＞{fmt_flow_cny(rules['capital_threshold_cny'])}。代表板块是观察参照，不能当作主题全部成分的合计。", '']
    order = {'dual_confirmed': 0, 'capital_led': 1, 'sentiment_only': 2, 'sentiment_bleeding': 3, 'bleeding': 4, 'unknown': 5}
    for theme in sorted(matrix['themes'], key=lambda r: (order.get(r['quadrant'], 5), -r['limit_up_count'])):
        ref = theme.get('representative_board_id') or (theme['boards'][0] if len(theme['boards']) == 1 else None)
        lines += [f"### {theme['name']}", '', f"**当前结构：{names[theme['quadrant']] if ref else '多个板块重叠尚未核清，暂不下整体结论'}。**"]
        lines += [f"涨停 {fmt_level(theme['limit_up_count'], 'count')} 家。" + (f"资金参照为{boards[ref]['name']}：{fmt_flow_cny(theme['board_fund_flow_cny'])}，板块涨跌{fmt_signed_pct(theme['board_change_pct_equal_weight'])}。" if ref else '资金分别列示于附录，未加总。')]
        scope = originals.get(theme['id'], {}).get('public_scope')
        if scope:
            lines += [scope]
        codes = originals.get(theme['id'], {}).get('limit_up_codes', [])
        lookup = {r['c']:r['n'] for r in ctx.zt}
        if codes and all(code in lookup for code in codes):
            lines += ['涨停成员：' + '、'.join(lookup[code] for code in codes) + '。']
        if ref in changes:
            change = changes[ref]
            lines += [f"**与前日相比：**净额 {fmt_flow_cny(change['prior'])} → {fmt_flow_cny(change['today'])}，变化 {fmt_flow_cny(change['change'])}。" + ('净额由负转正。' if change['prior'] < 0 < change['today'] else '净额由正转负。' if change['prior'] > 0 > change['today'] else '变化额与当日净额须分开看。')]
        matched = [g for g in groups if set(theme['boards']) & set(g['board_ids'])]
        for group in matched:
            contributions = group.get('contributions', [])
            positive = [r for r in contributions if r['fund_flow_cny'] > 0]
            negative = [r for r in contributions if r['fund_flow_cny'] < 0]
            if positive:
                top = max(positive, key=lambda r:r['fund_flow_cny'])
                coverage = '全成分' if group['contributions_complete'] else '已覆盖样本'
                share = group.get('top1_positive_share_pct')
                share_text = f'{share:.2f}%' if number(share) else '未知'
                lines += [f"**内部是否一致：**{group['name']}的{coverage}{len(contributions)}只中，净流入{len(positive)}只、净流出{len(negative)}只、净额为零{len(contributions)-len(positive)-len(negative)}只；{top['name']}净额{fmt_flow_cny(top['fund_flow_cny'])}，占正流入合计{share_text}。该占比的分母不含净流出，仅解释这个成分组。"]
        linked = [event for event in events if theme['id'] in event['affected_theme_ids']]
        if linked:
            for event in linked:
                lines += [f"**已知事件：**{event['fact']}（发布日 {event['published_at']}）。",
                          f"**传导假设：**{event.get('transmission') or event['mechanism_hypothesis']}。",
                          '**反方证据：**' + '；'.join(event['counter_evidence']) + '。']
        else:
            lines += ['**解释边界：**缺少已核实且能对应本主题的产业事件，当前只能解释交易结构，不能确认上涨或下跌的原因。']
        if not matched:
            lines += ['**内部覆盖：**尚无同范围的完整成分资金分解，不能把板块净额理解为普遍流入或普遍流出。']
        targets = [p for p in ctx.market.get('verification_points', []) if (p.get('subject') or {}).get('id') == theme['id']]
        lines += ['**后续核验：**' + ('；'.join(p['title'] for p in targets) if targets else '对照同一成员集合的涨停延续性、净额方向和头部集中度，当前未设可自动结算的主题条件') + '。', '']
    return [part for line in lines for part in (line, '')]


def continuity_reading(ctx):
    lines = ['### 昨日首板与连板，今天分别怎样', '']
    data = previous_pool_analysis(ctx)
    if not data['groups']:
        return lines + ['逐股的前池身份、当日行情或相邻池证据不足，暂不作首板与连板比较。', '']
    rows = []
    for g in data['groups']:
        flow = fmt_flow_cny(g['flow_total']) if g['flow_total'] is not None else f"样本{fmt_flow_cny(g['flow_sample'])}，整体未知"
        rows.append([g['name'], g['count'], f"{g['price_covered']}/{g['count']}", fmt_signed_pct(g['average']), fmt_signed_pct(g['median']), f"{g['flow_covered']}/{g['count']}", flow, g['promoted'], g['broken']])
    lines += table(['前池分组', '只数', '行情覆盖', '均涨', '中位', '资金覆盖', '当日净额', '再涨停', '未再涨停'], rows)
    lines += ['再涨停按两日涨停池代码交集统计；20%涨跌幅股票上涨超过10%不自动视为涨停。行情或资金只覆盖部分成员时，均值、中位和资金都只解释该样本。', '']
    if any(meta.get('retrieval_mode') == 'historical_archive' for meta in ctx.extra_metadata.values()):
        lines += ['资金补充来自历史存档与同日报价的交叉匹配，原始采集时刻未完整保留；该匹配不能证明每项资金值的更新时间。', '']
    broken = [r for r in data['rows'] if r['prior_streak'] > 1 and not r['promoted']]
    if broken:
        lines += [f"昨日连板股中，{len(broken)}只未再涨停；其中{sum(r['change'] is not None and r['change'] < 0 for r in broken)}只收跌，{sum(r['change'] is not None and r['change'] > 0 for r in broken)}只仍上涨。断板与收跌是两个不同结果。", '']
        lines += table(['未再涨停个股', '昨日板数', '当日涨跌', '当日净额'], ([r['name'], r['prior_streak'], fmt_signed_pct(r['change']), fmt_flow_cny(r['flow'])] for r in broken))
    return lines


def structure_reading(ctx):
    lines = ['### 高标与封板质量', '']
    quality = seal_quality(ctx.zt)
    prior = seal_quality(ctx.zt_prev)
    if quality['count']:
        if ctx.extra_metadata.get('zt_pool', {}).get('unresolved_conflict'):
            lines += ['封单存在后续历史查询与原存档不一致的情况，原因尚未确认。本版统一使用原存档整批；封单绝对值和跨日比值保留这一限制，不据此单独认定强弱。', '']
        lines += [f"当日涨停池{quality['count']}只，封单/成交额可计算{quality['ratio_covered']}只，中位比值{fmt_level(quality['ratio_median'], 'ratio')}；前池中位{fmt_level(prior['ratio_median'], 'ratio')}（覆盖{prior['ratio_covered']}/{prior['count']}）。不同日池成员有变化，比值仅作池结构对照。",
                  f"当前封住的股票中，盘中曾开板{quality['ever_broken']}/{quality['break_covered']}只；它们不属于收盘仍未封住的炸板池，两者不能相加。", '']
    for item in (ctx.deep.get('security_details') or {}).get('items', []):
        seal = item.get('seal_structure') or {}
        if item.get('streak') and seal:
            lines += [f"- {item['name']}：{item['streak']}板，开板{fmt_level(seal.get('break_count'), 'count')}次，封单{fmt_flow_cny(seal.get('sealed_order_amount_cny'))}。封单是该快照的未成交委托额，不等同已成交买入或资金承诺。"]
    lines += ['', '### 多周期资金：当日与累计是否一致', '']
    differences = window_comparisons(ctx)
    if differences:
        lines += table(['个股', '当日净额', '10日累计', '观察'], ([r['name'], fmt_flow_cny(r['daily']), fmt_flow_cny(r['long']), r['reading']] for r in differences))
    else:
        lines += ['已覆盖样本未发现当日与10日累计异号，或对应窗口不足；不代表趋势已经一致。', '']
    lines += ['1/3/5/10日为重叠累计窗口，不能相加，也不能用金额大小直接判断资金加速。完整窗口表见附录。', '', '### 同组个股对照', '']
    pairs = component_comparisons(ctx)
    lines += table(['资金组', '最高净额个股', '净额', '最低净额个股', '净额', '范围'], ([r['name'], r['high']['name'], fmt_flow_cny(r['high']['fund_flow_cny']), r['low']['name'], fmt_flow_cny(r['low']['fund_flow_cny']), '全成分' if r['complete'] else '样本'] for r in pairs))
    lines += ['以上为相同成员组内的资金分化。产业链环节需要另有业务映射证据，不能从证券名称、两只股票或净额大小推断机构意图。', '']
    pairs = industry_sample_pairs(ctx)
    if pairs:
        lines += ['### 同行业榜单样本中的两端', '']
        lines += table(['行业', '流入侧样本', '涨跌 / 净额', '流出侧样本', '涨跌 / 净额', '覆盖只数'],
                       ([r['industry'], r['high']['f14'], f"{fmt_signed_pct(r['high'].get('f3'))} / {fmt_flow_cny(r['high']['f62'])}",
                         r['low']['f14'], f"{fmt_signed_pct(r['low'].get('f3'))} / {fmt_flow_cny(r['low']['f62'])}", r['sample_size']] for r in pairs))
        lines += ['这是已覆盖资金榜样本中的最高与最低净额个股，未覆盖全行业，也不代表上游与下游。涨跌、换手和净额之间的同日关系不证明因果。', '']
    opposite = []
    for row in lhb_aggregate(ctx.extra.get('lhb_rows', [])):
        model = ctx.windows.get(row['code'], {}).get('f62', ctx.observations.get(row['code'], {}).get('flow'))
        if number(model) and model * row['net'] < 0:
            opposite.append([row['name'], fmt_flow_cny(model), fmt_flow_cny(row['net'])])
    if opposite:
        lines += ['### 同股不同资金口径', ''] + table(['个股', '主力模型净额', '所选龙虎榜净额'], opposite[:6])
        lines += ['两列统计范围不同，异号不能证明出货、吸筹或数据异常。需分别跟踪同口径的后续数据，不能相减当作未披露资金。', '']
    return lines


def market_reading(ctx):
    lines = ['## 市场与延续性', '']
    volume = ctx.deep.get('liquidity_regime') or {}
    benchmarks = volume.get('benchmarks', [])
    if benchmarks:
        lower = [r['name'] for r in benchmarks if number(r.get('ma20_distance_pct')) and r['ma20_distance_pct'] < 0]
        shrinking = [r['name'] for r in benchmarks if number(r.get('volume_ratio_5d')) and r['volume_ratio_5d'] < 1]
        checks = [c for b in benchmarks for c in b.get('checks', [])]
        failed = sum(c['status'] == 'failed' for c in checks)
        lines += [f"已覆盖{len(benchmarks)}个基准，{len(lower)}个位于20日均线下方，{len(shrinking)}个成交量低于前5日均量。" + ('低于5日均量：'+'、'.join(shrinking)+'。' if shrinking else ''),
                  f"基准量价条件中有{failed}项未成立。" + ('这只能说明当日确认不足；是否构成反转失败，还需前期信号与后续同口径数据。' if failed else '已观察的成立条件不自动构成后续趋势预测。'), '']
    p = ctx.derived.get('prev_pool_performance') or {}
    if number(p.get('avg_change_pct')) and number(p.get('median_change_pct')):
        lines += [f"昨日涨停池当日均涨{fmt_signed_pct(p['avg_change_pct'])}、中位{fmt_signed_pct(p['median_change_pct'])}。" + ('均值为正而中位为负，说明均值不能代表多数成员的表现。' if p['avg_change_pct'] > 0 > p['median_change_pct'] else '需要结合分组和分布理解整体均值。'), '']
    return lines + continuity_reading(ctx) + structure_reading(ctx)


def render(ctx, charts=None):
    charts = charts or {}
    revised = ctx.market['as_of'] > ctx.md
    parts = [f'# A股收盘复盘 · {ctx.md}', '',
             f"{'历史修订版' if revised else '当日复盘'}：观察交易日 {ctx.md}；信息截止 {ctx.market['snapshot']['cutoff_at']}；对照交易日 {ctx.prev_md}。", '']
    if revised:
        parts += ['本版含后来补核的历史资料，不代表全部信息在观察日收盘时已知；已过观察日的条件另标结算状态。', '']
    parts += [line.replace('## 一句话', '## 今日判断') for line in lead(ctx)]
    parts += theme_digest(ctx) + market_reading(ctx)
    for key in ('cycle', 'breadth', 'ladder'):
        if key in charts:
            parts += [f'![市场结构](charts/{charts[key]})', '']
    parts += conclusion_section(ctx) + ['## 证据附录', '', '保留完整指标、条件、个股窗口与消息记录，供逐项核对。', '']
    if ctx.market['analysis_mode'] == 'deep':
        parts += ['深度覆盖：' + '；'.join(f"{LABELS[k]}：" + {'available':'可得','partial':'部分可得','unknown':'未知'}[(ctx.deep.get(k) or {}).get('availability','unknown')] for k in DEEP_COMPONENTS) + '。', '']
    for fn in (indices_section, sentiment_section, volume_scan_section, mainline_section, stocks_section, news_section):
        content = fn(ctx)
        if fn is indices_section:
            # 矩阵已包含逐基准事实，避免再复述同一张表六遍。
            marker = '逐基准解读（由上表当日数值直接归纳，不预测方向）：'
            if marker in content:
                content = content[:content.index(marker)]
        parts += content
        keys = ('redirect',) if fn is mainline_section else ()
        for key in keys:
            if key in charts:
                title = {'cycle':'情绪历史样本','breadth':'同池涨跌分布','ladder':'连板梯队','redirect':'板块净额较前日变化'}[key]
                parts += [f'![{title}](charts/{charts[key]})', '']
    result = '\n'.join(parts)
    assert_public_language(result)
    assert_reader_language(result)
    return result
def render_html(ctx, md_text: str) -> str:
    """读者版 HTML：同一份内容套技能共享品牌层外壳（无渠道信息、无脚本）。"""
    import markdown as _md

    body = _md.markdown(md_text, extensions=["tables"])
    body = re.sub(r'<h1>.*?</h1>\s*', '', body, count=1, flags=re.S)
    for title in ('今日判断', '主线逐条看', '市场与延续性', '后续核验', '证据附录'):
        body = body.replace(f'<h2>{title}</h2>', f'<h2 id="{title}">{title}</h2>')
    marker = '<h2 id="证据附录">证据附录</h2>'
    if marker in body:
        before, appendix = body.split(marker, 1)
        body = before + marker + '<details><summary>展开完整数据、条件和消息记录</summary>' + appendix + '</details>'
    # 全部选择器锚在 main 下：共享品牌层有意排在技能样式之后（见
    # ashare_shared._insert_before_head 的 v2 注释），裸元素选择器会被品牌层的
    # 基础复位（h1,h2,h3,p{margin:0}、table/th/td 复位）整体压掉；main 前缀
    # 以特异性取胜，注入顺序不再影响读者版排版。列对齐交给 markdown 表格的
    # 行内 style（---: 列），不写 nth-child 全表右对齐，避免长文本列被右对齐。
    page_local = """
:root{}
main{max-width:980px;margin:auto;padding:28px 20px 60px;line-height:1.75}
.reader-head{border-bottom:2px solid var(--rule,#111417);padding-bottom:14px;margin-bottom:8px}
.reader-head h1{font-family:var(--font-display,sans-serif);font-size:26px;letter-spacing:.5px;margin:6px 0 4px}
.reader-head .meta{font-family:var(--font-ui,sans-serif);font-size:12.5px;color:var(--ink-tertiary,#7d838a)}
body{background:var(--canvas,#e9e6e0);color:var(--ink,#111417);font-family:var(--font-body,serif)}
main h2{font-family:var(--font-display,sans-serif);font-size:19px;font-weight:700;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line,#c9c6c0)}
main h3,main h4{font-family:var(--font-display,sans-serif);font-size:15px;margin:18px 0 8px}
main p{margin:8px 0}
main img{max-width:100%;height:auto;display:block;margin:10px auto}
main table{display:block;overflow-x:auto;width:100%;border-collapse:collapse;margin:12px 0;font-family:var(--font-ui,sans-serif);font-size:13px;background:var(--paper,#fff)}
main th{font-family:var(--font-ui,sans-serif);font-size:12.5px;font-weight:600;letter-spacing:normal;text-transform:none;color:var(--ink,#111417);border-top:2px solid var(--rule,#111417);border-bottom:1px solid var(--rule,#111417);padding:7px 9px;text-align:left;line-height:1.5}
main td{border-bottom:1px solid var(--line,#c9c6c0);padding:6px 9px;text-align:left;line-height:1.6}
main tr:last-child td{border-bottom:2px solid var(--rule,#111417)}
main ul,main ol{padding-left:22px;margin:8px 0}
main li{margin:5px 0}
main strong{font-weight:700}
main hr{border:none;border-top:1px solid var(--line,#c9c6c0);margin:26px 0}
main blockquote{margin:10px 0;padding:8px 14px;border-left:3px solid var(--line,#c9c6c0);color:var(--ink-secondary,#4b5158);font-size:13.5px}
main nav{display:flex;flex-wrap:wrap;gap:8px 18px;padding:12px 0;border-bottom:1px solid var(--line,#c9c6c0);font-family:var(--font-ui,sans-serif);font-size:13px}
main nav a{color:inherit;text-decoration:underline;text-underline-offset:4px}
main summary{cursor:pointer;font-weight:700;padding:14px 0}
main :focus-visible{outline:2px solid #206048;outline-offset:4px}
@media(max-width:600px){main{padding:18px 14px 36px}.reader-head h1{font-size:23px}main h2{font-size:19px}main table{font-size:12px}main th,main td{min-width:70px}}
"""
    html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow">'
        f"<title>A股收盘复盘（读者版）· {ctx.md}</title><style>{page_local}</style></head>"
        "<body><main>"
        f'<header class="reader-head"><p class="eyebrow" style="font-family:var(--font-ui,sans-serif);'
        f'font-size:11px;letter-spacing:2px;color:var(--ink-tertiary,#7d838a);margin:0">A股 · 收盘复盘（读者版）</p>'
        f"<h1>{ctx.md} 盘面全景</h1>"
        f'<p class="meta">信息截止 {escape(getattr(ctx, "market", {}).get("snapshot", {}).get("cutoff_at", ctx.md))} · 对照日 {ctx.prev_md} · 盘面结构复盘，不构成投资建议</p>'
        "</header>"
        + '<nav aria-label="报告章节">' + ''.join(f'<a href="#{title}">{title}</a>' for title in ('今日判断', '主线逐条看', '市场与延续性', '后续核验', '证据附录')) + '</nav>'
        + body
        + "</main></body></html>"
    )
    import _paths  # noqa: F401
    from ashare_shared import inject_shared_css

    return inject_shared_css(html)



def render_widget(ctx):
    """与正文共用通过门禁的数据；仅显示可得表。"""
    datasets = {
        '涨停池': [{'名称': r['n'], '连板': r['lbc']} for r in ctx.zt],
        '个股资金': [{'名称': r['name'], '涨跌': r['change'], '当日净额': r['flow']} for r in ctx.observations.values()],
        '昨日池': [{'名称': r['n'], '昨日连板': r['lbc']} for r in ctx.zt_prev],
        '龙虎榜': [{'名称': r['name'], '净额': r['net']} for r in lhb_aggregate(ctx.extra.get('lhb_rows', []))],
        '板块净额变化': [{'板块': r['name'], '昨日净额': r['prior'], '今日净额': r['today'], '净额变化': r['change']} for r in flow_changes(ctx)]}
    payload = json.dumps(datasets, ensure_ascii=False).replace('<', '\\u003c')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>盘面数据</title><style>body{font-family:sans-serif;margin:24px}td,th{padding:8px;border-bottom:1px solid #ddd}button,input{padding:8px;margin:4px}th{cursor:pointer}table{border-collapse:collapse}#wrap{overflow:auto}</style>
<h1>盘面数据 · ''' + ctx.md + '''</h1><p>仅展示通过日期与一致性检查的证据。缺失保持未知。金额单位：元；主力净额为模型推导；不构成个股推荐 / 只作结构归因。</p>
<nav></nav><input placeholder="搜索名称" id="search"><div id="wrap"></div>
<script>const data=''' + payload + ''';let current=Object.keys(data)[0],key=null,ascending=true;
const nav=document.querySelector('nav');Object.keys(data).forEach(name=>{const b=document.createElement('button');b.textContent=name;b.onclick=()=>{current=name;key=null;draw()};nav.append(b)});
function draw(){const root=document.getElementById('wrap');root.replaceChildren();let rows=data[current].filter(r=>Object.values(r).join(' ').includes(document.getElementById('search').value));if(key)rows.sort((a,b)=>{const x=a[key],y=b[key];return(typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??''),'zh'))*(ascending?1:-1)});if(!rows.length){root.textContent='无可用记录';return}const table=document.createElement('table'),head=table.createTHead().insertRow(),cols=Object.keys(rows[0]);cols.forEach(k=>{const th=document.createElement('th');const button=document.createElement('button');button.textContent=k;button.setAttribute('aria-label','按'+k+'排序');button.onclick=()=>{ascending=key===k?!ascending:true;key=k;draw();document.querySelectorAll('th button')[cols.indexOf(k)].focus()};th.append(button);head.append(th)});const body=table.createTBody();rows.forEach(r=>{const tr=body.insertRow();cols.forEach(k=>tr.insertCell().textContent=r[k]??'未知')});root.append(table)}document.getElementById('search').oninput=draw;draw();</script></html>'''


def main():
    ap = argparse.ArgumentParser()
    for key in ('input', 'workdir', 'date', 'output'):
        ap.add_argument('--' + key, required=True)
    for key in ('extra', 'board-hist', 'html-out', 'widget-out', 'history-dir', 'validation-out'):
        ap.add_argument('--' + key)
    args = ap.parse_args()
    try:
        ctx = Ctx(args)
        # 先完成语义与语言检查，失败时不发布部分产物。
        render(ctx)
        from reader_charts import build_charts, chart_data
        charts = build_charts(ctx, Path(args.output).parent / 'charts', flow_changes(ctx))
        md = render(ctx, charts)
        html = render_html(ctx, md) if args.html_out else None
        if html:
            for filename in charts.values():
                data = (Path(args.output).parent / 'charts' / filename).read_bytes()
                html = html.replace(f'src="charts/{filename}"', f'src="data:image/png;base64,{base64.b64encode(data).decode()}"')
            assert_public_language(md, html)
        for path, content in ((args.output, md), (args.html_out, html), (args.widget_out, render_widget(ctx) if args.widget_out else None)):
            if path:
                dest = Path(path); dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(content, encoding='utf-8')
        evidence = {'market_date': ctx.md, 'input_sha256': ctx.input_sha, 'exclusions': ctx.exclusions,
                    'breadth_conflict': ctx.breadth_conflict, 'charts': chart_data(ctx, flow_changes(ctx)),
                    'deep_coverage': {k: (ctx.deep.get(k) or {}).get('availability', 'unknown') for k in DEEP_COMPONENTS}}
        evidence['previous_pool_analysis'] = previous_pool_analysis(ctx)
        evidence['seal_quality'] = {'today': seal_quality(ctx.zt), 'previous': seal_quality(ctx.zt_prev)}
        if args.validation_out:
            Path(args.validation_out).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': args.output, 'excluded_supplements': len(ctx.exclusions), 'breadth_conflict': ctx.breadth_conflict}, ensure_ascii=False))
        return 0
    except (ReviewError, OSError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
