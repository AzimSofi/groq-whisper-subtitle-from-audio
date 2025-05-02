# audio_processing.py
import subprocess
import glob
import os
import re
import time
from dotenv import load_dotenv
from groq import Groq
from srt_utils import parse_srt, merge_subtitles, format_srt # Import from our utils file

load_dotenv()

# --- Groq Client Initialization ---
try:
    client = Groq()
except Exception as e:
    print(f"ERROR: Failed to initialize Groq client. Check API key and environment variables. {e}")
    client = None

# --- Timestamp Formatting ---
def format_timestamp(seconds: float, always_include_hours: bool = True, decimal_marker: str = ','):
    """Converts seconds to HH:MM:SS,ms format for SRT."""
    if seconds is None or not isinstance(seconds, (int, float)):
        print(f"Warning: Invalid seconds value '{seconds}' received in format_timestamp. Returning 00:00:00,000.")
        seconds = 0.0

    if seconds < 0:
        # print(f"Warning: Negative timestamp {seconds} received. Clamping to 0.")
        seconds = 0.0

    milliseconds = round(seconds * 1000.0)

    hours = int(milliseconds // (3600 * 1000))
    milliseconds -= hours * (3600 * 1000)

    minutes = int(milliseconds // (60 * 1000))
    milliseconds -= minutes * (60 * 1000)

    seconds_part = int(milliseconds // 1000)
    milliseconds -= seconds_part * 1000

    # Use f-string formatting for leading zeros
    hours_str = f"{hours:02d}"
    minutes_str = f"{minutes:02d}"
    seconds_str = f"{seconds_part:02d}"
    milliseconds_str = f"{int(milliseconds):03d}"

    # Force hours component for SRT standard
    time_str = f"{hours_str}:{minutes_str}:{seconds_str}{decimal_marker}{milliseconds_str}"
    return time_str

# --- SRT Time to Milliseconds ---
def _srt_time_to_ms(time_str):
    """Converts HH:MM:SS,ms SRT time string to milliseconds."""
    try:
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s_ms = parts[2].split(',')
        s = int(s_ms[0])
        ms = int(s_ms[1])
        return h * 3600000 + m * 60000 + s * 1000 + ms
    except Exception as e:
        print(f"Warning: Could not parse time string '{time_str}': {e}. Returning 0.")
        return 0

# --- Milliseconds to SRT Time ---
def _ms_to_srt_time(total_ms):
    """Converts milliseconds to HH:MM:SS,ms SRT time string."""
    if total_ms < 0:
        total_ms = 0
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    # Ensure conversion back to int before formatting
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(ms):03d}"

# --- Audio Transcription Segment ---
def process_audio_segment(audio_filepath, output_dir, model_name="whisper-large-v3", language="ja"):
    """
    Transcribes an audio segment using Groq (requesting verbose_json),
    parses timestamps, formats to SRT, and returns the path to the generated SRT file.
    """
    if not client:
         print("ERROR: Groq client not initialized. Cannot transcribe.")
         return None

    srt_base_filename = os.path.splitext(os.path.basename(audio_filepath))[0]
    srt_filename = f"{srt_base_filename}.srt"
    srt_path = os.path.join(output_dir, srt_filename)

    try:
        with open(audio_filepath, "rb") as audio_file:
            files = {"file": (os.path.basename(audio_filepath), audio_file, "audio/mpeg")}
            print(f"Requesting transcription for {audio_filepath} (lang: {language}, format: verbose_json)")
            # Request verbose_json to get timestamps
            transcript_response = client.audio.transcriptions.create(
                model=model_name,
                file=files["file"],
                language=language,
                response_format="verbose_json" # Request JSON with timestamps
            )
        print(f"Received transcription response for {audio_filepath}")

        # --- SRT Formatting Logic ---
        srt_content_parts = []
        # Adjust based on actual Groq response structure if necessary
        segments = getattr(transcript_response, 'segments', None)

        if segments is None or not isinstance(segments, list):
             print(f"Error: Could not generate SRT for {audio_filepath}. 'segments' field missing, empty, or not a list in response.")
             # Optional: Try to get plain text if available
             plain_text = getattr(transcript_response, 'text', None)
             if plain_text:
                 print(f"Warning: Saving plain text only for {audio_filepath} as no timestamp segments were found.")
                 txt_filename = f"{srt_base_filename}.txt"
                 txt_path = os.path.join(output_dir, txt_filename)
                 try:
                     with open(txt_path, "w", encoding="utf-8") as txt_file:
                         txt_file.write(plain_text)
                 except Exception as write_err:
                     print(f"Error writing plain text file {txt_path}: {write_err}")
             return None # Indicate failure to create SRT

        print(f"Found {len(segments)} segments for {audio_filepath}. Formatting SRT...")
        srt_index = 1
        for segment in segments:
            try:
                # Access segment attributes - adjust names if Groq uses different ones
                # Ensure they are numbers before formatting
                start_time_sec = float(segment['start']) # Use ['key'] access
                end_time_sec = float(segment['end'])   # Use ['key'] access
                text = str(segment['text']).strip()  # Use ['key'] access

                # Basic validation
                if start_time_sec >= end_time_sec:
                    print(f"Warning: Skipping segment {srt_index} in {audio_filepath} due to invalid time (start >= end): {start_time_sec} >= {end_time_sec}")
                    continue
                if not text:
                    # print(f"Note: Skipping segment {srt_index} in {audio_filepath} due to empty text.")
                    continue # Skip segments with no text

                start_srt = format_timestamp(start_time_sec)
                end_srt = format_timestamp(end_time_sec)

                srt_content_parts.append(f"{srt_index}\n")
                srt_content_parts.append(f"{start_srt} --> {end_srt}\n")
                srt_content_parts.append(f"{text}\n\n") # Add the required blank line
                srt_index += 1

            except (KeyError, ValueError, TypeError) as e: # Catch KeyError primarily
                print(f"Error processing segment data in {audio_filepath}: {e}. Check response structure/keys/types.")
                print(f"Problematic segment data: {segment}")
                continue # Skip this problematic segment
            except Exception as e: # Catch-all for unexpected errors
                print(f"Unexpected error processing segment {srt_index} in {audio_filepath}: {e}")
                print(f"Problematic segment data: {segment}")
                continue


        # Join the parts into the final SRT string
        srt_content = "".join(srt_content_parts).strip()

        if not srt_content:
             print(f"Error: No valid SRT content generated for {audio_filepath} after processing segments.")
             return None

        # Write the manually formatted SRT content
        with open(srt_path, "w", encoding="utf-8") as srt_file:
            srt_file.write(srt_content + '\n') # Ensure trailing newline

        print(f"Successfully generated SRT: {srt_path}")
        return srt_path

    except Exception as e:
        # Catch Groq API errors or other issues
        print(f"Error during transcription or SRT formatting for {audio_filepath}: {e}")
        # Print traceback for detailed debugging of unexpected errors
        # import traceback
        # traceback.print_exc()
        return None

# --- Download Audio ---
def download_audio_from_url(url, output_path, status_callback):
    """Downloads audio from a YouTube URL using yt-dlp."""
    if not url:
        status_callback("Error: Please enter a URL.")
        return None

    status_callback(f"Downloading audio from: {url}...")
    # Ensure yt-dlp is in PATH or provide full path if needed
    # Use --no-warnings potentially
    command = f"yt-dlp --no-warnings --extract-audio --audio-format mp3 -o \"{output_path}\" \"{url}\""
    try:
        # Use capture_output=True to get stderr/stdout
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, encoding='utf-8')
        status_callback(f"Successfully downloaded audio to: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        error_message = f"Error downloading audio: {e.stderr or e.stdout or 'Unknown yt-dlp error'}"
        status_callback(error_message)
        print(error_message) # Also print for debugging
        return None
    except FileNotFoundError:
        status_callback("Error: 'yt-dlp' command not found. Make sure it's installed and in your system's PATH.")
        print("Error: 'yt-dlp' command not found.")
        return None
    except Exception as e:
        status_callback(f"Unexpected error during download: {e}")
        print(f"Unexpected download error: {e}")
        return None


# --- Combine SRT Files (Moved here to handle timestamp adjustments) ---
def combine_srt_files(srt_files, output_dir, output_filepath):
    """
    Combines a list of SRT files generated from segments (with reset timestamps)
    into a single SRT file, adjusting timestamps.
    """
    if not srt_files:
        print("No SRT files to combine.")
        return None

    # Sort based on segment number in filename (more robust)
    def get_segment_number(filename):
        basename = os.path.basename(filename)
        # Try to match patterns like _segment_001.srt or _min01.srt etc.
        # Match numbers preceded by "segment_" or "_min" or just "segment"
        match = re.search(r'(?:segment_|segment|_min)(\d+)\.srt$', basename, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                return float('inf') # Put unparsable ones at the end
        print(f"Warning: Could not extract segment number from '{basename}'. Assigning high sort order.")
        return float('inf') # Put files without clear numbers at the end

    try:
        srt_files.sort(key=get_segment_number)
        print("Sorted SRT files for combination:", [os.path.basename(f) for f in srt_files])
    except Exception as e:
         print(f"Warning: Could not sort SRT files reliably based on name: {e}. Combining in detected order.")

    try:
        with open(output_filepath, 'w', encoding='utf-8') as outfile:
            overall_subtitle_index = 1
            time_offset_ms = 0
            last_segment_end_time_ms = 0

            for srt_filepath in srt_files:
                if not srt_filepath or not os.path.exists(srt_filepath):
                    print(f"Warning: Skipping missing SRT file: {srt_filepath}")
                    continue

                print(f"Combining: {os.path.basename(srt_filepath)}")
                try:
                    with open(srt_filepath, 'r', encoding='utf-8') as infile:
                        srt_content = infile.read()
                        # Use the parser from srt_utils
                        entries = parse_srt(srt_content)

                        if not entries:
                            print(f"Warning: No entries parsed from {srt_filepath}, skipping.")
                            continue

                        # Check if timestamps reset (first entry starts near 0)
                        # Important: Use the helper to convert SRT time string to ms
                        first_entry_start_ms = _srt_time_to_ms(entries[0]['start'])

                        # If the first subtitle starts very early, assume segment reset timestamps
                        # Add the end time of the *previous* segment as the offset.
                        if first_entry_start_ms < 1000: # If first sub is within 1 sec of 00:00:00
                           time_offset_ms = last_segment_end_time_ms
                           print(f"  Segment reset detected. Applying offset: {time_offset_ms}ms")
                        else:
                            # If timestamps seem continuous, don't add offset from previous segment
                            # (This might happen if ffmpeg -reset_timestamps wasn't used or failed)
                            time_offset_ms = 0
                            print(f"  Timestamps appear continuous (first start: {first_entry_start_ms}ms). No offset applied.")


                        segment_max_end_time_current_segment = 0
                        for entry in entries:
                             # Convert entry's SRT times to ms, add offset, convert back
                             current_start_ms = _srt_time_to_ms(entry['start'])
                             current_end_ms = _srt_time_to_ms(entry['end'])

                             new_start_ms = current_start_ms + time_offset_ms
                             new_end_ms = current_end_ms + time_offset_ms

                             # Basic check for validity
                             if new_start_ms >= new_end_ms:
                                 print(f"  Warning: Skipping entry {entry.get('index','?')} due to invalid time after offset: {new_start_ms} >= {new_end_ms}")
                                 continue

                             outfile.write(str(overall_subtitle_index) + '\n')
                             outfile.write(f"{_ms_to_srt_time(new_start_ms)} --> {_ms_to_srt_time(new_end_ms)}\n")
                             outfile.write(entry['text'].strip() + '\n\n') # Ensure text is stripped and add blank line
                             overall_subtitle_index += 1

                             # Track the maximum end time *within this segment* after applying offset
                             segment_max_end_time_current_segment = max(segment_max_end_time_current_segment, new_end_ms)

                        # Update the overall last segment end time for the *next* segment's offset calculation
                        # We should use the max end time seen in this segment
                        last_segment_end_time_ms = segment_max_end_time_current_segment
                        print(f"  Segment processed. Updated last_segment_end_time_ms to: {last_segment_end_time_ms}")


                except Exception as e:
                     print(f"Error processing individual SRT file {srt_filepath}: {e}")
                     # Decide whether to skip or halt; skipping allows partial results
                     continue # Skip to next file

        print(f"Successfully combined SRT files into: {output_filepath}")
        return output_filepath
    except Exception as e:
        print(f"Error combining SRT files into {output_filepath}: {e}")
        # Clean up potentially incomplete output file
        if os.path.exists(output_filepath):
            try:
                os.remove(output_filepath)
            except OSError:
                 pass
        return None

# --- Main Processing Function ---
def process_audio(
    input_path,               # URL or local file path
    output_srt_filepath,      # Full path for the final desired SRT file
    model_name,               # e.g., "whisper-large-v3"
    language,                 # Language code (e.g., "ja", "en")
    status_callback,          # Function to update GUI status
    lengthen_subtitles_flag,  # Boolean
    delete_segments_flag,     # Boolean
    delete_temp_audio_flag,   # Boolean (for downloaded audio)
    delete_segment_srts_flag  # Boolean
):
    """
    Main workflow: Processes audio (URL/file), segments, transcribes (handling verbose_json),
    combines with timestamp adjustment, optionally lengthens, optionally cleans up.
    Returns True on success, False on failure.
    """
    output_dir = os.path.dirname(output_srt_filepath)
    final_srt_base_name = os.path.splitext(os.path.basename(output_srt_filepath))[0]
    # Use more robust temporary names
    temp_combined_srt_path = os.path.join(output_dir, f"_temp_{final_srt_base_name}_combined_raw.srt")
    temp_lengthened_srt_path = os.path.join(output_dir, f"_temp_{final_srt_base_name}_combined_lengthened.srt")
    temp_downloaded_audio_file = os.path.join(output_dir, f"_temp_{final_srt_base_name}_downloaded.mp3")

    audio_to_process = None
    is_downloaded = False
    generated_segment_files = []
    generated_segment_srt_files = [] # Store paths of SRTs from segments

    os.makedirs(output_dir, exist_ok=True)

    try:
        # 1. Handle Input: Download or use local file
        if input_path.startswith("http://") or input_path.startswith("https://"):
            audio_to_process = download_audio_from_url(input_path, temp_downloaded_audio_file, status_callback)
            if not audio_to_process:
                return False
            is_downloaded = True
        elif os.path.exists(input_path):
             audio_to_process = input_path
             status_callback(f"Using local audio file: {input_path}")
        else:
            status_callback(f"Error: Input file not found: {input_path}")
            return False

        # 2. Segment audio using FFmpeg
        status_callback("Segmenting audio into 10-minute chunks...")
        # Use a specific prefix related to the output name
        segment_prefix = os.path.join(output_dir, f"{final_srt_base_name}_segment_%03d.mp3") # %03d allows up to 999 segments
        ffmpeg_command = [
            "ffmpeg",
            "-i", audio_to_process,
            "-f", "segment",
            "-segment_time", "600",  # 10 minutes
            "-c", "copy", # Use copy codec for speed if input is MP3
            segment_prefix,
            "-reset_timestamps", "1", # Crucial for combining logic
            "-y",  # Overwrite existing files
        ]
        try:
            print("Running FFmpeg command:", " ".join(ffmpeg_command))
            result = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, encoding='utf-8')
            if result.stderr: # Check stderr for potential warnings/errors even if exit code is 0
                 # Filter common non-error messages if needed
                 if "deprecated pixel format" not in result.stderr.lower() and "use -pix_fmt" not in result.stderr.lower():
                     print(f"FFmpeg stderr output:\n{result.stderr}")
                     # status_callback(f"FFmpeg messages during segmentation. Check console.")
            status_callback("Audio segmentation complete.")
        except subprocess.CalledProcessError as e:
            status_callback(f"Error during segmentation: FFmpeg failed. Check console.")
            print(f"FFmpeg Error stdout: {e.stdout}")
            print(f"FFmpeg Error stderr: {e.stderr}")
            return False
        except FileNotFoundError:
            status_callback("Error: 'ffmpeg' command not found. Make sure it's installed and in your system's PATH.")
            print("Error: 'ffmpeg' command not found.")
            return False
        except Exception as e:
             status_callback(f"Unexpected error during segmentation: {e}")
             print(f"Unexpected segmentation error: {e}")
             return False

        # Find generated segments (use the pattern from ffmpeg command)
        segmented_files_pattern = os.path.join(output_dir, f"{final_srt_base_name}_segment_*.mp3")
        generated_segment_files = sorted(glob.glob(segmented_files_pattern))
        if not generated_segment_files:
             status_callback("Error: No audio segments were created by ffmpeg.")
             print(f"Looked for segments matching: {segmented_files_pattern}")
             return False
        print(f"Found segments: {[os.path.basename(f) for f in generated_segment_files]}")

        # 3. Transcribe segments one by one
        total_segments = len(generated_segment_files)
        for i, audio_seg_file in enumerate(generated_segment_files):
            status_callback(f"Transcribing segment {i+1}/{total_segments}: {os.path.basename(audio_seg_file)}...")
            # Pass the selected language to the transcription function
            srt_path = process_audio_segment(audio_seg_file, output_dir, model_name, language)
            if srt_path:
                generated_segment_srt_files.append(srt_path) # Add path of the generated SRT
            else:
                status_callback(f"Error transcribing {os.path.basename(audio_seg_file)}. Skipping segment. Check console.")
                print(f"Failed to transcribe {os.path.basename(audio_seg_file)}, skipping.")

        # 4. Combine Segment SRT files (Adjusting Timestamps)
        if not generated_segment_srt_files:
            status_callback("Error: No SRT files were generated from segments.")
            return False

        status_callback("Combining transcribed SRT segments (adjusting timestamps)...")
        # Combine into the temporary raw combined path
        combined_success = combine_srt_files(generated_segment_srt_files, output_dir, temp_combined_srt_path)

        if not combined_success:
            status_callback("Error combining SRT files.")
            return False
        status_callback("SRT segments combined successfully.")


        # 5. Lengthen subtitles (Optional) - Operates on the combined file
        final_srt_to_rename = temp_combined_srt_path # Start with the raw combined path
        if lengthen_subtitles_flag:
            status_callback("Lengthening subtitles (merging short blocks)...")
            try:
                with open(temp_combined_srt_path, "r", encoding="utf-8") as f_in:
                    raw_srt_content = f_in.read()

                # Use srt_utils functions here
                parsed_data = parse_srt(raw_srt_content)
                if not parsed_data:
                     status_callback("Warning: Could not parse combined SRT for lengthening. Skipping lengthening.")
                     print("Warning: parse_srt returned no entries from combined file. Skipping lengthening.")
                else:
                    merged_data = merge_subtitles(parsed_data, min_chars=45) # Default 45 chars
                    output_srt_lengthened = format_srt(merged_data)

                    # Write lengthened data to a *different* temp file
                    with open(temp_lengthened_srt_path, "w", encoding="utf-8") as f_out:
                        f_out.write(output_srt_lengthened)

                    status_callback("Subtitles lengthened.")
                    final_srt_to_rename = temp_lengthened_srt_path # Update the path to be renamed

            except Exception as e:
                status_callback(f"Error lengthening subtitles: {e}. Using un-lengthened version.")
                print(f"Error lengthening subtitles: {e}")
                # Keep final_srt_to_rename as temp_combined_srt_path

        # 6. Rename the final temporary SRT file to the desired output filename
        status_callback(f"Saving final SRT to: {output_srt_filepath}")
        try:
            # Ensure the final source file exists before renaming
            if not os.path.exists(final_srt_to_rename):
                 status_callback(f"Error: Intermediate SRT file '{os.path.basename(final_srt_to_rename)}' not found before final rename.")
                 return False

            # If the final destination file exists, remove it first
            if os.path.exists(output_srt_filepath):
                os.remove(output_srt_filepath)

            os.rename(final_srt_to_rename, output_srt_filepath)
            status_callback(f"Successfully processed audio and saved SRT to: {output_srt_filepath}")
            return True # Indicate overall success

        except OSError as e:
            status_callback(f"Error saving final SRT file: {e}")
            print(f"Error renaming '{final_srt_to_rename}' to '{output_srt_filepath}': {e}")
            # Try to keep the intermediate file if renaming fails
            status_callback(f"Keeping intermediate SRT file: {final_srt_to_rename}")
            return False

    except Exception as e:
        status_callback(f"An critical error occurred during processing: {e}")
        print(f"CRITICAL PROCESSING Error: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        return False

    finally:
        # 7. Cleanup Intermediate Files (always attempt cleanup)
        status_callback("Cleaning up intermediate files...")
        cleaned_count = 0

        # Delete segment MP3 files
        if delete_segments_flag:
            for f in generated_segment_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                        cleaned_count += 1
                    except OSError as e:
                        print(f"Warning: Could not delete segment file {f}: {e}")
            status_callback(f"Cleaned up {cleaned_count} segment MP3 files.")
            cleaned_count = 0

        # Delete individual segment SRT files
        if delete_segment_srts_flag:
            for f in generated_segment_srt_files:
                 if os.path.exists(f):
                    try:
                        os.remove(f)
                        cleaned_count += 1
                    except OSError as e:
                        print(f"Warning: Could not delete segment SRT file {f}: {e}")
            status_callback(f"Cleaned up {cleaned_count} segment SRT files.")
            cleaned_count = 0

        # Delete downloaded audio file (if applicable)
        if is_downloaded and delete_temp_audio_flag and os.path.exists(temp_downloaded_audio_file):
            try:
                os.remove(temp_downloaded_audio_file)
                status_callback("Cleaned up downloaded audio file.")
            except OSError as e:
                print(f"Warning: Could not delete downloaded audio file {temp_downloaded_audio_file}: {e}")

        # --- Delete temporary combined files ---
        # Delete raw combined file if it exists AND wasn't the one successfully renamed
        if os.path.exists(temp_combined_srt_path) and temp_combined_srt_path != output_srt_filepath:
            try:
                os.remove(temp_combined_srt_path)
            except OSError as e:
                 print(f"Warning: Could not delete intermediate raw combined SRT {temp_combined_srt_path}: {e}")
        # Delete lengthened combined file if it exists AND wasn't the one successfully renamed
        if os.path.exists(temp_lengthened_srt_path) and temp_lengthened_srt_path != output_srt_filepath:
             try:
                 os.remove(temp_lengthened_srt_path)
             except OSError as e:
                  print(f"Warning: Could not delete intermediate lengthened SRT {temp_lengthened_srt_path}: {e}")

        status_callback("Cleanup finished.")
        # The function returns True/False based on processing success before cleanup
        