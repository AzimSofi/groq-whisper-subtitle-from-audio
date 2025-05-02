import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import queue # For thread-safe GUI updates

# Import the refactored processing function
try:
    from audio_processing import process_audio
    # Ensure srt_utils.py is in the same directory or Python path
    import srt_utils
except ImportError as e:
    messagebox.showerror("Import Error", f"Failed to import required modules: {e}\nMake sure audio_processing.py and srt_utils.py are present.")
    exit()


class AudioProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Processor GUI")
        # self.root.geometry("600x450") # Adjust size as needed

        # --- Variables ---
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.lengthen_subs_var = tk.BooleanVar(value=True) # Default to True
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

        self.lengthen_check = ttk.Checkbutton(options_frame, text="Lengthen Subtitles (Merge short blocks)", variable=self.lengthen_subs_var)
        self.lengthen_check.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        ttk.Label(options_frame, text="Cleanup:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.del_segments_check = ttk.Checkbutton(options_frame, text="Delete Segment MP3s", variable=self.delete_segments_var)
        self.del_segments_check.grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.del_temp_audio_check = ttk.Checkbutton(options_frame, text="Delete Downloaded MP3", variable=self.delete_temp_audio_var)
        self.del_temp_audio_check.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        self.del_segment_srts_check = ttk.Checkbutton(options_frame, text="Delete Segment SRTs", variable=self.delete_segment_srts_var)
        self.del_segment_srts_check.grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)

        # --- Controls ---
        control_frame = ttk.Frame(main_frame, padding="10")
        control_frame.grid(row=3, column=0, columnspan=3, pady=10)

        self.start_button = ttk.Button(control_frame, text="Start Processing", command=self.start_processing_thread)
        self.start_button.pack() # Simple packing for the button

        # --- Status Area ---
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1) # Make status area expand vertically

        self.status_text = tk.Text(status_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
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

    def browse_output_file(self):
        filepath = filedialog.asksaveasfilename(
            title="Select Output SRT File",
            defaultextension=".srt",
            filetypes=[("SRT Subtitles", "*.srt"), ("All Files", "*.*")]
        )
        if filepath:
            self.output_path_var.set(filepath)

    def update_status(self, message):
        """Appends a message to the status text box (thread-safe)."""
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
        finally:
            # Schedule the next check
            self.root.after(100, self.check_status_queue)

    def queue_status_update(self, message):
        """Callback function to be passed to the worker thread."""
        self.status_queue.put(message)

    def start_processing_thread(self):
        input_path = self.input_path_var.get().strip()
        output_path = self.output_path_var.get().strip()

        if not input_path:
            messagebox.showerror("Error", "Please provide an input URL or file path.")
            return
        if not output_path:
            messagebox.showerror("Error", "Please select an output SRT file path.")
            return
        if not output_path.lower().endswith(".srt"):
             messagebox.showwarning("Warning", "Output filename should ideally end with .srt")
             # You could force it or just warn:
             # output_path += ".srt"
             # self.output_path_var.set(output_path)

        # Disable button during processing
        self.start_button.config(state=tk.DISABLED)
        self.update_status("Starting processing...") # Initial status

        # Get options
        lengthen = self.lengthen_subs_var.get()
        del_segments = self.delete_segments_var.get()
        del_temp_audio = self.delete_temp_audio_var.get()
        del_seg_srts = self.delete_segment_srts_var.get()
        model = self.model_name_var.get()

        # Run processing in a separate thread
        self.processing_thread = threading.Thread(
            target=self.run_processing,
            args=(input_path, output_path, model, lengthen, del_segments, del_temp_audio, del_seg_srts),
            daemon=True # Allows closing the app even if thread is stuck (use with caution)
        )
        self.processing_thread.start()

    def run_processing(self, input_path, output_path, model, lengthen, del_segments, del_temp_audio, del_seg_srts):
        """Worker function that runs in the thread."""
        try:
            success = process_audio(
                input_path=input_path,
                output_srt_filepath=output_path,
                model_name=model,
                status_callback=self.queue_status_update, # Pass the queueing function
                lengthen_subtitles_flag=lengthen,
                delete_segments_flag=del_segments,
                delete_temp_audio_flag=del_temp_audio,
                delete_segment_srts_flag=del_seg_srts
            )

            # Final status update via queue
            if success:
                self.queue_status_update("--- PROCESSING FINISHED SUCCESSFULLY ---")
                # Schedule messagebox on main thread
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Processing complete. SRT saved to:\n{output_path}"))
            else:
                self.queue_status_update("--- PROCESSING FAILED ---")
                # Schedule messagebox on main thread
                self.root.after(0, lambda: messagebox.showerror("Error", "Processing failed. Check status messages for details."))

        except Exception as e:
            # Catch any unexpected errors in the thread itself
            error_msg = f"Critical Thread Error: {e}"
            print(error_msg) # Log critical error
            import traceback
            traceback.print_exc()
            self.queue_status_update(error_msg)
            self.queue_status_update("--- PROCESSING FAILED CRITICALLY ---")
            # Schedule messagebox on main thread
            self.root.after(0, lambda: messagebox.showerror("Critical Error", f"An unexpected error occurred:\n{e}"))

        finally:
            # Re-enable the button (schedule this action on the main thread)
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))


if __name__ == "__main__":
    # Check for .env file and API key (optional but good practice)
    if not os.getenv("GROQ_API_KEY"):
         print("Warning: GROQ_API_KEY environment variable not found.")
         print("Please ensure your API key is set in a .env file or environment variables.")
         # Optionally show a warning popup, but allow continuing
         # messagebox.showwarning("API Key Missing", "GROQ_API_KEY not found. Transcription will likely fail.")

    root = tk.Tk()
    app = AudioProcessorApp(root)
    root.mainloop()