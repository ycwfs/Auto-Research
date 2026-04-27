#!/usr/bin/env python3
"""
测试全文总结配置与报告生成。
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.summarizer.paper_summarizer import PaperSummarizer
from src.utils import load_config, load_env


def test_summary_agent_config():
    print("\n" + "=" * 70)
    print("🧪 测试全文总结代理配置")
    print("=" * 70)

    load_env()
    config = load_config()
    agent_config = config.get("agent", {})
    pipeline_config = config.get("pipeline", {})
    summary_config = agent_config.get("summary", {})

    required = [
        "pipeline.summary_backend",
        "copilot_command",
        "summary.prompt_file",
        "summary.log_dir",
        "summary.fulltext_dir",
    ]
    checks = {
        "pipeline.summary_backend": pipeline_config.get("summary_backend") in {"agent", "llm"},
        "copilot_command": bool(agent_config.get("copilot_command")),
        "summary.prompt_file": bool(summary_config.get("prompt_file")),
        "summary.log_dir": bool(summary_config.get("log_dir")),
        "summary.fulltext_dir": bool(summary_config.get("fulltext_dir")),
    }

    all_ok = True
    for label in required:
        passed = checks[label]
        print(f"  {'✅' if passed else '❌'} {label}")
        all_ok = all_ok and passed

    prompt_path = project_root / summary_config.get("prompt_file", "")
    prompt_ok = prompt_path.exists()
    print(f"  {'✅' if prompt_ok else '❌'} prompt file exists: {prompt_path}")
    all_ok = all_ok and prompt_ok

    return all_ok


def test_daily_report_rendering():
    print("\n" + "=" * 70)
    print("🧪 测试全文总结日报渲染")
    print("=" * 70)

    load_env()
    config = load_config()
    config.setdefault("pipeline", {})["summary_backend"] = "agent"
    summarizer = PaperSummarizer(config)
    sample_papers = [
        {
            "id": "2604.12345v1",
            "paper_id": "2604.12345",
            "title": "Sample Paper",
            "authors": ["Alice", "Bob"],
            "categories": ["cs.AI"],
            "pdf_url": "https://arxiv.org/pdf/2604.12345v1",
            "summary": "中文摘要。",
            "summary_en": "English summary.",
            "structured_summary": {
                "task_definition": "Input to output mapping.",
                "background_motivation": "Why this problem matters.",
                "research_method": "A new module stack.",
                "evaluation_metrics": "Accuracy and F1.",
                "results_conclusions": "Improves the baseline.",
            },
            "summary_error": False,
            "fulltext_markdown_path": "data/fulltext/2026-04-27/2604.12345.md",
        }
    ]

    report = summarizer.generate_daily_report(sample_papers)
    checks = [
        ("paper signature marker", "<!-- paper_signature:" in report),
        ("chinese summary section", "### 中文摘要" in report),
        ("english summary section", "### English Summary" in report),
        ("structured note section", "### Structured Notes" in report),
    ]

    all_ok = True
    for label, passed in checks:
        print(f"  {'✅' if passed else '❌'} {label}")
        all_ok = all_ok and passed

    return all_ok


def main():
    results = [
        ("代理配置", test_summary_agent_config()),
        ("日报渲染", test_daily_report_rendering()),
    ]

    print("\n" + "=" * 70)
    print("📊 测试总结")
    print("=" * 70)
    for name, passed in results:
        print(f"{'✅ 通过' if passed else '❌ 失败'} - {name}")

    return all(passed for _, passed in results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
