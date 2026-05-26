---
name: git-leak-cleanup
description: Use when a secret, credential, API key, password, or sensitive file has been committed to git history and needs to be fully removed — including rewriting history, rotating the credential, and force-pushing safely.
metadata:
  type: technique
---

# Git Leak Cleanup

## Overview

A committed secret is not safe until the credential is rotated **and** the history is rewritten. Neither step alone is sufficient. This skill covers the full remediation sequence.

## When to Use

- An API key, password, `.env`, or private key appears in `git log`
- A file containing credentials was committed (even if later deleted via a normal commit)
- You need to remove a large binary or sensitive file from all historical references

Do NOT use for removing untracked files — use `.gitignore` + `git clean` instead.

---

## Step 0 — Rotate First

**Before touching history**, rotate/revoke the exposed credential. History rewrite takes time; the window between "secret is live" and "history is clean" is a risk window.

1. Revoke the old key in the relevant service (Anthropic console, AWS IAM, GitHub tokens, etc.)
2. Generate a new key
3. Update your secrets store / `.env` (outside the repo working directory)

---

## Step 1 — Install git-filter-repo

```bash
pip install git-filter-repo   # or: brew install git-filter-repo
```

Prefer `git-filter-repo` over `git filter-branch` — it is faster, safer, and actively maintained.

---

## Step 2 — Remove a File from All History

```bash
# Remove a specific file path from every commit
git filter-repo --path <path/to/secret-file> --invert-paths

# Example: remove .env from all commits
git filter-repo --path .env --invert-paths
```

To remove a file that lived under multiple names or locations:

```bash
git filter-repo --path-glob '**/.env' --invert-paths
git filter-repo --path-regex '.*secret.*' --invert-paths
```

---

## Step 3 — Remove a String from File Contents

If the secret is embedded inside a file that should otherwise be kept:

```bash
git filter-repo --replace-text <(echo "ACTUAL_SECRET_VALUE==>REDACTED")
```

For multiple strings, create a replacements file:

```
# replacements.txt
sk-ant-XXXX==>REDACTED_API_KEY
ghp_XXXX==>REDACTED_GH_TOKEN
```

```bash
git filter-repo --replace-text replacements.txt
```

---

## Step 4 — Verify the Secret Is Gone

```bash
# Search all commits for the string
git log --all --full-history -- '*.env'
git grep -i 'ACTUAL_SECRET_VALUE' $(git rev-list --all)
```

Both commands should return no output.

---

## Step 5 — Add to .gitignore

```bash
echo ".env" >> .gitignore
echo "*.pem" >> .gitignore
git add .gitignore && git commit -m "chore: add secret patterns to .gitignore"
```

Move sensitive files to a location **outside** the git working directory (e.g., `~/.secrets/projectname/`) and reference them via absolute path in your shell profile.

---

## Step 6 — Force-Push (Coordinated)

`git filter-repo` rewrites history, so a force-push is required. Coordinate with teammates first:

```bash
# Confirm remote state before pushing
git fetch origin

# Push rewritten history (all branches)
git push origin --force --all
git push origin --force --tags
```

**Tell collaborators:** they must `git fetch` and then reset their local branches:

```bash
git fetch origin
git checkout main
git reset --hard origin/main
```

Any local branches that haven't been pushed yet need the same treatment. Stashed changes or local commits on top of the old history will need to be rebased onto the new history.

---

## Step 7 — Request Cache Purge (GitHub / GitLab)

GitHub caches repository data. After the force-push:

- GitHub: contact support to purge cached views of the exposed commits
- GitLab: use the Repository → Housekeeping → Prune unreachable objects option
- Self-hosted: run `git gc --aggressive --prune=now` on the server

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| Deleting the file in a new commit without rewriting history | History still contains the secret. Use `filter-repo`. |
| Rewriting history before rotating the credential | The window between history clean and credential rotated is still a live exposure. Rotate first. |
| Only removing from `main` branch | Use `--all` to cover all branches and tags. |
| Forgetting forks and CI caches | Notify fork owners; rotate the credential rather than trusting cache expiry. |
| Using `git filter-branch` | Use `git-filter-repo` — filter-branch is deprecated and has known correctness issues. |

---

## Prevention

- Store secrets in environment variables loaded from files outside the repo (`~/.secrets/`, system keychain, vault)
- Add a pre-commit hook: `pip install detect-secrets && detect-secrets scan --update .secrets.baseline`
- Use `.gitignore` templates for common secret file patterns before the first commit
- See the companion `pre-push-checklist` skill for lightweight pre-push scanning
