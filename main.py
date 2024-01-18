import os
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from PIL import Image
from io import BytesIO
import subprocess
from datetime import datetime
import requests
import time
import base64
import io
import json
import pytz
import re

load_dotenv()

API_KEY = os.getenv('AIRTABLE_API_KEY')

SPRIG_BASE_ID = os.getenv('SPRIG_BASE_ID')
SPRIG_TABLE_NAME = os.getenv('SPRIG_TABLE_NAME')
SPRIG_AIRTABLE_ENDPOINT = f'https://api.airtable.com/v0/{SPRIG_BASE_ID}/{SPRIG_TABLE_NAME}?filterByFormula=NOT%28%7BHow%20did%20you%20hear%20about%20Sprig%3F%7D%20%3D%20%27%27%29&sort%5B0%5D%5Bfield%5D=Submitted+AT&sort%5B0%5D%5Bdirection%5D=desc'

ONBOARD_BASE_ID = os.getenv('ONBOARD_BASE_ID')
ONBOARD_TABLE_NAME = os.getenv('ONBOARD_TABLE_NAME')
ONBOARD_AIRTABLE_ENDPOINT = f'https://api.airtable.com/v0/{ONBOARD_BASE_ID}/{ONBOARD_TABLE_NAME}?&sort%5B0%5D%5Bfield%5D=Created&sort%5B0%5D%5Bdirection%5D=desc'

TIMEZONE = "America/New_York"
JSON_DB_PATH = 'processed_records.json'
POLL_INTERVAL = 30

headers = {
    'Authorization': f'Bearer {API_KEY}'
}

def format_str_datetime(value):
  tz = pytz.timezone(TIMEZONE)
  dt = datetime.fromisoformat(value)
  dt = dt.astimezone(tz)
  return dt.strftime("%m/%d/%Y – %I:%M%p")

def generate_pdf(data, filename="receipt.pdf"):
  env = Environment(loader=FileSystemLoader('.'))
  env.filters['format_str_datetime'] = format_str_datetime
  template = env.get_template('receipt_template.jinja')

  html_out = template.render(grant=data)

  HTML(string=html_out, base_url=".").write_pdf(filename)

def print_pdf(filename):
  printer_name = os.environ.get('DEST_RECEIPT_PRINTER')

  subprocess.run(["lp", "-d", printer_name, filename])

def load_processed_records():
  try:
    with open(JSON_DB_PATH, 'r') as file:
      return json.load(file)
  except FileNotFoundError:
    return {}

def save_processed_records(records):
  with open(JSON_DB_PATH, 'w') as file:
    json.dump(records, file)

def get_pull_request_files(pr_url):
  # Extract owner, repo, and pull request number from the URL
  match = re.search(r'github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
  if not match:
    raise ValueError("Invalid GitHub pull request URL")

  owner, repo, pull_number = match.groups()

  # GitHub API endpoint to get files of a pull request
  api_url = f'https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/files'

  # Make a GET request to the GitHub API
  response = requests.get(api_url)
  if response.status_code != 200:
    raise Exception(f"GitHub API responded with status code {response.status_code}")

  # Extract the file names from the response
  file_names = [file_info['filename'] for file_info in response.json()]
  return file_names

# converts ['games/DoNotConsumeEmptyBowls.js', 'games/img/Do Not Consume Empty Bowls (1).png', 'games/img/DoNotConsumeEmptyBowls.png']
# into "DoNotConsumeEmptyBowls"
def extract_sprig_game_name(pr_files):
  for path in pr_files:
    if path.startswith('games/') and path.endswith('.js'):
      # Split the path and get the last part (file name with extension)
      file_name_with_extension = path.split('/')[-1]
      # Remove the .js extension to get the game name
      game_name = file_name_with_extension[:-3]
      return game_name
  return None

def save_sprig_game_thumbnail(game_name):
  output_filename = 'sprig_game_thumbnail.png'
  url = f"https://sprig.hackclub.com/api/thumbnail?key={game_name}"
  response = requests.get(url)
  response_json = response.json()

  if response_json['kind'] == 'png':
    # If the data is a PNG, decode and save directly
    image_data = base64.b64decode(response_json['data'])
    image = Image.open(io.BytesIO(image_data))
    image.save(output_filename, 'PNG')
  else:
    # If the data is raw, process and save
    decoded_string = base64.b64decode(response_json['data'])
    image_data = bytearray(decoded_string)

    # Create an image from the raw data
    image = Image.frombytes('RGBA', (response_json['width'], response_json['height']), bytes(image_data))
    image.save(output_filename, 'PNG')

  return output_filename

def prepare_sprig_record(record):
  fields = record.get('fields', {})

  pr_url = fields.get("Pull Request", "")
  pr_files = get_pull_request_files(pr_url)

  game_name = extract_sprig_game_name(pr_files)

  project_info = {
    "name": game_name,
    "image_url": save_sprig_game_thumbnail(game_name),
    "qr_codes": {
      "Play Game": f"https://sprig.hackclub.com/gallery/{game_name}",
      "Pull Request": pr_url,
      "Email": f"mailto:{fields.get('Email', '')}"
    }
  }

  gh = fields.get("GitHub Username")
  tz = pytz.timezone(TIMEZONE)

  formatted_record = {
    "grant_type": "sprig",
    "datetime": record.get("createdTime", ""),
    "name": fields.get("Name", ""),
    "avatar_url": f"https://github.com/{gh}.png",  # Replace with actual field name for avatar URL
    "city": fields.get("City", ""),
    "state": fields.get("State or Province", ""),
    "country": fields.get("Country", ""),
    "age": fields.get("Age (years)", ""),
    "q_a": {
      "How did you hear about Sprig?": fields.get("How did you hear about Sprig?", ""),
      "Is this the first video game you’ve made?": fields.get("Is this the first video game you've made?", ""),
      "What are we doing well?": fields.get("What are we doing well?", ""),
      "How can we improve?": fields.get("How can we improve?", ""),
      "Are you in a club?": fields.get("In a club?", "")
    },
    "project_info": project_info
  }

  return formatted_record

def process_new_records():
  # Sprig
  processed_records = load_processed_records()
  response = requests.get(SPRIG_AIRTABLE_ENDPOINT, headers=headers)
  data = response.json()

  for record in data.get('records', []):
    record_id = record['id']

    if record_id not in processed_records.get(f'{SPRIG_BASE_ID}/{SPRIG_TABLE_NAME}', {}):
      print(f'New Record {record_id} Found! Printing')
      generate_pdf(prepare_sprig_record(record), "receipt.pdf")
      print_pdf("receipt.pdf")

      processed_records.setdefault(f'{SPRIG_BASE_ID}/{SPRIG_TABLE_NAME}', {})[record_id] = True

      save_processed_records(processed_records)

  # OnBoard

  processed_records = load_processed_records()
  response = requests.get(ONBOARD_AIRTABLE_ENDPOINT, headers=headers)
  data = response.json()

  for record in data.get('records', []):
    record_id = record['id']

    if record_id not in processed_records.get(f'{ONBOARD_BASE_ID}/{ONBOARD_TABLE_NAME}', {}):
      generate_pdf({
        "grant_type": "onboard",
        "datetime": record['createdTime'],
        "name": record['fields']['Full Name'],
        "avatar_url": f"https://github.com/{record['fields']['GitHub handle']}.png",
        "city": record['fields']['City (shipping address)'],
        "state": record['fields']['State'],
        "country": record['fields']['Country'],
        "age": str(datetime.now().year - datetime.strptime(record['fields']['Birthdate'], '%Y-%m-%d').year),
        "q_a": {
          "How did you hear about OnBoard?": record['fields']['How did you hear about OnBoard?'],
          "What are we doing well?": record['fields']['What we are doing well?'],
          "How can we improve?": record['fields']['How can we improve?'],
          "Is this the first PCB you've made?": record['fields']["Is this the first PCB you've made?"],
        },
        "project_info": {
          "name": "",  # Assuming the project name is not available in 'record'
          "image_url": "",
          "qr_codes": {
            "Email": f"mailto:{record['fields']['Email']}"
          },
        }
      }, "receipt.pdf")

      print_pdf("receipt.pdf")

      processed_records.setdefault(f'{ONBOARD_BASE_ID}/{ONBOARD_TABLE_NAME}', {})[record_id] = True

      save_processed_records(processed_records)


if __name__ == "__main__":
   while True:
      print("Polling for new records...")
      process_new_records()
      time.sleep(POLL_INTERVAL)