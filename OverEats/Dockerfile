FROM python:3.11-slim

RUN apt-get update -y && apt-get upgrade -y && apt-get clean

# Add checker user
RUN useradd -ms /bin/bash -u 1000 checker

WORKDIR /checker

COPY requirements.txt .

USER checker
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY ./src .

ENTRYPOINT ["/home/checker/.local/bin/gunicorn", "-c", "gunicorn.conf.py", "checker:app"]
