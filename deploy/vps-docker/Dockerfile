FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       cabextract \
       curl \
       fluxbox \
       fonts-dejavu-core \
       fonts-liberation \
       gpg \
       procps \
       tini \
       unzip \
       winbind \
       x11-utils \
       x11vnc \
       xdotool \
       xvfb \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSLo /etc/apt/keyrings/winehq-archive.key \
       https://dl.winehq.org/wine-builds/winehq.key \
    && curl -fsSLo /etc/apt/sources.list.d/winehq-bookworm.sources \
       https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources \
    && apt-get update \
    && apt-get install -y --install-recommends winehq-stable \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
    && apt-get install -y --no-install-recommends x11-apps \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /bin/bash mt5

COPY entrypoint.sh /usr/local/bin/straddle-mt5-entrypoint
RUN chmod 0755 /usr/local/bin/straddle-mt5-entrypoint

USER mt5
ENV HOME=/home/mt5 \
    DISPLAY=:99 \
    WINEARCH=win64 \
    WINEDEBUG=-all \
    WINEDLLOVERRIDES=mscoree,mshtml= \
    WINEPREFIX=/data/wineprefix

WORKDIR /data

HEALTHCHECK --interval=20s --timeout=5s --start-period=60s --retries=3 \
  CMD test -S /tmp/.X11-unix/X99 \
      && { test "${MT5_START:-0}" != "1" || pgrep -x main >/dev/null; }

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/straddle-mt5-entrypoint"]
