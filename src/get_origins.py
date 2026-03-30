import requests
import os
from httplink import parse_link_header
import argparse



def get_origins(file, link, query_params):
    try:
        while not link is None:
            response = requests.get(link, params=query_params)


            for entry in response.json():
                file.write(entry["url"] + "," + entry["origin_visits_url"] + "\n")
    
            link = parse_link_header(response.headers["Link"])["next"].target
    except KeyboardInterrupt:
        with open("data/link_store.txt", "w") as link_file:
            link_file.write(link)
        
        print("Exiting, saved link:", link)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output_file_name")
    parser.add_argument("-c", "--origins_per_request", type=int, default=10000)
    args = parser.parse_args()
    print_headings = False

    link = "https://archive.softwareheritage.org/api/1/origins/"

    if os.path.isfile("data/link_store.txt"):
        with open("data/link_store.txt", "r") as link_file:
            link = link_file.readline()

    
    query_params = {
        "origin_count": args.origins_per_request
    }

    if not os.path.isfile(args.output_file_name):
        print_headings = True

    with open(args.output_file_name, "a") as fout:
        if print_headings:
            fout.write("url, origin_visits_url\n")

        get_origins(fout, link, query_params)