#!/usr/bin/env bash
# Lưu tài liệu của từng lô pipeline PDF vào Release <tag-base>-s<i> (D-011, D-030, D-033).
#
# Cách dùng: archive-releases.sh <thư mục chứa work-*> <tag-base> <target>
# Cần GH_TOKEN và REPO. Chạy lại được: Release đã có thì chỉ tải phần còn thiếu.
#
# Tài liệu học khu được gói thành một tệp docs.tar mỗi lô, không tải từng tệp: một lượt toàn quốc
# có khoảng 6.000 tài liệu, vượt giới hạn tải lên mỗi giờ của GITHUB_TOKEN. Tên tài liệu trong D1
# (asset_name) là tên tệp bên trong docs.tar. Các tệp báo cáo vẫn tải riêng.
set -euo pipefail
work="$1"; base="$2"; target="$3"
meta_names=(manifest.json report.md work.json extractions.json)

for dir in "$work"/work-*; do
  [ -f "$dir/pipeline.sql" ] || continue
  shard="${dir##*-}"
  tag="$base-s$shard"
  if gh release view "$tag" --repo "$REPO" > /dev/null 2>&1; then
    have=$(gh release view "$tag" --repo "$REPO" --json assets --jq '.assets[].name')
  else
    gh release create "$tag" --repo "$REPO" --title "$tag" --prerelease \
      --notes "Tài liệu học khu (docs.tar) và báo cáo của pipeline PDF (${target}), lô $shard."
    have=""
  fi

  uploads=()
  missing_doc=0
  for f in "$dir"/docs/*; do
    name=$(basename "$f")
    if printf '%s\n' "${meta_names[@]}" | grep -qxF "$name"; then
      grep -qxF "$name" <<< "$have" || uploads+=("$f")
    elif ! grep -qxF "$name" <<< "$have"; then
      missing_doc=1
    fi
  done
  if [ "$missing_doc" = 1 ] && ! grep -qxF docs.tar <<< "$have"; then
    bundle="$RUNNER_TEMP/docs-$shard/docs.tar"
    mkdir -p "$(dirname "$bundle")"
    find "$dir/docs" -maxdepth 1 -type f \
      ! -name manifest.json ! -name report.md ! -name work.json ! -name extractions.json \
      -printf '%f\n' | sort | tar -cf "$bundle" -C "$dir/docs" -T -
    uploads+=("$bundle")
  fi
  if [ "${#uploads[@]}" -gt 0 ]; then
    gh release upload "$tag" "${uploads[@]}" --repo "$REPO"
  fi
  echo "Release: $tag (tải thêm ${#uploads[@]} tệp)" >> "${GITHUB_STEP_SUMMARY:-/dev/stdout}"
done
