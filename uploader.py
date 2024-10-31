import json
import os
import pprint
import vimeo


class vimeouploader:

    def __init__(self):

        config_file = os.path.dirname(os.path.realpath(__file__)) + '/downloader.conf'
        config = json.load(open(config_file))

        # Check for a config file
        if 'client_id' not in config['vimeo'] or 'client_secret' not in config['vimeo']:
            raise Exception('We could not locate your client id or client secret ' +
                            'in `' + config_file + '`. Please create one, and ' +
                            'reference `config.json.example`.')

        # Instantiate the library with your client id, secret and access token
        # (pulled from dev site)
        self.client = vimeo.VimeoClient(
            token=config['vimeo']['access_token'],
            key=config['vimeo']['client_id'],
            secret=config['vimeo']['client_secret']
        )



    def upload(self, file_name):

        try:
            # Upload the file and include the video title and description.
            uri = self.client.upload(file_name, data={
                'name': 'Vimeo API SDK test upload',
                'description': "This video was uploaded through the Vimeo API's " +
                            "Python SDK."
            })

            # Get the metadata response from the upload and log out the Vimeo.com url
            video_data = self.client.get(uri + '?fields=link').json()
            print('"{}" has been uploaded to {}'.format(file_name, video_data['link']))

            # Make an API call to edit the title and description of the video.
            self.client.patch(uri, data={
                'name': 'Vimeo API SDK test edit',
                'description': "This video was edited through the Vimeo API's " +
                            "Python SDK."
            })

            print('The title and description for %s has been edited.' % uri)

            # Make an API call to see if the video is finished transcoding.
            video_data = self.client.get(uri + '?fields=transcode.status').json()
            print('The transcode status for {} is: {}'.format(
                uri,
                video_data['transcode']['status']
            ))
        except vimeo.exceptions.VideoUploadFailure as e:
            # We may have had an error. We can't resolve it here necessarily, so
            # report it to the user.
            print('Error uploading %s' % file_name)
            print('Server reported: %s' % e.message)


    def list(self):
        # Get the user's uploaded videos
        videos = self.client.get('/me/videos')

        # Print out their names, the url to their page, and their privacy
        for video in videos.json()['data']:
            print('{} - {} - {}'.format(
                video['name'],
                video['link'],
                video['privacy']['view']
            ))

    def listFolder(self, folder_name):
        # Get the user's uploaded videos
        folders = self.client.get('/me/folders') # + folder + '/videos')

        # Print out their names, the url to their page, and their privacy
        for folders in folders.json()['data']:
            if folders['name'] == folder_name:
                print('{} - {} '.format(
                    folders['name'],
                    folders['uri'],
                ))
                videos = self.client.get(folders['uri'] + '/videos?sort=alphabetical')
                for video in videos.json()['data']:
                    #pprint.pprint(video)
                    print(f"{video['name'][:2]} - {video['link']}")

def main():
    print("Hello World")
    uploader = vimeouploader()
    #uploader.upload('test.mp4')
    uploader.listFolder('gc-2023-12-20')

if __name__ == "__main__":
    main()
