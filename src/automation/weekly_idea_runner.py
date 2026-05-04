"""Weekly Zotero idea generation runner."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.automation.cli_runner import (
    PROJECT_ROOT,
    build_cli_command,
    get_configured_mcp_servers,
    resolve_project_path,
    validate_cli_environment,
    write_run_log,
)
from src.utils import get_current_datetime, save_json, save_text, load_json


DEFAULT_PROMPT_FILE = Path("config/prompts/weekly_zotero_idea_prompt.txt")
WEEKDAY_TO_INDEX = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


class WeeklyIdeaSkippedError(RuntimeError):
    """Raised when there is no weekly material to process."""


def get_weekly_idea_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return scheduler config for the weekly idea task."""
    return config.get("scheduler", {}).get("weekly_idea", {})


def _get_weekly_anchor_weekday(config: dict[str, Any]) -> int:
    """Return the configured weekly anchor weekday as a Python weekday index."""
    weekday_name = str(get_weekly_idea_config(config).get("day_of_week", "thu")).strip().lower()
    weekday_index = WEEKDAY_TO_INDEX.get(weekday_name)
    if weekday_index is None:
        raise ValueError(f"weekly_idea.day_of_week 配置无效: {weekday_name}")
    return weekday_index


def get_week_range(
    config: dict[str, Any], reference_datetime: datetime | None = None
) -> tuple[str, str]:
    """Return the last completed weekly window anchored to the configured weekday."""
    current_datetime = reference_datetime or get_current_datetime(config)
    anchor_weekday = _get_weekly_anchor_weekday(config)
    end_date = current_datetime.date() - timedelta(
        days=(current_datetime.date().weekday() - anchor_weekday) % 7
    )
    start_date = end_date - timedelta(days=7)
    return start_date.isoformat(), end_date.isoformat()


def _collect_weekly_material(config: dict[str, Any]) -> dict[str, Any]:
    week_start, week_end = get_week_range(config)

    weekly_days: list[dict[str, Any]] = []
    start_dt = datetime.fromisoformat(week_start).date()
    end_dt = datetime.fromisoformat(week_end).date()
    total_papers = 0

    day = start_dt
    while day <= end_dt:
        date_str = day.isoformat()
        papers_path = PROJECT_ROOT / "data" / "papers" / f"papers_{date_str}.json"
        summaries_path = PROJECT_ROOT / "data" / "summaries" / f"summaries_{date_str}.json"
        papers = load_json(str(papers_path)) if papers_path.exists() else []
        summaries = load_json(str(summaries_path)) if summaries_path.exists() else []

        if isinstance(papers, list) and papers:
            summary_map = {}
            if isinstance(summaries, list):
                for item in summaries:
                    if isinstance(item, dict):
                        paper_id = str(item.get("paper_id") or item.get("id") or "").strip()
                        if paper_id:
                            summary_map[paper_id] = item

            merged_papers = []
            for paper in papers:
                paper_id = str(paper.get("paper_id") or paper.get("id") or "").strip()
                summary_item = summary_map.get(paper_id, {})
                merged_papers.append(
                    {
                        "paper_id": paper_id,
                        "title": paper.get("title"),
                        "categories": paper.get("categories", []),
                        "abstract": paper.get("abstract", ""),
                        "summary_zh": summary_item.get("summary", ""),
                        "summary_en": summary_item.get("summary_en", ""),
                        "structured_summary": summary_item.get("structured_summary", {}),
                    }
                )

            weekly_days.append({"date": date_str, "papers": merged_papers})
            total_papers += len(merged_papers)

        day += timedelta(days=1)

    if total_papers == 0:
        raise WeeklyIdeaSkippedError("本周还没有可用于周报与选题构思的论文数据")

    return {
        "week_start": week_start,
        "week_end": week_end,
        "day_count": len(weekly_days),
        "paper_count": total_papers,
        "days": weekly_days,
    }


def validate_weekly_idea_environment(config: dict[str, Any]):
    """Ensure the weekly idea job can run."""
    agent_config = config.get("agent", {})
    command = agent_config.get("copilot_command", "copilot")
    validate_cli_environment(command=command, required_mcp_servers=["zotero"])


def run_weekly_idea_generation(config: dict[str, Any], logger=None) -> Path:
    """Run the weekly synthesis + idea job."""
    weekly_config = get_weekly_idea_config(config)
    if not weekly_config.get("enabled", False):
        raise WeeklyIdeaSkippedError("周度 idea 任务未启用")

    validate_weekly_idea_environment(config)
    weekly_material = _collect_weekly_material(config)

    agent_config = config.get("agent", {})
    command = agent_config.get("copilot_command", "copilot")
    model = agent_config.get("model", "")
    reasoning_effort = agent_config.get("reasoning_effort", "high")
    timeout_minutes = int(weekly_config.get("timeout_minutes", 120))
    prompt_file = resolve_project_path(
        weekly_config.get("prompt_file", str(DEFAULT_PROMPT_FILE))
    )
    log_dir = resolve_project_path(weekly_config.get("log_dir", "logs/weekly_idea"))
    collection_name = weekly_config.get("collection_name", "idea")
    focus_keywords = weekly_config.get("focus_keywords", [])
    if isinstance(focus_keywords, str):
        focus_keywords = [focus_keywords]
    focus_keywords = [
        str(keyword).strip() for keyword in focus_keywords if str(keyword).strip()
    ]
    focus_keywords_block = (
        "\n".join(f"- {keyword}" for keyword in focus_keywords)
        if focus_keywords
        else "- No extra keyword restriction configured."
    )

    timestamp = get_current_datetime(config).strftime("%Y%m%d_%H%M%S")
    workspace_dir = log_dir / f"workspace_{timestamp}"
    inputs_dir = workspace_dir / "inputs"
    outputs_dir = workspace_dir / "outputs"
    input_json_path = inputs_dir / "weekly_input.json"
    output_json_path = outputs_dir / "weekly_idea.json"
    output_markdown_path = outputs_dir / "weekly_idea.md"
    prompt_snapshot = log_dir / f"weekly_idea_prompt_{timestamp}.txt"

    log_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    save_json(weekly_material, str(input_json_path))
    prompt = prompt_file.read_text(encoding="utf-8").format(
        current_date=get_current_datetime(config).date().isoformat(),
        week_start=weekly_material["week_start"],
        week_end=weekly_material["week_end"],
        weekly_input_json=input_json_path,
        output_json=output_json_path,
        output_markdown=output_markdown_path,
        idea_collection=collection_name,
        focus_keywords_block=focus_keywords_block,
    )
    prompt_snapshot.write_text(prompt, encoding="utf-8")

    configured_mcp_servers = get_configured_mcp_servers(command)
    cli_command = build_cli_command(
        command=command,
        prompt=prompt,
        configured_mcp_servers=configured_mcp_servers,
        required_mcp_servers=["zotero"],
        add_dirs=[inputs_dir, outputs_dir],
        model=model,
        reasoning_effort=reasoning_effort,
    )

    try:
        result = subprocess.run(
            cli_command,
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_minutes * 60,
        )
    except subprocess.TimeoutExpired as exc:
        log_path = write_run_log(
            log_dir=log_dir,
            filename_prefix="weekly_idea",
            timestamp=timestamp,
            command=cli_command,
            prompt=prompt,
            stdout=exc.stdout,
            stderr=exc.stderr,
            exit_code=None,
        )
        raise RuntimeError(
            f"周度 idea 任务超时（>{timeout_minutes} 分钟），详见日志: {log_path}"
        ) from exc

    log_path = write_run_log(
        log_dir=log_dir,
        filename_prefix="weekly_idea",
        timestamp=timestamp,
        command=cli_command,
        prompt=prompt,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode,
    )
    if result.returncode != 0:
        raise RuntimeError(f"周度 idea 任务失败，详见日志: {log_path}")

    if not output_json_path.exists() or not output_markdown_path.exists():
        raise FileNotFoundError("周度 idea 任务未生成预期的本地输出文件")

    with output_json_path.open("r", encoding="utf-8") as file_obj:
        output_payload = json.load(file_obj)
    if not isinstance(output_payload, dict) or not output_payload.get("idea_title"):
        raise ValueError("周度 idea 输出格式不完整，缺少 idea_title")

    data_dir = PROJECT_ROOT / "data" / "ideas"
    data_dir.mkdir(parents=True, exist_ok=True)
    basename = f"idea_{weekly_material['week_start']}_to_{weekly_material['week_end']}"
    save_json(output_payload, str(data_dir / f"{basename}.json"))
    save_json(output_payload, str(data_dir / "latest.json"))
    save_text(output_markdown_path.read_text(encoding="utf-8"), str(data_dir / f"{basename}.md"))
    save_text(output_markdown_path.read_text(encoding="utf-8"), str(data_dir / "latest.md"))

    if logger:
        logger.info("周度 idea 任务完成，执行日志: %s", log_path)

    return log_path
