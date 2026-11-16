FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MUJOCO_GL=egl

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libegl1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_INDEX_URL=http://mirrors.cloud.aliyuncs.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.aliyuncs.com

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3.12-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
COPY simulation ./simulation

RUN python -m pip install --break-system-packages --no-cache-dir -e ".[simulation,vlm]"
RUN python -m pip install --break-system-packages --no-cache-dir "websockets>=15,<17"

EXPOSE 8000

CMD ["uvicorn", "cube_relay.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
