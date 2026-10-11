# Collection and marketplace

### Collection

```python
user = client.users.get("your_username")

# Folders
folders = user.collection.folders.list()
user.collection.folders.create(name="Industrial")

# Browse folder contents
for item in user.collection.folders.get(0).releases.list(sort="added"):
    print(item.basic_information.title)

# Add a release. The response identifies the copy you just created, which is
# how you tell it apart from copies of the same release you already own.
created = user.collection.folders.get(1).releases.create(release_id=352665)

# Deep chaining: folder -> release -> instance -> fields
instances = user.collection.folders.get(1).releases.get(352665).instances
instances.get(created.instance_id).fields.update(field_id=1, value="Signed copy")

# Collection value
value = user.collection.value.get()
print(f"Median: {value.median}, Maximum: {value.maximum}")

# Wantlist — the add takes only the release id; Discogs drops notes and ratings
# sent to it, so they go in the update call
user.wantlist.create(release_id=352665)
user.wantlist.update(352665, notes="Original pressing", rating=4)
for want in user.wantlist.list():
    print(want.basic_information.title)
```

### Marketplace

```python
# Listings
listing = client.marketplace.listings.get(123456789)
# The response identifies the new listing; it is not a full Listing.
created = client.marketplace.listings.create(
    release_id=352665,
    condition="Very Good Plus (VG+)",
    price=25.00,
)
client.marketplace.listings.update(created.listing_id, price=22.50)
client.marketplace.listings.delete(created.listing_id)

# Orders
for order in client.marketplace.orders.list(status="Payment Received"):
    print(f"Order {order.id}: {order.status}")

# Fee lookup
fee = client.marketplace.fee.get(price=25.00, currency="USD")
```
