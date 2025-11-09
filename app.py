# app.py
import os
import time
import uuid
import threading
from typing import List
from flask import Flask, request, jsonify, send_from_directory, abort
import requests
from dotenv import load_dotenv

load_dotenv()  # optional: load env vars from .env

app = Flask(__name__, static_folder='.', static_url_path='')

# In-memory tasks store (for demo). For production use persistent store.
tasks = {}
GRAPH_API_BASE = "https://graph.facebook.com"
API_VERSION = os.getenv("FB_API_VERSION", "v17.0")  # change if needed

def fb_post_comment(post_id: str, message: str, page_token: str, timeout=10):
    """
    Post a comment to Facebook Graph API.
    Returns (ok: bool, resp_json_or_text)
    """
    url = f"{GRAPH_API_BASE}/{API_VERSION}/{post_id}/comments"
    params = {
        "message": message,
        "access_token": page_token
    }
    try:
        resp = requests.post(url, data=params, timeout=timeout)
    except requests.RequestException as e:
        return False, {"error": "network", "message": str(e)}
    try:
        j = resp.json()
    except ValueError:
        return False, {"error": "non-json-response", "status_code": resp.status_code, "text": resp.text}

    if resp.status_code == 200 and "id" in j:
        return True, j
    else:
        # Graph API error payload under "error"
        return False, j

def validate_token(page_token: str):
    """
    Lightweight validation: call /me to confirm token is valid.
    For Page tokens, /me returns the Page id/name for Page tokens.
    Returns (ok, info)
    """
    url = f"{GRAPH_API_BASE}/{API_VERSION}/me"
    try:
        r = requests.get(url, params={"access_token": page_token}, timeout=8)
        data = r.json()
        if r.status_code == 200:
            return True, data
        else:
            return False, data
    except requests.RequestException as e:
        return False, {"error": "network", "message": str(e)}
    except ValueError:
        return False, {"error": "invalid_response"}

def posting_worker(task_id: str, post_id: str, page_token: str, messages: List[str], delay: float):
    """
    Background worker that posts comments sequentially.
    Respects tasks[task_id]['running'] to allow stop.
    """
    tasks[task_id]["logs"].append(f"Worker started for post {post_id} — {len(messages)} messages, delay {delay}s")
    for idx, raw_msg in enumerate(messages):
        if not tasks.get(task_id, {}).get("running"):
            tasks[task_id]["logs"].append("Stopped by user request.")
            break

        msg = raw_msg.strip()
        if not msg:
            tasks[task_id]["logs"].append(f"Skipping empty line #{idx+1}")
            continue

        # Try posting, with a small retry/backoff in case of transient errors
        attempt = 0
        max_attempts = 3
        backoff = 1
        success = False
        while attempt < max_attempts and tasks[task_id]["running"]:
            attempt += 1
            tasks[task_id]["logs"].append(f"[{idx+1}] Attempt {attempt}: posting...")
            ok, resp = fb_post_comment(post_id, msg, page_token)
            if ok:
                tasks[task_id]["logs"].append(f"[{idx+1}] Posted successfully: {resp.get('id')}")
                success = True
                break
            else:
                # Log Graph API error details (sanitized)
                err_summary = resp.get("error") if isinstance(resp, dict) else resp
                tasks[task_id]["logs"].append(f"[{idx+1}] Error: {err_summary}")
                # If error indicates permission or OAuth issue, stop the worker
                if isinstance(err_summary, dict):
                    code = err_summary.get("code")
                    subcode = err_summary.get("error_subcode")
                    # permission/auth errors: don't retry
                    if code in (190, 102, 4):  # 190 = OAuthException, 102/4 rate or temporary
                        tasks[task_id]["logs"].append(f"[{idx+1}] OAuth/permission error — aborting worker.")
                        tasks[task_id]["running"] = False
                        break
                # transient: wait then retry
                time.sleep(backoff)
                backoff *= 2

        if not success and tasks[task_id]["running"]:
            tasks[task_id]["logs"].append(f"[{idx+1}] Failed after {max_attempts} attempts — continuing to next message.")

        # Respect configured delay between messages
        # Also check running status after sleep
        slept = 0.0
        while slept < delay and tasks[task_id]["running"]:
            to_sleep = min(0.5, delay - slept)
            time.sleep(to_sleep)
            slept += to_sleep

    tasks[task_id]["running"] = False
    tasks[task_id]["logs"].append("Worker finished.")

# Serve the UI file (index.html) — ensure your frontend file is named index.html in same folder
@app.route("/", methods=["GET"])
def index():
    return send_from_directory('.', 'index.html')

@app.route("/start", methods=["POST"])
def start_task():
    """
    Expected form fields:
      - token: Page Access Token (string)
      - post_id: target post id (string)
      - hater: optional prefix for messages (string)
      - delay: seconds (float)
      - file: uploaded text file with one message per line
    """
    token = request.form.get("token") or request.form.get("page_token")
    post_id = request.form.get("post_id")
    hater = request.form.get("hater", "").strip()
    delay = float(request.form.get("delay", 5.0))

    if not token or not post_id:
        return jsonify({"error": "token and post_id required"}), 400

    uploaded = request.files.get("file")
    if uploaded:
        content = uploaded.read().decode(errors='ignore')
        messages = [line for line in content.splitlines() if line.strip()]
    else:
        # allow messages passed in form as newline-joined string
        raw = request.form.get("messages", "")
        messages = [line for line in raw.splitlines() if line.strip()]

    if not messages:
        return jsonify({"error": "no messages provided"}), 400

    # Prepend hater name if provided
    if hater:
        messages = [f"{hater}: {m}" for m in messages]

    # Basic token validation (best-effort)
    ok, info = validate_token(token)
    if not ok:
        return jsonify({"error": "invalid_token", "details": info}), 400

    # Create task
    task_id = "TASK-" + uuid.uuid4().hex[:8].upper()
    tasks[task_id] = {
        "running": True,
        "logs": [f"Task {task_id} created."],
        "post_id": post_id,
        "created_at": time.time()
    }

    # Start worker thread
    worker = threading.Thread(target=posting_worker, args=(task_id, post_id, token, messages, delay), daemon=True)
    worker.start()
    tasks[task_id]["thread"] = worker

    return jsonify({"task_id": task_id})

@app.route("/stop/<task_id>", methods=["POST"])
def stop_task(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "task_not_found"}), 404
    task["running"] = False
    task["logs"].append("Stop requested via API.")
    return jsonify({"message": f"stop requested for {task_id}"})

@app.route("/logs/<task_id>", methods=["GET"])
def get_logs(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "task_not_found"}), 404
    # Return last N logs for brevity
    return jsonify({"running": task["running"], "logs": task["logs"][-200:]})

@app.route("/tasks", methods=["GET"])
def list_tasks():
    # Basic listing
    return jsonify({tid: {"running": t["running"], "post_id": t.get("post_id"), "created_at": t.get("created_at")} for tid, t in tasks.items()})

if __name__ == "__main__":
    # For local development only. Use a proper WSGI server in production.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
