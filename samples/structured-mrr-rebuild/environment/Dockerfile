FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages \
    pandas==2.2.3 \
    pyarrow==18.1.0 \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5 \
    python-dateutil==2.9.0.post0

WORKDIR /root

COPY data /tmp/task-data
RUN mkdir -p /root/data && \
    python3 /tmp/task-data/build_inputs.py

# Claude Code
COPY skills /root/.claude/skills
# Codex
COPY skills /root/.codex/skills
# OpenCode
COPY skills /root/.opencode/skill
# Goose
COPY skills /root/.goose/skills
# Factory
COPY skills /root/.factory/skills
# Portable agents format
COPY skills /root/.agents/skills
# GitHub Copilot
COPY skills /root/.github/skills
# Gemini
COPY skills /root/.gemini/skills
