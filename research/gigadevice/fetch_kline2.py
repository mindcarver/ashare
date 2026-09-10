# -*- coding: utf-8 -*-
"""腾讯K线接口获取日K/周K"""
import urllib.request, json

def tencent_kline(code, ktype="day", count=320):
    """ktype: day日线 week周线 month月线"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh{code},{ktype},,,{count},qfq"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=15)
    d = json.loads(resp.read().decode("utf-8"))
    key = f"qfq{ktype}" if f"qfq{ktype}" in d["data"][f"sh{code}"] else ktype
    rows = d["data"][f"sh{code}"][key]
    out = []
    for r in rows:
        out.append({"date": r[0], "open": float(r[1]), "close": float(r[2]),
                    "high": float(r[3]), "low": float(r[4]),
                    "vol": float(r[5]) if len(r)>5 else 0})
    return out

d = tencent_kline("603986", "day", 320)
with open("/Users/carver/workspace/mindcarver/ashare/research/gigadevice/kline_daily.json", "w") as f:
    json.dump(d, f, ensure_ascii=False)
w = tencent_kline("603986", "week", 150)
with open("/Users/carver/workspace/mindcarver/ashare/research/gigadevice/kline_weekly.json", "w") as f:
    json.dump(w, f, ensure_ascii=False)
print("日K数量:", len(d))
print("最近20日:")
for r in d[-20:]:
    print(f"  {r['date']} O:{r['open']} C:{r['close']} H:{r['high']} L:{r['low']} V:{r['vol']/1e4:.0f}万手")
print("\n周K数量:", len(w))
print("最近10周:")
for r in w[-10:]:
    print(f"  {r['date']} C:{r['close']} H:{r['high']} L:{r['low']}")

# 计算关键均线
import statistics
closes = [r["close"] for r in d]
def ma(n): return round(sum(closes[-n:])/n, 2)
print(f"\nMA5={ma(5)} MA10={ma(10)} MA20={ma(20)} MA60={ma(60)} MA120={ma(120)} MA250={ma(250)}")
print(f"最新收盘: {closes[-1]}")
# 高点低点
hi = max(r["high"] for r in d); lo = min(r["low"] for r in d)
print(f"近{len(d)}日最高: {hi} 最低: {lo}")
# 回撤计算
peak = max(r["high"] for r in d[-250:])
print(f"近250日最高: {peak}, 当前价较最高回撤: {(closes[-1]/peak-1)*100:.1f}%")
