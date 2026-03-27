# GitHub Setup Guide

This guide walks you through pushing the AutoCAD Room Annotation Tool to GitHub.

## Prerequisites

1. **Git installed** — Download from https://git-scm.com/download/win
2. **GitHub account** — Create one at https://github.com if you don't have one
3. **GitHub CLI or SSH key** (optional but recommended for authentication)

---

## Step 1: Install Git

1. Visit https://git-scm.com/download/win
2. Download the Windows installer
3. Run the installer with default settings
4. Restart your terminal/PowerShell

Verify installation:
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

## Step 3: Create a Repository on GitHub

1. Go to https://github.com/new
2. **Repository name:** `autocad-room-annotation`
3. **Description:** "Production-style Python tool for annotating AutoCAD drawings with spreadsheet data and room polygon linkage"
4. **Visibility:** Public (recommended for open-source) or Private
5. **Initialize with:** Leave unchecked (we'll push existing code)
6. Click **Create repository**

You'll see a page with commands. Copy the HTTPS or SSH URL (we'll use it next).

---

## Step 4: Initialize Local Repository

Navigate to the project directory and run:

```powershell
cd "c:\Users\akompal\AutoCAD Automation"
git init
git add .
git commit -m "Initial commit: AutoCAD Room Annotation Tool with polygon linkage"
```

---

## Step 5: Connect to GitHub and Push

Replace `YOUR_USERNAME` and `YOUR_REPO_NAME` with your actual GitHub username and repository name:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/autocad-room-annotation.git
git branch -M main
git push -u origin main
```

When prompted, enter your GitHub credentials:
- **Username:** Your GitHub username
- **Password:** Your GitHub personal access token (not your password)

### Creating a Personal Access Token

If you don't have a token:
1. Go to https://github.com/settings/tokens
2. Click **Generate new token**
3. Select scopes: `repo` (full control of private repositories)
4. Click **Generate token**
5. Copy the token and use it as your password when pushing

---

## Step 6: Verify Push

Visit `https://github.com/YOUR_USERNAME/autocad-room-annotation` in your browser.
You should see all your files uploaded.

---

## Step 7: Add a License (Recommended)

1. In your GitHub repository, click **Add file** → **Create new file**
2. Name it `LICENSE`
3. Choose a license template (MIT is recommended for open-source)
4. Commit the file

Or locally:

```powershell
# Create LICENSE file with MIT license text
# Then:
git add LICENSE
git commit -m "Add MIT license"
git push
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
Run `git init` in the project directory first.

### "fatal: Authentication failed"
- Check your GitHub username is correct
- Use a personal access token instead of your password
- Generate a new token if the old one expired

### "fatal: remote origin already exists"
```powershell
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/autocad-room-annotation.git
```

### "fatal: The current branch main has no upstream branch"
```powershell
git push -u origin main
```

---

## Repository Structure (What Gets Pushed)

```
autocad-room-annotation/
├── main.py                 # Entry point
├── config.py               # Configuration constants
├── ui.py                   # Tkinter GUI
├── spreadsheet_loader.py   # Spreadsheet reading
├── autocad_scanner.py      # ModelSpace scanning
├── polygon_matcher.py      # Text→polygon association
├── annotation_writer.py    # MTEXT insertion with XData
├── metadata_utils.py       # XData helpers
├── utils.py                # Utilities and geometry
├── requirements.txt        # Python dependencies
├── README.md               # Quick-start guide
├── DOCUMENTATION.md        # Detailed documentation
├── GITHUB_SETUP.md         # This file
├── .gitignore              # Files to exclude from Git
├── .gitattributes          # Line ending rules
└── LICENSE                 # MIT license (add manually)
```

Files **excluded** (in `.gitignore`):
- `__pycache__/`, `*.pyc`
- `.venv/`, virtual environment
- `*.dwg`, `*.bak` (AutoCAD files)
- `debug_run.py`, test scripts
- `.vscode/`, `.idea/` (IDE settings)

---

## Next Steps

1. **Add topics** to your repository (GitHub → Settings → Topics):
   - `autocad`
   - `python`
   - `automation`
   - `spreadsheet`
   - `geometry`

2. **Add a GitHub Actions workflow** (optional) for CI/CD:
   - Lint Python code
   - Run tests
   - Check requirements

3. **Create releases** when you reach stable versions:
   ```powershell
   git tag v1.0.0
   git push origin v1.0.0
   ```

4. **Enable GitHub Pages** (optional) to host documentation

---

## Questions?

- GitHub Help: https://docs.github.com
- Git Documentation: https://git-scm.com/doc
- Personal Access Token: https://github.com/settings/tokens
