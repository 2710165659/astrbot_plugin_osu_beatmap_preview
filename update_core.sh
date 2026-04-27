#!/usr/bin/env bash

set -euo pipefail

# 手动更新内置 core。
# 同步上游仓库里的 osu-beatmap-preview 子目录
REPO_URL="https://github.com/2710165659/osu-agent-skills.git"
BRANCH="${1:-main}"
TARGET_DIR="osu-beatmap-preview"
TMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "${TMP_DIR}"
}

trap cleanup EXIT

echo "Cloning ${REPO_URL} (${BRANCH}) ..."
git clone --depth 1 --branch "${BRANCH}" --filter=blob:none --sparse "${REPO_URL}" "${TMP_DIR}"

echo "Fetching ${TARGET_DIR} ..."
git -C "${TMP_DIR}" sparse-checkout set "${TARGET_DIR}"

echo "Replacing local ${TARGET_DIR} ..."
rm -rf "${TARGET_DIR}"
cp -R "${TMP_DIR}/${TARGET_DIR}" "${TARGET_DIR}"

echo "Core updated: ${TARGET_DIR}"
