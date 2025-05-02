# srt_utils.py
import re
import io
import os

def parse_srt(srt_string):
    """Parses an SRT string into a list of subtitle entry dictionaries."""
    entries = []
    # More robust pattern: handles optional spaces, different line endings
    pattern = re.compile(
        r'(\d+)\r?\n'
        r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\r?\n'
        r'([\s\S]*?)\r?\n\r?\n',  # Match text until a blank line
        re.MULTILINE
    )
    # Add a check for potential final entry without double newline
    if not srt_string.strip().endswith('\n\n'):
        srt_string += '\n\n'

    for match in pattern.finditer(srt_string):
        try:
            index = int(match.group(1))
            start_time = match.group(2)
            end_time = match.group(3)
            text = match.group(4).strip() # Strip leading/trailing whitespace from text block
            if text: # Only add if text is not empty
                entries.append({
                    'index': index,
                    'start': start_time,
                    'end': end_time,
                    'text': text
                })
        except Exception as e:
            print(f"Warning: Skipping potentially malformed block near index {match.group(1) if match.group(1) else '?'} due to error: {e}")
            # Attempt to find the start of the block for logging
            # block_start = match.start()
            # print(f"Problematic block content preview:\n---\n{srt_string[block_start:block_start+100]}\n---")
    return entries

def merge_subtitles(entries, min_chars=45):
    """
    Merges consecutive subtitle entries if the *first* entry's text
    is shorter than min_chars. Appends text and extends end time.
    """
    if not entries:
        return []

    merged_entries = []
    i = 0
    while i < len(entries):
        current_entry = entries[i].copy() # Work with a copy

        # Check if we need to merge based on current entry's length
        while len(current_entry['text']) < min_chars and (i + 1) < len(entries):
            # Merge with the next entry
            next_entry = entries[i + 1]
            # Append text with a space if needed (optional, adjust if you prefer no space)
            if current_entry['text'] and next_entry['text']:
                 current_entry['text'] += " " + next_entry['text']
            else: # Handle cases where one text might be empty initially
                 current_entry['text'] += next_entry['text']

            current_entry['end'] = next_entry['end'] # Update end time to the end of the merged block
            i += 1 # Move index past the merged entry

        merged_entries.append(current_entry)
        i += 1 # Move to the next entry to evaluate

    return merged_entries


def format_srt(merged_entries):
    """Formats a list of merged entries back into an SRT string."""
    output = io.StringIO()
    for i, entry in enumerate(merged_entries, 1):
        # Ensure start/end times are strings in the correct format (they should be)
        start_time = entry.get('start', '00:00:00,000')
        end_time = entry.get('end', '00:00:00,000')
        text = entry.get('text', '').strip() # Ensure text is stripped

        if not text: # Skip entries with no text after potential merging/stripping
             continue

        output.write(str(i) + '\n')
        output.write(f"{start_time} --> {end_time}\n")
        # Ensure text doesn't end with multiple newlines before the blank line
        output.write(text + '\n\n') # Write text and the required blank line

    # Use rstrip to remove only trailing whitespace/newlines from the whole string
    # Add one newline at the end for POSIX compliance if desired, but SRT usually just ends after the last blank line.
    final_srt = output.getvalue().rstrip()
    if final_srt: # Add trailing newline only if there's content
        final_srt += '\n'
    return final_srt
