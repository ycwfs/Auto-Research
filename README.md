
# Auto-Research – AI Research Tracker 📚🤖

**English Document** | [中文文档](README_zh.md)

Automatically track the latest AI research papers on arXiv each day, generate full-text-based bilingual summaries with Copilot CLI + MinerU, analyze research trends, sync structured notes to Zotero, and create a weekly research idea.

## ✨ Features

### Core Functions

- 🔍 **Intelligent Crawling**: Daily automatic fetching of the newest papers from arXiv in specified fields  
  - Supports multiple research areas (cs.AI, cs.LG, cs.CV, etc.)  
  - Keyword filtering  
  - TF‑IDF based smart selection  
  - Keeps only papers not seen in earlier runs, and skips later steps when no new papers are found  

- 🤖 **Agent‑Driven Full‑Text Summarization**: Use Copilot CLI + MinerU MCP to read paper PDFs before summarizing  
  - Full-text extraction to Markdown for each paper  
  - Structured bilingual (Chinese + English) summaries  
  - Zotero-ready bilingual note bodies persisted in JSON  

- 📊 **Trend Analysis**: In‑depth analysis of research hot topics and technological trends  
  - TF‑IDF keyword extraction  
  - LDA topic modeling  
  - Word‑cloud visualization  
  - Copilot-driven daily narrative analysis (research hotspots, technology trends, future directions)  

- 🌐 **Web Interface**: Modern responsive web UI  
  - Built with Bootstrap 5  
  - Real‑time data display  
  - Detailed paper view  
  - Pagination and filtering  

- ⏰ **Scheduled Execution**: Various scheduling options  
  - APScheduler (recommended)  
  - Linux cron jobs  
  - Systemd service  

- 📚 **Zotero Sync**: Optional daily Copilot CLI + Zotero MCP upload job  
  - Reads `data/papers/latest.json` and `data/summaries/latest.json`  
  - Appends English and Chinese full-text-based notes to each paper  
  - Stores daily summary/analysis reports in the `daily analysis` collection  

- 💡 **Weekly Idea Generation**: Optional Thursday Copilot CLI + Zotero MCP synthesis job  
  - Summarizes this week's locally collected papers  
  - Reviews the broader Zotero repository for supporting signals  
  - Saves an introduction-ready idea into the `idea` collection and local artifacts  

- 📧 **Email Notifications**: Execution status via email  
  - Elegant HTML email templates  
  - Separate success/failure notices  
  - Detailed statistics  

## 📸 Interface Preview

![alt text](resources/image0.png)![alt text](resources/image1.png)![alt text](resources/image2.png)

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Conda (recommended) or virtualenv
- GitHub Copilot CLI logged in
- Configured `mineru` and `zotero` MCP servers
- Optional legacy LLM API keys only if you still use the older provider-based modules directly

### 1. Clone the repository

```bash
git clone https://github.com/ycwfs/Auto-Research
cd auto-research
```

### 2. Create a virtual environment

```bash
# Using Conda (recommended)
conda create -n auto-research python=3.12 -y
conda activate auto-research

# Or using venv
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 3. Install dependencies

```bash
pip install uv
uv pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
# Copy the example file
cp .env.example .env

# Edit the .env file
nano .env
```

Optional legacy API keys:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Google Gemini
GEMINI_API_KEY=...

# Anthropic Claude
ANTHROPIC_API_KEY=...

# DeepSeek
DEEPSEEK_API_KEY=...

# vLLM (local deployment)
VLLM_API_KEY=EMPTY

# Email notifications (optional)
EMAIL_PASSWORD=your-app-password
```

### 5. Configure `config.yaml`

Edit `config/config.yaml`:

```yaml
# Research fields
arxiv:
  categories:
    - "cs.AI"  # Artificial Intelligence
    - "cs.LG"  # Machine Learning
  
  keywords:
    - "large language model"
    - "transformer"
  
  max_results: 20

# Agent workflow
agent:
  copilot_command: "copilot"
  reasoning_effort: "high"

# Backend switching
pipeline:
  summary_backend: "agent"   # agent or llm
  analysis_backend: "agent"  # agent or llm

# Scheduler settings
scheduler:
  enabled: true
  run_time: "09:00"
  timezone: "Asia/Shanghai"
  zotero_upload:
    enabled: true
    run_time: "09:30"
  weekly_idea:
    enabled: true
    day_of_week: "thu"
    run_time: "10:00"
```

### 6. Run tests

```bash
# Test paper fetching
python test/test_fetcher.py

# Test full-text summarization config
python test/test_summarizer.py

# Test trend-analysis config and local helpers
python test/test_analyzer.py

# Test weekly idea config
python test/test_weekly_idea.py

# Test web service
python test/test_web.py

# Test scheduler
python test/test_scheduler.py
```

### 7. Execute the full workflow

```bash
# Manual single run
python main.py

# Manual Zotero upload run
python zotero_upload.py

# Manual weekly idea run
python weekly_idea.py
```

### 8. Start the web service

```bash
# Development mode
python src/web/app.py

# Open http://localhost:5000
```

### 9. Launch scheduled execution

```bash
# Recommended: use the start script
./deploy/start.sh

# Or run directly
python scheduler.py
```

If `scheduler.zotero_upload.enabled` is `true`, the same scheduler process also runs the daily Zotero upload prompt at the configured time. If `scheduler.weekly_idea.enabled` is `true`, it also runs the Thursday weekly synthesis-and-idea task after the daily upload window.

### Switching back to legacy API LLMs

The daily pipeline can now switch by config only:

```yaml
pipeline:
  summary_backend: "llm"
  analysis_backend: "llm"

llm:
  provider: "openai"  # or gemini / claude / deepseek / vllm
```

Then set the matching API key in `.env`. You can also mix backends, for example `summary_backend: "agent"` with `analysis_backend: "llm"`.

Visit http://localhost:5000 to view results.

## 📂 Project Structure

```
daily-arxiv/
├── config/
│   └── config.yaml              # Main configuration file
├── src/
│   ├── crawler/
│   │   └── arxiv_fetcher.py    # arXiv paper crawler
│   ├── summarizer/
│   │   └── paper_summarizer.py # Copilot + MinerU full-text summarizer
│   ├── analyzer/
│   │   └── trend_analyzer.py   # Local stats + Copilot narrative analysis
│   ├── automation/
│   │   ├── copilot_runner.py   # Shared Copilot CLI helpers
│   │   ├── weekly_idea_runner.py
│   │   └── zotero_prompt_runner.py
│   ├── web/
│   │   ├── app.py             # Flask web app
│   │   └── templates/
│   │       └── index.html     # Web UI page
│   ├── notifier/
│   │   └── email_notifier.py  # Email notifier
│   └── utils.py               # Utility functions
├── static/
│   └── js/
│       └── main.js            # Front‑end JavaScript
├── data/                      # Data storage
│   ├── papers/               # Paper JSON files
│   ├── summaries/            # Structured bilingual summary JSON files
│   ├── fulltext/             # MinerU Markdown outputs
│   ├── analysis/             # Trend reports and word clouds
│   └── ideas/                # Weekly idea artifacts
├── logs/                     # Log files
├── deploy/                   # Deployment scripts
│   ├── start.sh             # Start script
│   ├── daily-arxiv.service  # Systemd service
│   └── crontab.example      # Cron example
├── docs/                     # Documentation
│   ├── arxiv_fetcher_guide.md
│   ├── trend_analyzer_guide.md
│   ├── web_interface_guide.md
│   └── scheduler_guide.md
├── main.py                   # Main entry point
├── scheduler.py              # APScheduler dispatcher
├── test_*.py                # Test scripts
├── requirements.txt         # Python dependencies
├── .env.example            # Example env file
├── weekly_idea.py            # Weekly idea entry point
└── README.md                 # Project overview
```

## ⚙️ Configuration Details

### arXiv Category Codes

Common Computer Science categories:  
- `cs.AI` – Artificial Intelligence  
- `cs.LG` – Machine Learning  
- `cs.CV` – Computer Vision  
- `cs.CL` – Computation and Language (NLP)  
- `cs.NE` – Neural and Evolutionary Computing  
- `stat.ML` – Machine Learning (Statistics)  

See the full list at: https://arxiv.org/category_taxonomy

### LLM Providers

Supported providers:  
- **OpenAI**: GPT‑4, GPT‑3.5‑turbo  
- **Gemini**: Gemini models  
- **Anthropic**: Claude  
- **DeepSeek**: DeepSeek models  
- **vLLM**: Locally run open‑source models (OpenAI‑compatible API)

## 📝 Development Roadmap

- [x] Project scaffolding ✅  
- [x] arXiv crawling ✅  
- [x] LLM summarization ✅  
  - Support OpenAI, Gemini, Claude, DeepSeek, vLLM  
- [x] Trend analysis ✅  
  - Keyword extraction, topic modeling, word‑cloud generation  
  - LLM‑driven deep analysis (hotspots, trends, innovations)  
- [x] Web UI development  
- [x] Scheduling functionality  
- [x] Testing & optimization  
- [ ] UI beautification  
- [ ] Add WeChat public account integration  

## 🧪 Testing

```bash
# Test paper crawler
python test/test_fetcher.py

# Test summarizer
python test/test_summarizer.py

# Test trend analyzer
python test/test_analyzer.py

# Run full pipeline
python main.py
```

## 📊 Generated Files

```
data/
├── papers/
│   ├── papers_YYYY-MM-DD.json   # Daily paper data
│   └── latest.json              # Latest paper data
├── summaries/
│   ├── summaries_YYYY-MM-DD.json# Daily summaries
│   └── latest.json              # Latest summaries
└── analysis/
    ├── wordcloud_YYYY-MM-DD.png # Word‑cloud image
    ├── analysis_YYYY-MM-DD.json # Analysis results
    ├── report_YYYY-MM-DD.md     # Markdown report
    └── latest.json              # Latest analysis data
```

## 📖 Documentation

- [Paper Crawler Guide](docs/arxiv_fetcher_guide.md)  
- [LLM Summarizer Guide](docs/llm_guide.md)  
- [Configuration Guide](docs/config_guide.md)

## 🤝 Contributing

Feel free to open Issues and submit Pull Requests!

## 📄 License

MIT License
