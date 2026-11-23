#!/bin/sh
# Install compose on Linux or macOS.
#
#   ./install.sh                      # from this checkout
#   ./install.sh --source <path|git-url>
#   ./install.sh --yes                # don't ask before installing uv
#
# What it does: checks git, installs uv if it is missing (after asking), installs the
# `compose` command with `uv tool install`, then runs `compose check`. Claude Code itself
# is optional: compose uses the `claude` on your PATH, or the one bundled with the
# Claude Agent SDK that this installs.
set -eu

PYTHON_VERSION="3.12"
SOURCE=""
ASSUME_YES=0

say() { printf '%s\n' "$*"; }
fail() { printf 'install: %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --source) [ $# -ge 2 ] || fail "--source needs a path or git URL"; SOURCE="$2"; shift 2 ;;
        --source=*) SOURCE="${1#--source=}"; shift ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option: $1 (see --help)" ;;
    esac
done

case "$(uname -s)" in
    Linux|Darwin) ;;
    *) fail "this script is for Linux and macOS; on Windows use install.ps1" ;;
esac

if [ -z "$SOURCE" ]; then
    SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    [ -f "$SOURCE/pyproject.toml" ] || fail "run this from a compose checkout, or pass --source"
fi
case "$SOURCE" in
    http://*|https://*|ssh://*|git@*) TARGET="git+$SOURCE" ;;
    git+*) TARGET="$SOURCE" ;;
    *) [ -f "$SOURCE/pyproject.toml" ] || fail "$SOURCE is not a compose checkout"; TARGET="$SOURCE" ;;
esac

command -v git >/dev/null 2>&1 || fail "git is required: install it (e.g. 'xcode-select --install' on macOS, your package manager on Linux) and run this again"

if ! command -v uv >/dev/null 2>&1; then
    for dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        [ -x "$dir/uv" ] && PATH="$dir:$PATH"
    done
fi
if ! command -v uv >/dev/null 2>&1; then
    say "uv is not installed. It installs compose and the Python it needs."
    say "It would be installed with the official installer: https://astral.sh/uv/install.sh"
    if [ "$ASSUME_YES" -ne 1 ]; then
        printf 'Install uv now? [y/N] '
        read -r answer </dev/tty || answer=""
        case "$answer" in y|Y|yes|YES) ;; *) fail "uv is required: see https://docs.astral.sh/uv/" ;; esac
    fi
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        fail "curl or wget is needed to install uv"
    fi
    PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on PATH; open a new shell and run this again"
fi

say "Installing compose from $TARGET ..."
uv tool install --force --reinstall --python "$PYTHON_VERSION" "$TARGET"

BIN_DIR=$(uv tool dir --bin)
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        PATH="$BIN_DIR:$PATH"
        say ""
        say "$BIN_DIR is not on your PATH. Add it with:  uv tool update-shell"
        ;;
esac

say ""
# from $HOME, so only the prerequisites are checked, not the current repository
if (cd "$HOME" && compose check); then
    say ""
    say "compose is ready. In a repository: compose init --engine claude"
else
    say ""
    say "compose is installed, but 'compose check' found something to fix (see above)."
    if ! command -v claude >/dev/null 2>&1; then
        say "To install Claude Code: https://docs.claude.com/en/docs/claude-code/setup"
    fi
fi
