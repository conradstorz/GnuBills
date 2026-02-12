# Why Not Piecash?

## TL;DR
**We're sticking with raw SQL** for this bill processor project. While piecash offers nice abstractions, our specific use case is better served by direct SQLite access.

## What is Piecash?

Piecash is a Python library that provides an ORM (Object-Relational Mapping) interface to GnuCash databases using SQLAlchemy. It lets you work with GnuCash data as Python objects instead of writing SQL.

## The Appeal of Piecash

### Code Simplification
With raw SQL (our current approach):
```python
#80+ lines to create a vendor
vendor_guid = generate_guid()
with get_connection() as conn:
    cursor = conn.execute("SELECT MAX(CAST(id AS INTEGER)) FROM vendors")
    max_id = cursor.fetchone()[0] or 0
    vendor_id = f"{max_id + 1:06d}"
    
usd_guid = get_usd_guid()

conn.execute("""
    INSERT INTO vendors (guid, id, name, currency, active, notes, tax_override,
                        addr_name, addr_addr1, addr_addr2, addr_addr3, addr_addr4,
                        addr_phone, addr_email)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (vendor_guid, vendor_id, name, usd_guid, 1, '', 0, 
      addr_name or '', addr1 or '', addr2 or '', addr3 or '', addr4 or '',
      phone or '', email or ''))
conn.commit()
```

With piecash:
```python
# ~10 lines
with piecash.open_book(db_path, readonly=False) as book:
    vendor = piecash.Vendor(
        name=name,
        currency=book.default_currency,
        active=1,
        addr_addr1=addr1,
        addr_addr2=addr2,
        addr_addr3=addr3,
        addr_addr4=addr4,
        addr_phone=phone,
        addr_email=email
    )
    book.save()
```

That's an 8x reduction in code! Similar savings for bill creation (200+ lines → 15 lines).

## Why We're NOT Using Piecash

### 1. **Noisy SQLAlchemy Warnings**

Every single piecash operation floods the console with SQLAlchemy relationship warnings:

```
SAWarning: relationship 'Account.slots' will copy column accounts.guid to column slots.obj_guid, 
which conflicts with relationship(s): 'Slot.parent' (copies slots.guid_val to slots.obj_guid)...
```

These warnings appear because:
- GnuCash's schema has complex overlapping relationships
- Piecash's ORM mappings don't perfectly align with GnuCash's design
- The `slots` table is used for multiple relationship types

**Impact**: Professional software shouldn't spam users with technical warnings they can't fix.

### 2. **Bill Creation Limitations**

Piecash doesn't fully support vendor bill operations:

```python
# This looks nice but...
bill = piecash.Bill(  # ← Bill class may not exist or work correctly
    vendor=vendor,
    date_opened=date,
    notes=description
)
bill.add_entry(...)  # ← Entry creation is complex
bill.post()          # ← Posting may not handle all GnuCash requirements
```

**Reality check**:
- Bills in GnuCash require complex multi-table coordination
- Invoice/Bill posting involves lots, splits, and transactions
- Piecash's business module support is incomplete for vendor bills
- We've already solved this with 200 lines of working SQL

### 3. **We're Already Experts in Our SQL**

Our `create_posted_bill_DEPRECATED()` function:
- **Works perfectly** - creates valid GnuCash bills
- **Well-documented** - extensive comments explain every step
- **Battle-tested** - used in production
- **Fully understood** - we know exactly what it does

**Migration cost**:
- Rewrite working code
- Debug piecash quirks
- Handle edge cases we've already solved
- Risk breaking existing functionality

### 4. **Performance Considerations**

Raw SQL:
```python
with get_connection() as conn:
    vendors = conn.execute("SELECT * FROM vendors WHERE active = 1")
# Direct database access, minimal overhead
```

Piecash:
```python
with piecash.open_book(db_path) as book:
    vendors = book.query(piecash.Vendor).filter_by(active=1).all()
# ORM layer adds:
# - Object hydration
# - Relationship loading
# - SQLAlchemy query translation
# - Change tracking
```

For our use case (simple CRUD operations), the ORM overhead provides little value.

### 5. **Diagnostic Tool Requirements**

Tools like **Columbo** need:
- Access to ALL tables (including internal GnuCash tables)
- Raw data inspection
- Schema discovery
- Diff generation

Piecash:
- Only exposes mapped tables
- Hides internal GnuCash structures
- Not designed for schema exploration

**Verdict**: Raw SQL is essential for diagnostic tools.

### 6. **Dependency Concerns**

Piecash adds:
- `piecash` itself
- `SQLAlchemy` (heavy dependency)
- Additional abstraction layers
- Potential version conflicts

Current approach:
- `sqlite3` (Python stdlib)
- Zero external database dependencies
- Direct control

### 7. **The "Good Enough" Principle**

Our current code:
- ✅ Works reliably
- ✅ Is well-documented
- ✅ Handles all our use cases
- ✅ Is maintainable by us

Piecash would give us:
- ❓ Shorter code (nice but not essential)
- ❓ Higher-level abstractions (we don't need them)
- ❌ SQLAlchemy warnings (annoying)
- ❌ Migration effort (costly)
- ❌ New dependency (risky)

**ROI**: The benefits don't justify the costs.

## When Piecash WOULD Make Sense

Piecash is great for:

1. **Complex business logic** - If we needed to navigate vendor→bills→payments→accounts extensively
2. **New projects** - Starting fresh without existing SQL code
3. **Full business module usage** - Customer invoices, employee expenses, job tracking
4. **Report generation** - Complex queries across multiple relationships
5. **Read-only analysis** - Data exploration without modification

## Our Hybrid Approach

**Best of both worlds:**

- ✅ **Raw SQL for core operations**: Vendor creation, bill posting, updates
- ✅ **Raw SQL for diagnostics**: Columbo, check_bill_quantities, check_bill_dates
- ✅ **Raw SQL for schema discovery**: Table inspection, column enumeration
- ✅ **Simple and direct**: No mysterious ORM behavior

**Future consideration:**
- If we add complex reporting features, revisit piecash
- If GnuCash client lib improves, evaluate again
- If we need customer invoicing, piecash might help

## Conclusion

> "Premature optimization is the root of all evil." - Donald Knuth

Similarly: **Premature abstraction is the root of unnecessary complexity.**

Our SQL approach:
- Is working
- Is understood
- Is maintainable
- Is sufficient

**Decision**: Stay with raw SQL. 

When the pain of SQL becomes greater than the pain of migration, we'll revisit. Until then, **keep it simple**.

---

## Appendix: Code Comparison

### Creating a Vendor

#### Raw SQL (Current)
```python
def create_vendor(name: str, addr_addr1: str = None, ...) -> str:
    logger.info(f"Creating new vendor: {name}")
    vendor_guid = generate_guid()
    
    with get_connection() as conn:
        cursor = conn.execute("SELECT MAX(CAST(id AS INTEGER)) FROM vendors")
        max_id = cursor.fetchone()[0] or 0
        vendor_id = f"{max_id + 1:06d}"
    
    usd_guid = get_usd_guid()
    
    with get_connection(readonly=False) as conn:
        conn.execute("""
            INSERT INTO vendors (
                guid, id, name, currency, active, notes, tax_override,
                addr_name, addr_addr1, addr_addr2, addr_addr3, addr_addr4,
                addr_phone, addr_email
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (vendor_guid, vendor_id, name, usd_guid, 1, '', 0,
              addr_name or '', addr_addr1 or '', addr_addr2 or '',
              addr_addr3 or '', addr_addr4 or '',
              addr_phone or '', addr_email or ''))
        conn.commit()
    
    return vendor_guid
```

**Lines**: 25-30  
**Dependencies**: sqlite3 (stdlib)  
**Control**: Complete  
**Warnings**: None

#### Piecash (Alternative)
```python
def create_vendor_piecash(name: str, addr_addr1: str = None, ...) -> str:
    with piecash.open_book(db_path, readonly=False) as book:
        vendor = piecash.Vendor(
            name=name,
            currency=book.default_currency,
            active=1,
            addr_addr1=addr_addr1 or '',
            addr_addr2=addr_addr2 or '',
            addr_addr3=addr_addr3 or '',
            addr_addr4=addr_addr4 or '',
            addr_phone=addr_phone or '',
            addr_email=addr_email or ''
        )
        book.save()
        return vendor.guid
```

**Lines**: 15  
**Dependencies**: piecash, SQLAlchemy  
**Control**: ORM layer  
**Warnings**: 20+ SAWarnings on every call

### Updating a Vendor

#### Raw SQL (Current)
```python
def update_vendor_address(vendor_guid: str, **fields):
    updates = []
    params = []
    
    for field in ['addr_name', 'addr_addr1', 'addr_addr2', 
                  'addr_addr3', 'addr_addr4', 'addr_phone', 'addr_email']:
        if field in fields and fields[field] is not None:
            updates.append(f"{field} = ?")
            params.append(fields[field])
    
    if not updates:
        return
    
    params.append(vendor_guid)
    
    with get_connection(readonly=False) as conn:
        conn.execute(
            f"UPDATE vendors SET {', '.join(updates)} WHERE guid = ?",
            params
        )
        conn.commit()
```

**Lines**: 20  
**Flexibility**: Dynamic field updates  
**Performance**: Single UPDATE query

#### Piecash (Alternative)
```python
def update_vendor_piecash(vendor_guid: str, **fields):
    with piecash.open_book(db_path, readonly=False) as book:
        vendor = book.query(piecash.Vendor).filter_by(guid=vendor_guid).first()
        
        for field, value in fields.items():
            if value is not None:
                setattr(vendor, field, value)
        
        book.save()
```

**Lines**: 9  
**Overhead**: Query + object hydration + change tracking + flush  
**Dependencies**: Full ORM machinery

## The Verdict

**Less code ≠ Better code**

Piecash wins on brevity. We win on:
- Stability
- Performance  
- Simplicity
- Control  
- Zero noise

**We're keeping our SQL.** 🎯
