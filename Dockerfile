FROM ubuntu:24.04

WORKDIR /project/

RUN apt update
RUN apt upgrade -y
RUN apt install -y curl
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY ./.python-version ./
RUN $HOME/.local/bin/uv python install

COPY ./pyproject.toml ./
RUN $HOME/.local/bin/uv sync

COPY ./main.py ./

CMD $HOME/.local/bin/uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload