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
    """Sends the prompt and forces a strict JSON response schema."""
    headers = {"Content-Type": "application/json"}

    system_instruction = (
        "You are an autonomous coding agent. You will receive a request to modify a repository. "
        "You MUST respond ONLY with a valid JSON object. Do not wrap the JSON in markdown code blocks. "
        "CRITICAL: If modifying an existing file, you MUST output the ENTIRE updated file. "
        "Do not use placeholders, comments like '# existing code', or ellipses. Truncating code will crash the system.\n"
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
        "max_tokens": 5000 # Increased to allow for full-file outputs
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
        "base": "main",
        "body": body
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json().get("html_url")
    else:
        raise Exception(f"PR Creation Failed: {response.text}")

async def execute_task(update: Update, llm_prompt: str, commit_context: str):
    """Core logic for interacting with LLM and Git, shared by all commands."""
    await update.message.reply_text("Thinking and processing...")

    raw_response = ask_qwen(llm_prompt)
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
        repo.git.checkout('main')
        repo.git.pull('origin', 'main')

        branch_name = f"agent-update-{int(time.time())}"
        repo.git.checkout('HEAD', b=branch_name)

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

        if repo.is_dirty() or repo.untracked_files:
            commit_message = f"Agent Action: {action_text}"
            repo.index.commit(commit_message)

            origin = repo.remote(name='origin')
            origin.push(f"{branch_name}:{branch_name}")

            pr_url = create_pull_request(
                branch_name=branch_name,
                title=commit_message,
                body=f"Automated PR generated via Telegram.\n\nContext:\n> {commit_context}"
            )

            await update.message.reply_text(f"Success! {action_text}\nReview and merge your PR here: {pr_url}")
        else:
            await update.message.reply_text(f"Code for '{target_file}' generated, but matches existing Git state. No PR created.")

        repo.git.checkout('main')

    except Exception as e:
        try:
            repo.git.checkout('main')
        except:
            pass
        await update.message.reply_text(f"Git/Filesystem Error: {str(e)}")


async def handle_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /edit filename instructions command."""
    if len(context.args) < 2:
        await update.message.reply_text("Syntax Error. Usage: /edit <filename> <instructions>")
        return

    target_file = context.args[0]
    instructions = " ".join(context.args[1:])

    file_path = os.path.abspath(os.path.join(REPO_PATH, target_file))
    if not file_path.startswith(os.path.abspath(REPO_PATH)):
        await update.message.reply_text("Security Alert: Path traversal blocked.")
        return

    if not os.path.exists(file_path):
        await update.message.reply_text(f"Error: File '{target_file}' does not exist in the repository.")
        return

    try:
        with open(file_path, "r") as f:
            current_content = f.read()
    except Exception as e:
        await update.message.reply_text(f"Error reading file: {e}")
        return

    # Inject the file content into the LLM prompt
    injected_prompt = (
        f"Update the file '{target_file}'.\n\n"
        f"Instructions: {instructions}\n\n"
        f"Here is the current file content. You MUST output the ENTIRE updated file. "
        f"Do NOT use placeholders or truncate the code.\n\n"
        f"```\n{current_content}\n```"
    )

    await execute_task(update, injected_prompt, commit_context=instructions)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles standard text messages for creating new files."""
    user_request = update.message.text
    await execute_task(update, user_request, commit_context=user_request)


def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Map the /edit command
    application.add_handler(CommandHandler("edit", handle_edit_command))

    # Map standard text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
