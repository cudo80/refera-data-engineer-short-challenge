FROM python:3.10.10-slim

WORKDIR /usr/src/app

RUN apt-get update && \
    apt-get install -y postgresql-client && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY extract_load.py ./

CMD ["python3", "./extract_load.py"]