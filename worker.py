import os, time, base64, json, requests
import nest_asyncio, asyncio, contextlib, random, csv, re
import openai
import traceback

#  Private-repo imports
from server_config import append_logs_to_json, get_next_job, update_job_status, SERVER_URL, OPENAI_API_KEY
from openai_wrapper import ChatGPTWrapper
from automated_browsing.selenium_utility_module import SeleniumAgent
from automated_browsing.playwright_utility_module import PlaywrightAgent

from agentic_browsing_utils import process_job
from agentic_browsing_utils import process_verification

nest_asyncio.apply()      # keeps Colab-style async recursion happy

# TODO: Maintain a text file with job IDs that indicates which jobs have been tried already and can be safely dropped

QUEUE_FAILURE_INTERVAL = 40 # 40 seconds
NO_PENDING_INTERVAL = 360   # 6 minutes
JOB_PROCESSED_INTERVAL = 120 # 2 minutes
EXCEPTION_INTERVAL = 2400 # 40 minutes

# ------------------------------------------------------------------------------
#  Async wrapper that runs the complete Agentic pipeline for new jobs
# ------------------------------------------------------------------------------

async def run_full_agentic_pipeline(url_val, desc, promo):
    agent_s = SeleniumAgent()
    agent_p = PlaywrightAgent(headless=True)

    # unique folder for this job's screenshots/logs
    agent_p.path_stem = f"./job_artifacts/{promo}_{int(time.time())}/"
    os.makedirs(agent_p.path_stem, exist_ok=True)
        
    shopping_agent = ChatGPTWrapper(default_model="o4-mini-2025-04-16", api_key=OPENAI_API_KEY)
    verifier_agent = ChatGPTWrapper(default_model="o1-2024-12-17", api_key=OPENAI_API_KEY)
    
    status, output_dict, image_path = await process_job( url_val, desc, promo, agent_s, agent_p, shopping_agent, verifier_agent )
    output_dict['agent_p_log'] = agent_p.call_log

    return status, output_dict, image_path

# ------------------------------------------------------------------------------
#  Async wrapper that runs the Agentic pipeline for re-verification
# ------------------------------------------------------------------------------

async def run_verif_agentic_pipeline(url_val, desc, promo):
    agent_s = SeleniumAgent()
    agent_p = PlaywrightAgent(headless=True)

    # unique folder for this job's screenshots/logs
    agent_p.path_stem = f"./job_artifacts/{promo}_{int(time.time())}/"
    os.makedirs(agent_p.path_stem, exist_ok=True)
        
    shopping_agent = ChatGPTWrapper(default_model="o4-mini-2025-04-16", api_key=OPENAI_API_KEY)
    verifier_agent = ChatGPTWrapper(default_model="o1-2024-12-17", api_key=OPENAI_API_KEY)
    
    status, output_dict, image_path = "VERIFY", {}, None
    # status, output_dict, image_path = await process_verif_job( url_val, desc, promo, agent_s, agent_p, shopping_agent, verifier_agent )
    
    output_dict['agent_p_log'] = agent_p.call_log

    return status, output_dict, image_path


# ------------------------------------------------------------------------------
#  Main loop  – minimal, no logging
# ------------------------------------------------------------------------------
def main():
    while True:
        job_found = False
        
        # Get jobs, try to queue them then execute. different functions for pending/held or verify
        #for job_type in ["PENDING", "HELD", "VERIFY"]:
        
        for job_type in ["PENDING", "HELD"]:
            job = get_job(job_type) # Try to get a job of selected type
            
            if not job:
                # try the next job type
                time.sleep(4)
                continue
            
            job_found = True
            break
        
        # Completed checking for jobs, loop back if none found
        if not job_found:
            time.sleep(NO_PENDING_INTERVAL)
            continue
        
        # Try to lock a found job
        job_id = job["job_id"] # This is certain to be included, because the check gets made during get_job
        if not update_job_status(job_id, "QUEUED"):
            # wait for some time on failing to queue the job
            time.sleep(QUEUE_FAILURE_INTERVAL)
            continue

        # If all went fine, then try to process the job with a safe try except block
        try:
            url_val     = job["url"]
            description = job.get("description", "")
            promo_code  = job["promo_code"]

            if job_type == 'VERIFY':
                status, output_dict, image_path = await run_verif_agentic_pipeline(url_val, description, promo_code)
            else:
                status, output_dict, image_path = await run_full_agentic_pipeline(url_val, description, promo_code)
            
            update_job_status(job_id, status, text=output_dict, image_path=image_path)
            time.sleep(JOB_PROCESSED_INTERVAL)
            
        except Exception as exc:
            time.sleep(EXCEPTION_INTERVAL)
            error_message = str(exc)
            error_trace = traceback.format_exc()
        
            print("processing error:", error_message)
            print("full traceback:", error_trace)
        
            out_dict = {
                "error": error_message,
                "traceback": error_trace
            }
        
            update_job_status(job_id, "HELD", out_dict)



if __name__ == "__main__":
    main()
