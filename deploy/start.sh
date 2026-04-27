#!/bin/bash

# Daily arXiv 启动脚本

set -e

# 项目目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "============================================================"
echo "  🚀 Daily arXiv Scheduler Launcher"
echo "============================================================"
echo -e "${NC}"

# 检查 Python 环境
if ! command -v python &> /dev/null; then
    echo -e "${RED}❌ Python 未找到！${NC}"
    exit 1
fi

PYTHON_VERSION=$(python --version 2>&1)
echo -e "${GREEN}✅ Python 环境: $PYTHON_VERSION${NC}"

# 检查依赖
echo -e "\n${YELLOW}📦 检查依赖...${NC}"
if python -c "import apscheduler" 2>/dev/null; then
    echo -e "${GREEN}✅ APScheduler 已安装${NC}"
else
    echo -e "${RED}❌ APScheduler 未安装${NC}"
    echo -e "${YELLOW}正在安装...${NC}"
    pip install apscheduler
fi

# 检查配置文件
echo -e "\n${YELLOW}⚙️  检查配置...${NC}"
if [ -f "config/config.yaml" ]; then
    echo -e "${GREEN}✅ 配置文件存在${NC}"
else
    echo -e "${RED}❌ 配置文件不存在！${NC}"
    exit 1
fi

if [ -f ".env" ]; then
    echo -e "${GREEN}✅ 环境变量文件存在${NC}"
else
    echo -e "${YELLOW}⚠️  .env 文件不存在，使用默认配置${NC}"
fi

# 检查数据目录
echo -e "\n${YELLOW}📁 检查数据目录...${NC}"
mkdir -p data/papers data/summaries data/analysis logs
echo -e "${GREEN}✅ 数据目录已就绪${NC}"

# 检查日志目录
mkdir -p logs
echo -e "${GREEN}✅ 日志目录已就绪${NC}"

# 启动选项
echo -e "\n${BLUE}启动选项:${NC}"
echo "  1) 启动调度器 (前台运行)"
echo "  2) 启动调度器 (后台运行)"
echo "  3) 运行一次任务"
echo "  4) 测试邮件通知"
echo "  5) 查看调度器状态"
echo "  6) 停止调度器"
echo "  0) 退出"
echo ""
read -p "请选择 [0-6]: " choice

case $choice in
    1)
        echo -e "\n${GREEN}🚀 启动调度器 (前台运行)...${NC}"
        python scheduler.py
        ;;
    2)
        echo -e "\n${GREEN}🚀 启动调度器 (后台运行)...${NC}"
        nohup python scheduler.py > logs/scheduler.log 2>&1 &
        PID=$!
        echo $PID > logs/scheduler.pid
        echo -e "${GREEN}✅ 调度器已启动，PID: $PID${NC}"
        echo -e "${YELLOW}查看日志: tail -f logs/scheduler.log${NC}"
        echo -e "${YELLOW}停止调度器: ./deploy/start.sh (选项 6)${NC}"
        ;;
    3)
        echo -e "\n${GREEN}🔄 运行一次任务...${NC}"
        python main.py
        ;;
    4)
        echo -e "\n${GREEN}📧 测试邮件通知...${NC}"
        python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from src.utils import load_config, load_env
from src.notifier import send_test_email

load_env()
config = load_config()
notification_config = config.get('scheduler', {}).get('notification', {})
if notification_config.get('enabled', False):
    email_config = notification_config.get('email', {})
    send_test_email(email_config)
else:
    print('⚠️  邮件通知未启用')
"
        ;;
    5)
        echo -e "\n${YELLOW}📊 调度器状态:${NC}"
        if [ -f "logs/scheduler.pid" ]; then
            PID=$(cat logs/scheduler.pid)
            if ps -p $PID > /dev/null 2>&1; then
                echo -e "${GREEN}✅ 调度器运行中，PID: $PID${NC}"
                echo ""
                ps -f -p $PID
            else
                echo -e "${RED}❌ 调度器未运行 (PID 文件存在但进程不存在)${NC}"
                rm logs/scheduler.pid
            fi
        else
            echo -e "${YELLOW}⚠️  未找到 PID 文件${NC}"
        fi
        ;;
    6)
        echo -e "\n${YELLOW}🛑 停止调度器...${NC}"
        if [ -f "logs/scheduler.pid" ]; then
            PID=$(cat logs/scheduler.pid)
            if ps -p $PID > /dev/null 2>&1; then
                kill $PID
                echo -e "${GREEN}✅ 调度器已停止 (PID: $PID)${NC}"
                rm logs/scheduler.pid
            else
                echo -e "${YELLOW}⚠️  进程不存在${NC}"
                rm logs/scheduler.pid
            fi
        else
            echo -e "${YELLOW}⚠️  未找到 PID 文件${NC}"
        fi
        ;;
    0)
        echo -e "\n${BLUE}👋 再见！${NC}"
        exit 0
        ;;
    *)
        echo -e "\n${RED}❌ 无效选项${NC}"
        exit 1
        ;;
esac

echo ""
