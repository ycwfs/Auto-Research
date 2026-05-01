#!/usr/bin/env python3
"""
测试周度 idea 自动化配置。
"""

import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.automation.weekly_idea_runner import get_week_range, get_weekly_idea_config
from src.utils import load_config, load_env


def test_weekly_idea_config():
    print("\n" + "=" * 60)
    print("🧪 测试周度 idea 配置")
    print("=" * 60)

    load_env()
    config = load_config()
    weekly_config = get_weekly_idea_config(config)

    required_keys = [
        "enabled",
        "day_of_week",
        "run_time",
        "prompt_file",
        "collection_name",
    ]
    all_present = True
    for key in required_keys:
        if key in weekly_config and weekly_config[key] != "":
            print(f"  ✅ {key}: {weekly_config[key]}")
        else:
            print(f"  ❌ {key}: 未配置")
            all_present = False

    week_start, week_end = get_week_range(config)
    print(f"  ✅ 当前周范围: {week_start} -> {week_end}")

    prompt_path = project_root / weekly_config.get("prompt_file", "")
    if prompt_path.exists():
        print(f"  ✅ prompt_file 存在: {prompt_path}")
        prompt_text = prompt_path.read_text(encoding="utf-8")
        if "/ml-paper-writing" in prompt_text:
            print("  ❌ prompt_file 仍然依赖外部 ml-paper-writing skill 路径")
            all_present = False
        else:
            print("  ✅ prompt_file 已改为自包含，不依赖外部 skill 路径")
        if "Do not invoke external writing skills" in prompt_text:
            print("  ✅ prompt_file 已显式禁止读取外部参考文件")
        else:
            print("  ❌ prompt_file 缺少外部权限保护说明")
            all_present = False
    else:
        print(f"  ❌ prompt_file 不存在: {prompt_path}")
        all_present = False

    return all_present


def test_week_range_alignment():
    print("\n" + "=" * 60)
    print("🧪 测试周度时间窗口锚定")
    print("=" * 60)

    config = load_config()
    cases = [
        (datetime(2026, 4, 30, 20, 0, 0), ("2026-04-23", "2026-04-30")),
        (datetime(2026, 5, 1, 9, 0, 0), ("2026-04-23", "2026-04-30")),
    ]

    all_passed = True
    for reference_datetime, expected_range in cases:
        actual_range = get_week_range(config, reference_datetime=reference_datetime)
        if actual_range == expected_range:
            print(
                f"  ✅ {reference_datetime.isoformat()} -> "
                f"{actual_range[0]} -> {actual_range[1]}"
            )
        else:
            print(
                f"  ❌ {reference_datetime.isoformat()} -> "
                f"{actual_range[0]} -> {actual_range[1]} "
                f"(期望 {expected_range[0]} -> {expected_range[1]})"
            )
            all_passed = False

    return all_passed


def main():
    success = test_weekly_idea_config() and test_week_range_alignment()
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print("✅ 通过" if success else "❌ 失败")
    return success


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
