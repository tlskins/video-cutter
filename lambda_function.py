from moviepy.editor import *
import boto3
import math
import json
from os import environ
from os import listdir

dl_path = '/tmp'
write_path = '/tmp'


def lambda_handler(event, context):
    data_retrieved = event['Records'][0]['s3']
    bucket_name = data_retrieved['bucket']['name']
    file_key = data_retrieved['object']['key']
    print(file_key)
    file_paths = file_key.split('/')
    print(file_paths)

    root_folder = file_paths[0]
    user_id = file_paths[1]
    album_id = file_paths[2]
    full_file_name = file_paths[3]

    if not root_folder or not user_id or not album_id or not full_file_name:
        return {
            "statusCode": 422,
            "headers": {"content-type": "application/json"},
            "body":  "Invalid folder structure",
        }

    if 'ACCESS_KEY_ID' in environ:
        ACCESS_KEY_ID = environ['ACCESS_KEY_ID']
        SECRET_ACCESS_KEY = environ['SECRET_ACCESS_KEY']
        TARGET_BUCKET = environ['TARGET_BUCKET']
        TARGET_ROOT_FOLDER = environ['TARGET_ROOT_FOLDER']
        TARGET_META_FOLDER = environ['TARGET_META_FOLDER']
        CLIP_LENGTH_SECS = int(environ['CLIP_LENGTH_SECS'])
        MAX_CLIPS = int(environ['MAX_CLIPS'])
    else:
        import settings
        ACCESS_KEY_ID = settings.ACCESS_KEY_ID
        SECRET_ACCESS_KEY = settings.SECRET_ACCESS_KEY
        TARGET_BUCKET = settings.TARGET_BUCKET
        TARGET_ROOT_FOLDER = settings.TARGET_ROOT_FOLDER
        TARGET_META_FOLDER = settings.TARGET_META_FOLDER
        CLIP_LENGTH_SECS = int(settings.CLIP_LENGTH_SECS)
        MAX_CLIPS = int(settings.MAX_CLIPS)

    if TARGET_ROOT_FOLDER == root_folder:
        return {
            "statusCode": 422,
            "headers": {"content-type": "application/json"},
            "body":  "Source and target folders cannot be the same",
        }

    ext_idx = full_file_name.rfind('.')
    file_name = full_file_name[0:ext_idx]
    file_ext = full_file_name[ext_idx+1:]
    file_dl_path = '{}/{}.{}'.format(dl_path, file_name, file_ext)
    print(file_dl_path)

    s3 = boto3.client('s3')
    s3.download_file(
        bucket_name,
        file_key,
        file_dl_path,
    )

    source_vid = VideoFileClip(file_dl_path)
    print('duration {}'.format(source_vid.duration))

    clips = math.ceil(source_vid.duration / CLIP_LENGTH_SECS)
    if clips > MAX_CLIPS:
        clips = MAX_CLIPS
    print('clips {}'.format(clips))

    s3_session = boto3.session.Session(
        aws_access_key_id=ACCESS_KEY_ID,
        aws_secret_access_key=SECRET_ACCESS_KEY
    ).resource('s3')

    outputs = []
    for clip_num in range(0, clips):
        print('processing clip {}'.format(clip_num))
        # clip video
        startClip = CLIP_LENGTH_SECS*clip_num
        endClip = CLIP_LENGTH_SECS*(clip_num+1)
        clip = source_vid.subclip(startClip, endClip)
        clip_path = '{}/{}_clip_{}.mp4'.format(write_path, file_name, clip_num)
        clip.write_videofile(clip_path, audio=False)
        target_key = '{}/{}/{}/{}_clip_{}.mp4'.format(
            TARGET_ROOT_FOLDER, user_id, album_id, file_name, clip_num)
        print(target_key)
        s3_session.meta.client.upload_file(
            clip_path, TARGET_BUCKET, target_key)

        # save meta to json file
        metaPath = '{}/{}_clip_{}.txt'.format(write_path, file_name, clip_num)
        metaTargetKey = '{}/{}/{}/{}_clip_{}.txt'.format(
            TARGET_META_FOLDER, user_id, album_id, file_name, clip_num)
        clipMeta = {
            "path": target_key,
            "metaPath": metaTargetKey,
            "fileName": file_name,
            "number": clip_num,
            "startSec": startClip,
            "endSec": endClip,
            "userId": user_id,
            "uploadId": album_id,
        }
        with open(metaPath, 'w') as outfile:
            json.dump(clipMeta, outfile)
        s3_session.meta.client.upload_file(
            metaPath, TARGET_BUCKET, metaTargetKey)
        outputs.append(clipMeta)

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body":  {
            "userId": user_id,
            "uploadId": album_id,
            "bucket": TARGET_BUCKET,
            "outputs": outputs,
        },
    }
