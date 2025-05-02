# audio_gui.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import queue # For thread-safe GUI updates
import time

# Import the refactored processing function
try:
    # Ensure audio_processing.py is in the same directory or Python path
    from audio_processing import process_audio
    # srt_utils will be used indirectly by audio_processing
    import srt_utils
except ImportError as e:
    messagebox.showerror("Import Error", f"Failed to import required modules: {e}\nMake sure audio_processing.py and srt_utils.py are present.")
    exit()

# Supported Languages (Add more as needed with their ISO 639-1 codes)
SUPPORTED_LANGUAGES = {
    "Japanese": "ja",
    "English": "en",
    "Auto-Detect": "auto", # Using "auto" or similar for clarity, but Groq might expect None or empty string for auto
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Chinese": "zh",
    # Add other languages supported by Whisper/Groq
}
DEFAULT_LANGUAGE = "Japanese"


class AudioProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Groq Audio Processor GUI")
        # self.root.geometry("650x500") # Adjust size if needed

        # --- Variables ---
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.language_var = tk.StringVar(value=DEFAULT_LANGUAGE) # For language dropdown
        self.lengthen_subs_var = tk.BooleanVar(value=True)
        self.delete_segments_var = tk.BooleanVar(value=True)
        self.delete_temp_audio_var = tk.BooleanVar(value=True)
        self.delete_segment_srts_var = tk.BooleanVar(value=True)
        self.model_name_var = tk.StringVar(value="whisper-large-v3") # Keep model fixed for now

        # Use a queue for thread-safe status updates
        self.status_queue = queue.Queue()

        # --- Layout ---
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # --- Input Section ---
        input_frame = ttk.LabelFrame(main_frame, text="Input", padding="10")
        input_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="URL or File Path:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_path_var, width=60)
        self.input_entry.grid(row=0, column=1, padx=5, pady=5, sticky=(tk.W, tk.E))
        self.browse_input_btn = ttk.Button(input_frame, text="Browse File...", command=self.browse_input_file)
        self.browse_input_btn.grid(row=0, column=2, padx=5, pady=5)

        # --- Output Section ---
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding="10")
        output_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        output_frame.columnconfigure(1, weight=1)

        ttk.Label(output_frame, text="Output SRT File:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_path_var, width=60)
        self.output_entry.grid(row=0, column=1, padx=5, pady=5, sticky=(tk.W, tk.E))
        self.browse_output_btn = ttk.Button(output_frame, text="Select Output...", command=self.browse_output_file)
        self.browse_output_btn.grid(row=0, column=2, padx=5, pady=5)

        # --- Options Section ---
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        # Language Selection
        ttk.Label(options_frame, text="Language:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.language_dropdown = ttk.Combobox(options_frame, textvariable=self.language_var, values=list(SUPPORTED_LANGUAGES.keys()), state="readonly")
        self.language_dropdown.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        self.language_dropdown.set(DEFAULT_LANGUAGE) # Set default selection

        # Lengthen Checkbox
        self.lengthen_check = ttk.Checkbutton(options_frame, text="Lengthen Subtitles (Merge short blocks)", variable=self.lengthen_subs_var)
        self.lengthen_check.grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        # Cleanup Options
        ttk.Label(options_frame, text="Cleanup:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.del_segments_check = ttk.Checkbutton(options_frame, text="Delete Segment MP3s", variable=self.delete_segments_var)
        self.del_segments_check.grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.del_temp_audio_check = ttk.Checkbutton(options_frame, text="Delete Downloaded MP3", variable=self.delete_temp_audio_var)
        self.del_temp_audio_check.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        self.del_segment_srts_check = ttk.Checkbutton(options_frame, text="Delete Segment SRTs", variable=self.delete_segment_srts_var)
        self.del_segment_srts_check.grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)


        # --- Controls ---
        control_frame = ttk.Frame(main_frame, padding="10")
        control_frame.grid(row=3, column=0, columnspan=3, pady=10)

        self.start_button = ttk.Button(control_frame, text="Start Processing", command=self.start_processing_thread)
        self.start_button.pack()

        # --- Status Area ---
        status_frame = ttk.LabelFrame(main_frame, text="Status Log", padding="10")
        status_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1) # Make status area expand vertically

        self.status_text = tk.Text(status_frame, height=10, wrap=tk.WORD, state=tk.DISABLED, borderwidth=1, relief="solid")
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.status_text['yscrollcommand'] = scrollbar.set

        # Start checking the queue for status updates
        self.check_status_queue()

    def browse_input_file(self):
        filepath = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.ogg"), ("All Files", "*.*")]
        )
        if filepath:
            self.input_path_var.set(filepath)
            # Auto-populate output path based on input filename
            base = os.path.splitext(filepath)[0]
            self.output_path_var.set(base + ".srt")


    def browse_output_file(self):
        # Suggest filename based on input if possible
        initial_dir = os.path.dirname(self.output_path_var.get()) if self.output_path_var.get() else "."
        initial_file = os.path.basename(self.output_path_var.get()) if self.output_path_var.get() else "output.srt"

        filepath = filedialog.asksaveasfilename(
            title="Select Output SRT File",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=".srt",
            filetypes=[("SRT Subtitles", "*.srt"), ("All Files", "*.*")]
        )
        if filepath:
            self.output_path_var.set(filepath)

    def update_status(self, message):
        """Appends a message to the status text box (thread-safe)."""
        if self.status_text.winfo_exists(): # Check if widget still exists
            self.status_text.config(state=tk.NORMAL)
            self.status_text.insert(tk.END, message + "\n")
            self.status_text.see(tk.END) # Scroll to the end
            self.status_text.config(state=tk.DISABLED)

    def check_status_queue(self):
        """Periodically check the queue for messages from the worker thread."""
        try:
            while True:
                message = self.status_queue.get_nowait()
                self.update_status(message)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error in check_status_queue: {e}") # Log errors in the poller
        finally:
            # Schedule the next check if the window is still open
            if self.root.winfo_exists():
                 self.root.after(100, self.check_status_queue)

    def queue_status_update(self, message):
        """Callback function to be passed to the worker thread."""
        self.status_queue.put(message)

    def start_processing_thread(self):
        input_path = self.input_path_var.get().strip()
        output_path = self.output_path_var.get().strip()
        selected_language_name = self.language_var.get()

        if not input_path:
            messagebox.showerror("Input Missing", "Please provide an input URL or file path.")
            return
        if not output_path:
            messagebox.showerror("Output Missing", "Please select an output SRT file path.")
            return
        if not selected_language_name:
             messagebox.showerror("Language Missing", "Please select a language.")
             return

        if not output_path.lower().endswith(".srt"):
             # Automatically add .srt if missing
             output_path += ".srt"
             self.output_path_var.set(output_path)
             messagebox.showwarning("File Extension", f"Output filename automatically set to:\n{output_path}")


        # Get language code from selected name
        language_code = SUPPORTED_LANGUAGES.get(selected_language_name)
        # Handle 'Auto-Detect' - Groq might expect None or empty string. Test what works.
        # Let's pass None if 'auto' is selected, assuming the API handles it.
        if language_code == "auto":
             language_code = None # Or potentially "" if None causes issues

        # Disable button during processing
        self.start_button.config(state=tk.DISABLED)
        self.update_status("-----\nStarting new processing job...")

        # Get options
        lengthen = self.lengthen_subs_var.get()
        del_segments = self.delete_segments_var.get()
        del_temp_audio = self.delete_temp_audio_var.get()
        del_seg_srts = self.delete_segment_srts_var.get()
        model = self.model_name_var.get()

        # Clear status area for new job
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete('1.0', tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.update_status(f"Input: {input_path}")
        self.update_status(f"Output: {output_path}")
        self.update_status(f"Language: {selected_language_name} ({language_code if language_code else 'Auto'})")
        self.update_status(f"Model: {model}")
        self.update_status(f"Lengthen: {lengthen}, Cleanup SegMP3: {del_segments}, Cleanup DL: {del_temp_audio}, Cleanup SegSRT: {del_seg_srts}")
        self.update_status("---")


        # Run processing in a separate thread
        self.processing_thread = threading.Thread(
            target=self.run_processing,
            args=(input_path, output_path, model, language_code, lengthen, del_segments, del_temp_audio, del_seg_srts),
            daemon=True # Allows closing app even if thread is stuck (use with caution)
        )
        self.processing_thread.start()

    def run_processing(self, input_path, output_path, model, language_code, lengthen, del_segments, del_temp_audio, del_seg_srts):
        """Worker function that runs in the thread."""
        start_time = time.time()
        try:
            success = process_audio(
                input_path=input_path,
                output_srt_filepath=output_path,
                model_name=model,
                language=language_code, # Pass the language code
                status_callback=self.queue_status_update, # Pass the queueing function
                lengthen_subtitles_flag=lengthen,
                delete_segments_flag=del_segments,
                delete_temp_audio_flag=del_temp_audio,
                delete_segment_srts_flag=del_seg_srts
            )

            end_time = time.time()
            duration = end_time - start_time
            # Final status update via queue
            if success:
                final_message = f"--- PROCESSING FINISHED SUCCESSFULLY (Duration: {duration:.2f}s) ---"
                self.queue_status_update(final_message)
                # Schedule messagebox on main thread
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Processing complete!\nSRT saved to:\n{output_path}\n\nDuration: {duration:.2f} seconds"))
            else:
                final_message = f"--- PROCESSING FAILED (Duration: {duration:.2f}s) ---"
                self.queue_status_update(final_message)
                # Schedule messagebox on main thread
                self.root.after(0, lambda: messagebox.showerror("Error", "Processing failed. Check status log for details."))

        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            # Catch any unexpected errors in the thread itself
            error_msg = f"Critical Thread Error: {e}"
            print(error_msg) # Log critical error
            import traceback
            traceback.print_exc()
            self.queue_status_update(error_msg)
            self.queue_status_update(f"--- PROCESSING FAILED CRITICALLY (Duration: {duration:.2f}s) ---")
            # Schedule messagebox on main thread
            self.root.after(0, lambda: messagebox.showerror("Critical Error", f"An unexpected error occurred:\n{e}"))

        finally:
            # Re-enable the button (schedule this action on the main thread)
             if self.root.winfo_exists():
                 self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))


if __name__ == "__main__":
    # Check for .env file and API key (optional but good practice)
    if not os.getenv("GROQ_API_KEY"):
         print("Warning: GROQ_API_KEY environment variable not found.")
         print("Please ensure your API key is set in a .env file or environment variables.")
         # Optionally show a warning popup, but allow continuing
         messagebox.showwarning("API Key Missing", "GROQ_API_KEY environment variable not found.\nTranscription will likely fail.\n\nPlease set it in a '.env' file in the application directory.")

    root = tk.Tk()
    app = AudioProcessorApp(root)
    root.mainloop()
    