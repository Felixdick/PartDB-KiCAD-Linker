import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, Toplevel, Listbox, Scrollbar
import configparser
import os
import subprocess
import sys
import threading

# Import the new generator class
# This assumes generate_kicad_library.py is in the same directory
try:
    from generate_kicad_library import KiCadLibraryGenerator, GeneratorException
except ImportError:
    messagebox.showerror(
        "Error", 
        "Could not find 'generate_kicad_library.py'.\n"
        "Please make sure it is in the same directory as this GUI."
    )
    sys.exit()


CONFIG_FILE = 'config.ini'

class ChangesPopup(Toplevel):
    """
    A popup window to show new and modified parts and let the user
    select which ones to apply.
    """
    def __init__(self, parent, controller, new_parts, modified_parts):
        super().__init__(parent)
        self.title("Review Library Changes")
        self.transient(parent)
        self.grab_set()
        self.geometry("800x600")

        self.controller = controller
        
        # self.all_parts maps the unique display name to its (part_object, category_name)
        self.all_parts = {}
        self.categories = set()
        self.selected_parts = []
        
        # --- Create Frames ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        main_frame.rowconfigure(2, weight=1) # Row for listbox is expandable
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=0) # Button column
        main_frame.columnconfigure(2, weight=1)

        # --- Populate internal data from parts ---
        self.build_internal_part_list(new_parts, modified_parts)

        # --- Left Listbox (Available) ---
        ttk.Label(main_frame, text="Available Changes").grid(row=0, column=0, sticky="nsw", pady=(0, 5))
        
        # --- NEW: Category Filter Dropdown ---
        self.category_var = tk.StringVar(value="All Categories")
        self.category_cb = ttk.Combobox(
            main_frame, 
            textvariable=self.category_var, 
            state="readonly",
            values=["All Categories"] + sorted(list(self.categories))
        )
        self.category_cb.grid(row=1, column=0, sticky="new", pady=(0, 5))
        self.category_cb.bind('<<ComboboxSelected>>', self.refilter_lists)

        left_frame = ttk.Frame(main_frame, borderwidth=1, relief="sunken")
        left_frame.grid(row=2, column=0, sticky="nsew", rowspan=2)
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)

        self.available_list_lb = Listbox(left_frame, selectmode="extended", exportselection=False)
        self.available_list_lb.grid(row=0, column=0, sticky="nsew")
        
        available_scroll_y = Scrollbar(left_frame, orient="vertical", command=self.available_list_lb.yview)
        available_scroll_y.grid(row=0, column=1, sticky="ns")
        self.available_list_lb.config(yscrollcommand=available_scroll_y.set)
        
        # --- Center Buttons ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=1, padx=10, pady=10, sticky="n") # Changed to row 2

        ttk.Button(button_frame, text="Add >", command=self.move_to_apply).pack(pady=5)
        ttk.Button(button_frame, text="< Remove", command=self.move_to_available).pack(pady=5)
        ttk.Button(button_frame, text="Add All >>", command=self.move_all_to_apply).pack(pady=20)
        ttk.Button(button_frame, text="<< Remove All", command=self.move_all_to_available).pack(pady=5)

        # --- Right Listbox (To Apply) ---
        ttk.Label(main_frame, text="Changes to Apply").grid(row=0, column=2, sticky="nsw", pady=(0, 5))
        # Note: Right listbox (col 2) spans rows 1 and 2 to align with filter+list on left
        right_frame = ttk.Frame(main_frame, borderwidth=1, relief="sunken")
        right_frame.grid(row=1, column=2, sticky="nsew", rowspan=3) # Spans 3 rows
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)

        self.apply_list_lb = Listbox(right_frame, selectmode="extended", exportselection=False)
        self.apply_list_lb.grid(row=0, column=0, sticky="nsew")
        
        apply_scroll_y = Scrollbar(right_frame, orient="vertical", command=self.apply_list_lb.yview)
        apply_scroll_y.grid(row=0, column=1, sticky="ns")
        self.apply_list_lb.config(yscrollcommand=apply_scroll_y.set)

        # --- Bottom Buttons (Apply/Cancel) ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=4, column=0, columnspan=3, sticky="e", pady=(10, 0)) # Changed to row 4
        
        self.status_label = ttk.Label(bottom_frame, text="")
        self.status_label.pack(side="left", fill="x", expand=True, padx=5)

        ttk.Button(bottom_frame, text="Apply Changes", command=self.apply_changes).pack(side="right", padx=5)
        ttk.Button(bottom_frame, text="Cancel", command=self.destroy).pack(side="right")
        
        # --- Populate the listbox after all widgets are created ---
        self.refilter_lists()
        
    def build_internal_part_list(self, new_parts, modified_parts):
        """Populates self.all_parts and self.categories."""
        for part in new_parts:
            category_name = part.category.get('name', 'N/A')
            display_name = f"[NEW] {part.name} (Cat: {category_name})"
            self.all_parts[display_name] = (part, category_name)
            self.categories.add(category_name)
            
        for part in modified_parts:
            category_name = part.category.get('name', 'N/A')
            display_name = f"[MOD] {part.name} (Cat: {category_name})"
            self.all_parts[display_name] = (part, category_name)
            self.categories.add(category_name)

    def refilter_lists(self, event=None):
        """
        Clears and repopulates the 'Available' list based on the
        selected category and what's in the 'Apply' list.
        """
        selected_category = self.category_var.get()
        items_to_apply = set(self.apply_list_lb.get(0, "end"))
        
        self.available_list_lb.delete(0, "end")
        
        # Sort keys to ensure consistent order
        for display_name in sorted(self.all_parts.keys()):
            if display_name in items_to_apply:
                continue # Skip items already in the right-hand list
            
            part_obj, part_cat = self.all_parts[display_name]
            
            if selected_category == "All Categories" or selected_category == part_cat:
                self.available_list_lb.insert("end", display_name)

    def move_items(self, from_lb, to_lb):
        """Helper to move selected items from one listbox to another."""
        selected_indices = from_lb.curselection()
        for index in reversed(selected_indices):
            item_text = from_lb.get(index)
            to_lb.insert("end", item_text)
            from_lb.delete(index)

    def move_to_apply(self):
        """Move selected items from Available to Apply."""
        self.move_items(self.available_list_lb, self.apply_list_lb)
        
    def move_to_available(self):
        """Move selected items from Apply back to Available."""
        # This is more complex because we must respect the filter
        selected_indices = self.apply_list_lb.curselection()
        selected_category = self.category_var.get()
        
        for index in reversed(selected_indices):
            item_text = self.apply_list_lb.get(index)
            part_obj, part_cat = self.all_parts[item_text]
            
            # Only add back to list if it matches the current filter
            if selected_category == "All Categories" or selected_category == part_cat:
                self.available_list_lb.insert("end", item_text)
                
            self.apply_list_lb.delete(index)
            
        # We may need to re-sort the available list, but for now this is fine.

    def move_all_to_apply(self):
        """Moves all *visible* items from Available to Apply."""
        items_to_move = self.available_list_lb.get(0, "end")
        for item_text in items_to_move:
            self.apply_list_lb.insert("end", item_text)
        self.available_list_lb.delete(0, "end")

    def move_all_to_available(self):
        """Moves all items from Apply back to Available, respecting filter."""
        # Easiest way is to clear the apply list and just re-filter
        self.apply_list_lb.delete(0, "end")
        self.refilter_lists()

    def apply_changes(self):
        """Gathers the final list of parts and tells the controller to write them."""
        item_texts = self.apply_list_lb.get(0, "end")
        if not item_texts:
            messagebox.showwarning("No Changes", "No changes were selected to apply.", parent=self)
            return

        # Get the original part_object from the display name
        self.selected_parts = [self.all_parts[text][0] for text in item_texts]
        
        self.status_label.config(text=f"Applying {len(self.selected_parts)} changes...")
        self.update_idletasks() # Force UI update

        try:
            threading.Thread(target=self._run_write_operation, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start write operation:\n{e}", parent=self)
            self.status_label.config(text="Error!")

    def _run_write_operation(self):
        """Worker thread function for writing files."""
        try:
            log_messages = self.controller.write_selected_parts(self.selected_parts)
            self.after(0, self.on_write_complete, log_messages)
            
        except GeneratorException as e:
            self.after(0, self.on_write_error, e)
        except Exception as e:
            self.after(0, self.on_write_error, f"An unexpected error occurred:\n{e}")

    def on_write_complete(self, log_messages):
        messagebox.showinfo(
            "Success",
            f"Successfully applied {len(self.selected_parts)} changes.\n\n"
            "Logs:\n" + "\n".join(log_messages),
            parent=self
        )
        self.destroy() # Close the popup

    def on_write_error(self, error):
        messagebox.showerror("Write Error", str(error), parent=self)
        self.status_label.config(text="Write failed. Check logs.")


class ConfigEditor(tk.Tk):
    """
    Main GUI application.
    """
    def __init__(self):
        super().__init__()
        self.title("Part-DB Linker Configuration")
        self.resizable(False, False)

        self.config = configparser.ConfigParser()
        self.generator_controller = None
        
        self.api_url_var = tk.StringVar()
        self.api_token_var = tk.StringVar()
        self.after_date_var = tk.StringVar()
        self.template_file_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()

        self.create_widgets()
        self.load_config()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        # --- PartDB Section ---
        partdb_frame = ttk.LabelFrame(main_frame, text="PartDB Settings", padding="10")
        partdb_frame.pack(fill="x", expand=True, pady=5)
        
        ttk.Label(partdb_frame, text="API Base URL:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(partdb_frame, textvariable=self.api_url_var, width=60).grid(row=0, column=1, sticky="we", padx=5, pady=3)
        ttk.Label(partdb_frame, text="API Token:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(partdb_frame, textvariable=self.api_token_var, width=60).grid(row=1, column=1, sticky="we", padx=5, pady=3)
        ttk.Label(partdb_frame, text="Parts After Date (YYYY-MM-DD):").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(partdb_frame, textvariable=self.after_date_var, width=20).grid(row=2, column=1, sticky="w", padx=5, pady=3)
        partdb_frame.columnconfigure(1, weight=1)

        # --- Paths Section ---
        paths_frame = ttk.LabelFrame(main_frame, text="Path Settings", padding="10")
        paths_frame.pack(fill="x", expand=True, pady=5)
        
        ttk.Label(paths_frame, text="Template File:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(paths_frame, textvariable=self.template_file_var, width=60).grid(row=0, column=1, sticky="we", padx=5, pady=3)
        ttk.Label(paths_frame, text="Output Directory:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(paths_frame, textvariable=self.output_dir_var, width=60).grid(row=1, column=1, sticky="we", padx=5, pady=3)
        paths_frame.columnconfigure(1, weight=1)

        # --- Button Section ---
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        self.status_label = ttk.Label(button_frame, text="")
        self.status_label.pack(side="left", fill="x", expand=True, padx=5)

        self.run_button = ttk.Button(button_frame, text="Run Generator...", command=self.run_generator)
        self.run_button.pack(side="right", padx=5)
        
        self.save_button = ttk.Button(button_frame, text="Save Config", command=self.save_config)
        self.save_button.pack(side="right", padx=5)
        
        self.close_button = ttk.Button(button_frame, text="Close", command=self.destroy)
        self.close_button.pack(side="right")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            self.api_url_var.set("http://localhost:8888")
            self.after_date_var.set("2020-01-01")
            self.template_file_var.set("templates.yaml")
            self.output_dir_var.set("kicad_libs")
            return
        self.config.read(CONFIG_FILE)
        self.api_url_var.set(self.config.get('PartDB', 'API_BASE_URL', fallback='http://localhost:8888'))
        self.api_token_var.set(self.config.get('PartDB', 'API_TOKEN', fallback=''))
        self.after_date_var.set(self.config.get('PartDB', 'PARTS_AFTER_DATE', fallback='2020-01-01'))
        self.template_file_var.set(self.config.get('Paths', 'TEMPLATE_FILE', fallback='templates.yaml'))
        self.output_dir_var.set(self.config.get('Paths', 'OUTPUT_DIR', fallback='kicad_libs'))

    def save_config(self):
        if not self.config.has_section('PartDB'):
            self.config.add_section('PartDB')
        if not self.config.has_section('Paths'):
            self.config.add_section('Paths')
        self.config.set('PartDB', 'API_BASE_URL', self.api_url_var.get())
        self.config.set('PartDB', 'API_TOKEN', self.api_token_var.get())
        self.config.set('PartDB', 'PARTS_AFTER_DATE', self.after_date_var.get())
        self.config.set('Paths', 'TEMPLATE_FILE', self.template_file_var.get())
        self.config.set('Paths', 'OUTPUT_DIR', self.output_dir_var.get())
        try:
            with open(CONFIG_FILE, 'w') as f:
                self.config.write(f)
            self.status_label.config(text="Config saved.")
        except IOError as e:
            messagebox.showerror("Error", f"Could not save configuration:\n{e}")

    def run_generator(self):
        """
        Called by the "Run Generator" button.
        Runs the comparison in a separate thread.
        """
        self.status_label.config(text="Running comparison... Please wait.")
        self.run_button.config(state="disabled")
        self.save_button.config(state="disabled")
        self.close_button.config(state="disabled")
        self.update_idletasks() # Force UI update
        
        try:
            self.generator_controller = KiCadLibraryGenerator(
                api_url=self.api_url_var.get(),
                api_token=self.api_token_var.get(),
                after_date=self.after_date_var.get(),
                template_file=self.template_file_var.get(),
                output_dir=self.output_dir_var.get()
            )
            
            threading.Thread(target=self._run_compare_thread, daemon=True).start()
            
        except Exception as e:
            self.on_generator_error(e)

    def _run_compare_thread(self):
        """Worker thread function for running the comparison."""
        try:
            new_parts, modified_parts = self.generator_controller.run_comparison()
            self.after(0, self.on_compare_complete, new_parts, modified_parts)
            
        except GeneratorException as e:
            self.after(0, self.on_generator_error, e)
        except Exception as e:
            self.after(0, self.on_generator_error, f"An unexpected error occurred:\n{e}")

    def on_compare_complete(self, new_parts, modified_parts):
        """Called by the thread when comparison is done."""
        self.reset_ui()
        
        if not new_parts and not modified_parts:
            self.status_label.config(text="All libraries are up-to-date.")
            messagebox.showinfo("Up to Date", "All KiCad libraries are up-to-date.")
        else:
            self.status_label.config(text=f"Found {len(new_parts)} new, {len(modified_parts)} modified.")
            ChangesPopup(self, self.generator_controller, new_parts, modified_parts)

    def on_generator_error(self, error):
        """Called by the thread if an error occurs."""
        self.reset_ui()
        self.status_label.config(text="Error during generation.")
        messagebox.showerror("Generator Error", str(error))

    def reset_ui(self):
        """Resets the UI back to normal."""
        self.status_label.config(text="")
        self.run_button.config(state="normal")
        self.save_button.config(state="normal")
        self.close_button.config(state="normal")

if __name__ == "__main__":
    app = ConfigEditor()
    app.mainloop()