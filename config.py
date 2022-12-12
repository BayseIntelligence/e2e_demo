import sensitive

API_KEY = sensitive.API_KEY

BAYSE_API_ENDPOINT = "https://api.bayse.io"
BAYSE_KB_API_URL = f"{BAYSE_API_ENDPOINT}/destinations"
BAYSE_INTERPRET_API_URL = f"{BAYSE_API_ENDPOINT}/site/interpret"
SUBMIT_SITE_TO_INTERPRET = f"{BAYSE_INTERPRET_API_URL}/request"
GET_INTERPRET_STATUS = f"{BAYSE_INTERPRET_API_URL}/status?request_id="
LABELING_BINARY_DIR = "labeling/"