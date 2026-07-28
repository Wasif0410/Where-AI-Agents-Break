FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages \
    pandas==2.2.3 numpy==2.1.3 openpyxl==3.1.5 \
    pdfplumber==0.11.4 pyyaml==6.0.2 python-dateutil==2.9.0 \
    reportlab==4.2.5

WORKDIR /root

COPY data /tmp/task-data
RUN mkdir -p /root/data /root/project && python3 /tmp/task-data/build_inputs.py \
    && rm -rf /tmp/task-data \
    && pip3 uninstall -y reportlab 2>/dev/null || true
