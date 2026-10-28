FROM golang:1.26.10-alpine AS builder
ENV GOTOOLCHAIN=local
WORKDIR /src
# The upstream Caddy image still embeds Go 1.26.8 and x/net 0.59.0.
# Rebuild the same application release with the released security fixes.
RUN go mod init hillview.local/caddy \
    && go get github.com/caddyserver/caddy/v2@v2.11.7 golang.org/x/net@v0.60.0
COPY main.go ./
RUN go mod tidy && CGO_ENABLED=0 go build -trimpath -o /usr/bin/caddy .

FROM caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
RUN apk upgrade --no-cache
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
