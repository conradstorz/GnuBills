"""
Bill Entry GUI - Interactive tool for building bills_to_process.txt

Features:
- Real-time fuzzy matching as you type vendor names
- Tab completion from known vendors
- Validation of entries
- View and edit current bills queue
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sys
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Optional, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import config
import gnucash_db
from utils import fuzzy_match_vendor, strip_vendor_name, parse_input_line
from vendor_manager import VendorManager


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
        
        # Load vendor data
        self.vendor_manager = VendorManager()
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
