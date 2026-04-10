#!/usr/bin/env bash
set -eo pipefail

# Initialize variables with default values
image_name=""
org_name=""
push=0
load=0
tag_suffix=""
dry_run=0
platform_override=""
arch_suffix=""
tags_only=0

# Function to display usage information
usage() {
    echo "Usage: $0 -i <image_name> [-o <org_name>] [--push] [--load] [-t <tag_suffix>] [-p <platform>] [--dry] [--arch <arch>] [--tags-only]"
    echo "  -i: Image name (required)"
    echo "  -o: Organization name"
    echo "  --push: Push the image"
    echo "  --load: Load the image"
    echo "  -t: Tag suffix"
    echo "  -p: Platform(s) to build for (e.g. linux/amd64 or linux/amd64,linux/arm64)"
    echo "  --dry: Don't build, only create build-args.json"
    echo "  --arch: Architecture suffix (e.g. amd64 or arm64). Appends -<arch> to tags and forces single-platform build"
    echo "  --tags-only: Print final (non-arch-suffixed) fully-qualified tags and exit"
    exit 1
}

# Parse command-line options
while [[ $# -gt 0 ]]; do
    case $1 in
        -i) image_name="$2"; shift 2 ;;
        -o) org_name="$2"; shift 2 ;;
        --push) push=1; shift ;;
        --load) load=1; shift ;;
        -t) tag_suffix="$2"; shift 2 ;;
        -p) platform_override="$2"; shift 2 ;;
        --dry) dry_run=1; shift ;;
        --arch) arch_suffix="$2"; shift 2 ;;
        --tags-only) tags_only=1; shift ;;
        *) usage ;;
    esac
done
# Check if required arguments are provided
if [[ -z "$image_name" ]]; then
    echo "Error: Image name is required."
    usage
fi

# When --tags-only is set, redirect informational output to stderr so only tags go to stdout
if [[ $tags_only -eq 1 ]]; then
  log() { echo "$@" >&2; }
else
  log() { echo "$@"; }
fi

log "Building: $image_name"
tags=()

OPENHANDS_BUILD_VERSION="dev"

cache_tag_base="buildcache"
cache_tag="$cache_tag_base"

if [[ -n $RELEVANT_SHA ]]; then
  git_hash=$(git rev-parse --short "$RELEVANT_SHA")
  tags+=("$git_hash")
  tags+=("$RELEVANT_SHA")
fi

if [[ -n $GITHUB_REF_NAME ]]; then
  # check if ref name is a version number
  if [[ $GITHUB_REF_NAME =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    major_version=$(echo "$GITHUB_REF_NAME" | cut -d. -f1)
    minor_version=$(echo "$GITHUB_REF_NAME" | cut -d. -f1,2)
    tags+=("$major_version" "$minor_version")
    tags+=("latest")
  fi
  sanitized_ref_name=$(echo "$GITHUB_REF_NAME" | sed 's/[^a-zA-Z0-9.-]\+/-/g')
  OPENHANDS_BUILD_VERSION=$sanitized_ref_name
  sanitized_ref_name=$(echo "$sanitized_ref_name" | tr '[:upper:]' '[:lower:]') # lower case is required in tagging
  tags+=("$sanitized_ref_name")
  cache_tag+="-${sanitized_ref_name}"
fi

if [[ -n $tag_suffix ]]; then
  cache_tag+="-${tag_suffix}"
  for i in "${!tags[@]}"; do
    tags[$i]="${tags[$i]}-$tag_suffix"
  done
fi

log "Tags (before arch suffix): ${tags[@]}"

if [[ "$image_name" == "openhands" ]]; then
  dir="./containers/app"
elif [[ "$image_name" == "runtime" ]]; then
  dir="./containers/runtime"
else
  dir="./containers/$image_name"
fi

if [[ (! -f "$dir/Dockerfile") && "$image_name" != "runtime" ]]; then
  # Allow runtime to be built without a Dockerfile
  echo "No Dockerfile found"
  exit 1
fi
if [[ ! -f "$dir/config.sh" ]]; then
  echo "No config.sh found for Dockerfile"
  exit 1
fi

source "$dir/config.sh"

if [[ -n "$org_name" ]]; then
  DOCKER_ORG="$org_name"
fi

# If $DOCKER_IMAGE_SOURCE_TAG is set, add it to the tags
if [[ -n "$DOCKER_IMAGE_SOURCE_TAG" ]]; then
  tags+=("$DOCKER_IMAGE_SOURCE_TAG")
fi
# If $DOCKER_IMAGE_TAG is set, add it to the tags
if [[ -n "$DOCKER_IMAGE_TAG" ]]; then
  tags+=("$DOCKER_IMAGE_TAG")
fi

# Apply architecture suffix for split-arch builds (after all tags are collected)
if [[ -n "$arch_suffix" ]]; then
  cache_tag+="-${arch_suffix}"
  for i in "${!tags[@]}"; do
    tags[$i]="${tags[$i]}-${arch_suffix}"
  done
  # Force single-platform build for this architecture
  platform_override="linux/${arch_suffix}"
fi

DOCKER_REPOSITORY="$DOCKER_REGISTRY/$DOCKER_ORG/$DOCKER_IMAGE"
DOCKER_REPOSITORY=${DOCKER_REPOSITORY,,} # lowercase
log "Repo: $DOCKER_REPOSITORY"
log "Base dir: $DOCKER_BASE_DIR"
log "Tags: ${tags[@]}"

args=""
full_tags=()
for tag in "${tags[@]}"; do
  args+=" -t $DOCKER_REPOSITORY:$tag"
  full_tags+=("$DOCKER_REPOSITORY:$tag")
done

# --tags-only: print final fully-qualified tags (without arch suffix) and exit
if [[ $tags_only -eq 1 ]]; then
  for ftag in "${full_tags[@]}"; do
    if [[ -n "$arch_suffix" ]]; then
      echo "${ftag%-${arch_suffix}}"
    else
      echo "$ftag"
    fi
  done
  exit 0
fi

if [[ $push -eq 1 ]]; then
  args+=" --push"
  args+=" --cache-to=type=registry,ref=$DOCKER_REPOSITORY:$cache_tag,mode=max"
fi

if [[ $load -eq 1 ]]; then
  args+=" --load"
fi

echo "Args: $args"

# Determine the platform(s) to build for
if [[ -n "$platform_override" ]]; then
  platform="$platform_override"
elif [[ $load -eq 1 ]]; then
  # When loading, build only for the current platform
  platform=$(docker version -f '{{.Server.Os}}/{{.Server.Arch}}')
else
  # For push or without load, build for multiple platforms
  platform="linux/amd64,linux/arm64"
fi
if [[ $dry_run -eq 1 ]]; then
  echo "Dry Run is enabled. Writing build config to docker-build-dry.json"
  jq -n \
    --argjson tags "$(printf '%s\n' "${full_tags[@]}" | jq -R . | jq -s .)" \
    --arg platform "$platform" \
    --arg openhands_build_version "$OPENHANDS_BUILD_VERSION" \
    --arg dockerfile "$dir/Dockerfile" \
    '{
      tags: $tags,
      platform: $platform,
      build_args: [
        "OPENHANDS_BUILD_VERSION=" + $openhands_build_version
      ],
      dockerfile: $dockerfile
    }' > docker-build-dry.json

    exit 0
fi



echo "Building for platform(s): $platform"

docker buildx build \
  $args \
  --build-arg OPENHANDS_BUILD_VERSION="$OPENHANDS_BUILD_VERSION" \
  --cache-from=type=registry,ref=$DOCKER_REPOSITORY:$cache_tag \
  --cache-from=type=registry,ref=$DOCKER_REPOSITORY:${cache_tag_base}-main${arch_suffix:+-${arch_suffix}} \
  --platform $platform \
  --provenance=false \
  -f "$dir/Dockerfile" \
  "$DOCKER_BASE_DIR"

# If load was requested, print the loaded images
if [[ $load -eq 1 ]]; then
  echo "Local images built:"
  docker images "$DOCKER_REPOSITORY" --format "{{.Repository}}:{{.Tag}}"
fi
