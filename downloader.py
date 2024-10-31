#!/usr/bin/env python3

import base64
import json
import os
import requests
import argparse
# import signal
import sys
import re
import logging
from datetime import datetime
import tqdm as progress_bar
from urllib.parse import quote

logging.basicConfig(level=logging.INFO)

CONF_PATH = os.path.join(os.getcwd(), "downloader.conf")
try:
    with open(CONF_PATH, encoding="utf-8-sig") as json_file:
        CONF = json.loads(json_file.read())
except FileNotFoundError:
    logging.info(f"Error: Configuration file not found at {CONF_PATH}")
    sys.exit(1)
except json.JSONDecodeError:
    logging.info(f"Error: Unable to decode JSON in configuration file {CONF_PATH}")
    sys.exit(1)

ACCOUNT_ID = CONF["zoom_oauth"]["account_id"]
CLIENT_ID = CONF["zoom_oauth"]["client_id"]
CLIENT_SECRET = CONF["zoom_oauth"]["client_secret"]

AUDIO_FILE_RECORDING_START_TIME_FORMAT = r'%Y-%m-%dT%H:%M:%SZ'
AUDIO_FILE_LANGUAGE_LIST = {
    "D-AR": "ar",
    "D-BG": "bg",
    "D-CS": "cs",
    "简体中文": "zh",
    "D-DA": "da",
    "Deutsch": "de",
    "D-EL": "el",
    "D-ET": "et",
    "English": "en",
    "Español": "es",
    "Français": "fr",
    "D-IW": "he",
    "D-HR": "hr",
    "D-HU": "hu",
    "D-HY": "hy",
    "D-ID": "id",
    "日本語": "ja",
    "D-LT": "lt",
    "D-LV": "lv",
    "D-NL": "nl",
    "D-NO": "no",
    "D-PL": "pl",
    "D-RO": "ro",
    "Русский": "ru",
    "D-SV": "sv",
    "Tagalog": "tl",
    "D-UK": "uk",
}

RECORDING_TYPE_VIDEO = "shared_screen_with_speaker_view"
RECORDING_TYPE_AUDIO_1 = "audio_only"
RECORDING_TYPE_AUDIO_2 = "audio_interpretation"

FILE_NAME_BY_RECORDING_TYPE = {
    RECORDING_TYPE_VIDEO: "source-video.{}",
    RECORDING_TYPE_AUDIO_1: "source-audio.{}",
    RECORDING_TYPE_AUDIO_2: "audio-{}.{}"
}

RECORDING_TIME_THRESHOLD = 30
RECORDING_TIME_FORMAT = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'

class Color:
    CYAN = "\033[96m"
    DARK_CYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"

class ZoomOAuth:
    @staticmethod
    def get_account_id():
        return CONF["zoom_oauth"]["account_id"]
    @staticmethod
    def get_client_id():
        return CONF["zoom_oauth"]["client_id"]
    @staticmethod
    def get_client_secret():
        return CONF["zoom_oauth"]["client_secret"]

def convert_response_to_json(response):
    try:
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error in API request: {e}")
        return None  # or raise an exception based on your error handling strategy
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON response: {e}")
        return None

def load_zoom_access_token():
    """ OAuth function, thanks to https://github.com/freelimiter
    """
    zoom_oauth = ZoomOAuth()
    client_cred = f"{zoom_oauth.get_client_id()}:{zoom_oauth.get_client_secret()}"
    client_cred_base64_string = base64.b64encode(client_cred.encode("utf-8")).decode("utf-8")
    response = requests.post(
        url=f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={zoom_oauth.get_account_id()}",
        headers = {
            "Authorization": f"Basic {client_cred_base64_string}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    response_json = convert_response_to_json(response)
    if response_json is None:
        return None
    try:
        return response_json["access_token"]
    except KeyError:
        logging.error(f"{Color.RED}### The key 'access_token' wasn't found.{Color.END}")
        return None

def get_recordings(recording_date, meeting_id):
    """ Get all recordings for a given date and meeting id"""
    response = requests.get(
        url=f"https://api.zoom.us/v2/users/me/recordings?from={recording_date}&meeting_id={meeting_id}",
        headers={
            "Authorization": f"Bearer {ZOOM_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
    )
    return convert_response_to_json(response)

def get_by_meeting_uuid(meeting_uuid):
    """ Get the recording for a given meeting uuid"""

    # double encode the UUID before making an API request
    # in case the UUID contains / or //
    encoded_meeting_uuid = quote(meeting_uuid, safe='')
    encoded_meeting_uuid = quote(encoded_meeting_uuid, safe='')
    
    response = requests.get(
        url=f"https://api.zoom.us/v2/meetings/{encoded_meeting_uuid}/recordings",
        headers={
            "Authorization": f"Bearer {ZOOM_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
    )

    return convert_response_to_json(response)

def prepare_downloads(recording):
    """ Prepare the list of downloads for a given recording
    :param recording: the recording data
    :return: a list of tuples (output_file_name, download_url)
    """
    downloads = []
    for download in recording["recording_files"]:
        recording_type = download["recording_type"]
        output_file_name = None
        file_extension = download["file_extension"]
        if recording_type in FILE_NAME_BY_RECORDING_TYPE:
            if recording_type == RECORDING_TYPE_AUDIO_2:
                audio_file_name = download["file_name"]
                # if the audio file name contains parentheses,
                # it means it's a translated audio file
                # else it's the source audio file
                audio_file_language_name = audio_file_name[audio_file_name.find("(")+1:audio_file_name.find(")")]
                if audio_file_language_name in AUDIO_FILE_LANGUAGE_LIST:
                    output_file_name = FILE_NAME_BY_RECORDING_TYPE.get(recording_type).format(AUDIO_FILE_LANGUAGE_LIST[audio_file_language_name], file_extension.lower())
            else:
                output_file_name = FILE_NAME_BY_RECORDING_TYPE.get(recording_type).format(file_extension.lower())
            # must append access token to download_url
            download_url = f"{download['download_url']}?access_token={ZOOM_ACCESS_TOKEN}"
            downloads.append((output_file_name, download_url))
        else:
            logging.warning(f"Unknown recording type '{recording_type}'. Skipping.")
    return downloads

def download_recording(download_url, full_filename):
    """ Download a recording file
    :param download_url: the download URL
    :param full_filename: the full filename including the download directory
    :return: True if the download was successful, False otherwise
    """
    try:
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        block_size = 32 * 1024  # 32 Kibibytes

        prog_bar = progress_bar.tqdm(total=total_size, unit="iB", unit_scale=True)
        with open(full_filename, "wb") as fd:
            for chunk in response.iter_content(block_size):
                prog_bar.update(len(chunk))
                fd.write(chunk)  # write video chunk to disk
        prog_bar.close()

    except requests.RequestException as e:
        logging.error(f"{Color.RED}### Error in download request: {e}{Color.END}")
    except Exception as e:
        logging.error(f"{Color.RED}### The video recording with filename '{full_filename}{Color.END}' ")

def time_delta(time1, time2):
    """ Calculate the time delta between two times
    :param time1: the first time
    :param time2: the second time
    :return: the time delta in minutes
    """
    try:
        time1 = datetime.strptime(time1, '%Y-%m-%dT%H:%M:%SZ')
        time2 = datetime.strptime(time2, '%Y-%m-%dT%H:%M:%SZ')
        return abs(int((time1 - time2).total_seconds()/60))
    except ValueError as e:
        logging.warning(f"{Color.RED}### Error parsing datetime strings: {e}{Color.END}")
        return None

def get_recording_uuid(recordings, recording_time):
    """ Get the recording uuid for a given recording time
    :param recordings: the list of recordings for a give date
    :param recording_time: the recording time
    :return: the recording uuid
    """
    for recording in recordings["meetings"]:
        recording_time_delta = time_delta(recording["start_time"], recording_time)
        if recording_time_delta is None:
            return None
        if recording_time_delta < RECORDING_TIME_THRESHOLD:
            return recording["uuid"]
    return None

def main():
    global ZOOM_ACCESS_TOKEN
    ZOOM_ACCESS_TOKEN = load_zoom_access_token()
    if ZOOM_ACCESS_TOKEN is None:
        logging.error("Failed to get zoom api access token")
        exit(1)
    parser = argparse.ArgumentParser(description='zoom video file downloader')
    parser.add_argument('--time', help='meeting video recoring time', required=True, type=str)
    parser.add_argument('--meetingid', help='zoom meeting id', required=True, type=str)
    parser.add_argument('--dir', help='Output file path', required=True)
    args = parser.parse_args()
    recording_time = args.time
    meeting_id = args.meetingid
    output_dir = args.dir
    if not re.match(RECORDING_TIME_FORMAT, recording_time):
        logging.warning("Please provide valid recording time")
        logging.warning("Recording time format: YYYY-MM-DDTHH:MM:SSZ")
        logging.warning("Example: 2021-01-01T12:00:00Z")
        exit(1)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
        exit(1)
    recording_date = recording_time.split("T")[0]
    # get list recordings for the day
    recordings = get_recordings(recording_date, meeting_id)
    if recordings is None:
        logging.warning(f"⚠ No recording with the meeting id {meeting_id} found for the given time {recording_date}")
        exit(1)
    # get meeting uuid for a recording time with a 30 minute error margin
    meeting_uuid = get_recording_uuid(recordings, recording_time)
    if meeting_uuid is None:
        logging.warning(f"⚠ No recording found for the given time {recording_date}")
        exit(1)
    # get list of downloads for the meeting uuid
    logging.info("==> Preparing downloads...")
    downloads = prepare_downloads(get_by_meeting_uuid(meeting_uuid))
    # download each recording
    for output_file_name, download_url in downloads:
        full_filename = os.sep.join([output_dir, output_file_name])
        truncated_url = download_url[0:64] + "..."
        logging.info(
            f"==> Downloading as {output_file_name}: "
            f"{output_dir}: {truncated_url}"
        )
        download_recording(download_url, full_filename)
    logging.info("Done!")   

if __name__ == "__main__":
    # tell Python to shutdown gracefully when SIGINT is received
    #signal.signal(signal.SIGINT, sys.exit(0))
    main()
