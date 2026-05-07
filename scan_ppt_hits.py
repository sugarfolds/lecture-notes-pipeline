#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


TRANSCRIPT_DIR = Path("transcripts")

PPT_KEYWORDS = {
    "1-法律思维：右脑颠覆左脑": ["右脑", "左脑", "复杂系统", "涌现", "鸟群", "社会模拟"],
    "2-习近平法治思想": ["习近平法治思想", "科学立法", "法治政府", "法治社会", "营商环境", "负面清单"],
    "3-法理学对象、性质、方法与历史": ["法学皇冠", "法学研究对象", "文明灵魂", "法理学对象", "法学研习"],
    "4-法律思维": ["法律真实", "合规思维", "事实认定", "形式推理", "程序公正"],
    "5-法学谱系": ["自然法学派", "分析法学派", "社会法学派", "米兰达规则", "应然法"],
    "6-法律方法": ["五月花", "法律方法", "社科法学", "规范法学", "比较法"],
    "7-判例简史": ["判例简史", "李长城", "家乐福", "购物小票", "发票"],
    "8-判例技术": ["指导性案例", "判例技术", "语词选用", "概念的审慎"],
    "9-法律悖论": ["悖论", "半费之诉", "法律悖论"],
    "10-利益衡量1": ["利益衡量", "五月花案件", "龚硕皓", "李萍", "为什么出现了利益衡量"],
    "11-利益衡量2": ["利益衡量理论", "复数解释", "选择标准"],
    "12-利益衡量3": ["九民纪要", "表见代理", "公司纠纷", "外观主义"],
    "13-司法改革": ["基础司改", "综配司改", "全面政法改革", "孟建柱"],
    "14-商事合规": ["商事合规", "围串标", "刑法223条", "泄露标底"],
    "15-计算法学": ["计算法学", "乡愁", "塞尚", "数字化的长与短"],
    "16-中国特色社会主义法治体系": ["全面依法治国", "中国特色社会主义法治体系", "1954年宪法", "16字方针"],
}


def lecture_number(path: Path) -> int:
    match = re.search(r"第(\d+)课时", path.name)
    if not match:
        raise RuntimeError(f"无法解析课时号: {path.name}")
    return int(match.group(1))


def main() -> None:
    transcripts = sorted(TRANSCRIPT_DIR.glob("*.txt"), key=lecture_number)
    for transcript in transcripts:
        text = transcript.read_text(encoding="utf-8")
        hits: list[str] = []
        for ppt, keywords in PPT_KEYWORDS.items():
            count = sum(1 for item in keywords if item in text)
            if count:
                hits.append(f"{ppt}({count})")
        print(f"第{lecture_number(transcript):02d}课时: {', '.join(hits) if hits else 'NO_HITS'}")


if __name__ == "__main__":
    main()
