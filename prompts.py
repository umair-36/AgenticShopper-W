from prompt_helpers import (_is_yes, _lines_to_dict, _indexed_selection, 
                            make_indexed_list_string, _yes_no_query, _select_buttons)

# ----------------------------- specific llm calls ---------------------------- #

# ------------- Output as Dict

def _get_product_details(llm_agent, image_path, page_text):
    raw = llm_agent(
        f"Infer details such as productName, price, category and validProdcut (if the page is for adding a product to cart), based on product page as in attached image and page text as: {page_text}",
        instructions="Respond with details in the format: 'Detail type : Detail' in each line. Respond with 'None' if there are no details.",
        images=[image_path]
    ).output_text
    return _lines_to_dict(raw)

def _get_product_options(llm_agent, image_path):
    raw = llm_agent(
        "Based on the attached product page image, identify options that can be selected such as size, style, color etc. Some options such as color might often be preselected and would not need to be selected again. Take care to not include options that are crossed/unavailable/greyed out/etc",
        instructions="Respond with options that must be selected before adding to cart, in the format: 'Option type : Options' in each line. Respond with 'None' if there are no options.",
        # model = 'o1-2024-12-17',
        reasoning={"effort": "high"},
        images=[image_path]
    ).output_text
    return _lines_to_dict(raw)

def _get_essential_customizations(llm_agent, image_path, cust_dict):
    raw = llm_agent(
        f"Based on the attached product page image, and following customization options, identify which option must be selected before the product can be added to cart. Customization options:\n{cust_dict}",
        instructions="Respond in the following format in each line\nOption Name: Either 'required' or 'default'",
        # model = 'o1-2024-12-17',
        images=[image_path]
    ).output_text
    return _lines_to_dict(raw)


# ------------- Output as Button list

def _get_overlay_close_buttons(llm_agent, page_buttons, img):
    indexed_list = make_indexed_list_string(page_buttons)
    prompt = f"Based on attached image, which buttons are likely to close the overlay/dialog based on the following buttons list such as accept cookies or close or cancel etc:\n{indexed_list}"
    return _select_buttons(llm_agent, prompt, page_buttons, images=[img])

def _get_customization_buttons(llm_agent, cstm, opts, page_buttons):
    indexed_list = make_indexed_list_string(page_buttons)
    prompt = f"For selecting an option to customize {cstm}, any choice between options from {opts}, please select a button or buttons from the following list of buttons that are most likely to apply:\n{indexed_list}"
    return _select_buttons(llm_agent, prompt, page_buttons)

def _get_add_to_cart_buttons(llm_agent, page_buttons):
    indexed_list = make_indexed_list_string(page_buttons)
    prompt = f"Identify buttons that can be used to add the product to cart:\n{indexed_list}"
    return _select_buttons(llm_agent, prompt, page_buttons)

def _get_cart_checkout_options(llm_agent, links_and_buttons):
    indexed_list = make_indexed_list_string(links_and_buttons)
    prompt = f"Identify buttons/links that can be used to view the cart/checkout (take care of 'Add to cart' being something else):\n{indexed_list}"
    return _select_buttons(llm_agent, prompt, links_and_buttons)

def _get_promo_fields(llm_agent, text_fields, img):
    indexed_list = make_indexed_list_string(text_fields)
    prompt = f"Identify text fields that are most likely to be used for entering promo or coupon code:\n{indexed_list}"
    return _select_buttons(llm_agent, prompt, text_fields, images=[img])

def _get_apply_buttons(llm_agent, buttons, img):
    indexed_list = make_indexed_list_string(buttons)
    prompt = f"Identify buttons that are most likely to be used for applying/using the entered promo or coupon code:\n{indexed_list}"
    return _select_buttons(llm_agent, prompt, buttons, images=[img])

def _filter_product_links(llm_agent, links, q = None):
    add_on = f" Choose at most {q}." if q else ""
    indexed_list = make_indexed_list_string(links)
    prompt = f"Identify links that most likely to either product pages or product category pages:\n{indexed_list}.{add_on}"
    return _select_buttons(llm_agent, prompt, links)

# ------------- Output as Yes/No

def _has_overlay(llm_agent, image_path):
    yes, _ = _yes_no_query(
        llm_agent,
        "Based on the product page image, please identify if there is any popup or overlay on the page covering the screen",
        images=[image_path]
    )
    return yes

def _is_preselected(llm_agent, cstm, img):
    return _yes_no_query(
        llm_agent,
        f"Sometimes a default option is preselected for customizations etc. For {cstm}, look at the attached image to see if an option already seems selected. Respond Yes if one is already selected.",
        images=[img]
    )[0]

def _is_customization_applied(llm_agent, cstm, before_img, after_img):
    return _yes_no_query(
        llm_agent,
        f"Based on the product page images both before and after attempting to customize {cstm}, please identify has the customization been applied?",
        images=[before_img, after_img]
    )[0]

def _is_product_added(llm_agent, before_img, after_img):
    return _yes_no_query(
        llm_agent,
        "Based on the product page images both before and after attempting to add to cart, identify if it has been added",
        images=[before_img, after_img]
    )[0]

def _needs_more_quantity(llm_agent, promo_criteria, details):
    return _yes_no_query(
        llm_agent,
        f"Based on promo criteria as:\n{promo_criteria}\n\n and added product details as:\n{details}\n\n Is there an explicit requirement to increase quantity (other than for increasing order price)?",
    )[0]

def _is_url_valid(llm_agent, url_current, url_next):
    return _yes_no_query(
        llm_agent,
        f"Current URL is {url_current}\n, is this URL valid/complete? {url_next}",
    )[0]

def _cart_or_checkout_reached(llm_agent, before_img, after_img, _scenario = "cart"):
    return _yes_no_query(
        llm_agent,
        f"Based on the page images both before and after attempting to navigate, please identify if the {_scenario} page has been reached?",
        images=[before_img, after_img]
    )[0]

def _customization_required(llm_agent, criteria, product_details, added_products, cstm):
    add_on = ""
    if len(added_products)>0:
        add_on = f"\n\n and previously added product details are:\n{added_products}"
    return _yes_no_query(
        llm_agent,
        f"Assess if a customization for the category of '{cstm}' is required, based on promo criteria as:\n{criteria}\n\nProduct details are:{product_details}{add_on}",
    )[0]

def _is_promo_entered(llm_agent, before_img, after_img):
    return _yes_no_query(
        llm_agent,
        f"Based on the page images both before and after attempting to enter promo, please identify if promo field has been filled?",
        images=[before_img, after_img]
    )[0]

def _is_promo_applied(llm_agent, before_img, after_img, _scenario = "cart"):
    return _yes_no_query(
        llm_agent,
        f"Based on the page images both before and after attempting to enter promo, please identify if apply button has been attempted (regardless of whether it succeeded or not)?",
        images=[before_img, after_img]
    )[0]

def _is_product_applicable(llm_agent, promo_criteria, details):
    return _yes_no_query(
        llm_agent,
        f"Based on promo criteria as: {promo_criteria}\n can the following product be added to the cart:\n\n{details}",
        explained = True
    )

def _criteria_met(llm_agent, promo_criteria, added_products):
    return _yes_no_query(
        llm_agent,
        f"Based on promo criteria as:\n{promo_criteria}\n\n and added product details (must include at least one added product) as:\n{added_products}\n\n Has the promo criteria been met (making reasonable assumptions about intelligently selected products)? ",
        explained = True
    )

def _has_promo_field(llm_agent, page_img):
    return _yes_no_query(
        llm_agent,
        f"Look at the attached cart/checkout page and see if there is an option to enter and apply a promo or coupon code.",
        images=[page_img]
    )[0]

# ------------- Standard calls
def _sift_link_options(llm_agent, link_hrefs, promo_criteria, add_on):
    return llm_agent(
        f"These are the links to choose from:\n{link_hrefs}",
        # instructions = f"Respond with at least 5 or more links, one per line. Each line must start with either 'ADD:' or with 'BROWSE:'\n Here ADD is to add products or BROWSE to move to pages that fulfill the promo criteria as specified here: {promo_criteria}",
        instructions = f"Respond with at least 5 or more links, one per line. Each line must start with either 'ADD:' or with 'BROWSE:'\n Here ADD is to add products or BROWSE to move to pages that lead to products that fulfill the promo criteria as specified here: \n{promo_criteria}{add_on}",
        model = "o4-mini-2025-04-16",
    ).output_text

def _product_link_filter(llm_agent, links):
    # TODO: also provide URL and ask to ensure products are from the same site/brand. Remove length restriction from generate links to fallback to non-RTA.
    return llm_agent(
        f"These are the links to choose from:\n{links}",
        instructions = f"Respond with selected links, one per line. Select the ones that are more probable to point to a product buying page.",
        # instructions = f"Respond with selected links, one per line. Select the ones that are more probable to point to a product buying page that corresponds to promo criteria as: {promo_criteria}.",
        model = "o4-mini-2025-04-16",
    ).output_text

def _cause_of_failure(llm_agent, failure_image):
    return llm_agent(
        "Based on the attached product page image, please identify what might be causing the failure to add the product to cart",
        instructions="Respond with a brief explanation in one line, in format as 'Cause (one or two words)':'some detail such as missing setting or incorrect value etc'. If no reason is evident, respond with 'None'",
        images=[failure_image]
    ).output_text

def _make_valid_url(llm_agent, c_url, n_url, failed_urls = ""):
    return llm_agent(
        f"Current URL is {c_url}, next href to navigate to is {n_url}, try to generate correct possible url or urls based on these.{failed_urls}",
        #instructions = f"Respond with one or more urls, with only one per line.",
        instructions = f"Respond with one url in one line.",
    ).output_text


def _generate_criterion(llm_agent, description, promo, landing_page, add_on, ):
    format = """
    Promo Description: (repeat the promo description here)
    Product Categories: (specify if only specific categories are explicitly defined)
    Product Quantities: (specify if any quantity criteria is explicitly defined and needs to be met)
    Product Prices: (specify if any price criteria for applicable products or total price is explicitly defined)
    Specific Conditions: (specify if any additional conditions other than above are explicitly defined to apply the promo)
    Discount Effect: (specify what benefit the discount/promotion will provide, this will be verified at the end)
    """
    return llm_agent(
        f"Consider the attached website screenshot. For a discount description given as \"{description}\" for promo code \"{promo}\" , write down discount criteria.{add_on}",
        model = "o4-mini-2025-04-16",
        instructions = f"Adhere to this format:\n{format}",
        images = [landing_page]
    ).output_text

def _verify_criterion(llm_agent, description, promo_criteria):
    return llm_agent(
        f"For a discount description given as \"{description}\", is this summary complete?: {promo_criteria}",
        instructions = f"Start with either a Yes or No. If No, then continue to briefly explain why (very concisely).",
        model = "gpt-4.1-2025-04-14"
    ).output_text

def _make_valid_url_oneoff(llm_agent, p_url, n_href):
    return llm_agent(
        f"Form a link based on website url as {p_url} and href I want to visit as {n_href}, respond with same url as href if it is already formed.",
        instructions = "Respond with a url only in one line",
    ).output_text


def _customization_option_selections(llm_agent, product_page_img, promo_criteria, cstm, options):
    return llm_agent(
        f"Select the suitable option or options from {options}, that fulfill {cstm} requirements based on promo criteria as {promo_criteria}",
        instructions=f"Only respond with one or more option or options from {options}.",
        images=[product_page_img]
    ).output_text

def _final_outcome(llm_agent, promo_criteria, img_before, img_after):
    return llm_agent(
        f"Based on the attached images of both before promo/coupon and after, please assess what effect (if any) that the promo/coupon had. Promo details were: {promo_criteria}",
        instructions=f"Start response with one word about the promo application status, such as APPLIED/EXPIRED/INAPPLICABLE/NONEXISTANT etc whichever might be appropriate. Afterwards, detail the effects it had if any, such as reduction in price or removed shipping fees or error thrown or error message etc.",
        images=[img_before, img_after],
        model = 'o1-2024-12-17',
    ).output_text