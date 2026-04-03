"""
Upload car images to Supabase Storage and link them to inventory rows.

Prerequisites:
  1. Create a bucket called 'car-images' in Supabase Dashboard → Storage
  2. Set the bucket to PUBLIC (so URLs work without auth)

Image folder structure (each subfolder = inventory row ID):
  photos/
    42/
      front.jpg
      side.jpg
      interior.jpg
    15/
      img1.jpg
      img2.png

Usage:
  # Upload all car folders (max 3 images per car):
  python upload_images.py folders --dir photos/

  # Upload a single image for a specific inventory ID:
  python upload_images.py single --id 42 --file photos/bmw.jpg

  # List inventory rows without images:
  python upload_images.py list-missing
"""
import argparse
import json
import os
import sys
import mimetypes
from pathlib import Path

from database import supabase

BUCKET = os.getenv("SUPABASE_IMAGE_BUCKET", "car-images")
SUPABASE_URL = supabase.supabase_url
MAX_IMAGES_PER_CAR = 3
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def get_public_url(file_path_in_bucket: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{file_path_in_bucket}"


def upload_file(local_path: Path, remote_name: str) -> str:
    content_type = mimetypes.guess_type(str(local_path))[0] or "image/jpeg"
    with open(local_path, "rb") as f:
        data = f.read()

    try:
        supabase.storage.from_(BUCKET).remove([remote_name])
    except Exception:
        pass

    supabase.storage.from_(BUCKET).upload(
        remote_name,
        data,
        file_options={"content-type": content_type},
    )
    return get_public_url(remote_name)


def update_inventory_images(row_id, image_urls: list[str]):
    """Store image URLs as a JSON array string in the image_url column."""
    value = json.dumps(image_urls)
    supabase.table("inventory").update({"image_url": value}).eq("id", row_id).execute()
    print(f"  ✓ inventory id={row_id} → {len(image_urls)} image(s)")


def cmd_folders(args):
    """Upload from folder-per-car structure: <dir>/<row_id>/img1.jpg ..."""
    root = Path(args.dir)
    if not root.is_dir():
        print(f"Not a directory: {root}")
        sys.exit(1)

    subdirs = sorted(
        [d for d in root.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    if not subdirs:
        print(f"No subdirectories found in {root}. Expected folders named by inventory row ID.")
        sys.exit(1)

    total_uploaded = 0
    for sub in subdirs:
        try:
            row_id = int(sub.name.strip())
        except ValueError:
            print(f"  ✗ Skipping '{sub.name}/' — folder name must be the inventory row ID")
            continue

        images = sorted(f for f in sub.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        if not images:
            print(f"  ✗ No images in {sub.name}/")
            continue

        images = images[:MAX_IMAGES_PER_CAR]
        urls = []
        for i, img in enumerate(images):
            remote_name = f"{row_id}/{i}{img.suffix.lower()}"
            print(f"  Uploading {sub.name}/{img.name} → {remote_name}")
            url = upload_file(img, remote_name)
            urls.append(url)

        update_inventory_images(row_id, urls)
        total_uploaded += len(urls)

    print(f"\nDone. Uploaded {total_uploaded} image(s) across {len(subdirs)} car(s).")


def cmd_single(args):
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    remote_name = f"{args.id}/0{path.suffix.lower()}"
    print(f"Uploading {path} as {remote_name} ...")
    url = upload_file(path, remote_name)
    update_inventory_images(args.id, [url])
    print("Done.")


def cmd_list_missing(_args):
    rows = supabase.table("inventory").select("id, make, model, year, image_url").execute().data or []
    missing = [r for r in rows if not r.get("image_url")]
    if not missing:
        print("All inventory rows have an image_url.")
        return
    print(f"{len(missing)} row(s) missing image_url:\n")
    print(f"  {'ID':<6} {'Year':<6} {'Make':<15} {'Model':<20}")
    print(f"  {'—'*6} {'—'*6} {'—'*15} {'—'*20}")
    for r in missing:
        print(f"  {str(r.get('id','')):<6} {str(r.get('year','')):<6} {str(r.get('make','')):<15} {str(r.get('model','')):<20}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Upload car images to Supabase Storage")
    sub = p.add_subparsers(dest="cmd")

    s1 = sub.add_parser("folders", help="Upload from folder-per-car structure (<dir>/<row_id>/images...)")
    s1.add_argument("--dir", required=True, help="Parent directory containing row ID folders")

    s2 = sub.add_parser("single", help="Upload one image for a specific inventory ID")
    s2.add_argument("--id", required=True, type=int, help="Inventory row ID")
    s2.add_argument("--file", required=True, help="Path to image file")

    sub.add_parser("list-missing", help="List inventory rows without images")

    args = p.parse_args()
    if args.cmd == "folders":
        cmd_folders(args)
    elif args.cmd == "single":
        cmd_single(args)
    elif args.cmd == "list-missing":
        cmd_list_missing(args)
    else:
        p.print_help()
