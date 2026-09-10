# -*- coding: utf-8 -*-
"""东财研报 + 大宗交易 + 资金流"""
import requests, json, time, random

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CODE = "603986"
S = requests.Session(); S.headers.update({"User-Agent": UA})
_last = [0.0]
def em_get(url, params=None, headers=None, timeout=15):
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait + random.uniform(0.1, 0.4))
    try: return S.get(url, params=params, headers=headers, timeout=timeout)
    finally: _last[0] = time.time()

# 1. 研报
reports = []
try:
    for page in [1,2]:
        params = {"industryCode":"*","pageSize":"50","industry":"*","rating":"*","ratingChange":"*",
                  "beginTime":"2026-01-01","endTime":"2030-01-01","pageNo":str(page),"fields":"",
                  "qType":"0","orgCode":"","code":CODE,"rcode":"","p":str(page),"pageNum":str(page),"pageNumber":str(page)}
        r = em_get("https://reportapi.eastmoney.com/report/list", params=params,
                   headers={"Referer":"https://data.eastmoney.com/"}, timeout=30)
        rows = r.json().get("data") or []
        reports.extend(rows)
        if len(rows) < 50: break
        time.sleep(1)
except Exception as e:
    print("研报失败:", e)

print(f"2026年以来研报 {len(reports)} 篇")
for rp in reports[:15]:
    eps = rp.get("predictThisYearEps") or rp.get("predictNextYearEps")
    print(f"  {rp.get('publishDate','')[:10]} | {rp.get('orgSName')} | {rp.get('emRatingName')} | {rp.get('title','')[:45]} | 26EPS:{rp.get('predictThisYearEps')} 27EPS:{rp.get('predictNextYearEps')}")

# 2. 大宗交易
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
params = {"reportName":"RPT_DATA_BLOCKTRADE","columns":"ALL","filter":f'(SECURITY_CODE="{CODE}")',
          "pageNumber":"1","pageSize":"15","sortColumns":"TRADE_DATE","sortTypes":"-1","source":"WEB","client":"WEB"}
r = em_get(DC, params=params, timeout=15)
data = r.json().get("result",{}).get("data",[]) or []
print(f"\n大宗交易 {len(data)} 条")
for d in data[:8]:
    print(f"  {str(d.get('TRADE_DATE',''))[:10]} 价:{d.get('DEAL_PRICE')} 量:{d.get('DEAL_VOLUME')} 额:{round((d.get('DEAL_AMT') or 0)/1e4,0)}万 买:{d.get('BUYER_NAME','')[:20]}")

# 3. 资金流120日
params = {"secid": f"1.{CODE}", "fields1":"f1,f2,f3,f7",
          "fields2":"f51,f52,f53,f54,f55,f56,f57","lmt":"120"}
r = em_get("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get", params=params,
           headers={"Referer":"https://quote.eastmoney.com/"}, timeout=15)
kl = r.json().get("data",{}).get("klines",[]) or []
rows = []
for line in kl:
    p = line.split(",")
    if len(p)>=7: rows.append({"date":p[0], "main":float(p[1]) if p[1]!="-" else 0})
print(f"\n资金流(主力净流入,亿):")
for n in [5,10,20,60]:
    print(f"  近{n}日: {round(sum(x['main'] for x in rows[-n:])/1e8, 2)}")
print("  最近5日明细:")
for x in rows[-5:]:
    print(f"    {x['date']}: {round(x['main']/1e4,0)}万")
