#!/usr/bin/env python3

# system libraries
import base64
import json
import os
#import re as regex
import signal
import sys as system
from datetime import datetime

# installed libraries
import argparse
import dateutil.parser as parser
import pathvalidate as path_validate
import requests
import tqdm as progress_bar
import ffmpeg
from pydub import AudioSegment
from moviepy.editor import VideoFileClip
from youtube_upload.client import YoutubeUploader

CONF_PATH = "downloader.conf"
with open(CONF_PATH, encoding="utf-8-sig") as json_file:
    CONF = json.loads(json_file.read())

ACCOUNT_ID = CONF["zoom_oauth"]["account_id"]
CLIENT_ID = CONF["zoom_oauth"]["client_id"]
CLIENT_SECRET = CONF["zoom_oauth"]["client_secret"]

DOWNLOAD_DIRECTORY = 'downloads'

YOUTUBE_CATEGORY = "27"
YOUTUBE_CLIENT_ID = CONF["youtube_oauth"]["client_id"]
YOUTUBE_CLIENT_SECRET = CONF["youtube_oauth"]["client_secret"]
GOOGLE_OAUTH_ACCESS_TOKEN = CONF["youtube_oauth"]["access_token"]
GOOGLE_OAUTH_REFRESH_TOKEN = CONF["youtube_oauth"]["refresh_token"]

AUDIO_FILE_RECORDING_START_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
AUDIO_FILE_LANGUAGE_LIST = {
    "D-RO": "ro", 
    "D-NL": "nl", 
    "D-HY": "hy",
    "D-EL": "el",
    "D-UK": "uk",
    "D-LV": "lv",
    "D-AR": "ar",
    "D-LT": "lt",
    "D-HR": "hr",
    "D-DA": "da",
    "D-ET": "et",
    "D-PL": "pl",
    "D-SV": "sv",
    "D-IW": "iw",
    "D-HU": "hu",
    "D-BG": "bg",
    "D-NO": "no",
    "D-CS": "cs",
    "Deutsch": "de",
    "Русский": "ru",
    "English": "en",
    "Español": "es",
    "Français": "fr",
    "日本語": "ja",
}


class Color:
    CYAN = "\033[96m"
    DARK_CYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def load_access_token():
    """ OAuth function, thanks to https://github.com/freelimiter
    """
    url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ACCOUNT_ID}"

    client_cred = f"{CLIENT_ID}:{CLIENT_SECRET}"
    client_cred_base64_string = base64.b64encode(client_cred.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Basic {client_cred_base64_string}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = json.loads(requests.request("POST", url, headers=headers).text)

    global ACCESS_TOKEN
    global AUTHORIZATION_HEADER

    try:
        ACCESS_TOKEN = response["access_token"]
        AUTHORIZATION_HEADER = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        #print(ACCESS_TOKEN)
    except KeyError:
        print(f"{Color.RED}### The key 'access_token' wasn't found.{Color.END}")

def format_filename(params):
    file_name = None
    file_extension = params["file_extension"]
    recording_type = params["recording_type"]

    if recording_type == "shared_screen_with_speaker_view":
        file_name = "source-video"
    elif recording_type == "audio_interpretation":
        file_name = "source-audio"
    return (
        f"{file_name}.{file_extension.lower()}"
    )

def get_downloads(recording):
    if not recording.get("recording_files"):
        raise Exception
    downloads = []
    for download in recording["recording_files"]:
        recording_type = download["recording_type"]
        if recording_type == "shared_screen_with_speaker_view" or recording_type == "audio_interpretation":
            output_file_name = None
            directory_name = "."
            file_extension = download["file_extension"]
            if recording_type == "shared_screen_with_speaker_view":
                output_file_name = f"source-video.{file_extension.lower()}"
            if recording_type == "audio_interpretation":
                audio_file_name = download["file_name"]
                audio_file_language_name = audio_file_name[audio_file_name.find("(")+1:audio_file_name.find(")")]
                output_file_name = f"source-audio.{file_extension.lower()}"
                if audio_file_language_name in AUDIO_FILE_LANGUAGE_LIST:
                    directory_name = f"audio-{AUDIO_FILE_LANGUAGE_LIST[audio_file_language_name]}"
            # must append access token to download_url
            download_url = f"{download['download_url']}?access_token={ACCESS_TOKEN}"
            downloads.append((download["recording_start"], output_file_name, directory_name, download_url))
    return downloads

def download_recording(download_url, download_dir, full_filename):

    os.makedirs(download_dir, exist_ok=True)

    response = requests.get(download_url, stream=True)

    # total size in bytes.
    total_size = int(response.headers.get("content-length", 0))
    block_size = 32 * 1024  # 32 Kibibytes

    # create TQDM progress bar
    prog_bar = progress_bar.tqdm(total=total_size, unit="iB", unit_scale=True)
    try:
        with open(full_filename, "wb") as fd:
            for chunk in response.iter_content(block_size):
                prog_bar.update(len(chunk))
                fd.write(chunk)  # write video chunk to disk
        prog_bar.close()

        return True

    except Exception as e:
        print(
            f"{Color.RED}### The video recording with filename '{filename}' "
        )
        # print(
        #     f"{Color.RED}### The video recording with filename '{filename}' for user with email "
        #     f"'{email}' could not be downloaded because {Color.END}'{e}'"
        # )

        return False

def handle_graceful_shutdown(signal_received, frame):
    print(f"\n{Color.DARK_CYAN}SIGINT or CTRL-C detected. system.exiting gracefully.{Color.END}")

    system.exit(0)

def get_by_meeting_id(meeting_id):
    response = requests.get(
        url=f"https://api.zoom.us/v2/meetings/{meeting_id}/recordings",
        headers=AUTHORIZATION_HEADER
    )
    recordings_data = response.json()
    return recordings_data

# Now assigning audio and video for mix is by rounding off duration.
# But this is quite inaccurate. The best way is assigning by file name
# TODO: 1. Define audio and video for mix
#       2. Define output file name 
# def mix_audio_and_video(audio_files, video_files):
#     output_videos = []
#     audio_file_list = dict()
#     video_file_list = dict()
#     for audio_file in audio_files:
#         audio = AudioSegment.from_file(audio_file)
#         duration_in_seconds = len(audio) / 1000.0
#         duration_round_off = round(round(duration_in_seconds), -1)
#         if duration_round_off in audio_file_list:
#             audio_file_list[duration_round_off].append(audio_file)
#         else:
#             audio_file_list[duration_round_off] = [audio_file]
#     for video_file in video_files:
#         video_clip = VideoFileClip(video_file)
#         duration = video_clip.duration
#         video_clip.close()
#         duration_round_off = round(round(duration), -1)
#         if duration_round_off in video_file_list:
#             video_file_list[duration_round_off].append(video_file)
#         else:
#             video_file_list[duration_round_off] = [video_file]
#     for idx, duration in enumerate(audio_file_list):
#         for audio_idx, audio_file in enumerate(audio_file_list[duration]):
#             input_audio = ffmpeg.input(audio_file)
#             for video_idx, video_file in enumerate(video_file_list[duration]):
#                 input_video = ffmpeg.input(video_file)
#                 output_video = video_file[:video_file.rfind('.')] + "-" + str(duration) + "-" + str(video_idx) + "-" + str(audio_idx) + ".mp4"
#                 ffmpeg.concat(input_video, input_audio, v=1, a=1).output(output_video).run()
#                 output_videos.append(output_video)
#         # if idx == 1:
#         #     break
#     return output_videos

# TODO: Define option information
# def upload_videos_to_youtube(video_files):
#     uploader = YoutubeUploader(YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET)
#     uploader.authenticate(access_token=GOOGLE_OAUTH_ACCESS_TOKEN, refresh_token=GOOGLE_OAUTH_REFRESH_TOKEN)
#     for idx, video_file in enumerate(video_files):
#         # Video options
#         options = {
#             "title" : "TestVideo"+str(idx), # The video title
# #            "description" : "Example description", # The video description
# #            "tags" : ["tag1", "tag2", "tag3"],
#             "categoryId" : YOUTUBE_CATEGORY,
#             "privacyStatus" : "public", # Video privacy. Can either be "public", "private", or "unlisted"
# #            "thumbnailLink" : "https://cdn.havecamerawilltravel.com/photographer/files/2020/01/youtube-logo-new-1068x510.jpg" # Optional. Specifies video thumbnail.
#         }

#         # upload video
#         uploader.upload(video_file, options)
#     uploader.close()

# ################################################################
# #                        MAIN                                  #
# ################################################################

def main():
    # clear the screen buffer
    # os.system('cls' if os.name == 'nt' else 'clear')

    load_access_token()

    parser = argparse.ArgumentParser(description='zoom video file downloader')
    parser.add_argument('--time', help='meeting video recoring time')
    parser.add_argument('--meetingid', help='zoom meeting id')
    parser.add_argument('--dir', help='Output file path')
    args = parser.parse_args()
    recording_time = args.time
    meeting_id = args.meetingid
    output_dir = args.dir

    recording = get_by_meeting_id(meeting_id)
    try:
        downloads = get_downloads(recording)
        for recording_start, output_file_name, directory_name, download_url in downloads:
            if output_dir == "":
                output_dir = DOWNLOAD_DIRECTORY
            if recording_time == "":
                recording_time = datetime.now()
            if datetime.strptime(recording_start, AUDIO_FILE_RECORDING_START_TIME_FORMAT) > datetime.fromisoformat(recording_time):
                dl_dir = os.sep.join([output_dir, directory_name])
                full_filename = os.sep.join([dl_dir, output_file_name])
                truncated_url = download_url[0:64] + "..."
                print(
                    f"==> Downloading as {output_file_name}: "
                    f"{directory_name}: {truncated_url}"
                )
                download_recording(download_url, dl_dir, full_filename)
            else:
                print(f"{directory_name}"+"/"+f"{output_file_name}'s recording time {recording_start} is later than {recording_time}")
    except Exception:
        print(
              f"{Color.RED}### Recording files missing for call with id {Color.END}"
              f"'{recording['id']}'\n"
             )
    
    
    # audio_files = []
    # video_files = []
    # for file_type, file_extension, download_url, recording_type, recording_id in downloads:
    #     success = False
    #     if recording_type != 'incomplete':
    #         file_name, folder_name = (
    #             format_filename({
    #                 "file_type": file_type,
    #                 "recording": recording,
    #                 "file_extension": file_extension,
    #                 "recording_type": recording_type,
    #                 "recording_id": recording_id
    #                 })
    #             )
    #         dl_dir = os.sep.join([DOWNLOAD_DIRECTORY, folder_name])
    #         sanitized_download_dir = path_validate.sanitize_filepath(dl_dir)
    #         sanitized_filename = path_validate.sanitize_filename(file_name)
    #         full_filename = os.sep.join([sanitized_download_dir, sanitized_filename])
    #         _, file_extension = os.path.splitext(file_name)
    #         if file_extension == ".m4a":
    #             audio_files.append(full_filename)
    #         if file_extension == ".mp4":
    #             video_files.append(full_filename)
    #         # truncate URL to 64 characters
    #         truncated_url = download_url[0:64] + "..."
    #         print(
    #             f"==> Downloading as {recording_type}: "
    #             f"{recording_id}: {truncated_url}"
    #         )
    #         success |= download_recording(download_url, file_name, sanitized_download_dir, full_filename)

    #     else:
    #         print(
    #             f"{Color.RED}### Incomplete Recording for "
    #             f"recording with id {Color.END}'{recording_id}'"
    #         )
    #         success = False
    # try:
    #     mixed_video_files = mix_audio_and_video(audio_files, video_files)
    # except Exception as error:
    #     print(
    #           f"{Color.RED}### Mixing audio and video files has failed. {Color.END}", error
    #          )
    # try:
    #     upload_videos_to_youtube(mixed_video_files)
    # except Exception as error:
    #     print(
    #           f"{Color.RED}### Uploading video files has failed. {Color.END}", error
    #          )

    # print(f"\n{Color.BOLD}{Color.GREEN}*** All done! ***{Color.END}")
    # save_location = os.path.abspath(DOWNLOAD_DIRECTORY)
    # print(
    #     f"\n{Color.BLUE}Recordings have been saved to: {Color.UNDERLINE}{save_location}"
    #     f"{Color.END}\n"
    # )

if __name__ == "__main__":
    # tell Python to shutdown gracefully when SIGINT is received
    signal.signal(signal.SIGINT, handle_graceful_shutdown)

    main()
