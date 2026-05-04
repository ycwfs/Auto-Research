"""
趋势分析器

分析论文集合，生成：
1. 词云图
2. 研究热点分析
3. 趋势预测
4. 研究创新点建议
"""
import logging
import json
import subprocess
from typing import List, Dict, Any
from pathlib import Path
from collections import Counter
import re

# 词云和可视化
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端

# 文本处理
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
import nltk
from nltk.corpus import stopwords

from src.automation.cli_runner import (
    build_cli_command,
    get_configured_mcp_servers,
    resolve_project_path,
    validate_cli_environment,
    write_run_log,
)
from src.utils import (
    build_paper_set_signature,
    get_current_datetime,
    get_data_path,
    get_date_string,
    save_json,
    save_text,
)
from src.summarizer.llm_factory import LLMClientFactory


class TrendAnalyzer:
    """趋势分析器"""

    DEFAULT_PROMPT_FILE = Path("config/prompts/daily_trend_analysis_prompt.txt")
    SUPPORTED_BACKENDS = {"agent", "llm"}
    
    def __init__(self, config: Dict[str, Any], llm_client=None):
        """初始化
        
        Args:
            config: 配置字典
            llm_client: LLM 客户端（用于生成分析报告）
        """
        self.config = config
        self.llm_client = llm_client
        self.logger = logging.getLogger('daily_arxiv.analyzer')
        self.pipeline_config = config.get("pipeline", {})
        self.analysis_backend = str(
            self.pipeline_config.get("analysis_backend", "agent")
        ).strip().lower()
        if self.analysis_backend not in self.SUPPORTED_BACKENDS:
            raise ValueError(
                f"不支持的 analysis_backend: {self.analysis_backend}，"
                f"支持值: {', '.join(sorted(self.SUPPORTED_BACKENDS))}"
            )

        self.agent_config = config.get("agent", {})
        self.analysis_config = self.agent_config.get("analysis", {})
        self.command = self.agent_config.get("copilot_command", "copilot")
        self.model = self.agent_config.get("model", "")
        self.reasoning_effort = self.agent_config.get("reasoning_effort", "high")
        self.timeout_minutes = int(self.analysis_config.get("timeout_minutes", 90))
        self.log_dir = resolve_project_path(
            self.analysis_config.get("log_dir", "logs/daily_analysis")
        )
        self.prompt_file = resolve_project_path(
            self.analysis_config.get("prompt_file", str(self.DEFAULT_PROMPT_FILE))
        )
        self.analysis_engine_label = ""
        if self.analysis_backend == "agent":
            validate_cli_environment(command=self.command)
            self.analysis_engine_label = "CLI narrative analysis"
        else:
            if self.llm_client is None:
                self.llm_client = LLMClientFactory.create_client(config)
            self.analysis_engine_label = (
                f"{self.llm_client.get_provider_name()} API ({self.llm_client.model}) narrative analysis"
            )
        
        # 下载必要的 NLTK 数据
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            self.logger.info("下载 NLTK stopwords...")
            nltk.download('stopwords', quiet=True)
        
        self.stop_words = set(stopwords.words('english'))
        # 添加自定义停用词
        self.stop_words.update([
            'paper', 'study', 'research', 'approach', 'method', 'propose',
            'propose', 'present', 'show', 'demonstrate', 'arxiv', 'preprint',
            'et', 'al', 'also', 'based', 'using', 'used', 'use', 'new',
            'work', 'results', 'result', 'performance', 'model', 'models'
        ])
    
    def analyze(self, papers: List[Dict[str, Any]], summaries: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行完整的趋势分析
        
        Args:
            papers: 论文列表
            summaries: 论文总结列表（可选）
            
        Returns:
            分析结果字典
        """
        self.logger.info("=" * 60)
        self.logger.info("🔍 开始趋势分析")
        self.logger.info(f"分析论文数量: {len(papers)}")
        self.logger.info("分析后端: %s", self.analysis_engine_label)
        self.logger.info("=" * 60)
        
        if not papers:
            self.logger.warning("没有论文可分析")
            return {}
        
        # 1. 提取关键词和主题
        self.logger.info("\n步骤 1: 提取关键词和主题...")
        keywords = self._extract_keywords(papers)
        topics = self._extract_topics(papers)
        
        # 2. 生成词云
        self.logger.info("\n步骤 2: 生成词云...")
        wordcloud_path = self._generate_wordcloud(papers)
        
        # 3. 统计分析
        self.logger.info("\n步骤 3: 统计分析...")
        statistics = self._generate_statistics(papers, summaries)
        
        # 4. 生成深度分析
        self.logger.info("\n步骤 4: 生成深度分析报告...")
        llm_analysis = self._generate_narrative_analysis(papers, summaries, keywords, topics)
        
        # 组合所有分析结果
        analysis_result = {
            'date': get_date_string(config=self.config),
            'run_id': self.config.get('_runtime', {}).get('run_id'),
            'paper_count': len(papers),
            'paper_signature': build_paper_set_signature(papers),
            'analysis_engine': self.analysis_backend,
            'keywords': keywords,
            'topics': topics,
            'statistics': statistics,
            'wordcloud_path': wordcloud_path,
            'llm_analysis': llm_analysis,
            'generated_at': get_current_datetime(self.config).isoformat()
        }
        if self.analysis_backend == "agent":
            analysis_result["copilot_model"] = self.model
        elif self.llm_client is not None:
            analysis_result["llm_provider"] = self.llm_client.get_provider_name()
            analysis_result["llm_model"] = self.llm_client.model
        
        # 保存分析结果
        self._save_analysis(analysis_result)
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info("✅ 趋势分析完成")
        self.logger.info("=" * 60)
        
        return analysis_result
    
    def _extract_keywords(self, papers: List[Dict[str, Any]], top_n: int = 50) -> List[Dict[str, Any]]:
        """提取关键词（使用 TF-IDF）
        
        Args:
            papers: 论文列表
            top_n: 返回前 N 个关键词
            
        Returns:
            关键词列表，包含词和权重
        """
        # 合并所有论文的标题和摘要
        texts = []
        for paper in papers:
            text = paper['title'] + ' ' + paper['abstract']
            texts.append(text)
        
        # 使用 TF-IDF 提取关键词
        vectorizer = TfidfVectorizer(
            max_features=top_n,
            stop_words=list(self.stop_words),
            ngram_range=(1, 2),  # 包括单词和二元组
            min_df=2,  # 至少出现在2篇论文中
            max_df=0.8  # 最多出现在80%的论文中
        )
        
        tfidf_matrix = vectorizer.fit_transform(texts)
        feature_names = vectorizer.get_feature_names_out()
        
        # 计算每个词的平均 TF-IDF 分数
        avg_scores = tfidf_matrix.mean(axis=0).A1
        keyword_scores = list(zip(feature_names, avg_scores))
        keyword_scores.sort(key=lambda x: x[1], reverse=True)
        
        keywords = [
            {'keyword': kw, 'score': float(score)}
            for kw, score in keyword_scores[:top_n]
        ]
        
        self.logger.info(f"✓ 提取了 {len(keywords)} 个关键词")
        self.logger.info(f"  Top 10: {', '.join([k['keyword'] for k in keywords[:10]])}")
        
        return keywords
    
    def _extract_topics(self, papers: List[Dict[str, Any]], n_topics: int = 5) -> List[Dict[str, Any]]:
        """提取主题（使用 LDA）
        
        Args:
            papers: 论文列表
            n_topics: 主题数量
            
        Returns:
            主题列表
        """
        # 合并所有论文的标题和摘要
        texts = []
        for paper in papers:
            text = paper['title'] + ' ' + paper['abstract']
            texts.append(text)
        
        # 使用 CountVectorizer
        vectorizer = CountVectorizer(
            max_features=1000,
            stop_words=list(self.stop_words),
            min_df=2,
            max_df=0.8
        )
        
        doc_term_matrix = vectorizer.fit_transform(texts)
        feature_names = vectorizer.get_feature_names_out()
        
        # 使用 LDA 提取主题
        lda = LatentDirichletAllocation(
            n_components=n_topics,
            random_state=42,
            max_iter=20
        )
        lda.fit(doc_term_matrix)
        
        # 提取每个主题的关键词
        topics = []
        for topic_idx, topic in enumerate(lda.components_):
            top_indices = topic.argsort()[-10:][::-1]
            top_words = [feature_names[i] for i in top_indices]
            topic_weight = topic[top_indices]
            
            topics.append({
                'topic_id': topic_idx + 1,
                'keywords': top_words,
                'weights': [float(w) for w in topic_weight]
            })
        
        self.logger.info(f"✓ 提取了 {len(topics)} 个主题")
        for i, topic in enumerate(topics, 1):
            self.logger.info(f"  主题 {i}: {', '.join(topic['keywords'][:5])}")
        
        return topics
    
    def _generate_wordcloud(self, papers: List[Dict[str, Any]]) -> str:
        """生成词云图
        
        Args:
            papers: 论文列表
            
        Returns:
            词云图片路径
        """
        # 合并所有文本
        text = ' '.join([
            paper['title'] + ' ' + paper['abstract']
            for paper in papers
        ])
        
        # 清理文本
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        
        # 生成词云
        wordcloud = WordCloud(
            width=1600,
            height=800,
            background_color='white',
            stopwords=self.stop_words,
            max_words=100,
            relative_scaling=0.5,
            colormap='viridis',
            min_font_size=10
        ).generate(text)
        
        # 保存图片
        output_dir = Path('data/analysis')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        date_str = get_date_string(config=self.config)
        wordcloud_path = f"data/analysis/wordcloud_{date_str}.png"
        
        # 创建图表
        plt.figure(figsize=(16, 8))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.axis('off')
        plt.title(f'Research Trends Word Cloud - {date_str}', fontsize=20, pad=20)
        plt.tight_layout(pad=0)
        
        # 保存
        plt.savefig(wordcloud_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"✓ 词云已保存: {wordcloud_path}")
        
        return wordcloud_path
    
    def _generate_statistics(self, papers: List[Dict[str, Any]], 
                           summaries: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成统计信息
        
        Args:
            papers: 论文列表
            summaries: 论文总结列表
            
        Returns:
            统计信息字典
        """
        # 类别统计
        category_counts = Counter()
        for paper in papers:
            for category in paper.get('categories', []):
                category_counts[category] += 1
        
        # 作者统计
        author_counts = Counter()
        for paper in papers:
            for author in paper.get('authors', []):
                author_counts[author] += 1
        
        # 高频词统计
        word_counts = Counter()
        for paper in papers:
            title_words = paper['title'].lower().split()
            abstract_words = paper['abstract'].lower().split()
            for word in title_words + abstract_words:
                word = re.sub(r'[^\w]', '', word)
                if len(word) > 3 and word not in self.stop_words:
                    word_counts[word] += 1
        
        # 时间分布
        time_distribution = Counter()
        for paper in papers:
            published = paper.get('published', '')
            if published:
                date = published.split('T')[0]
                time_distribution[date] += 1
        
        statistics = {
            'total_papers': len(papers),
            'total_authors': len(author_counts),
            'total_categories': len(category_counts),
            'category_distribution': dict(category_counts.most_common(10)),
            'top_authors': dict(author_counts.most_common(10)),
            'top_words': dict(word_counts.most_common(30)),
            'time_distribution': dict(sorted(time_distribution.items())),
            'prolific_authors': {k: v for k, v in author_counts.items() if v >= 2}
        }
        
        return statistics
    
    def _generate_narrative_analysis(self, papers: List[Dict[str, Any]], 
                              summaries: List[Dict[str, Any]] = None,
                              keywords: List[Dict[str, Any]] = None,
                              topics: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.analysis_backend == "agent":
            return self._generate_agent_analysis(papers, summaries, keywords, topics)
        return self._generate_llm_analysis(papers, summaries, keywords, topics)

    def _generate_agent_analysis(self, papers: List[Dict[str, Any]], 
                              summaries: List[Dict[str, Any]] = None,
                              keywords: List[Dict[str, Any]] = None,
                              topics: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """使用 LLM 生成深度分析
        
        Args:
            papers: 论文列表
            summaries: 论文总结列表
            keywords: 关键词列表
            topics: 主题列表
            
        Returns:
            LLM 分析结果
        """
        timestamp = get_current_datetime(self.config).strftime("%Y%m%d_%H%M%S")
        workspace_dir = self.log_dir / f"workspace_{timestamp}"
        inputs_dir = workspace_dir / "inputs"
        outputs_dir = workspace_dir / "outputs"
        input_json_path = inputs_dir / "analysis_input.json"
        output_json_path = outputs_dir / "daily_analysis.json"
        prompt_snapshot = self.log_dir / f"daily_analysis_prompt_{timestamp}.txt"

        self.log_dir.mkdir(parents=True, exist_ok=True)
        inputs_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)

        input_payload = {
            "date": get_date_string(config=self.config),
            "run_id": self.config.get("_runtime", {}).get("run_id"),
            "paper_count": len(papers),
            "paper_signature": build_paper_set_signature(papers),
            "papers": [
                {
                    "paper_id": paper.get("paper_id") or paper.get("id"),
                    "title": paper.get("title"),
                    "categories": paper.get("categories", []),
                    "summary_zh": paper.get("summary", ""),
                    "summary_en": paper.get("summary_en", ""),
                    "structured_summary": paper.get("structured_summary", {}),
                }
                for paper in (summaries or papers)[:30]
            ],
            "keywords": keywords or [],
            "topics": topics or [],
            "statistics": self._generate_statistics(papers, summaries),
        }
        save_json(input_payload, str(input_json_path))

        prompt = self.prompt_file.read_text(encoding="utf-8").format(
            current_date=get_date_string(config=self.config),
            run_id=self.config.get("_runtime", {}).get("run_id", ""),
            analysis_input_json=input_json_path,
            output_json=output_json_path,
        )
        prompt_snapshot.write_text(prompt, encoding="utf-8")

        configured_mcp_servers = get_configured_mcp_servers(self.command)
        cli_command = build_cli_command(
            command=self.command,
            prompt=prompt,
            configured_mcp_servers=configured_mcp_servers,
            required_mcp_servers=[],
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
                filename_prefix="daily_analysis",
                timestamp=timestamp,
                command=cli_command,
                prompt=prompt,
                stdout=exc.stdout,
                stderr=exc.stderr,
                exit_code=None,
            )
            raise RuntimeError(
                f"每日趋势分析任务超时（>{self.timeout_minutes} 分钟），详见日志: {log_path}"
            ) from exc

        log_path = write_run_log(
            log_dir=self.log_dir,
            filename_prefix="daily_analysis",
            timestamp=timestamp,
            command=cli_command,
            prompt=prompt,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
        )
        if result.returncode != 0:
            raise RuntimeError(f"每日趋势分析任务失败，详见日志: {log_path}")

        if not output_json_path.exists():
            raise FileNotFoundError(f"未找到趋势分析输出文件: {output_json_path}")

        with output_json_path.open("r", encoding="utf-8") as file_obj:
            analysis = json.load(file_obj)

        required_keys = [
            "hotspots",
            "trends",
            "future_directions",
            "research_ideas",
            "full_analysis",
        ]
        missing_keys = [key for key in required_keys if not analysis.get(key)]
        if missing_keys:
            raise ValueError(f"趋势分析输出缺少关键字段: {', '.join(missing_keys)}")

        self.logger.info("✓ 代理趋势分析完成，执行日志: %s", log_path)
        return analysis

    def _generate_llm_analysis(self, papers: List[Dict[str, Any]], 
                              summaries: List[Dict[str, Any]] = None,
                              keywords: List[Dict[str, Any]] = None,
                              topics: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """使用旧版 API LLM 生成深度分析。"""
        if not self.llm_client:
            raise RuntimeError("LLM 分析后端未初始化")

        papers_summary = []
        summary_items = summaries or papers
        for i, paper in enumerate(summary_items[:30], 1):
            structured = paper.get("structured_summary", {}) if isinstance(paper, dict) else {}
            summary_text = str(paper.get("summary") or "") if isinstance(paper, dict) else ""
            if structured:
                summary_text = (
                    f"\n  任务定义: {structured.get('task_definition', '')}"
                    f"\n  方法: {structured.get('research_method', '')}"
                    f"\n  结果: {structured.get('results_conclusions', '')}"
                )
            elif summary_text:
                summary_text = f"\n  总结: {summary_text}"

            categories = paper.get("categories", []) if isinstance(paper, dict) else []
            title = paper.get("title", "") if isinstance(paper, dict) else ""
            papers_summary.append(
                f"{i}. {title}\n"
                f"  类别: {', '.join(categories[:3])}"
                f"{summary_text}"
            )

        top_keywords = [kw['keyword'] for kw in (keywords[:30] if keywords else [])]
        topic_descriptions = []
        if topics:
            for topic in topics:
                topic_descriptions.append(
                    f"主题 {topic['topic_id']}: {', '.join(topic['keywords'][:8])}"
                )

        prompt = self._build_llm_analysis_prompt(
            papers_summary="\n".join(papers_summary),
            keywords=", ".join(top_keywords),
            topics="\n".join(topic_descriptions),
            paper_count=len(papers),
        )

        self.logger.info("正在使用旧版 LLM API 生成分析报告...")
        response = self.llm_client.generate(prompt, max_tokens=self.llm_client.max_tokens)
        analysis = self._parse_llm_response(response)
        self.logger.info("✓ 旧版 LLM API 分析完成")
        return analysis

    def _build_llm_analysis_prompt(self, papers_summary: str, keywords: str, 
                              topics: str, paper_count: int) -> str:
        """构建旧版 LLM 分析提示词。"""
        prompt = f"""作为一位资深的 AI 研究专家，请基于以下 {paper_count} 篇最新的 arXiv 论文进行深入分析。

## 论文列表（前30篇）：
{papers_summary}

## 高频关键词：
{keywords}

## 主要研究主题：
{topics}

请按照以下结构进行全面分析（用中文回答）：

### 1. 当前研究热点分析 (Current Research Hotspots)
分析当前这个研究领域最热门的3-5个研究方向，并说明为什么这些方向受到关注。

### 2. 技术趋势与演进 (Technical Trends)
识别技术发展的趋势，包括：
- 主流的技术方法和架构
- 正在兴起的新技术
- 从论文中观察到的技术演进路径

### 3. 未来发展方向 (Future Directions)
基于当前研究状况，预测未来6-12个月可能的研究方向，包括：
- 现有热点的可能延伸
- 尚未充分探索但有潜力的方向
- 可能的技术突破点

### 4. 创新研究想法 (Research Ideas & Innovation Points)
提出5-8个具有创新性和可行性的研究想法，每个想法包括：
- 核心创新点
- 为什么这个想法有价值
- 可能的技术实现路径
- 潜在的应用场景

请用 Markdown 格式输出，使用清晰的标题和列表。"""

        return prompt
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应
        
        Args:
            response: LLM 响应文本
            
        Returns:
            解析后的分析结果
        """
        # 尝试按照标题分割
        sections = {
            'hotspots': '',
            'trends': '',
            'future_directions': '',
            'research_ideas': '',
            'full_analysis': response
        }
        
        # 简单的分割逻辑（可以根据实际响应格式调整）
        current_section = None
        current_content = []
        
        for line in response.split('\n'):
            line_stripped = line.strip()
            line_lower = line_stripped.lower()
            
            # 检查是否为标题行 (以 # 开头)
            is_header = line_stripped.startswith('#')
            
            if is_header and ('研究热点' in line or 'hotspot' in line_lower):
                if current_section and current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'hotspots'
                current_content = [line]
            elif is_header and ('趋势' in line or 'trend' in line_lower):
                if current_section and current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'trends'
                current_content = [line]
            elif is_header and ('未来' in line or 'future' in line_lower or '发展方向' in line):
                if current_section and current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'future_directions'
                current_content = [line]
            elif is_header and ('创新' in line or 'idea' in line_lower or '想法' in line):
                if current_section and current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'research_ideas'
                current_content = [line]
            elif current_section:
                current_content.append(line)
        
        # 保存最后一个部分
        if current_section and current_content:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return sections
    
    def _save_analysis(self, analysis: Dict[str, Any]):
        """保存分析结果
        
        Args:
            analysis: 分析结果
        """
        output_dir = Path('data/analysis')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        date_str = get_date_string(config=self.config)
        
        # 保存 JSON 格式
        json_path = f"data/analysis/analysis_{date_str}.json"
        save_json(analysis, json_path)
        self.logger.info(f"💾 分析结果已保存: {json_path}")
        
        # 保存最新分析（供 Web 服务使用）
        latest_path = "data/analysis/latest.json"
        save_json(analysis, latest_path)
        self.logger.info(f"💾 最新分析已保存: {latest_path}")
        
        # 生成 Markdown 报告
        markdown_path = f"data/analysis/report_{date_str}.md"
        self._generate_markdown_report(analysis, markdown_path)
        self.logger.info(f"📄 Markdown 报告已保存: {markdown_path}")
    
    def _generate_markdown_report(self, analysis: Dict[str, Any], output_path: str):
        """生成 Markdown 格式的分析报告
        
        Args:
            analysis: 分析结果
            output_path: 输出路径
        """
        llm_analysis = analysis.get('llm_analysis', {})
        statistics = analysis.get('statistics', {})
        keywords = analysis.get('keywords', [])
        
        report = f"""<!-- paper_signature:{analysis.get('paper_signature', '')} -->
# 研究趋势分析报告

**生成日期**: {analysis.get('date')}  
**运行ID**: {analysis.get('run_id', 'N/A')}  
**分析论文数**: {analysis.get('paper_count')}  
**分析方式**: {analysis.get('analysis_engine', 'unknown')}  
**生成时间**: {analysis.get('generated_at')}

---

## 📊 统计概览

- **总论文数**: {statistics.get('total_papers', 0)}
- **涉及作者数**: {statistics.get('total_authors', 0)}
- **研究类别数**: {statistics.get('total_categories', 0)}

### 类别分布

| 类别 | 论文数 |
|------|--------|
"""
        
        for cat, count in list(statistics.get('category_distribution', {}).items())[:10]:
            report += f"| {cat} | {count} |\n"
        
        report += "\n### 高频关键词\n\n"
        for kw in keywords[:20]:
            report += f"- **{kw['keyword']}** (权重: {kw['score']:.4f})\n"
        
        report += "\n---\n\n## 🔥 研究热点分析\n\n"
        report += llm_analysis.get('hotspots', '未生成')
        
        report += "\n\n---\n\n## 📈 技术趋势与演进\n\n"
        report += llm_analysis.get('trends', '未生成')
        
        report += "\n\n---\n\n## 🔮 未来发展方向\n\n"
        report += llm_analysis.get('future_directions', '未生成')
        
        report += "\n\n---\n\n## 💡 创新研究想法\n\n"
        report += llm_analysis.get('research_ideas', '未生成')
        
        report += "\n\n---\n\n## 📸 词云图\n\n"
        report += f"![词云图]({analysis.get('wordcloud_path', '')})\n"
        
        report += "\n---\n\n*本报告由 Daily arXiv Agent（Copilot 驱动分析）自动生成*\n"
        
        # 保存报告
        save_text(report, output_path)
    
    def print_analysis_summary(self, analysis: Dict[str, Any]):
        """打印分析摘要
        
        Args:
            analysis: 分析结果
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("📊 趋势分析摘要")
        self.logger.info("=" * 80)
        
        statistics = analysis.get('statistics', {})
        keywords = analysis.get('keywords', [])
        
        self.logger.info(f"\n总论文数: {statistics.get('total_papers', 0)}")
        self.logger.info(f"涉及作者: {statistics.get('total_authors', 0)}")
        self.logger.info(f"研究类别: {statistics.get('total_categories', 0)}")
        
        self.logger.info("\n高频关键词 (Top 15):")
        for kw in keywords[:15]:
            self.logger.info(f"  - {kw['keyword']}")
        
        self.logger.info("\n类别分布:")
        for cat, count in list(statistics.get('category_distribution', {}).items())[:8]:
            self.logger.info(f"  - {cat}: {count} 篇")
        
        llm_analysis = analysis.get('llm_analysis', {})
        if llm_analysis.get('full_analysis'):
            self.logger.info("\n" + "=" * 80)
            self.logger.info("🤖 Agent 深度分析")
            self.logger.info("=" * 80)
            # 只打印前500个字符
            full_text = llm_analysis.get('full_analysis', '')
            preview = full_text[:500] + "..." if len(full_text) > 500 else full_text
            self.logger.info(f"\n{preview}")
            self.logger.info(f"\n完整分析请查看: data/analysis/report_{analysis.get('date')}.md")
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info(f"📸 词云图: {analysis.get('wordcloud_path')}")
        self.logger.info("=" * 80 + "\n")


def main():
    """测试函数"""
    from src.utils import load_config, load_env, setup_logging, load_json
    
    load_env()
    config = load_config()
    logger = setup_logging(config)
    
    # 加载论文数据
    papers_path = Path(get_data_path(config, 'papers')) / 'latest.json'
    papers_data = load_json(str(papers_path))
    if not papers_data:
        logger.error("未找到论文数据，请先运行论文爬取")
        return
    
    papers = papers_data.get('papers', [])
    
    # 加载总结数据
    summaries_data = load_json('data/summaries/latest.json')
    summaries = summaries_data.get('papers', []) if summaries_data else None
    
    # 创建分析器
    analyzer = TrendAnalyzer(config)
    
    # 执行分析
    analysis = analyzer.analyze(papers, summaries)
    
    # 打印摘要
    analyzer.print_analysis_summary(analysis)


if __name__ == "__main__":
    main()
