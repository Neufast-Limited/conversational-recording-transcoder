#!/usr/bin/env bash
# Build and push one Docker image, without an OCI image index or attestations.
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: scripts/push_to_ecr.sh [tag]

Defaults: latest, ap-southeast-1, account 826961393531,
          repository conversational-media-transcoder, linux/amd64.
Overrides: AWS_PROFILE, AWS_REGION, AWS_ACCOUNT_ID, ECR_REPOSITORY,
           TARGET_PLATFORM (linux/amd64 or linux/arm64).
Always pulls the base image and rebuilds without cached layers.
Publishes to ECR only; does not update a Lambda function.
EOF
  exit 0
fi

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
[[ $# -le 1 ]] || die 'Expected at most one image tag. See --help.'

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REGION="${AWS_REGION:-ap-southeast-1}"
ACCOUNT_ID="${AWS_ACCOUNT_ID:-826961393531}"
REPOSITORY="${ECR_REPOSITORY:-conversational-media-transcoder}"
PLATFORM="${TARGET_PLATFORM:-linux/amd64}"
TAG="${1:-latest}"
[[ "$TAG" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$ ]] || die 'Invalid Docker image tag.'
[[ "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || die 'AWS_ACCOUNT_ID must contain 12 digits.'
case "$PLATFORM" in
  linux/amd64|linux/arm64) ;;
  *) die 'TARGET_PLATFORM must be linux/amd64 or linux/arm64 (one platform only).' ;;
esac

for dependency in aws docker; do
  command -v "$dependency" >/dev/null || die "$dependency is required."
done
docker info >/dev/null
docker buildx version >/dev/null
PUSH_HELP="$(docker push --help)"
[[ "$PUSH_HELP" == *'--platform'* ]] || die 'Docker must support docker push --platform (API 1.46 or newer). Upgrade Docker before publishing.'

AWS=(aws --region "$REGION")
CALLER_ACCOUNT="$("${AWS[@]}" sts get-caller-identity --query Account --output text)"
[[ "$CALLER_ACCOUNT" == "$ACCOUNT_ID" ]] || die "AWS credentials belong to $CALLER_ACCOUNT; expected $ACCOUNT_ID. Select the correct AWS_PROFILE."
"${AWS[@]}" ecr describe-repositories --repository-names "$REPOSITORY" >/dev/null

REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${REPOSITORY}:${TAG}"
printf 'Building %s for %s\n' "$IMAGE" "$PLATFORM"
# The Docker exporter loads a single image into the local daemon. Do not use
# --push here: registry exporters can publish an index with attestations.
docker buildx build \
  --pull \
  --no-cache \
  --platform "$PLATFORM" \
  --provenance=false \
  --sbom=false \
  --output type=docker,oci-mediatypes=false \
  --tag "$IMAGE" \
  "$PROJECT_DIR"

"${AWS[@]}" ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
# Push only the selected platform's image manifest, even when the daemon uses
# the containerd image store. This explicitly excludes an image index and its
# attestations from the upload.
docker push --platform "$PLATFORM" "$IMAGE"

MEDIA_TYPE="$("${AWS[@]}" ecr batch-get-image \
  --repository-name "$REPOSITORY" \
  --image-ids "imageTag=$TAG" \
  --query 'images[0].imageManifestMediaType' --output text)"
[[ "$MEDIA_TYPE" == 'application/vnd.docker.distribution.manifest.v2+json' ]] \
  || die "ECR returned unexpected manifest type: $MEDIA_TYPE. Expected a single Docker v2 image."
printf 'Published %s\nManifest: %s\n' "$IMAGE" "$MEDIA_TYPE"
"${AWS[@]}" ecr describe-images \
  --repository-name "$REPOSITORY" \
  --image-ids "imageTag=$TAG" \
  --query 'imageDetails[0].{Digest:imageDigest,PushedAt:imagePushedAt}' \
  --output table
