FROM python:3.9

WORKDIR /app

RUN apt-get update && \
    apt-get install -y \
    libssl-dev build-essential vim gettext \
    python3-pip python3-dotenv

COPY ./requirements.txt ./requirements.txt
RUN pip3 install -r requirements.txt

COPY . ./

EXPOSE 8083

CMD ["python3", "./run.py"]