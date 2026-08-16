# Supervisor stopped supplying BUILD_FROM in 2026.04.0, so the base image is
# named explicitly and the ARG is only an override for building by hand or on
# another architecture. On a Raspberry Pi this becomes aarch64-base-python, and
# `arch` in config.yaml has to agree.
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.23
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The panel is drawn in 1-bit with FreeType's monochrome rasteriser, so it needs
# real font files -- there is no system fallback that would do. DejaVu covers
# both roles the layout asks for, sans and serif, and panel/render/fonts.py
# looks in Alpine's /usr/share/fonts/dejavu first.
RUN apk add --no-cache font-dejavu

WORKDIR /app

# Dependencies first, so editing the layout does not reinstall Pillow.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY panel/ ./panel/
COPY data/ ./data/
COPY panel.yaml serve.py render_panel.py ./
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Fail the build rather than the first render if a font or an import is missing.
RUN python3 -c "\
from panel.render import fonts, layout; \
from panel import sample; \
missing = [role for role, path in fonts.available().items() if path is None]; \
assert not missing, f'no font for {missing}'; \
assert layout.render(sample.panel()).image.size == (800, 480); \
print('fonts:', fonts.available())"

LABEL \
  io.hass.name="Hallway Panel" \
  io.hass.description="Renders an 800x480 1-bit e-paper dashboard" \
  io.hass.type="addon" \
  io.hass.arch="amd64"

CMD ["/run.sh"]
