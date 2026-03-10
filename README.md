# NASVideoAPI

Program that displays all media files (photo, video) in a folder and previews them when selected. Runs on my NAS, however you can run it using docker anywhere.

## Changing directory to be displyed

### For Single Use (such as testing)

Run uvicorn app using ```MEDIA_DIR=~<directory> uvicorn app:app --reload```. Replace the directory with the directory you want to see.

### Permanent Solution

Modify line 15 in app.py to ```MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "<directory>")).resolve()```. Replace the directory with the directory you want to see.

## Putting on a phone

If running on a server with remote access (such as if it uses tailscale), visit the web server hosted on docker on your phone. Press share icon, and click "Add to home screen."



