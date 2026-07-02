# 使用主流稳定的 Python 3.9 基础镜像
FROM python:3.9-slim

WORKDIR /app

# 复制依赖列表并安装
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制整个项目内容
COPY . .

# 暴露端口 (FastAPI 默认运行在 8000)
EXPOSE 8000

# 启动 Uvicorn 后端服务器，挂载静态页面
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
