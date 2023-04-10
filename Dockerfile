FROM python:3.10

WORKDIR /app

COPY . .

RUN python3 -m pip install -U -r requirements.txt

CMD python -u -m easterobot