#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成图表化资本环境仪表盘 HTML —— ashare-capital-environment-dashboard 技能的生成脚本。

用法：
  1. 运行 --as-of YYYY-MM-DD 指定回放日期
  2. 可选 --cells cells.json 输入 28 格数据；每格可为单条记录或历史记录数组
     - market: global | us | cn | kr
     - dimension: growth | inflation | liquidity | funding-price | risk-credit | market-breadth | institutional-positioning
     - type: gauge | line | bar | unknown（配置格式见 references/html-template.md 第三节）
  3. 运行：python3 scripts/gen_dashboard.py --cells cells.json --as-of YYYY-MM-DD --out report.html
  4. 自检（SKILL.md 第五节）：node --check + CELLS JSON 校验 + 禁词扫描
  5. present_files 交付

仅选择 publishedAt <= asOf 的记录；无合格记录会诚实降级为未知。
覆盖矩阵、市场聚合徽章、overview 覆盖等级全部自动生成，无需手改。
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# ============ 28 格数据 ============
CELLS = {
    # ---- 全球（首版无可审计来源，诚实降级）----
    # ---- 全球（2026-08-02 实测升级：IMF WEO + 各央行官网 + ICE BofA）----
    "global|growth": {
        "type": "gauge", "value": 3.0, "unit": "%", "min": 0, "max": 6,
        "name": "2026 GDP增速预测", "sections": [[0.33, "#16a34a"], [0.67, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 3.1, "label": "4月预测 3.1%"}],
        "source": "imf-weo（IMF World Economic Outlook 2026/7/8 更新, 2026全球增速预测3.0%/2027 3.4%）",
        "observedAt": "2026-07-08", "publishedAt": "2026-07-08", "processingVersion": "v1.1", "availability": "available",
        "analysis": [
            ["水平", "3.0% 处近十年中枢下沿，略低于潜在增速，属「低增长」区间"],
            ["趋势", "7 月版较 4 月微降 0.1pp，主因中东战争拖累能源进口国；但 AI 链国家上修"],
            ["结构", "分化是关键词：发达经济体 ~1.5% vs 新兴市场 ~4%，AI 受益国 vs 能源进口国剪刀差扩大"],
            ["政策含义", "增长放缓 + 通胀回升的组合压缩央行宽松空间，财政空间普遍偏薄"],
        ],
        "takeaways": [["全球增长", "3.0% 低增长 + 4.4% 高通胀 = 类滞胀组合，政策空间双向受限"]],
        "risk": {"level": "high", "label": "全球增长", "text": "类滞胀钳制：3.0% 低增长 + 4.4% 高通胀，政策宽松空间被通胀封死"},
    },
    "global|inflation": {
        "type": "gauge", "value": 4.4, "unit": "%", "min": 0, "max": 8,
        "name": "全球通胀预测", "sections": [[0.25, "#16a34a"], [0.5, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 2.0, "label": "央合目标 ~2%"}],
        "source": "imf-weo（IMF WEO 2026/4, 全球通胀预测4.4%；7月版称下行趋势已停止）",
        "observedAt": "2026-04-14", "publishedAt": "2026-04-14", "processingVersion": "v1.1", "availability": "available",
        "analysis": [
            ["水平", "4.4% 为目标 2% 的两倍多，仍处高位"],
            ["趋势", "关键信号：IMF 7 月版明确「下行趋势已停止」，通胀二次抬升风险上升"],
            ["结构", "中东油价主导输入型通胀，叠加能源进口国压力；AI 需求推升部分商品"],
            ["预期差", "若战争升级，IMF 不利情景下通胀可达 5.4%——这是最大尾部风险"],
        ],
        "takeaways": [["全球通胀", "下行停止 + 油价风险 = 通胀二次抬升是下半年核心宏观变量"]],
        "risk": {"level": "high", "label": "全球通胀", "text": "下行趋势停止，中东油价若再涨，不利情景通胀 5.4%——二次抬升风险"},
    },
    "global|liquidity": {
        "type": "bar", "categories": ["美联储", "欧央行", "日央行", "中国央行"],
        "values": [6.74, 3.96, 5.8, 44.2], "colors": ["#2563eb", "#2563eb", "#2563eb", "#2563eb"], "unit": "$T/万亿",
        "source": "各央行官网：Fed总资产$6.74T(7/29, FRED WALCL)、ECB基准货币€3.96T(7/24周报)、BOJ资产约¥580万亿、PBoC约¥44.2万亿",
        "observedAt": "2026-07-29", "publishedAt": "2026-07-30", "processingVersion": "v1.1", "availability": "partial",
        "analysis": [
            ["水平", "Fed 6.74T 处 10 年 51 分位，QT 后回到中性水平；ECB 继续收缩"],
            ["趋势", "Fed 总资产同比 +0.4% 基本走平，RRP 已降至 $1B 枯竭——流动性边际由紧转稳"],
            ["结构", "美元流动性（Fed）走稳 vs 欧元流动性（ECB）收缩，全球资金再平衡"],
            ["政策含义", "RRP 枯竭意味着银行准备金成为边际约束，QT 接近尾部"],
        ],
        "takeaways": [["全球流动性", "Fed 资产负债表走平、RRP 枯竭，QT 近尾声，流动性从紧缩转向稳定"]],
        "risk": {"level": "low", "label": "全球流动性", "text": "Fed 资产负债表走平、RRP 枯竭，QT 近尾声，流动性从紧转稳"},
    },
    "global|funding-price": {
        "type": "bar", "categories": ["美联储", "欧央行", "日央行", "中国央行"],
        "values": [3.625, 2.25, 1.0, 1.40], "colors": ["#dc2626", "#dc2626", "#dc2626", "#dc2626"], "unit": "%",
        "source": "各央行官网：Fed 3.50-3.75%区间中值(7/30维持)、ECB存款利率2.25%(7/23维持)、BOJ 1.0%(7/31维持)、PBoC 7天逆回购1.40%",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.1", "availability": "available",
        "analysis": [
            ["水平", "四大央行利率 1.0%-3.625%，美联储最高、日央行最低"],
            ["趋势", "ECB 6月已加息、BOJ 6月加息至 31 年高位、BOK 7/16 三年半首次加息——全球重回紧缩周期"],
            ["相对", "Fed 7/30 按兵不动（3 票反对加息）成紧缩阵营中的「孤岛」，政策分化加剧"],
            ["政策路径", "BOJ 暗示 9/10 月或再加息；Fed 加息 vs 降息方向未明，市场定价摇摆"],
        ],
        "takeaways": [["全球紧缩", "欧日韩已先行加息，美联储按兵不动——全球紧缩周期重启但美国滞后"]],
        "risk": {"level": "medium", "label": "全球紧缩", "text": "欧日韩已加息、Fed 3 票反对维持——政策分歧扩大，利率路径不确定"},
    },
    "global|risk-credit": {
        "type": "gauge", "value": 2.87, "unit": "%", "min": 0, "max": 8,
        "name": "全球HY OAS代理", "sections": [[0.35, "#16a34a"], [0.65, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 4.61, "label": "3年高 4.61%"}],
        "source": "ice-bofa（ICE BofA US HY OAS 2.87%, 7/29 FRED；作全球信用代理；3年低2.59%/2025-01）",
        "observedAt": "2026-07-29", "publishedAt": "2026-07-30", "processingVersion": "v1.1", "availability": "partial",
        "analysis": [
            ["水平", "2.87% 处近 3 年 6% 分位，信用定价极度宽松"],
            ["趋势", "从 4.61% 高位回落至 2.67%-2.87%，risk-on 情绪明显修复"],
            ["背离", "信用利差极窄 vs 权益波动率仍高（SKEW 139.9）——股债市场对风险定价分歧"],
            ["逆向", "利差逼近 3 年低位意味着补偿极薄，小冲击易放大波动"],
        ],
        "takeaways": [["信用宽松", "HY OAS 2.87% 处极低分位，风险偏好高但缓冲薄"]],
        "risk": {"level": "high", "label": "全球信用", "text": "HY OAS 2.87% 处 6% 分位，信用缓冲极薄，冲击放大效应强"},
    },
    "global|market-breadth": {
        "type": "gauge", "value": 75, "unit": "%", "min": 0, "max": 100,
        "name": "S&P 500 above 200D MA", "sections": [[0.3, "#dc2626"], [0.55, "#f59e0b"], [1, "#16a34a"]],
        "markers": [{"value": 56, "label": "6月初 56%"}],
        "source": "global-breadth-proxies（Baird Five-for-Friday 7/31报告 S&P 500 ~75% above 200-day MA，作全球权益宽度主要代理；Investing.com S5TH 7/30收68.58%；STOXX 600/日经/MSCI ACWI 宽度公开覆盖不全）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.2", "availability": "partial",
        "analysis": [
            ["水平", "75% above 200D 处健康区间，较 6 月初 56% 显著改善"],
            ["趋势", "从「少数股拉动指数」转向普涨——7 月 AI 回调后小盘/价值补涨"],
            ["结构", "等权跑赢市值加权= 宽度改善；半导体回调但市场未崩 = 韧性信号"],
            ["相对", "这是代理口径：仅覆盖美股，欧亚市场宽度未纳入，跨市场结论需谨慎"],
        ],
        "takeaways": [["市场宽度", "75% 站上 200 日均线，普涨替代龙头独涨，宽度健康"]],
        "risk": {"level": "low", "label": "全球宽度", "text": "75% 站上 200 日均线，宽度健康，普涨替代龙头独涨"},
    },
    "global|institutional-positioning": {
        "type": "gauge", "value": -16.8, "unit": "K contracts", "min": -200, "max": 50,
        "name": "S&P 500 CFTC净投机持仓", "sections": [[0.4, "#dc2626"], [0.6, "#f59e0b"], [1, "#16a34a"]],
        "markers": [{"value": -42.6, "label": "7/8 -42.6K"}],
        "source": "global-positioning-proxies（CFTC COT S&P 500 净投机持仓 -16.8K contracts, 从 -38.9K 改善, CFTC 7/25周五发布, 覆盖截至7/22；作全球权益拥挤度代理；MSCI ACWI/13F合计因口径分散暂未聚合）",
        "observedAt": "2026-07-22", "publishedAt": "2026-07-25", "processingVersion": "v1.2", "availability": "partial",
        "analysis": [
            ["水平", "净投机 -16.8K 仍偏空，但已从 -42.6K 大幅收窄"],
            ["趋势", "连续两周空头回补（-38.9K → -16.8K），机构态度从防御转向中性"],
            ["结构", "7/31 微软财报后 AI 情绪反转，空头加速平仓与指数 +1.7% 形成正反馈"],
            ["逆向", "净持仓仍为负 = 机构尚未全面转多，反弹的机构参与度存疑"],
        ],
        "takeaways": [["机构持仓", "CFTC 净空头大幅回补（-42.6K→-16.8K），机构由防御转中性但仍未转多"]],
        "risk": {"level": "low", "label": "全球机构", "text": "CFTC 净空头回补（-42.6K→-16.8K），机构由防御转中性"},
    },

    # ---- 美国 ----
    "us|growth": {
        "type": "gauge", "value": 1.5, "unit": "%", "min": 0, "max": 6,
        "name": "Q2 实际GDP年化", "sections": [[0.33, "#16a34a"], [0.67, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 2.1, "label": "Q1 2.1%"}],
        "source": "us-bea（U.S. BEA, 二季度实际GDP年化季率初值）", "observedAt": "2026-06-30", "publishedAt": "2026-07-30",
        "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "1.5% 低于 Q1 2.1% 与市场预期（~2.3%），增长动能明显放缓"],
            ["结构", "消费仍有韧性但投资降温；6月非农仅 +57K（预期 110K）验证放缓"],
            ["预期差", "GDP 与 PCE 同时弱于预期，市场开始削减加息押注"],
            ["政策含义", "增长走弱 + 通胀仍高 = 美联储「滞胀式」两难，加息选项仍在桌上"],
        ],
        "takeaways": [["美国增长", "Q2 GDP 1.5% + 非农 57K 双弱于预期，增长放缓验证"]],
        "risk": {"level": "medium", "label": "美国增长", "text": "Q2 GDP 1.5% + 非农 57K 双弱于预期，若 8 月数据续弱则衰退预期升温"},
    },
    "us|inflation": {
        "type": "gauge", "value": 3.5, "unit": "%", "min": 0, "max": 6,
        "name": "6月CPI同比", "sections": [[0.33, "#16a34a"], [0.67, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 2.0, "label": "2%目标"}],
        "source": "us-bls（U.S. BLS, 6月CPI同比3.5%/核心2.6%；PCE 3.7%/核心3.3%）",
        "observedAt": "2026-06-30", "publishedAt": "2026-07-14", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "CPI 3.5% 仍高于 2% 目标，但核心 CPI 2.6% 明显温和"],
            ["趋势", "PCE 从 5月 4.1% → 6月 3.7%（核心 3.4→3.3%），通胀下行通道延续"],
            ["结构", "6月 CPI 环比 -0.4% 转负，能源/商品贡献回落，服务粘性仍在"],
            ["预期差", "6月 CPI 3.5% 低于市场预测 3.8%——利好风险资产的软数据"],
        ],
        "takeaways": [["美国通胀", "CPI/PCE 双双回落且低于预期，通胀下行通道延续但离 2% 仍远"]],
        "risk": {"level": "medium", "label": "美国通胀", "text": "PCE 回落但离 2% 仍远，油价反弹可能打断下行通道"},
    },
    "us|liquidity": {
        "type": "line", "dates": ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06"],
        "values": [4.2, 4.5, 4.8, 5.58, 5.53], "unit": "%",
        "markLines": [{"value": 4.14, "label": "一年前 4.14%"}],
        "source": "us-fred（St. Louis Fed, M2同比, H.6）", "observedAt": "2026-06-30", "publishedAt": "2026-07-28",
        "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "M2 同比 5.53% 显著高于一年前 4.14%，货币环境转松"],
            ["趋势", "从 2月 4.2% 一路回升至 5.5%+，5月见顶后 6月微降，量能仍在扩张区间"],
            ["政策含义", "M2 回升与 Fed 资产负债表走平一致，流动性对资产价格由拖累转支撑"],
        ],
        "takeaways": [["美国流动性", "M2 同比 5.53% 较一年前 +1.4pp，流动性由紧转松"]],
        "risk": {"level": "low", "label": "美国流动性", "text": "M2 同比 5.53% 回升，货币环境由紧转松，支撑资产价格"},
    },
    "us|funding-price": {
        "type": "line", "dates": ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"],
        "values": [4.16, 4.29, 4.36, 4.53, 4.52, 4.65], "unit": "%",
        "markLines": [{"value": 3.625, "label": "FFR中值 3.625%"}],
        "source": "us-treasury（U.S. Treasury 10Y；FFR 3.50-3.75% 7/30 FOMC维持）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "10Y 4.65% 处 19 年高位附近（FOMC 后冲高 5.19%/30Y）"],
            ["趋势", "4.16% → 4.65% 半年上行近 50bp，长端利率持续承压成长估值"],
            ["实际利率", "10Y 4.65% − breakeven ~2.2% = 实际利率 ~2.4%，处历史偏高水平"],
            ["政策含义", "市场曾定价 9 月加息 70%，GDP/PCE 弱于预期后回落——利率路径高度不确定"],
        ],
        "takeaways": [["美国资金价格", "10Y 4.65% 半年 +50bp，长端利率高位压制估值"]],
        "risk": {"level": "medium", "label": "美国资金价格", "text": "10Y 4.65% 半年 +50bp 处 19 年高位，实际利率 ~2.4% 压制估值"},
    },
    "us|risk-credit": {
        "type": "gauge", "value": 17.09, "unit": "", "min": 0, "max": 40,
        "name": "VIX（7/31 -17.28%）", "sections": [[0.5, "#16a34a"], [0.75, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 20, "label": "警戒 20"}, {"value": 35.3, "label": "年内高 35.3"}],
        "source": "us-cboe（CBOE VIX；SKEW 139.9；equity put/call 0.887；HY OAS 268bps 6%分位）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "VIX 17.09 处中低位，情绪平稳"],
            ["趋势", "单日 -17.28%（35.3 → 17），AI 恐慌一周内基本出清"],
            ["尾部", "SKEW 139.9 仍远高于中性区（100-120），尾部对冲需求高企——表面平静下有防备"],
            ["信用", "HY OAS 268bps 6% 分位极宽松，与 SKEW 高企构成「信用松、尾部防」的分歧"],
        ],
        "takeaways": [["美国风险偏好", "VIX 17 情绪修复，但 SKEW 139.9 高企——表面平静、尾部防备"]],
        "risk": {"level": "medium", "label": "美国风险偏好", "text": "SKEW 139.9 高企：VIX 17 表面平静但尾部对冲需求仍在（买保险信号）"},
    },
    "us|market-breadth": {
        "type": "bar", "categories": ["道指", "标普500", "纳指"],
        "values": [1.2, 1.7, 2.8], "colors": ["#dc2626", "#dc2626", "#dc2626"], "unit": "%",
        "source": "us-barchart（主要指数7/31涨跌幅；标普500仍低于50日均线0.42%，部分覆盖）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "partial",
        "analysis": [
            ["结构", "7/31 三大指数齐涨（道1.2/标1.7/纳2.8），普涨而非独涨"],
            ["趋势", "纳指 6 连跌后终结、费半单日 +8.2%——AI 主线的超跌反弹"],
            ["相对", "标普 500 仍低于 50 日均线 0.42%，指数在均线附近拉锯"],
            ["局限", "仅覆盖指数涨跌，个股级宽度（%above MA）需 Barchart 付费口径"],
        ],
        "takeaways": [["美国宽度", "三大指数齐涨普涨，纳指终结 6 连跌，AI 超跌反弹"]],
        "risk": {"level": "low", "label": "美国宽度", "text": "三大指数齐涨、纳指终结 6 连跌，普涨结构健康"},
    },
    "us|institutional-positioning": {
        "type": "gauge", "value": 19.69, "unit": "x", "min": 10, "max": 30,
        "name": "标普500远期PE", "sections": [[0.33, "#16a34a"], [0.67, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 19.85, "label": "10年均值 19.85"}],
        "source": "us-factset（FactSet via TrendOnify, 远期PE 19.69, 10年47.5分位）",
        "observedAt": "2026-07-30", "publishedAt": "2026-07-30", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "远期 PE 19.69 处 10 年 47.5 分位，估值中性不贵不便宜"],
            ["趋势", "从 22.6x（2025-08）回落至 19.69，估值消化 + 盈利上修共同作用"],
            ["结构", "科技/半导体 PE 偏高（28x vs 均值 20x），集中度风险（前 5 权重 ~22%）仍在"],
            ["拥挤度", "估值中性 + 持仓集中 = 系统性不贵，但结构性拥挤（AI 权重）"],
        ],
        "takeaways": [["美国机构持仓", "远期 PE 19.69 中性，但 AI 权重集中度仍在高位"]],
        "risk": {"level": "medium", "label": "美国机构持仓", "text": "远期 PE 19.69 中性，但 AI 权重集中（前 5 权重 ~22%）结构性拥挤"},
    },

    # ---- 中国 ----
    "cn|growth": {
        "type": "gauge", "value": 4.3, "unit": "%", "min": 0, "max": 8,
        "name": "Q2 GDP同比", "sections": [[0.25, "#16a34a"], [0.5, "#f59e0b"], [0.75, "#dc2626"]],
        "markers": [{"value": 5.0, "label": "Q1 5.0%"}],
        "source": "cn-nbs（国家统计局, 二季度GDP同比4.3%/上半年4.7%）",
        "observedAt": "2026-06-30", "publishedAt": "2026-07-15", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "Q2 GDP 4.3% 低于 Q1 5.0%，处全年目标（~5%）下方"],
            ["趋势", "上半年 4.7%，环比 Q2 +0.9%——增速放缓但未失速"],
            ["结构", "第三产业 5.1% 好于第二产业 3.0%，服务业贡献 69.4%；地产 -0.2% 拖累"],
            ["领先", "7月制造业 PMI 49.2 跌破荣枯线（6月 50.3）——增长动能转弱信号"],
        ],
        "takeaways": [["中国增长", "Q2 GDP 4.3% 放缓 + 7月 PMI 49.2 跌破荣枯线，稳增长压力上升"]],
        "risk": {"level": "high", "label": "中国增长", "text": "Q2 GDP 4.3% 放缓 + 7月 PMI 49.2 跌破荣枯线，稳增长压力上升"},
    },
    "cn|inflation": {
        "type": "line", "dates": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"],
        "values": [0.2, 1.3, 1.0, 1.2, 1.2, 1.0], "unit": "%",
        "markLines": [{"value": 2.0, "label": "目标 ~2%"}],
        "source": "cn-nbs（国家统计局, CPI同比：6月1.0%/核心1.0%；PPI 6月4.1%）",
        "observedAt": "2026-06-30", "publishedAt": "2026-07-09", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "CPI 1.0% 处温和区间，远低于 2% 目标——内需偏弱的价格映射"],
            ["结构", "PPI 4.1% vs CPI 1.0% = PPI-CPI 剪刀差 3pp，上游涨价未传导到消费端"],
            ["趋势", "CPI 上半年 1.0% 温和回升后走平，核心 CPI 1.0% 显示需求复苏力度有限"],
            ["政策含义", "低通胀给宽松政策留出空间，但 PPI 高位挤压中下游利润"],
        ],
        "takeaways": [["中国通胀", "CPI 1.0% 低通胀、PPI 4.1% 剪刀差 3pp，上游挤压下游"]],
        "risk": {"level": "low", "label": "中国通胀", "text": "CPI 1.0% 温和、PPI 4.1% 剪刀差 3pp，上游挤压下游利润"},
    },
    "cn|liquidity": {
        "type": "line", "dates": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"],
        "values": [9.0, 9.0, 8.5, 8.6, 8.6, 8.0], "unit": "%",
        "markLines": [{"value": 8.0, "label": "6月 8.0%"}],
        "source": "cn-pbc（中国人民银行, M2同比8.0%/M1 118.5万亿；社融-M2剪刀差-0.6%）",
        "observedAt": "2026-06-30", "publishedAt": "2026-07-15", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "M2 同比 8.0% 处宽松区间，但社融-M2 剪刀差 -0.6% 仍为负"],
            ["趋势", "从 9.0% 缓降至 8.0%，货币供应温和收敛"],
            ["结构", "M1 增速慢于 M2 = 资金活化不足，企业短期活钱仍少——「宽货币、弱活化」"],
            ["政策含义", "剪刀差为负指向需求侧偏弱，政策或需继续加力宽信用"],
        ],
        "takeaways": [["中国流动性", "M2 8.0% 宽松但 M1 活化不足、社融-M2 剪刀差 -0.6%，宽货币未传导到实体"]],
        "risk": {"level": "medium", "label": "中国流动性", "text": "M2 8.0% 宽松但 M1 活化不足、社融-M2 剪刀差 -0.6%，宽货币未传导实体"},
    },
    "cn|funding-price": {
        "type": "line", "dates": ["07-27", "07-28", "07-29", "07-30", "07-31"],
        "values": [1.734, 1.735, 1.733, 1.720, 1.714], "unit": "%",
        "markLines": [{"value": 1.714, "label": "7/31 1.714%"}],
        "source": "cn-chinabond（中国债券信息网, 中债国债10Y日收益率）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "10Y 1.714% 处历史极低位，债市定价深度宽松预期"],
            ["趋势", "一周内 1.735 → 1.714 持续下行，配置盘需求旺盛"],
            ["相对", "中美 10Y 利差倒挂 ~2.9pp（4.65% vs 1.71%），人民币汇率承压"],
            ["政策含义", "低利率支撑宽财政，但也压缩了货币政策进一步宽松的边际空间"],
        ],
        "takeaways": [["中国资金价格", "10Y 1.714% 历史低位，中美利差倒挂 2.9pp"]],
        "risk": {"level": "medium", "label": "中国资金价格", "text": "10Y 1.714% 历史低位 + 中美利差倒挂 2.9pp，汇率承压"},
    },
    "cn|risk-credit": {
        "type": "gauge", "value": 84, "unit": "%", "min": 0, "max": 100,
        "name": "A股上涨家数占比", "sections": [[0.3, "#dc2626"], [0.55, "#f59e0b"], [1, "#16a34a"]],
        "markers": [{"value": 50, "label": "涨跌平衡"}],
        "source": "cn-akshare-breadth（AkShare, 7/31上涨4691家/涨停103/跌停0；成交2.54万亿）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "上涨占比 84%，为过去一年 16% 时间才出现的高热度区间"],
            ["结构", "涨停 103 家 vs 跌停 0 家，赚钱效应极强；成交 2.54 万亿放量 1991 亿"],
            ["趋势", "半导体/算力超跌反弹主导，与日韩芯片股共振"],
            ["逆向", "情绪指标触及高位，短期波动易放大"],
        ],
        "takeaways": [["A股风险偏好", "上涨占比 84% + 涨停 103/跌停 0 + 成交 2.54 万亿，情绪高热"]],
        "risk": {"level": "medium", "label": "A股情绪", "text": "上涨占比 84% 触及历史高热度区间，情绪指标过热易放大波动"},
    },
    "cn|market-breadth": {
        "type": "bar", "categories": ["上涨", "下跌", "平盘", "停牌"],
        "values": [4691, 728, 115, 6], "colors": ["#dc2626", "#16a34a", "#94a3b8", "#cbd5e1"], "unit": "家",
        "source": "cn-akshare-index-sector（AkShare, 7/31收盘；上涨占比84%，情绪高）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["结构", "涨 4691 : 跌 728 = 6.4:1 极端偏多，普涨行情"],
            ["板块", "小盘跑赢大盘、成长跑赢价值；传媒/机器人/AI 领涨，油气/白酒垫底"],
            ["趋势", "7 月科技主线去化后进入底部区间，超跌反弹主导宽度修复"],
        ],
        "takeaways": [["A股宽度", "涨跌比 6.4:1 极端普涨，小盘成长领跑"]],
        "risk": {"level": "low", "label": "A股宽度", "text": "涨跌比 6.4:1 极端普涨，小盘成长领跑，结构健康但拥挤"},
    },
    "cn|institutional-positioning": {
        "type": "gauge", "value": 25763, "unit": "亿元", "min": 0, "max": 40000,
        "name": "两市融资余额", "sections": [[0.5, "#16a34a"], [0.75, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 26065, "label": "7/30 26065亿（隔日）"}],
        "source": "cn-sse-szse（沪深交易所, 融资余额25763亿, 7/30环比-366.6亿）",
        "observedAt": "2026-07-30", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "两融 25763 亿处历史高位区（历史第 130 位），杠杆资金活跃"],
            ["趋势", "单日 -366.6 亿显著去化，与 7/31 指数大涨形成「减杠杆 + 上涨」的背离"],
            ["结构", "ETF 净申购 137.66 亿，沪深300 ETF 连续 5 日净申购——被动资金替代融资盘"],
            ["逆向", "融资余额下跌 + 指数上涨 = 反弹由被动/长线资金驱动而非杠杆，持续性或更好"],
        ],
        "takeaways": [["A股机构持仓", "两融 25763 亿高位单日 -367 亿去化，ETF 净申购接棒，杠杆资金谨慎"]],
        "risk": {"level": "medium", "label": "A股机构持仓", "text": "两融高位单日 -367 亿去化 + ETF 接棒：杠杆撤、被动资金进，反弹质量待验证"},
    },

    # ---- 韩国 ----
    "kr|growth": {
        "type": "gauge", "value": 3.0, "unit": "%", "min": 0, "max": 6,
        "name": "2026 GDP增速预测", "sections": [[0.33, "#16a34a"], [0.67, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 2.0, "label": "原预测 2.0%"}],
        "source": "kr-moef（韩国企划财政部, 2026 GDP预测上调至3.0%, 7/14）",
        "observedAt": "2026-07-14", "publishedAt": "2026-07-14", "processingVersion": "v1.0", "availability": "partial",
        "analysis": [
            ["水平", "2026 GDP 预测 3.0%，政府从 2.0% 大幅上调 1pp"],
            ["趋势", "半导体出口强劲 + Q1 增速创近 6 年最快，经济过热迹象显现"],
            ["结构", "增长主要由出口/投资驱动，内需消费相对偏弱"],
            ["政策含义", "高增长是 BOK 敢于加息的底气——「经济过热 + 通胀超标」组合"],
        ],
        "takeaways": [["韩国增长", "GDP 预测上调至 3.0%，半导体周期驱动、经济过热"]],
        "risk": {"level": "medium", "label": "韩国增长", "text": "GDP 预测上调至 3.0% 但过热：增长与通胀目标冲突，政策被迫紧缩"},
    },
    "kr|inflation": {
        "type": "gauge", "value": 3.2, "unit": "%", "min": 0, "max": 6,
        "name": "6月CPI同比", "sections": [[0.33, "#16a34a"], [0.67, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 2.0, "label": "2%目标"}],
        "source": "kr-ecos（Bank of Korea ECOS, 6月CPI同比3.2%创30个月新高；核心2.5%）",
        "observedAt": "2026-06-30", "publishedAt": "2026-07-02", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "CPI 3.2% 创 30 个月新高，连续 4 个月超 2% 目标"],
            ["结构", "核心 2.5% 温和，主因能源（汽油+23%/柴油+34%）与韩元贬值输入型通胀"],
            ["趋势", "5 月起突破 3% 持续高位，下半年或维持 ~3%"],
            ["政策含义", "通胀超标是 BOK 7/16 加息 25bp 的直接导火索"],
        ],
        "takeaways": [["韩国通胀", "CPI 3.2% 连续 4 个月超目标，能源+汇率输入型通胀"]],
        "risk": {"level": "high", "label": "韩国通胀", "text": "CPI 3.2% 连续 4 个月超 2% 目标，能源+韩元贬值输入型通胀未缓解"},
    },
    "kr|liquidity": {
        "type": "line", "dates": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
        "values": [5.9, 6.3, 6.8, 7.1, 11.7], "unit": "%",
        "markLines": [{"value": 11.7, "label": "5月 old M2 同比"}],
        "source": "kr-ecos（BOK, 5月M2 4,184.4万亿韩元环比+0.8%；old M2(含ETF)同比+11.7% 2022/2来新高, 7/15发布）",
        "observedAt": "2026-05-31", "publishedAt": "2026-07-15", "processingVersion": "v1.1", "availability": "available",
        "analysis": [
            ["水平", "M2 4,184.4 万亿韩元，环比 +0.8% 创 9 个月最大增幅"],
            ["趋势", "old M2（含 ETF）同比 +11.7%，2022/2 以来新高——资金大幅流向股市"],
            ["结构", "企业（半导体）资金流入 MMF/存款 +30.1 万亿，居民减持存款转投股票 -19 万亿"],
            ["政策含义", "流动性宽松 + 股市过热，强化 BOK 紧缩必要性"],
        ],
        "takeaways": [["韩国流动性", "M2 环比 +0.8% 创 9 个月最大，old M2 同比 11.7% 新高，资金涌向股市"]],
        "risk": {"level": "medium", "label": "韩国流动性", "text": "M2 环比 +0.8% 创 9 个月最大、old M2 同比 11.7% 新高，资金涌向股市助涨波动"},
    },
    "kr|funding-price": {
        "type": "gauge", "value": 2.75, "unit": "%", "min": 0, "max": 6,
        "name": "BOK基准利率", "sections": [[0.5, "#16a34a"], [0.75, "#f59e0b"], [1, "#dc2626"]],
        "markers": [{"value": 2.5, "label": "加息前 2.50%"}],
        "source": "kr-ecos（BOK, 7/16加息25bp至2.75%, 2023年1月来首次；韩3Y国债3.848%）",
        "observedAt": "2026-07-16", "publishedAt": "2026-07-16", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "基准利率 2.75%，7/16 加息 25bp（2023/1 来首次加息）"],
            ["趋势", "结束 8 次按兵不动，进入渐进紧缩周期，市场预期 8 或 10 月再加 25bp"],
            ["相对", "韩元年内贬值超 4%，美韩利差驱动资本外流压力——加息含稳汇率意图"],
            ["政策含义", "控通胀 + 稳汇率 + 抑楼市三重目标下被迫紧缩"],
        ],
        "takeaways": [["韩国资金价格", "BOK 3 年半首次加息至 2.75%，开启紧缩周期"]],
        "risk": {"level": "medium", "label": "韩国资金价格", "text": "BOK 3 年半首次加息至 2.75%，市场预期 8/10 月再加息，紧缩周期开启"},
    },
    "kr|risk-credit": {
        "type": "gauge", "value": 17.91, "unit": "%", "min": -25, "max": 25,
        "name": "KOSPI单日涨跌", "sections": [[0.5, "#16a34a"], [0.5, "#f59e0b"]],
        "markers": [{"value": 0, "label": "0%"}],
        "source": "kr-krx（Korea Exchange, KOSPI 7/31收6595.45, 单日+17.91%历史最大涨幅）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "available",
        "analysis": [
            ["水平", "KOSPI 7/31 单日 +17.91% 至 6595.45，创历史最大单日涨幅"],
            ["趋势", "前 3 日跌超 17% 后暴力反转，微软财报缓解 AI 支出担忧触发芯片股回补"],
            ["结构", "SK 海力士 +17.5%、三星 +19%，存储链主导；外资净流入 2.32 万亿韩元推升"],
            ["波动", "单日 ±17% 级别的极端波动，显示市场在 AI 叙事与恐慌间剧烈摇摆"],
        ],
        "takeaways": [["韩国风险偏好", "KOSPI 单日 +17.91% 历史最大涨幅，AI 恐慌与修复剧烈切换"]],
        "risk": {"level": "high", "label": "韩股波动", "text": "KOSPI 单日 ±17.91% 历史级极端波动，市场失去理性定价能力"},
    },
    "kr|market-breadth": {
        "type": "bar", "categories": ["KOSPI", "日经225"],
        "values": [17.91, 4.03], "colors": ["#dc2626", "#dc2626"], "unit": "%",
        "source": "kr-krx（7/31日韩指数涨幅；KOSDAQ 791.84(7/16), 部分覆盖）",
        "observedAt": "2026-07-31", "publishedAt": "2026-07-31", "processingVersion": "v1.0", "availability": "partial",
        "analysis": [
            ["结构", "7/31 日韩共振反弹：KOSPI +17.91%、日经 +4.03%，亚太芯片链同步修复"],
            ["趋势", "KOSDAQ 7/16 收 791.84 后随主板巨震，小盘弹性更大"],
            ["局限", "仅覆盖指数级涨幅，个股涨跌家数分布未纳入（KRX 无免费明细）"],
        ],
        "takeaways": [["韩国宽度", "KOSPI/日经共振反弹，亚太芯片链同步修复"]],
        "risk": {"level": "medium", "label": "韩日宽度", "text": "KOSPI +17.91% / 日经 +4.03% 共振暴涨，情绪极端修复后回摆风险大"},
    },
    "kr|institutional-positioning": {
        "type": "bar", "categories": ["外资", "机构", "散户"],
        "values": [5959, 16480, -21647], "colors": ["#dc2626", "#dc2626", "#16a34a"], "unit": "亿韩元",
        "source": "kr-krx（7/21外资净流入5,959亿韩元、机构净流入1.65万亿、散户净流出2.16万亿；7/15外资曾净流入2.32万亿）",
        "observedAt": "2026-07-21", "publishedAt": "2026-07-21", "processingVersion": "v1.1", "availability": "partial",
        "analysis": [
            ["结构", "7/21 外资净流入 5,959 亿 + 机构净流入 1.65 万亿 vs 散户净流出 2.16 万亿"],
            ["趋势", "外资连续两日净流入（7/15 曾单日 2.32 万亿），从 7 月大跌抛售转向回流"],
            ["相对", "韩元 7/21 走强至 1474（最强 5/11 以来），外资流入 + 汇率升值互相印证"],
            ["局限", "仅覆盖单日流向，月度持仓总量（FSS）滞后约 2 周未纳入"],
        ],
        "takeaways": [["韩国外资", "外资/机构连续净流入、散户净流出，外资回流与韩元走强共振"]],
        "risk": {"level": "low", "label": "韩国外资", "text": "外资/机构连续净流入、散户净流出，外资回流与韩元走强共振"},
    },
}

# ============ 覆盖矩阵 ============
DIMS = ["growth", "inflation", "liquidity", "funding-price", "risk-credit", "market-breadth", "institutional-positioning"]
MARKETS = ["global", "us", "cn", "kr"]
MKT_LABEL = {"global": "全球", "us": "美国", "cn": "中国", "kr": "韩国"}
DIM_LABEL = {"growth": "增长", "inflation": "通胀", "liquidity": "流动性", "funding-price": "资金价格",
             "risk-credit": "风险偏好与信用", "market-breadth": "市场宽度", "institutional-positioning": "机构持仓与拥挤度"}
EXPECTED_KEYS = {f"{market}|{dimension}" for market in MARKETS for dimension in DIMS}
AVAILABILITIES = {"available", "partial", "unknown", "failed", "pending_review", "incomplete_reconstruction"}
FORBIDDEN_TERMS = ("买入", "卖出", "建议买", "建议卖", "目标价", "目标仓位", "牛熊分数", "总分", "确定牛", "确定熊", "必然涨", "必然跌")
# 板块倾向建议层（可选）：由 load_records 从 cells JSON 顶层 sectorAdvice 拆出
SECTOR_ADVICE = {}
SECTOR_STANCE_CLS = {"关注": "st-up", "中性": "st-mid", "回避": "st-down"}


def parse_date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是 YYYY-MM-DD：{value!r}") from exc


def parse_args():
    parser = argparse.ArgumentParser(description="生成按发布日期截止筛选的资本环境快照 HTML")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="回放截止日（YYYY-MM-DD，默认今天）")
    parser.add_argument("--cells", type=Path, help="可选 JSON 输入；每个  market|dimension 可为单条记录或按发布日期排序的记录数组")
    parser.add_argument("--out", type=Path, help="HTML 输出路径（默认 research/capital-environment/ 下按日期命名）")
    parser.add_argument("--check", action="store_true", help="只验证输入和点时选择，不写 HTML")
    return parser.parse_args()


def load_records(path):
    """读取 cells JSON。支持两种顶层结构：
    1) 28 个 market|dimension 键（原有）；
    2) 含 "cells" 与/或 "sectorAdvice" 的包装对象。
    sectorAdvice（板块倾向建议层）会被拆出存到全局 SECTOR_ADVICE，不参与 28 格校验。"""
    global SECTOR_ADVICE
    if path is None:
        return CELLS
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 cells JSON：{path}") from exc
    if isinstance(payload, dict) and "sectorAdvice" in payload:
        SECTOR_ADVICE = payload.get("sectorAdvice") or {}
    if isinstance(payload, dict) and "cells" in payload:
        records = payload["cells"]
    elif isinstance(payload, dict):
        records = {k: v for k, v in payload.items() if k != "sectorAdvice"}
    else:
        records = None
    if not isinstance(records, dict):
        raise ValueError("cells JSON 必须是对象，或包含对象字段 cells")
    return records


def unknown_cell(as_of):
    return {
        "type": "unknown",
        "availability": "unknown",
        "reason": f"截至 {as_of} 无已发布的可验证数据",
    }


def select_cells(records, as_of):
    missing = EXPECTED_KEYS - records.keys()
    extra = records.keys() - EXPECTED_KEYS
    if missing or extra:
        detail = []
        if missing:
            detail.append("缺少 " + ", ".join(sorted(missing)))
        if extra:
            detail.append("未知键 " + ", ".join(sorted(extra)))
        raise ValueError("cells 必须恰好包含 4×7 网格：" + "；".join(detail))

    selected = {}
    for key in sorted(EXPECTED_KEYS):
        candidates = records[key]
        if isinstance(candidates, dict):
            candidates = [candidates]
        if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
            raise ValueError(f"{key} 必须是记录对象或记录对象数组")
        eligible = [item for item in candidates if item.get("publishedAt") and parse_date(item["publishedAt"], f"{key}.publishedAt") <= as_of]
        selected[key] = max(eligible, key=lambda item: item["publishedAt"]) if eligible else unknown_cell(as_of)
    return selected


def validate_record_catalog(records):
    """在筛选前拒绝坏记录，避免 malformed 的未来记录被悄悄当成未知。"""
    missing = EXPECTED_KEYS - records.keys()
    extra = records.keys() - EXPECTED_KEYS
    if missing or extra:
        detail = []
        if missing:
            detail.append("缺少 " + ", ".join(sorted(missing)))
        if extra:
            detail.append("未知键 " + ", ".join(sorted(extra)))
        raise ValueError("cells 必须恰好包含 4×7 网格：" + "；".join(detail))
    for key, records_for_key in records.items():
        candidates = [records_for_key] if isinstance(records_for_key, dict) else records_for_key
        if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
            raise ValueError(f"{key} 必须是记录对象或记录对象数组")
        for cfg in candidates:
            availability = cfg.get("availability")
            if availability not in AVAILABILITIES:
                raise ValueError(f"{key}.availability 非法：{availability!r}")
            if availability in {"available", "partial", "pending_review"}:
                required = ("source", "observedAt", "publishedAt", "processingVersion")
                absent = [field for field in required if not cfg.get(field)]
                if absent:
                    raise ValueError(f"{key} 有值却缺少证据字段：{', '.join(absent)}")
                if not has_observable_value(cfg):
                    raise ValueError(f"{key} 标为 {availability} 却没有非零观测值")
            if cfg.get("publishedAt"):
                parse_date(cfg["publishedAt"], f"{key}.publishedAt")


def has_observable_value(cfg):
    if "value" in cfg:
        return cfg["value"] not in (None, 0)
    values = cfg.get("values")
    return isinstance(values, list) and any(value not in (None, 0) for value in values)


def validate_cells(cells, as_of):
    for key, cfg in cells.items():
        availability = cfg.get("availability")
        if availability not in AVAILABILITIES:
            raise ValueError(f"{key}.availability 非法：{availability!r}")
        if availability in {"available", "partial", "pending_review"}:
            required = ("source", "observedAt", "publishedAt", "processingVersion")
            absent = [field for field in required if not cfg.get(field)]
            if absent:
                raise ValueError(f"{key} 有值却缺少证据字段：{', '.join(absent)}")
            if not has_observable_value(cfg):
                raise ValueError(f"{key} 标为 {availability} 却没有非零观测值")
        published_at = cfg.get("publishedAt")
        if published_at and parse_date(published_at, f"{key}.publishedAt") > as_of:
            raise ValueError(f"{key} 引入了晚于回放日的数据：{published_at} > {as_of}")


ARGS = parse_args()
AS_OF_DATE = parse_date(ARGS.as_of, "--as-of")
AS_OF = AS_OF_DATE.isoformat()
YESTERDAY = (AS_OF_DATE - timedelta(days=1)).isoformat()
LAST_WEEK = (AS_OF_DATE - timedelta(days=7)).isoformat()
RECORD_CATALOG = load_records(ARGS.cells)
validate_record_catalog(RECORD_CATALOG)
CELLS = select_cells(RECORD_CATALOG, AS_OF_DATE)
validate_cells(CELLS, AS_OF_DATE)

def avail_class(a):
    return {"available": "a", "partial": "p", "unknown": "u", "failed": "u",
            "incomplete_reconstruction": "u", "pending_review": "p"}.get(a, "u")

def avail_label(a):
    return {"available": "可得", "partial": "部分", "unknown": "未知", "failed": "失败",
            "incomplete_reconstruction": "无法还原", "pending_review": "待复核"}.get(a, "未知")

def avail_badge_class(a):
    return {"available": "badge-up", "partial": "badge-mid", "unknown": "badge-down", "failed": "badge-down",
            "incomplete_reconstruction": "badge-down", "pending_review": "badge-muted"}.get(a, "badge-muted")

def mkt_aggregate(market):
    """市场级聚合：全available=available；有值格(available/partial)=partial；含待复核=pending_review；全未知=unknown"""
    avails = [CELLS[f"{market}|{d}"]["availability"] for d in DIMS]
    if all(a == "available" for a in avails):
        return "available"
    if any(a in ("available", "partial") for a in avails):
        return "partial"
    if any(a == "pending_review" for a in avails):
        return "pending_review"
    return "unknown"

# ============ 生成矩阵 HTML ============
matrix_rows = []
for m in MARKETS:
    row = [f'<div class="matrix-cell lbl">{MKT_LABEL[m]}</div>']
    for d in DIMS:
        c = CELLS[f"{m}|{d}"]["availability"]
        row.append(f'<div class="matrix-cell {avail_class(c)}">{"●" if m != "global" else "▲"}</div>')
    matrix_rows.append("\n    ".join(row))

# ============ 生成市场 section HTML ============
def risk_badge(cfg):
    """风险徽章：高=红点/中=橙点/低=绿点"""
    r = cfg.get("risk")
    if not r:
        return ""
    lvl = r.get("level")
    cls = {"high": "rk-high", "medium": "rk-medium", "low": "rk-low"}.get(lvl, "rk-low")
    title = {"high": "高风险", "medium": "需验证", "low": "缓解"}.get(lvl, "")
    return f'<span class="risk-dot {cls}" title="{title}"></span>'

def cell_html(m, d):
    cfg = CELLS[f"{m}|{d}"]
    a = cfg["availability"]
    # AI 分析摘要（透镜式）：analysis 数组，每项 [透镜名, 一句话]
    analysis_html = ""
    if cfg.get("analysis"):
        items = "".join(
            f'<li><span class="an-lens">{lens}</span><span class="an-txt">{txt}</span></li>'
            for lens, txt in cfg["analysis"]
        )
        analysis_html = (f'<div class="cell-analysis"><div class="an-head">AI 分析</div>'
                         f'<ul class="an-list">{items}</ul></div>')
    return (f'<div class="cell" data-key="{m}|{d}">'
            f'<div class="cell-head"><span class="cell-name">{DIM_LABEL[d]}{risk_badge(cfg)}</span>'
            f'<span class="badge {avail_badge_class(a)}">{avail_label(a)}</span></div>'
            f'<div class="chart-box" id="ch-{m}-{d}"></div>'
            f'{analysis_html}'
            f'<div class="cell-evidence" id="ev-{m}-{d}"></div></div>')

sections = []
for m in MARKETS:
    agg = mkt_aggregate(m)
    cells = "\n".join("        " + cell_html(m, d) for d in DIMS)
    sections.append(
        f'<section class="market" aria-label="{MKT_LABEL[m]}资本环境">\n'
        f'  <div class="market-head"><h2>{MKT_LABEL[m]}</h2>'
        f'<span class="badge {avail_badge_class(agg)}">{avail_label(agg)}</span></div>\n'
        f'  <div class="market-grid">\n{cells}\n  </div>\n</section>')

# ============ overview ============
mkts_ok = [m for m in MARKETS if mkt_aggregate(m) in ("available", "partial")]
covered_cells = sum(cfg["availability"] in ("available", "partial") for cfg in CELLS.values())
ALL_UNKNOWN = len(mkts_ok) == 0
if len(mkts_ok) == 0:
    overview = f"截至 {AS_OF} 的资本环境：无可得数据。"
elif covered_cells == len(EXPECTED_KEYS):
    overview = f"截至 {AS_OF} 的资本环境：完全覆盖。以下为各市场维度的可观测状态，区分已观测事实与未知。"
else:
    overview = (f"截至 {AS_OF} 的资本环境：部分覆盖，{len(mkts_ok)}/{len(MARKETS)} 市场、{covered_cells}/{len(EXPECTED_KEYS)} 格有可得数据。"
                f"以下为各市场维度的可观测状态，区分已观测事实与未知。")
DISCLAIMER = "以上为证据约束下的环境解释与研究辅助，不代表未来收益、因果关系或投资建议。"

# AI 综合研判（跨格交叉验证）：从 CELLS 的 takeaways（一句话）+ risk（风险信号）汇总
# risk 字段格式：{"level": "high"|"medium"|"low", "text": "风险描述", "evidence": "证据格子"}
AI_TAKEAWAYS = []      # [标签, 一句话] 用于交叉验证
RISK_HIGH = []         # (标签, 描述) 高优先级风险
RISK_MEDIUM = []       # (标签, 描述) 需验证信号
RISK_LOW = []          # (标签, 描述) 缓解因素
for key, cfg in CELLS.items():
    for tag, txt in (cfg.get("takeaways") or []):
        AI_TAKEAWAYS.append((tag, txt))
    r = cfg.get("risk")
    if r:
        entry = (r.get("label") or key.split("|")[0], r["text"])
        if r.get("level") == "high":
            RISK_HIGH.append(entry)
        elif r.get("level") == "medium":
            RISK_MEDIUM.append(entry)
        else:
            RISK_LOW.append(entry)


def limited(items, limit):
    """保留稳定顺序，避免同一条证据在顶部重复占位。"""
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
        if len(result) == limit:
            break
    return result


def takeaway_html():
    if ALL_UNKNOWN or not AI_TAKEAWAYS:
        return ""
    top_takeaways = limited(AI_TAKEAWAYS, 8)
    items = "".join(
        f'<div class="tw-item"><span class="tw-tag">{tag}</span><span class="tw-txt">{txt}</span></div>'
        for tag, txt in top_takeaways
    )
    def risk_block(title, entries, cls):
        if not entries:
            return ""
        rows = "".join(
            f'<div class="tw-item"><span class="tw-tag">{tag}</span><span class="tw-txt">{txt}</span></div>'
            for tag, txt in entries
        )
        return f'<div class="risk-section {cls}"><div class="risk-title">{title}</div><div class="tw-list">{rows}</div></div>'
    risk_html = (risk_block("高优先级风险", limited(RISK_HIGH, 3), "risk-high")
                 + risk_block("需验证信号", limited(RISK_MEDIUM, 3), "risk-medium")
                 + risk_block("缓解因素", limited(RISK_LOW, 2), "risk-low"))
    return (f'<div class="takeaway-box">'
            f'<div class="tw-head">AI 综合研判 · 跨格交叉验证</div>'
            f'<div class="tw-list">{items}</div></div>'
            f'<div class="risk-box">'
            f'<div class="tw-head">风险信号清单 · 投资视角</div>'
            f'{risk_html}</div>')


def sector_advice_html():
    """板块倾向建议层（可选）：用户要求投资/板块建议时，从 cells JSON 顶层 sectorAdvice 渲染。
    约束：仅板块/主题粒度；倾向只用 关注/中性/回避；每条必须带证据来源 + 证伪条件；卡头固定免责声明。"""
    if not SECTOR_ADVICE or not SECTOR_ADVICE.get("markets"):
        return ""
    disclaimer = (SECTOR_ADVICE.get("disclaimer")
                  or "以下为基于资本环境证据的板块方向性研究参考，仅为建议，不构成投资建议或买卖指令，不保证未来表现。")
    market_blocks = []
    for mkt in SECTOR_ADVICE.get("markets", []):
        rows = []
        for it in mkt.get("items", []):
            stance = it.get("stance", "中性")
            cls = SECTOR_STANCE_CLS.get(stance, "st-mid")
            rows.append(
                '<div class="sa-item">'
                f'<span class="sa-stance {cls}">{stance}</span>'
                f'<span class="sa-sector">{it.get("sector", "")}</span>'
                f'<div class="sa-ev"><b>证据：</b>{it.get("evidence", "")}</div>'
                f'<div class="sa-tr"><b>证伪条件：</b>{it.get("trigger", "")}</div>'
                '</div>'
            )
        mkt_name = mkt.get("market", "")
        mkt_date = f'<span class="sa-mkt-date">{mkt.get("date", "")}</span>' if mkt.get("date") else ""
        market_blocks.append(
            f'<div class="sa-mkt"><div class="sa-mkt-name">{mkt_name}</div>{mkt_date}'
            f'<div class="sa-list">{"".join(rows)}</div></div>'
        )
    return (f'<div class="sector-advice-box">'
            f'<div class="tw-head">板块倾向建议 · 研究参考（仅建议）</div>'
            f'<p class="sa-disclaimer">{disclaimer}</p>'
            f'{"".join(market_blocks)}</div>')


MATRIX_ROWS_HTML = "\n".join("    " + row for row in matrix_rows)
SECTIONS_HTML = "\n\n".join(sections)

if ALL_UNKNOWN:
    DASHBOARD_CONTENT = ('<div class="empty-state">该日期无可得的资本环境数据。'
                         '请选择一个有可靠数据的日期。</div>')
else:
    DASHBOARD_CONTENT = (f'<div class="matrix-wrap">\n'
                         f'  <div class="matrix-cell lbl">市场/维度</div>\n'
                         f'  <div class="matrix-cell lbl">增长</div>\n'
                         f'  <div class="matrix-cell lbl">通胀</div>\n'
                         f'  <div class="matrix-cell lbl">流动性</div>\n'
                         f'  <div class="matrix-cell lbl">资金价格</div>\n'
                         f'  <div class="matrix-cell lbl">风险偏好与信用</div>\n'
                         f'  <div class="matrix-cell lbl">市场宽度</div>\n'
                         f'  <div class="matrix-cell lbl">机构持仓与拥挤度</div>\n'
                         f'{MATRIX_ROWS_HTML}\n'
                         f'</div>\n'
                         f'<div class="matrix-legend">\n'
                         f'  <span><i class="swatch" style="background:var(--market-up-soft)"></i>可得</span>\n'
                         f'  <span><i class="swatch" style="background:var(--surface-muted)"></i>部分/待复核</span>\n'
                         f'  <span><i class="swatch" style="background:var(--market-down-soft)"></i>未知/失败/无法还原</span>\n'
                         f'</div>\n'
                         f'<div id="markets">\n{SECTIONS_HTML}\n</div>')

# ============ 组装 ============
template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>资本环境仪表盘 · {{AS_OF}}</title>
<meta name="description" content="全球、美国、中国、韩国资本环境的多维状态与证据（内部研究工具）" />
<meta name="robots" content="noindex, nofollow" />
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
:root{
  --canvas:#f8fafc;
  --surface-base:#ffffff;
  --surface-raised:#fafbfc;
  --surface-muted:#f1f5f9;
  --ink-primary:#0f172a;
  --ink-secondary:#475569;
  --ink-tertiary:#94a3b8;
  --border-hairline:#e2e8f0;
  --brand:#2563eb;
  --brand-foreground:#ffffff;
  --market-up:#16a34a;
  --market-up-soft:#dcfce7;
  --market-down:#dc2626;
  --market-down-soft:#fee2e2;
}
*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--ink-primary);
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  -webkit-font-smoothing:antialiased;}
main{min-height:100vh}
.container{max-width:72rem;margin:0 auto;padding:2.5rem 1.5rem}
.badge{display:inline-flex;align-items:center;border-radius:9999px;padding:0.125rem 0.5rem;
  font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:0.7rem;line-height:1rem;white-space:nowrap}
.badge-up{background:var(--market-up-soft);color:var(--market-up)}
.badge-down{background:var(--market-down-soft);color:var(--market-down)}
.badge-mid{background:var(--surface-muted);color:var(--ink-secondary)}
.badge-muted{background:var(--surface-muted);color:var(--ink-tertiary)}
.matrix-wrap{display:grid;grid-template-columns:auto repeat(7,1fr);gap:4px;margin-top:1.25rem;
  font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:0.68rem;color:var(--ink-secondary)}
.matrix-cell{display:flex;align-items:center;justify-content:center;padding:4px 2px;border-radius:4px;min-height:1.4rem;text-align:center}
.matrix-cell.a{background:var(--market-up-soft);color:var(--market-up)}
.matrix-cell.p{background:var(--surface-muted);color:var(--ink-secondary)}
.matrix-cell.u{background:var(--market-down-soft);color:var(--market-down)}
.matrix-cell.lbl{background:transparent;justify-content:flex-start;padding-left:2px;color:var(--ink-primary);font-weight:600}
.matrix-legend{display:flex;gap:0.75rem;margin-top:0.5rem;font-size:0.7rem;color:var(--ink-tertiary)}
.matrix-legend span{display:inline-flex;align-items:center;gap:4px}
.swatch{width:10px;height:10px;border-radius:2px;display:inline-block}
.empty-state{margin-top:1.25rem;padding:2.5rem 1.25rem;text-align:center;color:var(--ink-tertiary);background:var(--surface-muted);border:1px dashed var(--border-hairline);border-radius:0.5rem;font-size:0.875rem}
.summary-box{background:var(--surface-muted);border:1px solid var(--border-hairline);border-radius:0.5rem;padding:0.875rem 1.25rem;margin-top:1.25rem}
.summary-box p{margin:0}
.summary-box .overview{font-size:0.875rem;color:var(--ink-secondary)}
.summary-box .disclaimer{margin-top:0.375rem;font-size:0.7rem;color:var(--ink-tertiary)}
/* AI 综合研判卡 */
.takeaway-box{background:var(--surface-base);border:1px solid var(--border-hairline);border-left:3px solid var(--brand);border-radius:0.5rem;padding:0.75rem 1.25rem;margin-top:1rem}
.takeaway-box .tw-head{font-size:0.8rem;font-weight:600;color:var(--ink-primary);margin-bottom:0.5rem}
.takeaway-box .tw-list{display:flex;flex-direction:column;gap:0.375rem}
.takeaway-box .tw-item{display:flex;align-items:flex-start;gap:0.5rem;font-size:0.78rem;line-height:1.5;color:var(--ink-secondary)}
.takeaway-box .tw-tag{flex:0 0 auto;background:var(--brand);color:var(--brand-foreground);border-radius:4px;padding:0.05rem 0.4rem;font-size:0.68rem;font-weight:600;margin-top:0.15rem}
.takeaway-box .tw-txt{color:var(--ink-secondary)}
/* 风险信号清单卡 */
.risk-box{background:var(--surface-base);border:1px solid var(--border-hairline);border-left:3px solid var(--market-down);border-radius:0.5rem;padding:0.75rem 1.25rem;margin-top:0.625rem}
.risk-box .tw-head{font-size:0.8rem;font-weight:600;color:var(--ink-primary);margin-bottom:0.5rem}
.risk-section{margin-bottom:0.5rem}
.risk-section:last-child{margin-bottom:0}
.risk-title{font-size:0.72rem;font-weight:600;margin-bottom:0.25rem}
.risk-high .risk-title{color:var(--market-down)}
.risk-medium .risk-title{color:#b45309}
.risk-low .risk-title{color:var(--market-up)}
.risk-section .tw-item{font-size:0.75rem}
.risk-section .tw-tag{background:transparent;border:1px solid var(--border-hairline);color:var(--ink-tertiary)}
/* 板块倾向建议卡（研究参考，仅建议） */
.sector-advice-box{background:var(--surface-base);border:1px solid var(--border-hairline);border-left:3px solid #f59e0b;border-radius:0.5rem;padding:0.75rem 1.25rem;margin-top:0.625rem}
.sector-advice-box .tw-head{font-size:0.8rem;font-weight:600;color:var(--ink-primary);margin-bottom:0.375rem}
.sa-disclaimer{margin:0 0 0.625rem 0;font-size:0.7rem;color:var(--ink-tertiary);line-height:1.5}
.sa-mkt{margin-bottom:0.75rem;border-top:1px dashed var(--border-hairline);padding-top:0.5rem}
.sa-mkt:first-of-type{border-top:none;padding-top:0}
.sa-mkt-name{font-size:0.78rem;font-weight:600;color:var(--ink-primary);display:inline-block;margin-right:0.5rem}
.sa-mkt-date{font-size:0.68rem;color:var(--ink-tertiary);font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
.sa-list{display:flex;flex-direction:column;gap:0.5rem;margin-top:0.375rem}
.sa-item{border:1px solid var(--border-hairline);border-radius:0.375rem;padding:0.5rem 0.625rem;background:var(--surface-raised)}
.sa-item .sa-sector{font-size:0.78rem;font-weight:600;color:var(--ink-primary)}
.sa-item .sa-stance{float:right;border-radius:9999px;padding:0.05rem 0.5rem;font-size:0.68rem;font-weight:600;margin-left:0.5rem}
.sa-item .sa-stance.st-up{background:var(--market-up-soft);color:var(--market-up)}
.sa-item .sa-stance.st-mid{background:var(--surface-muted);color:var(--ink-secondary)}
.sa-item .sa-stance.st-down{background:var(--market-down-soft);color:var(--market-down)}
.sa-item .sa-ev,.sa-item .sa-tr{font-size:0.7rem;line-height:1.5;color:var(--ink-secondary);margin-top:0.25rem}
.sa-item .sa-tr{color:var(--ink-tertiary)}
.sa-item .sa-ev b,.sa-item .sa-tr b{color:var(--ink-primary);font-weight:600}
/* 每格风险点 */
.risk-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:6px;vertical-align:middle}
.risk-dot.rk-high{background:var(--market-down)}
.risk-dot.rk-medium{background:#f59e0b}
.risk-dot.rk-low{background:var(--market-up)}

/* 每格 AI 分析摘要 */
.cell-analysis{margin-top:0.5rem;padding:0.5rem 0.625rem;background:var(--surface-muted);border-radius:0.375rem;border:1px dashed var(--border-hairline)}
.cell-analysis .an-head{font-size:0.68rem;font-weight:600;color:var(--brand);margin-bottom:0.25rem;letter-spacing:0.02em}
.cell-analysis .an-list{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:0.2rem}
.cell-analysis .an-list li{display:flex;gap:0.375rem;font-size:0.7rem;line-height:1.45;color:var(--ink-secondary)}
.cell-analysis .an-lens{flex:0 0 auto;background:var(--brand);color:var(--brand-foreground);border-radius:3px;padding:0 0.3rem;font-size:0.62rem;font-weight:600;height:1.15rem;line-height:1.15rem;margin-top:0.1rem}
.cell-analysis .an-txt{color:var(--ink-secondary)}
section.market{margin-top:2rem}
.market-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem}
.market-head h2{font-size:1.125rem;font-weight:600;margin:0;color:var(--ink-primary)}
.market-grid{display:grid;gap:0.625rem}
@media (min-width:640px){.market-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:1024px){.market-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
.cell{border:1px solid var(--border-hairline);border-radius:0.5rem;padding:0.625rem;background:var(--surface-raised)}
.cell-head{display:flex;align-items:center;justify-content:space-between;gap:0.5rem;margin-bottom:0.25rem}
.cell-name{font-size:0.8rem;font-weight:500;color:var(--ink-primary)}
.chart-box{width:100%;height:180px}
.chart-box .unknown-msg{display:flex;align-items:center;justify-content:center;height:100%;color:var(--ink-tertiary);
  font-size:0.75rem;text-align:center;padding:0 0.5rem}
.cell-evidence{margin-top:0.25rem;padding-top:0.25rem;border-top:1px dashed var(--border-hairline);
  font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:0.62rem;color:var(--ink-tertiary);line-height:1.3}
header .breadcrumb{display:flex;align-items:center;gap:0.75rem;font-size:0.875rem;color:var(--ink-tertiary)}
header .breadcrumb a{color:var(--ink-tertiary);text-decoration:none}
header .breadcrumb a:hover{color:var(--brand)}
header h1{font-size:1.5rem;font-weight:700;margin:0.5rem 0 0 0}
header .asof{color:var(--ink-secondary);margin:0.25rem 0 0 0}
nav.dates{margin-top:1rem;display:flex;flex-wrap:wrap;align-items:center;gap:0.5rem;font-size:0.875rem}
nav.dates a,nav.dates button{border:1px solid var(--border-hairline);border-radius:0.375rem;padding:0.25rem 0.625rem;
  color:var(--ink-secondary);background:transparent;text-decoration:none;font:inherit;cursor:pointer}
nav.dates a:hover,nav.dates button:hover{background:var(--surface-muted)}
nav.dates input[type=date]{border:1px solid var(--border-hairline);border-radius:0.375rem;background:var(--surface-base);
  padding:0.25rem 0.5rem;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:0.875rem;color:var(--ink-primary)}
nav.dates button.primary{background:var(--brand);color:var(--brand-foreground);border-color:var(--brand)}
nav.dates button.primary:hover{opacity:0.9}
</style>
</head>
<body>
<main>
<div class="container">
  <header>
    <div class="breadcrumb"><a href="/console">← 返回运营台</a></div>
    <h1>资本环境仪表盘</h1>
    <p class="asof">回放日期：{{AS_OF}}</p>
  </header>

  <p class="asof">这是静态点时快照；请用生成器的 <code>--as-of YYYY-MM-DD</code> 生成其他日期，避免 URL 参数显示未筛选数据。</p>

  <div class="summary-box">
    <p class="overview">{{OVERVIEW}}</p>
    <p class="disclaimer">{{DISCLAIMER}}</p>
  </div>

  {{TAKEAWAYS_HTML}}

  {{SECTOR_ADVICE_HTML}}

  {{DASHBOARD_CONTENT}}
</div>
</main>
<script>
const CELLS = {{CELLS_JSON}};

const upColor = '#16a34a', downColor = '#dc2626', inkColor = '#0f172a',
      secColor = '#475569', terColor = '#94a3b8', lineColor = '#2563eb';

function evid(cfg){
  const ev = document.getElementById(cfg.evId);
  if (!ev) return;
  if (!cfg.source) {
    ev.textContent = cfg.reason ? '状态：' + cfg.reason : '';
    return;
  }
  let s = '来源：' + cfg.source;
  if (cfg.observedAt) s += ' · 观测：' + cfg.observedAt;
  if (cfg.publishedAt) s += ' · 发布：' + cfg.publishedAt;
  if (cfg.processingVersion) s += ' · ' + cfg.processingVersion;
  ev.textContent = s;
}

function renderUnknown(el, cfg){
  if (!el) return;
  el.innerHTML = '<div class="unknown-msg">' + (cfg.reason || '无可得数值（非零值）') + '</div>';
}

function renderGauge(el, cfg){
  if (!el) return;
  const chart = echarts.init(el);
  const value = Number(cfg.value);
  chart.setOption({
    series: [{
      type: 'gauge',
      startAngle: 210, endAngle: -30, min: cfg.min || 0, max: cfg.max || 10,
      radius: '92%', center: ['50%','58%'],
      axisLine: {
        lineStyle: {
          width: 12,
          color: (cfg.sections || [[0.3, upColor], [0.7, secColor], [1, downColor]]).map(function(s){ return [s[0], s[1]]; })
        }
      },
      pointer: { itemStyle: { color: inkColor }, length: '62%', width: 4 },
      axisTick: { distance: -12, length: 3, lineStyle: { color: '#fff', width: 1 } },
      splitLine: { distance: -14, length: 10, lineStyle: { color: '#fff', width: 2 } },
      axisLabel: { distance: 18, color: terColor, fontSize: 8 },
      title: { offsetCenter: [0, '68%'], fontSize: 9, color: terColor },
      detail: {
        valueAnimation: true,
        formatter: function(v){ return v + (cfg.unit ? ' ' + cfg.unit : ''); },
        color: inkColor, fontSize: 15, fontWeight: 600, offsetCenter: [0, '40%']
      },
      data: [{ value: value, name: cfg.name || '' }]
    }]
  });
  window.addEventListener('resize', function(){ chart.resize(); });
}

function renderLine(el, cfg){
  if (!el) return;
  const chart = echarts.init(el);
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 14, top: 18, bottom: 22 },
    xAxis: { type: 'category', data: cfg.dates || [],
      axisLine: { lineStyle: { color: secColor } }, axisLabel: { color: terColor, fontSize: 8 }, axisTick: { show: false } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: terColor, fontSize: 8 }, splitLine: { lineStyle: { color: '#eef2f7' } } },
    series: [{
      type: 'line', data: cfg.values || [], smooth: true, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: lineColor, width: 2 }, itemStyle: { color: lineColor },
      areaStyle: { color: { type: 'linear', x:0,y:0,x2:0,y2:1,
        colorStops: [{offset:0,color:'rgba(37,99,235,0.18)'},{offset:1,color:'rgba(37,99,235,0)'}] } },
      markLine: (cfg.markLines || []).map(function(m){
        return { name: m.label, yAxis: m.value, lineStyle: { color: downColor, type: 'dashed', width: 1 },
                 label: { formatter: m.label, color: downColor, fontSize: 8, position: 'insideEndTop' } };
      })
    }]
  });
  window.addEventListener('resize', function(){ chart.resize(); });
}

function renderBar(el, cfg){
  if (!el) return;
  const chart = echarts.init(el);
  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 44, right: 14, top: 16, bottom: 24 },
    xAxis: { type: 'category', data: cfg.categories || [],
      axisLabel: { color: terColor, fontSize: 9 }, axisTick: { show: false },
      axisLine: { lineStyle: { color: secColor } } },
    yAxis: { type: 'value', axisLabel: { color: terColor, fontSize: 8 }, splitLine: { lineStyle: { color: '#eef2f7' } } },
    series: [{
      type: 'bar', data: (cfg.values || []).map(function(v, i){
        return { value: v, itemStyle: { color: (cfg.colors || [])[i] || secColor, borderRadius: [3,3,0,0] } };
      }), barWidth: '46%',
      label: { show: true, position: 'top', color: inkColor, fontSize: 9, fontWeight: 600,
               formatter: function(p){ return p.value + (cfg.unit ? ' ' + cfg.unit : ''); } }
    }]
  });
  window.addEventListener('resize', function(){ chart.resize(); });
}

function renderCell(key, cfg){
  const id = key.replace('|', '-');
  const el = document.getElementById('ch-' + id);
  const ev = document.getElementById('ev-' + id);
  if (!el) return;
  if (cfg.type === 'unknown' || cfg.type === undefined) {
    renderUnknown(el, cfg);
  } else if (cfg.type === 'gauge') {
    renderGauge(el, cfg);
  } else if (cfg.type === 'line') {
    renderLine(el, cfg);
  } else if (cfg.type === 'bar') {
    renderBar(el, cfg);
  }
  evid(Object.assign({ evId: 'ev-' + id }, cfg));
}

Object.keys(CELLS).forEach(function(key){ renderCell(key, CELLS[key]); });
</script>
</body>
</html>
"""

html = (template
        .replace("{{AS_OF}}", AS_OF).replace("{{YESTERDAY}}", YESTERDAY).replace("{{LAST_WEEK}}", LAST_WEEK)
        .replace("{{OVERVIEW}}", overview).replace("{{DISCLAIMER}}", DISCLAIMER)
        .replace("{{TAKEAWAYS_HTML}}", takeaway_html())
        .replace("{{SECTOR_ADVICE_HTML}}", sector_advice_html())
        .replace("{{DASHBOARD_CONTENT}}", DASHBOARD_CONTENT)
        .replace("{{CELLS_JSON}}", json.dumps(CELLS, ensure_ascii=False, indent=1)))

if "{{" in html:
    raise RuntimeError("HTML 模板仍有未替换占位符")
for term in FORBIDDEN_TERMS:
    if term in html:
        raise ValueError(f"生成内容命中禁词：{term}")

if ARGS.check:
    print(f"✅ 点时数据验证通过：asOf={AS_OF}，{len(CELLS)} 格，allUnknown={ALL_UNKNOWN}")
    sys.exit(0)

default_out = Path(__file__).resolve().parents[3] / "research" / "capital-environment" / f"ashare-capital-environment-dashboard-{AS_OF}.html"
out = ARGS.out or default_out
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html, encoding="utf-8")

print(f"✅ 已生成 {out}")
print(f"   大小: {len(html)} 字节")
print(f"   overview: {overview}")
for m in MARKETS:
    print(f"   {MKT_LABEL[m]}: {avail_label(mkt_aggregate(m))}")
