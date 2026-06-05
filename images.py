#!/usr/bin/env python3
"""
Sync gallery images from Google Drive, then build thumbnails + manifests.

Phase 1 — Drive sync (Drive is the source of truth for IMAGES):
  * Downloads every folder and image under the hard-coded Drive folder
    into the local `resources` directory, mirroring the structure.
  * Deletes local images that no longer exist on Drive.
  * Leaves JSON files (and locally generated thumbnails) untouched.

Phase 2 — Image processing, across all galleries:
  * Every directory directly under `resources` is treated as a gallery,
    EXCEPT `projects`.
  * `resources/projects` holds one sub-directory per project; each of
    those is treated as a gallery.
  * For each gallery: write thumbnails into its `thumbs/` sub-dir and
    (re)write its `images.json`, preserving captions from any existing
    manifest and removing orphaned thumbnails.

Setup:
  pip install Pillow pillow-heif google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
  (pillow-heif is required to read .heic/.heif images.)
  Put an OAuth client file from Google Cloud Console next to this script as
  `credentials.json` (Desktop app type). First run opens a browser once and
  caches `token.json`.

Usage:
  python sync_and_thumbnails.py                 # sync from Drive, then process
  python sync_and_thumbnails.py --skip-download # process local files only
  python sync_and_thumbnails.py --size 500
"""

import argparse
import json
import os
import re
import sys

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Needs Pillow:  pip install Pillow")

# HEIC/HEIF support (and browser compatibility): browsers generally can't
# display .heic, so these are decoded and re-emitted as web JPEGs.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except ImportError:
    HEIF_OK = False

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1ABYVhzQObI0mtfkJZ9GRIheaUeXyAX4i"
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE       = "token.json"
SCOPES           = ["https://www.googleapis.com/auth/drive.readonly"]

RESOURCES_DIR  = "resources"
PROJECTS_DIR   = "Projects"        # the one dir under resources that holds sub-galleries
THUMBS_DIRNAME = "thumbs"
MANIFEST_NAME  = "images.json"
IMAGE_EXTS     = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
HEIC_EXTS      = {".heic", ".heif"}    # converted to JPEG (same base name) locally
DEFAULT_SIZE   = 400
JPEG_QUALITY   = 85

FOLDER_MIME = "application/vnd.google-apps.folder"


def is_image(name):
    return os.path.splitext(name)[1].lower() in IMAGE_EXTS


# ======================================================================
# Phase 1 — Google Drive sync
# ======================================================================
def folder_id_from_url(url):
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", url) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
    if not m:
        sys.exit(f"Couldn't find a folder id in DRIVE_FOLDER_URL: {url}")
    return m.group(1)


def get_drive_service():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        sys.exit("Needs Google libs:  pip install google-api-python-client "
                 "google-auth google-auth-oauthlib google-auth-httplib2")

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                sys.exit(f"Missing {CREDENTIALS_FILE} (OAuth client from Google Cloud Console).")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as fh:
            fh.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def list_children(service, folder_id):
    items, page_token = [], None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageToken=page_token,
        ).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            return items


def download_file(service, file_id, dest):
    from googleapiclient.http import MediaIoBaseDownload
    req = service.files().get_media(fileId=file_id)
    with open(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def sync_folder(service, folder_id, local_dir, remote_images):
    """Mirror a Drive folder into local_dir; record downloaded image paths."""
    os.makedirs(local_dir, exist_ok=True)
    for item in list_children(service, folder_id):
        name, mime = item["name"], item["mimeType"]
        dest = os.path.join(local_dir, name)
        if mime == FOLDER_MIME:
            sync_folder(service, item["id"], dest, remote_images)
        elif is_image(name) or mime.startswith("image/"):
            base, ext = os.path.splitext(name)
            heic = ext.lower() in HEIC_EXTS
            local_name = base + ".jpg" if heic else name   # heic stored as jpg
            dest = os.path.join(local_dir, local_name)
            remote_images.add(os.path.normpath(dest))
            if os.path.exists(dest):
                print(f"  = exists, skipped {os.path.relpath(dest)}")
            elif heic:
                if not HEIF_OK:
                    print(f"  ! {name}: install pillow-heif to convert HEIC; skipped")
                    remote_images.discard(os.path.normpath(dest))
                    continue
                tmp = os.path.join(local_dir, name)         # temp .heic
                download_file(service, item["id"], tmp)
                convert_to_jpeg(tmp, dest)
                os.remove(tmp)
                print(f"  v downloaded + converted {name} -> {local_name}")
            else:
                download_file(service, item["id"], dest)
                print(f"  v downloaded {os.path.relpath(dest)}")
        else:
            print(f"  . skipped (not an image): {name}")


def drive_sync(resources):
    folder_id = folder_id_from_url(DRIVE_FOLDER_URL)
    service = get_drive_service()
    remote_images = set()
    print(f"Syncing Drive folder {folder_id} -> {resources}/")
    sync_folder(service, folder_id, resources, remote_images)
    return remote_images


# ======================================================================
# Phase 2 — thumbnails + manifests
# ======================================================================
def load_existing_captions(manifest_path):
    if not os.path.isfile(manifest_path):
        return {}
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as err:
        print(f"  ! couldn't read {manifest_path} ({err}); ignoring it.")
        return {}
    images = data.get("images", []) if isinstance(data, dict) else data
    return {e["full"]: e["caption"] for e in images
            if isinstance(e, dict) and e.get("full") and e.get("caption")}


def top_level_images(directory):
    return sorted(n for n in os.listdir(directory)
                  if os.path.isfile(os.path.join(directory, n)) and is_image(n))


def make_thumbnail(src, dst, size):
    if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return False
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((size, size))
        ext = os.path.splitext(dst)[1].lower()
        if ext in (".jpg", ".jpeg") and im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        kwargs = {"quality": JPEG_QUALITY, "optimize": True} if ext in (".jpg", ".jpeg") else {}
        im.save(dst, **kwargs)
    return True


def convert_to_jpeg(src, dst):
    """Decode an image (e.g. HEIC) and save it as a JPEG at full resolution."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.save(dst, quality=88, optimize=True)


def clean_orphans(thumbs_dir, valid_names):
    removed = 0
    if not os.path.isdir(thumbs_dir):
        return removed
    for name in os.listdir(thumbs_dir):
        path = os.path.join(thumbs_dir, name)
        if os.path.isfile(path) and name not in valid_names:
            os.remove(path)
            removed += 1
    return removed


def prune_gallery_images(directory, remote_images):
    """Delete top-level images not present on Drive. JSON/thumbs untouched."""
    removed = 0
    for name in top_level_images(directory):
        full = os.path.normpath(os.path.join(directory, name))
        if full not in remote_images:
            os.remove(full)
            removed += 1
            print(f"  - removed local-only image: {os.path.relpath(full)}")
    return removed


def convert_local_heic(directory):
    """Replace any local .heic/.heif with a same-named .jpg. Covers
    --skip-download runs or manually added files; with a Drive sync the
    conversion already happened at download time."""
    for name in top_level_images(directory):
        base, ext = os.path.splitext(name)
        if ext.lower() in HEIC_EXTS:
            if not HEIF_OK:
                print(f"  ! {name}: install pillow-heif to convert HEIC; skipped")
                continue
            src = os.path.join(directory, name)
            convert_to_jpeg(src, os.path.join(directory, base + ".jpg"))
            os.remove(src)
            print(f"  ~ converted {name} -> {base}.jpg")


def process_gallery(directory, size):
    convert_local_heic(directory)
    manifest_path = os.path.join(directory, MANIFEST_NAME)
    thumbs_dir = os.path.join(directory, THUMBS_DIRNAME)
    captions = load_existing_captions(manifest_path)
    images = top_level_images(directory)
    os.makedirs(thumbs_dir, exist_ok=True)

    entries, made = [], 0
    for name in images:
        try:
            if make_thumbnail(os.path.join(directory, name),
                              os.path.join(thumbs_dir, name), size):
                made += 1
        except Exception as err:
            print(f"  ! skipped {name}: {err}")
            continue
        entry = {"thumb": f"{THUMBS_DIRNAME}/{name}", "full": name}
        if name in captions:
            entry["caption"] = captions[name]
        entries.append(entry)

    removed = clean_orphans(thumbs_dir, {e["full"] for e in entries})
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"images": entries}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"  [{os.path.relpath(directory)}] {len(entries)} image(s), "
          f"{made} thumb(s) built, {removed} orphan thumb(s) removed")


def pick_hero(images):
    """The image named 'hero' (any extension) if present, else the first."""
    for name in images:
        if os.path.splitext(name)[0].lower() == "hero":
            return name
    return images[0] if images else None


def generate_projects_json(resources):
    """(Re)write resources/<Projects>/projects.json: set each project's hero
    from its folder, preserving name/description/order from any existing file."""
    base = os.path.join(resources, PROJECTS_DIR)
    if not os.path.isdir(base):
        return
    manifest = os.path.join(base, "projects.json")

    existing, order = {}, []
    if os.path.isfile(manifest):
        try:
            data = json.load(open(manifest, encoding="utf-8"))
            for e in (data.get("projects", []) if isinstance(data, dict) else data):
                if isinstance(e, dict) and e.get("folder"):
                    existing[e["folder"]] = e
                    order.append(e["folder"])
        except (json.JSONDecodeError, OSError) as err:
            print(f"  ! couldn't read {manifest} ({err}); rebuilding.")

    subdirs = [d for d in sorted(os.listdir(base))
               if os.path.isdir(os.path.join(base, d)) and d != THUMBS_DIRNAME]
    # keep prior order, then append any new project folders
    ordered = [f for f in order if f in subdirs] + [d for d in subdirs if d not in order]

    projects = []
    for folder in ordered:
        images = top_level_images(os.path.join(base, folder))
        if not images:
            print(f"  ! project '{folder}' has no images; skipped")
            continue
        hero = pick_hero(images)
        prev = existing.get(folder, {})
        projects.append({
            "name": prev.get("name", folder),
            "description": prev.get("description", ""),
            "folder": folder,
            "hero": f"{folder}/{hero}",
        })

    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"projects": projects}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"  [projects.json] {len(projects)} project(s)")


def gallery_dirs(resources):
    """Every dir under resources is a gallery except `projects`, whose
    sub-directories are each galleries."""
    dirs = []
    for name in sorted(os.listdir(resources)):
        path = os.path.join(resources, name)
        if not os.path.isdir(path) or name == THUMBS_DIRNAME:
            continue
        if name == PROJECTS_DIR:
            for sub in sorted(os.listdir(path)):
                subpath = os.path.join(path, sub)
                if os.path.isdir(subpath) and sub != THUMBS_DIRNAME:
                    dirs.append(subpath)
        else:
            dirs.append(path)
    return dirs


# ======================================================================
def main():
    ap = argparse.ArgumentParser(description="Sync from Drive and build gallery thumbnails.")
    ap.add_argument("--resources", default=RESOURCES_DIR, help="path to the resources directory")
    ap.add_argument("--size", type=int, default=DEFAULT_SIZE, help=f"max thumb dimension (default {DEFAULT_SIZE})")
    ap.add_argument("--skip-download", action="store_true", help="skip Drive sync; process local files only")
    args = ap.parse_args()

    resources = args.resources
    os.makedirs(resources, exist_ok=True)

    remote_images = None
    if not args.skip_download:
        remote_images = drive_sync(resources)

    galleries = gallery_dirs(resources)
    print(f"\nProcessing {len(galleries)} gallery director(ies):")
    for d in galleries:
        if remote_images is not None:
            prune_gallery_images(d, remote_images)
        process_gallery(d, args.size)

    generate_projects_json(resources)

    print("\nDone.")


if __name__ == "__main__":
    main()