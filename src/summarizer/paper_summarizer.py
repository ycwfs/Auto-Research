"""
论文总结器

使用 Copilot CLI + MinerU MCP 基于论文全文生成结构化双语总结。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
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
from src.utils import (
    build_paper_set_signature,
    get_current_datetime,
    get_date_string,
    get_paper_identity,
    normalize_paper_pdf_url,
    save_json,
)
from .llm_factory import LLMClientFactory


class PaperSummarizer:
    """基于全文生成论文总结。"""

    DEFAULT_PROMPT_FILE = Path("config/prompts/daily_paper_digest_prompt.txt")
    SUPPORTED_BACKENDS = {"agent", "llm"}
    LLM_SYSTEM_PROMPT = """你是一个专业的学术论文分析助手。你将读取论文的标题、作者和摘要，并只输出中文摘要正文。

要求：
1. 只输出中文摘要正文，不要输出 JSON、Markdown 标题、代码块或额外说明。
2. 摘要应基于标题、作者与摘要内容，优先概括任务、方法、结果与应用场景。
3. 不要编造摘要中没有明确提到的公式、指标、实验细节或结论。
4. 如果摘要信息不足，就保持简洁保守，不要强行补全结构化内容。
"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("daily_arxiv.summarizer")
        self.pipeline_config = config.get("pipeline", {})
        self.summary_backend = str(
            self.pipeline_config.get("summary_backend", "agent")
        ).strip().lower()
        if self.summary_backend not in self.SUPPORTED_BACKENDS:
            raise ValueError(
                f"不支持的 summary_backend: {self.summary_backend}，"
                f"支持值: {', '.join(sorted(self.SUPPORTED_BACKENDS))}"
            )

        self.agent_config = config.get("agent", {})
        self.summary_config = self.agent_config.get("summary", {})
        self.command = self.agent_config.get("copilot_command", "copilot")
        self.model = self.agent_config.get("model", "")
        self.reasoning_effort = self.agent_config.get("reasoning_effort", "high")
        self.timeout_minutes = int(self.summary_config.get("timeout_minutes", 180))
        self.log_dir = resolve_project_path(
            self.summary_config.get("log_dir", "logs/daily_digest")
        )
        self.fulltext_dir = resolve_project_path(
            self.summary_config.get("fulltext_dir", "data/fulltext")
        )
        self.prompt_file = resolve_project_path(
            self.summary_config.get("prompt_file", str(self.DEFAULT_PROMPT_FILE))
        )
        self.llm_client = None
        self.summary_engine_label = ""

        if self.summary_backend == "agent":
            validate_cli_environment(
                command=self.command,
                required_mcp_servers=["mineru"],
            )
            self.summary_engine_label = "CLI + MinerU MCP 全文解析"
        else:
            self.llm_client = LLMClientFactory.create_client(config)
            self.summary_engine_label = (
                f"{self.llm_client.get_provider_name()} API ({self.llm_client.model}) 中文摘要总结"
            )

    def summarize_papers(
        self,
        papers: list[dict[str, Any]],
        show_progress: bool = True,
    ) -> list[dict[str, Any]]:
        """批量总结论文。"""
        del show_progress  # 保持兼容旧接口
        papers = [normalize_paper_pdf_url(paper) for paper in papers]
        if not papers:
            self.logger.warning("没有论文需要总结")
            return []

        if self.summary_backend == "llm":
            return self._summarize_papers_with_llm(papers)

        return self._summarize_papers_with_agent(papers)

    def _summarize_papers_with_agent(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.logger.info("=" * 60)
        self.logger.info("开始基于全文总结 %s 篇论文", len(papers))
        self.logger.info("使用代理: CLI + MinerU MCP")
        self.logger.info("=" * 60)

        timestamp = get_current_datetime(self.config).strftime("%Y%m%d_%H%M%S")
        workspace_dir = self.log_dir / f"workspace_{timestamp}"
        inputs_dir = workspace_dir / "inputs"
        outputs_dir = workspace_dir / "outputs"
        fulltext_output_dir = outputs_dir / "fulltext"
        prompt_snapshot = self.log_dir / f"daily_digest_prompt_{timestamp}.txt"
        staged_papers_path = inputs_dir / "papers_latest.json"
        output_json_path = outputs_dir / "daily_digest.json"

        self.log_dir.mkdir(parents=True, exist_ok=True)
        inputs_dir.mkdir(parents=True, exist_ok=True)
        fulltext_output_dir.mkdir(parents=True, exist_ok=True)

        staged_payload = {
            "date": get_date_string(config=self.config),
            "run_id": self.config.get("_runtime", {}).get("run_id"),
            "count": len(papers),
            "paper_signature": build_paper_set_signature(papers),
            "papers": papers,
        }
        save_json(staged_payload, str(staged_papers_path))

        prompt = self._build_prompt(
            papers_json=staged_papers_path,
            output_json=output_json_path,
            fulltext_dir=fulltext_output_dir,
        )
        prompt_snapshot.write_text(prompt, encoding="utf-8")

        configured_mcp_servers = get_configured_mcp_servers(self.command)
        cli_command = build_cli_command(
            command=self.command,
            prompt=prompt,
            configured_mcp_servers=configured_mcp_servers,
            required_mcp_servers=["mineru"],
            add_dirs=[inputs_dir, outputs_dir],
            model=self.model,
            reasoning_effort=self.reasoning_effort,
        )

        try:
            result = subprocess.run(
                cli_command,
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_minutes * 60,
            )
        except subprocess.TimeoutExpired as exc:
            log_path = write_run_log(
                log_dir=self.log_dir,
                filename_prefix="daily_digest",
                timestamp=timestamp,
                command=cli_command,
                prompt=prompt,
                stdout=exc.stdout,
                stderr=exc.stderr,
                exit_code=None,
            )
            raise RuntimeError(
                f"论文全文总结任务超时（>{self.timeout_minutes} 分钟），详见日志: {log_path}"
            ) from exc

        log_path = write_run_log(
            log_dir=self.log_dir,
            filename_prefix="daily_digest",
            timestamp=timestamp,
            command=cli_command,
            prompt=prompt,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
        )
        if result.returncode != 0:
            raise RuntimeError(f"论文全文总结任务失败，详见日志: {log_path}")

        raw_output = self._load_output_json(output_json_path)
        summarized_papers = self._merge_summaries(
            papers=papers,
            output_payload=raw_output,
            fulltext_output_dir=fulltext_output_dir,
        )

        success_count = sum(1 for paper in summarized_papers if not paper.get("summary_error"))
        fail_count = len(summarized_papers) - success_count
        self.logger.info(
            "✅ 全文总结完成: %s 篇成功, %s 篇失败，执行日志: %s",
            success_count,
            fail_count,
            log_path,
        )

        self._save_summaries(summarized_papers)
        return summarized_papers

    def _summarize_papers_with_llm(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.logger.info("=" * 60)
        self.logger.info("开始基于标题与摘要总结 %s 篇论文", len(papers))
        self.logger.info("使用后端: %s", self.summary_engine_label)
        self.logger.info("=" * 60)

        summarized_papers = [self._summarize_single_paper_with_llm(paper) for paper in papers]
        self._save_summaries(summarized_papers)
        return summarized_papers

    def _summarize_single_paper_with_llm(self, paper: dict[str, Any]) -> dict[str, Any]:
        paper_with_summary = paper.copy()
        paper_with_summary["paper_id"] = get_paper_identity(paper)
        paper_with_summary["summarized_at"] = get_current_datetime(self.config).isoformat()

        prompt = self._build_llm_summary_prompt(paper)

        try:
            assert self.llm_client is not None
            response = self.llm_client.generate(
                prompt=prompt,
                system_prompt=self.LLM_SYSTEM_PROMPT,
            )
            paper_with_summary["summary"] = self._normalize_llm_summary_text(response)
            paper_with_summary["summary_en"] = ""
            paper_with_summary["structured_summary"] = {}
            paper_with_summary["zotero_note_zh"] = self._build_llm_chinese_note(
                paper_with_summary["summary"]
            )
            paper_with_summary["zotero_note_en"] = ""
            paper_with_summary["summary_error"] = False
            paper_with_summary["summary_error_message"] = ""
        except Exception as exc:
            self.logger.error("总结论文失败 [%s]: %s", paper.get("title", "Unknown"), str(exc))
            paper_with_summary["summary"] = ""
            paper_with_summary["summary_en"] = ""
            paper_with_summary["structured_summary"] = {}
            paper_with_summary["zotero_note_zh"] = ""
            paper_with_summary["zotero_note_en"] = ""
            paper_with_summary["summary_error"] = True
            paper_with_summary["summary_error_message"] = str(exc)

        return paper_with_summary

    def _build_llm_summary_prompt(self, paper: dict[str, Any]) -> str:
        authors = ", ".join(paper.get("authors", [])[:8])
        return f"""请根据下面的论文信息，直接写一段简洁准确的中文摘要。

要求：
1. 只输出中文摘要正文，不要输出 JSON、标题、项目符号或额外解释。
2. 摘要应尽量覆盖论文任务、核心方法、主要结果或结论，但只能基于已提供的摘要内容。
3. 如果原摘要没有明确给出结果、指标或方法细节，不要编造。
4. 控制在 1-2 段，语言自然凝练。

标题：{paper.get('title', '')}
作者：{authors}
类别：{', '.join(paper.get('categories', []))}
摘要：
{paper.get('abstract', '')}"""

    @staticmethod
    def _normalize_llm_summary_text(response: str) -> str:
        text = response.strip()
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = re.sub(r"^\s*中文摘要[:：]\s*", "", text)
        text = text.strip().strip('"').strip("'").strip()
        if not text:
            raise ValueError("LLM 未返回可用的中文摘要")
        return text

    @staticmethod
    def _build_llm_chinese_note(summary: str) -> str:
        return f"# 论文总结\n\n{summary}".strip()

    def _extract_json_payload(self, response: str) -> dict[str, Any]:
        response = response.strip()
        try:
            data = json.loads(response)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise ValueError("LLM 响应中未找到 JSON 对象")

        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            raise ValueError("LLM 响应 JSON 不是对象")
        return data

    def _build_zotero_note(
        self,
        *,
        language: str,
        summary: str,
        structured: dict[str, Any],
    ) -> str:
        if language == "zh":
            headings = [
                ("任务定义", "task_definition"),
                ("研究背景与动机", "background_motivation"),
                ("主要创新点", "innovations"),
                ("方法", "research_method"),
                ("评测指标", "evaluation_metrics"),
                ("结果与结论", "results_conclusions"),
            ]
            title = "# 论文总结"
        else:
            headings = [
                ("Task Definition", "task_definition"),
                ("Background & Motivation", "background_motivation"),
                ("Main Innovations", "innovations"),
                ("Method", "research_method"),
                ("Evaluation Metrics", "evaluation_metrics"),
                ("Results & Conclusions", "results_conclusions"),
            ]
            title = "# Paper Summary"

        lines = [title]
        if summary:
            lines.extend(["", summary])

        for label, key in headings:
            lines.extend(["", f"## {label}", str(structured.get(key) or "N/A")])

        return "\n".join(lines).strip()

    def _build_prompt(self, *, papers_json: Path, output_json: Path, fulltext_dir: Path) -> str:
        template = self.prompt_file.read_text(encoding="utf-8")
        return template.format(
            current_date=get_date_string(config=self.config),
            run_id=self.config.get("_runtime", {}).get("run_id", ""),
            papers_json=papers_json,
            output_json=output_json,
            fulltext_dir=fulltext_dir,
        )

    def _load_output_json(self, output_path: Path) -> dict[str, Any]:
        if not output_path.exists():
            raise FileNotFoundError(f"未找到论文总结输出文件: {output_path}")

        with output_path.open("r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)

        if not isinstance(data, dict):
            raise ValueError("论文总结输出格式错误，应为 JSON 对象")

        papers = data.get("papers")
        if not isinstance(papers, list):
            raise ValueError("论文总结输出缺少 papers 列表")

        return data

    @staticmethod
    def _has_usable_summary_content(output_item: dict[str, Any]) -> bool:
        """判断代理输出是否已经包含完整的双语总结与笔记。"""
        summary_zh = str(output_item.get("summary_zh") or "").strip()
        summary_en = str(output_item.get("summary_en") or "").strip()
        note_zh = str(output_item.get("zotero_note_zh") or "").strip()
        note_en = str(output_item.get("zotero_note_en") or "").strip()
        structured_summary = output_item.get("structured_summary")
        has_structured_summary = isinstance(structured_summary, dict) and any(
            str(value).strip() for value in structured_summary.values()
        )
        return all([summary_zh, summary_en, note_zh, note_en, has_structured_summary])

    def _merge_summaries(
        self,
        *,
        papers: list[dict[str, Any]],
        output_payload: dict[str, Any],
        fulltext_output_dir: Path,
    ) -> list[dict[str, Any]]:
        merged_papers: list[dict[str, Any]] = []
        output_items = output_payload.get("papers", [])
        output_by_identity: dict[str, dict[str, Any]] = {}

        for item in output_items:
            if not isinstance(item, dict):
                continue
            paper_id = str(item.get("paper_id") or item.get("id") or "").strip()
            if paper_id:
                output_by_identity[paper_id] = item

        date_str = get_date_string(config=self.config)
        target_fulltext_dir = self.fulltext_dir / date_str
        target_fulltext_dir.mkdir(parents=True, exist_ok=True)

        for paper in papers:
            paper_identity = get_paper_identity(paper)
            output_item = output_by_identity.get(paper_identity)
            merged = normalize_paper_pdf_url(paper)
            merged["paper_id"] = paper_identity
            merged["summarized_at"] = get_current_datetime(self.config).isoformat()

            if not output_item:
                merged["summary"] = ""
                merged["summary_en"] = ""
                merged["zotero_note_zh"] = ""
                merged["zotero_note_en"] = ""
                merged["structured_summary"] = {}
                merged["summary_error"] = True
                merged["summary_error_message"] = "未在代理输出中找到该论文的总结结果"
                merged_papers.append(merged)
                continue

            merged["structured_summary"] = output_item.get("structured_summary", {})
            merged["summary"] = str(output_item.get("summary_zh") or "").strip()
            merged["summary_en"] = str(output_item.get("summary_en") or "").strip()
            merged["zotero_note_zh"] = str(output_item.get("zotero_note_zh") or "").strip()
            merged["zotero_note_en"] = str(output_item.get("zotero_note_en") or "").strip()

            fulltext_name = output_item.get("fulltext_markdown")
            if isinstance(fulltext_name, str) and fulltext_name.strip():
                source_fulltext_path = fulltext_output_dir / fulltext_name.strip()
                if source_fulltext_path.exists():
                    target_fulltext_path = target_fulltext_dir / source_fulltext_path.name
                    shutil.copy2(source_fulltext_path, target_fulltext_path)
                    merged["fulltext_markdown_path"] = str(
                        target_fulltext_path.relative_to(PROJECT_ROOT)
                    )

            summary_error = bool(output_item.get("summary_error"))
            if summary_error and self._has_usable_summary_content(output_item):
                summary_error = False
            merged["summary_error"] = summary_error
            if summary_error:
                merged["summary_error_message"] = str(
                    output_item.get("summary_error_message") or "代理未提供可用总结"
                )
                if not merged["summary"]:
                    merged["summary"] = merged["summary_error_message"]
            else:
                merged["summary_error_message"] = ""

            merged_papers.append(merged)

        return merged_papers

    def _save_summaries(self, papers: list[dict[str, Any]]):
        if not papers:
            return

        data_path = Path("data/summaries")
        data_path.mkdir(parents=True, exist_ok=True)

        date_str = get_date_string(config=self.config)
        filepath = data_path / f"summaries_{date_str}.json"
        save_json(papers, str(filepath))
        self.logger.info("💾 总结数据已保存到: %s", filepath)

        latest_payload = {
            "date": date_str,
            "run_id": self.config.get("_runtime", {}).get("run_id"),
            "count": len(papers),
            "paper_signature": build_paper_set_signature(papers),
            "has_errors": any(paper.get("summary_error") for paper in papers),
            "papers": papers,
            "summary_engine": self.summary_backend,
        }
        if self.summary_backend == "agent":
            latest_payload["copilot_model"] = self.model
        else:
            assert self.llm_client is not None
            latest_payload["llm_provider"] = self.llm_client.get_provider_name()
            latest_payload["llm_model"] = self.llm_client.model
        latest_path = data_path / "latest.json"
        save_json(latest_payload, str(latest_path))
        self.logger.info("💾 最新总结已保存到: %s", latest_path)

    def generate_daily_report(self, papers: list[dict[str, Any]]) -> str:
        if not papers:
            return "今日没有论文。"

        paper_signature = build_paper_set_signature(papers)
        report_parts = [
            f"<!-- paper_signature:{paper_signature} -->",
            "# 📚 每日 arXiv 全文总结",
            f"\n**日期**: {get_date_string(config=self.config)}",
            f"**运行ID**: {self.config.get('_runtime', {}).get('run_id', 'N/A')}",
            f"**论文数量**: {len(papers)} 篇",
            f"**总结方式**: {self.summary_engine_label}",
            "\n---\n",
        ]

        for index, paper in enumerate(papers, 1):
            report_parts.append(f"\n## {index}. {paper['title']}")
            report_parts.append(
                f"\n**作者**: {', '.join(paper['authors'][:3])}"
                + (" et al." if len(paper['authors']) > 3 else "")
            )
            report_parts.append(f"\n**类别**: {', '.join(paper.get('categories', [])[:3])}")
            report_parts.append(f"\n**链接**: [{paper['id']}]({paper['pdf_url']})")
            if paper.get("fulltext_markdown_path"):
                report_parts.append(
                    f"\n**全文 Markdown**: `{paper['fulltext_markdown_path']}`"
                )

            if paper.get("summary_error"):
                report_parts.append(
                    f"\n**总结状态**: 失败 - {paper.get('summary_error_message', '未知错误')}"
                )
                report_parts.append("\n---\n")
                continue

            structured = paper.get("structured_summary", {})
            report_parts.append("\n### 中文摘要")
            report_parts.append(f"\n{paper.get('summary', '暂无')}")
            if paper.get("summary_en"):
                report_parts.append("\n### English Summary")
                report_parts.append(f"\n{paper.get('summary_en', 'N/A')}")
            if isinstance(structured, dict) and any(str(value).strip() for value in structured.values()):
                report_parts.append("\n### Structured Notes")
                report_parts.append(
                    f"\n- **Task / IO**: {structured.get('task_definition', 'N/A')}"
                )
                report_parts.append(
                    f"\n- **Background & Motivation**: {structured.get('background_motivation', 'N/A')}"
                )
                report_parts.append(
                    f"\n- **Method**: {structured.get('research_method', 'N/A')}"
                )
                report_parts.append(
                    f"\n- **Metrics**: {structured.get('evaluation_metrics', 'N/A')}"
                )
                report_parts.append(
                    f"\n- **Results & Conclusions**: {structured.get('results_conclusions', 'N/A')}"
                )
            report_parts.append("\n---\n")

        return "\n".join(report_parts)


def main():
    """测试函数"""
    from src.utils import load_config, load_env, load_json, setup_logging

    load_env()
    config = load_config()
    logger = setup_logging(config)

    papers_data = load_json("data/papers/latest.json")
    if not papers_data or not papers_data.get("papers"):
        logger.error("没有找到论文数据，请先运行论文爬取")
        return

    papers = papers_data["papers"][:2]
    summarizer = PaperSummarizer(config)
    summarized = summarizer.summarize_papers(papers)
    report = summarizer.generate_daily_report(summarized)
    print(report)


if __name__ == "__main__":
    main()
