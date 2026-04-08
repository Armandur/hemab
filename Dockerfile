FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hemab_api.py ics_builder.py app.py ./
COPY templates/ templates/

ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
