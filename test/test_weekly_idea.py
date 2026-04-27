#!/usr/bin/env python3
"""
测试周度 idea 自动化配置。
"""

import sys
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
    else:
        print(f"  ❌ prompt_file 不存在: {prompt_path}")
        all_present = False

    return all_present


def main():
    success = test_weekly_idea_config()
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print("✅ 通过" if success else "❌ 失败")
    return success


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
