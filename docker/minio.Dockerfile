# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM golang:1.24.8-alpine@sha256:3d78beb141d98f42337f1252ecf2a5f20374109929a4c3f6817f9e4179cc0ae5 AS build

ARG TARGETOS
ARG TARGETARCH
ENV GOTOOLCHAIN=local GOMAXPROCS=1 GOGC=30 GOMEMLIMIT=512MiB CGO_ENABLED=0
RUN apk add --no-cache git ca-certificates
WORKDIR /src
RUN git init \
    && git remote add origin https://github.com/minio/minio.git \
    && git fetch --depth 1 origin 9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a"
RUN --mount=type=cache,target=/go/pkg/mod go mod download && go mod verify
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    ldflags="$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go 2025-10-15T17:29:55Z)" \
    && GOOS="${TARGETOS:-linux}" GOARCH="${TARGETARCH:-arm64}" \
       go build -p 1 -mod=readonly -trimpath -ldflags "$ldflags" -o /out/minio . \
    && git archive --format=tar.gz HEAD -o /out/minio-source.tar.gz

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8
RUN apk add --no-cache ca-certificates curl
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /usr/share/doc/minio/LICENSE
COPY --from=build /out/minio-source.tar.gz /usr/share/doc/minio/source.tar.gz
LABEL org.opencontainers.image.title="MinIO Server" \
      org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a" \
      org.opencontainers.image.version="RELEASE.2025-10-15T17-29-55Z" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
EXPOSE 9000
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data"]
