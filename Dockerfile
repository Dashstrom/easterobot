FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt requirements.txt

RUN python3 -m pip install -U -r requirements.txt

COPY . .

CMD python -u -m easterobot