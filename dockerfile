FROM python:3.13.0-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN useradd -m myuser
RUN chown -R myuser:myuser /app

USER myuser

EXPOSE 5001

CMD ["python", "src/main.py"]