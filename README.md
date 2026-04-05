# LocalClaw

A containerised Python agent that uses a local LLM to process Telegram commands, write code, and autonomously open GitHub Pull Requests.

## Overview

LocalClaw is an autonomous AI coding agent that bridges Telegram messaging with GitHub development. Send a coding request via Telegram, and the agent will:

1. Process your request using a local LLM (e.g., Qwen via Llama.cpp)
2. Generate and write code changes to your repository
3. Create a feature branch with the changes
4. Automatically open a GitHub Pull Request for review

## Features

- **Telegram Integration**: Receive and respond to commands through Telegram
- **Local LLM Processing**: Uses local language models (compatible with OpenAI-compatible APIs)
- **Autonomous Git Operations**: Automatically clones repos, creates branches, and manages commits
- **GitHub PR Automation**: Generates and opens pull requests with your changes
- **Security**: Path traversal protection to prevent unauthorized file modifications
- **Containerized**: Runs in Docker for easy deployment and isolation

## Architecture

```
Telegram → Agent (Docker) → Local LLM → Git Operations → GitHub API
```

The agent:
- Listens for messages on Telegram
- Sends prompts to a local LLM API endpoint
- Parses JSON responses defining file operations (write/delete)
- Executes git operations (checkout, commit, push)
- Creates pull requests via GitHub REST API

## Prerequisites

- Docker and Docker Compose
- A local LLM server running (e.g., llama.cpp)
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- GitHub Personal Access Token (PAT)
- A GitHub repository to target

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/dark-knight404/LocalClaw.git
cd LocalClaw
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_TOKEN=your_bot_token_here
GITHUB_PAT=your_personal_access_token
GITHUB_REPO=username/repo
LLM_API_URL=http://host.docker.internal:8080/v1/chat/completions
```

**Variable Guide:**
- `TELEGRAM_TOKEN`: Bot token from Telegram BotFather
- `GITHUB_PAT`: GitHub Personal Access Token (needs `repo` scope)
- `GITHUB_REPO`: Target repository in format `owner/repo`
- `LLM_API_URL`: Local LLM API endpoint (default: llama.cpp on port 8080)

### 3. Start the Local LLM Server

Command will be server-specific.

The server should be accessible at `http://localhost:8080/v1/chat/completions`

### 4. Run with Docker Compose

```bash
docker-compose up --build
```

The agent will start and listen for Telegram messages.

## Usage

Send a message to your Telegram bot describing what you want to code:

```
Create a new file called utils.py with a function that reverses a string
```

The agent will:
1. Generate code based on your request
2. Create a branch named `agent-update-{timestamp}`
3. Write the file(s)
4. Push to GitHub
5. Open a PR with a summary of changes
6. Reply with a link to the PR

## How It Works

### Message Handling Flow

1. **User sends Telegram message** → Agent receives via `handle_message()`
2. **LLM Processing** → Prompt sent to local LLM API with strict JSON schema requirement
3. **JSON Parsing** → Extracts action (write/delete) and file path
4. **Git Operations**:
   - Checkout and pull latest `main` branch
   - Create feature branch: `agent-update-{timestamp}`
   - Execute file operations (write or delete)
   - Commit changes
   - Push branch to GitHub
5. **PR Creation** → Uses GitHub API to open pull request
6. **User Notification** → Sends Telegram reply with PR link

### LLM Response Schema

The agent expects JSON responses from the LLM:

```json
{
  "action": "write" | "delete",
  "filename": "path/to/file.ext",
  "content": "file content here (empty if action is delete)"
}
```

## Configuration

### LLM API Endpoint

The default configuration assumes llama.cpp running locally. To use a different LLM:

1. Update `LLM_API_URL` in `.env` to point to your API
2. Ensure the API is compatible with OpenAI's chat completions format

### Git Defaults

The agent currently targets the `main` branch by default. To use `master` or another branch, edit line 77 in `agent.py`:

```python
"base": "main",  # Change to your default branch
```

## Security Considerations

- **Path Traversal Protection**: Blocks attempts to write outside the target repository
- **GitHub Token**: Keep your PAT secure; don't commit `.env` to version control
- **LLM Validation**: Validates LLM JSON responses before executing file operations

## Troubleshooting

### Container can't reach local LLM
- Ensure the LLM server is running (default port 11434)
- Check `LLM_API_URL` is correct in `.env`
- Docker uses `host.docker.internal` to access host services (configured in docker-compose.yml)

### PR creation fails
- Verify `GITHUB_PAT` has `repo` scope permissions
- Check `GITHUB_REPO` format is correct: `owner/repo`
- Ensure the GitHub repository exists and is accessible

### Agent doesn't respond to Telegram messages
- Verify `TELEGRAM_TOKEN` is correct
- Check container logs: `docker-compose logs agent`
- Ensure the bot is not already running elsewhere with the same token

### LLM returns invalid JSON
- Lower the temperature in `agent.py` (line 43) for more deterministic outputs
- Provide more specific prompts to the agent

## Dependencies

- `python-telegram-bot`: Telegram bot framework
- `requests`: HTTP library for API calls
- `gitpython`: Git repository management
See `requirements.txt` for versions.
---
