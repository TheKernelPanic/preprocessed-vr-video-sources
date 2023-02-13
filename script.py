import time
import uuid
import os
import pathlib
from dotenv import load_dotenv
from MySQLdb import _mysql
import shutil
import ffmpeg
import subprocess
import math

load_dotenv()

hosted_on_id = int(input("Host Id: "))

source_path = os.path.join(os.getcwd(), "source")
output_path = os.path.join(os.getcwd(), "output")
temporary_path = os.path.join(os.getcwd(), "tmp")

# Database server connection

database_connection = _mysql.connect(
    host=os.getenv("MYSQL_DATABASE_HOST"),
    user=os.getenv("MYSQL_DATABASE_USER"),
    password=os.getenv("MYSQL_DATABASE_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE_NAME"),
)

# Listing source directory and assign uuid

source_files = []
for entry in os.scandir(source_path):
   if pathlib.Path(os.path.join(os.getcwd(), entry.name)).suffix != '.mp4':
       continue
   source_files.append({
       'original_filename': entry.name,
       'uuid': str(uuid.uuid4())
   })


# Check existing vr videos on database by original filename
for source_file in source_files:
    database_connection.query(
        f'SELECT uuid FROM vr_video WHERE original_filename = \'{source_file["original_filename"]}\' LIMIT 1'
    )
    result = database_connection.store_result()
    if len(result.fetch_row()) > 0:
        raise Exception("Existing file with name: " + source_file["original_filename"])

# Move and rename files
for source_file in source_files:
    os.mkdir(os.path.join(output_path, 'vr-video', source_file["uuid"]))
    shutil.move(os.path.join(source_path, source_file["original_filename"]), os.path.join(output_path, 'vr-video', source_file["uuid"], "video.mp4"))
    with open(os.path.join(output_path, 'vr-video', source_file["uuid"], 'metadata.txt'), 'w') as file:
        file.write(source_file["original_filename"])
    file.close()

# Read property files
vr_videos_properties = []
for source_file in source_files:
    path_file = os.path.join(output_path, 'vr-video', source_file['uuid'], 'video.mp4')
    probe = ffmpeg.probe(path_file)

    vr_videos_properties.append({**{
        'duration_seconds': math.floor(float(probe['format']['duration'])),
        'file_size': math.floor(float(probe['format']['size'])),
        'width': probe['streams'][0]['width'] if 'width' in probe['streams'][0] else 0,
        'height': probe['streams'][0]['height'] if 'height' in probe['streams'][0] else 0,
        'date': time.strftime("%Y-%m-%d %H:%M:%S", time.strptime(time.ctime(os.path.getmtime(path_file))))
    }, **source_file})

del source_files


# Create images

def format_to_hhmmss(seconds):
    hours = seconds // (60*60)
    seconds %= (60*60)
    minutes = seconds // 60
    seconds %= 60
    return "%02i:%02i:%02i" % (hours, minutes, seconds)


def get_times(duration):
    list_times = []
    max_times = 12
    amount_seconds = 0
    i = 1
    while i <= max_times:
        if 1 < i < max_times:
            amount_seconds += math.floor(duration / 12)
            list_times.append(format_to_hhmmss(amount_seconds))
        i += 1
    return list_times


for vr_video_properties in vr_videos_properties:
    path_file = os.path.join(output_path, 'vr-video', vr_video_properties['uuid'], 'video.mp4')  

    if os.path.isdir(os.path.join(temporary_path, vr_video_properties['uuid'])) is False:
        os.mkdir(os.path.join(temporary_path, vr_video_properties['uuid']))

    vr_video_properties['images'] = []
    for index, time_format in enumerate(get_times(vr_video_properties['duration_seconds'])):

        output_tmp_image_path = os.path.join(temporary_path, vr_video_properties['uuid'],  f'{str(index + 1)}.jpg')  
        ffmpeg.input(path_file, ss=time_format).filter('scale', 4000, -1).output(output_tmp_image_path, vframes=1).overwrite_output().run(capture_stdout=True, capture_stderr=True)

        output_image_filename = vr_video_properties['uuid'] + f'_{str(index + 1)}.jpg'
        output_image_path = os.path.join(output_path, 'images', output_image_filename)
        subprocess.call(f'magick {output_tmp_image_path} -crop 1500x1500+250+250 {output_image_path}', shell=True)
        vr_video_properties['images'].append(output_image_filename)


# Create transactional script
sql_script = ''
sql_script += "SET AUTOCOMMIT = OFF;"
sql_script += "\n"
sql_script += "START TRANSACTION;"
sql_script += "\n"
sql_script += "\tSET @videoId = IFNULL((SELECT id FROM vr_video ORDER BY id DESC LIMIT 1), 0) + 1;"
sql_script += "\n"
sql_script += "\tSET @imageId = IFNULL((SELECT id FROM image ORDER BY id DESC LIMIT 1), 0) + 1;"
sql_script += "\n"
sql_script += "\tSET @imageVideoId = IFNULL((SELECT id FROM image_vr_video ORDER BY id DESC LIMIT 1), 0) + 1;"

for vr_video_properties in vr_videos_properties:

    uuid = vr_video_properties['uuid']
    file_size = vr_video_properties['file_size']
    width = vr_video_properties['width']
    height = vr_video_properties['height']
    date = vr_video_properties['date']
    original_filename = vr_video_properties['original_filename']
    duration_seconds = vr_video_properties['duration_seconds']

    sql_script += "\n\n"

    sql_script += "\tINSERT INTO vr_video "
    sql_script += "(id, rating, updated_at, hosted_on_id, width, height, viewed_times, uuid, reported, original_filename, file_size, favourite, duration_seconds, description, created_at, format)"
    sql_script += " VALUES "
    sql_script += f"((@videoId := @videoId + 1), 0, NULL, {hosted_on_id}, {width}, {height}, 0, '{uuid}', 0, '{original_filename}', {file_size}, 0, {duration_seconds}, NULL, '{date}', 'STEREO_180_LR');"
    sql_script += "\n\n"

    for vr_video_image in vr_video_properties['images']:

        sql_script += "\tINSERT INTO image "
        sql_script += "(id, created_at, directory, filename, updated_at)"
        sql_script += " VALUES "
        sql_script += f"((@imageId := @imageId + 1), NOW(), 'vr-videos', '{vr_video_image}', NULL);"
        sql_script += "\n\n"

        sql_script += "\tINSERT INTO image_vr_video "
        sql_script += "(id, image_id, vr_video_id)"
        sql_script += " VALUES "
        sql_script += f"((@imageVideoId := @imageVideoId + 1), @imageId, @videoId);"
        sql_script += "\n"

    sql_script += "\n"

sql_script += "COMMIT;"

with open(os.path.join(output_path, f'transaction-{time.strftime("%Y%m%d-%H%M%S")}.sql'), 'w') as file:
    file.write(sql_script)
file.close()
