# LocalClaw

A containerised Python agent that uses a local LLM to process Telegram commands, write code, and autonomously open GitHub Pull Requests.

## Overview

LocalClaw is an autonomous AI coding agent that bridges Telegram messaging with GitHub development. Send a coding request via Telegram, and the agent will:

1. Process your request using a local LLM (e.g., Qwen via Llama.cpp)
2. Generate and write code changes to your repository
3. Create a feature branch with the changes
4. Automatically open a GitHub Pull Request for review

**Now with targeted file editing:** Use the `/edit` command to safely update existing files with natural language instructions!

## Features

- **Telegram Integration:** Receive and respond to commands through Telegram chat
- **Local LLM Processing:** Send structured requests to a local LLM API (OpenAI compatible)
- **File Editing with /edit:** Update existing files with explicit instructions
- **Autonomous Git Operations:** Clones repo, creates branches, commits changes, and pushes
- **GitHub PR Automation:** Opens PRs for review automatically
- **Security:** Path traversal protections prevent unauthorized operations
- **Containerized:** Runs in Docker for easy deployment

## Architecture

```
Telegram → Agent (Docker) → Local LLM → Git Operations → GitHub API
```

- Listens for messages and `/edit` commands on Telegram
- Sends prompts to LLM with strict JSON response requirement
- Executes git file operations from LLM's response (`write`/`delete`)
- Creates PRs for reviews

## Prerequisites

- Docker & Docker Compose
- Local LLM server (e.g., llama.cpp)
- Telegram Bot Token ([@BotFather](https://t.me/botfather))
- GitHub Personal Access Token (PAT)
- Target GitHub repository

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/dark-knight404/LocalClaw.git
cd LocalClaw
```

### 2. Configure Environment Variables

Copy `.env.example` and edit with your credentials:

```bash
cp .env.example .env
```

`.env` entries:

```env
TELEGRAM_TOKEN=your_bot_token
GITHUB_PAT=your_github_personal_access_token
GITHUB_REPO=username/repo
LLM_API_URL=http://host.docker.internal:8080/v1/chat/completions
```

### 3. Start the Local LLM Server

Make sure your LLM server is running and accessible at the specified API URL.

### 4. Run with Docker Compose

```bash
docker-compose up --build
```

The agent now listens for Telegram messages and commands.

## Usage

### 1. Freeform Code Generation

Send a plain message to the bot, e.g.

```
Create a new file called utils.py with a function that reverses a string
```

The agent will:
- Generate the code
- Create a branch `agent-update-{timestamp}`
- Make file changes
- Push and open a PR
- Reply with a PR link

### 2. Precise File Editing with /edit

Update an existing file with detailed instructions:

```
/edit <relative/path/to/file.py> <natural language instructions>
```

**Example:**

```
/edit app/utils.py Add a function called count_words(text) that returns the number of words in a string
```

**How it works:**
- Agent injects current file content + your instruction into the LLM prompt  
- LLM generates the entire updated file (partial outputs or placeholders are blocked)
- The agent:  
    - Checks out the main branch, pulls latest changes, creates a new feature branch
    - Writes the updated file, commits, pushes the branch, and opens a PR
    - Replies in Telegram with the PR link

**Notes:**
- The `/edit` command only works on files that already exist in the repository.
- It blocks any attempt to edit files outside the repo (path traversal protection).
- If the file does not exist, you’ll receive an error message.

### 3. File Operations (via LLM Instructions)

For other file operations (creating new files, deleting), just send a clear message.  
The LLM and agent coordinate using a strict JSON API for safety.

---

## Command Summary

| Command                  | Description                                               |
|--------------------------|-----------------------------------------------------------|
| Text message             | Create, modify, or delete files based on your prompt      |
| `/edit <file> <inst>`    | Update specific existing file with your instructions      |

---

## LLM Response Schema

All LLM replies **must** use this JSON structure:

```json
{
  "action": "write" | "delete",
  "filename": "path/to/file.ext",
  "content": "entire file content (leave blank if deleting)"
}
```

- `"write"`: The entire updated file is required; placeholders will trigger an error.
- `"delete"`: File will be removed if it exists.

---

## Configuration Tips

- To use a different LLM, update `LLM_API_URL` in `.env`
- The default PR base branch is `main`. To change, edit the `"base"` value in `agent.py`.

---

## Security

- **Path Traversal Protection:** Blocks access/edits outside repo folder.
- **PAT:** Never commit your `.env`/token to version control.
- **Validation:** Invalid LLM responses are identified and rejected.

---

## Troubleshooting

- **Container can't reach local LLM:** Check LLM is running and API URL is reachable. Try `host.docker.internal` for Docker-to-host.
- **PR failures:** Ensure the PAT is valid and has `repo` scope, and your repo exists.
- **/edit fails:** Make sure you provide a valid path to an existing file.
- **Bot doesn't respond:** Validate your Telegram token and view docker logs:  
  ```
  docker-compose logs agent
  ```

---

## Dependencies

- [`python-telegram-bot`](https://python-telegram-bot.org/)
- [`requests`](https://docs.python-requests.org/)
- [`gitpython`](https://gitpython.readthedocs.io/)

See `requirements.txt` for exact versions.

---
