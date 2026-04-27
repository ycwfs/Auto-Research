#!/usr/bin/env python3
"""
测试趋势分析基础功能与代理配置。
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analyzer.trend_analyzer import TrendAnalyzer
from src.utils import load_config, load_env, load_json


def load_latest_papers():
    papers_data = load_json("data/papers/latest.json")
    if not papers_data:
        print("❌ 未找到论文数据，请先运行 python main.py")
        return None
    return papers_data.get("papers", [])


def test_analyzer_config():
    print("\n" + "=" * 60)
    print("🧪 测试趋势分析代理配置")
    print("=" * 60)

    load_env()
    config = load_config()
    agent_config = config.get("agent", {})
    pipeline_config = config.get("pipeline", {})
    analysis_config = agent_config.get("analysis", {})
    prompt_path = project_root / analysis_config.get("prompt_file", "")

    checks = [
        ("pipeline.analysis_backend", pipeline_config.get("analysis_backend") in {"agent", "llm"}),
        ("copilot_command", bool(agent_config.get("copilot_command"))),
        ("analysis.prompt_file", bool(analysis_config.get("prompt_file"))),
        ("analysis.log_dir", bool(analysis_config.get("log_dir"))),
        ("prompt exists", prompt_path.exists()),
    ]

    all_ok = True
    for label, passed in checks:
        print(f"  {'✅' if passed else '❌'} {label}")
        all_ok = all_ok and passed

    return all_ok


def test_local_analysis_helpers():
    print("\n" + "=" * 60)
    print("🧪 测试本地关键词/主题/统计分析")
    print("=" * 60)

    load_env()
    config = load_config()
    config.setdefault("pipeline", {})["analysis_backend"] = "agent"
    papers = load_latest_papers()
    if not papers:
        return False

    analyzer = TrendAnalyzer(config)
    keywords = analyzer._extract_keywords(papers, top_n=10)
    topics = analyzer._extract_topics(papers, n_topics=3)
    statistics = analyzer._generate_statistics(papers)

    checks = [
        ("keywords extracted", len(keywords) > 0),
        ("topics extracted", len(topics) == 3),
        ("statistics total_papers", statistics.get("total_papers") == len(papers)),
    ]

    all_ok = True
    for label, passed in checks:
        print(f"  {'✅' if passed else '❌'} {label}")
        all_ok = all_ok and passed

    return all_ok


def main():
    results = [
        ("代理配置", test_analyzer_config()),
        ("本地分析辅助函数", test_local_analysis_helpers()),
    ]

    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    for name, passed in results:
        print(f"{'✅ 通过' if passed else '❌ 失败'} - {name}")

    return all(passed for _, passed in results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
