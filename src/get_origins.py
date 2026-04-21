import requests
import os
import time
from requests.exceptions import HTTPError
from httplink import parse_link_header
import argparse



LINK_STORE_PATH = "../data/origins.txt"


def fetch_with_retry(link, params, max_retries=10, initial_delay=1, max_delay=60):
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        response = requests.get(link, params=params)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait = int(retry_after)
            else:
                wait = delay
            print(f"429 received (try {attempt}/{max_retries}), sleeping {wait}s...")
            time.sleep(wait)
            delay = min(delay * 2, max_delay)
            continue
        try:
            response.raise_for_status()
            return response
        except HTTPError:
            raise
    raise RuntimeError("Too many 429 responses; aborting")

def get_origins(file, link, query_params):
    try:
        while link is not None:
            response = fetch_with_retry(link, query_params)

            data = response.json()
            if isinstance(data, dict):
                entries = data.get("origins") or data.get("results") or data.get("data") or []
            else:
                entries = data

            if not isinstance(entries, list):
                raise ValueError(f"Unexpected JSON structure: {type(entries)}")

            for entry in entries:
                if not isinstance(entry, dict):
                    # skip malformed entries
                    continue

                url = entry.get("url")
                visits_url = entry.get("origin_visits_url")
                if url and visits_url:
                    file.write(f"{url},{visits_url}\n")

            next_link = None
            link_header = response.headers.get("Link")
            if link_header:
                parsed = parse_link_header(link_header)
                if parsed and "next" in parsed:
                    next_link = parsed["next"].target

            # save next resume position before iterating
            with open(LINK_STORE_PATH, "w") as link_file:
                link_file.write(next_link if next_link is not None else "")

            link = next_link

    except KeyboardInterrupt:
        with open(LINK_STORE_PATH, "w") as link_file:
            link_file.write(link if link else "")
        print("Interrupted, saved link:", link)

    except Exception as e:
        with open(LINK_STORE_PATH, "w") as link_file:
            link_file.write(link if link else "")
        print("Error, saved link:", link)
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output_file_name")
    parser.add_argument("-c", "--origins_per_request", type=int, default=10000)
    args = parser.parse_args()
    print_headings = False

    link = "https://archive.softwareheritage.org/api/1/origins/"

    if os.path.isfile(LINK_STORE_PATH):
        with open(LINK_STORE_PATH, "r") as link_file:
            saved = link_file.readline().strip()
            if saved:
                link = saved

    
    query_params = {
        "origin_count": args.origins_per_request
    }

    if not os.path.isfile(args.output_file_name):
        print_headings = True

    with open(args.output_file_name, "a") as fout:
        if print_headings:
            fout.write("url, origin_visits_url\n")

        get_origins(fout, link, query_params)