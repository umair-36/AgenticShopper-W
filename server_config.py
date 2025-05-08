import os, time, base64, json, requests

#  Environment
SERVER_URL      = os.environ.get("SERVER_URL", "http://127.0.0.1:5000")
OPENAI_API_KEY  = os.environ["OPENAI_API_KEY"] # must be supplied

#  Helper: server API
def get_next_job():
    try:
        r = requests.get(f"{SERVER_URL}/private_api/get_next_job", timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data if "job_id" in data else None
    except Exception as e:
        print("get_next_job error:", e)
    return None


def update_job_status(job_id, status, text=None, image_path=None):
    payload = {"job_id": job_id, "status": status}

    if text is not None:
        payload["text_file_data"] = text

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            payload["image_file_data"] = base64.b64encode(f.read()).decode("ascii")

    try:
        r = requests.post(f"{SERVER_URL}/private_api/update", json=payload, timeout=30)
        return r.status_code == 200
    except Exception as e:
        print(f"update_job_status({job_id}) error:", e)
        return False
        

def append_logs_to_json(file_path, output_path,
                        promo_applied, promo_criteria, added_products, fin_out):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    logs = [
        "--- RETURN LOG for apply_promo ---",
        f"promo_applied: {promo_applied}",
        f"promo_criteria: {promo_criteria}",
        f"added_products: {json.dumps(added_products, ensure_ascii=False)}",
        f"fin_out: {fin_out}"
    ]

    # In case the session log isn't a list, coerce to list then extend
    if isinstance(data, list):
        data.extend(logs)
    else:
        data = [data] + logs

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)