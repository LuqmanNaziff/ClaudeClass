# Claude AI for Programmers and Automation

This repository is the starting point for the **Claude AI for Programmers and
Automation** course. We build a backend application incrementally with Python, FastAPI, Pydantic, and the Anthropic Claude API.

The repository is intentionally a small scaffold at the start of the course.

## What you need

Install the following before starting:

- **Git**, to download and update the repository.
- **Python 3.11 or newer**, with the option to add Python to your `PATH`
  during installation.
- An **Anthropic API key** supplied for the course. Do not share it or commit
  it to Git.
- A terminal:
  - macOS: Terminal or iTerm2
  - Linux: your preferred terminal
  - Windows: PowerShell, Windows Terminal, or Command Prompt

The commands below use `python` and `pip`. If your system uses `python3`
instead, substitute `python3` for `python`. On Windows, the Python launcher
command `py` can also be used instead of `python`.

## Download the repository

Clone the repository and move into its directory:

```text
git clone https://github.com/marcnzedspaces/Claude_AI_for_Programmers_and_Automation_C2_2026.git
cd Claude_AI_for_Programmers_and_Automation_C2_2026
```

If you already have the repository, update it with:

```text
git pull
```

## Create a virtual environment

Using a virtual environment keeps this course's packages separate from other
Python projects.

### macOS and Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell prevents activation because of its execution-policy settings,
run this once for your user account, then activate the environment again:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Windows Command Prompt

```bat
py -m venv .venv
.\.venv\Scripts\activate.bat
```

When the environment is active, your terminal prompt normally starts with
`.venv`.

## Install the dependencies

With the virtual environment active, install the pinned course dependencies:

```text
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

This installs FastAPI, Uvicorn, Pydantic, PyMongo, and the Anthropic Python
SDK. Use `python -m pip` so that packages are installed into the active
environment.

## Configure environment variables

Create a local `.env` file from the provided template:

### macOS and Linux

```bash
cp .env.example .env
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### Windows Command Prompt

```bat
copy .env.example .env
```

Open `.env` in a text editor and replace
`your_real_key_here` with the Anthropic API key supplied for the course.
Review the model, timeout, and retry settings as the exercise requires.

Never commit `.env`, paste its contents into an issue, or share its API key.
The `.env.example` file contains names and safe placeholder values only.

## Run the application

The initial repository is a scaffold and does not yet contain an application
entry point. In particular, `app/main.py` and the `app` FastAPI object are
added during the relevant course exercise. Therefore, the server command
below will work after that exercise has created `app/main.py` with an object
named `app`:

```text
python -m uvicorn app.main:app --reload
```

The `--reload` option restarts the development server when source files
change. It is useful for local development and should not be used as a
production deployment configuration.

When the server starts, open:

- <http://127.0.0.1:8000>
- <http://127.0.0.1:8000/docs> for FastAPI's interactive API documentation

If the course exercise uses a different module or application variable, use
the entry point specified by the instructor instead of `app.main:app`.

To stop the server, press `Ctrl+C`. To leave the virtual environment, run:

```text
deactivate
```

## Typical course workflow

1. Activate `.venv`.
2. Pull the latest exercise changes.
3. Install dependencies if `requirements.txt` changed.
4. Confirm `.env` exists and contains your local API key.
5. Start the development server with Uvicorn.
6. Use `/docs` or an HTTP client such as Postman to call the endpoints.
7. Stop the server with `Ctrl+C` before deactivating the environment.

## Troubleshooting

- **`python` or `pip` is not recognized:** install Python, restart the
  terminal, and confirm `python --version` (or `python3 --version`).
- **Packages are installed but imports fail:** activate `.venv` and reinstall
  with `python -m pip install -r requirements.txt`.
- **`Could not import module "app.main"`:** the current exercise has not added
  `app/main.py` yet, or the command is being run outside the repository root.
- **PowerShell will not activate `.venv`:** use the execution-policy command
  shown above, or use Command Prompt instead.
- **Port 8000 is already in use:** stop the other local server or run
  `python -m uvicorn app.main:app --reload --port 8001`, then open port 8001
  in your browser.
