FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY identity.py sensor.py main.py ./

ENTRYPOINT ["python3", "main.py"]
