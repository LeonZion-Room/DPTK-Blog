#!/bin/bash

# 微信名片H5签名服务启动脚本

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 激活虚拟环境
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# 进入服务器目录
cd "$SCRIPT_DIR/server"

# 启动服务（内网模式）
echo "========================================="
echo "  微信名片H5签名服务"
echo "========================================="
echo "服务地址: http://119.145.17.34:8000"
echo "后台管理: http://119.145.17.34:8000/admin"
echo "管理员账号: admin / admin123"
echo "========================================="
echo ""

exec python3 server.py --mode external
