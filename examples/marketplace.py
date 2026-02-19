"""Marketplace — listings, orders, fees, and inventory.

Covers:
  - Listings: get, create, update, delete
  - Orders: get, list with filters, update status
  - Order messages: list, create
  - Fee lookup
  - User inventory browsing

All write operations require OAuth authentication.
"""

from discogs_sdk import Discogs

# Reads DISCOGS_CONSUMER_KEY, DISCOGS_CONSUMER_SECRET, DISCOGS_ACCESS_TOKEN,
# and DISCOGS_ACCESS_TOKEN_SECRET from the environment.
# You can also pass them explicitly as constructor arguments.
client = Discogs()

# ━━ Listings ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Get an existing listing.
listing = client.marketplace.listings.get(123456789)
print(f"{listing.release.description} — ${listing.price.value} {listing.price.currency}")

# Create a new listing.
new_listing = client.marketplace.listings.create(
    release_id=352665,
    condition="Very Good Plus (VG+)",
    price=25.00,
    status="For Sale",
)
print(f"Created listing #{new_listing.id}")

# Update a listing.
client.marketplace.listings.update(
    new_listing.id,
    price=22.50,
    condition="Near Mint (NM or M-)",
)

# Delete a listing.
client.marketplace.listings.delete(new_listing.id)


# ━━ Orders ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Get a specific order.
order = client.marketplace.orders.get("12345-1")
print(f"Order {order.id}: {order.status}")

# List orders with filters.
# Statuses: "New Order", "Buyer Contacted", "Invoice Sent", "Payment Pending",
#           "Payment Received", "Shipped", "Cancelled"
# Sorts: "id", "buyer", "created", "status", "last_activity"
for order in client.marketplace.orders.list(
    status="Payment Received",
    sort="created",
    sort_order="desc",
):
    print(f"  Order {order.id}: {order.status}")

# Update order status.
updated = client.marketplace.orders.update(
    "12345-1",
    status="Shipped",
    shipping=5.00,
)
print(f"Order now: {updated.status}")


# ━━ Order messages ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# List messages on an order.
# .get() returns a LazyResource; .messages is a sub-resource accessor
# (no HTTP).  .list() returns a paginated iterator.
for msg in client.marketplace.orders.get("12345-1").messages.list():
    print(f"  [{msg.timestamp}] {msg.message}")

# Send a message (optionally with a status change).
client.marketplace.orders.get("12345-1").messages.create(
    message="Your order has shipped! Tracking: 1Z999AA10123456784",
    status="Shipped",
)


# ━━ Fees ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Look up the Discogs fee for a given price.
fee = client.marketplace.fee.get(price=25.00)
print(f"Fee: {fee.value} {fee.currency}")

# With a specific currency.
fee = client.marketplace.fee.get(price=25.00, currency="EUR")
print(f"Fee: {fee.value} {fee.currency}")


# ━━ User inventory ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Browse another user's inventory (marketplace listings).
# This is a sub-resource of users, not marketplace.
user = client.users.get("seller_username")
for listing in user.inventory.list(sort="price", sort_order="asc"):
    print(f"  {listing.id}: ${listing.price.value}")

# Filter by status.
for listing in user.inventory.list(status="For Sale"):
    print(f"  {listing.id}")
