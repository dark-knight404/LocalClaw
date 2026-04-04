import os
import requests
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
    """Sends the prompt to the host llama-server."""
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "You are an automated coding agent. Output ONLY the raw code content. No markdown wrappers, no conversational text."
            },
            {
                "role": "user",
                "content": prompt_text
            }
        ],
        "temperature": 0.2,
        "max_tokens": 4000
    }
    
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        # Parse the OpenAI-style response
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_request = update.message.text
    await update.message.reply_text("Thinking...")

    new_code = ask_qwen(user_request)
    
    if not new_code:
        await update.message.reply_text("LLM failed to generate a response.")
        return

    # Hardcoded target file for testing the pipeline
    target_file = "workspace.py"
    file_path = os.path.join(REPO_PATH, target_file)

    try:
        with open(file_path, "w") as f:
            f.write(new_code)
        
        # Git Operations
        repo.git.add(all=True)
        # Check if there are changes to commit
        if repo.is_dirty() or repo.untracked_files:
            repo.index.commit(f"Agent update via Telegram: {user_request[:30]}...")
            origin = repo.remote(name='origin')
            origin.push()
            await update.message.reply_text(f"Code pushed to {target_file} on GitHub.")
        else:
            await update.message.reply_text("Code generated, but no changes detected for Git to commit.")

    except Exception as e:
        await update.message.reply_text(f"Execution Error: {str(e)}")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == "__main__":
    main()
