from moviepy.editor import *
import boto3
import math
import json
from os import environ
from os import listdir

downloadPath = '/tmp'
writePath = '/tmp'


def lambda_handler(event, context):
    dataRetrieved = event['Records'][0]['s3']
    bucketName = dataRetrieved['bucket']['name']
    fileKey = dataRetrieved['object']['key']
    print(fileKey)
    filePaths = fileKey.split('/')
    print(filePaths)

    rootFolder = filePaths[0]
    userId = filePaths[1]
    uploadId = filePaths[2]
    fullFileName = filePaths[3]

    if not rootFolder or not userId or not uploadId or not fullFileName:
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

    if TARGET_ROOT_FOLDER == rootFolder:
        return {
            "statusCode": 422,
            "headers": {"content-type": "application/json"},
            "body":  "Source and target folders cannot be the same",
        }

    extIdx = fullFileName.rfind('.')
    fileName = fullFileName[0:extIdx]
    fileExt = fullFileName[extIdx+1:]
    fileDownloadPath = '{}/{}.{}'.format(downloadPath, fileName, fileExt)
    print(fileDownloadPath)

    s3 = boto3.client('s3')
    s3.download_file(
        bucketName,
        fileKey,
        fileDownloadPath,
    )

    srcVideo = VideoFileClip(fileDownloadPath)
    print('duration {}'.format(srcVideo.duration))

    clips = math.ceil(srcVideo.duration / CLIP_LENGTH_SECS)
    if clips > MAX_CLIPS:
        clips = MAX_CLIPS
    print('clips {}'.format(clips))

    s3Session = boto3.session.Session(
        aws_access_key_id=ACCESS_KEY_ID,
        aws_secret_access_key=SECRET_ACCESS_KEY
    ).resource('s3')

    outputs = []
    for clipNum in range(0, clips):
        print('processing clip {}'.format(clipNum))
        # clip video
        startClip = CLIP_LENGTH_SECS*clipNum
        endClip = CLIP_LENGTH_SECS*(clipNum+1)
        clip = srcVideo.subclip(startClip, endClip)
        clipPath = '{}/{}_clip_{}.mp4'.format(writePath, fileName, clipNum)
        clip.write_videofile(clipPath, audio=False)
        targetKey = '{}/{}/{}/{}_clip_{}.mp4'.format(
            TARGET_ROOT_FOLDER, userId, uploadId, fileName, clipNum)
        print(targetKey)
        s3Session.meta.client.upload_file(
            clipPath, TARGET_BUCKET, targetKey)

        # save meta to json file
        metaPath = '{}/{}_clip_{}.txt'.format(writePath, fileName, clipNum)
        metaTargetKey = '{}/{}/{}/{}_clip_{}.txt'.format(
            TARGET_META_FOLDER, userId, uploadId, fileName, clipNum)
        clipMeta = {
            "path": targetKey,
            "metaPath": metaTargetKey,
            "fileName": fileName,
            "number": clipNum,
            "startSec": startClip,
            "endSec": endClip,
            "userId": userId,
            "uploadId": uploadId,
        }
        with open(metaPath, 'w') as outfile:
            json.dump(clipMeta, outfile)
        s3Session.meta.client.upload_file(
            metaPath, TARGET_BUCKET, metaTargetKey)
        outputs.append(clipMeta)

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body":  {
            "userId": userId,
            "uploadId": uploadId,
            "bucket": TARGET_BUCKET,
            "outputs": outputs,
        },
    }
