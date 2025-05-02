import subprocess
import glob
import os
from dotenv import load_dotenv
from groq import Groq
from srt_utils import combine_srt_files, parse_srt, merge_subtitles, format_srt
import tkinter as tk
from tkinter import messagebox

load_dotenv()

client = Groq()


def format_timestamp(seconds: float, always_include_hours: bool = False, decimal_marker: str = ','):
    """
    Convert seconds to a timestamp string in the format HH:MM:SS,ms
    """
    if seconds is None:
        return "00:00:00,000"  # Handle None case

    milliseconds = round(seconds * 1000)

    hours = milliseconds // (3600 * 1000)
    milliseconds -= hours * (3600 * 1000)

    minutes = milliseconds // (60 * 1000)
    milliseconds -= minutes * (60 * 1000)

    seconds = milliseconds // 1000
    milliseconds -= seconds * 1000

    hours_str = f"{hours:02}" if always_include_hours or hours > 0 else ""
    minutes_str = f"{minutes:02}"
    seconds_str = f"{seconds:02}"
    milliseconds_str = f"{milliseconds:03}"

    time_str = f"{hours_str+':' if hours_str else ''}{minutes_str}:{seconds_str}{decimal_marker}{milliseconds_str}"
    return time_str


def process_audio_segment(audio_filepath, output_dir, model_name="whisper-large-v3"):
    """
    Transcribes an audio segment using Groq and returns the path to the SRT file.
    """
    try:
        with open(audio_filepath, "rb") as audio_file:
            files = {"file": audio_file}
            transcript = client.speech.transcriptions.create(
                model=model_name,
                file=files["file"],
                language="en",
                response_format="srt"
            )

        srt_content = transcript.text
        base_filename = os.path.splitext(os.path.basename(audio_filepath))[0]
        srt_filename = f"{base_filename}.srt"
        srt_path = os.path.join(output_dir, srt_filename)

        with open(srt_path, "w", encoding="utf-8") as srt_file:
            srt_file.write(srt_content)

        return srt_path
    except Exception as e:
        print(f"Error transcribing {audio_filepath}: {e}")
        return None


def download_audio_from_url(url, status_label, window):
    """Downloads audio from a YouTube URL using yt-dlp."""
    if not url:
        status_label.config(text="Error: Please enter a URL.")
        return None

    status_label.config(text=f"Downloading audio from: {url}...")
    window.update()

    command = f"yt-dlp.exe --extract-audio --audio-format mp3 {url}"
    try:
        subprocess.run(command, shell=True, check=True, capture_output=True)
        status_label.config(text=f"Successfully downloaded audio from: {url}")
        return True
    except subprocess.CalledProcessError as e:
        status_label.config(text=f"Error downloading audio: {e.stderr.decode()}")
        return False


def process_audio(input_path, output_filepath, model_name, status_label, window, streamlined_lengthen_subtitles_var, auto_delete_var=None, output_filename_entry=None, lengthen_subtitles_var=None):
    """
    Processes audio from a URL or a local file, segments it, transcribes it, and combines the SRT files.
    """
    output_dir = os.path.dirname(output_filepath)
    base_filename = os.path.splitext(os.path.basename(output_filepath))[0]
    temp_audio_file = os.path.join(output_dir, "temp_audio.mp3")
    combined_srt_path = os.path.join(output_dir, "combined_audio.srt")

    try:
        # 1. Download audio if it's a URL
        if input_path.startswith("http://") or input_path.startswith("https://"):
            status_label.config(text=f"Downloading audio from: {input_path}...")
            window.update()
            command = f"yt-dlp.exe --extract-audio --audio-format mp3 -o {temp_audio_file} {input_path}"
            subprocess.run(command, shell=True, check=True, capture_output=True)
            status_label.config(text=f"Successfully downloaded audio to: {temp_audio_file}")
            window.update()
            audio_file_path = temp_audio_file  # Use the downloaded file for further processing
        else:
            audio_file_path = input_path  # Use the local file path directly

        # 2. Segment audio
        status_label.config(text="Segmenting audio into 10-minute chunks...")
        window.update()
        segment_prefix = os.path.join(output_dir, f"segment_min%02d.mp3")
        ffmpeg_command = [
            "ffmpeg",
            "-i", audio_file_path,
            "-f", "segment",
            "-segment_time", "600",  # 10 minutes
            "-segment_format", "mp3",
            segment_prefix,
            "-reset_timestamps", "1",
            "-y",  # Overwrite existing files without asking
        ]
        subprocess.run(ffmpeg_command, shell=True, check=True, capture_output=True)
        status_label.config(text="Audio segmentation complete.")
        window.update()

        # 3. Transcribe segments
        segmented_files_pattern = os.path.join(output_dir, f"segment_min*.mp3")
        segmented_audio_files = glob.glob(segmented_files_pattern)
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

        # 4. Combine SRT files
        if generated_srt_files:
            status_label.config(text="Combining SRT files...")
            window.update()
            combined_srt_path = combine_srt_files(generated_srt_files, output_dir)

            if combined_srt_path:
                # 5. Lengthen subtitles (if enabled)
                if streamlined_lengthen_subtitles_var.get():
                    status_label.config(text="Lengthening subtitles...")
                    window.update()
                    try:
                        with open(combined_srt_path, "r", encoding="utf-8") as f_in:
                            srt_content = f_in.read()
                        parsed_data = parse_srt(srt_content)
                        merged_data = merge_subtitles(parsed_data, min_chars=45)
                        output_srt = format_srt(merged_data)
                        with open(combined_srt_path, "w", encoding="utf-8") as f_out:
                            f_out.write(output_srt)
                        status_label.config(text="Subtitles lengthened.")
                        window.update()
                    except Exception as e:
                        status_label.config(text=f"Error lengthening subtitles: {e}")
                        messagebox.showerror("Error", f"Failed to lengthen subtitles: {e}")

                # 6. Rename the combined SRT file
                output_filename = base_filename + ".srt"
                output_filepath = os.path.join(output_dir, output_filename)
                try:
                    os.rename(os.path.join(output_dir, "combined_audio.srt"), output_filepath)
                    status_label.config(text=f"Successfully processed audio and saved SRT to: {output_filepath}")
                    messagebox.showinfo("Success", f"Audio processed and SRT saved to: {output_filepath}")
                except FileNotFoundError as e:
                    status_label.config(text=f"Error: combined_audio.srt not found. Check console for details. {e}")
                    messagebox.showerror("Error", f"Failed to rename combined_audio.srt. Check console for details. {e}")
            else:
                status_label.config(text="Error combining SRT files.")
                messagebox.showerror("Error", "Failed to combine SRT files.")
        else:
            status_label.config(text="No SRT files were generated.")
            messagebox.showerror("Error", "No SRT files generated.")

    except Exception as e:
        status_label.config(text=f"An error occurred during processing: {e}")
        messagebox.showerror("Error", f"Processing Error: {e}")
    finally:
        # Clean up temporary audio file
        if os.path.exists(temp_audio_file):
            os.remove(temp_audio_file)


def process_and_combine_selected(audio_filepaths, output_dir, model_name, status_label, window, lengthen_subtitles_var2):
    if not audio_filepaths:
        status_label.config(text="Error: No audio files selected from list.")
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
            # --- Lengthen Subtitles Logic ---
            if lengthen_subtitles_var2.get():
                status_label.config(text="Lengthening subtitles...")
                window.update()
                try:
                    with open(combined_srt_path, "r", encoding="utf-8") as f_in:
                        srt_content = f_in.read()
                    parsed_data = parse_srt(srt_content)
                    merged_data = merge_subtitles(parsed_data, min_chars=45)
                    output_srt = format_srt(merged_data)
                    with open(combined_srt_path, "w", encoding="utf-8") as f_out:
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
