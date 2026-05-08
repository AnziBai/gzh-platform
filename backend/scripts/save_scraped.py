"""Write scraped articles data to JSON file, then run the update script."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The 68 articles scraped from WeChat backend via Playwright
articles = [
    {"title": "多周期共振：大中小周期如何协同决策", "reads": 15, "shares": 2, "favorites": 5, "likes": 1},
    {"title": "仓位管理：为什么说轻仓是最好的风险控制", "reads": 19, "shares": 0, "favorites": 3, "likes": 0},
    {"title": "量化交易入门：什么是程序化交易", "reads": 40, "shares": 2, "favorites": 5, "likes": 1},
    {"title": "顺势操作的认知陷阱：什么叫真正的顺势", "reads": 28, "shares": 1, "favorites": 6, "likes": 0},
    {"title": "均线系统实战：五线排列的判断标准", "reads": 66, "shares": 4, "favorites": 17, "likes": 2},
    {"title": "全天候策略：桥水基金的配置逻辑", "reads": 17, "shares": 0, "favorites": 0, "likes": 0},
    {"title": "宽论品牌故事：桥博士和《概率的朋友》的诞生", "reads": 34, "shares": 0, "favorites": 0, "likes": 0},
    {"title": "交易心理进阶：如何在连续止损后保持执行力", "reads": 36, "shares": 3, "favorites": 7, "likes": 1},
    {"title": "CTA策略基础：趋势跟踪的核心逻辑", "reads": 29, "shares": 1, "favorites": 5, "likes": 0},
    {"title": "海龟交易法则：经典系统的现代解读", "reads": 40, "shares": 1, "favorites": 6, "likes": 0},
    {"title": "资金管理进阶：凯利公式的实战改造", "reads": 15, "shares": 1, "favorites": 2, "likes": 0},
    {"title": "期望值思维：单笔结果不重要，100笔的数学期望才重要", "reads": 18, "shares": 0, "favorites": 0, "likes": 0},
    {"title": "参数优化陷阱：为什么最优参数不等于最好策略", "reads": 20, "shares": 1, "favorites": 4, "likes": 0},
    {"title": "回测的正确方式：避免过拟合的三个原则", "reads": 44, "shares": 1, "favorites": 5, "likes": 0},
    {"title": "交易日志：职业选手和业余选手的分水岭", "reads": 3, "shares": 45, "favorites": 325, "likes": 8},
    {"title": "从亏损中学习：如何把每次止损变成数据", "reads": 57, "shares": 1, "favorites": 10, "likes": 0},
    {"title": "一致性大于爆发力：100次交易的数学期望", "reads": 29, "shares": 3, "favorites": 1, "likes": 1},
    {"title": "短鱼出现时该怎么做：应对假突破的操作手册", "reads": 28, "shares": 0, "favorites": 3, "likes": 1},
    {"title": "如何用带鱼法则过滤假突破：3个量价条件", "reads": 42, "shares": 0, "favorites": 5, "likes": 0},
    {"title": "连续止损3次后怎么办：保持执行力的心理训练", "reads": 10, "shares": 0, "favorites": 1, "likes": 0},
    {"title": "聪明人炒股为什么更容易亏钱", "reads": 13, "shares": 0, "favorites": 1, "likes": 0},
    {"title": "带鱼原理深度解析：为什么带鱼体现的是主力意图", "reads": 14, "shares": 0, "favorites": 1, "likes": 0},
    {"title": "从感觉到规则：系统化交易的关键跨越", "reads": 17, "shares": 0, "favorites": 4, "likes": 0},
    {"title": "从CDVA到下单：一个完整买卖决策的流程图", "reads": 15, "shares": 2, "favorites": 3, "likes": 1},
    {"title": "弹下看空不是做空：弹论的防守思维与保命逻辑", "reads": 16, "shares": 0, "favorites": 4, "likes": 0},
    {"title": "弹中震荡为什么不能操作：概率数据告诉你答案", "reads": 27, "shares": 1, "favorites": 3, "likes": 0},
    {"title": "弹上做多的完整操作框架：进场、减仓与止损", "reads": 5, "shares": 0, "favorites": 0, "likes": 0},
    {"title": "弹论三区域完全指南：上中下如何判断趋势", "reads": 25, "shares": 2, "favorites": 8, "likes": 2},
    {"title": "V型反转 vs A型见顶：散户最常搞混的两种形态", "reads": 26, "shares": 1, "favorites": 6, "likes": 0},
    {"title": "CDVA结合弹论：双重确认体系的实战应用", "reads": 20, "shares": 2, "favorites": 6, "likes": 1},
    {"title": "MACD金叉买入，为什么每次都被套？", "reads": 100, "shares": 9, "favorites": 24, "likes": 2},
    {"title": "均线系统为什么让你越用越亏？", "reads": 11, "shares": 1, "favorites": 1, "likes": 1},
    {"title": "K线形态背了100种，为什么还是看不懂图？", "reads": 113, "shares": 12, "favorites": 26, "likes": 2},
    {"title": "做了8000笔交易，我学到了这5件事", "reads": 40, "shares": 3, "favorites": 7, "likes": 1},
    {"title": "学了量化交易还是亏钱？你少了这个关键环节", "reads": 20, "shares": 1, "favorites": 4, "likes": 0},
    {"title": "均线用了这么多年还在亏？因为你只学了皮毛", "reads": 79, "shares": 6, "favorites": 24, "likes": 2},
    {"title": "学了3年波浪理论还在数浪？一招带鱼法则终结你的困惑", "reads": 13, "shares": 0, "favorites": 1, "likes": 0},
    {"title": "海龟交易法则作者破产流浪，交易系统再好为什么还会爆仓？", "reads": 9, "shares": 2, "favorites": 1, "likes": 0},
    {"title": "做了30年交易，我发现亏钱的人都有同一个习惯", "reads": 63, "shares": 5, "favorites": 6, "likes": 2},
    {"title": "学了这么多K线形态还是不会用？试试宽论分型", "reads": 18, "shares": 1, "favorites": 3, "likes": 0},
    {"title": "99%的人都在错误使用MACD，上涨之眼才是真正的买点", "reads": 37, "shares": 3, "favorites": 6, "likes": 3},
    {"title": "90%散户亏钱的真相：你一直在和概率作对", "reads": 52, "shares": 2, "favorites": 5, "likes": 0},
    {"title": "MACD背离：高手藏着不说的技巧，其实比金叉死叉准多了", "reads": 181, "shares": 6, "favorites": 29, "likes": 1},
    {"title": "K线形态，散户没学会的3个维度", "reads": 84, "shares": 1, "favorites": 13, "likes": 0},
    {"title": "MACD指标为什么总是不准？", "reads": 207, "shares": 5, "favorites": 22, "likes": 0},
    {"title": "散户怎么入门量化交易", "reads": 48, "shares": 1, "favorites": 9, "likes": 1},
    {"title": "K线经典口诀｜新手炒股避坑指南", "reads": 11, "shares": 360, "favorites": 2, "likes": 168},
    {"title": "新手炒股｜1 分钟看懂股票界面", "reads": 179, "shares": 11, "favorites": 30, "likes": 3},
    {"title": "宽论：一套基于概率与回测的交易体系（上）", "reads": 164, "shares": 11, "favorites": 28, "likes": 3},
    {"title": "Aberration策略回测代码", "reads": 41, "shares": 6, "favorites": 12, "likes": 3},
    {"title": "别再亏钱了！用这招检验你的选股方法真伪（下）", "reads": 57, "shares": 13, "favorites": 18, "likes": 7},
    {"title": "别再亏钱了！用这招检验你的选股方法真伪（上）", "reads": 59, "shares": 9, "favorites": 12, "likes": 6},
    {"title": "散户必学的程序化交易：打破人性瓶颈，构建自己的交易圣杯", "reads": 26, "shares": 3, "favorites": 7, "likes": 0},
    {"title": "散户必学的BIAS背离战法：从原理到实战，高效识别买卖点（附源码）", "reads": 29, "shares": 0, "favorites": 5, "likes": 0},
    {"title": "散户必学的移动均线战法：趋势动能一眼看透，金叉死叉不再被骗！", "reads": 43, "shares": 3, "favorites": 9, "likes": 2},
    {"title": "散户必学的ATR动态止损：从理论到实战（附源码）", "reads": 37, "shares": 4, "favorites": 12, "likes": 2},
    {"title": "宽客相对论（四）：打破流派对立，量化分析+价值投资的融合之道", "reads": 65, "shares": 1, "favorites": 15, "likes": 1},
    {"title": "宽客相对论（三）：多模型+多周期+多品种，3步构建稳健组合", "reads": 65, "shares": 1, "favorites": 11, "likes": 0},
    {"title": "宽客相对论（二）：教你3步学会相对涨跌幅，选出强于大盘的个股", "reads": 92, "shares": 2, "favorites": 6, "likes": 1},
    {"title": "宽客相对论（一）：从概率优势到组合策略，3步学会量化投资", "reads": 80, "shares": 1, "favorites": 9, "likes": 1},
    {"title": "MACD四大经典看涨形态！别只懂金叉死叉，学会这样用，照着做，就吃肉！（含图解）", "reads": 62, "shares": 0, "favorites": 10, "likes": 0},
    {"title": "从入门到精通：MACD指标深度解析，带你读懂趋势密码", "reads": 57, "shares": 2, "favorites": 10, "likes": 2},
    {"title": "90%交易者不知道的MACD秘密：三值优化让策略盈利能力翻倍", "reads": 238, "shares": 3, "favorites": 19, "likes": 1},
    {"title": "8分钟讲透《MACD指标形态》：直接教会你看完就能用！（附回测报告）", "reads": 153, "shares": 5, "favorites": 15, "likes": 0},
    {"title": "指标之王-MACD的前世今生", "reads": 60, "shares": 0, "favorites": 12, "likes": 0},
    {"title": "为什么MACD是最受欢迎的量化指标之王，答案是……", "reads": 47, "shares": 2, "favorites": 8, "likes": 1},
    {"title": "为什么MACD有时会不准？真相是.....", "reads": 62, "shares": 1, "favorites": 7, "likes": 1},
]

out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scraped_articles.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(articles, f, ensure_ascii=False, indent=2)

print(f"Saved {len(articles)} articles to {out_path}")

# Now run the update script
from scripts.scrape_wechat_backend import update_db_from_scraped_data
update_db_from_scraped_data(out_path)
