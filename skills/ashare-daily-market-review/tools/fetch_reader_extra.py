#!/usr/bin/env python3
"""按指定日采集读者增量；最新快照错日时拒用，元数据随块保存。"""
import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')


def get(url):
    request = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://quote.eastmoney.com/'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def meta(day, key, url):
    now = datetime.now(ZONE)
    return {'observed_at':day, 'published_at':now.date().isoformat(), 'publication_basis':'known_by_fetch', 'fetched_at':now.isoformat(),
            'method_category':'exchange_fact' if key=='lhb_rows' else 'provider_model',
            'source':{'id':f'reader-{key}-{day}', 'name':key, 'url':url}}


def snapshot_rows(response, day):
    rows = (response.get('data') or {}).get('diff')
    if not isinstance(rows,list) or not rows:
        raise ValueError('快照为空，不能当作零')
    for row in rows:
        stamp = row.get('f124')
        if not isinstance(stamp,(int,float)) or datetime.fromtimestamp(stamp,ZONE).date().isoformat()!=day:
            raise ValueError('最新快照日期不符，不能回填历史日')
    return rows


def collect(day):
    date.fromisoformat(day)
    result = {'evidence':{},'collection_errors':[]}
    for key, order in [('stock_inflow',1),('stock_outflow',0)]:
        try:
            rows=[]
            for page in (1,2):
                query=urllib.parse.urlencode({'pn':page,'pz':100,'po':order,'np':1,'fltt':2,'invt':2,'fid':'f62',
                    'fs':'m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23','fields':'f12,f14,f2,f3,f6,f62,f8,f100,f124'})
                url='https://push2delay.eastmoney.com/api/qt/clist/get?'+query
                rows.extend(snapshot_rows(get(url),day))
            result[key]=rows;result['evidence'][key]=meta(day,key,url)
        except Exception as exc:
            result['collection_errors'].append({'component':key,'reason':str(exc)})
    try:
        query=urllib.parse.urlencode({'reportName':'RPT_DAILYBILLBOARD_DETAILSNEW','columns':'ALL','pageSize':500,'pageNumber':1,'filter':f"(TRADE_DATE='{day}')"})
        url='https://datacenter-web.eastmoney.com/api/data/v1/get?'+query
        data=get(url).get('result') or {};rows=data.get('data') or []
        if not rows or data.get('pages',1)>1 or any(str(r.get('TRADE_DATE',''))[:10]!=day for r in rows):
            raise ValueError('龙虎榜为空、分页未完或日期不符')
        result['lhb_rows']=rows;result['evidence']['lhb_rows']=meta(day,'lhb_rows',url)
    except Exception as exc:
        result['collection_errors'].append({'component':'lhb_rows','reason':str(exc)})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();output=Path(args.output)
    if output.exists():parser.error('输出已存在，请使用新的修订文件名')
    result=collect(args.date);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'output':str(output),'unavailable':len(result['collection_errors'])},ensure_ascii=False))


if __name__=='__main__':main()
