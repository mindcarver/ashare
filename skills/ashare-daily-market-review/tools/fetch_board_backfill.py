#!/usr/bin/env python3
"""板块净额历史补充：按目标日截断，保留逐板块来源和缺口。"""
import argparse
import json
from pathlib import Path
from fetch_reader_extra import get, meta


def collect(market):
    day=market['market_date'];boards={};errors=[];refs=[]
    for item in market['sections']['sectors'].get('items',[]):
        if not item.get('fund_flow'):continue
        board=item['id']
        url=f'https://push2his.eastmoney.com/api/qt/stock/fflow/kline/get?lmt=0&klt=101&fields1=f1,f2,f3,f7&fields2=f51,f52&secid=90.{board}'
        try:
            response=get(url);rows=(response.get('data') or {}).get('klines') or []
            rows=[r for r in rows if r.split(',')[0]<=day]
            if not rows or rows[-1].split(',')[0]!=day:raise ValueError('缺少目标日，不能使用其他日期')
            evidence=meta(day,board,url);refs.append(evidence['source']['id'])
            boards[board]={'name':item['name'],'rows':rows[-6:],'evidence':evidence}
        except Exception as exc:errors.append({'component':board,'reason':str(exc)})
    result={'collection_errors':errors}
    if boards:
        evidence=meta(day,'board_history',url)
        evidence['source']={'id':'board-history-'+day,'name':'板块净额历史汇集','kind':'derived','evidence_refs':refs}
        result.update(board_history={'boards':boards},evidence={'board_history':evidence})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();output=Path(args.output)
    if output.exists():parser.error('输出已存在，请使用新的修订文件名')
    result=collect(json.loads(Path(args.input).read_text()))
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
