# Hack Club YSWS Receipt Printer

## About
This project will automatically print new YSWS (You Ship, We Ship) projects on a standard 80mm receipt printer. It is designed for internal use at Hack Club HQ, but when provided with the proper data and API keys, it can be used anywhere with some modifications.

## Prerequisites
* A modern version of Python 3 (Not sure what the cutoff is, but 3.11 works)
* An Airtable API key with access to a Table having the following fields:
    * ID, in the format "<ysws_type>–<name_of_submitter>"
    * Email
    * "How did you hear about this?"
    * "What are we doing well?"
    * "How can we improve?"
    * Age When Approved
    * Code URL
    * Screenshot (can handle multiple)
    * Description
    * GitHub Username
    * Approved At
    * Created (timestamp)
* A Receipt Printer


## Setup
1. Clone the repo
2. Install dependencies with `pip install -r requirements.txt`
    * You should probably use a virtual environment, but I won't go into detail here.
3. Create .env file and populate AIRTABLE_API_KEY, BASE, TABLE, and VIEW with your Airtable information

## Usage
```
Unified YSWS Printing Bot [-h] [-c COUNT] [-a AFTER] [-b BEFORE] [-n] [-v]

This program automatically checks the Unified YSWS database for new records. It can also print a specified number of records or those dated before,
after, or between specified dates upon request.

options:
  -h, --help            show this help message and exit
  -c COUNT, --count COUNT
                        The number of most recent records to print. If provided, this script will print this number of records and then exit.
  -a AFTER, --after AFTER
                        The date in format YYYY-MM-DD at which to start printing records in chronological order. Can be combined with -b/--before to
                        print all records between two dates.
  -b BEFORE, --before BEFORE
                        The date in format YYYY-MM-DD at which to start printing records in REVERSE chronological order. Best used with -a/--after.
  -n, --no_print        Do not print out generated documents. Used for debugging.
  -v, --verbose         Verbode mode. Used for debugging.
```

Enjoy!
