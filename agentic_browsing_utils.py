import asyncio
import time
import random

from prompts import ( _get_product_details, _get_product_options, _get_essential_customizations
                    , _get_overlay_close_buttons, _get_customization_buttons, _get_add_to_cart_buttons, 
                    _get_cart_checkout_options, _get_promo_fields, _get_apply_buttons, _has_overlay, 
                    _filter_product_links, _is_preselected, _is_customization_applied, _criteria_met, 
                    _is_product_added, _needs_more_quantity, _is_url_valid, _cart_or_checkout_reached, 
                    _customization_required, _is_promo_entered, _is_promo_applied, _is_product_applicable, 
                    _has_promo_field, _sift_link_options, _product_link_filter, _cause_of_failure, 
                    _make_valid_url, _generate_criterion, _verify_criterion, _make_valid_url_oneoff, 
                    _customization_option_selections, _final_outcome, 
                    )


def format_url(url):
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def generate_criterion(path_stem, url, desc, promo, agent_s, promo_agent, verifier_agent, DEBUG = False, attempts = 4):
    add_on = ""
    img_path = f"{path_stem}landing_page.png"
    agent_s.navigate_to_url(url); time.sleep(4)
    agent_s.take_screenshot(img_path)
    all_text = agent_s.get_body_text()
    while attempts > 0:
        criteria = _generate_criterion(promo_agent, desc, promo, img_path, add_on)
        verifier_resp = _verify_criterion(verifier_agent, desc, criteria)
        if 'no' in verifier_resp[:4].lower():
            attempts -= 1
            add_on += f"\nPlease take care to avoid this (but still keep the output concise) {verifier_resp}"
            if DEBUG:
                print(add_on)
                print(f"\nPrevious summary was {criteria}")
        else:
            agent_s.close_driver()
            return criteria, verifier_resp
    # best to just continue with it after 4 attemps at refining
    agent_s.close_driver()
    return criteria, verifier_resp


async def generate_links_fallback(url, promo_criteria, agent_p, link_agent, hops = 5):
    to_browse = []
    to_add = []
    browsed = [url]
    add_on = ""

    source_url_dict = {}
    base_url = url

    await agent_p.initialize_driver()
    await agent_p.navigate_to_url(url)

    hop_i = 0
    tried_twice = []

    while hops>0:
        hop_i += 1
        print(f"Attempting hop {hop_i}")
        possible_links = await agent_p.get_possible_links()
        try:
            # need to properly form URLs
            link_base_hrefs = [link["href"] for link in possible_links]
            if len(link_base_hrefs) > 10:
                print("More than 7 links found on page, filtering down")
                link_base_hrefs_filtered = _filter_product_links(link_agent, link_base_hrefs)
                if len(link_base_hrefs_filtered) <= 4:
                    link_base_hrefs_filtered = link_base_hrefs[:10]
                elif len(link_base_hrefs_filtered) > 10:
                    link_base_hrefs_filtered = random.sample(link_base_hrefs_filtered, 10)
                print(f"Remaining links: {link_base_hrefs_filtered}")
            else:
                print(f"Only {len(link_base_hrefs)} links found:\n{link_base_hrefs}")
                link_base_hrefs_filtered = link_base_hrefs.copy()
            if len(link_base_hrefs_filtered) > 7:
                  link_base_hrefs_filtered = link_base_hrefs_filtered[:7]
            link_hrefs = [_make_valid_url_oneoff( link_agent, base_url, href) for href in link_base_hrefs_filtered]
            print(f"Links: {link_hrefs}")
            for href in link_hrefs:
                valid_href = False
                for base_href in link_base_hrefs:
                    if base_href in href:
                        valid_href = True
                        break
                if not valid_href:
                    # link_hrefs.remove(href)
                    print(f"Found possibly invalid href as {href}")
        except Exception as e:
            print("Faced exception as {e}")
            link_hrefs = []

        if (hop_i == 1) and len(link_hrefs) < 1:
            raise Exception("No links found on landing page")

        hits = 0
        if len(link_hrefs) >= 1 :
            link_resp = _sift_link_options(link_agent, link_hrefs, promo_criteria, add_on)
            for line in link_resp.split('\n'):
                if line.startswith('ADD:') and hop_i != 1:
                    new_url = line[4:].strip()
                    if new_url not in link_hrefs:
                        print(f"URL hallucination detected with url: {new_url}")
                    elif new_url not in to_add:
                        hits += 1
                        to_add.append(new_url)
                        source_url_dict[new_url] = url
                elif line.startswith('BROWSE:'):
                    new_url = line[7:].strip()
                    if new_url not in link_hrefs:
                        print(f"URL hallucination detected with url: {new_url}")
                    elif (new_url not in browsed) and (new_url not in to_browse):
                        hits += 1
                        to_browse.append(new_url)
        if hits == 0:
            await agent_p.close_driver()
            await asyncio.sleep(10)
            await agent_p.initialize_driver()
            await asyncio.sleep(5)
            if url not in tried_twice:
                to_browse += [url]
                tried_twice += [url]
        if len(to_browse) > 1:
          next_url_idx = random.randint(0, len(to_browse)-1)
        else:
          next_url_idx = 0
        _next_url = to_browse.pop(next_url_idx) if to_browse else None
        if _next_url:

            try:
                # try the playwright version, fallback to selenium version
                current_url = agent_p.page.url
            except:
                current_url = agent_p.driver.current_url
            if not _is_url_valid(link_agent, current_url, _next_url):
                next_url = _make_valid_url(link_agent, current_url, _next_url)
                print(f"URL {_next_url} was incomplete, attempting fixing to {next_url}")
            else:
                next_url = _next_url

            browsed.append(next_url)
            await agent_p.navigate_to_url(next_url)
            url = next_url
            hops -= 1
            if len(to_add) >= 10:
                hops = 0
        else:
            if (len(to_add) < 5) and add_on == "":
                print("Entered contingency prompt stance")
                add_on = f"\nIf no relevant product or page links are found, you must find BROWSE links that are likely to lead to the products you're looking for."
            else:
                hops = 0
    if len(to_add)>4:
        links = "\n".join(to_add)
        link_resp = _product_link_filter(link_agent, links)
        r_to_add = link_resp.split("\n")
    else:
        r_to_add = to_add

    agent_p.close_driver()
    return r_to_add, source_url_dict, to_browse, browsed

def generate_links(url, promo_criteria, agent_s, link_agent, hops = 5):
    to_browse = []
    to_add = []
    browsed = [url]
    add_on = ""

    source_url_dict = {}

    agent_s.initialize_driver()
    agent_s.navigate_to_url(url)

    hop_i = 0
    tried_twice = []

    while hops>0:
        hop_i += 1
        print(f"Attempting hop {hop_i}")

        possible_links = agent_s.get_possible_links()
        try:
            link_hrefs = [link["href"] for link in possible_links]
        except:
            link_hrefs = []

        if (hop_i == 1) and len(link_hrefs) < 1:
            raise Exception("No links found on landing page")
        
        hits = 0
        if len(link_hrefs) >= 1 :
            link_resp = _sift_link_options(link_agent, link_hrefs, promo_criteria, add_on)
            for line in link_resp.split('\n'):
                if line.startswith('ADD:') and hop_i != 1:
                    new_url = line[4:].strip()
                    if new_url not in link_hrefs:
                        print(f"URL hallucination detected with url: {new_url}")
                    elif new_url not in to_add:
                        hits += 1
                        to_add.append(new_url)
                        source_url_dict[new_url] = url
                elif line.startswith('BROWSE:'):
                    new_url = line[7:].strip()
                    if new_url not in link_hrefs:
                        print(f"URL hallucination detected with url: {new_url}")
                    elif (new_url not in browsed) and (new_url not in to_browse):
                        hits += 1
                        to_browse.append(new_url)
                
        if hits == 0:
            agent_s.close_driver()
            time.sleep(10)
            agent_s.initialize_driver()
            time.sleep(5)
            if url not in tried_twice:
                to_browse += [url]
                tried_twice += [url]
        if len(to_browse) > 1:
          next_url_idx = random.randint(0, len(to_browse)-1)
        else:
          next_url_idx = 0
        _next_url = to_browse.pop(next_url_idx) if to_browse else None
        if _next_url:

            try:
                # try the playwright version, fallback to selenium version
                current_url = agent_s.page.url
            except:
                current_url = agent_s.driver.current_url
            if not _is_url_valid(link_agent, current_url, _next_url):
                next_url = _make_valid_url(link_agent, current_url, _next_url)
                print(f"URL {_next_url} was incomplete, attempting fixing to {next_url}")
            else:
                next_url = _next_url

            browsed.append(next_url)
            agent_s.navigate_to_url(next_url)
            url = next_url
            hops -= 1
            if len(to_add) >= 10:
                hops = 0
        else:
            if (len(to_add) < 5) and add_on == "":
                print("Entered contingency prompt stance")
                add_on = f"\nIf no relevant product or page links are found, you must find BROWSE links that are likely to lead to the products you're looking for."
            else:
                hops = 0
    if len(to_add)>4:
        links = "\n".join(to_add)
        link_resp = _product_link_filter(link_agent, links)
        r_to_add = link_resp.split("\n")
    else:
        r_to_add = to_add

    agent_s.close_driver()
    return r_to_add, source_url_dict, to_browse, browsed

# --------------------------- specific action tasks --------------------------- #
async def apply_customization(agent_p, shopping_agent, product_idx, cstm, options):
    before_img = f"{agent_p.path_stem}product_{product_idx}_cstm_{cstm}.png"
    await agent_p.take_screenshot(before_img) ; await asyncio.sleep(4)

    page_buttons = await agent_p.list_available_buttons()
    cstm_buttons_to_attempt = _get_customization_buttons(shopping_agent, cstm, options, page_buttons)
    # random.shuffle(cstm_buttons_to_attempt)

    starting_url = agent_p.page.url
    cstm_applied = False
    for btn in cstm_buttons_to_attempt:
        print(f"Attempting button {btn} for {cstm}")
        await agent_p.select_and_click_button(btn, only_one = False) ; await asyncio.sleep(4)

        if starting_url != agent_p.page.url:
            print(f"Failed to use button {btn} for {cstm} and went to another page, returning back.")
            await agent_p.navigate(starting_url)
            continue

        after_img = f"{agent_p.path_stem}product_{product_idx}_cstm_{cstm}_{btn}.png"
        await agent_p.take_screenshot(after_img) ; await asyncio.sleep(4)

        cstm_applied = _is_customization_applied(shopping_agent, cstm, before_img, after_img)

        if cstm_applied:
            print(f"Successfully used button {btn} for {cstm}")
            break
        else:
            print(f"Failed to use button {btn} for {cstm}")
    return cstm_applied


async def attempt_clearing_overlay(agent_p, shopping_agent, product_idx, fs_idx = 6, overlay_image_path = None):
    if overlay_image_path is None:
        overlay_image_path = f"{agent_p.path_stem}"+str(random.randint(0,100000))+".png"
        agent_p.take_screenshot(overlay_image_path)
    page_buttons = await agent_p.list_available_buttons()
    close_buttons = _get_overlay_close_buttons(shopping_agent, page_buttons, overlay_image_path)

    buttons_to_click = close_buttons
    pressed_buttons = []
    print(f"Buttons to click: {buttons_to_click}")
    starting_url = agent_p.page.url
    overlay_detected = False
    for button in buttons_to_click:
        if button in pressed_buttons:
            continue
        else:
            pressed_buttons += [button]

        print(f"Attempting to press {button}")
        await agent_p.select_and_click_button(button, only_one = False) ; await asyncio.sleep(4)

        # ensure that the url stayed the same
        if starting_url != agent_p.page.url:
            print('Accidently moved away from URL')
            await agent_p.navigate(starting_url) ; await asyncio.sleep(4)

        updated_image_attempt_button = f"{agent_p.path_stem}product_{product_idx}_{fs_idx}_{button}.png"
        await agent_p.take_screenshot(updated_image_attempt_button) ; await asyncio.sleep(4)
        overlay_detected = _has_overlay(shopping_agent, updated_image_attempt_button)
        if not overlay_detected:
            await agent_p.take_screenshot(f"{agent_p.path_stem}product_{product_idx}_cleared_overlay_{fs_idx}.png")
            return not(overlay_detected)
    return not(overlay_detected)


async def attempt_to_add_product(agent_p, shopping_agent, product_idx, img_suffix = "", quantity = 0):
    starting_url = agent_p.page.url
    page_buttons = await agent_p.list_available_buttons()

    cart_attempt_image = f"{agent_p.path_stem}product_{product_idx}_q{quantity}_beforeAdding.png"
    await agent_p.take_screenshot(cart_attempt_image) ; await asyncio.sleep(4)

    adding_btns = _get_add_to_cart_buttons(shopping_agent, page_buttons)
    random.shuffle(adding_btns)
    print(f"Identified buttons for adding product to cart: {adding_btns}")
    add_bttn_image = cart_attempt_image # This is just a fallback to be on the safer side
    for btn in adding_btns:
        print(f"Attempting button {btn} for adding product to cart")
        await agent_p.select_and_click_button(btn, only_one = True) ; await asyncio.sleep(4)

        if starting_url != agent_p.page.url:
            print(f"Failed to use button {btn} for adding product to cart and went to another page, returning back.")
            await agent_p.navigate(starting_url)
            continue

        add_bttn_image = f"{agent_p.path_stem}product_{product_idx}_q{quantity}_addtocart_{btn}.png"
        await agent_p.take_screenshot(add_bttn_image) ; await asyncio.sleep(4)

        product_added = _is_product_added(shopping_agent, cart_attempt_image, add_bttn_image)

        if product_added:
            print(f"Successfully added product!!")
            return product_added, add_bttn_image
        else:
            print(f"Failed to use button {btn} for adding product")
    return False, add_bttn_image


async def navigate_to_cart_checkout(agent_p, shopping_agent, scenario_ = "cart", starting_url = None):
    if starting_url:
        await agent_p.navigate(starting_url)
    else:
        starting_url = agent_p.page.url
    starting_page_img = f"{agent_p.path_stem}cart_buttons_s-{scenario_}.png"

    cart_img_path = starting_page_img

    await agent_p.take_screenshot(starting_page_img)

    page_buttons_full_all = await agent_p.get_buttons_full()
    page_links = await agent_p.get_possible_links()
    all_items = page_buttons_full_all + page_links

    nav_options = _get_cart_checkout_options(shopping_agent, all_items)
    print(f"Identified options for moving to cart/check s-{scenario_}: {nav_options}")
    try_idx = 0
    for option in nav_options:

        try_idx += 1

        if 'href' in option.keys():
            href = option['href']
            c_url = agent_p.page.url
            formed_link = _make_valid_url_oneoff( shopping_agent, c_url, href)
            await agent_p.navigate(formed_link)

        else:
            # TODO: to make sure replay doesn't break, remove keys: element and others
            option.pop('element', None)
            # await agent_p.select_and_click_button(option, only_one = True)
            await agent_p.click_button_by_attrs(option)

        # ideally should be at the cart/checkout page now
        await asyncio.sleep(8)
        cart_img_path = f"{agent_p.path_stem}possible_cartcheckout_page_s-{scenario_}_t{try_idx}.png"
        await agent_p.take_screenshot(cart_img_path)

        if _cart_or_checkout_reached(shopping_agent, starting_page_img, cart_img_path, scenario_):
            print(f"Successfully navigated to cart/checkout s-{scenario_} using option: {option}")
            return cart_img_path
            break
        else:
            print(f"Failed to navigate to cart/checkout s-{scenario_} using option: {option}")

    # In case of failure, you can include an option to return to home
    # await agent_p.navigate(starting_url)
    return cart_img_path
  
  
async def process_product(agent_p, shopping_agent, verifier_agent, product_idx, product_link, link_source, promo_criteria, added_products, attempt_overlay_clear = True):
    # navigate to product page
    await agent_p.navigate(product_link) ; await asyncio.sleep(4)
    await agent_p.take_screenshot(f"{agent_p.path_stem}product_{product_idx}_landing_page_initial.png") ; await asyncio.sleep(4)

    # ------------------------------- Clearing Overlays -------------------------------- #
    # During first run, we need to check and clear popups and overlays
    if attempt_overlay_clear:
        attempt_overlay_clear = False
        overlay_detected = _has_overlay(shopping_agent, f"{agent_p.path_stem}product_{product_idx}_landing_page_initial.png")

        overlay_image_path = f"{agent_p.path_stem}product_{product_idx}_landing_page_updated.png"
        await agent_p.take_screenshot(overlay_image_path) ; await asyncio.sleep(4)

        failsafe_attempts = 2
        while overlay_detected:
            await attempt_clearing_overlay(agent_p, shopping_agent, product_idx, failsafe_attempts, overlay_image_path)

            # Double check
            updated_image_attempt = f"{agent_p.path_stem}product_{product_idx}_landing_page_updated_{failsafe_attempts}.png"
            await agent_p.take_screenshot(updated_image_attempt) ; await asyncio.sleep(4)
            overlay_detected = _has_overlay(shopping_agent, updated_image_attempt)

            failsafe_attempts -= 1
            if failsafe_attempts <= 0:
                break
        # Currently making the assumption that overlay has been cleared, which may not necessarily be true.
    # ---------------------------------------------------------------------------------- #

    # -------------------------------- Getting Details --------------------------------- #
    # This assumes that there is no overlay
    landing_page_img_path = f"{agent_p.path_stem}product_{product_idx}_landing_page.png"
    await agent_p.take_screenshot(landing_page_img_path) ; await asyncio.sleep(4)

    page_text = await agent_p.page.evaluate("() => document.body.innerText")
    page_buttons = await agent_p.list_available_buttons()

    details_dict        = _get_product_details(shopping_agent, landing_page_img_path, page_text)
    custmizations_dict  = _get_product_options(shopping_agent, landing_page_img_path)
    essentials          = _get_essential_customizations(shopping_agent, landing_page_img_path, custmizations_dict)

    details_dict.update({
        'link': product_link,
        'source': link_source,
        'customizations': custmizations_dict,
        'essential_customizations': essentials
    })

    print(details_dict)
    # ---------------------------------------------------------------------------------- #


    # ------------------------------ Applicability Check ------------------------------- #

    applicable_bool, promo_resp = _is_product_applicable(verifier_agent, promo_criteria, details_dict)
    details_dict['applicability'] = promo_resp

    print(f"Product Applicability: {promo_resp}")

    if not applicable_bool:
        pass
        return added_products       # exit early

    # ---------------------------------------------------------------------------------- #


    # ----------------------------- Adding Customizations ------------------------------ #
    # Add an option so that applying customizations is done through function calling
    cstm_applied_dict = {}

    for cstm in custmizations_dict.keys():
        if not _customization_required(shopping_agent, promo_criteria, details_dict, added_products, cstm):
            print(f"{cstm} is not required for product {product_idx}")
            continue
        else:
            all_options = custmizations_dict[cstm]
            options = _customization_option_selections(shopping_agent, landing_page_img_path, promo_criteria, cstm, all_options)
            print(f"{cstm} is required for product {product_idx}, ideally set to {options}")

        cstm_applied_dict[cstm] = False
        if _is_preselected(shopping_agent, cstm, landing_page_img_path):
            print(f"{cstm} is already preselected for product {product_idx}")
            # continue
        cstm_applied_dict[cstm] = await apply_customization(agent_p, shopping_agent, product_idx, cstm, options)
        if not cstm_applied_dict[cstm]:
            # Try again once if failed (sometimes a button gets repressed an)
            cstm_applied_dict[cstm] = await apply_customization(agent_p, shopping_agent, product_idx+0.1, cstm, options)

    print(f"Resulting Customizations: {cstm_applied_dict}")

    # ---------------------------------------------------------------------------------- #


    # --------------------------------- Adding Product --------------------------------- #

    starting_url = agent_p.page.url
    attempting_add_product = True
    quantity = 0
    img_suffix = ""

    tries = 0

    while attempting_add_product:
        tries += 1
        attempting_add_product = False
        product_added, add_bttn_image = await attempt_to_add_product(agent_p, shopping_agent, product_idx, img_suffix = img_suffix, quantity = quantity, )
        if product_added:
            quantity += 1
            details_dict['quantity_added'] = 1 + details_dict.get('quantity_added', 0)
            added_products += [details_dict]
            quantity_required = _needs_more_quantity(shopping_agent, promo_criteria, details_dict)

            while quantity_required:
                print('Trying to add the product once again to increase quantity.')
                agent_p.navigate(starting_url)
                quantity_required = _needs_more_quantity(shopping_agent, promo_criteria, details_dict)
        else:
            failure_cause = _cause_of_failure(shopping_agent, add_bttn_image)
            print(f"Failure cause: {failure_cause}")
            if 'None' not in failure_cause.lower()[:6]:
                cstm = failure_cause.split(':', 1)[0]
                options = failure_cause.split(':', 1)[1]
                option_reset = await apply_customization(agent_p, shopping_agent, product_idx+tries/10, cstm, options)
                if option_reset:
                    img_suffix += cstm
                    attempting_add_product = True

        if tries >= 4:
            break
    # ---------------------------------------------------------------------------------- #
    return added_products




async def add_products_to_cart(agent_p, shopping_agent, verifier_agent, all_product_links, product_link_sources, promo_criteria, base_url):
    criteria_met = False
    product_idx = 0
    attempt_overlay_clear = True
    added_products = []

    # ----------------------------- Starting Control Flow ------------------------------ #

    # navigate to landing page
    await agent_p.__aenter__()
    await agent_p.navigate(base_url)
    await asyncio.sleep(20)
    await agent_p.take_screenshot(f"{agent_p.path_stem}landing_page_initial.png") ; await asyncio.sleep(4)

    product_links = all_product_links.copy()

    if len(product_links) < 1:
        if len(added_products) <= 0:
            raise Exception("No more product links to process")

    # ---------------------------------------------------------------------------------- #
    for product_idx in range(len(product_links)):
        # Getting product link
        product_link_idx = 0 if len(product_links) < 2 else random.randint(0, len(product_links)-1)
        product_link = product_links.pop(product_link_idx).strip()
        link_source = product_link_sources[product_link]

        added_products = await process_product(agent_p, shopping_agent, verifier_agent, product_idx, product_link, link_source, promo_criteria, added_products, attempt_overlay_clear)

        criteria_met, met_desc = _criteria_met(shopping_agent, promo_criteria, added_products)
        if criteria_met:
            print(f"Criteria Met?: {met_desc}")
            break

    return added_products


async def attempt_applying_promo(agent_p, shopping_agent, promo, cart_img_path):
    # ----------------------------- Attempting Promo Code ------------------------------ #
    all_text_fields = await agent_p.list_text_entry_fields()
    likely_promo_fields = _get_promo_fields(shopping_agent, all_text_fields, cart_img_path)

    if len(likely_promo_fields) <= 0:
        print("No reasonable promo entering fields found!!")
        return False, "", ""

        
    pre_promo_img = f"{agent_p.path_stem}prepromo.png"
    await agent_p.take_screenshot(pre_promo_img)

    for pf_idx, promo_field in enumerate(likely_promo_fields):
        print(f"Attempting promo field {pf_idx}: {promo_field}")
        promo_field.pop('element', None)
        await agent_p.add_text_to_field(promo_field, promo) ; await asyncio.sleep(4)

        post_promo_img = f"{agent_p.path_stem}postpromo_{pf_idx}.png"
        await agent_p.take_screenshot(post_promo_img)

        promo_entered = _is_promo_entered(shopping_agent, pre_promo_img, post_promo_img)
        if promo_entered:
            # attempt applying the promo
            print("Promo Entered!!")
            all_apply_buttons = await agent_p.get_buttons_full(include_elements = False)
            likely_apply_buttons = _get_apply_buttons(shopping_agent, all_apply_buttons, post_promo_img)

            if len(likely_apply_buttons) <= 0:
                print("No apply buttons found!!")
                return False, "", ""

            for ab_idx, apply_button in enumerate(likely_apply_buttons):
                print(f"Attempting apply button {ab_idx} for text field {pf_idx}: {apply_button}")
                apply_button.pop("element", None)
                await agent_p.click_button_by_attrs(apply_button, only_one = True) ; await asyncio.sleep(12)

                apply_promo_img = f"{agent_p.path_stem}promo-apply_{pf_idx}_{ab_idx}.png"
                await agent_p.take_screenshot(apply_promo_img)

                if _is_promo_applied(shopping_agent, post_promo_img, apply_promo_img):
                    print("Promo Applied!!!!")
                    return True, post_promo_img, apply_promo_img
                else:
                    print("Promo not applied")
            break
        else:
            print("Promo not entered")
    return False, "", ""
    # ---------------------------------------------------------------------------------- #




async def process_job(url, desc, promo, agent_s, agent_p, shopping_agent, verifier_agent, compute_fin = True):
    # agent_s = SeleniumAgent()
    # agent_p = PlaywrightAgent(headless=True)
 
    # shopping_agent = ChatGPTWrapper( default_model='o4-mini-2025-04-16', api_key = OPENAI_API_KEY )
    # verifier_agent = ChatGPTWrapper( default_model='o1-2024-12-17', api_key = OPENAI_API_KEY )

    url = format_url(url)
    stem = agent_p.path_stem
    # Phase 1
    promo_criteria, p1_v_resp = generate_criterion(stem, url, desc, promo, agent_s, shopping_agent, verifier_agent, DEBUG=True)
    print(promo_criteria)

    # Phase 2
    try:
        rta, sta, tb, br = generate_links(url, promo_criteria, agent_s, shopping_agent)
        if len(rta)< 2:
            raise Exception("Could not find sufficient links")
    except:
        print(f"Failed to generate links from agent_s, opting for agent_p")
        rta, sta, tb, br = await generate_links_fallback(url, promo_criteria, agent_p, shopping_agent)
        

    all_product_links = rta.copy()
    product_link_sources = sta.copy()
    base_url = url
    print(product_link_sources)

    # Phase 3
    added_products = await add_products_to_cart(agent_p, shopping_agent, verifier_agent, all_product_links, product_link_sources, promo_criteria, base_url)

    # Phase 4
    # -------------------------- Navigating to Cart/Checkout --------------------------- #
    cart_img_path = await navigate_to_cart_checkout(agent_p, shopping_agent, scenario_ = "cart", starting_url = base_url)

    if not _has_promo_field(shopping_agent, cart_img_path):
        # TODO: check if any information needs to be put in before moving to checkout; if yes, then enter info, else move to checkout page
        cart_img_path = await navigate_to_cart_checkout(agent_p, shopping_agent, scenario_ = "checkout")

    # check if there needs to be information put in, if yes then fill text fields and select from selectors, else find promo area
    # selectors = await agent_p.list_select_fields()
    # ---------------------------------------------------------------------------------- #
    promo_applied, pre_promo_img, apply_promo_img = await attempt_applying_promo(agent_p, shopping_agent, promo, cart_img_path)
    
    # closing
    if promo_applied:
        if compute_fin:
            fin_out = _final_outcome(verifier_agent, promo_criteria, pre_promo_img, apply_promo_img)
        else:
            fin_out = "Execution Succeeded"
    else:
      fin_out = "Execution Failed"

    return promo_applied, promo_criteria, added_products, fin_out, pre_promo_img, apply_promo_img
