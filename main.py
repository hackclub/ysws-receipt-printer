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
import markdown
import tempfile
import zipfile
import shutil

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

# repo: 'hackclub/onboard
# username 'zachlatta'
def get_first_matching_pr_for_user(repo, username):
  query = f"repo:{repo} is:pr is:merged author:{username}"
  
  url = "https://api.github.com/search/issues"
  headers = {
    "Accept": "application/vnd.github.v3+json",
  }
  
  params = {
    "q": query,
    "order": "desc",
    "per_page": 1  # Limit to the first result
  }
  
  response = requests.get(url, headers=headers, params=params)
  
  if response.status_code == 200:
    data = response.json()
    if data["items"]:
      first_pr = data["items"][0]

      return first_pr
    else:
      return None
  else:
    raise Exception(f"GitHub API error: {response.status_code}")

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

def get_gh_file_contents(owner, repo, file_path):
  try:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"

    response = requests.get(api_url)

    if response.status_code == 200:
      data = response.json()


      if data.get("encoding") == "base64":
        import base64
        content = base64.b64decode(data["content"])

        try:
          return content.decode("utf-8")
        except UnicodeDecodeError:
          return content # return raw bytes if it can't decide into a string (ex. if it's a zip file)
      else:
        raise Exception("File content not in base64 encoding.")
    else:
      raise Exception(f"GitHub API error: {response.status_code}")
  except Exception as e:
    raise ValueError(f"Error processing GitHub file: {e}")

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

def preprocess_onboard_project_description_markdown(md_content):
  # remove frontmatter
  md_content = re.sub(r'^---.*?---\s*', '', md_content, flags=re.DOTALL)

  # remote first top-level heading if it exists
  md_content = re.sub(r'(?:\n|^)# .+?\n', '', md_content, count=1, flags=re.MULTILINE)

  # Replace all headings (#, ##, ###, ####, #####) with ###
  md_content = re.sub(r'^#+', '###', md_content, flags=re.MULTILINE)

  return md_content

def render_pcb_svgs(owner, repo, gerber_zip_file_path):
  zip_bytes = get_gh_file_contents(owner, repo, gerber_zip_file_path)

  with tempfile.TemporaryDirectory() as temp_dir:
    with BytesIO(zip_bytes) as zip_bio:
      with zipfile.ZipFile(zip_bio) as zip_file:
        zip_file.extractall(path=temp_dir)
        extracted_filenames = zip_file.namelist()
        filename_extensions = [
          '.gbl', '.gbo', '.gbs', '.gtl', '.gto', '.gtp', '.gts', '.gbl',
          '.gbo', '.gbs', '.gko', '.gml', '.gpb', '.gpt', '.gts', '.gbr', '.drl'
        ]
        gbr_filenames = [file for file in extracted_filenames if file.lower().endswith(tuple(filename_extensions)) and not file.split('/')[-1].startswith('.')]

        # render gerber files to svg files - top.svg and bottom.svg
        subprocess.run(['tracespace', '-b.color.sm="rgba(128,00,00,0.75)"', *gbr_filenames], cwd=temp_dir)

        shutil.copyfile(f"{temp_dir}/top.svg", "onboard_board_preview.svg")
      
  return "onboard_board_preview.svg"

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
      matching_pr = get_first_matching_pr_for_user('hackclub/onboard', record['fields']['GitHub handle'])

      pdf_info = {
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
      }

      if matching_pr:
        pr_files = get_pull_request_files(matching_pr['html_url'])

        pdf_info['project_info']['name'] = matching_pr['title']
        pdf_info['project_info']['qr_codes']['Pull Request'] = matching_pr['html_url']

        readme_files = [ file for file in pr_files if file.lower().endswith('readme.md')]

        if len(readme_files) > 0:
          readme_contents = get_gh_file_contents('hackclub', 'onboard', readme_files[0])
          processed_contents = preprocess_onboard_project_description_markdown(readme_contents)
          html = markdown.markdown(processed_contents)
          pdf_info['project_info']['html_description'] = html
        
        gerber_files = [ file for file in pr_files if file.lower().endswith('.zip')]

        if len(gerber_files) > 0:
          pdf_info['project_info']['image_url'] = render_pcb_svgs('hackclub', 'onboard', gerber_files[0])

      generate_pdf(pdf_info, "receipt.pdf")

      print_pdf("receipt.pdf")

      processed_records.setdefault(f'{ONBOARD_BASE_ID}/{ONBOARD_TABLE_NAME}', {})[record_id] = True

      save_processed_records(processed_records)


if __name__ == "__main__":
   while True:
      print("Polling for new records...")
      process_new_records()
      time.sleep(POLL_INTERVAL)