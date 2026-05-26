---
name: pre-push-checklist
description: Use before pushing a branch — especially to a shared remote — to catch secrets, large files, sensitive paths, and other common mistakes before they become permanent history.
metadata:
  type: reference
---

# Pre-Push Checklist

Run through this before `git push`, especially for a first push of a branch or before opening a PR.

---

## 1 — Secrets Scan

```bash
# Quick grep for common secret patterns in staged/changed files
git diff origin/main...HEAD | grep -iE '(api[_-]?key|secret|password|token|private[_-]?key|BEGIN RSA|BEGIN EC|sk-ant|ghp_|glpat-)' | grep '^+' | grep -v '^+++'

# Full history scan with detect-secrets (if installed)
detect-secrets scan --list-all-files
```

If any match: stop, rotate the credential, then follow the `git-leak-cleanup` skill.

---

## 2 — Large File Check

```bash
# Find files over 1 MB added in this branch
git diff --stat origin/main...HEAD | awk '{print $1, $3}' | sort -rn | head -20

# Or: find objects > 500KB in the staging area
git ls-files -z | xargs -0 du -k | sort -rn | head -20
```

Large binaries committed to git inflate clone times permanently. Move them to object storage or a `.gitignore`d location.

---

## 3 — Sensitive Paths

```bash
# Check for files that should never be committed
git diff --name-only origin/main...HEAD | grep -iE '\.(env|pem|key|p12|pfx|jks|keystore|secret)$|^\.env|credentials|id_rsa|id_ed25519'
```

Expected output: nothing. If any path appears, remove it with `git rm --cached <path>` and add to `.gitignore`.

---

## 4 — .gitignore Coverage

```bash
# List untracked files that are NOT ignored — potential accidental additions
git status --porcelain | grep '^??'
```

Review each `??` file. If it should never be committed, add it to `.gitignore` now.

---

## 5 — Commit Message Hygiene

```bash
# Review commits that will be pushed
git log origin/main...HEAD --oneline
```

Check: no WIP commits, no "fixup!" commits, no commit messages that embed secrets or internal URLs.

---

## 6 — Force-Push Gate

```bash
# Confirm whether a force-push would be needed
git status -sb
```

If the branch has diverged from remote, understand why before force-pushing. Force-pushing shared branches (`main`, `dev`, release branches) requires team coordination — see the `git-leak-cleanup` skill for the full force-push protocol.

---

## Quick One-Liner (all checks combined)

```bash
git diff origin/main...HEAD | grep -iE '(api[_-]?key|secret|password|token|sk-ant|ghp_)' | grep '^+' | grep -v '^+++' && \
git diff --name-only origin/main...HEAD | grep -iE '\.(env|pem|key|p12)$|^\.env' && \
echo "Issues found above — do not push" || echo "Clean — safe to push"
```

---

## If a Secret Is Found

Do not push. Follow the `git-leak-cleanup` skill:
1. Rotate the credential immediately
2. Rewrite history with `git filter-repo`
3. Force-push with coordination
