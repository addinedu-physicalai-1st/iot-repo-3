# SoyServer (FastAPI). 빌드 컨텍스트는 프로젝트 루트 (docker-compose에서 context: . 지정)
FROM python:3.12-slim

WORKDIR /app

# 의존성만 먼저 복사해 레이어 캐시 활용
COPY pyproject.toml uv.lock ./
COPY soy-server/ ./soy-server/

# 서버 + 마이그레이션용 의존성 (pyproject.toml과 동기화)
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" alembic sqlalchemy pymysql bcrypt pyserial \
    && python -c "import serial; print('pyserial OK')"

EXPOSE 8000 9001

# 기동 시 마이그레이션 적용 후 uvicorn 실행 (sh로 실행해 볼륨 마운트 시 실행권한 없어도 동작)
CMD ["sh", "/app/soy-server/entrypoint.sh"]
