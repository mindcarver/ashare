import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools'))
import test_reader_integrity
import render_reader_report as reader
from schema import ReviewError


class ReaderDepthTests(unittest.TestCase):
    setUp = test_reader_integrity.ReaderIntegrityTests.setUp
    context = test_reader_integrity.ReaderIntegrityTests.context
    metadata = test_reader_integrity.ReaderIntegrityTests.metadata
    def test_volume_and_amount_are_separate(self):
        from price_volume import price_volume_metrics
        rows = [{'date': f'2026-08-{20+i:02d}', 'close': 10, 'volume': 100,
                 'amount': 1000} for i in range(6)]
        rows[-1].update(volume=80, amount=1200)
        values = price_volume_metrics(rows, '2026-08-25')
        self.assertEqual(values['volume_ratio_5d'], 0.8)
        self.assertEqual(values['amount_ratio_5d'], 1.2)
        self.assertEqual(values['consecutive_volume_days'], 0)
        self.assertIsNone(values['volume_percentile_120d'])
        with self.assertRaises(ReviewError):
            price_volume_metrics(rows, '2026-08-26')

    def test_amount_disguised_as_volume_is_rejected(self):
        from price_volume import validate_bar_metrics
        rows = [{'date': f'2026-08-{20+i:02d}', 'close': 10, 'volume': 100,
                 'amount': 1000} for i in range(6)]
        rows[-1].update(volume=80, amount=1200)
        with self.assertRaisesRegex(ReviewError, 'volume_ratio_5d'):
            validate_bar_metrics({'daily_bars': rows, 'volume_ratio_5d': {'value': 1.2}}, '2026-08-25')

    def test_pool_groups_use_intersection_and_disclose_missing_flow(self):
        from reader_depth import previous_pool_analysis
        ctx = self.context()
        ctx.zt_prev = [{'c': 'a', 'n': '甲', 'lbc': 2}, {'c': 'b', 'n': '乙', 'lbc': 1}, {'c': 'c', 'n': '丙', 'lbc': 1}]
        ctx.zt = [{'c': 'b', 'n': '乙', 'lbc': 2}]
        ctx.windows = {'a': {'f12': 'a', 'f3': 12.9, 'f62': -1e8}, 'b': {'f12': 'b', 'f3': 10, 'f62': 2e8}}
        ctx.observations = {}
        result = previous_pool_analysis(ctx)
        self.assertEqual(result['groups'][1]['promoted'], 0)
        self.assertEqual(result['groups'][1]['broken'], 1)
        self.assertEqual(result['groups'][0]['price_covered'], 1)
        self.assertIsNone(result['groups'][0]['flow_total'])
        self.assertEqual(result['groups'][0]['flow_sample'], 2e8)

    def test_pool_summary_conflict_is_rejected(self):
        from reader_depth import previous_pool_analysis
        ctx = self.context()
        ctx.zt_prev = [{'c': 'a', 'n': '甲', 'lbc': 1}]
        ctx.zt = [{'c': 'a', 'n': '甲', 'lbc': 2}]
        ctx.windows = {'a': {'f12': 'a', 'f3': 10}}
        ctx.observations = {}
        ctx.derived['prev_pool_performance'] = {'pool_size': 1, 'promotion_count': 1, 'avg_change_pct': -1}
        with self.assertRaisesRegex(ReviewError, '昨日池'):
            previous_pool_analysis(ctx)

    def test_confirmed_zero_limit_up_keeps_previous_groups(self):
        from reader_depth import previous_pool_analysis
        from reader_evidence import checked_extra
        ctx = self.context()
        accepted, excluded = checked_extra({'zt_pool': [], 'evidence': {'zt_pool': self.metadata()}}, ctx.market, {})
        self.assertEqual(accepted['zt_pool'], [])
        ctx.zt_available = True
        ctx.zt = []
        ctx.zt_prev = [{'c': 'a', 'n': '甲', 'lbc': 2}]
        ctx.windows = {'a': {'f3': -5, 'f62': -10}}
        ctx.observations = {}
        result = previous_pool_analysis(ctx)
        self.assertEqual(result['groups'][1]['promoted'], 0)
        self.assertEqual(result['groups'][1]['broken'], 1)

    def test_seal_snapshot_conflict_is_not_silently_mixed(self):
        from reader_evidence import checked_extra
        ctx = self.context()
        raw = {'zt_pool': [{'c': 'a', 'n': '甲', 'lbc': 2, 'fund': 30000000}],
               'evidence': {'zt_pool': self.metadata()}}
        observations = {'a': {'seal_amount': 2000000}}
        accepted, excluded = checked_extra(raw, ctx.market, observations)
        self.assertNotIn('zt_pool', accepted)
        self.assertIn('封单', excluded[0]['reason'])

    def test_reader_order_and_no_duplicate_lead(self):
        ctx = self.context()
        text = reader.render(ctx)
        titles = ['## 今日判断', '## 主线逐条看', '## 市场与延续性', '## 后续核验', '## 证据附录']
        self.assertEqual(sorted(text.index(s) for s in titles), [text.index(s) for s in titles])
        self.assertEqual(text.count('短线状态：'), 1)
        page = reader.render_html(ctx, text)
        self.assertIn('<details', page)
        self.assertEqual(page.count('<h1>'), 1)

    def test_past_observation_is_not_called_tomorrow(self):
        ctx = self.context()
        ctx.market['as_of'] = '2026-09-20'
        ctx.market['snapshot']['cutoff_at'] = '2026-09-20T16:00:00+08:00'
        text = reader.render(ctx)
        self.assertIn('历史修订版', text)
        self.assertIn('已到观察日', text)
        self.assertNotIn('下一交易日观察', text)

    def test_representative_board_does_not_add_parent_child(self):
        import test_deep_analysis
        m = test_deep_analysis.DeepAnalysisTests().deep_market()
        boards = m['sections']['sectors']['items']
        child = __import__('copy').deepcopy(boards[0])
        child.update(id='child-board', name='子板块')
        boards.append(child)
        theme = m['sections']['mainline_matrix']['themes'][0]
        theme['boards'] = [boards[0]['id'], child['id']]
        theme['representative_board_id'] = boards[0]['id']
        ctx = self.context(m)
        result = ctx.derived['mainline_matrix']['themes'][0]
        self.assertEqual(result['board_fund_flow_cny'], boards[0]['fund_flow']['value'])
        self.assertNotIn('未确认可加总', '\n'.join(reader.mainline_section(ctx)))
        from render_analysis import markdown_mainline, html_mainline
        md = '\n'.join(markdown_mainline(ctx.derived['mainline_matrix'],ctx.sections['mainline_matrix']))
        html = html_mainline(ctx.derived['mainline_matrix'],ctx.sections['mainline_matrix'])
        self.assertNotIn('声明板块求和',md)
        self.assertNotIn('板块涨跌(等权)',html)
        self.assertIn('不代表全主题去重合计',md)
        self.assertIn('不代表全主题去重合计',html)
        theme['representative_board_id'] = 'nonexistent'
        with self.assertRaises(ReviewError):
            self.context(m)

    def test_archive_cash_requires_independent_dated_price_match(self):
        from reader_evidence import checked_extra
        from datetime import datetime
        ctx = self.context()
        stamp = datetime.fromisoformat('2026-08-25T15:00:00+08:00').timestamp()
        meta = self.metadata()
        meta.update(retrieval_mode='historical_archive', publication_basis='known_by_fetch',
                    quote_crosscheck=[{'f12':'a','f2':10,'f3':1,'f124':stamp}])
        raw = {'stock_windows':{'a':{'f12':'a','f2':10,'f3':1,'f62':2}}, 'evidence':{'stock_windows':meta}}
        self.assertIn('stock_windows',checked_extra(raw,ctx.market,{})[0])
        raw['stock_windows']['a']['f2']=11
        self.assertNotIn('stock_windows',checked_extra(raw,ctx.market,{})[0])

    def test_window_difference_does_not_claim_day_to_day_reversal(self):
        from reader_depth import window_comparisons
        ctx=self.context()
        ctx.deep={'security_details':{'items':[{'name':'甲','fund_flow_windows_cny':{1:1,10:-1}}]}}
        self.assertEqual(window_comparisons(ctx)[0]['reading'],'当日净额为正，10日累计为负')

    def test_partial_lhb_has_chinese_missing_seats(self):
        from deep_render import markdown_lhb
        text='\n'.join(markdown_lhb({'availability':'partial','observed_at':'2026-08-25','published_at':'2026-08-25','note':'仅净额可得','items':[{
            'name':'甲','code':'000001','buy_amount_cny':None,'sell_amount_cny':None,'net_amount_cny':10,
            'buyer_count':None,'seller_count':None,'top_buyer_share_pct':None,'top_seller_share_pct':None,'seat_types':[]}]}))
        self.assertNotIn('unknown',text)
        self.assertIn('未知/未知',text)


if __name__ == '__main__':
    unittest.main()
