# -*- coding: utf-8 -*-
"""新浪财报三表 + K线"""
import requests, json

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CODE = "603986"

def sina_financial(code, rtype, num=8):
    prefix = "sh" if code.startswith("6") else "sz"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {"paperCode": f"{prefix}{code}", "source": rtype, "type": "0", "page": "1", "num": str(num)}
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
    rl = r.json().get("result", {}).get("data", {}).get("report_list", {}) or {}
    rows = []
    for period in sorted(rl.keys(), reverse=True)[:num]:
        obj = rl[period]
        rec = {"报告期": f"{period[:4]}-{period[4:6]}"}
        for it in obj.get("data", []) or []:
            t = it.get("item_title", "")
            if not t or it.get("item_value") is None: continue
            rec[t] = it.get("item_value")
            tb = it.get("item_tongbi")
            if tb not in (None, ""): rec[t+"_同比"] = tb
        rows.append(rec)
    return rows

out = {}
out["lrb"] = sina_financial(CODE, "lrb", 8)
out["llb"] = sina_financial(CODE, "llb", 8)
out["fzb"] = sina_financial(CODE, "fzb", 6)

# 精简输出
for name in ["lrb","llb","fzb"]:
    print(f"\n===== {name} =====")
    for rec in out[name][:6]:
        keep = {k:v for k,v in rec.items() if k in ["报告期","营业总收入","营业收入","净利润","归属于母公司所有者的净利润","扣除非经常性损益后的净利润","销售毛利率","净资产收益率","经营活动产生的现金流量净额","总资产","总负债","所有者权益(或股东权益)合计","货币资金","存货","应收账款","营业总成本","销售费用","管理费用","研发费用","财务费用","基本每股收益","加权平均净资产收益率","销售净利率"]}
        print(json.dumps(keep, ensure_ascii=False))
