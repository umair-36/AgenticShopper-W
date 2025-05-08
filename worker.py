import os, time, base64, json, requests
import nest_asyncio, asyncio, contextlib, random, csv, re
import openai

nest_asyncio.apply()      # keeps Colab-style async recursion happy


#  Private-repo imports
from server_config import append_logs_to_json, get_next_job, update_job_status, SERVER_URL, OPENAI_API_KEY
from agentic_browsing_utils import process_job
from openai_wrapper import ChatGPTWrapper
from automated_browsing.selenium_utility_module import SeleniumAgent
from automated_browsing.playwright_utility_module import PlaywrightAgent




# ─────────────────────────────────────────────────────────────────────────────
#  Async wrapper that runs the Agentic pipeline
#  • returns combined-log text and the apply-promo image path (may be None)
# ─────────────────────────────────────────────────────────────────────────────
async def run_agentic_pipeline(url_val, desc, promo):
    agent_s = SeleniumAgent()
    agent_p = PlaywrightAgent(headless=True)

    # unique folder for this job's screenshots/logs
    agent_p.path_stem = f"./job_artifacts/{promo}_{int(time.time())}/"
    
    try:
        os.mkdir(agent_p.path_stem)
    except:
        pass
        
    shopping_agent = ChatGPTWrapper(default_model="o4-mini-2025-04-16",
                                    api_key=OPENAI_API_KEY)
    verifier_agent = ChatGPTWrapper(default_model="o1-2024-12-17",
                                    api_key=OPENAI_API_KEY)

    # Execute the business logic
    (
        promo_applied,
        promo_criteria,
        added_products,
        fin_out,
        pre_promo_img,
        apply_promo_img
    ) = await process_job(
        url_val, desc, promo,
        agent_s, agent_p, shopping_agent, verifier_agent
    )

    # Save the raw session log
    agent_p.save_log(f"{agent_p.path_stem}session.json")

    # Create augmented session file
    output_json_path = f"{agent_p.path_stem}session_with_return.json"
    append_logs_to_json(
        f"{agent_p.path_stem}session.json",
        output_json_path,
        promo_applied, promo_criteria, added_products, fin_out
    )

    # Read file text to send as text_file_data
    with open(output_json_path, "r", encoding="utf-8") as f:
        text_blob = f.read()

    return text_blob, apply_promo_img   # (may be None)

# ─────────────────────────────────────────────────────────────────────────────
#  Main loop  – minimal, no logging
# ─────────────────────────────────────────────────────────────────────────────
def main():
    while True:
        job = get_next_job()
        if not job:
            time.sleep(5)
            continue

        job_id      = job["job_id"]
        url_val     = job["url"]
        description = job.get("description", "")
        promo_code  = job["promo_code"]

        # Try to lock the job
        if not update_job_status(job_id, "QUEUED"):
            continue            # someone else got it

        # Run async pipeline
        try:
            text_blob, img_path = asyncio.run(
                run_agentic_pipeline(url_val, description, promo_code)
            )
            update_job_status(job_id, "PROCESSED", text=text_blob, image_path=img_path)

        except Exception as exc:
            print("processing error:", exc)
            update_job_status(job_id, "FAILED")

        time.sleep(2)

def main_test():
    job_id      = "36"
    url_val     = 'www.lifestride.com'
    description = "$15 off $75 + Free Shipping ."
    promo_code  = 'LS15OFF'

    try:
        text_blob, img_path = asyncio.run(
            run_agentic_pipeline(url_val, description, promo_code)
        )
        print(f"Got outputs as {img_path} and {text_blob}!!!!")
    except Exception as exc:
        print("processing error:", exc)

    time.sleep(2)

if __name__ == "__main__":
    main_test()
