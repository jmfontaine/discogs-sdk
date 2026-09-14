"""Collection — folders, instances, custom fields, value, and wantlist.

Covers:
  - Folders: list, create, update, delete
  - Browse folder contents (paginated)
  - Add releases to a folder
  - Instance management (rating, move, delete)
  - Custom fields
  - Collection value
  - Wantlist CRUD

All operations require OAuth authentication and target a specific user.
"""

from discogs_sdk import Discogs

# Reads DISCOGS_CONSUMER_KEY, DISCOGS_CONSUMER_SECRET, DISCOGS_ACCESS_TOKEN,
# and DISCOGS_ACCESS_TOKEN_SECRET from the environment.
# You can also pass them explicitly as constructor arguments.
client = Discogs()

USERNAME = "your_username"
user = client.users.get(USERNAME)

# ━━ Folders ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# List all folders.  Returns a plain list (not paginated).
folders = user.collection.folders.list()
for folder in folders:
    print(f"  [{folder.id}] {folder.name} ({folder.count} items)")

# Folder 0 is the special "All" folder — always present, not editable.
# Folder 1 is "Uncategorized" — the default folder for new additions.

# Get a specific folder.
folder = user.collection.folders.get(1)
print(f"Folder: {folder.name}")

# Create a new folder.
new_folder = user.collection.folders.create(name="Industrial")
print(f"Created folder #{new_folder.id}: {new_folder.name}")

# Rename a folder.
user.collection.folders.update(new_folder.id, name="Industrial / EBM")

# Delete a folder (must be empty).
user.collection.folders.delete(new_folder.id)


# ━━ Browsing folder contents ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# List releases in a folder (paginated).
# Sort options: "label", "artist", "title", "catno", "format", "rating",
#               "added", "year"
for item in user.collection.folders.get(0).releases.list(
    sort="added",
    sort_order="desc",
):
    info = item.basic_information
    if info:
        artists = ", ".join(a.name or "" for a in info.artists or [])
        print(f"  {info.title} by {artists} (rating: {item.rating})")


# ━━ Adding releases ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Add a release to a folder.  Folder 1 = "Uncategorized".
# The response identifies the copy you just created.  Keep it: the same
# release can sit in your collection several times, and this instance id
# is the only way to tell your new copy from the ones already there.
created = user.collection.folders.get(1).releases.create(release_id=352665)
instance_id = created.instance_id
print(f"Added instance #{instance_id} ({created.resource_url})")


# ━━ Instance management ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Each copy of a release in your collection is an "instance".
# Deep chaining: folder -> release -> instance.
#
# Everything below edits the copy created above, so cleanup runs in a
# `finally`: a failed edit must still not leave the example's copy behind.
try:
    # Get a reference to that instance.  This is a lightweight ref object —
    # no HTTP calls yet.
    instance_ref = (
        user.collection.folders.get(1)  # folder (no HTTP)
        .releases.get(352665)  # release ref (no HTTP)
        .instances.get(instance_id)  # instance ref (no HTTP)
    )

    # Update instance fields (e.g. rating).
    user.collection.folders.get(1).releases.get(352665).instances.update(
        instance_id,
        rating=5,
    )

    # ━━ Custom fields ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # List custom fields defined for this collection.
    fields = user.collection.fields.list()
    for field in fields:
        print(f"  [{field.id}] {field.name} ({field.type})")

    # Update a custom field value on that instance.
    # Navigate: folder -> release -> instance -> fields -> update
    instance_ref.fields.update(field_id=1, value="Signed copy")
finally:
    # Remove only the copy this example created.
    user.collection.folders.get(1).releases.get(352665).instances.delete(instance_id)


# ━━ Collection value ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

value = user.collection.value.get()
print(f"Minimum: {value.minimum}")
print(f"Median:  {value.median}")
print(f"Maximum: {value.maximum}")


# ━━ Cross-folder release lookup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Find all instances of a release across all folders.
for item in user.collection.releases.get(352665).list():
    print(f"  Folder {item.folder_id}, instance {item.instance_id}")


# ━━ Wantlist ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# List wantlist (paginated).
for want in user.wantlist.list():
    if want.basic_information:
        print(f"  {want.basic_information.title} (rating: {want.rating})")

# Add to wantlist. The endpoint takes the release id and nothing else: Discogs
# discards notes and ratings sent here.
want = user.wantlist.create(release_id=352665)
print(f"Added want #{want.id}")

# Notes and rating are set by the update call.
user.wantlist.update(352665, notes="Looking for original US pressing", rating=4)

# Remove from wantlist.
user.wantlist.delete(352665)
