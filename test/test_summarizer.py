#!/usr/bin/env python3
"""
测试全文总结配置与报告生成。
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.summarizer.paper_summarizer import PaperSummarizer
from src.utils import load_config, load_env, normalize_paper_pdf_url


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


def test_arxiv_pdf_url_normalization():
    print("\n" + "=" * 70)
    print("🧪 测试 arXiv PDF 链接规范化")
    print("=" * 70)

    normalized = normalize_paper_pdf_url(
        {
            "id": "2604.12345v1",
            "pdf_url": "https://arxiv.org/pdf/2604.12345v1",
            "entry_url": "http://arxiv.org/abs/2604.12345v1",
        }
    )
    checks = [
        (
            "raw arxiv pdf url gains .pdf suffix",
            normalized["pdf_url"] == "https://arxiv.org/pdf/2604.12345v1.pdf",
        ),
    ]

    all_ok = True
    for label, passed in checks:
        print(f"  {'✅' if passed else '❌'} {label}")
        all_ok = all_ok and passed

    return all_ok


def test_html_fallback_digest_entry_counts_as_success():
    print("\n" + "=" * 70)
    print("🧪 测试 HTML fallback 总结不计为失败")
    print("=" * 70)

    load_env()
    config = load_config()
    config.setdefault("pipeline", {})["summary_backend"] = "agent"
    summarizer = PaperSummarizer(config)
    paper = {
        "id": "2604.28173v1",
        "title": "Fallback Paper",
        "authors": ["Alice"],
        "categories": ["cs.AI"],
        "pdf_url": "https://arxiv.org/pdf/2604.28173v1",
        "entry_url": "http://arxiv.org/abs/2604.28173v1",
    }
    output_payload = {
        "papers": [
            {
                "paper_id": "2604.28173",
                "summary_error": True,
                "summary_error_message": "arXiv PDF URL returned 404",
                "summary_zh": "中文总结",
                "summary_en": "English summary",
                "structured_summary": {
                    "task_definition": "task",
                    "background_motivation": "motivation",
                    "research_method": "method",
                    "evaluation_metrics": "metrics",
                    "results_conclusions": "results",
                },
                "zotero_note_zh": "# 论文总结\n\n中文总结",
                "zotero_note_en": "# Paper Summary\n\nEnglish summary",
            }
        ]
    }

    with TemporaryDirectory() as temp_dir:
        merged = summarizer._merge_summaries(
            papers=[normalize_paper_pdf_url(paper)],
            output_payload=output_payload,
            fulltext_output_dir=Path(temp_dir),
        )

    checks = [
        ("fallback summary is treated as success", merged[0]["summary_error"] is False),
        ("fallback error message is cleared", merged[0]["summary_error_message"] == ""),
        (
            "pdf url stays normalized",
            merged[0]["pdf_url"] == "https://arxiv.org/pdf/2604.28173v1.pdf",
        ),
    ]

    all_ok = True
    for label, passed in checks:
        print(f"  {'✅' if passed else '❌'} {label}")
        all_ok = all_ok and passed

    return all_ok


def main():
    results = [
        ("代理配置", test_summary_agent_config()),
        ("PDF 链接规范化", test_arxiv_pdf_url_normalization()),
        ("HTML fallback 成功判定", test_html_fallback_digest_entry_counts_as_success()),
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
