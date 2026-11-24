FROM python:3.12-slim

LABEL org.opencontainers.image.title="MoneyThistle" \
      org.opencontainers.image.description="Simple personal money manager with a browser interface and WebDAV/Nextcloud backups" \
      net.unraid.docker.webui="http://[IP]:[PORT:8080]/"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    DATA_DIR=/data \
    BACKUP_DIR=/backups \
    NO_BROWSER=1 \
    PUID=99 \
    PGID=100 \
    UMASK=002 \
    TZ=Etc/UTC

# Time zone data, so "today" (bills due, budgets) matches the TZ you set.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /data /backups /app

WORKDIR /app
COPY main.py ./
COPY moneyapp ./moneyapp

# Starts as root only to hand /data and /backups to PUID:PGID (Unraid: 99:100,
# i.e. nobody:users), then drops to that user before opening the money file.
VOLUME ["/data", "/backups"]
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/healthz',timeout=4)"

# Docker sends SIGTERM on stop; the app then runs its after-changes backup.
STOPSIGNAL SIGTERM
CMD ["python", "main.py"]
