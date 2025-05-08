import os
import base64
import requests
from server_config import append_logs_to_json, get_next_job, update_job_status

test_job_id = 0
input_json_path = f"session.json"
output_json_path = f"./job_artifacts/EXTRA25_1746076314/session_with_return.json"
output_img_path = "./job_artifacts/EXTRA25_1746076314/promo-apply_0_0.png"

print(f"current next job is {get_next_job()}")
promo_applied = True
promo_criteria = "Promo Description: Sitewide – 10% off One Pair (use code PINK10)\nProduct Categories: Applies to all products across the site (sitewide).\nProduct Quantities: Discount limited to one pair of shoes per order. If you purchase multiple pairs, only one pair will receive the 10% discount.\nProduct Prices: No minimum-purchase or price threshold required.\nSpecific Conditions: Customer must enter promo code “PINK10” at checkout. One‐time use; not combinable with other discount codes or offers on the same item."
added_products = [{ 'productName': 'MADISON MINT 12 PIECE DINNERWARE SET, SERVICE FOR 4', 'price': '$119.99', 'category': 'Dinnerware', 'validProduct': 'true', 'link': 'https://www.mikasa.com/products/madison-mint-12-piece-dinnerware-set-service-for-4', 'source': 'https://www.mikasa.com/collections/new-arrivals', 'customizations': {}, 'essential_customizations': {'Quantity': 'default'}, 'applicability': 'Yes - It can be added because the promo applies sitewide with no minimum quantity or purchase value requirements.', 'quantity_added': 1 }]
fin_out = 'INAPPLICABLE. The discount code entry returned an error (“Enter a valid discount code”), and the order total remained unchanged at $119.99, with no applied discount or fee removal.'

append_logs_to_json( input_json_path, output_json_path, promo_applied, promo_criteria, added_products, fin_out )

# Read file text to send as text_file_data
with open(output_json_path, "r", encoding="utf-8") as f:
	text_blob = f.read()

update_job_status( test_job_id, "PROCESSED", text_blob, output_img_path )
