# The knowledge layer service. Untested here (no Docker daemon on the machine it was written on).
FROM python:3.12-slim
WORKDIR /app
COPY requirements-service.txt .
RUN pip install --no-cache-dir -r requirements-service.txt
COPY src/ src/
COPY projects/ projects/
COPY codegraph/ codegraph/
COPY kl/ kl/
COPY extract-prompt.md .
ENV KL_DATA_DIR=/data KL_PUBLIC_URL=http://localhost:8080 PYTHONUTF8=1
VOLUME /data
EXPOSE 8080
CMD ["python", "-m", "kl", "serve", "--host", "0.0.0.0", "--port", "8080"]
