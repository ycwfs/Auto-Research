#!/usr/bin/env python3
"""
测试抓取历史去重逻辑。
"""

import copy
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytz

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.crawler.arxiv_fetcher import ArxivFetcher
from src.utils import load_config, load_env, save_json


def make_paper(paper_id: str, fetched_at: str) -> dict:
    """构造测试论文数据。"""
    return {
        "id": paper_id,
        "title": f"Paper {paper_id}",
        "authors": ["Test Author"],
        "abstract": f"Abstract for {paper_id}",
        "categories": ["cs.AI"],
        "primary_category": "cs.AI",
        "published": "2026-04-19T00:00:00+00:00",
        "updated": "2026-04-19T00:00:00+00:00",
        "pdf_url": f"https://arxiv.org/pdf/{paper_id}",
        "entry_url": f"http://arxiv.org/abs/{paper_id}",
        "comment": None,
        "journal_ref": None,
        "doi": None,
        "fetched_at": fetched_at,
    }


def test_history_dedup():
    """验证历史去重会排除昨天的论文并累积当天新增论文。"""
    print("\n" + "=" * 60)
    print("🧪 测试历史论文去重")
    print("=" * 60)

    load_env()
    config = copy.deepcopy(load_config())
    timezone = pytz.timezone(config.get("scheduler", {}).get("timezone", "Asia/Shanghai"))
    run_datetime = timezone.localize(datetime(2026, 4, 20, 9, 0, 0))
    date_str = run_datetime.strftime("%Y-%m-%d")
    previous_date = (run_datetime - timedelta(days=1)).strftime("%Y-%m-%d")

    with TemporaryDirectory() as temp_dir:
        config["storage"]["json_path"] = temp_dir
        config.setdefault("_runtime", {})["run_datetime"] = run_datetime
        config["_runtime"]["run_id"] = run_datetime.strftime("%Y%m%dT%H%M%S%z")

        save_json(
            [make_paper("2604.00001v1", "2026-04-19T09:00:00+08:00")],
            f"{temp_dir}/papers_{previous_date}.json",
        )
        save_json(
            [make_paper("2604.00003v1", "2026-04-20T09:00:00+08:00")],
            f"{temp_dir}/papers_{date_str}.json",
        )

        fetcher = ArxivFetcher(config)
        prepared = fetcher._prepare_daily_papers(
            [
                make_paper("2604.00001v2", "2026-04-20T09:00:00+08:00"),
                make_paper("2604.00002v1", "2026-04-20T09:00:00+08:00"),
                make_paper("2604.00003v1", "2026-04-20T09:00:00+08:00"),
            ]
        )

        checks = [
            (
                "yesterday's paper is treated as duplicate even across versions",
                prepared["duplicate_count"] == 2,
            ),
            (
                "only unseen paper remains new",
                [paper["id"] for paper in prepared["new_papers"]] == ["2604.00002v1"],
            ),
            (
                "today's file stays cumulative after merge",
                [paper["id"] for paper in prepared["daily_papers"]]
                == ["2604.00003v1", "2604.00002v1"],
            ),
            (
                "arxiv pdf links are normalized with .pdf suffix",
                all(
                    paper["pdf_url"].endswith(".pdf")
                    for paper in prepared["daily_papers"]
                ),
            ),
        ]

        all_passed = True
        for label, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {label}")
            all_passed = all_passed and passed

        return all_passed


def main():
    """运行测试。"""
    success = test_history_dedup()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
