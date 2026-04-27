"""
Daily arXiv Agent - 周度论文综述与 idea 入口

使用 Copilot CLI 与 Zotero MCP 生成本周综述和 introduction-ready 研究想法。
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.automation.weekly_idea_runner import (
    WeeklyIdeaSkippedError,
    get_week_range,
    run_weekly_idea_generation,
)
from src.utils import load_config, load_env, setup_logging


def main():
    load_env()
    config = load_config()
    logger = setup_logging(config)
    week_start, week_end = get_week_range(config)

    logger.info("=" * 60)
    logger.info("Daily arXiv 周度 idea 任务启动")
    logger.info("周范围: %s -> %s", week_start, week_end)
    logger.info("=" * 60)

    try:
        log_path = run_weekly_idea_generation(config, logger=logger)
        logger.info("✅ 周度 idea 任务完成")
        logger.info("📄 执行日志: %s", log_path)
    except WeeklyIdeaSkippedError as exc:
        logger.info(str(exc))
    except Exception as exc:
        logger.error("❌ 周度 idea 任务失败: %s", str(exc), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
