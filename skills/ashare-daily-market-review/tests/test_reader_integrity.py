import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'scripts'))
import render_reader_report as reader
from reader_evidence import breadth_distribution, check_breadth, exact_series, checked_extra
from reader_charts import chart_data
import test_deep_analysis as deep_fixture

class ReaderIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def context(self, market=None, extra=None, day='2026-08-25'):
        p=self.work/'market.json';p.write_text(json.dumps(market or json.loads((ROOT/'tests/fixtures/market.json').read_text())))
        e=self.work/'extra.json';e.write_text(json.dumps(extra or {}))
        return reader.Ctx(SimpleNamespace(input=str(p),extra=str(e),workdir=str(self.work),date=day,board_hist=None,history_dir=None))

    def metadata(self, day='2026-08-25'):
        return {'observed_at':day,'published_at':day,'fetched_at':day+'T16:00:00+08:00',
                'source':{'id':'test-extra','name':'测试来源','url':'https://example.com/evidence'},
                'method_category':'provider_model','window':{'trading_days':5,'end_at':day}}

    def test_input_date_mismatch_is_rejected(self):
        with self.assertRaises(reader.ReviewError):self.context(day='2026-08-26')

    def test_market_evidence_validation_is_not_bypassed(self):
        m=json.loads((ROOT/'tests/fixtures/market.json').read_text());m['sections']['indices']['items'][0]['close']['observed_at']='2026-08-26'
        with self.assertRaises(reader.ReviewError):self.context(m)

    def test_missing_target_kline_does_not_use_latest(self):
        ctx=self.context();ctx.klines={'x':[{'date':'2026-08-26','close':999}]}
        self.assertEqual(ctx.kline('x'),{});self.assertEqual(exact_series(ctx.klines['x'],ctx.md),[])
        self.assertEqual(exact_series([{'date':ctx.md,'close':1},{'date':'2026-08-26','close':999}],ctx.md),[{'date':ctx.md,'close':1}])

    def test_undated_and_future_extra_are_excluded(self):
        ctx=self.context();raw={'volume_scan':{'1':{'f12':'1','f14':'错日股','f3':-9,'f10':2}}}
        valid,excluded=checked_extra(raw,ctx.market,{})
        self.assertNotIn('volume_scan',valid);self.assertEqual(len(excluded),1)
        raw['evidence']={'volume_scan':self.metadata('2026-08-26')}
        self.assertNotIn('volume_scan',checked_extra(raw,ctx.market,{})[0])

    def test_extra_quote_conflict_is_excluded_even_with_metadata(self):
        ctx=self.context();raw={'stock_inflow':[{'f12':'1','f14':'甲','f3':-2}],'evidence':{'stock_inflow':self.metadata()}}
        valid,excluded=checked_extra(raw,ctx.market,{'1':{'change':10}})
        self.assertNotIn('stock_inflow',valid);self.assertIn('冲突',excluded[0]['reason'])

    def test_bucket_boundaries_and_chart_reuse(self):
        rows=[{'f12':str(i),'f3':v} for i,v in enumerate([-9,-5,-0.05,-0.01,0,0.01,0.05,5,9])]
        stats=breadth_distribution(rows);self.assertEqual(stats['counts'],[1,1,2,1,2,1,1]);self.assertEqual(stats['total'],9)
        ctx=self.context();ctx.breadth=stats
        self.assertEqual(chart_data(ctx,[])['breadth']['values'],stats['counts'])
        self.assertIn('−5%＜涨跌幅＜0%为 2 只','\n'.join(reader.sentiment_section(ctx)))

    def test_st_universe_conflict_is_detected(self):
        with self.assertRaisesRegex(reader.ReviewError,'ST'):
            check_breadth([{'f12':'1','f14':'*ST甲','f3':1}],{'universe':{'includes_st':False}})

    def test_missing_values_and_all_unknown_can_render(self):
        m=json.loads((ROOT/'tests/fixtures/unknown.json').read_text());text=reader.render(self.context(m))
        self.assertIn('未知',text);self.assertNotIn('100.00%',text);self.assertNotIn('一日游',text);self.assertNotIn('5板',text)

    def test_volume_missing_return_is_not_a_decline(self):
        ctx=self.context();ctx.extra={'volume_scan':{'x':{'f14':'缺涨跌','f10':2},'y':{'f14':'平盘股','f10':3,'f3':0}}}
        text='\n'.join(reader.volume_scan_section(ctx));self.assertNotIn('缺涨跌 |',text);self.assertIn('放量平盘',text);self.assertNotIn('放量下跌',text)

    def test_cash_delta_not_daily_outflow(self):
        ctx=self.context();ctx.prev_md='2026-08-24';ctx.board_hist={'boards':{'x':{'name':'电子','rows':['2026-08-24,22703000000','2026-08-25,-12668000000','2026-08-26,99999999999']}}}
        rows=reader.flow_changes(ctx);self.assertEqual(rows[0]['today'],-12668000000);self.assertEqual(rows[0]['change'],-35371000000)
        self.assertEqual(chart_data(ctx,rows)['redirect']['decrease'][0]['change'],-35371000000)
        text='\n'.join(reader.mainline_section(ctx));self.assertIn('-126.68亿元',text);self.assertIn('-353.71亿元',text);self.assertNotIn('单日被抽',text)

    def test_declared_mainline_rules_change_reader_classification(self):
        m=deep_fixture.DeepAnalysisTests().deep_market();text='\n'.join(reader.mainline_section(self.context(m)));self.assertIn('情绪与资金同向',text)
        m['sections']['mainline_matrix']['quadrant_rules']['capital_threshold_cny']=9e12
        text='\n'.join(reader.mainline_section(self.context(m)));self.assertNotIn('情绪与资金同向',text);self.assertNotIn('泰达',text)

    def test_deep_coverage_preserved_and_no_unsupported_causation(self):
        text=reader.render(self.context(deep_fixture.DeepAnalysisTests().deep_market()))
        for name in reader.LABELS.values():self.assertIn(name,text)
        self.assertNotIn('跌幅由浮筹决定',text);self.assertNotIn('http',text);self.assertNotIn('测试来源',text)

    def test_insight_requires_exact_code_and_hypothesis_fields(self):
        ctx=self.context();valid,excluded=checked_extra({'insights':[{'text':'电子被抽354亿','anchors':[]}]},ctx.market,{})
        self.assertFalse(valid.get('insights'));self.assertEqual(len(excluded),1)

    def test_two_industries_not_relabelled_as_first_industry(self):
        ctx=self.context();ctx.extra={'stock_inflow':[{'f14':'芯片甲','f100':'半导体','f3':12,'f62':1e9},{'f14':'汽车乙','f100':'汽车','f3':10,'f62':9e8}]}
        text='\n'.join(reader.stocks_section(ctx));self.assertIn('芯片甲 | 半导体',text);self.assertIn('汽车乙 | 汽车',text);self.assertNotIn('半导体内',text)

    def test_breadth_row_timestamp_cannot_be_overridden_by_metadata(self):
        from datetime import datetime
        ctx=self.context()
        raw={'breadth_rows':[{'f12':'1','f14':'甲','f3':1,'f124':datetime.fromisoformat('2026-08-26T15:00:00+08:00').timestamp()}],
             'evidence':{'breadth_rows':self.metadata()}}
        valid,excluded=checked_extra(raw,ctx.market,{})
        self.assertNotIn('breadth_rows',valid)
        self.assertTrue(excluded)

    def test_inconsistent_sealing_denominator_is_rejected(self):
        ctx=self.context()
        up=reader.metric(ctx.sections['breadth'],'limit_up')
        ctx.sections['short_term_sentiment']['metrics']={'open_board_failed':{'value':20},'limit_attempts':{'value':up+21}}
        with self.assertRaises(reader.ReviewError):ctx._check_pools()

    def test_multiple_board_rollup_is_not_presented_as_deduplicated(self):
        ctx=self.context(deep_fixture.DeepAnalysisTests().deep_market())
        row=ctx.derived['mainline_matrix']['themes'][0]
        row['boards']=['parent','child'];row['board_fund_flow_cny']=8558000000
        text='\n'.join(reader.mainline_section(ctx))
        self.assertIn('多板块需先去重',text)
        self.assertNotIn('85.58',text)
        self.assertNotIn('情绪与资金同向',text)

    def test_board_history_cross_checks_canonical_amount_and_id(self):
        ctx=self.context(deep_fixture.DeepAnalysisTests().deep_market())
        raw={'board_history':{'boards':{'sw-a':{'name':'任意标签','rows':['2026-08-25,90000000000']}}},
             'evidence':{'board_history':self.metadata()}}
        valid,excluded=checked_extra(raw,ctx.market,{})
        self.assertNotIn('board_history',valid)
        self.assertIn('冲突',excluded[0]['reason'])
        raw['board_history']['boards']['sw-a']['rows']=['2026-08-24,1000000000','2026-08-25,3000000000']
        valid,excluded=checked_extra(raw,ctx.market,{})
        self.assertFalse(excluded)
        self.assertEqual(valid['board_history']['boards']['sw-a']['name'],ctx.market['sections']['sectors']['items'][0]['name'])
        raw['board_history']['boards']['sw-a']['rows'].append('2026-08-25,3000000000')
        self.assertNotIn('board_history',checked_extra(raw,ctx.market,{})[0])

    def test_collector_snapshot_date_is_verified_before_labelling(self):
        import fetch_reader_extra
        from datetime import datetime
        day='2026-08-25'
        row={'f12':'1','f124':datetime.fromisoformat(day+'T15:00:00+08:00').timestamp()}
        self.assertEqual(fetch_reader_extra.snapshot_rows({'data':{'diff':[row]}},day),[row])
        with self.assertRaises(ValueError):fetch_reader_extra.snapshot_rows({'data':{'diff':[row]}},'2026-08-24')

    def test_collector_does_not_invent_historical_publication_day(self):
        import fetch_reader_extra
        meta=fetch_reader_extra.meta('2020-01-02','stock_inflow','https://example.com')
        self.assertEqual(meta['published_at'],meta['fetched_at'][:10])
        self.assertEqual(meta['publication_basis'],'known_by_fetch')
        self.assertNotEqual(meta['published_at'],'2020-01-02')

    def test_report_is_deterministic(self):
        ctx=self.context();self.assertEqual(reader.render(ctx),reader.render(ctx));self.assertEqual(reader.render_widget(ctx),reader.render_widget(ctx))

if __name__=='__main__':unittest.main()
