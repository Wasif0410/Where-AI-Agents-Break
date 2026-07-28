FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages \
    reportlab==4.2.5 \
    pandas==2.2.3 \
    pdfplumber==0.11.4 \
    pyarrow==18.1.0 \
    scikit-learn==1.5.2 \
    numpy==1.26.4 \
    PyYAML==6.0.2

WORKDIR /root

COPY data /tmp/task-data
RUN mkdir -p /root/data /root/project && \
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
