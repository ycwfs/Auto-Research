"""
定时调度器

使用 APScheduler 实现每日自动运行
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz
import traceback
import logging

from src.utils import get_data_path, load_config, load_env, setup_logging, load_json
from src.automation import (
    get_effective_pipeline_state,
    get_effective_upload_date,
    get_weekly_idea_config,
    get_pipeline_skip_message,
    is_pipeline_uploadable,
    run_zotero_upload,
    run_weekly_idea_generation,
    validate_weekly_idea_environment,
    validate_zotero_upload_environment,
    wait_for_zotero_artifacts,
    WeeklyIdeaSkippedError,
    ZoteroUploadSkippedError,
)
from src.notifier import EmailNotifier
from main import main as run_daily_task


def scheduled_task(logger=None, notifier=None):
    """定时执行的任务"""
    start_time = datetime.now()
    
    print("\n" + "=" * 60)
    print(f"⏰ 定时任务触发 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    if logger:
        logger.info(f"定时任务开始执行 - {start_time}")
    
    try:
        # 执行主任务
        run_daily_task()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "=" * 60)
        print(f"✅ 任务执行成功！")
        print(f"⏱️  耗时: {duration:.2f} 秒")
        print(f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60 + "\n")
        
        if logger:
            logger.info(f"定时任务执行成功，耗时 {duration:.2f} 秒")
        
        # 发送成功通知
        if notifier:
            try:
                # 读取统计信息
                current_config = load_config()
                papers_path = Path(get_data_path(current_config, 'papers')) / 'latest.json'
                stats = load_json(str(papers_path))
                summaries_data = load_json('data/summaries/latest.json')
                papers = stats.get('papers', []) if stats else []
                summaries = summaries_data.get('papers', []) if summaries_data else []
                stats_info = {
                    'papers_count': len(papers),
                    'summaries_count': len(summaries),
                    'categories_count': len(set(p.get('primary_category', '') for p in papers)) if papers else 0,
                    'keywords_count': 50  # 从分析结果获取
                }
                notifier.send_notification(success=True, stats=stats_info, duration=duration)
            except Exception as e:
                logger.warning(f"发送邮件通知失败: {str(e)}")
        
        return True
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "=" * 60)
        print(f"❌ 任务执行失败！")
        print(f"⏱️  耗时: {duration:.2f} 秒")
        print(f"🔴 错误: {str(e)}")
        print("=" * 60)
        print("\n详细错误信息:")
        traceback.print_exc()
        print()
        
        if logger:
            logger.error(f"定时任务执行失败: {str(e)}", exc_info=True)
        
        # 发送失败通知
        if notifier:
            try:
                notifier.send_notification(
                    success=False,
                    error_msg=f"{str(e)}\n\n{traceback.format_exc()}",
                    duration=duration
                )
            except Exception as email_error:
                logger.warning(f"发送邮件通知失败: {str(email_error)}")
        
        return False


def scheduled_zotero_upload_task(logger=None):
    """定时执行 Zotero 上传任务"""
    start_time = datetime.now()

    print("\n" + "=" * 60)
    print(f"📚 Zotero 上传任务触发 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    if logger:
        logger.info(f"Zotero 上传任务开始执行 - {start_time}")

    try:
        load_env()
        config = load_config()
        pipeline_state = get_effective_pipeline_state(config)
        if not is_pipeline_uploadable(pipeline_state):
            message = get_pipeline_skip_message(pipeline_state)
            print(message)
            if logger:
                logger.info(message)
            return True

        upload_date = pipeline_state["run_date"]
        wait_for_zotero_artifacts(config, upload_date, logger=logger)
        run_zotero_upload(config, logger=logger, date_str=upload_date)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "=" * 60)
        print("✅ Zotero 上传任务执行成功！")
        print(f"⏱️  耗时: {duration:.2f} 秒")
        print(f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60 + "\n")

        if logger:
            logger.info(f"Zotero 上传任务执行成功，耗时 {duration:.2f} 秒")

        return True

    except ZoteroUploadSkippedError as e:
        print(str(e))
        if logger:
            logger.info(str(e))
        return True

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "=" * 60)
        print("❌ Zotero 上传任务执行失败！")
        print(f"⏱️  耗时: {duration:.2f} 秒")
        print(f"🔴 错误: {str(e)}")
        print("=" * 60)
        print("\n详细错误信息:")
        traceback.print_exc()
        print()

        if logger:
            logger.error(f"Zotero 上传任务执行失败: {str(e)}", exc_info=True)

        return False


def scheduled_weekly_idea_task(logger=None):
    """定时执行周度综述与 idea 任务。"""
    start_time = datetime.now()

    print("\n" + "=" * 60)
    print(f"💡 周度 idea 任务触发 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    if logger:
        logger.info(f"周度 idea 任务开始执行 - {start_time}")

    try:
        load_env()
        config = load_config()
        log_path = run_weekly_idea_generation(config, logger=logger)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "=" * 60)
        print("✅ 周度 idea 任务执行成功！")
        print(f"⏱️  耗时: {duration:.2f} 秒")
        print(f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60 + "\n")

        if logger:
            logger.info(f"周度 idea 任务执行成功，耗时 {duration:.2f} 秒，日志: {log_path}")

        return True

    except WeeklyIdeaSkippedError as e:
        print(str(e))
        if logger:
            logger.info(str(e))
        return True

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "=" * 60)
        print("❌ 周度 idea 任务执行失败！")
        print(f"⏱️  耗时: {duration:.2f} 秒")
        print(f"🔴 错误: {str(e)}")
        print("=" * 60)
        print("\n详细错误信息:")
        traceback.print_exc()
        print()

        if logger:
            logger.error(f"周度 idea 任务执行失败: {str(e)}", exc_info=True)

        return False


def parse_run_time(run_time: str):
    """解析 HH:MM 运行时间。"""
    try:
        hour, minute = map(int, run_time.split(":"))
    except ValueError as exc:
        raise ValueError(f"无效的运行时间格式: {run_time}，应为 HH:MM 格式") from exc

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"无效的运行时间范围: {run_time}")

    return hour, minute


def calculate_next_run(hour: int, minute: int, tz):
    """计算下次运行时间。"""
    from datetime import timedelta

    now = datetime.now(tz)
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def main():
    """主函数"""
    # 加载配置
    load_env()
    config = load_config()
    logger = setup_logging(config)
    
    scheduler_config = config.get('scheduler', {})
    
    if not scheduler_config.get('enabled', False):
        logger.warning("定时调度未启用，请在 config.yaml 中设置 scheduler.enabled = true")
        print("\n⚠️  定时调度未启用")
        print("请在 config/config.yaml 中设置:")
        print("  scheduler:")
        print("    enabled: true")
        return
    
    # 获取配置
    run_time = scheduler_config.get('run_time', '09:00')
    timezone = scheduler_config.get('timezone', 'Asia/Shanghai')
    run_on_start = scheduler_config.get('run_on_start', True)
    
    try:
        hour, minute = parse_run_time(run_time)
    except ValueError as e:
        logger.error(str(e))
        print(f"❌ {str(e)}")
        print("请使用 HH:MM 格式，例如: 09:00")
        return
    
    tz = pytz.timezone(timezone)
    
    # 创建调度器
    scheduler = BlockingScheduler(timezone=tz)
    
    # 添加定时任务
    trigger = CronTrigger(
        hour=hour,
        minute=minute,
        timezone=tz
    )
    
    # 初始化邮件通知器
    notifier = None
    notification_config = scheduler_config.get('notification', {})
    if notification_config.get('enabled', False):
        email_config = notification_config.get('email', {})
        notifier = EmailNotifier(email_config)
        logger.info("邮件通知已启用")
    
    scheduler.add_job(
        scheduled_task,
        trigger=trigger,
        args=[logger, notifier],
        id='daily_arxiv_task',
        name='Daily arXiv Paper Fetching',
        max_instances=1,
        coalesce=True
    )
    
    next_run = calculate_next_run(hour, minute, tz)

    zotero_job_added = False
    zotero_next_run = None
    zotero_run_time = None
    zotero_run_on_start = False
    zotero_config = scheduler_config.get('zotero_upload', {})
    weekly_job_added = False
    weekly_next_run = None
    weekly_run_time = None
    weekly_run_on_start = False
    weekly_config = get_weekly_idea_config(config)

    if zotero_config.get('enabled', False):
        zotero_run_time = zotero_config.get('run_time', '09:30')
        zotero_run_on_start = zotero_config.get('run_on_start', False)

        try:
            zotero_hour, zotero_minute = parse_run_time(zotero_run_time)
            validate_zotero_upload_environment(config)
        except Exception as e:
            logger.error(f"Zotero 上传任务未加入调度: {str(e)}")
            print(f"⚠️  Zotero 上传任务未加入调度: {str(e)}")
        else:
            scheduler.add_job(
                scheduled_zotero_upload_task,
                trigger=CronTrigger(hour=zotero_hour, minute=zotero_minute, timezone=tz),
                args=[logger],
                id='daily_zotero_upload_task',
                name='Daily Zotero Upload',
                max_instances=1,
                coalesce=True
            )
            zotero_next_run = calculate_next_run(zotero_hour, zotero_minute, tz)
            zotero_job_added = True
            logger.info(
                f"Zotero 上传任务已加入调度，将在每天 {zotero_run_time} ({timezone}) 执行"
            )

    if weekly_config.get('enabled', False):
        weekly_run_time = weekly_config.get('run_time', '10:00')
        weekly_run_on_start = weekly_config.get('run_on_start', False)
        weekly_weekday = weekly_config.get('day_of_week', 'thu')

        try:
            weekly_hour, weekly_minute = parse_run_time(weekly_run_time)
            validate_weekly_idea_environment(config)
        except Exception as e:
            logger.error(f"周度 idea 任务未加入调度: {str(e)}")
            print(f"⚠️  周度 idea 任务未加入调度: {str(e)}")
        else:
            weekly_trigger = CronTrigger(
                day_of_week=weekly_weekday,
                hour=weekly_hour,
                minute=weekly_minute,
                timezone=tz,
            )
            scheduler.add_job(
                scheduled_weekly_idea_task,
                trigger=weekly_trigger,
                args=[logger],
                id='weekly_idea_task',
                name='Weekly Zotero Idea Generation',
                max_instances=1,
                coalesce=True,
            )
            weekly_next_run = weekly_trigger.get_next_fire_time(None, datetime.now(tz))
            weekly_job_added = True
            logger.info(
                "周度 idea 任务已加入调度，将在每周 %s %s (%s) 执行",
                weekly_weekday,
                weekly_run_time,
                timezone,
            )

    logger.info(f"定时调度器已启动，将在每天 {run_time} ({timezone}) 执行任务")
    print("\n" + "=" * 60)
    print("⏰ Daily arXiv 定时调度器")
    print("=" * 60)
    print(f"📅 执行时间: 每天 {run_time}")
    print(f"🌍 时区: {timezone}")
    print(f"⏭️  下次运行: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔄 启动时立即运行: {'是' if run_on_start else '否'}")
    if zotero_job_added and zotero_next_run and zotero_run_time:
        print(f"📚 Zotero 上传: 每天 {zotero_run_time}")
        print(f"⏭️  Zotero 下次运行: {zotero_next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔄 Zotero 启动时立即运行: {'是' if zotero_run_on_start else '否'}")
    if weekly_job_added and weekly_next_run and weekly_run_time:
        print(f"💡 周度 idea: 每周四 {weekly_run_time}")
        print(f"⏭️  周度 idea 下次运行: {weekly_next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔄 周度 idea 启动时立即运行: {'是' if weekly_run_on_start else '否'}")
    print("=" * 60)
    print("\n按 Ctrl+C 停止调度器\n")
    
    # 启动时立即运行一次
    if run_on_start:
        logger.info("启动时立即执行任务...")
        print("🚀 启动时立即执行任务...\n")
        scheduled_task(logger, notifier)

    if zotero_job_added and zotero_run_on_start:
        logger.info("启动时立即执行 Zotero 上传任务...")
        print("📚 启动时立即执行 Zotero 上传任务...\n")
        scheduled_zotero_upload_task(logger)

    if weekly_job_added and weekly_run_on_start:
        logger.info("启动时立即执行周度 idea 任务...")
        print("💡 启动时立即执行周度 idea 任务...\n")
        scheduled_weekly_idea_task(logger)
    
    try:
        # 启动调度器
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("定时调度器已停止")
        print("\n" + "=" * 60)
        print("👋 定时调度器已停止")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
