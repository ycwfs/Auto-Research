"""
Daily arXiv Agent - Zotero 上传入口

使用 Copilot CLI 和 Zotero MCP 将每日论文与报告同步到 Zotero。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.automation import (
    get_effective_pipeline_state,
    get_effective_upload_date,
    get_pipeline_skip_message,
    is_pipeline_uploadable,
    run_zotero_upload,
    wait_for_zotero_artifacts,
    ZoteroUploadSkippedError,
)
from src.utils import load_config, load_env, setup_logging


def main():
    """主函数"""
    load_env()
    config = load_config()
    logger = setup_logging(config)

    logger.info("=" * 60)
    logger.info("Daily arXiv Zotero 上传任务启动")
    logger.info(f"日期: {get_effective_upload_date(config)}")
    logger.info("=" * 60)

    try:
        pipeline_state = get_effective_pipeline_state(config)
        if not is_pipeline_uploadable(pipeline_state):
            logger.info(get_pipeline_skip_message(pipeline_state))
            return

        upload_date = pipeline_state["run_date"]
        wait_for_zotero_artifacts(config, upload_date, logger=logger)
        log_path = run_zotero_upload(config, logger=logger, date_str=upload_date)
        logger.info("✅ Zotero 上传任务完成")
        logger.info(f"📄 执行日志: {log_path}")
    except ZoteroUploadSkippedError as e:
        logger.info(str(e))
    except Exception as e:
        logger.error(f"❌ Zotero 上传任务失败: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
