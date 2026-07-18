#!/usr/bin/env bash
# Chạy TRÊN VPS qua `ssh ... 'bash -s' < deploy/remote_deploy.sh` từ GitHub Actions.
# Nguyên tắc: không bao giờ down stack cũ trước khi bản mới build xong & healthy —
# build fail => stack cũ nguyên vẹn; `up --wait` fail => job đỏ, container cũ đã bị
# thay chỉ ở service hỏng, các service còn lại giữ nguyên.
set -euo pipefail

REPO_URL="https://github.com/ForwardInfinity/vietnam-ai-hackathon.git"
APP_DIR="/opt/app"

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ ! -d .git ]; then
  git init -q
fi
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
git fetch -q origin master
git reset --hard -q origin/master

# .env: POSTGRES_PASSWORD sinh một lần rồi giữ nguyên (volume pgdata giữ password cũ);
# API keys làm mới mỗi deploy từ GitHub secrets (scp lên .env.secrets trước khi chạy script).
touch .env
chmod 600 .env
if ! grep -q '^POSTGRES_PASSWORD=' .env; then
  echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env
fi
if [ -f .env.secrets ]; then
  grep -vE '^(OPENROUTER_API_KEY|DEEPSEEK_API_KEY)=' .env > .env.new || true
  cat .env.secrets >> .env.new
  chmod 600 .env.new
  mv .env.new .env
  rm -f .env.secrets
fi

docker compose build --pull
docker compose up -d --wait --remove-orphans

echo "deploy OK: $(git rev-parse --short HEAD)"
