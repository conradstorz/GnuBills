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
import threading
import queue
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


class VendorSyncProgressDialog:
    """Dialog to show vendor sync progress."""
    
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Vendor Sync Progress")
        self.dialog.geometry("600x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Progress text area
        frame = ttk.Frame(self.dialog, padding=10)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Vendor Sync Progress:", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 5))
        
        self.text = scrolledtext.ScrolledText(frame, wrap="word", height=20, font=('Consolas', 9))
        self.text.pack(fill="both", expand=True)
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(10, 0))
        
        self.close_btn = ttk.Button(btn_frame, text="Close", command=self.close, state="disabled")
        self.close_btn.pack(side="right")
        
        # Status
        self.status_var = tk.StringVar()
        self.status_var.set("Running vendor sync...")
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side="left")
        
        self.is_running = True
        
    def append_text(self, text):
        """Append text to the progress display."""
        self.text.insert("end", text + "\n")
        self.text.see("end")
        self.dialog.update_idletasks()
        
    def set_complete(self, success=True):
        """Mark sync as complete."""
        self.is_running = False
        if success:
            self.status_var.set("✅ Sync completed successfully!")
        else:
            self.status_var.set("❌ Sync completed with errors")
        self.close_btn.config(state="normal")
        
    def close(self):
        """Close the dialog."""
        self.dialog.destroy()


class AccountSelectionDialog:
    """Dialog for selecting expense and checking accounts before processing bills."""
    
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Select Accounts for Bill Processing")
        self.dialog.geometry("600x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.selected_expense_guid = None
        self.selected_checking_guid = None
        self.cancelled = True
        
        self._create_widgets()
        
    def _create_widgets(self):
        """Create dialog widgets."""
        frame = ttk.Frame(self.dialog, padding=20)
        frame.pack(fill="both", expand=True)
        
        # Title
        ttk.Label(
            frame, 
            text="Select accounts for processing bills:",
            font=('TkDefaultFont', 11, 'bold')
        ).pack(anchor="w", pady=(0, 15))
        
        # Expense Account Section
        exp_frame = ttk.LabelFrame(frame, text="Expense Account", padding=10)
        exp_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(exp_frame, text="Select an expense account (non-placeholder):").pack(anchor="w", pady=(0, 5))
        
        self.expense_var = tk.StringVar()
        self.expense_combo = ttk.Combobox(exp_frame, textvariable=self.expense_var, state="readonly", width=70)
        self.expense_combo.pack(fill="x")
        
        # Checking Account Section
        check_frame = ttk.LabelFrame(frame, text="Checking Account", padding=10)
        check_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(check_frame, text="Select a checking account (non-placeholder):").pack(anchor="w", pady=(0, 5))
        
        self.checking_var = tk.StringVar()
        self.checking_combo = ttk.Combobox(check_frame, textvariable=self.checking_var, state="readonly", width=70)
        self.checking_combo.pack(fill="x")
        
        # Status message
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(frame, textvariable=self.status_var, foreground="red")
        self.status_label.pack(fill="x", pady=(0, 10))
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x")
        
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side="right", padx=(5, 0))
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side="right")
        
        # Load accounts
        self._load_accounts()
        
    def _load_accounts(self):
        """Load accounts from database."""
        try:
            # Get expense accounts
            expense_accounts = gnucash_db.get_expense_accounts()
            if not expense_accounts:
                self.status_var.set("⚠️ No expense accounts found. Please create an expense account in GnuCash first.")
                self.expense_combo.config(state="disabled")
            else:
                expense_items = [f"{acc['name']} ({acc['guid'][:8]}...)" for acc in expense_accounts]
                self.expense_combo['values'] = expense_items
                self.expense_accounts = expense_accounts
                if expense_items:
                    self.expense_combo.current(0)
            
            # Get checking accounts
            checking_accounts = gnucash_db.get_checking_accounts()
            if not checking_accounts:
                self.status_var.set("⚠️ No checking accounts found. Please create a checking account in GnuCash first.")
                self.checking_combo.config(state="disabled")
            else:
                checking_items = [f"{acc['name']} ({acc['guid'][:8]}...)" for acc in checking_accounts]
                self.checking_combo['values'] = checking_items
                self.checking_accounts = checking_accounts
                if checking_items:
                    self.checking_combo.current(0)
                    
        except Exception as e:
            logger.error(f"Failed to load accounts: {e}")
            self.status_var.set(f"Error loading accounts: {e}")
    
    def ok(self):
        """OK button handler."""
        # Validate selections
        exp_idx = self.expense_combo.current()
        check_idx = self.checking_combo.current()
        
        if exp_idx < 0:
            self.status_var.set("Please select an expense account")
            return
            
        if check_idx < 0:
            self.status_var.set("Please select a checking account")
            return
        
        # Get selected GUIDs
        self.selected_expense_guid = self.expense_accounts[exp_idx]['guid']
        self.selected_checking_guid = self.checking_accounts[check_idx]['guid']
        self.cancelled = False
        self.dialog.destroy()
    
    def cancel(self):
        """Cancel button handler."""
        self.cancelled = True
        self.dialog.destroy()


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
        
        # Verify/create AP account at startup
        try:
            ap_guid = gnucash_db.ensure_ap_account_exists()
            logger.info(f"AP account verified/created: {ap_guid}")
        except Exception as e:
            logger.error(f"Failed to verify AP account at startup: {e}")
            messagebox.showerror(
                "Database Error",
                f"Could not verify Accounts Payable account:\n{e}\n\nThe application may not function correctly."
            )
        
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
        
        # Create bill line (comma-separated to match parse_input_line format)
        bill_line = f"{vendor_name}, {amount:.2f}, {memo}, {date_str}\n"
        
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
        """Launch the vendor sync utility with progress dialog."""
        logger.debug("Launching Vendor Sync")
        
        # Create progress dialog
        progress = VendorSyncProgressDialog(self.root)
        
        def run_sync():
            """Run vendor sync in a thread."""
            try:
                # Import vendor_sync module
                import vendor_sync
                
                # Create sync utility
                sync_util = vendor_sync.VendorSyncUtility()
                
                # Redirect output to progress dialog
                class ProgressWriter:
                    def __init__(self, dialog):
                        self.dialog = dialog
                        
                    def write(self, text):
                        if text.strip():
                            self.dialog.append_text(text.rstrip())
                            
                    def flush(self):
                        pass
                
                # Temporarily redirect stdout
                import sys
                old_stdout = sys.stdout
                sys.stdout = ProgressWriter(progress)
                
                try:
                    # Run bidirectional sync (default behavior)
                    progress.append_text("🔄 Starting bidirectional vendor sync...")
                    progress.append_text("")
                    
                    success = sync_util.sync_bidirectional(dry_run=False)
                    
                    # Update UI on main thread
                    self.root.after(0, lambda: progress.set_complete(success))
                    self.root.after(100, self._update_vendor_stats)
                    
                    if success:
                        self.root.after(0, lambda: self.status_var.set("✅ Vendor sync completed"))
                    else:
                        self.root.after(0, lambda: self.status_var.set("❌ Vendor sync had errors"))
                        
                finally:
                    # Restore stdout
                    sys.stdout = old_stdout
                    
            except Exception as e:
                logger.error(f"Error during vendor sync: {e}")
                import traceback
                error_msg = f"❌ Error: {e}\n\n{traceback.format_exc()}"
                self.root.after(0, lambda: progress.append_text(error_msg))
                self.root.after(0, lambda: progress.set_complete(False))
                self.root.after(0, lambda: self.status_var.set("❌ Vendor sync failed"))
        
        # Start sync in background thread
        sync_thread = threading.Thread(target=run_sync, daemon=True)
        sync_thread.start()
        
        logger.info("Vendor Sync started in background")

    
    def _launch_bill_processor(self):
        """Launch the bill processor with progress dialog."""
        logger.debug("Launching Bill Processor")
        
        # Check if there are bills to process
        bills_file = Path(config.PROJECT_ROOT) / "data" / "bills_to_process.txt"
        if not bills_file.exists() or bills_file.stat().st_size == 0:
            messagebox.showinfo(
                "No Bills", 
                "There are no bills in the queue to process.\n\nAdd bills first, then click 'Process Bills'."
            )
            return
        
        # Show account selection dialog
        account_dialog = AccountSelectionDialog(self.root)
        self.root.wait_window(account_dialog.dialog)
        
        # If user cancelled, abort
        if account_dialog.cancelled:
            logger.info("Bill processing cancelled by user")
            return
        
        # Get selected accounts
        expense_guid = account_dialog.selected_expense_guid
        checking_guid = account_dialog.selected_checking_guid
        
        logger.info(f"Selected expense account: {expense_guid}")
        logger.info(f"Selected checking account: {checking_guid}")
        
        # Create progress dialog
        progress = VendorSyncProgressDialog(self.root)
        progress.dialog.title("Bill Processing Progress")
        
        def run_bill_processor():
            """Run bill processor in a thread."""
            try:
                # Import required modules
                from vendor_manager import VendorManager
                from utils import parse_input_line, format_currency
                
                # Redirect output to progress dialog
                class ProgressWriter:
                    def __init__(self, dialog):
                        self.dialog = dialog
                        
                    def write(self, text):
                        if text.strip():
                            self.dialog.append_text(text.rstrip())
                            
                    def flush(self):
                        pass
                
                # Temporarily redirect stdout
                import sys
                old_stdout = sys.stdout
                sys.stdout = ProgressWriter(progress)
                
                try:
                    progress.append_text("💳 Starting bill processor...")
                    progress.append_text(f"Input file: {bills_file}")
                    progress.append_text("")
                    
                    # Read and parse bills
                    bills = []
                    with open(bills_file, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            parsed = parse_input_line(line)
                            if parsed:
                                parsed['line_num'] = line_num
                                bills.append(parsed)
                    
                    if not bills:
                        progress.append_text("⚠️  No bills found to process")
                        self.root.after(0, lambda: progress.set_complete(True))
                        return
                    
                    # Show bills
                    total_amount = sum(b['amount'] for b in bills)
                    progress.append_text(f"Found {len(bills)} bill(s) totaling {format_currency(total_amount)}")
                    progress.append_text("")
                    
                    for i, bill in enumerate(bills, 1):
                        progress.append_text(f"  {i}. {bill['vendor_name']}: {format_currency(bill['amount'])}")
                    
                    progress.append_text("")
                    progress.append_text("Processing bills...")
                    progress.append_text("")
                    
                    # Ensure Accounts Payable account exists before processing bills
                    try:
                        ap_guid = gnucash_db.ensure_ap_account_exists()
                        progress.append_text("✓ Accounts Payable account ready")
                        progress.append_text("")
                    except Exception as e:
                        progress.append_text(f"✗ Could not create/find Accounts Payable account: {e}")
                        self.root.after(0, lambda: progress.set_complete(False))
                        return
                    
                    # Process bills (non-interactive mode)
                    vendor_manager = VendorManager()
                    results = {'total': len(bills), 'success': 0, 'failed': 0, 'skipped': 0}
                    
                    for bill in bills:
                        try:
                            # NOTE: This is simplified non-interactive processing
                            # It will skip vendors that don't exist rather than prompting
                            vendor_name = bill['vendor_name']
                            amount = bill['amount']
                            memo = bill['memo']
                            bill_date = bill['date']
                            
                            progress.append_text(f"Processing: {vendor_name}")
                            
                            # Find vendor
                            vendor_data, match_type = vendor_manager.find_vendor(vendor_name)
                            
                            if vendor_data:
                                progress.append_text(f"  ✓ Found vendor: {vendor_data.get('display_name')} ({match_type} match)")
                                
                                # Get vendor GUID
                                vendor_guid = vendor_data.get('gnucash_guid')
                                if not vendor_guid:
                                    # Try to find in GnuCash by name
                                    gc_vendor = gnucash_db.find_vendor_by_name(vendor_data.get('display_name'))
                                    if gc_vendor:
                                        vendor_guid = gc_vendor['guid']
                                    else:
                                        progress.append_text(f"  ✗ Could not find vendor GUID")
                                        results['failed'] += 1
                                        progress.append_text("")
                                        continue
                                
                                # Use the user-selected expense account for all bills
                                expense_acct_guid = expense_guid
                                
                                # Create the bill
                                bill_guid = gnucash_db.create_posted_bill(
                                    vendor_guid=vendor_guid,
                                    expense_account_guid=expense_acct_guid,
                                    amount=amount,
                                    memo=memo,
                                    bill_date=bill_date
                                )
                                
                                if bill_guid:
                                    progress.append_text(f"  ✓ Bill created successfully ({format_currency(amount)})")
                                    results['success'] += 1
                                else:
                                    progress.append_text(f"  ✗ Failed to create bill")
                                    results['failed'] += 1
                            else:
                                progress.append_text(f"  ⚠️  Vendor not found - skipping")
                                progress.append_text(f"     Use 'Manage Vendors' to create '{vendor_name}' first")
                                results['skipped'] += 1
                            
                            progress.append_text("")
                            
                        except Exception as e:
                            progress.append_text(f"  ✗ Error: {e}")
                            results['failed'] += 1
                            progress.append_text("")
                    
                    # Show summary
                    progress.append_text("=" * 50)
                    progress.append_text("PROCESSING COMPLETE")
                    progress.append_text("=" * 50)
                    progress.append_text(f"Total bills: {results['total']}")
                    progress.append_text(f"Successful:  {results['success']}")
                    progress.append_text(f"Failed:      {results['failed']}")
                    progress.append_text(f"Skipped:     {results['skipped']}")
                    
                    success = results['failed'] == 0 and results['skipped'] == 0
                    
                    if results['success'] > 0:
                        progress.append_text("")
                        progress.append_text("✓ Bills are ready in GnuCash for payment!")
                        progress.append_text("  Open GnuCash -> Business -> Vendor -> Pay Bill")
                        
                        # Clear the bills file after successful processing
                        if success:
                            try:
                                bills_file.unlink(missing_ok=True)
                                progress.append_text("")
                                progress.append_text("✓ Bills file cleared")
                                logger.info("Cleared bills_to_process.txt after successful processing")
                            except Exception as e:
                                logger.error(f"Failed to clear bills file: {e}")
                                progress.append_text(f"⚠️  Could not clear bills file: {e}")
                    
                    # Update UI on main thread
                    self.root.after(0, lambda: progress.set_complete(success))
                    self.root.after(100, self._load_current_bills)  # Refresh bill list
                    
                    if success:
                        self.root.after(0, lambda: self.status_var.set("✅ Bills processed successfully"))
                    else:
                        self.root.after(0, lambda: self.status_var.set("⚠️  Some bills were skipped or failed"))
                        
                finally:
                    # Restore stdout
                    sys.stdout = old_stdout
                    
            except Exception as e:
                logger.error(f"Error during bill processing: {e}")
                import traceback
                error_msg = f"❌ Error: {e}\n\n{traceback.format_exc()}"
                self.root.after(0, lambda: progress.append_text(error_msg))
                self.root.after(0, lambda: progress.set_complete(False))
                self.root.after(0, lambda: self.status_var.set("❌ Bill processing failed"))
        
        # Start processing in background thread
        processor_thread = threading.Thread(target=run_bill_processor, daemon=True)
        processor_thread.start()
        
        logger.info("Bill Processor started in background")


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