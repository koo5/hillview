# Preserve the reviewed application release while refreshing Alpine security
# packages independently of the upstream image publication schedule.
FROM ghcr.io/umami-software/umami@sha256:87312d334d009ee67ee0d2fba8fed01435547cc468e452243aef5133a9984d48
USER root
RUN apk upgrade --no-cache
USER nextjs
