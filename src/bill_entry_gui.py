"""
Bill Entry GUI - Interactive tool for building bills_to_process.txt

Features:
- Real-time fuzzy matching as you type vendor names
- Tab completion from known vendors
- Validation of entries
- View and edit current bills queue
- Integrated bill processing with progress display
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sys
import time
import threading
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Optional, Tuple, Callable
from loguru import logger

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import config
import gnucash_db
import address_lookup
from schema_discovery import SchemaDiscovery, get_schema
from utils import fuzzy_match_vendor, strip_vendor_name, parse_input_line, make_expense_account_name
from vendor_manager import VendorManager


class NewVendorDialog:
    """Dialog for creating a new vendor with address options."""
    
    def __init__(self, parent: tk.Tk, vendor_name: str, all_vendors: List[Dict], prefill_data: Dict = None):
        self.result = None  # Will be 'create', 'match', or 'skip'
        self.vendor_data = None
        self.matched_vendor = None
        self.prefill_data = prefill_data  # Data to restore if reopening after error
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"New Vendor: {vendor_name}")
        self.dialog.geometry("550x550")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.vendor_name = vendor_name
        self.all_vendors = all_vendors
        
        self._create_widgets()
        self._prefill_fields()  # Fill in any preserved data
        
        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def _prefill_fields(self):
        """Fill in fields with preserved data from a previous failed attempt."""
        if not self.prefill_data:
            return
        
        # Clear and fill display name
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, self.prefill_data.get('display_name', self.vendor_name))
        
        # Fill address fields
        if self.prefill_data.get('addr_name'):
            self.addr_name_entry.insert(0, self.prefill_data['addr_name'])
        if self.prefill_data.get('addr_line1'):
            self.addr_line1_entry.insert(0, self.prefill_data['addr_line1'])
        if self.prefill_data.get('addr_line2'):
            self.addr_line2_entry.insert(0, self.prefill_data['addr_line2'])
        if self.prefill_data.get('phone'):
            self.phone_entry.insert(0, self.prefill_data['phone'])
        
    def _create_widgets(self):
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Header
        header_text = f"Vendor '{self.vendor_name}' not found"
        if self.prefill_data:
            header_text = f"Retry: {self.vendor_name} (your data preserved)"
        ttk.Label(
            main_frame, 
            text=header_text,
            font=('TkDefaultFont', 11, 'bold')
        ).pack(pady=(0, 10))
        
        # === Option 1: Match to Existing Vendor ===
        match_frame = ttk.LabelFrame(main_frame, text="Option 1: Match to Existing Vendor", padding="10")
        match_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(match_frame, text="Search:").pack(side="left")
        self.match_search = ttk.Entry(match_frame, width=30)
        self.match_search.pack(side="left", padx=(5, 10))
        self.match_search.bind('<KeyRelease>', self._on_match_search)
        
        self.match_combo = ttk.Combobox(match_frame, width=35, state="readonly")
        self.match_combo.pack(side="left", padx=(0, 10))
        
        ttk.Button(match_frame, text="Use Selected", command=self._use_matched).pack(side="left")
        
        # Populate combo with vendor names
        vendor_names = sorted(set(v['name'] for v in self.all_vendors))
        self.match_combo['values'] = vendor_names
        
        # === Option 2: Create New Vendor ===
        create_frame = ttk.LabelFrame(main_frame, text="Option 2: Create New Vendor", padding="10")
        create_frame.pack(fill="both", expand=True, pady=(0, 10))
        create_frame.columnconfigure(1, weight=1)
        
        # Display name
        ttk.Label(create_frame, text="Display Name:").grid(row=0, column=0, sticky="w", pady=3)
        self.name_entry = ttk.Entry(create_frame, width=40)
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=3, padx=(5, 0))
        self.name_entry.insert(0, self.vendor_name)
        
        # Address fields
        ttk.Label(create_frame, text="Address Name:").grid(row=1, column=0, sticky="w", pady=3)
        self.addr_name_entry = ttk.Entry(create_frame, width=40)
        self.addr_name_entry.grid(row=1, column=1, sticky="ew", pady=3, padx=(5, 0))
        
        ttk.Label(create_frame, text="Street Address:").grid(row=2, column=0, sticky="w", pady=3)
        self.addr_line1_entry = ttk.Entry(create_frame, width=40)
        self.addr_line1_entry.grid(row=2, column=1, sticky="ew", pady=3, padx=(5, 0))
        
        ttk.Label(create_frame, text="City, State ZIP:").grid(row=3, column=0, sticky="w", pady=3)
        self.addr_line2_entry = ttk.Entry(create_frame, width=40)
        self.addr_line2_entry.grid(row=3, column=1, sticky="ew", pady=3, padx=(5, 0))
        
        ttk.Label(create_frame, text="Phone:").grid(row=4, column=0, sticky="w", pady=3)
        self.phone_entry = ttk.Entry(create_frame, width=20)
        self.phone_entry.grid(row=4, column=1, sticky="w", pady=3, padx=(5, 0))
        
        # Web search button
        search_btn_frame = ttk.Frame(create_frame)
        search_btn_frame.grid(row=5, column=0, columnspan=2, pady=(10, 5))
        
        ttk.Button(
            search_btn_frame, 
            text="🔍 Web Search for Address", 
            command=self._web_search
        ).pack(side="left", padx=5)
        
        self.search_status = ttk.Label(search_btn_frame, text="", foreground="gray")
        self.search_status.pack(side="left", padx=5)
        
        # Create buttons
        create_btn_frame = ttk.Frame(create_frame)
        create_btn_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(
            create_btn_frame, 
            text="Create Vendor", 
            command=self._create_vendor
        ).pack(side="left", padx=5)
        
        ttk.Button(
            create_btn_frame, 
            text="Create Without Address", 
            command=self._create_no_address
        ).pack(side="left", padx=5)
        
        # === Option 3: Skip ===
        skip_frame = ttk.Frame(main_frame)
        skip_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(
            skip_frame, 
            text="Skip This Bill", 
            command=self._skip
        ).pack(side="right")
        
    def _on_match_search(self, event):
        """Filter vendor combo based on search text."""
        search = self.match_search.get().lower()
        if len(search) < 2:
            return
        
        matches = [v['name'] for v in self.all_vendors 
                   if search in v['name'].lower()]
        self.match_combo['values'] = sorted(set(matches))[:20]
        if matches:
            self.match_combo.set(matches[0])
    
    def _use_matched(self):
        """Use the selected existing vendor."""
        selected = self.match_combo.get()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a vendor to match to.")
            return
        
        # Find the vendor data
        for v in self.all_vendors:
            if v['name'] == selected:
                self.result = 'match'
                self.matched_vendor = v
                self.dialog.destroy()
                return
        
        messagebox.showerror("Error", "Could not find selected vendor.")
    
    def _web_search(self):
        """Search for address using web APIs."""
        search_name = self.name_entry.get().strip() or self.vendor_name
        self.search_status.config(text="Searching...", foreground="blue")
        self.dialog.update()
        
        try:
            result = address_lookup.lookup_address(search_name)
            
            if result:
                self.search_status.config(text="✓ Found", foreground="green")
                # Fill in the fields
                self.addr_name_entry.delete(0, tk.END)
                self.addr_name_entry.insert(0, result.get('name', ''))
                
                self.addr_line1_entry.delete(0, tk.END)
                self.addr_line1_entry.insert(0, result.get('addr_line1', ''))
                
                self.addr_line2_entry.delete(0, tk.END)
                self.addr_line2_entry.insert(0, result.get('addr_line2', ''))
                
                self.phone_entry.delete(0, tk.END)
                self.phone_entry.insert(0, result.get('phone', ''))
            else:
                self.search_status.config(text="No results found", foreground="orange")
        except Exception as e:
            logger.error(f"Address lookup error: {e}")
            self.search_status.config(text=f"Error: {e}", foreground="red")
    
    def _create_vendor(self):
        """Create vendor with entered address."""
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Required", "Display name is required.")
            return
        
        self.result = 'create'
        self.vendor_data = {
            'display_name': name,
            'addr_name': self.addr_name_entry.get().strip() or name,
            'addr_line1': self.addr_line1_entry.get().strip(),
            'addr_line2': self.addr_line2_entry.get().strip(),
            'phone': self.phone_entry.get().strip(),
        }
        self.dialog.destroy()
    
    def _create_no_address(self):
        """Create vendor without address info."""
        name = self.name_entry.get().strip() or self.vendor_name
        
        self.result = 'create'
        self.vendor_data = {
            'display_name': name,
            'addr_name': name,
            'addr_line1': '',
            'addr_line2': '',
            'phone': '',
        }
        self.dialog.destroy()
    
    def _skip(self):
        """Skip this bill."""
        self.result = 'skip'
        self.dialog.destroy()
    
    def show(self) -> Tuple[str, Optional[Dict]]:
        """Show dialog and return result."""
        self.dialog.wait_window()
        return self.result, self.vendor_data or self.matched_vendor


class ProcessingDialog:
    """Dialog showing bill processing progress."""
    
    def __init__(self, parent: tk.Tk, bills: List[Dict], vendor_manager: VendorManager, 
                 all_vendors: List[Dict], on_complete: Callable):
        self.parent = parent
        self.bills = bills
        self.vendor_manager = vendor_manager
        self.all_vendors = all_vendors
        self.on_complete = on_complete
        
        self.results = {'success': [], 'failed': [], 'skipped': []}
        self.processing = False
        self.current_bill_idx = 0
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Processing Bills")
        self.dialog.geometry("600x450")
        self.dialog.transient(parent)
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self._create_widgets()
        
        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
    def _create_widgets(self):
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Progress bar
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_label = ttk.Label(progress_frame, text="Ready to process...")
        self.progress_label.grid(row=0, column=0, sticky="w")
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.progress_bar['maximum'] = len(self.bills)
        
        # Log area
        log_frame = ttk.LabelFrame(main_frame, text="Processing Log", padding="5")
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=70, state='disabled')
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        # Configure tags for colored text
        self.log_text.tag_configure('success', foreground='green')
        self.log_text.tag_configure('error', foreground='red')
        self.log_text.tag_configure('warning', foreground='orange')
        self.log_text.tag_configure('info', foreground='blue')
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, sticky="ew")
        
        self.start_btn = ttk.Button(btn_frame, text="Start Processing", command=self._start_processing)
        self.start_btn.pack(side="left", padx=5)
        
        self.close_btn = ttk.Button(btn_frame, text="Close", command=self._on_close, state='disabled')
        self.close_btn.pack(side="right", padx=5)
        
    def _log(self, message: str, tag: str = None):
        """Add message to log area."""
        self.log_text.config(state='normal')
        if tag:
            self.log_text.insert(tk.END, message + "\n", tag)
        else:
            self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.dialog.update()
    
    def _start_processing(self):
        """Start processing bills."""
        # Check for GnuCash lock
        if gnucash_db.is_gnucash_locked():
            messagebox.showerror(
                "GnuCash is Running",
                "GnuCash appears to be running (lock file detected).\n\n"
                "Please close GnuCash before processing bills.\n\n"
                f"Lock file: {gnucash_db.get_lock_file_path()}"
            )
            return
        
        self.processing = True
        self.start_btn.config(state='disabled')
        self._log("Starting bill processing...", 'info')
        self._log(f"Processing {len(self.bills)} bill(s)\n")
        
        # Process bills one at a time with delay for visibility
        self.dialog.after(100, self._process_next_bill)
    
    def _process_next_bill(self):
        """Process the next bill in the queue."""
        if self.current_bill_idx >= len(self.bills):
            self._processing_complete()
            return
        
        bill = self.bills[self.current_bill_idx]
        self.progress_bar['value'] = self.current_bill_idx + 1
        self.progress_label.config(
            text=f"Processing {self.current_bill_idx + 1} of {len(self.bills)}: {bill['vendor_name']}"
        )
        
        self._log(f"{'─'*50}")
        self._log(f"Bill {self.current_bill_idx + 1}: {bill['vendor_name']}")
        self._log(f"  Amount: ${bill['amount']:.2f}")
        self._log(f"  Memo: {bill['memo']}")
        
        # Try to process this bill
        try:
            success = self._process_single_bill(bill)
            if success:
                self.results['success'].append(bill)
                self._log(f"  ✓ Bill created successfully", 'success')
            elif success is None:
                self.results['skipped'].append(bill)
                self._log(f"  ⊘ Bill skipped", 'warning')
            else:
                self.results['failed'].append(bill)
                self._log(f"  ✗ Bill failed", 'error')
        except Exception as e:
            logger.exception(f"Error processing bill: {e}")
            self.results['failed'].append(bill)
            self._log(f"  ✗ Error: {e}", 'error')
        
        self.current_bill_idx += 1
        
        # Schedule next bill with delay for readability
        self.dialog.after(500, self._process_next_bill)
    
    def _process_single_bill(self, bill: Dict) -> Optional[bool]:
        """
        Process a single bill. Returns True if success, False if failed, None if skipped.
        """
        vendor_name = bill['vendor_name']
        amount = bill['amount']
        memo = bill['memo']
        bill_date = bill['date']
        
        # Find vendor
        vendor_data, match_type = self.vendor_manager.find_vendor(vendor_name)
        
        if vendor_data:
            self._log(f"  Found vendor: {vendor_data.get('display_name')} ({match_type} match)")
            
            # Check if vendor exists in GnuCash - VERIFY the GUID, don't just check if present
            stored_guid = vendor_data.get('gnucash_guid')
            vendor_exists_in_gnucash = False
            
            if stored_guid:
                # Verify this GUID actually exists in GnuCash (might be stale after rollback)
                gc_vendor = gnucash_db.find_vendor_by_guid(stored_guid)
                if gc_vendor:
                    vendor_exists_in_gnucash = True
                    self._log(f"  Vendor verified in GnuCash: {gc_vendor['name']}")
                else:
                    self._log(f"  Stored GUID is stale - vendor not in GnuCash", 'warning')
            
            if not vendor_exists_in_gnucash:
                self._log(f"  Creating vendor in GnuCash...", 'warning')
                try:
                    vendor_guid = gnucash_db.create_vendor(
                        name=vendor_data.get('display_name'),
                        addr_name=vendor_data.get('addr_name', ''),
                        addr_addr1=vendor_data.get('addr_line1', ''),
                        addr_addr2=vendor_data.get('addr_line2', ''),
                        addr_phone=vendor_data.get('phone', '')
                    )
                    
                    # Update JSON with new GnuCash info
                    vendor_record = gnucash_db.find_vendor_by_name(vendor_data.get('display_name'))
                    vendor_key = strip_vendor_name(vendor_data.get('display_name'))
                    
                    if vendor_key in self.vendor_manager.vendors['vendors']:
                        self.vendor_manager.vendors['vendors'][vendor_key]['gnucash_guid'] = vendor_guid
                        self.vendor_manager.vendors['vendors'][vendor_key]['gnucash_id'] = vendor_record['id'] if vendor_record else None
                        self.vendor_manager.save()
                    
                    vendor_data['gnucash_guid'] = vendor_guid
                    self._log(f"  ✓ Vendor created in GnuCash", 'success')
                except Exception as e:
                    self._log(f"  ✗ Failed to create vendor in GnuCash: {e}", 'error')
                    return False
        else:
            self._log(f"  Vendor not found - opening dialog...", 'warning')
            
            # Show new vendor dialog - loop until success or skip
            prefill_data = None
            while True:
                dialog = NewVendorDialog(self.dialog, vendor_name, self.all_vendors, prefill_data)
                result, data = dialog.show()
                
                if result == 'skip':
                    return None
                elif result == 'match':
                    vendor_data = data
                    self._log(f"  Matched to: {vendor_data.get('name', vendor_data.get('display_name'))}")
                    break
                elif result == 'create':
                    # IMMEDIATELY save user's data to JSON - this is precious!
                    vendor_key = strip_vendor_name(data['display_name'])
                    self._log(f"  Saving vendor data to local database...")
                    self.vendor_manager.vendors['vendors'][vendor_key] = {
                        'display_name': data['display_name'],
                        'gnucash_guid': None,  # Will be filled in after GnuCash creation
                        'gnucash_id': None,
                        'addr_name': data['addr_name'],
                        'addr_line1': data['addr_line1'],
                        'addr_line2': data['addr_line2'],
                        'phone': data['phone'],
                    }
                    self.vendor_manager.save()
                    self._log(f"  ✓ Vendor data saved to JSON", 'success')
                    
                    # Now try to create in GnuCash
                    self._log(f"  Creating vendor in GnuCash: {data['display_name']}")
                    try:
                        vendor_guid = gnucash_db.create_vendor(
                            name=data['display_name'],
                            addr_name=data['addr_name'],
                            addr_addr1=data['addr_line1'],
                            addr_addr2=data['addr_line2'],
                            addr_phone=data['phone']
                        )
                        
                        # Get vendor record and update JSON with GnuCash info
                        vendor_record = gnucash_db.find_vendor_by_name(data['display_name'])
                        
                        # Update the JSON record with GnuCash GUID
                        self.vendor_manager.vendors['vendors'][vendor_key]['gnucash_guid'] = vendor_guid
                        self.vendor_manager.vendors['vendors'][vendor_key]['gnucash_id'] = vendor_record['id'] if vendor_record else None
                        self.vendor_manager.save()
                        
                        vendor_data = {
                            'gnucash_guid': vendor_guid,
                            'gnucash_id': vendor_record['id'] if vendor_record else None,
                            'display_name': data['display_name'],
                        }
                        
                        self._log(f"  ✓ Vendor created in GnuCash", 'success')
                        break  # Success - exit loop
                    except Exception as e:
                        self._log(f"  ✗ Failed to create in GnuCash: {e}", 'error')
                        self._log(f"  ℹ Vendor data is safely stored in JSON", 'info')
                        # Data is already saved to JSON, offer to retry or continue
                        retry = messagebox.askyesno(
                            "GnuCash Creation Failed",
                            f"Failed to create vendor in GnuCash: {e}\n\n"
                            "Your vendor data has been saved to the local database.\n\n"
                            "Would you like to retry creating in GnuCash?\n"
                            "(No = Skip this bill for now)"
                        )
                        if retry:
                            prefill_data = data
                            continue
                        else:
                            return None  # Skip this bill
                else:
                    return None
        
        # Get expense account
        try:
            expense_acct_name = make_expense_account_name(
                vendor_data.get('display_name') or vendor_data.get('name', vendor_name)
            )
            existing_accts = gnucash_db.find_expense_accounts_like(expense_acct_name)
            
            if existing_accts:
                expense_acct_guid = existing_accts[0]['guid']
                self._log(f"  Using expense account: {existing_accts[0]['name']}")
            else:
                self._log(f"  Creating expense account: {expense_acct_name}")
                expense_acct_guid = gnucash_db.create_expense_account(expense_acct_name)
        except Exception as e:
            self._log(f"  ✗ Expense account error: {e}", 'error')
            return False
        
        # Create the bill
        try:
            vendor_guid = vendor_data.get('gnucash_guid') or vendor_data.get('guid')
            if not vendor_guid:
                gc_vendor = gnucash_db.find_vendor_by_name(
                    vendor_data.get('display_name') or vendor_data.get('name')
                )
                if gc_vendor:
                    vendor_guid = gc_vendor['guid']
                else:
                    self._log(f"  ✗ Could not find vendor GUID", 'error')
                    return False
            
            bill_guid = gnucash_db.create_posted_bill(
                vendor_guid=vendor_guid,
                expense_account_guid=expense_acct_guid,
                amount=amount,
                memo=memo,
                bill_date=bill_date
            )
            
            return True
            
        except Exception as e:
            logger.exception(f"Error creating bill: {e}")
            self._log(f"  ✗ Failed to create bill: {e}", 'error')
            return False
    
    def _processing_complete(self):
        """Called when all bills have been processed."""
        self.processing = False
        self.close_btn.config(state='normal')
        
        self._log(f"\n{'='*50}")
        self._log("PROCESSING COMPLETE", 'info')
        self._log(f"  Successful: {len(self.results['success'])}", 'success')
        self._log(f"  Failed: {len(self.results['failed'])}", 'error' if self.results['failed'] else None)
        self._log(f"  Skipped: {len(self.results['skipped'])}", 'warning' if self.results['skipped'] else None)
        
        self.progress_label.config(text="Processing complete!")
        
    def _on_close(self):
        """Handle dialog close."""
        if self.processing:
            if not messagebox.askyesno("Processing", "Processing is still running. Cancel?"):
                return
        
        self.dialog.destroy()
        self.on_complete(self.results)
    
    def show(self):
        """Show the dialog."""
        self.dialog.wait_window()


class BillEntryGUI:
    """Main GUI application for bill entry."""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GnuCash Bill Entry")
        self.root.geometry("800x700")
        self.root.minsize(600, 500)
        
        # Database connection status
        self.gnucash_connected = False
        self.gnucash_error = None
        self.schema_valid = False
        self.schema_errors = []
        self.schema_warnings = []
        
        # Load vendor data FIRST (before validation - we need it to validate GUIDs)
        self.vendor_manager = VendorManager()
        
        # Run schema validation at startup (validates schema AND all stored GUIDs)
        self._validate_schema_at_startup()
        
        # Load all vendors for autocomplete
        self.all_vendors = self._load_all_vendors()
        
        # Autocomplete state
        self.autocomplete_window = None
        self.selected_vendor = None
        
        # Build UI
        self._create_widgets()
        self._load_current_bills()
        
        # Bind keyboard shortcuts
        self.root.bind('<Control-s>', lambda e: self._save_bill())
        self.root.bind('<Control-n>', lambda e: self._clear_form())
    
    def _validate_schema_at_startup(self):
        """
        Validate GnuCash schema AND all stored data at startup.
        
        This runs before UI is built to:
        1. Discover database schema with FULL VERIFICATION
        2. Find required accounts  
        3. Validate ALL vendor GUIDs stored in vendor_database.json
        4. Clear stale GUIDs (from database rollback, etc.)
        5. Offer to fix issues (create A/P account, etc.)
        6. Log ALL verification failures to history
        
        This is CRITICAL for data integrity - ensures we never use stale GUIDs.
        """
        logger.info("=" * 60)
        logger.info("STARTUP VALIDATION - Verifying ALL stored data")
        logger.info("=" * 60)
        
        try:
            schema = get_schema()
            result = schema.discover()
            
            self.schema_valid = result['valid']
            self.schema_errors = result['errors']
            self.schema_warnings = result['warnings']
            
            # Get verification details
            self.verification_result = result.get('verification', {})
            
            logger.info(f"Schema validation: valid={self.schema_valid}, "
                       f"errors={len(self.schema_errors)}, warnings={len(self.schema_warnings)}")
            
            # Log verification summary
            if self.verification_result:
                passed = self.verification_result.get('passed_checks', 0)
                total = self.verification_result.get('total_checks', 0)
                failed = self.verification_result.get('failed_checks', 0)
                logger.info(f"Verification: {passed}/{total} checks passed, {failed} failed")
            
            # If we have errors, show them and offer fixes
            if self.schema_errors:
                self._handle_schema_errors(schema)
            
            # ====== VENDOR GUID VALIDATION ======
            # This is critical - catch stale GUIDs from database rollbacks
            logger.info("Validating vendor GUIDs against GnuCash...")
            sync_result = schema.sync_vendors_with_gnucash(self.vendor_manager)
            
            # Report stale GUIDs found
            if sync_result['stale_cleared']:
                stale_names = [s['display_name'] for s in sync_result['stale_cleared']]
                warn_msg = (
                    f"Found {len(stale_names)} vendor(s) with stale GnuCash references:\n\n"
                )
                for name in stale_names:
                    warn_msg += f"• {name}\n"
                warn_msg += (
                    "\nThese vendors will need to be re-created in GnuCash.\n"
                    "(This can happen after a database restore/rollback)"
                )
                self.schema_warnings.append(warn_msg)
                logger.warning(f"Cleared stale GUIDs for: {stale_names}")
            
            # Report GnuCash vendors not in our database
            if sync_result['newly_found']:
                logger.info(f"Found {len(sync_result['newly_found'])} GnuCash vendors not in local database")
                for v in sync_result['newly_found'][:5]:  # Log first 5
                    logger.debug(f"  - {v['name']} (ID: {v['id']})")
            
            logger.info(f"Vendor validation complete: {len(sync_result['verified'])} verified, "
                       f"{len(sync_result['stale_cleared'])} stale cleared")
            
            # ====== EXPENSE ACCOUNT VALIDATION ======
            # Validate default_expense_account GUIDs stored for vendors
            self._validate_expense_account_guids(schema)
            
            # ====== SHOW VERIFICATION FAILURES ======
            # Get any failures from current or previous runs
            failures = schema.get_verification_failures(last_n_runs=1)
            if failures:
                self._show_verification_failures(failures)
            
            # Show warnings but don't block
            if self.schema_warnings and self.schema_valid:
                warn_msg = "GnuCash setup warnings:\n\n"
                for warn in self.schema_warnings:
                    warn_msg += f"• {warn}\n\n"
                logger.warning(f"Schema warnings: {self.schema_warnings}")
            
            self.gnucash_connected = True
            
            logger.info("=" * 60)
            logger.info("STARTUP VALIDATION COMPLETE")
            logger.info("=" * 60)
            
        except FileNotFoundError as e:
            self.gnucash_connected = False
            self.gnucash_error = str(e)
            self.schema_valid = False
            logger.error(f"Database not found: {e}")
        except Exception as e:
            self.gnucash_connected = False
            self.gnucash_error = str(e)
            self.schema_valid = False
            logger.exception(f"Schema validation failed: {e}")
    
    def _validate_expense_account_guids(self, schema: SchemaDiscovery):
        """
        Validate expense account GUIDs stored in vendor data.
        
        Each vendor can have a default_expense_account - verify these exist.
        """
        logger.info("Validating expense account GUIDs...")
        
        vendors = self.vendor_manager.vendors.get('vendors', {})
        invalid_expense_accounts = []
        
        try:
            conn = schema._get_connection()
            
            for vendor_key, vendor_data in vendors.items():
                expense_guid = vendor_data.get('default_expense_account')
                if not expense_guid:
                    continue
                
                # Check if account exists
                cursor = conn.execute(
                    "SELECT guid, name FROM accounts WHERE guid = ?",
                    (expense_guid,)
                )
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"Invalid expense account GUID for {vendor_key}: {expense_guid[:12]}...")
                    invalid_expense_accounts.append({
                        'vendor_key': vendor_key,
                        'display_name': vendor_data.get('display_name', vendor_key),
                        'old_guid': expense_guid
                    })
                    # Clear the invalid GUID
                    vendor_data['default_expense_account'] = None
            
            conn.close()
            
            if invalid_expense_accounts:
                self.vendor_manager.save()
                names = [a['display_name'] for a in invalid_expense_accounts]
                logger.warning(f"Cleared invalid expense accounts for: {names}")
                self.schema_warnings.append(
                    f"Cleared {len(invalid_expense_accounts)} invalid expense account references"
                )
                
        except Exception as e:
            logger.error(f"Error validating expense accounts: {e}")
    
    def _show_verification_failures(self, failures: list):
        """
        Show verification failures to the user and log them prominently.
        
        These failures are IMPORTANT - they indicate issues with the database
        that could cause data loss or corruption.
        """
        if not failures:
            return
        
        logger.warning("=" * 60)
        logger.warning(f"VERIFICATION FAILURES: {len(failures)} issues found")
        logger.warning("=" * 60)
        
        for f in failures:
            logger.warning(
                f"  [{f.get('check_name')}] {f.get('table')}: "
                f"{f.get('description')} - {f.get('details', 'No details')}"
            )
        
        # Build message for user (only show if there are critical failures)
        critical_failures = [f for f in failures 
                           if f.get('check_name') in 
                           ('AP_ACCOUNT', 'USD_CURRENCY', 'BOOK_GUID', 
                            'POST_WRITE_VERIFY', 'DB_FILE', 'DB_ACCESS')]
        
        if critical_failures:
            msg = "Database Verification Issues:\n\n"
            for f in critical_failures[:5]:  # Show max 5
                msg += f"• {f.get('check_name')}: {f.get('description')}\n"
                if f.get('details'):
                    msg += f"  Details: {f.get('details')}\n"
                msg += "\n"
            
            if len(critical_failures) > 5:
                msg += f"... and {len(critical_failures) - 5} more issues.\n"
            
            msg += "\nSee the log file for complete details."
            
            messagebox.showwarning("Verification Issues", msg)
    
    def _handle_schema_errors(self, schema: SchemaDiscovery):
        """Handle schema errors - offer to fix what we can."""
        # Check if A/P account is missing
        if schema.needs_ap_account():
            logger.info("A/P account missing - offering to create")
            
            # Check we have liabilities parent first
            liab_guid = schema.get_account_guid('liabilities_parent')
            if not liab_guid:
                # Can't create A/P without liabilities parent - just warn
                messagebox.showwarning(
                    "GnuCash Setup Issue",
                    "No Accounts Payable account found, and no Liabilities parent account exists.\n\n"
                    "Please create a Liabilities account in GnuCash first, then restart this application."
                )
                return
            
            # Offer to create A/P
            if messagebox.askyesno(
                "Create Accounts Payable?",
                "No Accounts Payable account found in GnuCash.\n\n"
                "This account is required for vendor bills.\n\n"
                "Would you like to create it now?\n"
                f"(Will be created under '{schema.get_account_name('liabilities_parent')}')"
            ):
                try:
                    ap_guid = gnucash_db.create_ap_account()
                    # Update schema with new A/P account
                    schema.update_ap_account(ap_guid, "Accounts Payable")
                    
                    # Remove this error
                    self.schema_errors = [e for e in self.schema_errors if 'Accounts Payable' not in e]
                    self.schema_valid = len(self.schema_errors) == 0
                    
                    messagebox.showinfo("Success", "Accounts Payable account created!")
                    logger.info("A/P account created successfully")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create A/P account:\n{e}")
                    logger.error(f"Failed to create A/P account: {e}")
        
        # If there are remaining errors, show them
        remaining_errors = [e for e in self.schema_errors if 'Accounts Payable' not in e or schema.needs_ap_account()]
        if remaining_errors:
            error_msg = "GnuCash setup issues:\n\n"
            for err in remaining_errors:
                error_msg += f"• {err}\n\n"
            error_msg += "Some features may not work correctly."
            messagebox.showwarning("GnuCash Setup", error_msg)
        
    def _load_all_vendors(self) -> List[Dict]:
        """Load vendors from both JSON database and GnuCash."""
        vendors = []
        
        # From JSON database
        for key, data in self.vendor_manager.vendors.get('vendors', {}).items():
            vendors.append({
                'name': data.get('display_name', key),
                'source': 'local',
                'key': key,
                'data': data
            })
        
        # From aliases
        for alias, key in self.vendor_manager.vendors.get('aliases', {}).items():
            # Add alias as searchable name pointing to same vendor
            if key in self.vendor_manager.vendors.get('vendors', {}):
                vendors.append({
                    'name': alias,
                    'source': 'alias',
                    'key': key,
                    'data': self.vendor_manager.vendors['vendors'][key]
                })
        
        # From GnuCash database
        try:
            gc_vendors = gnucash_db.get_all_vendors()
            self.gnucash_connected = True
            for gv in gc_vendors:
                # Check if already in local database
                already_local = any(
                    v['data'].get('gnucash_guid') == gv['guid'] 
                    for v in vendors if v['source'] == 'local'
                )
                if not already_local:
                    vendors.append({
                        'name': gv['name'],
                        'source': 'gnucash',
                        'key': gv['guid'],
                        'data': gv
                    })
        except Exception as e:
            self.gnucash_connected = False
            self.gnucash_error = str(e)
        
        return vendors
    
    def _create_widgets(self):
        """Create all GUI widgets."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights for resizing
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # === Database Connection Warning ===
        if not self.gnucash_connected:
            warning_frame = tk.Frame(main_frame, bg="#ffcccc", padx=10, pady=8)
            warning_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
            
            warning_text = "⚠️ GnuCash database not connected - vendor matching disabled"
            if self.gnucash_error:
                warning_text += f"\n{self.gnucash_error}"
            warning_text += "\n\nEdit src/config.py to set GNUCASH_DB_PATH to your .gnucash file"
            
            warning_label = tk.Label(
                warning_frame, 
                text=warning_text,
                bg="#ffcccc", 
                fg="#990000",
                font=('TkDefaultFont', 9),
                justify="left"
            )
            warning_label.pack(anchor="w")
            
            form_row = 1  # Shift form down
        else:
            # Show connected status
            status_frame = tk.Frame(main_frame, bg="#ccffcc", padx=10, pady=5)
            status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
            
            status_label = tk.Label(
                status_frame,
                text=f"✓ Connected to GnuCash ({len([v for v in self.all_vendors if v['source'] == 'gnucash'])} vendors loaded)",
                bg="#ccffcc",
                fg="#006600",
                font=('TkDefaultFont', 9)
            )
            status_label.pack(anchor="w")
            
            form_row = 1
        
        # === Entry Form Section ===
        form_frame = ttk.LabelFrame(main_frame, text="New Bill Entry", padding="10")
        form_frame.grid(row=form_row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        form_frame.columnconfigure(1, weight=1)
        
        # Vendor name with autocomplete
        ttk.Label(form_frame, text="Vendor:").grid(row=0, column=0, sticky="w", pady=5)
        self.vendor_entry = ttk.Entry(form_frame, width=40)
        self.vendor_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=(5, 0))
        self.vendor_entry.bind('<KeyRelease>', self._on_vendor_key)
        self.vendor_entry.bind('<Tab>', self._on_tab_complete)
        self.vendor_entry.bind('<Return>', self._on_vendor_return)
        self.vendor_entry.bind('<Down>', self._on_down_arrow)
        self.vendor_entry.bind('<Escape>', self._close_autocomplete)
        
        # Match indicator
        self.match_label = ttk.Label(form_frame, text="", foreground="gray")
        self.match_label.grid(row=0, column=2, padx=(10, 0))
        
        # Amount
        ttk.Label(form_frame, text="Amount:").grid(row=1, column=0, sticky="w", pady=5)
        amount_frame = ttk.Frame(form_frame)
        amount_frame.grid(row=1, column=1, sticky="w", pady=5, padx=(5, 0))
        
        ttk.Label(amount_frame, text="$").pack(side="left")
        self.amount_entry = ttk.Entry(amount_frame, width=15)
        self.amount_entry.pack(side="left")
        self.amount_entry.bind('<Return>', lambda e: self._save_bill())
        
        # Memo
        ttk.Label(form_frame, text="Memo:").grid(row=2, column=0, sticky="w", pady=5)
        self.memo_entry = ttk.Entry(form_frame, width=40)
        self.memo_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=(5, 0))
        self.memo_entry.insert(0, config.DEFAULT_MEMO)
        
        # Date
        ttk.Label(form_frame, text="Date:").grid(row=3, column=0, sticky="w", pady=5)
        date_frame = ttk.Frame(form_frame)
        date_frame.grid(row=3, column=1, sticky="w", pady=5, padx=(5, 0))
        
        self.date_entry = ttk.Entry(date_frame, width=15)
        self.date_entry.pack(side="left")
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        
        ttk.Button(date_frame, text="Today", command=self._set_today).pack(side="left", padx=(10, 0))
        
        # Buttons
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(15, 0))
        
        ttk.Button(button_frame, text="Add Bill (Ctrl+S)", command=self._save_bill).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Clear (Ctrl+N)", command=self._clear_form).pack(side="left", padx=5)
        
        # === Current Bills Section ===
        bills_frame = ttk.LabelFrame(main_frame, text="Bills to Process", padding="10")
        bills_frame.grid(row=form_row+1, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        bills_frame.columnconfigure(0, weight=1)
        bills_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(form_row+1, weight=1)
        
        # Treeview for bills
        columns = ('vendor', 'amount', 'memo', 'date')
        self.bills_tree = ttk.Treeview(bills_frame, columns=columns, show='headings', height=8)
        
        self.bills_tree.heading('vendor', text='Vendor')
        self.bills_tree.heading('amount', text='Amount')
        self.bills_tree.heading('memo', text='Memo')
        self.bills_tree.heading('date', text='Date')
        
        self.bills_tree.column('vendor', width=200)
        self.bills_tree.column('amount', width=100)
        self.bills_tree.column('memo', width=200)
        self.bills_tree.column('date', width=100)
        
        # Scrollbar for treeview
        scrollbar = ttk.Scrollbar(bills_frame, orient="vertical", command=self.bills_tree.yview)
        self.bills_tree.configure(yscrollcommand=scrollbar.set)
        
        self.bills_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Bills action buttons
        bills_btn_frame = ttk.Frame(bills_frame)
        bills_btn_frame.grid(row=1, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(bills_btn_frame, text="Remove Selected", command=self._remove_selected).pack(side="left", padx=5)
        ttk.Button(bills_btn_frame, text="Edit Selected", command=self._edit_selected).pack(side="left", padx=5)
        ttk.Button(bills_btn_frame, text="Refresh", command=self._load_current_bills).pack(side="left", padx=5)
        ttk.Button(bills_btn_frame, text="Pre-process Bills", command=self._preprocess_bills).pack(side="left", padx=5)
        
        # Total display
        self.total_label = ttk.Label(bills_btn_frame, text="Total: $0.00", font=('TkDefaultFont', 10, 'bold'))
        self.total_label.pack(side="right", padx=20)
        
        # === Vendor Suggestions Section ===
        suggest_frame = ttk.LabelFrame(main_frame, text="Matching Vendors", padding="10")
        suggest_frame.grid(row=form_row+2, column=0, columnspan=2, sticky="ew")
        suggest_frame.columnconfigure(0, weight=1)
        
        # Listbox for suggestions
        self.suggest_list = tk.Listbox(suggest_frame, height=5)
        self.suggest_list.grid(row=0, column=0, sticky="ew")
        self.suggest_list.bind('<Double-Button-1>', self._on_suggest_select)
        self.suggest_list.bind('<Return>', self._on_suggest_select)
        
        # === Status Bar ===
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.grid(row=form_row+3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        
        # Focus on vendor entry
        self.vendor_entry.focus()
    
    def _on_vendor_key(self, event):
        """Handle keypress in vendor entry - update fuzzy matches."""
        # Ignore special keys
        if event.keysym in ('Tab', 'Return', 'Down', 'Up', 'Escape', 'Shift_L', 'Shift_R', 'Control_L', 'Control_R'):
            return
        
        search_text = self.vendor_entry.get().strip()
        
        if len(search_text) < 2:
            self.suggest_list.delete(0, tk.END)
            self.match_label.config(text="", foreground="gray")
            self.selected_vendor = None
            return
        
        # Find matches
        matches = self._find_vendor_matches(search_text)
        
        # Update suggestion list
        self.suggest_list.delete(0, tk.END)
        for match in matches[:10]:  # Limit to 10 suggestions
            source_tag = f" [{match['source']}]" if match['source'] != 'local' else ""
            self.suggest_list.insert(tk.END, f"{match['name']} ({match['score']}%){source_tag}")
        
        # Update match indicator
        if matches:
            best = matches[0]
            if best['score'] >= 90:
                self.match_label.config(text=f"✓ {best['name']}", foreground="green")
                self.selected_vendor = best
            elif best['score'] >= config.FUZZY_MATCH_THRESHOLD:
                self.match_label.config(text=f"? {best['name']}", foreground="orange")
                self.selected_vendor = best
            else:
                self.match_label.config(text="New vendor", foreground="blue")
                self.selected_vendor = None
        else:
            self.match_label.config(text="New vendor", foreground="blue")
            self.selected_vendor = None
    
    def _find_vendor_matches(self, search_text: str) -> List[Dict]:
        """Find vendors matching search text with fuzzy matching."""
        from thefuzz import fuzz
        
        matches = []
        search_lower = search_text.lower()
        
        for vendor in self.all_vendors:
            # Use token_set_ratio for flexible matching
            score = fuzz.token_set_ratio(search_lower, vendor['name'].lower())
            
            # Also check partial ratio for prefix matching (typing as you go)
            partial_score = fuzz.partial_ratio(search_lower, vendor['name'].lower())
            
            # Use the higher of the two scores
            best_score = max(score, partial_score)
            
            if best_score >= 50:  # Low threshold for suggestions
                matches.append({
                    'name': vendor['name'],
                    'score': best_score,
                    'source': vendor['source'],
                    'key': vendor['key'],
                    'data': vendor['data']
                })
        
        # Sort by score descending
        matches.sort(key=lambda x: x['score'], reverse=True)
        
        # Remove duplicates (same vendor might match via name and alias)
        seen_names = set()
        unique_matches = []
        for m in matches:
            if m['name'].lower() not in seen_names:
                seen_names.add(m['name'].lower())
                unique_matches.append(m)
        
        return unique_matches
    
    def _on_tab_complete(self, event):
        """Tab completion - fill in best match."""
        if self.selected_vendor:
            self.vendor_entry.delete(0, tk.END)
            self.vendor_entry.insert(0, self.selected_vendor['name'])
            self.match_label.config(text=f"✓ {self.selected_vendor['name']}", foreground="green")
            # Move focus to amount
            self.amount_entry.focus()
            return "break"  # Prevent default tab behavior
        elif self.suggest_list.size() > 0:
            # Use first suggestion
            first = self.suggest_list.get(0)
            # Extract name (before the score percentage)
            name = first.split(' (')[0]
            self.vendor_entry.delete(0, tk.END)
            self.vendor_entry.insert(0, name)
            self._on_vendor_key(event)  # Update match status
            self.amount_entry.focus()
            return "break"
        return None
    
    def _on_vendor_return(self, event):
        """Enter key in vendor field - move to amount."""
        self.amount_entry.focus()
        return "break"
    
    def _on_down_arrow(self, event):
        """Down arrow - focus suggestion list."""
        if self.suggest_list.size() > 0:
            self.suggest_list.focus()
            self.suggest_list.selection_set(0)
            return "break"
        return None
    
    def _on_suggest_select(self, event):
        """Select a vendor from the suggestion list."""
        selection = self.suggest_list.curselection()
        if selection:
            item = self.suggest_list.get(selection[0])
            # Extract name (before the score percentage)
            name = item.split(' (')[0]
            self.vendor_entry.delete(0, tk.END)
            self.vendor_entry.insert(0, name)
            self._on_vendor_key(event)
            self.amount_entry.focus()
    
    def _close_autocomplete(self, event):
        """Close autocomplete popup."""
        self.suggest_list.delete(0, tk.END)
        return "break"
    
    def _set_today(self):
        """Set date to today."""
        self.date_entry.delete(0, tk.END)
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
    
    def _validate_form(self) -> Tuple[bool, str]:
        """Validate form inputs. Returns (is_valid, error_message)."""
        vendor = self.vendor_entry.get().strip()
        if not vendor:
            return False, "Vendor name is required"
        
        amount_str = self.amount_entry.get().strip()
        if not amount_str:
            return False, "Amount is required"
        
        try:
            amount = float(amount_str.replace('$', '').replace(',', ''))
            if amount <= 0:
                return False, "Amount must be positive"
        except ValueError:
            return False, "Invalid amount format"
        
        date_str = self.date_entry.get().strip()
        if date_str:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                return False, "Invalid date format (use YYYY-MM-DD)"
        
        return True, ""
    
    def _save_bill(self):
        """Save current bill entry to file."""
        is_valid, error = self._validate_form()
        if not is_valid:
            messagebox.showerror("Validation Error", error)
            return
        
        vendor = self.vendor_entry.get().strip()
        amount = self.amount_entry.get().strip().replace('$', '').replace(',', '')
        memo = self.memo_entry.get().strip() or config.DEFAULT_MEMO
        bill_date = self.date_entry.get().strip() or date.today().strftime("%Y-%m-%d")
        
        # Format line
        if memo == config.DEFAULT_MEMO and bill_date == date.today().strftime("%Y-%m-%d"):
            line = f"{vendor}, {amount}\n"
        elif bill_date == date.today().strftime("%Y-%m-%d"):
            line = f"{vendor}, {amount}, {memo}\n"
        else:
            line = f"{vendor}, {amount}, {memo}, {bill_date}\n"
        
        # Append to file
        bills_path = Path(config.BILLS_INPUT_PATH)
        bills_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(bills_path, 'a', encoding='utf-8') as f:
            f.write(line)
        
        self.status_var.set(f"Added: {vendor} - ${amount}")
        self._clear_form()
        self._load_current_bills()
        
        # Focus back on vendor entry
        self.vendor_entry.focus()
    
    def _clear_form(self):
        """Clear the entry form."""
        self.vendor_entry.delete(0, tk.END)
        self.amount_entry.delete(0, tk.END)
        self.memo_entry.delete(0, tk.END)
        self.memo_entry.insert(0, config.DEFAULT_MEMO)
        self.date_entry.delete(0, tk.END)
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        self.match_label.config(text="", foreground="gray")
        self.suggest_list.delete(0, tk.END)
        self.selected_vendor = None
        self.vendor_entry.focus()
    
    def _load_current_bills(self):
        """Load and display current bills from file."""
        # Clear treeview
        for item in self.bills_tree.get_children():
            self.bills_tree.delete(item)
        
        bills_path = Path(config.BILLS_INPUT_PATH)
        if not bills_path.exists():
            self.total_label.config(text="Total: $0.00")
            return
        
        total = 0.0
        line_num = 0
        
        with open(bills_path, 'r', encoding='utf-8') as f:
            for line in f:
                line_num += 1
                parsed = parse_input_line(line)
                if parsed:
                    amount_str = f"${parsed['amount']:,.2f}"
                    date_str = parsed['date'].strftime("%Y-%m-%d")
                    self.bills_tree.insert('', 'end', iid=str(line_num), values=(
                        parsed['vendor_name'],
                        amount_str,
                        parsed['memo'],
                        date_str
                    ))
                    total += parsed['amount']
        
        self.total_label.config(text=f"Total: ${total:,.2f}")
    
    def _remove_selected(self):
        """Remove selected bill from the file."""
        selection = self.bills_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a bill to remove")
            return
        
        if not messagebox.askyesno("Confirm", "Remove selected bill(s)?"):
            return
        
        # Get line numbers to remove (1-indexed)
        lines_to_remove = set(int(s) for s in selection)
        
        # Read all lines
        bills_path = Path(config.BILLS_INPUT_PATH)
        with open(bills_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Write back without removed lines
        with open(bills_path, 'w', encoding='utf-8') as f:
            for i, line in enumerate(lines, 1):
                if i not in lines_to_remove:
                    f.write(line)
        
        self._load_current_bills()
        self.status_var.set(f"Removed {len(lines_to_remove)} bill(s)")
    
    def _edit_selected(self):
        """Load selected bill into form for editing."""
        selection = self.bills_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a bill to edit")
            return
        
        if len(selection) > 1:
            messagebox.showwarning("Multiple Selection", "Please select only one bill to edit")
            return
        
        # Get values from treeview
        values = self.bills_tree.item(selection[0])['values']
        
        # Load into form
        self._clear_form()
        self.vendor_entry.insert(0, values[0])
        self.amount_entry.insert(0, values[1].replace('$', '').replace(',', ''))
        self.memo_entry.delete(0, tk.END)
        self.memo_entry.insert(0, values[2])
        self.date_entry.delete(0, tk.END)
        self.date_entry.insert(0, values[3])
        
        # Trigger vendor matching
        self._on_vendor_key(None)
        
        # Remove from file
        line_num = int(selection[0])
        bills_path = Path(config.BILLS_INPUT_PATH)
        with open(bills_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        with open(bills_path, 'w', encoding='utf-8') as f:
            for i, line in enumerate(lines, 1):
                if i != line_num:
                    f.write(line)
        
        self._load_current_bills()
        self.status_var.set("Editing bill - make changes and click Add Bill")
        self.vendor_entry.focus()

    def _preprocess_bills(self):
        """Process all queued bills within the GUI."""
        logger.info("Pre-process bills requested")
        
        # Check for GnuCash lock first
        if gnucash_db.is_gnucash_locked():
            logger.warning("GnuCash is locked - cannot process")
            messagebox.showerror(
                "GnuCash is Running",
                "GnuCash appears to be running (lock file detected).\n\n"
                "Please close GnuCash before processing bills.\n\n"
                f"Lock file: {gnucash_db.get_lock_file_path()}"
            )
            return
        
        # Re-validate schema (accounts may have been moved/renamed since startup)
        logger.info("Re-validating schema before processing...")
        schema = get_schema()
        result = schema.discover()
        
        if not result['valid']:
            logger.warning(f"Schema validation failed: {result['errors']}")
            
            # Check if missing A/P account - we can create it
            if schema.needs_ap_account():
                if messagebox.askyesno(
                    "Create Accounts Payable?",
                    "No Accounts Payable account found in GnuCash.\n\n"
                    "This account is required for vendor bills.\n\n"
                    "Would you like to create it now?\n"
                    f"(Will be created under '{schema.get_account_name('liabilities_parent') or 'Liabilities'}')"
                ):
                    try:
                        ap_guid = gnucash_db.create_ap_account()
                        schema.update_ap_account(ap_guid, "Accounts Payable")
                        messagebox.showinfo("Success", "Accounts Payable account created!")
                        logger.info("A/P account created")
                        # Re-validate
                        result = schema.discover()
                    except Exception as e:
                        logger.error(f"Failed to create A/P: {e}")
                        messagebox.showerror("Error", f"Failed to create A/P account:\n{e}")
                        return
                else:
                    return
            
            # Check if still invalid
            if not result['valid']:
                error_msg = "Cannot process bills - GnuCash setup issues:\n\n"
                for err in result['errors']:
                    error_msg += f"• {err}\n\n"
                error_msg += "Please fix these issues in GnuCash and try again."
                messagebox.showerror("GnuCash Setup Required", error_msg)
                return
        
        # Show warnings if any
        if result['warnings']:
            warn_msg = "GnuCash setup warnings:\n\n"
            for warn in result['warnings']:
                warn_msg += f"• {warn}\n\n"
            warn_msg += "Continue anyway?"
            if not messagebox.askyesno("Warnings", warn_msg):
                return
        
        # Load bills from file
        bills_path = Path(config.BILLS_INPUT_PATH)
        bills = []
        
        if bills_path.exists():
            with open(bills_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parsed = parse_input_line(line)
                    if parsed:
                        bills.append(parsed)
        
        if not bills:
            messagebox.showinfo("No Bills", "There are no bills to process.")
            return
        
        logger.info(f"Processing {len(bills)} bills")
        
        # Show processing dialog
        dialog = ProcessingDialog(
            self.root,
            bills,
            self.vendor_manager,
            self.all_vendors,
            self._on_processing_complete
        )
        dialog.show()
    
    def _on_processing_complete(self, results: Dict):
        """Handle completion of bill processing."""
        success_count = len(results['success'])
        failed_count = len(results['failed'])
        skipped_count = len(results['skipped'])
        
        # Remove successfully processed bills from file
        if results['success']:
            self._remove_processed_bills(results['success'])
        
        # Show summary
        summary = f"Processing Complete!\n\n"
        summary += f"✓ Successful: {success_count}\n"
        summary += f"✗ Failed: {failed_count}\n"
        summary += f"⊘ Skipped: {skipped_count}\n"
        
        if results['failed']:
            summary += f"\nFailed bills remain in queue for retry."
        
        if results['skipped']:
            summary += f"\nSkipped bills remain in queue."
        
        if success_count > 0:
            summary += f"\n\nBills have been entered into GnuCash.\n"
            summary += f"Database: {config.GNUCASH_DB_PATH}"
            
            # Offer to launch GnuCash
            if messagebox.askyesno(
                "Processing Complete",
                summary + "\n\nWould you like to launch GnuCash now?"
            ):
                self._launch_gnucash()
            else:
                messagebox.showinfo("Processing Complete", summary)
        else:
            messagebox.showinfo("Processing Complete", summary)
        
        # Refresh the bills list
        self._load_current_bills()
        
        # Reload vendors in case new ones were created
        self.all_vendors = self._load_all_vendors()
    
    def _remove_processed_bills(self, processed_bills: List[Dict]):
        """Remove successfully processed bills from the input file."""
        bills_path = Path(config.BILLS_INPUT_PATH)
        
        if not bills_path.exists():
            return
        
        # Get vendor names of processed bills
        processed_vendors = {b['vendor_name'].lower() for b in processed_bills}
        
        # Read all lines
        with open(bills_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Write back only unprocessed lines
        with open(bills_path, 'w', encoding='utf-8') as f:
            for line in lines:
                parsed = parse_input_line(line)
                if parsed:
                    # Check if this bill was processed
                    if parsed['vendor_name'].lower() in processed_vendors:
                        # Remove from set so we only remove one instance
                        processed_vendors.discard(parsed['vendor_name'].lower())
                        continue
                f.write(line)
    
    def _launch_gnucash(self):
        """Launch GnuCash application."""
        import subprocess
        import platform
        
        gnucash_path = config.GNUCASH_DB_PATH
        
        try:
            if platform.system() == "Windows":
                # Try to open with associated application
                import os
                os.startfile(str(gnucash_path))
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", str(gnucash_path)])
            else:  # Linux
                subprocess.Popen(["gnucash", str(gnucash_path)])
            
            self.status_var.set("GnuCash launched")
        except Exception as e:
            logger.error(f"Failed to launch GnuCash: {e}")
            messagebox.showerror(
                "Launch Failed",
                f"Could not launch GnuCash:\n{e}\n\n"
                f"Please open manually:\n{gnucash_path}"
            )


def main():
    """Main entry point."""
    root = tk.Tk()
    
    # Set icon if available
    try:
        # You can add an icon file later if desired
        pass
    except:
        pass
    
    app = BillEntryGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
