# Push to GitHub Repository — dev_mtext Branch

This guide walks you through pushing the code to the existing repository:
`https://github.com/Aravind5100/AutoCAD-Automation.git`

---

## Prerequisites

1. **Git installed** — Download from https://git-scm.com/download/win if not already installed
2. **GitHub credentials** — Your username and personal access token (or SSH key)

---

## Step 1: Install Git (if needed)

1. Visit https://git-scm.com/download/win
2. Download the Windows installer
3. Run the installer with default settings
4. **Restart PowerShell/Command Prompt**

Verify:
```powershell
git --version
```

---

## Step 2: Configure Git (First Time Only)

```powershell
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

---

## Step 3: Initialize Repository and Push to dev_mtext Branch

Navigate to your project directory and run these commands in order:

```powershell
cd "c:\Users\akompal\AutoCAD Automation"

# Initialize git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: AutoCAD Room Annotation Tool with polygon linkage and XData metadata"

# Add remote origin pointing to the existing repository
git remote add origin https://github.com/Aravind5100/AutoCAD-Automation.git

# Create and checkout the dev_mtext branch
git checkout -b dev_mtext

# Push to the dev_mtext branch
git push -u origin dev_mtext
```

---

## Step 4: Authentication

When prompted for credentials:

**Option A: Personal Access Token (Recommended)**
- Go to https://github.com/settings/tokens
- Click **Generate new token**
- Select scopes: `repo` (full control of repositories)
- Click **Generate token**
- Copy the token
- When Git prompts for password, paste the token

**Option B: SSH Key (Advanced)**
- Generate SSH key: `ssh-keygen -t ed25519 -C "your.email@example.com"`
- Add to GitHub: https://github.com/settings/keys
- Use SSH URL: `git@github.com:Aravind5100/AutoCAD-Automation.git`

---

## Step 5: Verify Push

Visit the repository in your browser:
https://github.com/Aravind5100/AutoCAD-Automation

You should see:
- A new branch `dev_mtext` in the branch dropdown
- All your files on that branch

---

## If Repository Already Has Content

If the repository already has commits, you may need to pull first:

```powershell
git pull origin dev_mtext --allow-unrelated-histories
git push -u origin dev_mtext
```

---

## Future Updates

After making changes locally:

```powershell
git add .
git commit -m "Description of changes"
git push
```

---

## Troubleshooting

### "fatal: not a git repository"
Make sure you're in the correct directory:
```powershell
cd "c:\Users\akompal\AutoCAD Automation"
git init
```

### "fatal: Authentication failed"
- Verify your GitHub username is correct
- Use a personal access token instead of your password
- Generate a new token if the old one expired

### "fatal: remote origin already exists"
```powershell
git remote remove origin
git remote add origin https://github.com/Aravind5100/AutoCAD-Automation.git
```

### "fatal: The current branch dev_mtext has no upstream branch"
```powershell
git push -u origin dev_mtext
```

### "fatal: refusing to merge unrelated histories"
```powershell
git pull origin dev_mtext --allow-unrelated-histories
git push -u origin dev_mtext
```

---

## What Gets Pushed

✅ All source code (10 Python modules)
✅ Documentation (README.md, DOCUMENTATION.md, GITHUB_SETUP.md)
✅ Configuration (requirements.txt, config.py)
✅ Git configuration (.gitignore, .gitattributes)

❌ Excluded (in .gitignore):
- Virtual environment (.venv/)
- Python cache (__pycache__)
- AutoCAD files (*.dwg, *.bak)
- Test/debug scripts

---

## Quick Reference

```powershell
# One-liner to initialize and push (if starting fresh)
cd "c:\Users\akompal\AutoCAD Automation" && git init && git add . && git commit -m "Initial commit: AutoCAD Room Annotation Tool with polygon linkage and XData metadata" && git remote add origin https://github.com/Aravind5100/AutoCAD-Automation.git && git checkout -b dev_mtext && git push -u origin dev_mtext
```

---

## Next Steps

1. **Create a Pull Request** (optional):
   - Go to the repository on GitHub
   - Click **Pull requests** → **New pull request**
   - Compare `dev_mtext` to `main`
   - Add description and create PR

2. **Merge to main** (when ready):
   - Review the PR
   - Click **Merge pull request**
   - Delete the `dev_mtext` branch (optional)

3. **Create a Release** (when stable):
   ```powershell
   git tag v1.0.0
   git push origin v1.0.0
   ```

---

## Questions?

- GitHub Help: https://docs.github.com
- Git Documentation: https://git-scm.com/doc
- Personal Access Token: https://github.com/settings/tokens
