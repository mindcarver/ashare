"""只消费正文共用的派生数据，不重新取数或定义统计口径。"""


def chart_data(ctx, changes):
    result = {}
    points = (ctx.deep.get('sentiment_cycle') or {}).get('points', [])
    points = [p for p in points if p['market_date'] <= ctx.md and isinstance(p.get('limit_up'), (int, float))]
    if points:
        result['cycle'] = {'labels': [p['market_date'][5:] for p in points], 'values': [p['limit_up'] for p in points]}
    if ctx.breadth:
        result['breadth'] = {'labels': ctx.breadth['labels'], 'values': ctx.breadth['counts']}
    elif not ctx.breadth_conflict:
        metrics = ctx.sections['breadth'].get('metrics', {})
        vals = [(metrics.get(k) or {}).get('value') for k in ('decliners', 'unchanged', 'advancers')]
        if all(isinstance(v, (int, float)) for v in vals):
            result['breadth'] = {'labels': ['下跌', '平盘', '上涨'], 'values': vals}
    tiers = (ctx.derived.get('streak_distribution') or {}).get('tiers', [])
    if tiers:
        result['ladder'] = {'labels': [f"{r['streak']}板" for r in tiers], 'values': [r['count'] for r in tiers]}
    if changes:
        result['redirect'] = {'decrease': [r for r in changes if r['change'] < 0][:8],
                              'increase': sorted((r for r in changes if r['change'] > 0), key=lambda r: -r['change'])[:8]}
    return result


def build_charts(ctx, out_dir, changes):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams['font.family'] = [name for name in ('Hiragino Sans GB', 'Noto Sans CJK SC', 'DejaVu Sans') if name in available]
    plt.rcParams['axes.unicode_minus'] = False
    out_dir.mkdir(parents=True, exist_ok=True)
    names = {}
    titles = {'cycle': '涨停家数（实际历史样本）', 'breadth': '同池涨跌分布', 'ladder': '连板梯队'}
    for key, data in chart_data(ctx, changes).items():
        if key == 'redirect':
            panels = [(data['decrease'], '净额减少'), (data['increase'], '净额增加')]
            panels = [(rows, title) for rows, title in panels if rows]
            if not panels:
                continue
            fig, axes = plt.subplots(1, len(panels), figsize=(7.2, 4), squeeze=False)
            for ax, (rows, title) in zip(axes[0], panels):
                vals = [r['change']/1e8 for r in rows]
                ax.barh([r['name'] for r in rows], vals, color='#0e7a45' if vals[0] < 0 else '#d2232b')
                ax.invert_yaxis()
                ax.set_title(title, fontsize=11, pad=8)
                ax.margins(x=0.3)
                for i, v in enumerate(vals):
                    ax.annotate(f'{v:+.2f}', (v, i), xytext=(3 if v >= 0 else -3, 0), textcoords='offset points', va='center', ha='left' if v >= 0 else 'right', fontsize=8)
            fig.suptitle('净额较前日变化（亿元；左右独立刻度），非当天净额', fontsize=10)
        else:
            fig, ax = plt.subplots(figsize=(7.2, 2.8))
            axes = [[ax]]
            vals, labels = data['values'], data['labels']
            if key == 'cycle':
                ax.plot(labels, vals, color='#d2232b', marker='o')
            else:
                colors = ['#0e7a45', '#c9c6c0', '#d2232b'] if key == 'breadth' and len(vals) == 3 else (['#0e7a45']*3 + ['#c9c6c0'] + ['#d2232b']*3 if key == 'breadth' else '#d2232b')
                ax.bar(labels, vals, color=colors)
            for i, v in enumerate(vals):
                ax.annotate(str(int(v)), (i, v), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=8)
            ax.set_ylim(0, max(max(vals)*1.25, 1))
            ax.set_title(titles[key], fontsize=11, pad=8)
        for row in axes:
            for ax in row:
                ax.spines[['top', 'right']].set_visible(False)
                ax.tick_params(labelsize=8)
                ax.set_axisbelow(True)
                ax.grid(axis='y', color='#c9c6c0', linewidth=0.5, alpha=0.6)
        fig.tight_layout()
        filename = f'{key}.png'
        fig.savefig(out_dir / filename, dpi=150, facecolor='white', metadata={'Software': 'ashare-reader'})
        plt.close(fig)
        names[key] = filename
    return names
