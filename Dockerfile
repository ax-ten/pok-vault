FROM python:3.10.12
WORKDIR /usr/src/app
COPY . .
RUN mkdir ./images

RUN pip install --upgrade pip

# Installa le dipendenze da requirements.txt e registra gli errori
RUN pip install --no-cache-dir -r requirements.txt 

CMD ["python", "-u", "./bot.py"]
