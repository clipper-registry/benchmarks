ARG BASE=nvidia/cuda:12.9.0-runtime-ubuntu24.04
ARG EXTRA_PACKAGES=""
FROM ${BASE}
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ${EXTRA_PACKAGES} && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --break-system-packages flask requests numpy pandas scikit-learn torch --extra-index-url https://download.pytorch.org/whl/cu124
COPY app.py /app/app.py
WORKDIR /app
CMD ["python", "app.py"]
