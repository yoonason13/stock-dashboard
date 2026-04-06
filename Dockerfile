FROM python:3.12-slim

# UTF-8 인코딩 강제 설정 (한국어 처리 필수)
ENV PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/cache

EXPOSE 8080

CMD ["gunicorn", "app:app", "--workers", "1", "--timeout", "300", "--bind", "0.0.0.0:8080"]
