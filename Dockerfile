# Backend image: Node API + the Python ML bridge it spawns.
#
# Vercel's Node runtime has no Python, so `POST /api/v1/score`, the canopy
# ledger and the Disha assistant cannot run there. This image keeps the exact
# local stack (Express + python3 + shapely/pyproj) so the deployed behaviour is
# the same as `npm start` on a developer machine.
#
# Ships the 5-ward demo pack only; the 1.1 GB census index stays out of the
# image (see .dockerignore).

FROM node:20-bookworm-slim

ENV NODE_ENV=production \
    PORT=8080 \
    PYTHON_COMMAND=python3 \
    PMC_DATA_DIR=/app/ml_pipeline/data/demo \
    PMC_CACHE_DIR=/app/ml_pipeline/data/demo \
    PMC_DEMO_WARDS=2,12,23,33,41

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# shapely and pyproj are optional in the pipeline (it falls back to
# equirectangular maths), but the fallback is not what the tests were run
# against. Install them so the deployed numbers match the local ones.
RUN pip3 install --break-system-packages --no-cache-dir shapely==2.2.0 pyproj==3.7.2

WORKDIR /app

COPY backend/package.json backend/package-lock.json ./backend/
RUN cd backend && npm ci --omit=dev

COPY backend ./backend
COPY ml_pipeline ./ml_pipeline

RUN mkdir -p /app/backend/data /app/backend/uploads

EXPOSE 8080

CMD ["node", "backend/src/server.js"]
