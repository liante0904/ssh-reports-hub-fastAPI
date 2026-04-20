FROM python:3.12-slim

WORKDIR /app

# uv 설치 및 환경 설정
RUN pip install --no-cache-dir uv

# uv를 사용하여 의존성 설치 (.venv 생성)
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# 소스 코드 복사
COPY . .

# uv run 대신 가상환경 내의 uvicorn을 직접 실행 (uv 캐시 이슈 원천 차단)
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
