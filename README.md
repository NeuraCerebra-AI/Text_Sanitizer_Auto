# Text_Sanitizer_Auto

## Overview

Text_Sanitizer_Auto is a robust tool designed to clean, chunk, and process text files efficiently. It leverages advanced features such as rate limiting, detailed logging, retry logic, and multi-threaded processing to ensure high performance and resilience. This script is ideal for anyone needing to clean large volumes of text files, preserving content integrity while removing unwanted formatting and artifacts.

## Features

- **Advanced Text Cleaning**: Removes page numbers, headers, footers, and other irrelevant information.
- **Chunk Processing**: Splits large text files into manageable chunks for efficient processing.
- **Rate Limiting**: Ensures API usage compliance with configurable rate limits.
- **Retry Logic**: Automatically retries failed operations with exponential backoff.
- **Detailed Logging**: Provides comprehensive logs for each processing step, aiding in debugging and monitoring.
- **Multi-Threaded Processing**: Speeds up processing by handling multiple files concurrently.
- **Content Filtering Handling**: Manages and logs content filtering issues gracefully.

## Installation

### Prerequisites

Ensure you have the following installed:
- Python 3.8 or higher
- Pip (Python package installer)

### Setup

1. Clone the repository:
    ```bash
    git clone https://github.com/PixelPoser/Text_Sanitizer_Auto.git
    cd Text_Sanitizer_Auto
    ```

2. Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Set your Anthropic API key:
    ```bash
    export ANTHROPIC_API_KEY='your_api_key_here'
    ```

## Usage

1. **Prepare your text files**: Place your text files in a directory. The script accepts both individual text files and directories containing multiple text files.

2. **Run the script**:
    ```bash
    python text_sanitizer_auto.py.py
    ```

3. **Follow the prompts**: The script will prompt you to enter the path to your text file or directory. It will then proceed to clean and process the files, saving the cleaned versions and logs in designated folders.

## Configuration

### Rate Limiting

The rate limiter is set to allow 999 API calls per minute by default. You can adjust this setting in the `RateLimiter` class within the script if needed.

### Chunk Size

The default chunk size for processing is 200 lines. This can be modified by changing the `chunk_size` parameter in the `chunk_text` function.

## Logging

Logs are saved in a folder named `processing_logs` within the source directory. Each file processed will have an individual log file detailing the processing steps and any issues encountered.

## Error Handling

The script includes robust error handling and retry logic, utilizing the `tenacity` library to retry failed operations with exponential backoff. Content filtering issues are logged and managed gracefully.

## Contributing

We welcome contributions! If you'd like to contribute, please follow these steps:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Make your changes and commit them (`git commit -m 'Add new feature'`).
4. Push to the branch (`git push origin feature-branch`).
5. Create a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgements

- Special thanks to the Anthropic.


---

This `README.md` covers all essential aspects of your project, providing clear instructions for setup, usage, configuration, and contribution, while highlighting the script's features and benefits.
