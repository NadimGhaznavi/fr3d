#!/usr/bin/env bash
# Create and publish a Fr3d release.
#
# Flow: feat/* -> dev -> main, tag main, synchronize dev, then create the next
# feature branch. The annotated tag is the authoritative project version.

set -Eeuo pipefail

readonly REMOTE="origin"
readonly MAIN_BRANCH="main"
readonly DEV_BRANCH="dev"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly CHANGELOG="${PROJECT_DIR}/CHANGELOG.md"
readonly CONSTANTS_FILE="${PROJECT_DIR}/constants/DFr3d.py"

CURRENT_BRANCH=""
NEW_VERSION=""
RELEASE_DESCRIPTION=""
RELEASE_MESSAGE=""
NEXT_FEATURE_BRANCH=""
TAG_NAME=""

info() { printf '[INFO] %s\n' "$*"; }
success() { printf '[SUCCESS] %s\n' "$*"; }
warn() { printf '[WARNING] %s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

usage() {
    local current_version=""
    local likely_version="0.1.0"
    local likely_feature_version="0.1.1"

    if [[ -f "${CONSTANTS_FILE}" ]]; then
        current_version=$(sed -nE 's/^    VERSION: Final\[str\] = "([^"]+)"$/\1/p' "${CONSTANTS_FILE}")
    fi
    if [[ "${current_version}" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
        local major=${BASH_REMATCH[1]}
        local minor=${BASH_REMATCH[2]}
        local release_patch=$((10#${BASH_REMATCH[3]} + 1))
        likely_version="${major}.${minor}.${release_patch}"
        likely_feature_version="${major}.${minor}.$((release_patch + 1))"
    fi

    cat <<EOF
Usage: $(basename -- "$0") <version> <message> <next-feature-branch>

Likely next version: ${likely_version}

Example:
  $(basename -- "$0") ${likely_version} "Maintenance release" feat/maint-${likely_feature_version}

Run this from a clean feat/* or feature/* branch. The script updates the
changelog, merges the feature through dev to main, creates an annotated vX.Y.Z
tag, pushes the release atomically, and creates the next local feature branch.
EOF
}

ref_exists() {
    git show-ref --verify --quiet "$1"
}

validate_arguments() {
    [[ $# -eq 3 ]] || { usage >&2; exit 2; }

    NEW_VERSION=$1
    RELEASE_DESCRIPTION=$2
    RELEASE_MESSAGE="Release ${NEW_VERSION}: ${RELEASE_DESCRIPTION}"
    NEXT_FEATURE_BRANCH=$3
    TAG_NAME="v${NEW_VERSION}"

    [[ "${NEW_VERSION}" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z][0-9A-Za-z.-]*)?(\+[0-9A-Za-z][0-9A-Za-z.-]*)?$ ]] ||
        die "Version must be a semantic version without a leading v."
    [[ -n "${RELEASE_DESCRIPTION}" ]] || die "Release message must not be empty."
    [[ "${NEXT_FEATURE_BRANCH}" == feat/* || "${NEXT_FEATURE_BRANCH}" == feature/* ]] ||
        die "Next feature branch must start with feat/ or feature/."
    git check-ref-format --branch "${NEXT_FEATURE_BRANCH}" >/dev/null ||
        die "Invalid feature branch name: ${NEXT_FEATURE_BRANCH}"
}

preflight() {
    command -v git >/dev/null 2>&1 || die "Required command not found: git"
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
        die "Not inside a Git repository."
    [[ "$(git rev-parse --show-toplevel)" == "${PROJECT_DIR}" ]] ||
        die "Run this script from the Fr3d repository."
    git remote get-url "${REMOTE}" >/dev/null 2>&1 ||
        die "Git remote '${REMOTE}' is not configured."

    CURRENT_BRANCH=$(git branch --show-current)
    [[ "${CURRENT_BRANCH}" == feat/* || "${CURRENT_BRANCH}" == feature/* ]] ||
        die "Run this from a feature branch (currently '${CURRENT_BRANCH:-detached HEAD}')."
    [[ -z "$(git status --porcelain)" ]] || {
        git status --short >&2
        die "Working tree is not clean; commit or stash changes first."
    }

    [[ -f "${CHANGELOG}" ]] || die "CHANGELOG.md is required."
    grep -Fxq '## [Unreleased]' "${CHANGELOG}" ||
        die "CHANGELOG.md must contain an '## [Unreleased]' heading."
    [[ -f "${CONSTANTS_FILE}" ]] || die "constants/DFr3d.py is required."
    grep -Eq '^    VERSION: Final\[str\] = "[^"]+"$' "${CONSTANTS_FILE}" ||
        die "DFr3d.VERSION is missing or malformed."
    ref_exists "refs/heads/${MAIN_BRANCH}" || die "Local branch '${MAIN_BRANCH}' is missing."
    ref_exists "refs/heads/${DEV_BRANCH}" || die "Local branch '${DEV_BRANCH}' is missing."

    info "Fetching refs from ${REMOTE}..."
    git fetch --prune --tags "${REMOTE}"

    ref_exists "refs/remotes/${REMOTE}/${MAIN_BRANCH}" ||
        die "Remote branch '${REMOTE}/${MAIN_BRANCH}' is missing."
    [[ "$(git rev-parse "${MAIN_BRANCH}")" == "$(git rev-parse "${REMOTE}/${MAIN_BRANCH}")" ]] ||
        die "Local and remote '${MAIN_BRANCH}' differ; reconcile them first."

    if ref_exists "refs/remotes/${REMOTE}/${DEV_BRANCH}"; then
        [[ "$(git rev-parse "${DEV_BRANCH}")" == "$(git rev-parse "${REMOTE}/${DEV_BRANCH}")" ]] ||
            die "Local and remote '${DEV_BRANCH}' differ; reconcile them first."
    else
        warn "Remote '${REMOTE}/${DEV_BRANCH}' is absent and will be created."
    fi

    git merge-base --is-ancestor "${MAIN_BRANCH}" "${DEV_BRANCH}" ||
        die "'${DEV_BRANCH}' does not contain '${MAIN_BRANCH}'."
    ! ref_exists "refs/tags/${TAG_NAME}" || die "Tag '${TAG_NAME}' already exists."
    ! ref_exists "refs/heads/${NEXT_FEATURE_BRANCH}" ||
        die "Local branch '${NEXT_FEATURE_BRANCH}' already exists."
    ! ref_exists "refs/remotes/${REMOTE}/${NEXT_FEATURE_BRANCH}" ||
        die "Remote branch '${REMOTE}/${NEXT_FEATURE_BRANCH}' already exists."
}

confirm_release() {
    printf '\nRelease summary:\n'
    printf '  Source:       %s\n' "${CURRENT_BRANCH}"
    printf '  Tag:          %s\n' "${TAG_NAME}"
    printf '  Message:      %s\n' "${RELEASE_MESSAGE}"
    printf '  Next branch:  %s\n' "${NEXT_FEATURE_BRANCH}"
    printf '  Remote:       %s\n\n' "$(git remote get-url "${REMOTE}")"

    [[ -t 0 ]] || die "Confirmation requires an interactive terminal."
    read -r -p "Create and push this release? [y/N] " reply
    [[ "${reply}" == y || "${reply}" == Y ]] || {
        warn "Release cancelled."
        exit 0
    }
}

update_changelog() {
    local release_date temp_file
    release_date=$(date '+%Y-%m-%d @ %H:%M')
    temp_file=$(mktemp "${PROJECT_DIR}/.CHANGELOG.md.XXXXXX")

    awk -v heading="## [${NEW_VERSION}] - ${release_date}" '
        /^## \[Unreleased\]$/ {
            print
            print ""
            print heading
            next
        }
        { print }
    ' "${CHANGELOG}" >"${temp_file}" || {
        rm -f -- "${temp_file}"
        die "Failed to update CHANGELOG.md."
    }

    chmod --reference="${CHANGELOG}" "${temp_file}"
    mv -- "${temp_file}" "${CHANGELOG}"
    git add -- CHANGELOG.md
    git commit -m "Update changelog for ${TAG_NAME}"
}

update_project_version() {
    local temp_file
    temp_file=$(mktemp "${PROJECT_DIR}/constants/.DFr3d.py.XXXXXX")

    awk -v version="${NEW_VERSION}" '
        /^    VERSION: Final\[str\] = "[^"]+"$/ {
            print "    VERSION: Final[str] = \"" version "\""
            next
        }
        { print }
    ' "${CONSTANTS_FILE}" >"${temp_file}" || {
        rm -f -- "${temp_file}"
        die "Failed to update DFr3d.VERSION."
    }

    chmod --reference="${CONSTANTS_FILE}" "${temp_file}"
    mv -- "${temp_file}" "${CONSTANTS_FILE}"
    git add -- constants/DFr3d.py
}

merge_no_ff() {
    local source=$1 message=$2
    info "Merging '${source}' into '$(git branch --show-current)'..."
    git merge --no-ff "${source}" -m "${message}"
}

create_release() {
    git switch "${DEV_BRANCH}"
    merge_no_ff "${CURRENT_BRANCH}" "Merge ${CURRENT_BRANCH} for ${TAG_NAME}"
    update_project_version
    update_changelog

    git switch "${MAIN_BRANCH}"
    merge_no_ff "${DEV_BRANCH}" "${RELEASE_MESSAGE}"
    git tag -a "${TAG_NAME}" -m "${RELEASE_MESSAGE}"

    git switch "${DEV_BRANCH}"
    git merge --ff-only "${MAIN_BRANCH}"

    info "Pushing release refs atomically..."
    git push --atomic "${REMOTE}" \
        "refs/heads/${MAIN_BRANCH}:refs/heads/${MAIN_BRANCH}" \
        "refs/heads/${DEV_BRANCH}:refs/heads/${DEV_BRANCH}" \
        "refs/tags/${TAG_NAME}:refs/tags/${TAG_NAME}"

    git switch -c "${NEXT_FEATURE_BRANCH}"
}

main() {
    cd -- "${PROJECT_DIR}"
    if [[ ${1:-} == -h || ${1:-} == --help ]]; then
        usage
        exit 0
    fi
    validate_arguments "$@"
    preflight
    confirm_release
    create_release

    success "Release ${TAG_NAME} was published successfully."
    success "Now on new feature branch: ${NEXT_FEATURE_BRANCH}"
}

main "$@"
