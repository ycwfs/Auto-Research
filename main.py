"""
Daily arXiv Agent - 主程序入口

每日追踪 arXiv 最新论文，使用 LLM 进行总结和分析
"""
import fcntl
import re
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils import (
    build_paper_set_signature,
    get_current_datetime,
    get_date_string,
    load_json,
    load_config,
    load_env,
    save_json,
    save_text,
    setup_logging,
)


REPORT_RUN_ID_PATTERN = re.compile(r"\*\*运行ID\*\*:\s*([^\s<]+)")


def get_reusable_artifact_run_id(run_date: str, daily_papers: list[dict]) -> str | None:
    """检查当天产物是否完整且属于同一次运行，若是则返回可复用的 run_id。"""
    papers_latest = load_json("data/papers/latest.json")
    summaries_latest = load_json("data/summaries/latest.json")
    analysis_latest = load_json("data/analysis/latest.json")
    expected_count = len(daily_papers)
    expected_signature = build_paper_set_signature(daily_papers)
    summaries_report_path = Path(f"data/summaries/report_{run_date}.md")
    analysis_report_path = Path(f"data/analysis/report_{run_date}.md")

    def read_report(report_path: Path) -> str | None:
        if not report_path.exists():
            return None
        return report_path.read_text(encoding="utf-8")

    summaries_report = read_report(summaries_report_path)
    analysis_report = read_report(analysis_report_path)
    if (
        not isinstance(papers_latest, dict)
        or papers_latest.get("date") != run_date
        or papers_latest.get("count") != expected_count
        or papers_latest.get("paper_signature") != expected_signature
        or not isinstance(summaries_latest, dict)
        or summaries_latest.get("date") != run_date
        or summaries_latest.get("count") != expected_count
        or summaries_latest.get("paper_signature") != expected_signature
        or summaries_latest.get("has_errors", False)
        or not isinstance(analysis_latest, dict)
        or analysis_latest.get("date") != run_date
        or analysis_latest.get("paper_count") != expected_count
        or analysis_latest.get("paper_signature") != expected_signature
        or summaries_report is None
        or analysis_report is None
        or f"<!-- paper_signature:{expected_signature} -->" not in summaries_report
        or f"<!-- paper_signature:{expected_signature} -->" not in analysis_report
    ):
        return None

    report_run_ids = set()
    for report_content in [summaries_report, analysis_report]:
        match = REPORT_RUN_ID_PATTERN.search(report_content)
        if not match:
            return None
        report_run_ids.add(match.group(1))

    run_ids = [
        papers_latest.get("run_id"),
        summaries_latest.get("run_id"),
        analysis_latest.get("run_id"),
        *report_run_ids,
    ]
    normalized_run_ids = []
    for run_id in run_ids:
        if not isinstance(run_id, str):
            return None
        normalized_run_id = run_id.strip()
        if not normalized_run_id or normalized_run_id == "N/A":
            return None
        normalized_run_ids.append(normalized_run_id)

    unique_run_ids = set(normalized_run_ids)
    if len(unique_run_ids) != 1:
        return None

    return normalized_run_ids[0]


@contextmanager
def pipeline_run_lock(run_date: str):
    """串行化主流程运行，避免共享 latest/state 文件互相覆盖。"""
    lock_path = Path("data/runtime/pipeline.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def main():
    """主函数"""
    # 加载配置
    load_env()
    config = load_config()
    run_datetime = get_current_datetime(config)
    config.setdefault('_runtime', {})['run_datetime'] = run_datetime
    config['_runtime']['run_id'] = run_datetime.strftime('%Y%m%dT%H%M%S%z')
    run_date = get_date_string(config=config)
    pipeline_state_path = "data/runtime/pipeline_state.json"

    def wall_clock_now():
        tzinfo = run_datetime.tzinfo
        return datetime.now(tzinfo) if tzinfo else datetime.now()

    logger = None
    with pipeline_run_lock(run_date):
        try:
            logger = setup_logging(config)

            logger.info("=" * 60)
            logger.info("Daily arXiv Agent 启动")
            logger.info(f"日期: {run_date}")
            logger.info("=" * 60)
            logger.info(
                "运行配置: summary_backend=%s, analysis_backend=%s, agent=%s, llm_provider=%s, run_date=%s, run_id=%s",
                config.get("pipeline", {}).get("summary_backend", "agent"),
                config.get("pipeline", {}).get("analysis_backend", "agent"),
                config.get("agent", {}).get("copilot_command", "copilot"),
                config.get("llm", {}).get("provider", "unknown"),
                run_date,
                config["_runtime"]["run_id"],
            )

            summaries_ready = False
            summary_report_ready = False
            summaries_have_errors = False
            analysis_ready = False
            missing_artifacts = []

            # 第二步 - 实现论文爬取 ✅
            logger.info("步骤 1: 爬取 arXiv 论文...")
            from src.crawler.arxiv_fetcher import ArxivFetcher
            fetcher = ArxivFetcher(config)
        
            # 尝试获取论文，如果没找到，逐步放宽条件
            papers = fetcher.fetch_papers(days_back=1)
            found_only_duplicates = (
                fetcher.last_fetch_stats.get("raw_count", 0) > 0
                and fetcher.last_fetch_stats.get("new_count", 0) == 0
            )
        
            if not papers:
                if fetcher.last_fetch_stats.get("duplicate_count", 0) > 0:
                    logger.warning("⚠️  过去1天抓取到的论文均已在历史记录中，尝试扩大到7天...")
                else:
                    logger.warning("⚠️  过去1天没有找到符合条件的论文，尝试扩大到7天...")
                papers = fetcher.fetch_papers(days_back=7)
        
            if papers:
                fetcher.print_paper_summary(papers)
            else:
                daily_papers = fetcher.get_daily_papers(run_date)
                reusable_artifact_run_id = (
                    get_reusable_artifact_run_id(run_date, daily_papers)
                    if daily_papers
                    else None
                )
                no_new_papers = bool(daily_papers) or (
                    found_only_duplicates
                    or (
                        fetcher.last_fetch_stats.get("raw_count", 0) > 0
                        and fetcher.last_fetch_stats.get("new_count", 0) == 0
                    )
                )
                if daily_papers and not reusable_artifact_run_id:
                    logger.info("ℹ️ 今日没有新增论文，但检测到当天产物不完整，将基于已保留论文重新生成")
                    fetcher.save_latest_snapshot(
                        daily_papers,
                        date_str=run_date,
                        run_id=config["_runtime"]["run_id"],
                    )
                    papers = daily_papers
                    fetcher.print_paper_summary(papers)
                elif reusable_artifact_run_id:
                    existing_state = load_json(pipeline_state_path)
                    logger.info("ℹ️ 本次未发现新的未采集论文，跳过后续总结、分析与上传准备")
                    fetcher.save_latest_snapshot(
                        daily_papers,
                        date_str=run_date,
                        run_id=reusable_artifact_run_id,
                    )
                    save_json(
                        {
                            "run_date": run_date,
                            "run_id": reusable_artifact_run_id,
                            "status": "completed",
                            "started_at": (existing_state or {}).get("started_at")
                            or run_datetime.isoformat(),
                            "completed_at": wall_clock_now().isoformat(),
                            "reused_outputs": True,
                            "raw_count": fetcher.last_fetch_stats.get("raw_count", 0),
                            "new_count": fetcher.last_fetch_stats.get("new_count", 0),
                            "duplicate_count": fetcher.last_fetch_stats.get("duplicate_count", 0),
                        },
                        pipeline_state_path,
                    )
                    return
                elif not daily_papers or no_new_papers:
                    logger.warning("⚠️  没有找到符合条件的论文")
                    if no_new_papers:
                        logger.info("ℹ️ 没有可复用的当天论文快照，本次不生成后续产物")
                        pipeline_status = "no_new_papers"
                    else:
                        logger.info("💡 提示: 可以尝试以下方法：")
                        logger.info("   1. 在 config.yaml 中增加 days_back 或 max_results")
                        logger.info("   2. 减少或删除关键词过滤（设置 keywords: []）")
                        logger.info("   3. 修改类别范围")
                        pipeline_status = "no_papers"
                    save_json(
                        {
                            "run_date": run_date,
                            "run_id": config["_runtime"]["run_id"],
                            "status": pipeline_status,
                            "started_at": run_datetime.isoformat(),
                            "finished_at": wall_clock_now().isoformat(),
                            "raw_count": fetcher.last_fetch_stats.get("raw_count", 0),
                            "new_count": fetcher.last_fetch_stats.get("new_count", 0),
                            "duplicate_count": fetcher.last_fetch_stats.get("duplicate_count", 0),
                        },
                        pipeline_state_path,
                    )
                    return

            save_json(
                {
                    "run_date": run_date,
                    "run_id": config["_runtime"]["run_id"],
                    "status": "running",
                    "started_at": run_datetime.isoformat(),
                },
                pipeline_state_path,
            )

            # 第三步 - 实现论文总结 ✅
            logger.info("\n步骤 2: 总结论文...")
            from src.summarizer.paper_summarizer import PaperSummarizer
        
            try:
                summarizer = PaperSummarizer(config)
                summarized_papers = summarizer.summarize_papers(papers)
                summaries_have_errors = any(
                    paper.get("summary_error") for paper in summarized_papers
                )
                summaries_ready = not summaries_have_errors
                if summaries_have_errors:
                    logger.warning("⚠️ 存在论文总结失败，本次运行将标记为未完成")
            except Exception as e:
                logger.error(f"论文总结失败: {str(e)}")
                logger.info("继续执行后续步骤...")
                summarized_papers = papers
            else:
                try:
                    logger.info("\n生成每日报告...")
                    report = summarizer.generate_daily_report(summarized_papers)

                    report_path = f"data/summaries/report_{run_date}.md"
                    save_text(report, report_path)
                    logger.info(f"📄 每日报告已保存到: {report_path}")
                    summary_report_ready = True
                except Exception as e:
                    logger.error(f"每日报告生成失败: {str(e)}")
                    logger.info("继续执行后续步骤...")
        
            # 第四步 - 实现趋势分析 ✅
            logger.info("\n步骤 3: 分析研究趋势...")
            try:
                from src.analyzer.trend_analyzer import TrendAnalyzer

                analyzer = TrendAnalyzer(config)
                analysis = analyzer.analyze(papers, summarized_papers)
                
                if analysis:
                    analyzer.print_analysis_summary(analysis)
                    analysis_ready = True
                
            except Exception as e:
                logger.error(f"趋势分析失败: {str(e)}", exc_info=True)
                logger.info("继续执行后续步骤...")

            if not summaries_ready:
                missing_artifacts.append("data/summaries/latest.json")
            if summaries_have_errors:
                missing_artifacts.append("data/summaries/latest.json (contains summary errors)")
            if not summary_report_ready:
                missing_artifacts.append(f"data/summaries/report_{run_date}.md")
            if not analysis_ready:
                missing_artifacts.append(f"data/analysis/report_{run_date}.md")

            pipeline_status = "completed" if not missing_artifacts else "partial"
            logger.info("=" * 60)
            if pipeline_status == "completed":
                logger.info("✅ 所有任务完成！")
                logger.info("提示: 运行 'python src/web/app.py' 启动 Web 服务查看结果")
            else:
                logger.warning("⚠️ 主流程完成，但 Zotero 上传输入不完整")
                logger.warning("缺失产物: %s", ", ".join(missing_artifacts))
            logger.info("=" * 60)
            save_json(
                {
                    "run_date": run_date,
                    "run_id": config["_runtime"]["run_id"],
                    "status": pipeline_status,
                    "started_at": run_datetime.isoformat(),
                    "completed_at": wall_clock_now().isoformat(),
                    "missing_artifacts": missing_artifacts,
                },
                pipeline_state_path,
            )

        except Exception as e:
            save_json(
                {
                    "run_date": run_date,
                    "run_id": config["_runtime"]["run_id"],
                    "status": "failed",
                    "started_at": run_datetime.isoformat(),
                    "failed_at": wall_clock_now().isoformat(),
                    "error": str(e),
                },
                pipeline_state_path,
            )
            if logger:
                logger.error(f"❌ 执行出错: {str(e)}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
