FROM python:3.12-slim

WORKDIR /app

# uv 설치 및 권한 설정
RUN pip install --no-cache-dir uv
RUN mkdir -p /.cache/uv && chmod -R 777 /.cache
ENV UV_CACHE_DIR=/.cache/uv

# uv를 사용하여 의존성 설치
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# 소스 코드 복사
COPY . .

# uv run uvicorn 명령어로 실행
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
