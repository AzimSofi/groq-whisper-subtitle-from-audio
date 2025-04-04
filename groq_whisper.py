import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, Listbox
import tkinter.ttk as ttk
import os
from dotenv import load_dotenv
from groq import Groq
import datetime
import subprocess  # ffmpeg
import glob

load_dotenv()

client = Groq()

def format_timestamp(seconds):
    """Converts seconds to SRT timestamp format (HH:MM:SS,milliseconds)."""
    timedelta = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(timedelta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int(timedelta.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def process_audio_segment(filename, output_dir, model_name):
    """Transcribes an audio segment using Groq Whisper and saves SRT to output_dir."""
    srt_filename = os.path.splitext(os.path.basename(filename))[0] + ".srt"
    output_filepath = os.path.join(output_dir, srt_filename)

    current_model = model_name.get()

    try:
        with open(filename, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model=current_model,
                response_format="verbose_json",
            )

        if hasattr(transcription, 'segments') and transcription.segments:
            segment_duration = 10 * 60 # 10 minutes
            segment_index_str = os.path.basename(filename).split('_min')[1].split('.')[0] if '_min' in os.path.basename(filename) else '0' # Extract segment number, default to 0 if naming convention not followed
            try:
                segment_index = int(segment_index_str)
            except ValueError:
                print(f"Warning: Could not parse segment index from filename: {filename}. Assuming index 0.")
                segment_index = 0
            start_offset = segment_index * segment_duration

            with open(output_filepath, 'w', encoding='utf-8') as srt_file:
                for segment in transcription.segments:
                    start_time = start_offset + segment['start']
                    end_time = start_offset + segment['end']
                    srt_file.write(f"{segment['id'] + 1}\n")
                    srt_file.write(f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n")
                    srt_file.write(f"{segment['text'].strip()}\n\n")
            return output_filepath

        else:
            print(f"No transcription segments found for {filename}.")
            return None

    except FileNotFoundError:
        print(f"Error: Audio file not found at {filename}")
        return None
    except AttributeError as e:
        print(f"AttributeError: {e}. Check transcription object structure.")
        return None
    except Exception as e:
        print(f"An error occurred during transcription of {filename}: {e}")
        return None

def combine_srt_files(srt_files, output_dir):
    """Combines a list of SRT files into a single SRT file in output_dir."""
    if not srt_files:
        print("No SRT files to combine.")
        return None

    # Sort assuming filenames contain '_min' and segment number, otherwise maintain order
    def get_segment_number(filename):
        if '_min' in filename:
            try:
                return int(os.path.basename(filename).split('_min')[1].split('.')[0])
            except ValueError:
                return float('inf') # Put files without valid segment numbers at the end
        return float('inf') # For files not matching naming convention, keep original order if not sortable

    srt_files.sort(key=get_segment_number)

    output_filepath = os.path.join(output_dir, "combined_audio.srt")

    try:
        with open(output_filepath, 'w', encoding='utf-8') as outfile:
            subtitle_index = 1
            for srt_filepath in srt_files:
                if not srt_filepath:
                    continue
                with open(srt_filepath, 'r', encoding='utf-8') as infile:
                    lines = infile.readlines()
                    i = 0
                    while i < len(lines):
                        line = lines[i].strip()
                        if line.isdigit() and int(line) > 0:
                            outfile.write(str(subtitle_index) + '\n')
                            subtitle_index += 1
                            i += 1
                            outfile.write(lines[i])
                            i += 1
                            while i < len(lines) and lines[i].strip() != "":
                                outfile.write(lines[i])
                                i += 1
                            outfile.write('\n')
                            i += 1
                        else:
                            i += 1
        return output_filepath
    except Exception as e:
        print(f"Error combining SRT files: {e}")
        return None


def create_combined_srt_gui():
    """GUI to transcribe audio segments and combine SRT files with segmentation option."""

    # --- GUI Setup ---
    window = tk.Tk()
    window.title("Audio to Combined SRT Converter")

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

    def segment_and_process():
        large_audio_filepath = large_audio_entry.get()
        if not large_audio_filepath:
            status_label.config(text="Error: No large audio file selected for segmentation.")
            return

        output_dir = filedialog.askdirectory(title="Select Output Directory for SRT and Segmented Audio")
        if not output_dir:
            status_label.config(text="Output directory selection cancelled.")
            return

        status_label.config(text="Segmenting audio into 10-minute chunks...")
        window.update()

        base_filename = os.path.splitext(os.path.basename(large_audio_filepath))[0]
        segment_prefix = os.path.join(output_dir, f"{base_filename}_min%02d.mp3") # Segmented files output here

        ffmpeg_command = [
            "ffmpeg",
            "-i", large_audio_filepath,
            "-f", "segment",
            "-segment_time", "600", # 10 minutes
            "-segment_format", "mp3",
            segment_prefix,
            "-reset_timestamps", "1",
            "-y" # Overwrite existing files without asking
        ]

        try:
            subprocess.run(ffmpeg_command, check=True, capture_output=True) # Debugging
            status_label.config(text="Audio segmentation complete. Transcribing segments...")
            window.update()

            segmented_files_pattern = os.path.join(output_dir, f"{base_filename}_min*.mp3")
            segmented_audio_files = glob.glob(segmented_files_pattern) # Find segmented files

            if not segmented_audio_files:
                status_label.config(text="Error: No segmented audio files found after segmentation.")
                messagebox.showerror("Error", "No segmented audio files found. Segmentation may have failed.")
                return

            generated_srt_files = []
            for audio_file in segmented_audio_files:
                status_label.config(text=f"Transcribing: {os.path.basename(audio_file)}...")
                window.update()
                srt_path = process_audio_segment(audio_file, output_dir, model_name)
                if srt_path:
                    generated_srt_files.append(srt_path)
                else:
                    status_label.config(text=f"Error transcribing {os.path.basename(audio_file)}. Check console for details.")
                    window.update()

            if generated_srt_files:
                status_label.config(text="Combining SRT files...")
                window.update()
                combined_srt_path = combine_srt_files(generated_srt_files, output_dir)
                if combined_srt_path:
                    status_label.config(text=f"Successfully segmented, transcribed and combined SRT files into: {combined_srt_path}")
                    messagebox.showinfo("Success", f"Audio segmented, SRTs generated and combined to: {combined_srt_path}")
                else:
                    status_label.config(text="Error combining SRT files. Check console for details.")
                    messagebox.showerror("Error", "Failed to combine SRT files. Check console for details.")
            else:
                status_label.config(text="No SRT files were generated from segments. Transcription failed for all segments.")
                messagebox.showerror("Error", "No SRT files generated from segments. Transcription failed for all segments.")

            # --- Auto-Delete and Filename ---
            if auto_delete_var.get():
                status_label.config(text="Deleting segmented audio and SRT files...")
                window.update()
                for audio_file in segmented_audio_files:
                    try:
                        os.remove(audio_file)
                    except Exception as e:
                        print(f"Error deleting {audio_file}: {e}")
                try:
                    os.remove(large_audio_filepath)
                except Exception as e:
                    print(f"Error deleting {large_audio_filepath}: {e}")
                for srt_file in generated_srt_files:
                    try:
                        os.remove(srt_file)
                    except Exception as e:
                        print(f"Error deleting {srt_file}: {e}")

            output_filename = output_filename_entry.get() + ".srt"
            output_filepath = os.path.join(output_dir, output_filename)
            try:
                os.rename(os.path.join(output_dir, "combined_audio.srt"), output_filepath)
                status_label.config(text=f"Successfully segmented, transcribed and combined SRT files into: {output_filepath}")
                messagebox.showinfo("Success", f"Audio segmented, SRTs generated and combined to: {output_filepath}")
            except FileNotFoundError as e:
                status_label.config(text=f"Error: combined_audio.srt not found. Check console for details. {e}")
                messagebox.showerror("Error", f"Failed to rename combined_audio.srt. Check console for details. {e}")

        except subprocess.CalledProcessError as e:
            status_label.config(text=f"FFmpeg segmentation error: {e.stderr.decode()}")  # Decode stderr for error message
            messagebox.showerror("FFmpeg Error", f"Audio segmentation with FFmpeg failed. See status for details. Ensure FFmpeg is installed and in your system's PATH.")
        except FileNotFoundError:
            status_label.config(text="Error: FFmpeg command not found. Please ensure FFmpeg is installed and added to your system's PATH.")
            messagebox.showerror("Error", "FFmpeg Not Found", "FFmpeg command not found. Please install FFmpeg and ensure it's in your system's PATH.")
        except Exception as e:
            status_label.config(text=f"An unexpected error occurred during segmentation: {e}")
            messagebox.showerror("Error", f"Unexpected Segmentation Error: {e}")

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

        generated_srt_files = []
        for audio_file in audio_filepaths:
            status_label.config(text=f"Transcribing: {os.path.basename(audio_file)}...")
            window.update()
            srt_path = process_audio_segment(audio_file, output_dir, model_name)
            if srt_path:
                generated_srt_files.append(srt_path)
            else:
                status_label.config(text=f"Error transcribing {os.path.basename(audio_file)}. Check console for details.")
                window.update()

        if generated_srt_files:
            status_label.config(text="Combining SRT files...")
            window.update()
            combined_srt_path = combine_srt_files(generated_srt_files, output_dir)
            if combined_srt_path:
                status_label.config(text=f"Successfully combined SRT files into: {combined_srt_path}")
                messagebox.showinfo("Success", f"SRT files combined and saved to: {combined_srt_path}")
            else:
                status_label.config(text="Error combining SRT files. Check console for details.")
                messagebox.showerror("Error", "Failed to combine SRT files. Check console for details.")
        else:
            status_label.config(text="No SRT files were generated. Transcription failed for all segments.")
            messagebox.showerror("Error", "No SRT files generated. Transcription failed.")

    # --- GUI Setup ---
    # --- Model Selection ---
    model_frame = tk.Frame(window)
    model_frame.pack(pady=10, fill=tk.X, padx=10)

    model_label = tk.Label(model_frame, text="Select Model:")
    model_label.pack(side=tk.LEFT)

    model_dropdown = tk.OptionMenu(model_frame, model_name, "whisper-large-v3", "whisper-large-v3-turbo")
    model_dropdown.pack(side=tk.LEFT, padx=5)

    # --- Notebook (Tabs) ---
    notebook = ttk.Notebook(window)
    notebook.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

    # --- Large Audio File Tab ---
    large_audio_tab = tk.Frame(notebook)
    notebook.add(large_audio_tab, text="Large Audio File")

    large_audio_frame = tk.Frame(large_audio_tab)
    large_audio_frame.pack(pady=10, fill=tk.X, padx=10)

    large_audio_label = tk.Label(large_audio_frame, text="Large Audio File:")
    large_audio_label.pack(side=tk.LEFT)

    large_audio_entry = tk.Entry(large_audio_frame, width=50)
    large_audio_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    select_large_audio_button = tk.Button(large_audio_frame, text="Select Large Audio", command=select_large_audio_file)
    select_large_audio_button.pack(side=tk.LEFT, padx=5)

    segment_process_button = tk.Button(large_audio_tab, text="Segment & Process Large Audio to SRT", command=segment_and_process)
    segment_process_button.pack(pady=10)

    # --- Auto-Delete Checkbox ---
    auto_delete_var = tk.BooleanVar(value=False)
    auto_delete_check = tk.Checkbutton(large_audio_tab, text="Auto-Delete Audio Segments and Original Audio", variable=auto_delete_var)
    auto_delete_check.pack(pady=5)

    # --- Output Filename Entry ---
    output_filename_label = tk.Label(large_audio_tab, text="Output Filename:")
    output_filename_label.pack()
    output_filename_entry = tk.Entry(large_audio_tab, width=30)
    output_filename_entry.insert(0, "combined_audio")  # Default filename
    output_filename_entry.pack(pady=5)

    # --- Segmented Audio Files Tab ---
    segmented_audio_tab = tk.Frame(notebook)
    notebook.add(segmented_audio_tab, text="Segmented Audio Files")

    select_audio_button = tk.Button(segmented_audio_tab, text="Select Audio Segments", command=select_audio_files)
    select_audio_button.pack(pady=10)

    selected_audio_label = tk.Label(segmented_audio_tab, text="Selected Audio Segments (for manual selection):")
    selected_audio_label.pack()

    process_combine_button = tk.Button(segmented_audio_tab, text="Process & Combine Selected to SRT", command=process_and_combine_selected)
    process_combine_button.pack(pady=10)

    # --- Auto-Delete Checkbox ---
    auto_delete_var2 = tk.BooleanVar(value=False)
    auto_delete_check2 = tk.Checkbutton(segmented_audio_tab, text="Auto-Delete Audio Segments and Original Audio", variable=auto_delete_var2)
    auto_delete_check2.pack(pady=5)

    # --- Output Filename Entry ---
    output_filename_label2 = tk.Label(segmented_audio_tab, text="Output Filename:")
    output_filename_label2.pack()
    output_filename_entry2 = tk.Entry(segmented_audio_tab, width=30)
    output_filename_entry2.insert(0, "combined_audio")  # Default filename
    output_filename_entry2.pack(pady=5)

    status_label = tk.Label(window, text="")
    status_label.pack(pady=10)

    window.mainloop()


if __name__ == "__main__":
    create_combined_srt_gui()
