FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIBCIFPP_DATA_DIR=/usr/share/libcifpp

# 1. Install dssp, curl, gzip, and certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    dssp \
    curl \
    ca-certificates \
    gzip \
    && rm -rf /var/lib/apt/lists/*

# 2. Download and uncompress components.cif into /usr/share/libcifpp
RUN mkdir -p /usr/share/libcifpp /var/cache/libcifpp && \
    curl -fsSL https://files.wwpdb.org/pub/pdb/data/monomers/components.cif.gz | gunzip -c > /usr/share/libcifpp/components.cif && \
    curl -fsSL -o /usr/share/libcifpp/mmcif_pdbx.dic https://mmcif.wwpdb.org/dictionaries/ascii/mmcif_pdbx_v50.dic && \
    curl -fsSL -o /usr/share/libcifpp/mmcif_ma.dic https://github.com/ihmwg/ModelCIF/raw/master/dist/mmcif_ma.dic && \
    cp /usr/share/libcifpp/* /var/cache/libcifpp/

# 3. Ensure mkdssp is on PATH
RUN which mkdssp || ln -s $(which dssp) /usr/local/bin/mkdssp

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
