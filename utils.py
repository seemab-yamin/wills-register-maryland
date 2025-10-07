import requests
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
import warnings
import logging
from logging.handlers import RotatingFileHandler


def setup_logging():
    """
    Sets up logging configuration for the application.

    Configures:
    - Console handler for INFO level and above
    - File handler with rotation (5MB max, 3 backups)
    - Consistent log format
    - Root logger level set to INFO
    """
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Create file handler with rotation
    file_handler = RotatingFileHandler(
        "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Log the setup completion
    logger = logging.getLogger(__name__)
    logger.info("Logging setup completed")


def get_html(url: str):
    """
    Fetches and parses HTML content from a given URL.

    Args:
        url: The URL to fetch.

    Returns:
        A BeautifulSoup object representing the parsed HTML, or None if an error occurs.
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Fetching HTML from URL: {url}")

    # In requests, headers are passed as a dictionary.
    # The 'User-Agent' and 'Referer' from curl_setopt are also moved here.
    headers = {
        "Host": "registers.maryland.gov",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:78.0) Gecko/20100101 Firefox/78.0",
        "Referer": "https://registers.maryland.gov",
    }

    try:
        # Log and suppress the InsecureRequestWarning because SSL verification is turned off
        logger.warning(
            "Suppressing InsecureRequestWarning: SSL verification is disabled for this request."
        )
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

        response = requests.get(
            url,
            headers=headers,
            verify=False,
            allow_redirects=True,
            timeout=30,
        )
        # Check if the request was successful (status code 2xx)
        response.raise_for_status()
        logger.debug(f"Successfully fetched HTML from {url}")
        return response.text

    except requests.exceptions.RequestException as e:
        # This catches connection errors, timeouts, invalid URLs, etc.
        logger.error(f"Request error for {url}: {e}")
        return None


def get_parameters(soup, counter):
    """
    Parses the BeautifulSoup object to extract ASP.NET form parameters
    and the next page number for pagination.

    Args:
        soup (BeautifulSoup): The parsed HTML object of the current page.
        counter (int): The current request counter. Used to determine if
                       we should check for the end of pagination.

    Returns:
        dict: A dictionary containing the 'viewstate', 'viewstategenerator',
              'eventvalidation', and 'page_number'. Returns an empty dictionary
              if the required parameters are not found or if pagination has ended.
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Extracting parameters from page (counter: {counter})")

    try:
        # Extract the hidden form field values needed for the next request.
        # Using .get('value', '') is safer in case a tag is found but has no value.
        parameters = {
            "viewstate": soup.find("input", {"id": "__VIEWSTATE"}).get("value", ""),
            "viewstategenerator": soup.find(
                "input", {"id": "__VIEWSTATEGENERATOR"}
            ).get("value", ""),
            "eventvalidation": soup.find("input", {"id": "__EVENTVALIDATION"}).get(
                "value", ""
            ),
        }
    except AttributeError:
        # This occurs if one of the find() calls returns None (tag not found).
        # It indicates an invalid page or the end of scraping.
        logger.warning(f"Failed to extract form parameters (counter: {counter})")
        return {}

    page_number = ""

    # Find the <span> tag for the current page. It's inside a pager element.
    # soup.select_one is equivalent to find(..., 0)
    current_page_span = soup.select_one(".grid-pager span")

    if current_page_span:
        # The link to the next page is the next <a> tag sibling of the current page's <span>.
        # find_next_sibling('a') is robust as it skips over whitespace text nodes.
        next_page_link = current_page_span.find_next_sibling("a")

        if next_page_link and isinstance(next_page_link, Tag):
            href = next_page_link.get("href", "")

            # Replicate the string cleaning to isolate the page number from the javascript call.
            # BeautifulSoup un-escapes ' to ', so we replace based on that.
            page_number_str = href.replace(
                "javascript:__doPostBack('dgSearchResults$ctl24$ctl", ""
            )
            page_number_str = page_number_str.replace("','')", "")
            page_number = page_number_str.strip()

    parameters["page_number"] = page_number

    # This is the crucial end-of-pagination check.
    # If this isn't the first request AND we didn't find a next page link,
    # it means we are on the last page. Return empty dict to stop the loop.
    if counter > 1 and not page_number:
        logger.info(f"Reached end of pagination (counter: {counter})")
        return {}

    logger.debug(
        f"Successfully extracted parameters (counter: {counter}, page_number: {page_number})"
    )
    return parameters


def post_request(parameters, date_from, date_to, party_type, counter):
    """
    Sends a POST request to the Maryland Registers of Wills website to search for estates.

    Args:
        parameters (dict): Contains ASP.NET state values like 'viewstate'.
                           For pagination, it includes 'page_number'.
        date_from (str): The start date for the search (e.g., 'MM/DD/YYYY').
        date_to (str): The end date for the search.
        party_type (str): The party type to search for (e.g., 'DE').
        counter (int): Determines the request type. 1 for initial search,
                       other values for pagination.

    Returns:
        str: The HTML content of the response.
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Sending POST request (counter: {counter})")

    url = "https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:78.0) Gecko/20100101 Firefox/78.0",
        "content-type": "application/x-www-form-urlencoded",
    }

    if counter == 1:
        # Payload for the initial search
        payload = {
            "__VIEWSTATE": parameters["viewstate"],
            "__VIEWSTATEGENERATOR": parameters["viewstategenerator"],
            "__EVENTVALIDATION": parameters["eventvalidation"],
            "txtEstateNo": "",
            "txtLN": "",
            "cboCountyId": "",
            "txtFN": "",
            "txtMN": "",
            "cboStatus": "",
            "cboType": "",
            "DateOfFilingFrom": date_from,
            "DateOfFilingTo": date_to,
            "txtDOF": "",
            "cboPartyType": party_type,
            "cmdSearch": "Search",
        }
        logger.debug(
            f"Initial search payload - Date range: {date_from} to {date_to}, Party type: {party_type}"
        )
    else:
        # Payload for pagination
        payload = {
            "__EVENTTARGET": f"dgSearchResults$ctl24$ctl{parameters['page_number']}",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": parameters["viewstate"],
            "__VIEWSTATEGENERATOR": parameters["viewstategenerator"],
            "__EVENTVALIDATION": parameters["eventvalidation"],
        }
        logger.debug(f"Pagination payload - Page number: {parameters['page_number']}")

    try:
        # requests.post handles URL encoding of the payload dictionary
        response = requests.post(
            url,
            headers=headers,
            data=payload,
            verify=False,  # Equivalent to CURLOPT_SSL_VERIFYPEER/HOST = FALSE
            timeout=20,  # Equivalent to CURLOPT_CONNECTTIMEOUT
        )
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        logger.debug(f"POST request successful (counter: {counter})")
        return (
            response.text
        )  # Returns the raw HTML, similar to what str_get_html() would parse
    except requests.exceptions.RequestException as e:
        logger.error(f"POST request failed (counter: {counter}): {e}")
        return None


def scrape_page(parameters, case_urls, date_from, date_to, party_type, counter):
    """
    Scrapes a single page of search results, extracts detail page URLs,
    and gets the form parameters needed for the next page.

    Args:
        parameters (dict): Form data for the request (viewstate, etc.).
        case_urls (set): A set of URLs that have already been processed
                             to prevent duplicates. Using a set provides fast lookups.
        date_from (str): The start date for the search.
        date_to (str): The end date for the search.
        party_type (str): The party type for the search.
        counter (int): The request counter (1 for initial, >1 for pagination).

    Returns:
        tuple: A tuple containing (parameters, updated_case_urls).
               parameters (dict): The parameters needed for the next page request.
                                      Returns an empty dict if scraping is complete or fails.
               updated_case_urls (set): The updated set of scraped URLs.
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Scraping page (counter: {counter})")

    raw_html = post_request(parameters, date_from, date_to, party_type, counter)

    if not raw_html:
        # If the request failed, return empty params and the original URL set
        logger.error(f"Failed to fetch HTML content (counter: {counter})")
        return {}, case_urls

    soup = BeautifulSoup(raw_html, "html.parser")

    # Find all table rows within the results table using a CSS selector
    # This is equivalent to $html->find("#dgSearchResults tr")
    items = soup.select("#dgSearchResults tr")

    base_url = "https://registers.maryland.gov/RowNetWeb/Estates/"

    for item in items:
        # Find the first anchor tag <a> within the table row <tr>
        link_tag = item.find("a")

        # Ensure the tag and its 'href' attribute exist
        if link_tag and "href" in link_tag.attrs:
            item_href = link_tag["href"]

            # Filter out javascript links
            if "javascript:" not in item_href:
                # Construct the absolute URL safely
                item_url = urljoin(base_url, item_href)

                # Check if the URL has already been scraped
                if item_url not in case_urls:
                    case_urls.add(item_url)  # Add to the set of processed URLs

    # get_parameters should be a function that takes the soup object
    parameters = get_parameters(soup, counter)

    return parameters, case_urls


def get_element_text(soup, selector):
    """Safely finds an element by CSS selector and returns its stripped text."""
    element = soup.select_one(selector)
    if element:
        text = element.get_text(strip=True)
        # Remove extra whitespace and newline characters using regex
        return re.sub(r"\s+", " ", text).strip()
    return ""


def get_location_parts(location_string, address_key, city_key, state_key, zip_key):
    """Parses a location string into pr_address, city, state, and zip."""
    parts = dict.fromkeys([address_key, city_key, state_key, zip_key])
    if not location_string:
        return parts

    # Regex to find State and ZIP (e.g., MD 21201)
    state_zip_match = re.search(r"([A-Z]{2})\s+(\d{5}(?:-\d{4})?)", location_string)
    if state_zip_match:
        parts[state_key] = state_zip_match.group(1)
        parts[zip_key] = state_zip_match.group(2)
        if "-" in parts[zip_key]:
            parts[zip_key] = str(
                parts[zip_key].split("-")[0]
            )  # Keep only the first 5 digits
        # City is whatever comes before the state and zip
        city_part = location_string[: state_zip_match.start()].strip()
        if city_part.endswith(","):
            parts[city_key] = city_part[:-1].strip()
        else:
            parts[city_key] = city_part
        # Address is not clearly separated, often missing, so we'll leave it blank
        # as it's not present in the small tag.
    else:
        # Fallback if regex fails
        parts[address_key] = location_string

    # split the city into address and city using last comma if city exists and has comma
    if parts.get(city_key):
        address_city = parts[city_key].split(",", -1)
        if len(address_city) >= 2:
            parts[address_key] = ",".join(address_city[:-1])
            parts[city_key] = address_city[-1].strip()
    return parts


def scrape_single(item_url):
    """
    Scrapes a single estate detail page, extracts all information,
    and returns structured data with the new field names.

    Args:
        item_url (str): The URL of the detail page to scrape.

    Returns:
        list: A list of dictionaries containing the scraped data with updated field names.
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Scraping single item: {item_url}")

    master_data = []
    raw_html = get_html(item_url)
    if not raw_html:
        logger.error(f"Failed to fetch HTML for {item_url}")
        return []
    soup = BeautifulSoup(raw_html, "html.parser")

    # --- 1. Extract Common Information ---
    case_data = {
        "case_number": "",
        "estate_number": get_element_text(soup, "#lblEstateNumber"),
        "county_jurisdiction": get_element_text(soup, "td:contains('Estate Record')"),
        "date_of_filing": get_element_text(soup, "#lblDateOfFiling"),
        "date_of_will": get_element_text(soup, "#lblDateOfWill"),
        # "time": get_element_text(soup, "#lblDateOpened"),
        "type": get_element_text(soup, "#lblType"),
        "status": get_element_text(soup, "#lblStatus"),
        "will": get_element_text(soup, "#lblWill"),
        "decedent": get_element_text(soup, "#lblName"),
        "date_of_death": get_element_text(soup, "#lblDateOfDeath"),
        "decedent_address": "",
        "executor_first_name": "",
        "executor_last_name": "",
        "administrator_first_name": "",
        "administrator_last_name": "",
        "pow_first_name": "",
        "pow_last_name": "",
        "subscriber_first_name": "",
        "subscriber_last_name": "",
        # "decedent_alias": get_element_text(soup, "#lblAliases"),
        "url": item_url,
    }

    # Extract County
    if case_data.get("county_jurisdiction"):
        county_part = case_data["county_jurisdiction"].split("(")[1]
        case_data["county_jurisdiction"] = (
            county_part.replace("County)", "").replace(")", "").strip()
        )
    else:
        case_data["county_jurisdiction"] = ""

    # --- 2. Extract Attorney Information ---
    attorney_data = {
        "attorney_first_name": "",
        "attorney_ last_name": "",
        "attorney_address": "",
        "attorney_city": "",
        "attorney_state": "",
        "attorney_zip": "",
    }
    attorney_name = get_element_text(soup, "#lblAttorney")
    if attorney_name:
        name_parts = attorney_name.split("[")[0].strip().split()
        if len(name_parts) >= 2:
            attorney_data["attorney_first_name"] = name_parts[0]
            attorney_data["attorney_last_name"] = name_parts[
                -1
            ]  # Use last part for robustness

        attorney_location_str = get_element_text(soup, "#lblAttorney small")
        loc_parts = get_location_parts(
            attorney_location_str,
            "attorney_address",
            "attorney_city",
            "attorney_state",
            "attorney_zip",
        )
        attorney_data.update(loc_parts)

    reps_container = soup.select_one("#lblPersonalReps")
    # Use decode_contents to get inner HTML and split by <br>, same as PHP
    if reps_container and reps_container.decode_contents():
        rep_html_chunks = reps_container.decode_contents().split("<br/>")

        for chunk in rep_html_chunks:
            if not chunk.strip() or "[" not in chunk:
                continue

            # Parse the individual HTML chunk for this representative
            rep_soup = BeautifulSoup(chunk, "html.parser")

            # Personal Rep Name Parsing
            name_str = rep_soup.get_text(strip=True).split("[")[0].strip()
            name_parts = name_str.split()
            pr_first_name, pr_middle_name, pr_last_name = "", "", ""
            if len(name_parts) > 2:
                pr_first_name, pr_middle_name, pr_last_name = (
                    name_parts[0],
                    name_parts[1],
                    " ".join(name_parts[2:]),
                )
            elif len(name_parts) == 2:
                pr_first_name, pr_last_name = name_parts[0], name_parts[1]
            elif len(name_parts) == 1:
                pr_first_name = name_parts[0]

            # Personal Rep Location Parsing
            pr_loc_str = get_element_text(rep_soup, "small")
            pr_loc_parts = get_location_parts(
                pr_loc_str, "pr_address", "pr_city", "pr_state", "pr_zip"
            )

            # Write one row per representative
            row = {
                **case_data,
                "pr_first_name": pr_first_name,
                "pr_middle_name": pr_middle_name,
                "pr_last_name": pr_last_name,
                **pr_loc_parts,
                **attorney_data,
            }
            master_data.append(row)  # Append to the master data list
    else:
        # If no reps are found, write a single line with available info
        row = {
            **case_data,
            **attorney_data,
        }
        master_data.append(row)  # Append to the master data list

    logger.debug(f"Successfully scraped {len(master_data)} records from {item_url}")
    return master_data
