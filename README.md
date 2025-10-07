# wills-register-maryland
Wills Register - Maryland is a project that involves the development and building of the Exe tool. That takes user input and performs scraping, and saves scraped data in an Excel file.

# TODO
- MM/DD/YYYY ✔️
- Demo Exe Generation ✔️
- Complete Exe Generation ✔️
- Reformat ✔️
- Update the output format ✔️
- Capitalize PR Columns ✔️
- Split Address/City ✔️
- Patch Zip Code to String. Now it will note remove trailing 0 ✔️ 
- Command Line Arguments To Run the Program ✔️
- Generate Exe For Testing ✔️
- Implement Heavy Computation in BG Thread
- Disable Warning (WARNING - Suppressing InsecureRequestWarning: SSL verification is disabled for this request)


```python
python main.py --headless=True --date-from=10/05/2025 --date-to=10/06/2025 --doc-type=d --output-dir="./output" --record-limit=3
```