import os
import anthropic
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging
import json
import threading
from tenacity import retry, stop_after_attempt, wait_exponential

# Set up logging with more detailed format
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

# Configure Anthropic API
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
if not ANTHROPIC_API_KEY:
    raise ValueError("The Anthropic API key is not set in the environment variables.")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Global rate limiting
class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            with self.lock:
                now = time.time()
                self.calls = [t for t in self.calls if now - t < self.period]
                if len(self.calls) >= self.max_calls:
                    sleep_time = self.period - (now - self.calls[0])
                    logging.debug(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds")
                    time.sleep(sleep_time)
                self.calls.append(now)
                logging.debug(f"Rate limiter: {len(self.calls)} calls in the last {self.period} seconds")
            return func(*args, **kwargs)
        return wrapper

# Create a rate limiter that allows 999 calls per minute
rate_limiter = RateLimiter(max_calls=999, period=60)

def get_user_input():
    """Prompt the user for input and validate it."""
    logging.info("Requesting user input for file or folder path")
    while True:
        path = input("Enter the path to a text file or a folder containing text files: ").strip()
        logging.debug(f"User input received: {path}")
        if os.path.isfile(path) and path.lower().endswith('.txt'):
            logging.info(f"Valid single file path provided: {path}")
            return [path], os.path.dirname(path)
        elif os.path.isdir(path):
            txt_files = [os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith('.txt')]
            if txt_files:
                logging.info(f"Valid folder path provided. Found {len(txt_files)} text files.")
                return txt_files, path
            else:
                logging.warning(f"No text files found in the specified folder: {path}")
                print("No text files found in the specified folder.")
        else:
            logging.warning(f"Invalid input provided: {path}")
            print("Invalid input. Please enter a valid text file path or folder path.")

def create_output_folder(source_folder):
    """Create an output folder for cleaned text files."""
    output_folder = os.path.join(source_folder, "cleaned_text")
    os.makedirs(output_folder, exist_ok=True)
    logging.info(f"Created output folder: {output_folder}")
    return output_folder

def create_log_folder(source_folder):
    """Create a log folder for processing logs."""
    log_folder = os.path.join(source_folder, "processing_logs")
    os.makedirs(log_folder, exist_ok=True)
    logging.info(f"Created log folder: {log_folder}")
    return log_folder

def read_file_with_fallback_encoding(file_path):
    """Attempt to read a file with multiple encodings."""
    encodings = ['utf-8', 'latin-1', 'ascii', 'utf-16']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                content = file.read()
                logging.info(f"Successfully read file {file_path} with encoding {encoding}")
                return content
        except UnicodeDecodeError:
            logging.debug(f"Failed to read {file_path} with encoding {encoding}")
    logging.error(f"Unable to read the file {file_path} with any of the attempted encodings")
    raise ValueError(f"Unable to read the file {file_path} with any of the attempted encodings")

def chunk_text(text, chunk_size=200):
    """Split the text into chunks of approximately equal size."""
    logging.info(f"Chunking text of length {len(text)} with chunk size {chunk_size}")
    chunks = []
    current_chunk = []
    current_size = 0
    for line in text.split('\n'):
        if current_size + len(line) > chunk_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = []
            current_size = 0
        current_chunk.append(line)
        current_size += len(line) + 1  # +1 for newline
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    # Skip empty chunks
    chunks = [chunk for chunk in chunks if chunk.strip()]
    logging.info(f"Created {len(chunks)} non-empty chunks")
    return chunks

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
@rate_limiter
def clean_text_chunk(chunk, chunk_number, total_chunks):
    """Clean a chunk of text using Claude 3 Haiku with improved error handling."""
    logging.info(f"Processing chunk {chunk_number} of {total_chunks}")
    prompt = f"""
    You are formatting chunk {chunk_number} of {total_chunks} from a larger text file. 
    Please follow these formatting instructions:

    1. Remove any irrelevant information such as page numbers, headers, footers, and formatting artifacts.
        - If you see a random "chapter"-like half-sentence blurb seemingly inside or in-between an unrelated sentence, assume that is a Chapter name that occurs on every page and get rid of it.
        - Get rid of any random numbers in-between or inside sentences that do not make sense. These are likely page numbers.
    2. Ensure the words are exactly the same except for formatting fixes and misspellings.
        - Never write commentary, for example: "Here is the cleaned text content for chunk 336 of 644:".
    3. Ensure that the output is clean and well-formatted.
    4. If the text contains descriptions of tables, charts, or images, preserve this information in a clear, textual format.
    5. Maintain the context and flow of the text, considering that this is part of a larger document.
    6. It is crucial that you process and return the ENTIRE chunk.

    Here's the text chunk to clean:

    {chunk}

    Please provide ONLY the cleaned text content without any additional commentary or confirmation:
    """
    
    logging.debug(f"Prompt for chunk {chunk_number}:\n{prompt}")

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4000,
            temperature=0.0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        logging.debug(f"Raw API response for chunk {chunk_number}:\n{response.content[0].text[:500]}...")

        cleaned_text = response.content[0].text.strip()
        logging.info(f"Successfully cleaned chunk {chunk_number}")
        return cleaned_text, True

    except anthropic.APIError as e:
        if "content filtering" in str(e).lower():
            logging.warning(f"Content filter triggered for chunk {chunk_number}. Returning original chunk.")
            return chunk, False
        else:
            logging.error(f"API error for chunk {chunk_number}: {str(e)}")
            raise

    except Exception as e:
        logging.error(f"Unexpected error processing chunk {chunk_number}: {str(e)}")
        raise

def process_text_file(file_path, output_folder, log_folder):
    """Process a single text file."""
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    logging.info(f"Starting to process file: {file_path}")

    # Create chunk folder
    chunk_folder = os.path.join(output_folder, "chunks", base_name)
    os.makedirs(chunk_folder, exist_ok=True)
    logging.info(f"Created chunk folder: {chunk_folder}")

    log_file = os.path.join(log_folder, f"{base_name}_log.json")
    
    log_data = {
        "file_name": base_name,
        "start_time": time.time(),
        "status": "processing",
        "errors": [],
        "chunks_info": []
    }

    try:
        text = read_file_with_fallback_encoding(file_path)
        chunks = chunk_text(text)
        log_data["total_chunks"] = len(chunks)

        # Generate all chunks first
        logging.info(f"Generating {len(chunks)} chunks for {base_name}")
        for i, chunk in enumerate(chunks, 1):
            chunk_file_path = os.path.join(chunk_folder, f"{base_name}_chunk_{i}.txt")
            with open(chunk_file_path, 'w', encoding='utf-8') as out_file:
                out_file.write(chunk)
            logging.debug(f"Wrote chunk {i} to {chunk_file_path}")

        # Process all chunks sequentially
        cleaned_chunks = 0
        logging.info(f"Processing {len(chunks)} chunks for {base_name}")

        for i in range(len(chunks)):
            chunk_number = i + 1
            chunk_file_path = os.path.join(chunk_folder, f"{base_name}_chunk_{chunk_number}.txt")
            while True:
                try:
                    with open(chunk_file_path, 'r', encoding='utf-8') as in_file:
                        chunk = in_file.read()

                    cleaned_chunk, was_cleaned = clean_text_chunk(chunk, chunk_number, len(chunks))
                    if was_cleaned:
                        cleaned_chunks += 1

                    with open(chunk_file_path, 'w', encoding='utf-8') as out_file:
                        out_file.write(cleaned_chunk + "\n\n")

                    chunk_info = {
                        "chunk_number": chunk_number,
                        "original_length": len(chunk),
                        "cleaned_length": len(cleaned_chunk),
                        "cleaned": was_cleaned
                    }
                    log_data["chunks_info"].append(chunk_info)

                    logging.info(f"Chunk {chunk_number} of {base_name} processed {'and cleaned' if was_cleaned else 'but not cleaned due to content filter'}")
                    break

                except Exception as e:
                    logging.error(f"Error processing chunk {chunk_number} of {base_name}: {str(e)}", exc_info=True)
                    log_data["errors"].append(f"Chunk {chunk_number}: {str(e)}")
                    time.sleep(5)  # Wait before retrying

        # Combine chunks into a single file
        logging.info(f"Combining processed chunks for {base_name}")
        cleaned_text = ""
        for i in range(1, len(chunks) + 1):
            chunk_file_path = os.path.join(chunk_folder, f"{base_name}_chunk_{i}.txt")
            if os.path.exists(chunk_file_path):
                with open(chunk_file_path, 'r', encoding='utf-8') as in_file:
                    cleaned_text += in_file.read()
                logging.debug(f"Added content from chunk {i} to final cleaned text")

        # Write the combined cleaned text to the output file
        output_file = os.path.join(output_folder, f"{base_name}_cleaned.txt")
        with open(output_file, 'w', encoding='utf-8') as out_file:
            out_file.write(cleaned_text)
        logging.info(f"Wrote combined cleaned text to {output_file}")

        log_data["status"] = "completed"
        log_data["end_time"] = time.time()
        log_data["processing_time"] = log_data["end_time"] - log_data["start_time"]
        log_data["cleaned_chunks"] = cleaned_chunks
        logging.info(f"Finished processing file: {file_path}")

    except Exception as e:
        logging.error(f"Error processing {file_path}: {str(e)}", exc_info=True)
        log_data["status"] = "failed"
        log_data["errors"].append(str(e))
    
    finally:
        log_data["end_time"] = time.time()
        log_data["processing_time"] = log_data["end_time"] - log_data["start_time"]
        
        with open(log_file, 'w', encoding='utf-8') as log:
            json.dump(log_data, log, indent=2)
        logging.info(f"Wrote processing log to {log_file}")

    return cleaned_chunks, len(chunks)

def main():
    logging.info("Starting main process")
    txt_files, source_folder = get_user_input()
    output_folder = create_output_folder(source_folder)
    log_folder = create_log_folder(source_folder)
    
    successful_files = 0
    total_chunks = 0
    total_cleaned_chunks = 0
    total_start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=len(txt_files)) as executor:
        futures = [executor.submit(process_text_file, txt_file, output_folder, log_folder) for txt_file in txt_files]
        
        with tqdm(total=len(txt_files), desc="Overall Progress") as pbar:
            for future in as_completed(futures):
                cleaned, total = future.result()
                total_cleaned_chunks += cleaned
                total_chunks += total
                if cleaned > 0:
                    successful_files += 1
                pbar.update(1)
    
    total_time = time.time() - total_start_time
    
    # Calculate statistics
    failed_files = len(txt_files) - successful_files
    not_cleaned_chunks = total_chunks - total_cleaned_chunks
    cleaning_percentage = (total_cleaned_chunks / total_chunks * 100) if total_chunks > 0 else 0
    
    # Prepare summary report
    summary = f"""
    Processing Summary:
    -------------------
    Total files processed: {len(txt_files)}
    Successfully processed files: {successful_files}
    Failed files: {failed_files}
    
    Chunk Statistics:
    -----------------
    Total chunks: {total_chunks}
    Cleaned chunks: {total_cleaned_chunks}
    Not cleaned chunks: {not_cleaned_chunks}
    Percentage of chunks cleaned: {cleaning_percentage:.2f}%
    
    Performance:
    ------------
    Total processing time: {total_time:.2f} seconds
    Average time per file: {total_time / len(txt_files):.2f} seconds
    
    Output Locations:
    -----------------
    Cleaned text files are saved in: {output_folder}
    Processing logs are saved in: {log_folder}
    """
    
    print(summary)
    logging.info(summary)
    
    # Write summary to a file
    summary_file = os.path.join(log_folder, "processing_summary.txt")
    with open(summary_file, 'w') as f:
        f.write(summary)
    logging.info(f"Wrote processing summary to {summary_file}")
    
    # Check for any completely failed files
    if failed_files > 0:
        logging.warning(f"{failed_files} files failed to process completely. Check the logs for details.")
    
    # Suggest next steps
    if cleaning_percentage < 50:
        print("\nNote: Less than 50% of chunks were cleaned. You may want to review the content filtering settings or the nature of your input text.")
    
    print("\nProcessing complete. Check the processing_summary.txt file for a detailed report.")

if __name__ == "__main__":
    main()
