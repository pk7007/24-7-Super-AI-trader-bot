FROM python:3.12-slim@sha256:5b5fe805d367f8f5a359ded6ab2652b7f9a206453ee6ee789c0045ba6ec15016
ENV TZ=UTC PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock
COPY bot ./bot
COPY SAFETY_RULES.md ./
RUN useradd -m bot && mkdir -p state data models && chown -R bot /app
USER bot
# No secrets in the image (RULE 6). Paper/shadow need none; .dockerignore keeps .env out of the build context.
CMD ["python", "-m", "bot.main", "paper"]
