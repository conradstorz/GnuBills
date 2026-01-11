import json
with open('data/vendor_database.json', 'r') as f:
    data = json.load(f)

# The actual vendors are here:
vendors = data.get('vendors', {})
print(f"Found {len(vendors)} actual vendors")
for name, info in vendors.items():
    print(f"\nVendor: {name}")
    print(f"  addr_line1: {info.get('addr_line1', 'MISSING')}")
    print(f"  addr_line2: {info.get('addr_line2', 'MISSING')}")