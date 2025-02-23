# Verwenden Sie ein offizielles Python-Image als Basis
FROM python:3.11-slim

# Setzen Sie die Arbeitsverzeichnis im Container
WORKDIR /app

# Kopieren Sie die requirements.txt-Datei in den Container
COPY requirements.txt .

# Installieren Sie die Python-Abhängigkeiten
RUN pip install --no-cache-dir -r requirements.txt

# Kopieren Sie den Rest des Anwendungscodes in den Container
COPY . .

# Setzen Sie die Umgebungsvariable für die .env-Datei
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Befehl zum Ausführen des Skripts
CMD ["python", "biance_bot_advanced.py"]
