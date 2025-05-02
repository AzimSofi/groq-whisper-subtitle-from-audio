import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, Listbox
import tkinter.ttk as ttk
import os
from dotenv import load_dotenv
from groq import Groq
import datetime
import subprocess  # ffmpeg
import glob
# import re  # Removed
# import io  # Removed
from srt_utils import parse_srt, merge_subtitles, format_srt, combine_srt_files
from audio_processing import download_audio_from_url, process_audio


load_dotenv()

client = Groq()


def create_combined_srt_gui():
    """GUI to transcribe audio segments and combine SRT files with segmentation option."""

    # --- GUI Setup ---
    window = tk.Tk()
    window.title("Audio to Combined SRT Converter")

    # --- Selected Audio List ---
    selected_audio_frame = ttk.LabelFrame(window, text="Selected Audio Segments")
    selected_audio_frame.pack(padx=10, pady=5, fill="x")

    selected_audio_list = tk.Listbox(selected_audio_frame, height=5, selectmode=tk.MULTIPLE)
    selected_audio_list.pack(padx=5, pady=5, fill="both", expand=True)

    # --- Large Audio File Input ---
    large_audio_label = ttk.Label(window, text="Large Audio File:")
    large_audio_label.pack(padx=10, pady=5, anchor="w")
    large_audio_entry = ttk.Entry(window, width=50)
    large_audio_entry.pack(padx=10, pady=5, fill="x")

    # --- Output Filename Input ---
    output_filename_label = ttk.Label(window, text="Output Filename:")
    output_filename_label.pack(padx=10, pady=5, anchor="w")
    output_filename_entry = ttk.Entry(window, width=50)
    output_filename_entry.pack(padx=10, pady=5, fill="x")

    # --- Lengthen Subtitles Option (Streamlined) ---
    streamlined_lengthen_subtitles_var = tk.BooleanVar(value=True)
    streamlined_lengthen_subtitles_check = ttk.Checkbutton(
        window,
        text="Lengthen Subtitles (Streamlined)",
        variable=streamlined_lengthen_subtitles_var
    )
    streamlined_lengthen_subtitles_check.pack(padx=10, pady=5, anchor="w")

    # --- URL Input ---
    url_label = ttk.Label(window, text="URL:")
    url_label.pack(padx=10, pady=5, anchor="w")
    url_entry = ttk.Entry(window, width=50)
    url_entry.pack(padx=10, pady=5, fill="x")

    # --- Output Path Input ---
    output_path_label = ttk.Label(window, text="Output File Path:")
    output_path_label.pack(padx=10, pady=5, anchor="w")
    output_path_entry = ttk.Entry(window, width=50)
    output_path_entry.pack(padx=10, pady=5, fill="x")

    # --- Lengthen Subtitles Option 1 ---
    lengthen_subtitles_var = tk.BooleanVar(value=True)
    lengthen_subtitles_check = ttk.Checkbutton(
        window,
        text="Lengthen Subtitles (Segmentation)",
        variable=lengthen_subtitles_var
    )
    lengthen_subtitles_check.pack(padx=10, pady=5, anchor="w")

    # --- Lengthen Subtitles Option 2 ---
    lengthen_subtitles_var2 = tk.BooleanVar(value=True)
    lengthen_subtitles_check2 = ttk.Checkbutton(
        window,
        text="Lengthen Subtitles (Combine)",
        variable=lengthen_subtitles_var2
    )
    lengthen_subtitles_check2.pack(padx=10, pady=5, anchor="w")

    # --- Status Label ---
    status_label = ttk.Label(window, text="Ready")
    status_label.pack(padx=10, pady=10, anchor="w")

    # --- Model Selection ---
    model_name = tk.StringVar(value="whisper-large-v3")

    def select_audio_files():
        filetypes = (("Audio files", "*.mp3;*.wav;*.flac"), ("All files", "*.*"))
        audio_files = filedialog.askopenfilenames(title="Select Audio Segments", filetypes=filetypes)
        if audio_files:
            selected_audio_list.delete(0, tk.END)
            for file in audio_files:
                selected_audio_list.insert(tk.END, file)
            status_label.config(text=f"Selected {len(audio_files)} audio segments.")
        else:
            status_label.config(text="Audio file selection cancelled.")

    def select_large_audio_file():
        filetypes = (("Audio files", "*.mp3;*.wav;*.flac"), ("All files", "*.*"))
        large_audio_file = filedialog.askopenfilename(title="Select Large Audio File", filetypes=filetypes)
        if large_audio_file:
            large_audio_entry.delete(0, tk.END)
            large_audio_entry.insert(0, large_audio_file)
            status_label.config(text=f"Selected large audio file: {os.path.basename(large_audio_file)}.")
        else:
            status_label.config(text="Large audio file selection cancelled.")

    def segment_and_process_local():
        large_audio_filepath = large_audio_entry.get()
        output_dir = filedialog.askdirectory(title="Select Output Directory for SRT and Segmented Audio")
        if not output_dir:
            status_label.config(text="Output directory selection cancelled.")
            return

        output_filename = output_filename_entry.get() + ".srt"
        output_filepath = os.path.join(output_dir, output_filename)

        process_audio(large_audio_filepath, output_filepath, model_name.get(), status_label, window, lengthen_subtitles_var)
        status_label.config(text=f"Processing complete. SRT file saved to: {output_filepath}")
        messagebox.showinfo("Success", f"Audio processed and SRT saved to: {output_filepath}")

    def process_and_combine_selected():
        audio_filepaths = selected_audio_list.get(0, tk.END)
        if not audio_filepaths:
            status_label.config(text="Error: No audio files selected from list.")
            return

        output_dir = filedialog.askdirectory(title="Select Output Directory for SRT files")
        if not output_dir:
            status_label.config(text="Output directory selection cancelled.")
            return

        status_label.config(text="Processing selected audio segments and transcribing...")
        window.update()

        srt_files = []
        for audio_file in audio_filepaths:
            output_filename = os.path.splitext(os.path.basename(audio_file))[0] + ".srt"
            output_filepath = os.path.join(output_dir, output_filename)
            process_audio(audio_file, output_filepath, model_name.get(), status_label, window, lengthen_subtitles_var2)
            srt_files.append(output_filepath)

        status_label.config(text="Combining SRT files...")
        window.update()
        combined_srt_path = combine_srt_files(srt_files, output_dir)

        if combined_srt_path:
            # --- Lengthen Subtitles Logic ---
            if lengthen_subtitles_var2.get():
                status_label.config(text="Lengthening subtitles...")
                window.update()
                try:
                    with open(combined_srt_path, 'r', encoding='utf-8') as f_in:
                        srt_content = f_in.read()
                    parsed_data = parse_srt(srt_content)
                    merged_data = merge_subtitles(parsed_data, min_chars=45)
                    output_srt = format_srt(merged_data)
                    with open(combined_srt_path, 'w', encoding='utf-8') as f_out:
                        f_out.write(output_srt)
                    status_label.config(text=f"Successfully combined and lengthened SRT files into: {combined_srt_path}")
                    messagebox.showinfo("Success", f"SRT files combined and lengthened to: {combined_srt_path}")
                except Exception as e:
                    status_label.config(text=f"Error lengthening subtitles: {e}")
                    messagebox.showerror("Error", f"Failed to lengthen subtitles: {e}")
            else:
                status_label.config(text=f"Successfully combined SRT files into: {combined_srt_path}")
                messagebox.showinfo("Success", f"SRT files combined and saved to: {combined_srt_path}")
        else:
            status_label.config(text="No SRT files were generated. Transcription failed for all segments.")
            messagebox.showerror("Error", "No SRT files generated. Transcription failed.")

    def download_audio_from_url_local():
        url = url_entry.get()
        if not url:
            status_label.config(text="Error: Please enter a URL.")
            messagebox.showerror("Error", "Please enter a URL.")
            return

        if download_audio_from_url(url, status_label, window):
            status_label.config(text=f"Successfully downloaded audio from: {url}")
            messagebox.showinfo("Success", f"Successfully downloaded audio from: {url}")
        else:
            status_label.config(text=f"Error downloading audio from: {url}")
            messagebox.showerror("Error", f"Error downloading audio from: {url}")

    def start_full_process_local():
        url = url_entry.get()
        output_filepath = output_path_entry.get()

        if not url or not output_filepath:
            status_label.config(text="Error: Please enter both URL and output file path.")
            messagebox.showerror("Error", "Please enter both URL and output file path.")
            return

        process_audio(url, output_filepath, model_name.get(), status_label, window, streamlined_lengthen_subtitles_var)
        status_label.config(text=f"Processing complete. SRT file saved to: {output_filepath}")
        messagebox.showinfo("Success", f"Audio processed and SRT saved to: {output_filepath}")

    window.mainloop()

create_combined_srt_gui()
