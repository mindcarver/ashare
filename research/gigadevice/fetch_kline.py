# -*- coding: utf-8 -*-
"""获取兆易创新日K线（近250日）保存为CSV，供技术面分析"""
import requests, json

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def kline(code, klt=101, lmt=300):
    """klt=101日线, 102周线"""
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {"secid": f"1.{code}", "klt": klt, "fqt": "1", "lmt": lmt,
              "end": "20500101", "iscca": "1",
              "fields1": "f1,f2,f3,f4,f5,f6",
              "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"}
    r = requests.get(url, params=params, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15)
    d = r.json().get("data", {})
    rows = []
    for line in d.get("klines", []):
        p = line.split(",")
        rows.append({"date": p[0], "open": p[1], "close": p[2], "high": p[3], "low": p[4],
                     "vol": p[5], "amount": p[6], "turnover": p[7] if len(p)>7 else ""})
    return rows

def kline_baidu(code):
    """百度K线带MA"""
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {"all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
              "isFutures": "false", "isStock": "true", "newFormat": "1",
              "group": "quotation_kline_ab", "finClientType": "pc",
              "code": code, "start_time": "", "ktype": "1"}
    hd = {"User-Agent": UA, "Accept": "application/vnd.finance-web.v1+json",
          "Origin": "https://gushitong.baidu.com", "Referer": "https://gushitong.baidu.com/"}
    r = requests.get(url, params=params, headers=hd, timeout=10)
    d = r.json()
    md = d.get("Result", {}).get("newMarketData", {})
    return {"keys": md.get("keys", []), "rows": (md.get("marketData", "") or "").split(";")}

d = kline("603986", 101, 300)
with open("/Users/carver/workspace/mindcarver/ashare/research/gigadevice/kline_daily.json", "w") as f:
    json.dump(d, f, ensure_ascii=False)
w = kline("603986", 102, 120)
with open("/Users/carver/workspace/mindcarver/ashare/research/gigadevice/kline_weekly.json", "w") as f:
    json.dump(w, f, ensure_ascii=False)

print("日K数量:", len(d))
print("最近15日:")
for r in d[-15:]:
    print(f"  {r['date']} O:{r['open']} C:{r['close']} H:{r['high']} L:{r['low']} V:{int(float(r['vol']))/1e4:.0f}万手")
print("\n周K数量:", len(w))
print("最近8周:")
for r in w[-8:]:
    print(f"  {r['date']} C:{r['close']} H:{r['high']} L:{r['low']}")
