# Valio Aimo ordering portal: one small Python server.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "uvicorn[standard]"
COPY api ./api
COPY chefagent ./chefagent
COPY public ./public
# Account documents live on a mounted volume. Valio's catalogue is downloaded
# from Valio's API on first start and is never part of the image.
ENV AURORA_LOCAL_DB=/data/accounts.sqlite
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
