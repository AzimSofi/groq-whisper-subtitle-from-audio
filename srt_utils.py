import re
import io
import os


def parse_srt(srt_string):
    """Parses an SRT string into a list of subtitle entry dictionaries."""
    entries = []
    pattern = re.compile(
        r'(\d+)\s*'  # Index
        r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*'  # Timestamps
        r'([\s\S]*?)\s*'  # Text (non-greedy match until next block or end)
        r'(?=\n\n\d+|\Z)', # Lookahead for blank line + next index or end of string
        re.MULTILINE
    )
    for match in pattern.finditer(srt_string.strip()):
        try:
            index = int(match.group(1))
            start_time = match.group(2)
            end_time = match.group(3)
            text = match.group(4).strip()
            entries.append({
                'index': index,
                'start': start_time,
                'end': end_time,
                'text': text
            })
        except Exception as e:
            print(f"Warning: Skipping potentially malformed block near index {match.group(1)} due to error: {e}")
            # Optionally add more robust error handling or logging here
    return entries

def merge_subtitles(entries, min_chars=45):
    """Merges consecutive subtitle entries based on minimum character count."""
    if not entries:
        return []

    merged_entries = []
    current_block = None

    for entry in entries:
        if current_block is None:
            # Start the first block
            current_block = {
                'start': entry['start'],
                'end': entry['end'],
                'text': entry['text'],
                'char_count': len(entry['text'])
            }
        else:
            # Get text to add (could be empty)
            text_to_add = entry['text']
            current_text_len = current_block['char_count']
            
            # Decide whether to merge based on the *current* block's length
            if current_text_len < min_chars:
                # Merge this entry into the current block regardless of the added length
                combined_text = current_block['text'] + text_to_add
                current_block['end'] = entry['end']
                current_block['text'] = combined_text
                current_block['char_count'] = len(combined_text) # Update count
            else:
                # Current block was already long enough. Finalize it.
                merged_entries.append({
                    'start': current_block['start'],
                    'end': entry['end'],
                    'text': current_block['text']
                })
                # Start a new block with the current entry
                current_block = {
                    'start': entry['start'],
                    'end': entry['end'],
                    'text': text_to_add,
                    'char_count': len(text_to_add)
                }

    # Add the last remaining block (handle leftovers)
    if current_block:
        merged_entries.append({
            'start': current_block['start'],
            'end': current_block['end'],
            'text': current_block['text']
        })

    return merged_entries

def format_srt(merged_entries):
    """Formats a list of merged entries back into an SRT string."""
    output = io.StringIO()
    for i, entry in enumerate(merged_entries, 1):
        output.write(str(i) + '\n')
        output.write(f"{entry['start']} --> {entry['end']}\n")
        # Ensure text doesn't end with multiple newlines before the blank line
        output.write(entry['text'].strip() + '\n\n')
    # Use rstrip to remove only trailing whitespace/newlines from the whole string
    return output.getvalue().rstrip() + '\n'  # Ensure single trailing newline


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
                return float('inf')  # Put files without valid segment numbers at the end
        return float('inf')  # For files not matching naming convention, keep original order if not sortable

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
