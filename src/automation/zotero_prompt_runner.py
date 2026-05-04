"""使用 CLI (Copilot/Claude/Codex) + Zotero MCP 执行每日 Zotero 上传任务。"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

import pytz

from src.automation.cli_runner import (
    PROJECT_ROOT,
    build_cli_command,
    get_configured_mcp_servers,
    resolve_project_path,
    validate_cli_environment,
)
from src.utils import get_current_datetime, get_data_path, get_date_string, load_json
DEFAULT_PROMPT_FILE = Path("config/prompts/zotero_daily_upload_prompt.txt")
PIPELINE_STATE_FILE = PROJECT_ROOT / "data/runtime/pipeline_state.json"
PIPELINE_UPLOADABLE_STATUSES = {"running", "completed"}
STALE_RUNNING_STATE_MAX_AGE = timedelta(hours=3)


class DailyArtifactsNotReadyError(RuntimeError):
    """当天的输入文件尚未就绪。"""


class ZoteroUploadSkippedError(RuntimeError):
    """当前主流程状态不适合继续执行 Zotero 上传。"""


def get_pipeline_skip_message(pipeline_state: Dict[str, Any]) -> str:
    """格式化跳过 Zotero 上传的原因。"""
    return (
        "⏭️ 跳过 Zotero 上传：主流程状态不可上传"
        f"（status={pipeline_state.get('status') or 'missing'}, "
        f"run_id={pipeline_state.get('run_id') or 'N/A'}）"
    )


def _parse_iso_datetime(value: Any) -> datetime | None:
    """解析 ISO 时间戳。"""
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _align_datetime_timezone(reference: datetime, value: datetime) -> tuple[datetime, datetime]:
    """对齐 datetime 的时区信息，便于比较。"""
    if reference.tzinfo and value.tzinfo is None:
        value = value.replace(tzinfo=reference.tzinfo)
    elif reference.tzinfo is None and value.tzinfo:
        reference = reference.replace(tzinfo=value.tzinfo)

    return reference, value


def _is_recent_cross_midnight_state(
    config: Dict[str, Any],
    pipeline_state: Dict[str, Any],
    run_date: str | None,
    status: str | None,
) -> bool:
    """判断是否为应继续沿用的跨午夜状态。"""
    if status not in PIPELINE_UPLOADABLE_STATUSES or not run_date:
        return False

    try:
        run_day = datetime.strptime(run_date, "%Y-%m-%d").date()
    except ValueError:
        return False

    current_datetime = get_current_datetime(config)
    if current_datetime.date() != run_day + timedelta(days=1):
        return False

    timestamp_key = "completed_at" if status == "completed" else "started_at"
    state_datetime = _parse_iso_datetime(pipeline_state.get(timestamp_key))
    if state_datetime is None:
        return False

    current_datetime, state_datetime = _align_datetime_timezone(current_datetime, state_datetime)
    if state_datetime > current_datetime:
        return False

    return current_datetime - state_datetime <= timedelta(hours=6)


def _is_stale_running_state(
    config: Dict[str, Any],
    pipeline_state: Dict[str, Any],
    target_date: str,
) -> bool:
    """判断同日 running 状态是否已经失效。"""
    if pipeline_state.get("status") != "running":
        return False
    if pipeline_state.get("run_date") != target_date:
        return False

    started_at = _parse_iso_datetime(pipeline_state.get("started_at"))
    if started_at is None:
        return True

    current_datetime, started_at = _align_datetime_timezone(
        get_current_datetime(config), started_at
    )
    if started_at > current_datetime:
        return True

    return current_datetime - started_at > STALE_RUNNING_STATE_MAX_AGE


def is_pipeline_uploadable(pipeline_state: Dict[str, Any]) -> bool:
    """判断当前主流程状态是否允许启动 Zotero 上传。"""
    return (
        pipeline_state.get("status") in PIPELINE_UPLOADABLE_STATUSES
        and bool(pipeline_state.get("run_id"))
    )


def get_zotero_upload_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取 Zotero 上传任务配置。"""
    return config.get("scheduler", {}).get("zotero_upload", {})


def resolve_project_path(path_value: str | Path) -> Path:
    """将相对路径解析到项目根目录。"""
    root = PROJECT_ROOT.resolve()
    path = Path(path_value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"路径必须位于项目目录内: {resolved}") from exc

    return resolved


def resolve_data_path(path_value: str | Path) -> Path:
    """解析数据路径，支持相对路径和绝对路径。"""
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _require_file(filepath: Path, label: str) -> Path:
    """确保文件存在。"""
    if not filepath.exists():
        raise FileNotFoundError(f"{label}不存在: {filepath}")
    return filepath


def _require_daily_json(
    filepath: Path,
    label: str,
    date_str: str,
    run_id: str | None = None,
) -> Path:
    """确保 latest.json 对应的是当天数据。"""
    if not filepath.exists():
        raise DailyArtifactsNotReadyError(f"{label}不存在: {filepath}")

    try:
        data = load_json(str(filepath))
    except json.JSONDecodeError as exc:
        raise DailyArtifactsNotReadyError(f"{label}正在写入中: {filepath}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label}格式错误，期望为 JSON 对象: {filepath}")

    actual_date = data.get("date")
    if actual_date != date_str:
        raise DailyArtifactsNotReadyError(
            f"{label}日期不匹配，期望 {date_str}，实际为 {actual_date or '缺失'}: {filepath}"
        )

    if run_id and data.get("run_id") != run_id:
        raise DailyArtifactsNotReadyError(
            f"{label}运行ID不匹配，期望 {run_id}，实际为 {data.get('run_id') or '缺失'}: {filepath}"
        )

    return filepath


def _validate_report_file(
    report_path: Path,
    label: str,
    date_str: str,
    run_id: str | None = None,
) -> Path:
    """校验 Markdown 报告内容是否对应目标日期。"""
    content = report_path.read_text(encoding="utf-8")
    date_markers = [
        f"**生成日期**: {date_str}",
        f"**日期**: {date_str}",
    ]
    if not any(marker in content for marker in date_markers):
        raise DailyArtifactsNotReadyError(f"{label}日期内容不匹配: {report_path}")

    if run_id and f"**运行ID**: {run_id}" not in content:
        raise DailyArtifactsNotReadyError(f"{label}运行ID不匹配: {report_path}")

    return report_path


def _require_daily_report(
    report_dir: Path,
    label: str,
    date_str: str,
    run_id: str | None = None,
) -> Path:
    """确保当天 Markdown 报告存在。"""
    report_path = report_dir / f"report_{date_str}.md"
    if not report_path.exists():
        raise DailyArtifactsNotReadyError(f"{label}不存在: {report_path}")
    return _validate_report_file(report_path, label, date_str, run_id=run_id)


def get_zotero_upload_date(config: Dict[str, Any], date_str: str | None = None) -> str:
    """根据调度时区获取当天日期。"""
    if date_str:
        return date_str

    timezone = config.get("scheduler", {}).get("timezone", "").strip()
    if timezone:
        tz = pytz.timezone(timezone)
        return datetime.now(tz).strftime("%Y-%m-%d")

    return get_date_string(config=config)


def get_effective_upload_date(config: Dict[str, Any], date_str: str | None = None) -> str:
    """获取应上传的目标日期，优先参考主流程运行状态。"""
    return get_effective_pipeline_state(config, date_str=date_str).get("run_date")


def get_effective_pipeline_state(
    config: Dict[str, Any],
    date_str: str | None = None,
) -> Dict[str, Any]:
    """获取应消费的主流程运行状态。"""
    today = get_zotero_upload_date(config)
    target_date = date_str or today
    pipeline_state = load_json(str(PIPELINE_STATE_FILE))
    if not isinstance(pipeline_state, dict):
        return {"run_date": target_date, "run_id": None, "status": None}

    run_date = pipeline_state.get("run_date")
    run_id = pipeline_state.get("run_id")
    status = pipeline_state.get("status")
    if _is_stale_running_state(config, pipeline_state, today):
        return {"run_date": today, "run_id": None, "status": "stale_running"}

    if date_str:
        if run_date == target_date:
            return {"run_date": run_date, "run_id": run_id, "status": status}
        return {"run_date": target_date, "run_id": None, "status": None}

    if run_date == today:
        return {"run_date": run_date, "run_id": run_id, "status": status}

    if _is_recent_cross_midnight_state(config, pipeline_state, run_date, status):
        return {"run_date": run_date, "run_id": run_id, "status": status}

    return {"run_date": today, "run_id": None, "status": None}


def build_zotero_upload_prompt(config: Dict[str, Any], date_str: str | None = None) -> str:
    """构建每日 Zotero 上传提示词。"""
    pipeline_state = get_effective_pipeline_state(config, date_str=date_str)
    current_date = pipeline_state["run_date"]
    input_files = get_daily_input_files(
        config,
        current_date,
        run_id=pipeline_state.get("run_id"),
    )
    return build_zotero_upload_prompt_from_files(config, current_date, input_files)


def get_daily_input_files(
    config: Dict[str, Any],
    date_str: str,
    run_id: str | None = None,
) -> Dict[str, Path]:
    """获取并校验当天需要上传的输入文件。"""
    return {
        "papers_json": _require_daily_json(
            resolve_data_path(get_data_path(config, "papers")) / "latest.json",
            "论文元数据文件",
            date_str,
            run_id=run_id,
        ),
        "summaries_json": _require_daily_json(
            PROJECT_ROOT / "data/summaries/latest.json",
            "论文总结文件",
            date_str,
            run_id=run_id,
        ),
        "analysis_report": _require_daily_report(
            PROJECT_ROOT / "data/analysis",
            "分析报告",
            date_str,
            run_id=run_id,
        ),
        "summaries_report": _require_daily_report(
            PROJECT_ROOT / "data/summaries",
            "总结报告",
            date_str,
            run_id=run_id,
        ),
    }


def build_zotero_upload_prompt_from_files(
    config: Dict[str, Any],
    current_date: str,
    input_files: Dict[str, Path],
) -> str:
    """基于指定文件路径构建每日 Zotero 上传提示词。"""
    zotero_config = get_zotero_upload_config(config)
    prompt_file = resolve_project_path(
        zotero_config.get("prompt_file", str(DEFAULT_PROMPT_FILE))
    )

    template = _require_file(prompt_file, "Zotero 上传提示词模板").read_text(
        encoding="utf-8"
    )

    return template.format(
        current_date=current_date,
        project_root=PROJECT_ROOT,
        data_dir=PROJECT_ROOT / "data",
        papers_json=input_files["papers_json"],
        summaries_json=input_files["summaries_json"],
        analysis_report=input_files["analysis_report"],
        summaries_report=input_files["summaries_report"],
    )


def _build_copilot_command(
    prompt: str,
    zotero_config: Dict[str, Any],
    mcp_servers: list[str],
    input_dir: Path,
) -> list[str]:
    """构建 CLI 命令。"""
    command = zotero_config.get("copilot_command", "copilot")
    model = zotero_config.get("model", "").strip()
    reasoning_effort = zotero_config.get("reasoning_effort", "").strip()

    return build_cli_command(
        command=command,
        prompt=prompt,
        configured_mcp_servers=mcp_servers,
        required_mcp_servers=["zotero"],
        add_dirs=[input_dir],
        model=model,
        reasoning_effort=reasoning_effort,
    )


def _write_run_log(
    log_dir: Path,
    timestamp: str,
    command: list[str],
    prompt: str,
    stdout: str | None,
    stderr: str | None,
    exit_code: int | None,
) -> Path:
    """保存执行日志。"""
    from src.automation.cli_runner import write_run_log
    return write_run_log(
        log_dir=log_dir,
        filename_prefix="zotero_upload",
        timestamp=timestamp,
        command=command,
        prompt=prompt,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
    )


def validate_zotero_upload_environment(config: Dict[str, Any]):
    """校验 CLI 和 Zotero MCP 是否可用。"""
    zotero_config = get_zotero_upload_config(config)
    command = zotero_config.get("copilot_command", "copilot")
    print(f"🔍 检查 CLI 命令: {command}")

    validate_cli_environment(
        command=command,
        required_mcp_servers=["zotero"],
    )




def wait_for_zotero_artifacts(
    config: Dict[str, Any],
    upload_date: str,
    logger=None,
):
    """等待当天的上传输入就绪，避免与主流程竞争。"""
    zotero_config = get_zotero_upload_config(config)
    max_wait_minutes = int(zotero_config.get("artifact_wait_minutes", 90))
    check_interval_seconds = int(
        zotero_config.get("artifact_check_interval_seconds", 60)
    )
    deadline = time.time() + max_wait_minutes * 60
    last_error = None

    while time.time() <= deadline:
        pipeline_state = get_effective_pipeline_state(config, date_str=upload_date)
        if pipeline_state.get("run_date") == upload_date and not is_pipeline_uploadable(
            pipeline_state
        ):
            raise ZoteroUploadSkippedError(get_pipeline_skip_message(pipeline_state))

        try:
            build_zotero_upload_prompt(config, date_str=upload_date)
            return
        except DailyArtifactsNotReadyError as exc:
            last_error = exc
            if logger:
                logger.warning(
                    "Zotero 上传输入尚未就绪，将在 %s 秒后重试: %s",
                    check_interval_seconds,
                    exc,
                )
            time.sleep(check_interval_seconds)

    raise RuntimeError(
        f"等待当天 Zotero 上传输入超时（>{max_wait_minutes} 分钟）: {last_error}"
    )


def run_zotero_upload(
    config: Dict[str, Any],
    logger=None,
    date_str: str | None = None,
) -> Path:
    """执行每日 Zotero 上传任务。"""
    zotero_config = get_zotero_upload_config(config)
    validate_zotero_upload_environment(config)
    command = zotero_config.get("copilot_command", "copilot")
    mcp_servers = get_configured_mcp_servers(command)
    timestamp = get_current_datetime(config).strftime("%Y%m%d_%H%M%S")
    timeout_minutes = int(zotero_config.get("timeout_minutes", 45))
    log_dir = resolve_project_path(zotero_config.get("log_dir", "logs/zotero_upload"))
    prompt_path = log_dir / f"zotero_upload_prompt_{timestamp}.txt"
    workspace_dir = log_dir / f"workspace_{timestamp}"
    input_dir = workspace_dir / "inputs"
    pipeline_state = get_effective_pipeline_state(config, date_str=date_str)
    if not is_pipeline_uploadable(pipeline_state):
        raise ZoteroUploadSkippedError(get_pipeline_skip_message(pipeline_state))
    upload_date = pipeline_state["run_date"]
    run_id = pipeline_state.get("run_id")
    source_files = get_daily_input_files(config, upload_date, run_id=run_id)

    log_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)

    staged_files = {
        "papers_json": input_dir / "papers_latest.json",
        "summaries_json": input_dir / "summaries_latest.json",
        "analysis_report": input_dir / "analysis_report.md",
        "summaries_report": input_dir / "summaries_report.md",
    }
    for key, target_path in staged_files.items():
        shutil.copy2(source_files[key], target_path)

    _require_daily_json(
        staged_files["papers_json"], "论文元数据文件", upload_date, run_id=run_id
    )
    _require_daily_json(
        staged_files["summaries_json"], "论文总结文件", upload_date, run_id=run_id
    )
    _validate_report_file(
        staged_files["analysis_report"], "分析报告", upload_date, run_id=run_id
    )
    _validate_report_file(
        staged_files["summaries_report"], "总结报告", upload_date, run_id=run_id
    )

    prompt = build_zotero_upload_prompt_from_files(config, upload_date, staged_files)
    command = _build_copilot_command(prompt, zotero_config, mcp_servers, input_dir)
    prompt_path.write_text(prompt, encoding="utf-8")

    if logger:
        logger.info("开始执行每日 Zotero 上传任务")
        logger.info("提示词快照已保存到: %s", prompt_path)

    final_state = get_effective_pipeline_state(config, date_str=upload_date)
    if not is_pipeline_uploadable(final_state):
        raise ZoteroUploadSkippedError(get_pipeline_skip_message(final_state))
    if final_state.get("run_id") != run_id:
        raise ZoteroUploadSkippedError(
            "⏭️ 跳过 Zotero 上传：主流程运行ID已变化"
            f"（expected={run_id}, actual={final_state.get('run_id') or 'N/A'}）"
        )

    try:
        result = subprocess.run(
            command,
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_minutes * 60,
        )
    except subprocess.TimeoutExpired as exc:
        log_path = _write_run_log(
            log_dir=log_dir,
            timestamp=timestamp,
            command=command,
            prompt=prompt,
            stdout=exc.stdout,
            stderr=exc.stderr,
            exit_code=None,
        )
        raise RuntimeError(
            f"每日 Zotero 上传任务超时（>{timeout_minutes} 分钟），详见日志: {log_path}"
        ) from exc

    log_path = _write_run_log(
        log_dir=log_dir,
        timestamp=timestamp,
        command=command,
        prompt=prompt,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode,
    )

    if result.returncode != 0:
        raise RuntimeError(f"每日 Zotero 上传任务失败，详见日志: {log_path}")

    if logger:
        logger.info("每日 Zotero 上传任务完成，执行日志: %s", log_path)

    return log_path
