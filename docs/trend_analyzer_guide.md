# 趋势分析模块使用指南

## 📖 模块介绍

`trend_analyzer.py` 是负责分析论文集合，生成研究趋势报告的核心模块。它结合了传统的文本分析技术和 LLM 的深度理解能力，提供全面的研究趋势洞察。

## 🎯 主要功能

### 1. 关键词提取 (Keyword Extraction)

使用 **TF-IDF** 算法提取最重要的研究关键词：

- 识别高频技术术语
- 支持单词和二元组 (bigrams)
- 自动过滤停用词
- 返回带权重的关键词列表

**输出示例**:
```json
{
  "keyword": "transformer",
  "score": 0.2845
}
```

### 2. 主题提取 (Topic Modeling)

使用 **LDA (Latent Dirichlet Allocation)** 发现潜在研究主题：

- 自动聚类相似论文
- 识别研究子方向
- 提取每个主题的代表性关键词

**输出示例**:
```json
{
  "topic_id": 1,
  "keywords": ["neural", "network", "training", "optimization"],
  "weights": [0.15, 0.12, 0.10, 0.08]
}
```

### 3. 词云生成 (Word Cloud)

生成美观的词云图，直观展示研究热点：

- 高分辨率图片 (1600x800)
- 自定义配色方案
- 自动调整字体大小
- 保存为 PNG 格式

**生成路径**: `data/analysis/wordcloud_YYYY-MM-DD.png`

### 4. 统计分析 (Statistical Analysis)

生成详细的统计报告：

- 论文、作者、类别数量统计
- 类别分布
- 高产作者识别
- 高频词统计
- 时间分布分析

### 5. LLM 深度分析 (LLM Deep Analysis)

使用大语言模型进行深度分析，生成：

#### a) 当前研究热点 (Current Hotspots)
- 识别最热门的研究方向
- 分析热度原因
- 关注度趋势

#### b) 技术趋势与演进 (Technical Trends)
- 主流技术方法和架构
- 正在兴起的新技术
- 技术演进路径分析

#### c) 未来发展方向 (Future Directions)
- 预测未来 6-12 个月的研究方向
- 识别未充分探索的机会
- 可能的技术突破点

#### d) 创新研究想法 (Research Ideas)
- 5-8 个具体的研究想法
- 每个想法包括：
  - 核心创新点
  - 价值分析
  - 技术实现路径
  - 应用场景

## 🚀 使用方法

### 基础用法

```python
from src.utils import load_config, load_env, setup_logging, load_json
from src.analyzer.trend_analyzer import TrendAnalyzer
from src.summarizer.llm_factory import LLMClientFactory

# 初始化
load_env()
config = load_config()
logger = setup_logging(config)

# 加载论文数据
papers_data = load_json('data/papers/latest.json')
papers = papers_data['papers']

# 加载论文总结（可选）
summaries_data = load_json('data/summaries/latest.json')
summaries = summaries_data.get('summaries', [])

# 创建 LLM 客户端
llm_client = LLMClientFactory.create_client(config)

# 创建分析器
analyzer = TrendAnalyzer(config, llm_client)

# 执行完整分析
analysis = analyzer.analyze(papers, summaries)

# 打印摘要
analyzer.print_analysis_summary(analysis)
```

### 高级用法

#### 1. 只提取关键词（不需要 LLM）

```python
analyzer = TrendAnalyzer(config, llm_client=None)
keywords = analyzer._extract_keywords(papers, top_n=50)

for kw in keywords[:10]:
    print(f"{kw['keyword']}: {kw['score']:.4f}")
```

#### 2. 只生成词云

```python
analyzer = TrendAnalyzer(config, llm_client=None)
wordcloud_path = analyzer._generate_wordcloud(papers)
print(f"词云已保存: {wordcloud_path}")
```

#### 3. 自定义主题数量

```python
topics = analyzer._extract_topics(papers, n_topics=10)
```

#### 4. 获取统计信息

```python
statistics = analyzer._generate_statistics(papers, summaries)
print(f"总论文数: {statistics['total_papers']}")
print(f"类别分布: {statistics['category_distribution']}")
```

## 📊 输出文件

### 1. JSON 格式 (`data/analysis/analysis_YYYY-MM-DD.json`)

完整的分析结果，包含所有数据：

```json
{
  "date": "2025-10-13",
  "paper_count": 20,
  "keywords": [...],
  "topics": [...],
  "statistics": {...},
  "wordcloud_path": "...",
  "llm_analysis": {...},
  "generated_at": "2025-10-13T14:30:00"
}
```

### 2. Markdown 报告 (`data/analysis/report_YYYY-MM-DD.md`)

格式化的分析报告，适合阅读和分享：

```markdown
# 研究趋势分析报告

**生成日期**: 2025-10-13
**分析论文数**: 20

## 📊 统计概览
...

## 🔥 研究热点分析
...

## 📈 技术趋势与演进
...

## 🔮 未来发展方向
...

## 💡 创新研究想法
...
```

### 3. 词云图片 (`data/analysis/wordcloud_YYYY-MM-DD.png`)

高分辨率的词云可视化图片

### 4. 最新分析 (`data/analysis/latest.json`)

供 Web 服务使用的最新分析结果

## ⚙️ 配置说明

分析器会使用 `config.yaml` 中的 LLM 配置：

```yaml
llm:
  provider: "openai"  # 或 gemini, claude, deepseek, vllm
  
  openai:
    api_key: "your-key"
    model: "gpt-4"
    temperature: 0.7
    max_tokens: 3000  # 分析需要更多 tokens
```

### 推荐配置

对于趋势分析，推荐使用：

- **模型**: GPT-4, Claude 3 Opus, Gemini Pro
- **温度**: 0.7-0.8 (需要一定创造性)
- **Max Tokens**: 2000-3000 (分析报告较长)

## 🔍 分析质量优化

### 1. 论文数量

- **最少**: 10 篇论文（基础分析）
- **推荐**: 20-50 篇论文（较全面）
- **最佳**: 50+ 篇论文（深度分析）

### 2. 包含论文总结

提供论文总结会显著提升分析质量：

```python
# 先总结论文
summaries = summarizer.summarize_papers(papers)

# 再分析趋势（包含总结）
analysis = analyzer.analyze(papers, summaries)
```

### 3. 选择合适的 LLM

不同任务的推荐：

| 任务 | 推荐模型 | 原因 |
|------|---------|------|
| 研究热点 | GPT-4, Claude 3 | 深度理解能力强 |
| 趋势预测 | GPT-4, Gemini Pro | 推理能力好 |
| 创新想法 | Claude 3, GPT-4 | 创造性强 |
| 快速分析 | GPT-3.5, Gemini | 成本低，速度快 |

## 📝 实际应用场景

### 场景 1: 每日研究跟踪

```python
# 每天运行
papers = fetcher.fetch_papers(days_back=1)
summaries = summarizer.summarize_papers(papers)
analysis = analyzer.analyze(papers, summaries)
```

### 场景 2: 周报生成

```python
# 每周运行
papers = fetcher.fetch_papers(days_back=7)
summaries = summarizer.summarize_papers(papers)
analysis = analyzer.analyze(papers, summaries)

# 使用生成的 Markdown 报告作为周报
```

### 场景 3: 选题研究

```python
# 获取大量论文
papers = fetcher.fetch_papers(days_back=30)
config['arxiv']['max_results'] = 100

# 深度分析
analysis = analyzer.analyze(papers, summaries)

# 从 research_ideas 中选择课题
ideas = analysis['llm_analysis']['research_ideas']
```

### 场景 4: 竞品分析

```python
# 配置特定关键词
config['arxiv']['keywords'] = ['competitor_method']

# 分析竞争对手的研究方向
papers = fetcher.fetch_papers()
analysis = analyzer.analyze(papers)
```

## 🐛 常见问题

### Q1: 词云生成失败

**可能原因**:
- 缺少字体文件
- matplotlib 后端问题

**解决方法**:
```python
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
```

### Q2: LLM 分析超时

**解决方法**:
- 减少论文数量（只用前 30 篇）
- 增加 `max_tokens` 限制
- 优化提示词长度

### Q3: 关键词不准确

**优化方法**:
```python
# 添加自定义停用词
analyzer.stop_words.update(['custom', 'stopword'])

# 调整 TF-IDF 参数
keywords = analyzer._extract_keywords(
    papers, 
    top_n=100,  # 增加数量
    min_df=3    # 提高最小文档频率
)
```

### Q4: 主题重叠严重

**解决方法**:
```python
# 调整主题数量
topics = analyzer._extract_topics(papers, n_topics=8)

# 或增加论文数量以提高区分度
```

### Q5: 分析报告质量不高

**改进建议**:

1. **提供更多上下文**:
```python
# 包含论文总结
summaries = summarizer.summarize_papers(papers)
analysis = analyzer.analyze(papers, summaries)
```

2. **使用更好的模型**:
```yaml
llm:
  provider: "openai"
  openai:
    model: "gpt-4"  # 而不是 gpt-3.5-turbo
```

3. **调整提示词**:
修改 `_build_analysis_prompt()` 方法以适应你的需求

## 💡 最佳实践

### 1. 完整工作流

```python
# 1. 爬取论文
papers = fetcher.fetch_papers(days_back=7)

# 2. 总结论文
summaries = summarizer.summarize_papers(papers)

# 3. 趋势分析
analysis = analyzer.analyze(papers, summaries)

# 4. 生成报告
analyzer.print_analysis_summary(analysis)
```

### 2. 定期更新词云

```bash
# 每周一次更新词云背景图
python -c "
from src.analyzer.trend_analyzer import TrendAnalyzer
analyzer = TrendAnalyzer(config)
analyzer._generate_wordcloud(papers)
"
```

### 3. 自定义分析深度

```python
# 浅层分析（快速）
analysis_light = {
    'keywords': analyzer._extract_keywords(papers),
    'wordcloud': analyzer._generate_wordcloud(papers),
    'statistics': analyzer._generate_statistics(papers)
}

# 深度分析（完整）
analysis_deep = analyzer.analyze(papers, summaries)
```

## 📚 相关文档

- [论文爬取指南](arxiv_fetcher_guide.md)
- [论文总结指南](paper_summarizer_guide.md)
- [配置指南](config_guide.md)

## 🔗 技术参考

- [TF-IDF 算法](https://en.wikipedia.org/wiki/Tf%E2%80%93idf)
- [LDA 主题模型](https://en.wikipedia.org/wiki/Latent_Dirichlet_allocation)
- [WordCloud 文档](https://amueller.github.io/word_cloud/)
- [scikit-learn 文档](https://scikit-learn.org/)
