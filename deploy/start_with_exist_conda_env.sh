#!/bin/bash

# Daily arXiv 自动化部署脚本
# 用于将项目注册为 Systemd 服务并设置开机自启

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}===================================================${NC}"
echo -e "${GREEN}  🚀 Daily arXiv 服务部署脚本${NC}"
echo -e "${GREEN}===================================================${NC}"

# 定义服务文件路径
SCHEDULER_SERVICE="$SCRIPT_DIR/daily-arxiv-scheduler.service"
WEB_SERVICE="$SCRIPT_DIR/daily-arxiv-web.service"

# 1. 检查服务文件是否存在
echo -e "\n${YELLOW}[1/4] 检查配置文件...${NC}"
if [ ! -f "$SCHEDULER_SERVICE" ] || [ ! -f "$WEB_SERVICE" ]; then
    echo -e "${RED}错误：在 $SCRIPT_DIR 目录下未找到 .service 配置文件${NC}"
    exit 1
fi
echo "配置文件检查通过。"

# 2. 链接服务文件
echo -e "\n${YELLOW}[2/4] 注册系统服务 (需要 sudo 权限)...${NC}"
echo "正在链接服务文件到 /etc/systemd/system/ ..."
sudo ln -sf "$SCHEDULER_SERVICE" /etc/systemd/system/
sudo ln -sf "$WEB_SERVICE" /etc/systemd/system/

# 3. 重载配置
echo -e "\n${YELLOW}[3/4] 重新加载 systemd 配置...${NC}"
sudo systemctl daemon-reload

# 4. 启动服务
echo -e "\n${YELLOW}[4/4] 启用并启动服务...${NC}"
echo "启动 Scheduler 服务..."
sudo systemctl enable --now daily-arxiv-scheduler
echo "启动 Web 服务..."
sudo systemctl enable --now daily-arxiv-web

echo -e "\n${GREEN}===================================================${NC}"
echo -e "${GREEN}✅ 服务部署成功！${NC}"
echo -e "${GREEN}===================================================${NC}"
echo ""
echo "服务状态查询："
echo "  sudo systemctl status daily-arxiv-scheduler"
echo "  sudo systemctl status daily-arxiv-web"
echo ""
echo "实时日志查看："
echo "  调度器日志: tail -f $PROJECT_ROOT/logs/scheduler.log"
echo "  Web日志:   tail -f $PROJECT_ROOT/logs/web.log"
echo ""
