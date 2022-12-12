import base64
import config
from datetime import datetime
import json
import requests
import time

# Constants
VALID_RESULT_TYPES = ["interpretation", "screenshot", "knowledge", "statistics", "partial_knowledge",
                      "all_destination_details"]
RESULTS_WITH_BINARY_DATA = ["screenshot"]
TIME_DELAY_SECONDS = 10


def get_interpret_result(url):
    """Takes a URL that points to where an interpret result is stored and gets it. If there are screenshots,
       it will turn them back into the screenshot.
    """
    try:
        response = requests.get(url)
    except Exception as e:
        print(f"Failed to get interpret results from url: {e}")
        return
    try:
        data = response.json()
        if "results" not in data:
            print(f"No results.")
            return None
        for element in data["results"]:
            if type(element) != dict:
                print(f"Failed to get any meaningful results.")
                return None
            if element["type"] in VALID_RESULT_TYPES:
                current_type = element["type"]
                if current_type in element and element[current_type]:
                    if current_type in RESULTS_WITH_BINARY_DATA:
                        print(f"{current_type.upper()}: {element['message']}")
                        if current_type == "screenshot":
                            img_data = base64.b64decode(element[current_type])
                            time_string = datetime.now().strftime("%Y-%m-%d_%H%M%S.%fZ")
                            filename = f"{time_string}_{current_type}.png"
                            with open(filename, "wb") as fout:
                                fout.write(img_data)
                            print(f"Successfully saved {current_type} to {filename}")
                    else:
                        for info in element:
                            print(f"{info}: {element[info]}")
                        print(f"{'+' * 80}")
    except Exception as e:
        print(f"Failed to parse interpret result as JSON: {e}")
        return


def interpret_url(url_to_interpret, screenshot=False, all_dest_details=False):
    """Submits the URL for interpretation and any other requested functionality. Polls for the response and returns
       the data to the user when received.
    """
    results = None
    request_id = None
    url = config.SUBMIT_SITE_TO_INTERPRET
    payload = json.dumps({
        "url": f"{url_to_interpret}",
        "getScreenshot": screenshot,
        "allDestinationDetails": all_dest_details
    })
    headers = {
        "X-API-KEY": f"{config.API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.status_code != 200:
        print(f"Failed to interpret URL: {response.text}")
    try:
        data = response.json()
        if "request_id" not in data:
            print(f"Failed to interpret URL: {response.text}")
        else:
            request_id = data["request_id"]
    except Exception as e:
        print(f"Error encountered while interpreting URL: {e}")
    if request_id:
        url = f"{config.GET_INTERPRET_STATUS}{request_id}"
        headers = {"X-API-KEY": f"{config.API_KEY}"}
        payload = {}
        response = requests.request("GET", url, headers=headers, data=payload)
        if response.status_code != 200:
            print(f"Failed to get status for URL: {response.text}")
        else:
            failed = False
            while not results and not failed:
                time.sleep(TIME_DELAY_SECONDS)
                response = requests.request("GET", url, headers=headers, data=payload)
                if response.status_code != 200:
                    print(f"Failed to get status for URL: {response.text}")
                    failed = True
                else:
                    try:
                        data = response.json()
                        if "status" not in data:
                            print(f"Failed to interpret URL: {response.text}")
                            failed = True
                        else:
                            if data["status"] == "Failed":
                                print(f"Something failed while interpreting URL.")
                                failed = True
                            elif data["status"] == "Complete":
                                results = data["download_link"]
                            # Otherwise we're just waiting on an in progress interpretation.
                    except Exception as e:
                        print(f"Error encountered while interpreting URL: {e}")
                        failed = True
    return results
