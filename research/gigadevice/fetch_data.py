# -*- coding: utf-8 -*-
"""兆易创新(603986) 综合数据采集"""
import json, urllib.request, time, random, requests

CODE = "603986"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# ---------- 1. 腾讯实时行情 ----------
def tencent_quote(codes):
    prefixed = [f"sh{c}" if c.startswith(("6","9")) else f"sz{c}" for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        code = key[2:]
        result[code] = {
            "name": vals[1], "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0, "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return result

# ---------- 2. 东财 datacenter 查询 ----------
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_last = [0.0]
def em_get(url, params=None, headers=None, timeout=15, **kw):
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait + random.uniform(0.1, 0.4))
    try: return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kw)
    finally: _last[0] = time.time()

DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
def dc_query(report, flt="", ps=50, sort="", st="-1"):
    params = {"reportName": report, "columns": "ALL", "filter": flt,
              "pageNumber": "1", "pageSize": str(ps),
              "sortColumns": sort, "sortTypes": st, "source": "WEB", "client": "WEB"}
    r = em_get(DC, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"): return d["result"]["data"]
    return []

out = {}
# ---------- 行情 ----------
q = tencent_quote([CODE])
out["quote"] = q.get(CODE, {})

# ---------- 股东户数 ----------
holders = dc_query("RPT_HOLDERNUMLATEST", f'(SECURITY_CODE="{CODE}")', ps=10, sort="END_DATE")
out["holders"] = [{"date": str(h.get("END_DATE",""))[:10], "num": h.get("HOLDER_NUM"), "chg_ratio": h.get("HOLDER_NUM_RATIO"), "avg": h.get("AVG_FREE_SHARES")} for h in holders[:6]]

# ---------- 解禁 ----------
from datetime import datetime, timedelta
today = "2026-08-01"
hist = dc_query("RPT_LIFT_STAGE", f'(SECURITY_CODE="{CODE}")', ps=10, sort="FREE_DATE", st="-1")
out["lockup_hist"] = [{"date": str(h.get("FREE_DATE",""))[:10], "type": h.get("LIMITED_STOCK_TYPE"), "shares": h.get("FREE_SHARES_NUM"), "ratio": h.get("FREE_RATIO")} for h in hist[:6]]
end = (datetime.strptime(today,"%Y-%m-%d")+timedelta(days=180)).strftime("%Y-%m-%d")
upc = dc_query("RPT_LIFT_STAGE", f'(SECURITY_CODE="{CODE}")(FREE_DATE>=\'{today}\')(FREE_DATE<=\'{end}\')', ps=20, sort="FREE_DATE", st="1")
out["lockup_upcoming"] = [{"date": str(h.get("FREE_DATE",""))[:10], "type": h.get("LIMITED_STOCK_TYPE"), "shares": h.get("FREE_SHARES_NUM"), "ratio": h.get("FREE_RATIO")} for h in upc]

# ---------- 融资融券 ----------
margin = dc_query("RPTA_WEB_RZRQ_GGMX", f'(SCODE="{CODE}")', ps=10, sort="DATE")
out["margin"] = [{"date": str(m.get("DATE",""))[:10], "rzye_yi": round((m.get("RZYE") or 0)/1e8, 2), "rzmre_yi": round((m.get("RZMRE") or 0)/1e8, 2)} for m in margin[:6]]

# ---------- 资金流120日 ----------
def fund_flow(code):
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {"secid": f"1.{code}", "fields1": "f1,f2,f3,f7",
              "fields2": "f51,f52,f53,f54,f55,f56,f57",
              "lmt": "120"}
    hd = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        r = em_get(url, params=params, headers=hd, timeout=15)
        k = r.json().get("data", {}).get("klines", [])
        rows = []
        for line in k:
            p = line.split(",")
            if len(p) >= 7:
                rows.append({"date": p[0], "main_net": float(p[1]) if p[1]!="-" else 0})
        return rows
    except Exception as e:
        return []
ff = fund_flow(CODE)
if ff:
    out["fund_flow"] = {
        "d5": round(sum(x["main_net"] for x in ff[-5:])/1e8, 2),
        "d10": round(sum(x["main_net"] for x in ff[-10:])/1e8, 2),
        "d20": round(sum(x["main_net"] for x in ff[-20:])/1e8, 2),
        "d60": round(sum(x["main_net"] for x in ff[-60:])/1e8, 2),
        "last": ff[-1]["date"],
    }

# ---------- 龙虎榜 ----------
lhb = dc_query("RPT_DAILYBILLBOARD_DETAILSNEW", f"(TRADE_DATE>='2026-04-01')(TRADE_DATE<='2026-08-01')(SECURITY_CODE=\"{CODE}\")", ps=20, sort="TRADE_DATE")
out["lhb"] = [{"date": str(r.get("TRADE_DATE",""))[:10], "reason": r.get("EXPLANATION"), "net_buy_wan": round((r.get("BILLBOARD_NET_AMT") or 0)/1e4, 0)} for r in lhb[:10]]

# ---------- 分红 ----------
div = dc_query("RPT_SHAREBONUS_DET", f'(SECURITY_CODE="{CODE}")', ps=5, sort="EX_DIVIDEND_DATE")
out["dividend"] = [{"date": str(d.get("EX_DIVIDEND_DATE",""))[:10], "bonus": d.get("PRETAX_BONUS_RMB"), "progress": d.get("ASSIGN_PROGRESS")} for d in div[:4]]

print(json.dumps(out, ensure_ascii=False, indent=1))
