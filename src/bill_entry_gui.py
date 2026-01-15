"""
Bill Entry GUI - Simple tool for building bills_to_process.txt

Features:
- Simple form for entering bill data
- Direct writing to bills_to_process.txt
- Launch external tools for vendor management and database operations
- View and edit current bills queue
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Optional
from loguru import logger

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import config
from utils import parse_input_line
from logging_setup import setup_logging_for_script, log_function_entry, log_function_exit, log_stage
import vendor_manager
import gnucash_db


class SimpleBillEntryGUI:
    """Simple GUI application for bill entry - no database operations."""
    
    def __init__(self, root: tk.Tk):
        log_function_entry("SimpleBillEntryGUI.__init__")
        logger.info("Initializing Simple Bill Entry GUI application")
        
        self.root = root
        self.root.title("Simple Bill Entry - GnuCash Bills")
        self.root.geometry("800x700")
        self.root.minsize(600, 500)
        
        # Status
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        self.vendor_stats_var = tk.StringVar()
        self.vendor_stats_var.set("Vendors: Loading...")
        
        # Build UI
        self._create_widgets()
        self._load_current_bills()
        self._update_vendor_stats()  # Load vendor statistics
        
        # Bind keyboard shortcuts
        self.root.bind('<Control-s>', lambda e: self._save_bill())
        self.root.bind('<Control-n>', lambda e: self._clear_form())
        
        log_function_exit("SimpleBillEntryGUI.__init__")
    
    def _create_widgets(self):
        """Create the main GUI elements."""
        log_function_entry("SimpleBillEntryGUI._create_widgets")
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # === Bill Entry Form ===
        entry_frame = ttk.LabelFrame(main_frame, text="Enter New Bill", padding="10")
        entry_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        entry_frame.columnconfigure(1, weight=1)
        
        # Vendor name
        ttk.Label(entry_frame, text="Vendor Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.vendor_entry = ttk.Entry(entry_frame, width=50, font=('TkDefaultFont', 10))
        self.vendor_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)
        self.vendor_entry.focus()
        
        # Amount
        ttk.Label(entry_frame, text="Amount:").grid(row=1, column=0, sticky="w", pady=5)
        self.amount_entry = ttk.Entry(entry_frame, width=20)
        self.amount_entry.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=5)
        
        # Memo
        ttk.Label(entry_frame, text="Memo:").grid(row=2, column=0, sticky="w", pady=5)
        self.memo_entry = ttk.Entry(entry_frame, width=50)
        self.memo_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Date
        ttk.Label(entry_frame, text="Date:").grid(row=3, column=0, sticky="w", pady=5)
        date_frame = ttk.Frame(entry_frame)
        date_frame.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=5)
        
        self.date_entry = ttk.Entry(date_frame, width=15)
        self.date_entry.pack(side="left")
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        
        ttk.Button(date_frame, text="Today", command=self._set_today, width=8).pack(side="left", padx=(5, 0))
        
        # Buttons
        btn_frame = ttk.Frame(entry_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Save Bill (Ctrl+S)", command=self._save_bill).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Clear (Ctrl+N)", command=self._clear_form).pack(side="left", padx=5)
        
        # === External Tools ===
        tools_frame = ttk.LabelFrame(main_frame, text="External Tools", padding="10")
        tools_frame.grid(row=0, column=2, sticky="new", padx=(10, 0))
        
        ttk.Button(tools_frame, text="🔍 Manage Vendors:\nFind, create,\nand manage vendors", 
                   command=self._launch_address_lookup, width=20).pack(pady=5, fill="x")
        ttk.Button(tools_frame, text="🗃️ Vendor Sync:\nSync Vendor Records\nbetween this tool and\nthe GnuCash Database", 
                   command=self._launch_vendor_sync, width=20).pack(pady=5, fill="x")
        ttk.Button(tools_frame, text="💳 Process Bills:\nCreate queued bills\n in GnuCash database", 
                   command=self._launch_bill_processor, width=20).pack(pady=5, fill="x")
        
        # === Current Bills List ===
        bills_frame = ttk.LabelFrame(main_frame, text="Current Bills Queue", padding="5")
        bills_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        bills_frame.columnconfigure(0, weight=1)
        bills_frame.rowconfigure(0, weight=1)
        
        # Treeview for bills
        columns = ("vendor", "amount", "memo", "date")
        self.bills_tree = ttk.Treeview(bills_frame, columns=columns, show="headings", height=12)
        
        # Configure columns
        self.bills_tree.heading("vendor", text="Vendor")
        self.bills_tree.heading("amount", text="Amount")
        self.bills_tree.heading("memo", text="Memo")
        self.bills_tree.heading("date", text="Date")
        
        self.bills_tree.column("vendor", width=200)
        self.bills_tree.column("amount", width=80, anchor="e")
        self.bills_tree.column("memo", width=250)
        self.bills_tree.column("date", width=80, anchor="center")
        
        self.bills_tree.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbar for treeview
        scrollbar = ttk.Scrollbar(bills_frame, orient="vertical", command=self.bills_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.bills_tree.configure(yscrollcommand=scrollbar.set)
        
        # Bind selection event to show vendor details
        self.bills_tree.bind('<<TreeviewSelect>>', self._on_bill_selected)
        
        # Bills management buttons
        bills_btn_frame = ttk.Frame(bills_frame)
        bills_btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        
        ttk.Button(bills_btn_frame, text="Edit Selected", command=self._edit_selected_bill).pack(side="left", padx=5)
        ttk.Button(bills_btn_frame, text="Delete Selected", command=self._delete_selected_bill).pack(side="left", padx=5)
        ttk.Button(bills_btn_frame, text="Clear All", command=self._clear_all_bills).pack(side="left", padx=5)
        ttk.Button(bills_btn_frame, text="Refresh List", command=self._load_current_bills).pack(side="right", padx=5)
        
        # === Vendor Details Display ===
        details_frame = ttk.LabelFrame(main_frame, text="Vendor Details", padding="10")
        details_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        details_frame.columnconfigure(0, weight=1)
        
        self.vendor_details_text = tk.Text(details_frame, height=8, wrap="word", font=('TkDefaultFont', 9))
        self.vendor_details_text.pack(fill="both", expand=True)
        self.vendor_details_text.insert("1.0", "Select a bill to view vendor details...")
        self.vendor_details_text.config(state="disabled")
        
        # === Status Bar ===
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        
        ttk.Label(status_frame, textvariable=self.status_var, relief="sunken", anchor="w").grid(row=0, column=0, sticky="ew")
        ttk.Label(status_frame, textvariable=self.vendor_stats_var, relief="sunken", anchor="e").grid(row=0, column=1, sticky="ew")
        
        log_function_exit("SimpleBillEntryGUI._create_widgets")
    
    def _set_today(self):
        """Set date entry to today."""
        logger.debug("Setting date to today")
        self.date_entry.delete(0, tk.END)
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
    
    def _save_bill(self):
        """Save current bill to bills_to_process.txt."""
        log_function_entry("SimpleBillEntryGUI._save_bill")
        
        vendor_name = self.vendor_entry.get().strip()
        amount_str = self.amount_entry.get().strip()
        memo = self.memo_entry.get().strip()
        date_str = self.date_entry.get().strip()
        
        # Basic validation
        if not vendor_name:
            messagebox.showerror("Error", "Vendor name is required.")
            self.vendor_entry.focus()
            return
        
        if not amount_str:
            messagebox.showerror("Error", "Amount is required.")
            self.amount_entry.focus()
            return
        
        try:
            amount = float(amount_str.replace('$', '').replace(',', ''))
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid amount: {amount_str}")
            self.amount_entry.focus()
            return
        
        if not memo:
            memo = f"Bill from {vendor_name}"
        
        # Validate date
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
            self.date_entry.focus()
            return
        
        # Create bill line
        bill_line = f"{vendor_name}\t{amount:.2f}\t{memo}\t{date_str}\n"
        
        # Append to bills file
        bills_file = Path(config.PROJECT_ROOT) / "data" / "bills_to_process.txt"
        try:
            with open(bills_file, "a", encoding="utf-8") as f:
                f.write(bill_line)
            
            logger.info(f"Bill saved: {vendor_name} - ${amount:.2f}")
            self.status_var.set(f"Bill saved: {vendor_name} - ${amount:.2f}")
            
            # Clear form and reload list
            self._clear_form()
            self._load_current_bills()
            
        except Exception as e:
            logger.error(f"Failed to save bill: {e}")
            messagebox.showerror("Error", f"Failed to save bill: {e}")
        
        log_function_exit("SimpleBillEntryGUI._save_bill")
    
    def _clear_form(self):
        """Clear all form fields."""
        logger.debug("Clearing form fields")
        self.vendor_entry.delete(0, tk.END)
        self.amount_entry.delete(0, tk.END)
        self.memo_entry.delete(0, tk.END)
        self.date_entry.delete(0, tk.END)
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        self.vendor_entry.focus()
        self.status_var.set("Form cleared")
    
    def _load_current_bills(self):
        """Load and display current bills from bills_to_process.txt."""
        log_function_entry("SimpleBillEntryGUI._load_current_bills")
        
        # Clear existing items
        for item in self.bills_tree.get_children():
            self.bills_tree.delete(item)
        
        bills_file = Path(config.PROJECT_ROOT) / "data" / "bills_to_process.txt"
        if not bills_file.exists():
            logger.debug("Bills file does not exist yet")
            self.status_var.set("No bills file found - ready for first bill")
            log_function_exit("SimpleBillEntryGUI._load_current_bills")
            return
        
        try:
            bill_count = 0
            with open(bills_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    try:
                        bill_data = parse_input_line(line)
                        if bill_data:
                            # Add to tree
                            self.bills_tree.insert("", "end", values=(
                                bill_data['vendor_name'],
                                f"${bill_data['amount']:.2f}",
                                bill_data['memo'],
                                bill_data['date']
                            ))
                            bill_count += 1
                    except Exception as e:
                        logger.warning(f"Skipping invalid line {line_num}: {line} - {e}")
            
            logger.info(f"Loaded {bill_count} bills")
            self.status_var.set(f"Loaded {bill_count} bills")
            
        except Exception as e:
            logger.error(f"Error loading bills: {e}")
            messagebox.showerror("Error", f"Error loading bills: {e}")
    
    def _update_vendor_stats(self):
        """Update vendor statistics display."""
        try:
            # Count vendors in JSON
            json_count = 0
            try:
                from vendor_manager import VendorManager
                vendor_mgr = VendorManager()
                json_count = len(vendor_mgr.vendors.get('vendors', {}))
            except Exception as e:
                logger.warning(f"Could not load JSON vendors: {e}")
            
            # Count vendors in GnuCash
            gnucash_count = 0
            try:
                from gnucash_db import get_connection
                with get_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM vendors")
                    gnucash_count = cursor.fetchone()[0]
            except Exception as e:
                logger.warning(f"Could not count GnuCash vendors: {e}")
            
            # Update display
            self.vendor_stats_var.set(f"Vendors: JSON={json_count} | GnuCash={gnucash_count}")
            
        except Exception as e:
            logger.error(f"Error updating vendor stats: {e}")
            self.vendor_stats_var.set("Vendors: Error loading stats")
        
        log_function_exit("SimpleBillEntryGUI._load_current_bills")
    
    def _edit_selected_bill(self):
        """Edit the selected bill."""
        logger.debug("Editing selected bill")
        selection = self.bills_tree.selection()
        if not selection:
            logger.warning("No bill selected for editing")
            messagebox.showwarning("No Selection", "Please select a bill to edit.")
            return
        
        item = selection[0]
        values = self.bills_tree.item(item, "values")
        logger.info(f"Loading bill for editing: vendor={values[0]}, amount={values[1]}")
        
        # Fill form with selected bill data
        self.vendor_entry.delete(0, tk.END)
        self.vendor_entry.insert(0, values[0])
        
        self.amount_entry.delete(0, tk.END)
        amount_str = values[1].replace('$', '')
        self.amount_entry.insert(0, amount_str)
        
        self.memo_entry.delete(0, tk.END)
        self.memo_entry.insert(0, values[2])
        
        self.date_entry.delete(0, tk.END)
        self.date_entry.insert(0, values[3])
        
        # Remove from list (will be re-added when saved)
        self._delete_selected_bill_from_file(item)
        
        self.status_var.set(f"Editing bill: {values[0]}")
    
    def _delete_selected_bill(self):
        """Delete the selected bill."""
        logger.debug("Attempting to delete selected bill")
        selection = self.bills_tree.selection()
        if not selection:
            logger.warning("No bill selected for deletion")
            messagebox.showwarning("No Selection", "Please select a bill to delete.")
            return
        
        item = selection[0]
        values = self.bills_tree.item(item, "values")
        logger.info(f"Prompting to delete bill: vendor={values[0]}, amount={values[1]}")
        
        if messagebox.askyesno("Confirm Delete", f"Delete bill for {values[0]} - {values[1]}?"):
            logger.info(f"Deleting bill for vendor: {values[0]}")
            self._delete_selected_bill_from_file(item)
            self.status_var.set(f"Deleted bill: {values[0]}")
    
    def _delete_selected_bill_from_file(self, tree_item):
        """Remove the selected bill from the file."""
        logger.debug("Removing bill from file")
        values = self.bills_tree.item(tree_item, "values")
        vendor_name = values[0]
        amount_str = values[1].replace('$', '')
        memo = values[2]
        date_str = values[3]
        
        bills_file = Path(config.PROJECT_ROOT) / "data" / "bills_to_process.txt"
        
        try:
            # Read all lines
            lines = []
            with open(bills_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Find and remove matching line
            new_lines = []
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                
                try:
                    bill_data = parse_input_line(line_stripped)
                    if (bill_data and 
                        bill_data['vendor_name'] == vendor_name and
                        f"{bill_data['amount']:.2f}" == amount_str and
                        bill_data['memo'] == memo and
                        bill_data['date'] == date_str):
                        # Skip this line (delete it)
                        continue
                except:
                    pass
                
                new_lines.append(line)
            
            # Write back to file
            with open(bills_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            
            # Remove from tree
            self.bills_tree.delete(tree_item)
            
        except Exception as e:
            logger.error(f"Error deleting bill: {e}")
            messagebox.showerror("Error", f"Error deleting bill: {e}")
    
    def _clear_all_bills(self):
        """Clear all bills from the file."""
        logger.debug("Clear all bills requested")
        if messagebox.askyesno("Confirm Clear All", "Delete ALL bills from the queue?"):
            logger.warning("Clearing all bills from queue")
            bills_file = Path(config.PROJECT_ROOT) / "data" / "bills_to_process.txt"
            try:
                bills_file.unlink(missing_ok=True)
                self._load_current_bills()
                self.status_var.set("All bills cleared")
            except Exception as e:
                logger.error(f"Error clearing bills: {e}")
                messagebox.showerror("Error", f"Error clearing bills: {e}")
    
    def _on_bill_selected(self, event):
        """Handle bill selection - display vendor details."""
        logger.debug("Bill selection changed")
        selection = self.bills_tree.selection()
        if not selection:
            # Clear vendor details
            self.vendor_details_text.config(state="normal")
            self.vendor_details_text.delete("1.0", "end")
            self.vendor_details_text.insert("1.0", "Select a bill to view vendor details...")
            self.vendor_details_text.config(state="disabled")
            return
        
        item = selection[0]
        values = self.bills_tree.item(item, "values")
        vendor_name = values[0]
        logger.info(f"Loading vendor details for: {vendor_name}")
        
        # Update display
        self.vendor_details_text.config(state="normal")
        self.vendor_details_text.delete("1.0", "end")
        
        try:
            # Load vendor manager
            vm = vendor_manager.VendorManager()
            
            # Search for vendor
            vendor_data, match_type = vm.find_vendor(vendor_name)
            
            # Build details text
            details = f"Vendor: {vendor_name}\n"
            details += "=" * 60 + "\n\n"
            
            if vendor_data:
                details += f"✅ FOUND in database ({match_type} match)\n\n"
                details += f"Display Name: {vendor_data.get('display_name', 'N/A')}\n"
                details += f"GnuCash GUID: {vendor_data.get('gnucash_guid', 'Not set')}\n"
                details += f"GnuCash ID: {vendor_data.get('gnucash_id', 'Not set')}\n\n"
                
                # Address info
                details += "Address:\n"
                addr_name = vendor_data.get('addr_name', '')
                addr_line1 = vendor_data.get('addr_line1', '')
                addr_line2 = vendor_data.get('addr_line2', '')
                phone = vendor_data.get('phone', '')
                
                if addr_name:
                    details += f"  {addr_name}\n"
                if addr_line1:
                    details += f"  {addr_line1}\n"
                if addr_line2:
                    details += f"  {addr_line2}\n"
                if phone:
                    details += f"  Phone: {phone}\n"
                if not (addr_name or addr_line1 or addr_line2):
                    details += "  (No address on file)\n"
                
                details += f"\nExpense Account: {vendor_data.get('expense_account', 'Not set')}\n"
                
                # Check if vendor exists in GnuCash
                if vendor_data.get('gnucash_guid'):
                    try:
                        gc_vendor = gnucash_db.find_vendor_by_guid(vendor_data['gnucash_guid'])
                        if gc_vendor:
                            details += "\n✅ Verified in GnuCash database\n"
                        else:
                            details += "\n⚠️ GUID exists but vendor not found in GnuCash database\n"
                    except Exception as e:
                        details += f"\n⚠️ Error checking GnuCash: {e}\n"
                else:
                    details += "\n❌ Not yet created in GnuCash database\n"
            else:
                details += "❌ NOT FOUND in vendor database\n\n"
                details += "This vendor does not exist in the system yet.\n"
                details += "Use 'Vendor Manager' to create this vendor before processing bills.\n"
            
            self.vendor_details_text.insert("1.0", details)
            
        except Exception as e:
            error_msg = f"Error loading vendor details:\n{e}"
            logger.error(error_msg)
            self.vendor_details_text.insert("1.0", error_msg)
        
        self.vendor_details_text.config(state="disabled")
    
    def _launch_address_lookup(self):
        """Launch the vendor manager GUI with selected vendor if available."""
        logger.debug("Launching Vendor Manager")
        try:
            script_path = Path(__file__).parent / "vendor_manager_gui.py"
            
            # Get selected vendor from the bills queue
            vendor_name = None
            selection = self.bills_tree.selection()
            if selection:
                item = self.bills_tree.item(selection[0])
                vendor_name = item['values'][0]  # First column is vendor name
            
            # Launch with vendor name if available
            cmd = [sys.executable, str(script_path)]
            if vendor_name:
                cmd.append(vendor_name)
                logger.info(f"Launching Vendor Manager for vendor: {vendor_name}")
                self.status_var.set(f"Launched Vendor Manager for {vendor_name}")
            else:
                logger.info("Launching Vendor Manager (no vendor selected)")
                self.status_var.set("Launched Vendor Manager")
            
            subprocess.Popen(cmd, cwd=str(Path(__file__).parent))
            
        except Exception as e:
            logger.error(f"Error launching vendor manager: {e}")
            messagebox.showerror("Error", f"Could not launch vendor manager: {e}")
    
    def _launch_vendor_sync(self):
        """Launch the vendor sync utility."""
        logger.debug("Launching Vendor Sync")
        try:
            script_path = Path(__file__).parent / "vendor_sync.py"
            subprocess.Popen([sys.executable, str(script_path)], cwd=str(Path(__file__).parent))
            logger.info("Vendor Sync launched successfully")
            self.status_var.set("Launched Vendor Sync")
            # Update stats after a brief delay to allow sync to complete
            self.root.after(2000, self._update_vendor_stats)
        except Exception as e:
            logger.error(f"Error launching vendor sync: {e}")
            messagebox.showerror("Error", f"Could not launch vendor sync: {e}")
    
    def _launch_bill_processor(self):
        """Launch the bill processor."""
        logger.debug("Launching Bill Processor")
        try:
            script_path = Path(__file__).parent / "bill_processor.py"
            subprocess.Popen([sys.executable, str(script_path)], cwd=str(Path(__file__).parent))
            logger.info("Bill Processor launched successfully")
            self.status_var.set("Launched Bill Processor")
        except Exception as e:
            logger.error(f"Error launching bill processor: {e}")
            messagebox.showerror("Error", f"Could not launch bill processor: {e}")


def main():
    """Main function."""
    # Set up logging
    setup_logging_for_script("simple_bill_entry_gui")
    
    log_stage("Starting Simple Bill Entry GUI")
    
    root = tk.Tk()
    app = SimpleBillEntryGUI(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        raise
    finally:
        logger.info("Simple Bill Entry GUI application ended")


if __name__ == "__main__":
    main()