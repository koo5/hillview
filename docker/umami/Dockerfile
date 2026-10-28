# Preserve the reviewed application release while refreshing Alpine security
# packages independently of the upstream image publication schedule.
# umami 3.4.1 (tag 3.4.1 / postgresql-latest on 2026-10-25, published 2026-10-23). Bumped from
# 3.3.0 on 2026-10-25 for CVE-2026-111497: the 3.3.0 image ships Node 22.23.2 with the
# vulnerable bundled brotli decoder; this one ships Node 22.23.4. Taken inside the 14-day
# cooloff as a deliberate security exception.
FROM ghcr.io/umami-software/umami@sha256:e69d1a7932e9dab0fc523edc7be1f3a53f3c261f57856fc2167ae74a8fc022e8
USER root
RUN apk upgrade --no-cache
USER nextjs
