"""
Upload car images to Supabase Storage and link them to inventory rows.

Prerequisites:
  1. Create a bucket called 'car-images' in Supabase Dashboard → Storage
  2. Set the bucket to PUBLIC (so URLs work without auth)

Usage:
  # Upload a single image and link to an inventory row by ID:
  python upload_images.py --id 42 --file photos/bmw-3-series.jpg

  # Bulk upload: a folder of images named <inventory_id>.jpg (or .png/.webp):
  python upload_images.py --dir photos/

  # Bulk upload: match by make_model (filename = "BMW_3 Series.jpg"):
  python upload_images.py --dir photos/ --match-by make_model

  # List inventory rows without images:
  python upload_images.py --list-missing
"""
import argparse
import os
import sys
import mimetypes
from pathlib import Path

from database import supabase

BUCKET = os.getenv("SUPABASE_IMAGE_BUCKET", "car-images")
SUPABASE_URL = supabase.supabase_url


def get_public_url(file_path_in_bucket: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{file_path_in_bucket}"


def upload_file(local_path: Path, remote_name: str) -> str:
    """Upload a file to Supabase Storage. Returns the public URL."""
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


def update_inventory_image(row_id, image_url: str):
    supabase.table("inventory").update({"image_url": image_url}).eq("id", row_id).execute()
    print(f"  ✓ inventory id={row_id} → {image_url}")


def cmd_single(args):
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    ext = path.suffix.lower()
    remote_name = f"{args.id}{ext}"
    print(f"Uploading {path} as {remote_name} ...")
    url = upload_file(path, remote_name)
    update_inventory_image(args.id, url)
    print("Done.")


def cmd_dir(args):
    folder = Path(args.dir)
    if not folder.is_dir():
        print(f"Not a directory: {folder}")
        sys.exit(1)

    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    files = sorted(f for f in folder.iterdir() if f.suffix.lower() in image_exts)
    if not files:
        print(f"No image files found in {folder}")
        sys.exit(1)

    print(f"Found {len(files)} image(s) in {folder}/")

    if args.match_by == "make_model":
        rows = supabase.table("inventory").select("id, make, model").execute().data or []
        lookup = {}
        for r in rows:
            key = f"{r.get('make', '')}_{r.get('model', '')}".strip().lower()
            lookup[key] = r["id"]

        for f in files:
            stem = f.stem.strip().lower()
            row_id = lookup.get(stem)
            if row_id is None:
                stem_alt = stem.replace("-", " ").replace("_", " ")
                for k, v in lookup.items():
                    if k.replace("_", " ") == stem_alt:
                        row_id = v
                        break
            if row_id is None:
                print(f"  ✗ No inventory match for '{f.name}' (tried key '{stem}')")
                continue
            remote_name = f"{row_id}{f.suffix.lower()}"
            print(f"  Uploading {f.name} → {remote_name} ...")
            url = upload_file(f, remote_name)
            update_inventory_image(row_id, url)
    else:
        for f in files:
            stem = f.stem.strip()
            try:
                row_id = int(stem)
            except ValueError:
                print(f"  ✗ Skipping '{f.name}' — filename must be the inventory row ID (e.g. 42.jpg)")
                continue
            remote_name = f"{row_id}{f.suffix.lower()}"
            print(f"  Uploading {f.name} → {remote_name} ...")
            url = upload_file(f, remote_name)
            update_inventory_image(row_id, url)

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

    s1 = sub.add_parser("single", help="Upload one image for a specific inventory ID")
    s1.add_argument("--id", required=True, type=int, help="Inventory row ID")
    s1.add_argument("--file", required=True, help="Path to image file")

    s2 = sub.add_parser("bulk", help="Bulk upload a directory of images")
    s2.add_argument("--dir", required=True, help="Directory containing images")
    s2.add_argument("--match-by", choices=["id", "make_model"], default="id",
                    help="How to match filenames to inventory rows (default: filename = row ID)")

    sub.add_parser("list-missing", help="List inventory rows without images")

    args = p.parse_args()
    if args.cmd == "single":
        cmd_single(args)
    elif args.cmd == "bulk":
        cmd_dir(args)
    elif args.cmd == "list-missing":
        cmd_list_missing(args)
    else:
        p.print_help()
