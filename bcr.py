# baccarat_local_server.py
# pip install flask requests

from flask import Flask, Response, jsonify
import requests
import json
import os
from pathlib import Path

app = Flask(__name__, static_folder=".", static_url_path="")

URL = "https://aibcr.me/baccarat/getnewresult"


def load_secret(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value

    secrets_file = Path(__file__).with_name("secrets.json")
    if not secrets_file.exists():
        return ""

    try:
        return json.loads(secrets_file.read_text(encoding="utf-8")).get(name, "")
    except Exception:
        return ""


AIBCR_CSRF_TOKEN = load_secret("AIBCR_CSRF_TOKEN")
AIBCR_XSRF_TOKEN = load_secret("AIBCR_XSRF_TOKEN")
AIBCR_LARAVEL_SESSION = load_secret("AIBCR_LARAVEL_SESSION")

HEADERS = {
    "authority": "aibcr.me",
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7,fr-FR;q=0.6,fr;q=0.5",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://aibcr.me",
    "referer": "https://aibcr.me/ae/lobby",
    "priority": "u=1, i",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "x-csrf-token": AIBCR_CSRF_TOKEN,
    "x-requested-with": "XMLHttpRequest"
}

COOKIES = {
    key: value for key, value in {
        "XSRF-TOKEN": AIBCR_XSRF_TOKEN,
        "laravel_session": AIBCR_LARAVEL_SESSION,
    }.items() if value
}

DATA = {
    "table": "all"
}


def is_ae_table(table: dict) -> bool:
    identity = " ".join(str(table.get(key, "")) for key in (
        "game_code",
        "table_id",
        "table_name",
        "platform",
        "vendor",
        "provider",
    )).lower()

    if "wm" in identity:
        return False

    return "ae" in identity


def filter_ae_tables(data: dict) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return data

    filtered_data = dict(data)
    filtered_data["data"] = [table for table in data["data"] if is_ae_table(table)]
    return filtered_data


# ─────────────────────────────────────────────
#  BACCARAT ROAD LOGIC
# ─────────────────────────────────────────────

def result_to_columns(result: str) -> list[list[str]]:
    """
    Chuyển chuỗi result (B/P/T) thành Big Road dạng cột.
    T (Tie) không tạo cột mới, được gắn vào ô cuối cùng.
    Trả về list các cột, mỗi cột là list các ký tự B/P.
    """
    columns = []
    current_col = []
    last_bp = None

    for ch in result:
        if ch == 'T':
            # Tie không đổi cột, bỏ qua trong logic cầu phụ
            continue
        if ch not in ('B', 'P'):
            continue

        if last_bp is None:
            # Ván đầu tiên
            current_col.append(ch)
            last_bp = ch
        elif ch == last_bp:
            # Cùng kết quả → xuống hàng trong cột hiện tại
            current_col.append(ch)
        else:
            # Đổi kết quả → sang cột mới
            columns.append(current_col)
            current_col = [ch]
            last_bp = ch

    if current_col:
        columns.append(current_col)

    return columns


def compute_derived_road(columns: list[list[str]], look_back: int) -> list[dict]:
    """
    Tính bảng cầu phụ theo đúng thuật toán chuẩn Baccarat.

    look_back:
      - Big Eye Boy   = 1 (bắt đầu từ ô đầu tiên của cột 2)
      - Small Road    = 2 (bắt đầu từ ô đầu tiên của cột 3)
      - Cockroach Pig = 3 (bắt đầu từ ô đầu tiên của cột 4)

    Quy tắc cho từng ô trong Big Road tại (col_idx, row_idx):

    CASE 1 - Ô đầu cột (row_idx == 0), tức là kết quả vừa đổi chiều:
      So sánh độ sâu cột (col_idx - 1) với cột (col_idx - 1 - look_back)
      Bằng nhau → ĐỎ, khác nhau → XANH

    CASE 2 - Ô tiếp theo trong cột (row_idx > 0), tức là streak tiếp tục:
      Nhìn vào ô tại (col_idx - look_back, row_idx - 1) trong Big Road
      Nếu tồn tại → ĐỎ, không tồn tại → XANH

    Trả về list dict {col, row, color: "red"|"blue"}
    """
    road = []
    grid_col = 0
    grid_row = 0

    for col_idx, col in enumerate(columns):
        # Cần đủ look_back cột trước mới bắt đầu
        if col_idx < look_back:
            continue

        grid_row = 0
        for row_idx, _ in enumerate(col):
            if row_idx == 0:
                # CASE 1: đổi chiều - so sánh độ sâu 2 cột
                prev_col_len = len(columns[col_idx - 1]) if col_idx - 1 >= 0 else 0
                ref_col_len  = len(columns[col_idx - 1 - look_back]) if (col_idx - 1 - look_back) >= 0 else 0
                color = "red" if prev_col_len == ref_col_len else "blue"
            else:
                # CASE 2: streak tiếp tục - kiểm tra ô tham chiếu
                ref_col_idx = col_idx - look_back
                ref_row_idx = row_idx - 1
                if ref_col_idx >= 0 and ref_row_idx < len(columns[ref_col_idx]):
                    color = "red"
                else:
                    color = "blue"

            road.append({"col": grid_col, "row": grid_row, "color": color})
            grid_row += 1

        grid_col += 1

    return road


def compute_all_roads(result: str) -> dict:
    """
    Tính toàn bộ 3 bảng cầu phụ từ chuỗi result.
    """
    columns = result_to_columns(result)

    big_eye_boy   = compute_derived_road(columns, look_back=1)
    small_road    = compute_derived_road(columns, look_back=2)
    cockroach_pig = compute_derived_road(columns, look_back=3)

    return {
        "columns":      columns,
        "big_eye_boy":  big_eye_boy,
        "small_road":   small_road,
        "cockroach_pig": cockroach_pig,
    }


# ─────────────────────────────────────────────
#  API CALL
# ─────────────────────────────────────────────

def call_api():
    r = requests.post(
        URL,
        headers=HEADERS,
        cookies=COOKIES,
        data=DATA,
        timeout=20
    )
    return r


# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def home():
    return jsonify({
        "name": "baccarat-sexy-api",
        "status": "running",
        "endpoints": ["/status", "/api", "/pretty", "/roads"]
    })


@app.route("/status")
def status():
    return jsonify({
        "local_server": "running",
        "port": int(os.environ.get("PORT", 8000)),
        "target": URL,
        "configured": {
            "csrf_token": bool(AIBCR_CSRF_TOKEN),
            "xsrf_token": bool(AIBCR_XSRF_TOKEN),
            "laravel_session": bool(AIBCR_LARAVEL_SESSION)
        }
    })


@app.route("/api")
def api():
    try:
        r = call_api()
        try:
            data = filter_ae_tables(r.json())
            return Response(
                json.dumps(data, ensure_ascii=False),
                status=r.status_code,
                mimetype="application/json"
            )
        except:
            pass

        return Response(
            r.text,
            status=r.status_code,
            content_type=r.headers.get("content-type", "application/json")
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/pretty")
def pretty():
    try:
        r = call_api()
        try:
            data = filter_ae_tables(r.json())
            return Response(
                json.dumps(data, indent=4, ensure_ascii=False),
                mimetype="application/json"
            )
        except:
            return Response(r.text, mimetype="text/plain")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/roads")
def roads():
    """
    Trả về 3 bảng cầu phụ cho tất cả bàn (hoặc 1 bàn cụ thể).
    Query params: game_code, table_id (optional)
    """
    from flask import request as freq

    game_code_filter = freq.args.get("game_code")
    table_id_filter  = freq.args.get("table_id")

    try:
        r = call_api()
        data = filter_ae_tables(r.json())
        tables = data.get("data", [])

        result_list = []
        for t in tables:
            gc = t.get("game_code", "")
            tid = t.get("table_id", "")
            result_str = t.get("result", "")

            # Filter nếu có query param
            if game_code_filter and gc != game_code_filter:
                continue
            if table_id_filter and tid != table_id_filter:
                continue

            if not result_str:
                continue

            roads_data = compute_all_roads(result_str)

            result_list.append({
                "game_code":    gc,
                "table_id":     tid,
                "table_name":   t.get("table_name", ""),
                "result":       result_str,
                "goodRoad":     t.get("goodRoad", ""),
                "columns":      roads_data["columns"],
                "big_eye_boy":  roads_data["big_eye_boy"],
                "small_road":   roads_data["small_road"],
                "cockroach_pig": roads_data["cockroach_pig"],
            })

        return Response(
            json.dumps({"code": 200, "data": result_list}, indent=4, ensure_ascii=False),
            mimetype="application/json"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("=" * 50)
    print("LOCAL SERVER RUNNING")
    print(f"http://127.0.0.1:{port}")
    print(f"http://localhost:{port}/api")
    print(f"http://localhost:{port}/pretty")
    print(f"http://localhost:{port}/roads")
    print("=" * 50)

    app.run(host="0.0.0.0", port=port, debug=False)
