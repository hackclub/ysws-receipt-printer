print("Loading...")

import argparse
import base64
import datetime
import io
import time
from pyairtable import Api
import markdown
from dotenv import load_dotenv
import os
from typing import Dict, List
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from os import system
import qrcode


parser = argparse.ArgumentParser(
                    prog='Unified YSWS Printing Bot',
                    description='This program automatically checks the Unified YSWS database for new records. It can also print a specified number of records or those dated before, after, or between specified dates upon request.',
                    epilog='Made with love by Micha Albert.')
parser.add_argument('-c', '--count', help="The number of most recent records to print. If provided, this script will print this number of records and then exit.")
parser.add_argument('-a', '--after', help="The date in format YYYY-MM-DD at which to start printing records in chronological order. Can be combined with -b/--before to print all records between two dates.")
parser.add_argument('-b', '--before', help="The date in format YYYY-MM-DD at which to start printing records in REVERSE chronological order. Best used with -a/--after.")
parser.add_argument('-n', '--no_print', help="Do not print out generated documents. Used for debugging.", action="store_true")
parser.add_argument('-v', '--verbose', help="Verbode mode. Used for debugging.", action="store_true")
args = parser.parse_args()

if not args.count and not args.after and not args.before:
    print("Please specify at least one of -c/--count, -b/--before, or -a/--after. Exiting now.")
    exit()

PRINTING = not args.no_print
VERBOSE = args.verbose

if VERBOSE:
    print("Modules imported!")
    print("Setting up AirTable API...")

load_dotenv()

BASE = os.getenv("BASE")
TABLE = os.getenv("TABLE")
VIEW = os.getenv("VIEW")

airtable = Api(os.getenv("AIRTABLE_API_KEY"))

if VERBOSE:
    print("API set up!")

def check_for_updates(entries):
    updated_entries = airtable.base(BASE).table(TABLE).all(view=VIEW)
    new_entries = []
    if updated_entries != entries:
        for entry in updated_entries:
            if entry not in entries:
                new_entries.append(entry)
    return new_entries


def html_template(grant_info: Dict[str, str | List[str]]):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
    <p style="text-align: center; font-size: 65px; font-weight: bold; margin: 0">{grant_info["type"]}</p>
    <p style="margin: 0">{grant_info["created"]}</p>
    <br/>
    <img src="https://github.com/{grant_info["gh"]}.png" style="width: 35%; height: auto" />
    <p style="margin: 0; font-size: 150%">{grant_info["name"]}</p>
    <p style="margin: 0">{grant_info["location"]}</p>
    {f"<p style=\"margin: 0\">Age {grant_info["age"]}</p>" if grant_info["age"] != "" else ""}
    <br />
    {f"<p style=\"text-decoration-line: underline;font-weight: bold; margin: 0\">How did you hear about {grant_info["type"]}?<br/><div style=\"text-decoration-line: none; font-weight: regular\">{grant_info["ref"]}</div></p>" if grant_info["ref"] != "" else ""}

    {f"<p style=\"text-decoration-line: underline;font-weight: bold; margin: 0\">What are we doing well?<br/><div style=\"text-decoration-line: none; font-weight: regular\">{grant_info["good"]}</div></p>" if grant_info["good"] != "" else ""}

    {f"<p style=\"text-decoration-line: underline;font-weight: bold; margin: 0\">How can we improve?<br/><div style=\"text-decoration-line: none; font-weight: regular\">{grant_info["bad"]}</div></p>" if grant_info["bad"] != "" else ""}

    {f"<p style=\"text-decoration-line: underline;font-weight: bold; margin: 0\">Description<br/><div style=\"text-decoration-line: none; font-weight: regular\">{grant_info["description"]}</div></p>" if grant_info["description"] != "" else ""}

    {"\n".join(grant_info["screenshots"])}
    <div style="display: flex; justify-content: space-evenly; width: 100%; margin-top: 0">
        <div>
            {(f"""<p style="text-decoration-line: underline;font-weight: bold;text-align:center; margin-bottom: 0">Email</p>
            <img src="{grant_info["email_qr"]}" style="width: 75pt; height: auto"/>""") if grant_info["email_qr"] != "" else ""}
        </div>
        <div>
            {(f"""<p style="text-decoration-line: underline;font-weight: bold;text-align:center; margin-bottom: 0">Code URL</p>
            <img src="{grant_info["code_qr"]}" style="width: 75pt; height: auto"/>""") if grant_info["code_qr"] != "" else ""}
        </div>
    </div>
    <h6 style="text-align: center; margin-top: 0">This was printed at {grant_info["time"]}</h6>
</body>
</html>"""

if VERBOSE:
    print("Initalizing CSS renderer...")

font_config = FontConfiguration()

def pillow_image_to_base64_string(img):
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


css = CSS(
    string="""
@page {
    /* Very important - The recipts won't print correctly without these exact dimensions */
    size: 204pt 5668pt;
    margin: 0;
}

body {
    font-family: 'Roboto', sans-serif;
    margin-left: 0;
    margin-right: 0;
    margin-top: 0;
}"""
)

if VERBOSE:
    print("CSS renderer initalized!")
    print("Fetching all entries...")

entries = airtable.base(BASE).table(TABLE).all(view=VIEW)

if VERBOSE:
    print("All entries fetched!")


def get_before(entries, date: str):
    before_entries = []
    for entry in entries:
        if entry["fields"]["Approved At"] == date:
            before_entries.append(entry)
    return before_entries

def get_after(entries, date: str):
    after_entries = []
    for entry in entries:
        if entry["fields"]["Approved At"] == date:
            after_entries.append(entry)
    return after_entries




def print_entry(entry):
    description = ""  
    if "Description" in entry["fields"]:
        if VERBOSE:print("Has description")
        description = entry["fields"]["Description"]
    screenshots = []
    if "Screenshot" in entry["fields"]:
        if VERBOSE:print("Has screenshot")
        for screenshot in entry["fields"]["Screenshot"]:
            screenshots.append(f"<img src=\"{screenshot["url"]}\" style=\"width: 75%; height: auto; display: block; margin-left: auto; margin-right: auto\"/>")
    html = HTML(
        string=html_template(
            {
                "type": entry["fields"]["ID"].split("–")[0],
                "gh": entry["fields"]["GitHub Username"] if "GitHub Username" in entry["fields"] else "",
                "name": " ".join(entry["fields"]["ID"].split("–")[1:]),
                "age": entry["fields"]["Age When Approved"] if "Age When Approved" in entry["fields"] else "",
                "time": time.strftime("%A %b. %-d, %Y"),
                "location": f"{entry["fields"]["City"]}, {entry["fields"]["State / Province"]} - {entry["fields"]["Country"]}",
                "ref": entry["fields"]["How did you hear about this?"] if "How did you hear about this?" in entry["fields"] else "",
                "good": entry["fields"]["What are we doing well?"] if "What are we doing well?" in entry["fields"] else "",
                "bad": entry["fields"]["How can we improve?"] if "How can we improve?" in entry["fields"] else "",
                "description": description,
                "screenshots": screenshots,
                "email_qr": ('data:image/jpeg;base64,' + pillow_image_to_base64_string(qrcode.make(entry["fields"]["Email"]))) if "Email" in entry["fields"] else "",
                "code_qr": ('data:image/jpeg;base64,' + pillow_image_to_base64_string(qrcode.make(entry["fields"]["Code URL"]))) if "Code URL" in entry["fields"] else "",
                "created": datetime.datetime.fromisoformat(str(entry["fields"]["Created"])).strftime("%m/%d/%Y – %I:%M%p")

            }
        )
    )
    html.write_pdf("out.pdf", stylesheets=[css])
    if PRINTING:
        system("lp out.pdf")

def print_qty(qty: int):
    for entry in entries[:qty]:
        print_entry(entry)

def poll():
    while True:
        print("Polling Airtable...")
        updated_entries = check_for_updates(entries)
        if len(updated_entries) > 0:
            print("Found at least one new entry!")
        entries = airtable.base(BASE).table(TABLE).all(view=VIEW)
        for entry in updated_entries:
            print_entry(entry)
        time.sleep(7)

def main():
    print("Loaded!")
    if args.count:
        print_qty(int(args.count))
    elif args.before and not args.after:
        for entry in get_before(entries, args.before):
            print_entry(entry)
    elif args.after and not args.before:
        print('e')
        for entry in get_after(entries, args.after):
            print_entry(entry)
    elif args.before and args.after:
        for entry in dict(get_before(entries, args.before) & get_after(entries, args.after)):
            print_entry(entry)

if __name__ == "__main__":
    main()
