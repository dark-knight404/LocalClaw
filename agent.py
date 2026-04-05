import os
import json
import re
import requests
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from git import Repo

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
LLM_API_URL = os.environ.get("LLM_API_URL")
REPO_PATH = "/app/repo"

# Initialize Repo
if not os.path.exists(os.path.join(REPO_PATH, ".git")):
    git_url = f"https://oauth2:{GITHUB_PAT}@github.com/{GITHUB_REPO}.git"
    Repo.clone_from(git_url, REPO_PATH)

repo = Repo(REPO_PATH)

def ask_qwen(prompt_text):
    """Sends the prompt and forces a strict JSON response schema with action types."""
    headers = {"Content-Type": "application/json"}

    system_instruction = (
        "You are an autonomous coding agent. You will receive a request to modify a repository. "
        "You MUST respond ONLY with a valid JSON object. Do not wrap the JSON in markdown code blocks. "
        "Use this exact schema:\n"
        "{\n"
        '  "action": "write" OR "delete",\n'
        '  "filename": "path/to/the/file.ext",\n'
        '  "content": "the raw code content here (leave empty if action is delete)"\n'
        "}"
    )

    payload = {
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt_text}
        ],
        "temperature": 0.1,
        "max_tokens": 4000
    }

    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"API Error: {str(e)}"

def extract_json_payload(raw_response):
    """Aggressively hunts for a JSON object."""
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None

def create_pull_request(branch_name, title, body):
    """Uses the GitHub REST API to create a PR."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls"
    headers = {
        "Authorization": f"Bearer {GITHUB_PAT}",
        "Accept": "application/vnd.github+json"
    }
    data = {
        "title": title,
        "head": branch_name,
        "base": "main",  # Change this if your default branch is 'master'
        "body": body
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json().get("html_url")
    else:
        raise Exception(f"PR Creation Failed: {response.text}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_request = update.message.text
    await update.message.reply_text("Thinking and processing...")

    raw_response = ask_qwen(user_request)
    if not raw_response or raw_response.startswith("API Error"):
        await update.message.reply_text(f"LLM failure: {raw_response}")
        return

    parsed_data = extract_json_payload(raw_response)
    if not parsed_data or "filename" not in parsed_data or "action" not in parsed_data:
        await update.message.reply_text("Execution Error: LLM failed to output the correct JSON schema.")
        print(f"FAILED PARSE RAW OUTPUT:\n{raw_response}")
        return

    action = parsed_data.get("action")
    target_file = parsed_data.get("filename")
    new_code = parsed_data.get("content", "")

    # Security Check
    file_path = os.path.abspath(os.path.join(REPO_PATH, target_file))
    if not file_path.startswith(os.path.abspath(REPO_PATH)):
        await update.message.reply_text(f"Security Alert: Blocked path traversal attempt to {target_file}")
        return

    try:
        # 1. Reset to main and pull latest changes to avoid conflicts
        repo.git.checkout('main')
        repo.git.pull('origin', 'main')

        # 2. Create a unique branch for this task
        branch_name = f"agent-update-{int(time.time())}"
        repo.git.checkout('HEAD', b=branch_name)

        # 3. Execute the File Action
        if action == "delete":
            if os.path.exists(file_path):
                os.remove(file_path)
                repo.git.rm(target_file)
                action_text = f"Deleted {target_file}"
            else:
                await update.message.reply_text(f"Error: Agent tried to delete '{target_file}' but it doesn't exist.")
                return
        elif action == "write":
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                f.write(new_code)
            repo.git.add(all=True)
            action_text = f"Created/Updated {target_file}"
        else:
            await update.message.reply_text(f"Error: Unknown action '{action}' hallucinated by LLM.")
            return

        # 4. Commit, Push, and PR
        if repo.is_dirty() or repo.untracked_files:
            commit_message = f"Agent Action: {action_text}"
            repo.index.commit(commit_message)

            origin = repo.remote(name='origin')
            # Push the new branch to origin
            origin.push(f"{branch_name}:{branch_name}")

            # Create the PR via API
            pr_url = create_pull_request(
                branch_name=branch_name,
                title=commit_message,
                body=f"Automated PR generated via Telegram prompt:\n\n> {user_request}"
            )

            await update.message.reply_text(f"Success! {action_text}\nReview and merge your PR here: {pr_url}")
        else:
            await update.message.reply_text(f"Code for '{target_file}' generated, but matches existing Git state. No PR created.")

        # 5. Clean up: Return agent to main branch
        repo.git.checkout('main')

    except Exception as e:
        # If it fails, attempt to return to main branch so the repo isn't left in a broken state
        try:
            repo.git.checkout('main')
        except:
            pass
        await update.message.reply_text(f"Git/Filesystem Error: {str(e)}")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == "__main__":
    main()
