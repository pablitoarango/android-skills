#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Usage: ./install.sh [--uninstall]

Symlinks every skill in this repo into ~/.claude/skills and ~/.agents/skills.
Symlinks that point into this repo but no longer match a skill (renamed or
deleted skills) are removed. Existing folders, and symlinks with the same name
that point somewhere else, are left untouched and reported.

  --uninstall   Remove every symlink that points into this repo and exit
EOF
}

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
targets=("$HOME/.claude/skills" "$HOME/.agents/skills")
uninstall=false

case "${1:-}" in
  "") ;;
  --uninstall) uninstall=true ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 1 ;;
esac

for target in "${targets[@]}"; do
  mkdir -p "$target"

  for link in "$target"/*; do
    [ -L "$link" ] || continue
    case "$(readlink "$link")" in
      "$repo"/*) rm "$link" ;;
    esac
  done

  if [ "$uninstall" = true ]; then
    echo "Removed android-skills links from $target"
    continue
  fi

  count=0
  for skill_md in "$repo"/*/*/SKILL.md; do
    skill_dir="$(dirname "$skill_md")"
    name="$(basename "$skill_dir")"
    if [ -L "$target/$name" ]; then
      echo "Skipped $target/$name: already links to $(readlink "$target/$name")"
      continue
    fi
    if [ -e "$target/$name" ]; then
      echo "Skipped $target/$name: a folder that is not a symlink already exists"
      continue
    fi
    ln -s "$skill_dir" "$target/$name"
    count=$((count + 1))
  done
  echo "Linked $count skills into $target"
done
