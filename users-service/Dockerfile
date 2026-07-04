pavan@fedora:~/projects/library-project/rentals-service$ cat Dockerfile
FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:1.13-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY . .
RUN useradd --create-home django
USER django
EXPOSE 8002
CMD ["python", "manage.py", "runserver", "0.0.0.0:8002"]
