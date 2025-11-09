from flask import Flask, request, jsonify, send_from_directory
import requests

app = Flask(__name__)

def parse_cookies(cookie_str):
    cookies = {}
    for item in cookie_str.split(';'):
        if '=' in item:
            key, value = item.strip().split('=', 1)
            cookies[key] = value
    return cookies

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/comment', methods=['POST'])
def comment():
    data = request.json
    cookies_str = data.get('cookies')
    post_id = data.get('postId')
    comment_text = data.get('commentText')

    if not (cookies_str and post_id and comment_text):
        return jsonify({"success": False, "error": "Missing required fields"})

    cookies = parse_cookies(cookies_str)

    # Facebook comment URL & payload - this is a simplified example
    url = f"https://www.facebook.com/ufi/add/comment/?post_id={post_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": f"https://www.facebook.com/{post_id}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # Payload format might need to be updated based on actual Facebook request inspect
    payload = {
        "comment_text": comment_text
        # Facebook expects more data in real scenario; inspect Facebook network tab for exact fields
    }

    with requests.Session() as session:
        session.cookies.update(cookies)
        try:
            response = session.post(url, headers=headers, data=payload)
            if response.ok:
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": f"HTTP {response.status_code}"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(debug=True)
