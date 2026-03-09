FROM python:3.11-slim

# Install FFmpeg + fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Montserrat font
RUN mkdir -p /usr/share/fonts/truetype/montserrat && \
    curl -sL "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf" \
    -o /usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf && \
    curl -sL "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Regular.ttf" \
    -o /usr/share/fonts/truetype/montserrat/Montserrat-Regular.ttf && \
    fc-cache -fv

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Create workspace dirs
RUN mkdir -p workspace/clips workspace/audio workspace/output workspace/temp

# Environment
ENV FONT_BOLD=/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf
ENV FONT_REGULAR=/usr/share/fonts/truetype/montserrat/Montserrat-Regular.ttf
ENV PYTHONUNBUFFERED=1

EXPOSE 8420

CMD ["python", "-m", "spiral_render.server"]
