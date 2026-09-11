FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
EXPOSE 8000
VOLUME ["/root/.brig"]
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=10s \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/live')" || exit 1
CMD ["brig", "serve", "--host", "0.0.0.0", "--port", "8000"]
