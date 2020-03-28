FROM python:3.6-alpine

# Create project directory
RUN mkdir /joonbot
WORKDIR /joonbot/

# cffi depenencies
RUN apk add build-base libffi-dev

# Install Poetry
RUN apk add curl
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python

# Install Python dependencies
COPY pyproject.toml /joonbot/pyproject.toml
COPY poetry.lock /joonbot/poetry.lock
RUN /root/.poetry/bin/poetry config virtualenvs.create false
RUN /root/.poetry/bin/poetry install --no-root --no-dev

COPY . /joonbot

EXPOSE 8080

CMD python manage.py
