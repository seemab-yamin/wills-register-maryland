# Logging Implementation Documentation

## Overview

This project now includes comprehensive logging functionality using Python's built-in `logging` module. The logging system provides detailed tracking of application events, errors, and debugging information.

## Features

### ✅ Implemented Requirements

1. **Dual Output**: Logs are output to both console and file (`app.log`)
2. **Consistent Format**: Uses the format `'%(asctime)s - %(name)s - %(levelname)s - %(message)s'`
3. **INFO Level Default**: Set to INFO level by default
4. **Modular Setup**: Encapsulated in a reusable `setup_logging()` function
5. **File Rotation**: Log files rotate after 5MB, keeping the last 3 backups

### Additional Features

- **Module-specific Loggers**: Each module gets its own logger with appropriate names
- **Comprehensive Coverage**: All major functions and error conditions are logged
- **Debug Information**: Detailed debug logs for troubleshooting
- **Error Tracking**: Proper error logging with context information

## Log Format

```
2025-07-29 09:13:45,136 - __main__ - INFO - MDScraperApp initialized
```

- **Timestamp**: ISO format with milliseconds
- **Module Name**: Identifies which module generated the log
- **Log Level**: INFO, WARNING, ERROR, DEBUG
- **Message**: Descriptive log message

## Log Levels Used

- **DEBUG**: Detailed information for debugging (not shown in console by default)
- **INFO**: General information about application flow
- **WARNING**: Warning messages for potential issues
- **ERROR**: Error messages for failed operations

## File Rotation

The logging system automatically manages log files:

- **Current Log**: `app.log`
- **Backup Files**: `app.log.1`, `app.log.2`, `app.log.3`
- **Max Size**: 5MB per file
- **Backup Count**: 3 backup files

## Implementation Details

### Setup Function

The `setup_logging()` function in `utils.py`:

```python
def setup_logging():
    """
    Sets up logging configuration for the application.
    
    Configures:
    - Console handler for INFO level and above
    - File handler with rotation (5MB max, 3 backups)
    - Consistent log format
    - Root logger level set to INFO
    """
```

### Usage in Code

Each module creates its own logger:

```python
logger = logging.getLogger(__name__)
logger.info("Application started")
logger.error("An error occurred")
```

### Key Logging Points

#### Main Application (`main.py`)
- Application initialization
- UI component creation
- User interactions (directory selection, form validation)
- Scraping process start/completion
- Error conditions

#### Utils Module (`utils.py`)
- HTTP request attempts and results
- Parameter extraction
- Page scraping progress
- Individual item processing
- Error handling

## Testing

A test script (`test_logging.py`) is included to verify logging functionality:

```bash
python test_logging.py
```

This script tests:
- All log levels
- File creation
- Log format
- Module-specific loggers

## Log File Location

Log files are created in the project root directory:
- `app.log` - Current log file
- `app.log.1`, `app.log.2`, `app.log.3` - Backup files (when rotation occurs)

## Example Log Output

```
2025-07-29 09:13:44,966 - utils - INFO - Logging setup completed
2025-07-29 09:13:44,966 - __main__ - INFO - Starting MDScraperApp
2025-07-29 09:13:45,136 - __main__ - INFO - MDScraperApp initialized
2025-07-29 09:13:45,155 - __main__ - INFO - UI components created successfully
2025-07-29 09:13:45,177 - __main__ - INFO - Application window displayed
2025-07-29 09:13:54,522 - __main__ - INFO - Selected output directory: /Users/levi/untitled folder
2025-07-29 09:13:55,490 - __main__ - INFO - User requested exit - showing confirmation dialog
2025-07-29 09:13:56,675 - __main__ - INFO - User confirmed exit - shutting down application
```

## Benefits

1. **Debugging**: Easy to trace application flow and identify issues
2. **Monitoring**: Track user interactions and system performance
3. **Error Tracking**: Comprehensive error logging with context
4. **Maintenance**: Rotating log files prevent disk space issues
5. **Development**: Debug logs help during development and testing

## Configuration

To modify logging behavior, edit the `setup_logging()` function in `utils.py`:

- Change log level: Modify `setLevel()` calls
- Adjust file size: Change `maxBytes` parameter
- Modify backup count: Change `backupCount` parameter
- Update format: Modify the `Formatter` string

## Troubleshooting

### Common Issues

1. **No log file created**: Check write permissions in project directory
2. **Logs not appearing**: Verify log level settings
3. **Large log files**: Check rotation settings and backup count

### Debug Mode

To enable debug logging, modify the log level in `setup_logging()`:

```python
console_handler.setLevel(logging.DEBUG)
file_handler.setLevel(logging.DEBUG)
```

This will show all log messages including DEBUG level information. 