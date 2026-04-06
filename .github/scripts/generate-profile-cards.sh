#!/usr/bin/env bash
set -euo pipefail

OWNER="${OWNER:-${GITHUB_REPOSITORY_OWNER:-}}"

if [[ -z "${OWNER}" ]]; then
  echo "OWNER (or GITHUB_REPOSITORY_OWNER) must be set"
  exit 1
fi

mkdir -p profile

fetch_svg() {
  local url="$1"
  local output="$2"

  curl --fail --silent --show-error --location \
    --retry 3 --retry-all-errors \
    "$url" -o "$output"

  if ! grep -q "<svg" "$output"; then
    echo "Card response for $output was not SVG"
    head -n 20 "$output" || true
    exit 1
  fi
}

fetch_svg \
  "https://github-readme-stats.vercel.app/api?username=${OWNER}&show_icons=true&include_all_commits=true&rank_icon=percentile&hide_border=true&theme=transparent&custom_title=GitHub%20Activity" \
  "profile/stats.svg"

fetch_svg \
  "https://github-readme-stats.vercel.app/api/top-langs/?username=${OWNER}&layout=compact&langs_count=8&hide=html,css&hide_border=true&theme=transparent&custom_title=Core%20Languages" \
  "profile/top-langs.svg"

# Intentionally fixed to zhittsova repos to support featured profile pins.
fetch_svg \
  "https://github-readme-stats.vercel.app/api/pin/?username=zhittsova&repo=agri-weather-yield-drivers&show_owner=false&hide_border=true&theme=transparent" \
  "profile/pin-agri-weather-yield-drivers.svg"

fetch_svg \
  "https://github-readme-stats.vercel.app/api/pin/?username=zhittsova&repo=bi-python-uv-project-scaffolder&show_owner=false&hide_border=true&theme=transparent" \
  "profile/pin-bi-python-uv-project-scaffolder.svg"
