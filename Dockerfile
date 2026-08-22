FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONPATH=/app/src \
    LEGALRAG_POPPLER_PATH=/usr/bin \
    LEGALRAG_TESSERACT_CMD=/usr/bin/tesseract

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN python -c "from pathlib import Path; p=Path('/app/requirements.txt'); b=p.read_bytes(); enc='utf-16' if b.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig' if b.startswith(b'\xef\xbb\xbf') else 'utf-8'); Path('/tmp/legalrag-requirements.txt').write_text(b.decode(enc), encoding='utf-8', newline='\n')"

RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement /tmp/legalrag-requirements.txt \
    && rm -f /tmp/legalrag-requirements.txt

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin legalrag

COPY --chown=legalrag:legalrag src/ /app/src/

RUN mkdir -p \
        /app/db \
        /app/data \
        /app/docs \
        /app/source_evidence_store \
        /app/report_projections \
        /app/governed_analytical_authorities \
    && chown -R legalrag:legalrag \
        /app/db \
        /app/data \
        /app/docs \
        /app/source_evidence_store \
        /app/report_projections \
        /app/governed_analytical_authorities

USER legalrag

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--server.fileWatcherType=none", "--browser.gatherUsageStats=false"]
