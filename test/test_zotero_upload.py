#!/usr/bin/env python3
"""
测试 Zotero 上传任务配置

检查 Copilot CLI、Zotero MCP 和提示词构建是否可用。
"""

import json
import sys
from datetime import timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.automation import validate_zotero_upload_environment
from src.automation.zotero_prompt_runner import (
    PIPELINE_STATE_FILE,
    build_zotero_upload_prompt_from_files,
    get_effective_pipeline_state,
    get_daily_input_files,
    is_pipeline_uploadable,
)
from src.utils import get_current_datetime, get_data_path, load_config, load_env


def test_zotero_upload_config():
    """测试配置项与提示词构建。"""
    print("\n" + "=" * 60)
    print("🧪 测试 Zotero 上传配置")
    print("=" * 60)

    load_env()
    config = load_config()
    zotero_config = config.get("scheduler", {}).get("zotero_upload", {})

    required_keys = ["enabled", "run_time", "prompt_file", "copilot_command"]
    all_present = True

    for key in required_keys:
        if key in zotero_config and zotero_config[key] != "":
            print(f"  ✅ {key}: {zotero_config[key]}")
        else:
            print(f"  ❌ {key}: 未配置")
            all_present = False

    if not all_present:
        return False

    papers_dir = Path(get_data_path(config, "papers"))
    papers_path = papers_dir if papers_dir.is_absolute() else (project_root / papers_dir)
    latest_papers = json.loads((papers_path / "latest.json").read_text(encoding="utf-8"))
    input_files = get_daily_input_files(config, latest_papers["date"], run_id=None)
    prompt = build_zotero_upload_prompt_from_files(
        config,
        latest_papers["date"],
        input_files,
    )
    prompt_checks = [
        ("papers/latest.json", str(papers_path / "latest.json") in prompt),
        ("summaries/latest.json", "data/summaries/latest.json" in prompt),
        ("analysis report", "data/analysis/report_" in prompt),
        ("daily analysis collection", '"daily analysis"' in prompt),
        ("english note field remains optional", "zotero_note_en" in prompt),
        ("chinese note field", "zotero_note_zh" in prompt),
        ("legacy chinese summary fallback", "legacy LLM summary backend only produced `summary` / Chinese content" in prompt),
        ("attach_mode import", 'attach_mode set to \'import\'' in prompt),
        ("no project root leakage", "Project root:" not in prompt),
        ("no data dir leakage", "sourced from " not in prompt),
    ]

    print("\n提示词内容检查:")
    for label, passed in prompt_checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {label}")
        all_present = all_present and passed

    if all_present:
        print(f"\n✅ 提示词构建成功，长度: {len(prompt)} 字符")

    return all_present


def test_copilot_and_mcp():
    """测试 Copilot CLI 与 Zotero MCP。"""
    print("\n" + "=" * 60)
    print("🔌 测试 Copilot CLI 与 Zotero MCP")
    print("=" * 60)

    load_env()
    config = load_config()

    try:
        validate_zotero_upload_environment(config)
        print("  ✅ Copilot CLI 可用")
        print("  ✅ Zotero MCP 已配置")
        return True
    except Exception as exc:
        print(f"  ❌ 环境检查失败: {exc}")
        return False


def test_pipeline_state_selection():
    """测试跨午夜与显式日期覆盖逻辑。"""
    print("\n" + "=" * 60)
    print("🕒 测试上传日期与运行ID选择")
    print("=" * 60)

    load_env()
    config = load_config()
    state_path = PIPELINE_STATE_FILE
    original_text = state_path.read_text(encoding="utf-8") if state_path.exists() else None
    state_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        current_datetime = get_current_datetime(config)
        previous_date = (current_datetime - timedelta(days=1)).strftime("%Y-%m-%d")

        state_path.write_text(
            json.dumps(
                {
                    "run_date": previous_date,
                    "run_id": "cross-midnight-run",
                    "status": "completed",
                    "completed_at": current_datetime.isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        cross_midnight_state = get_effective_pipeline_state(config)

        state_path.write_text(
            json.dumps(
                {
                    "run_date": previous_date,
                    "run_id": "cross-midnight-running-run",
                    "status": "running",
                    "started_at": (current_datetime - timedelta(hours=4)).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        cross_midnight_running_state = get_effective_pipeline_state(config)
        explicit_cross_midnight_running_state = get_effective_pipeline_state(
            config, date_str=previous_date
        )

        state_path.write_text(
            json.dumps(
                {
                    "run_date": "2099-01-02",
                    "run_id": "20990102T093000+0800",
                    "status": "completed",
                    "completed_at": "2099-01-02T09:45:00+08:00",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        stale_state = get_effective_pipeline_state(config)
        explicit_match_state = get_effective_pipeline_state(config, date_str="2099-01-02")
        explicit_override_state = get_effective_pipeline_state(config, date_str="2099-01-03")

        state_path.write_text(
            json.dumps(
                {
                    "run_date": "2099-01-04",
                    "run_id": "failed-same-day-run",
                    "status": "failed",
                    "failed_at": "2099-01-04T09:45:00+08:00",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        failed_same_day_state = get_effective_pipeline_state(config, date_str="2099-01-04")

        current_date = current_datetime.strftime("%Y-%m-%d")
        state_path.write_text(
            json.dumps(
                {
                    "run_date": current_date,
                    "run_id": "stale-running-run",
                    "status": "running",
                    "started_at": (current_datetime - timedelta(hours=4)).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        stale_running_state = get_effective_pipeline_state(config)

        checks = [
            (
                "recent cross-midnight run preserved",
                cross_midnight_state["run_date"] == previous_date
                and cross_midnight_state["run_id"] == "cross-midnight-run",
            ),
            (
                "recent cross-midnight running state preserved",
                cross_midnight_running_state["run_date"] == previous_date
                and cross_midnight_running_state["run_id"] == "cross-midnight-running-run",
            ),
            (
                "explicit cross-midnight running state stays preserved",
                explicit_cross_midnight_running_state["run_date"] == previous_date
                and explicit_cross_midnight_running_state["run_id"] == "cross-midnight-running-run",
            ),
            (
                "stale completed run ignored by default",
                stale_state["run_date"] != "2099-01-02"
                and stale_state["run_id"] is None
                and stale_state["status"] is None,
            ),
            (
                "matching explicit date keeps run_id",
                explicit_match_state["run_date"] == "2099-01-02"
                and explicit_match_state["run_id"] == "20990102T093000+0800",
            ),
            (
                "explicit date overrides mismatched state",
                explicit_override_state["run_date"] == "2099-01-03"
                and explicit_override_state["run_id"] is None,
            ),
            (
                "same-day failed state keeps run_id for validation",
                failed_same_day_state["run_date"] == "2099-01-04"
                and failed_same_day_state["run_id"] == "failed-same-day-run"
                and failed_same_day_state["status"] == "failed",
            ),
            (
                "failed state is not uploadable",
                is_pipeline_uploadable(failed_same_day_state) is False,
            ),
            (
                "stale running state is rejected",
                stale_running_state["run_id"] is None
                and stale_running_state["status"] == "stale_running",
            ),
            (
                "stale running state is not uploadable",
                is_pipeline_uploadable(stale_running_state) is False,
            ),
        ]

        all_passed = True
        for label, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {label}")
            all_passed = all_passed and passed

        return all_passed
    finally:
        if original_text is None:
            if state_path.exists():
                state_path.unlink()
        else:
            state_path.write_text(original_text, encoding="utf-8")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🧪 Daily arXiv Zotero 上传测试")
    print("=" * 60)

    tests = [
        ("Zotero 上传配置", test_zotero_upload_config()),
        ("上传日期 / 运行ID 选择", test_pipeline_state_selection()),
        ("Copilot CLI / Zotero MCP", test_copilot_and_mcp()),
    ]

    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)

    for name, result in tests:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")

    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    print(f"\n通过: {passed}/{total}")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
