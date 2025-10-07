import argparse
import logging
import os
import sys
import time
from datetime import datetime

import pandas as pd
import pandera.pandas as pa
from bs4 import BeautifulSoup
from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data_schemas import ProbateSchema
from utils import get_html, get_parameters, scrape_page, scrape_single, setup_logging

PARTY_TYPES = {
    "pr": "Personal Representative",
    "d": "Decedent",
}


class MDScraperApp(QMainWindow):

    def __init__(self, record_limit=None):
        super().__init__()
        self.record_limit = record_limit
        self.setWindowTitle("Wills Register Maryland Scraper")
        self.setFixedSize(500, 300)
        self._close_enabled = True

        # Setup logging for this application
        self.logger = logging.getLogger(__name__)
        self.logger.info("MDScraperApp initialized")

        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Create form widgets
        self.create_date_widgets(main_layout)
        self.create_type_widgets(main_layout)
        self.create_output_widgets(main_layout)
        self.create_action_buttons(main_layout)

        self.logger.info("UI components created successfully")

    def create_date_widgets(self, layout):
        # Date range section
        date_layout = QHBoxLayout()

        # From date
        from_layout = QVBoxLayout()
        from_layout.addWidget(QLabel("From Date:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("MM/dd/yyyy")
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        from_layout.addWidget(self.date_from)

        # To date
        to_layout = QVBoxLayout()
        to_layout.addWidget(QLabel("To Date:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("MM/dd/yyyy")
        self.date_to.setDate(QDate.currentDate())
        to_layout.addWidget(self.date_to)

        date_layout.addLayout(from_layout)
        date_layout.addLayout(to_layout)
        layout.addLayout(date_layout)

    def create_type_widgets(self, layout):
        # Document type selection
        type_layout = QVBoxLayout()
        type_layout.addWidget(QLabel("Party Type:"))
        self.doc_type = QComboBox()
        self.doc_type.addItems(["Personal Representative", "Decedent"])
        type_layout.addWidget(self.doc_type)
        layout.addLayout(type_layout)

    def create_output_widgets(self, layout):
        # Output directory selection
        output_layout = QVBoxLayout()
        output_layout.addWidget(QLabel("Output Directory:"))

        dir_layout = QHBoxLayout()
        self.output_dir = QLineEdit()
        self.output_dir.setReadOnly(True)
        dir_layout.addWidget(self.output_dir)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.select_directory)
        dir_layout.addWidget(self.browse_btn)

        output_layout.addLayout(dir_layout)
        layout.addLayout(output_layout)

    def create_action_buttons(self, layout):
        # Action buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Scraping")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.start_btn.clicked.connect(self.start_process)
        btn_layout.addWidget(self.start_btn)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.reset_btn.clicked.connect(self.reset_form)
        btn_layout.addWidget(self.reset_btn)

        self.exit_btn = QPushButton("Exit")
        self.exit_btn.setStyleSheet("background-color: #888888; color: white;")
        self.exit_btn.clicked.connect(self.confirm_exit)
        btn_layout.addWidget(self.exit_btn)

        layout.addLayout(btn_layout)

    def confirm_exit(self):
        self.logger.info("User requested exit - showing confirmation dialog")
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.logger.info("User confirmed exit - shutting down application")
            QApplication.instance().quit()

    def set_close_enabled(self, enabled):
        # Enable/disable window close button and Exit button
        self.exit_btn.setEnabled(enabled)
        self._close_enabled = enabled
        self.logger.debug(f"Close functionality {'enabled' if enabled else 'disabled'}")

    def closeEvent(self, event):
        if hasattr(self, "_close_enabled") and not self._close_enabled:
            event.ignore()
            self.logger.warning("Close attempt blocked - process is running")
            QMessageBox.warning(
                self, "Action Blocked", "Cannot close while process is running."
            )
        else:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.logger.info("User confirmed exit via window close button")
                event.accept()
            else:
                self.logger.debug("User cancelled exit via window close button")
                event.ignore()

    def select_directory(self):
        self.logger.debug("Opening directory selection dialog")
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly,
        )
        if directory:
            self.output_dir.setText(directory)
            self.logger.info(f"Selected output directory: {directory}")
        else:
            self.logger.debug("No directory selected")

    def validate_inputs(self):
        if not self.output_dir.text():
            self.logger.warning("Validation failed: No output directory selected")
            QMessageBox.warning(
                self, "Missing Directory", "Please select an output directory"
            )
            return False

        if self.date_from.date() > self.date_to.date():
            self.logger.warning("Validation failed: Invalid date range")
            QMessageBox.warning(
                self, "Invalid Date Range", "From date cannot be after To date"
            )
            return False

        self.logger.debug("Input validation passed")
        return True

    def start_process(self):
        self.logger.info("Starting scraping process")
        if not self.validate_inputs():
            return

        # Disable close and exit during process
        self.set_close_enabled(False)
        self.start_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)

        # Gather data using variables as strings
        self.date_from = self.date_from.date().toString("MM/dd/yyyy")
        self.date_to = self.date_to.date().toString("MM/dd/yyyy")
        self.party_type = self.doc_type.currentText()

        self.logger.info(
            f"Scraping parameters - Date range: {self.date_from} to {self.date_to}, Party type: {self.party_type}"
        )

        # Scrape the data
        master_list = self.scraping(
            self.date_from, self.date_to, self.party_type, self.record_limit
        )
        if master_list:
            date = datetime.now().strftime("%m%d%Y_%H%M%S")
            filename = f"MD Probate Extracted Data_{date}.xlsx"
            output_path = os.path.join(self.output_dir.text(), filename)

            df = pd.DataFrame(master_list)

            df.columns = [col.lower().replace(" ", "_") for col in df.columns]

            final_columns = [
                "fiduciary_number",
                "court_file_number",
                "estate_number",
                "case_number",
                "county_jurisdiction",
                "date_of_filing",
                "date_of_will",
                "type",
                "status",
                "will",
                "decedent",
                "date_of_death",
                "decedent_address",
                "executor_first_name",
                "executor_last_name",
                "administrator_first_name",
                "administrator_last_name",
                "pow_first_name",
                "pow_last_name",
                "subscriber_first_name",
                "subscriber_last_name",
                "pr_first_name",
                "pr_last_name",
                "pr_address",
                "pr_city",
                "pr_state",
                "pr_zip",
                "heir_1_first_name",
                "heir_1_last_name",
                "relationship_1",
                "age_1",
                "address_1",
                "city_1",
                "state_1",
                "zip_1",
                "attorney_first_name",
                "attorney_last_name",
                "attorney_address",
                "attorney_city",
                "attorney_state",
                "attorney_zip",
                "url",
                "aggregated",
            ]
            missing_columns = set(final_columns) - set(df.columns)
            if missing_columns:
                # add missing columns with NaN values
                for col in missing_columns:
                    df[col] = ""

            df["age_1"] = pd.to_numeric(df["age_1"], errors="coerce").astype("Int64")
            for col in df.columns:
                if "zip" in col.lower():
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

            df["date_of_death"] = pd.to_datetime(df["date_of_death"], errors="coerce")

            # Populate Aggregate column with column:value;column:value;column:value;
            def aggregate_row(row):
                return (
                    ";".join(
                        f"{col}:{row[col] if pd.notnull(row[col]) and row[col] != '' else ''}"
                        for col in df.columns
                        if col != "aggregated"
                    )
                    + ";"
                )

            df["aggregated"] = df.apply(aggregate_row, axis=1)

            df = df[final_columns]
            # Validate the DataFrame against the shared schema
            try:
                ProbateSchema.validate(df, lazy=True)
                logger.info("DataFrame validation successful!")
                # Construct PR Columns
                new_columns = []
                for col in df.columns:
                    new_col = col.title().replace("_", " ")
                    if "pr " in new_col.lower():
                        new_col = new_col.replace("Pr ", "PR ")
                    new_columns.append(new_col)
                df.columns = new_columns
            except pa.errors.SchemaErrors as e:
                logger.error("DataFrame validation failed! %s", e.failure_cases)
                logger.error(f"DataFrame validation failed for file '{filename}': {e}")

            df.to_excel(output_path, index=False)
            self.logger.info(f"Excel file generated successfully: {output_path}")
            info_text = f"Excel generated successfully at:\n{output_path}"
        else:
            self.logger.error("Scraping failed - no data collected")
            info_text = (
                "Scraping failed. Please check your internet connection and try again."
            )

        # Show success message
        QMessageBox.information(
            self,
            "Execution Completed",
            info_text,
        )

        # Re-enable close and exit after process
        self.set_close_enabled(True)
        self.start_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        self.logger.info("Scraping process completed")

    def scraping(self, date_from, date_to, party_type, record_limit):
        self.logger.info("Starting scraping operation")
        counter = 1
        url = "https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx"
        raw_html = get_html(url)
        if not raw_html:
            self.logger.error("Failed to make request for fetching parameters")
            return []
        soup = BeautifulSoup(raw_html, "html.parser")
        parameters = get_parameters(soup, counter)
        case_urls = set()

        new_parameters, case_urls = scrape_page(
            parameters, case_urls, date_from, date_to, party_type, counter
        )
        counter += 1

        while new_parameters:
            self.logger.debug(f"Processing page {counter}")
            new_parameters, case_urls = scrape_page(
                new_parameters, case_urls, date_from, date_to, party_type, counter
            )
            counter += 1

        if record_limit:
            case_urls = list(case_urls)[:record_limit]
        total = len(case_urls)
        self.logger.info(f"Total case URLs collected: {total}")
        master_list = []

        for idx, url in enumerate(case_urls, 1):
            self.logger.info(f"Processing {idx} of {total}: {url}")
            master_list.extend(scrape_single(url))
            time.sleep(0.5)
            # Log current progress percentage
            progress = int((idx / total) * 100)
            self.logger.debug(f"Progress: {progress}%")

        self.logger.info(f"Scraping completed - {len(master_list)} records collected")
        return master_list

    def reset_form(self):
        self.logger.info("Resetting form to default values")
        # Reset date fields
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_to.setDate(QDate.currentDate())

        # Reset document type
        self.doc_type.setCurrentIndex(0)

        # Clear directory
        self.output_dir.clear()

        # Re-enable close and exit after reset
        self.set_close_enabled(True)
        self.start_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        self.logger.info("Form reset completed")


class MDScraperCli:
    def __init__(self, date_from, date_to, doc_type, output_dir, record_limit=None):

        # Setup logging for this application
        self.logger = logging.getLogger(__name__)
        self.logger.info("MDScraperApp initialized")

        # From date
        self.date_from_str = date_from
        self.date_from_obj = datetime.strptime(self.date_from_str, "%m/%d/%Y")

        # To date
        self.date_to_str = date_to
        self.date_to_obj = datetime.strptime(self.date_to_str, "%m/%d/%Y")

        self.doc_type = doc_type
        self.output_dir = output_dir
        self.party_type = PARTY_TYPES[self.doc_type]

        self.record_limit = record_limit

    def validate_inputs(self):
        if not self.output_dir:
            self.logger.warning("Validation failed: No output directory selected")
            QMessageBox.warning(
                self, "Missing Directory", "Please select an output directory"
            )
            return False

        if self.date_from_obj > self.date_to_obj:
            self.logger.warning("Validation failed: Invalid date range")
            QMessageBox.warning(
                self, "Invalid Date Range", "From date cannot be after To date"
            )
            return False

        self.logger.debug("Input validation passed")
        return True

    def start_process(self):
        self.logger.info("Starting scraping process")
        if not self.validate_inputs():
            return

        self.logger.info(
            f"Scraping parameters - Date range: {self.date_from_str} to {self.date_to_str}, Party type: {self.party_type}"
        )

        # Scrape the data
        master_list = self.scraping(
            self.date_from_str, self.date_to_str, self.party_type, self.record_limit
        )
        if master_list:
            date = datetime.now().strftime("%m%d%Y_%H%M%S")
            filename = f"MD Probate Extracted Data_{date}.xlsx"
            output_path = os.path.join(self.output_dir, filename)

            df = pd.DataFrame(master_list)
            df.columns = [col.lower().replace(" ", "_") for col in df.columns]

            final_columns = [
                "fiduciary_number",
                "court_file_number",
                "estate_number",
                "case_number",
                "county_jurisdiction",
                "date_of_filing",
                "date_of_will",
                "type",
                "status",
                "will",
                "decedent",
                "date_of_death",
                "decedent_address",
                "executor_first_name",
                "executor_last_name",
                "administrator_first_name",
                "administrator_last_name",
                "pow_first_name",
                "pow_last_name",
                "subscriber_first_name",
                "subscriber_last_name",
                "pr_first_name",
                "pr_last_name",
                "pr_address",
                "pr_city",
                "pr_state",
                "pr_zip",
                "heir_1_first_name",
                "heir_1_last_name",
                "relationship_1",
                "age_1",
                "address_1",
                "city_1",
                "state_1",
                "zip_1",
                "attorney_first_name",
                "attorney_last_name",
                "attorney_address",
                "attorney_city",
                "attorney_state",
                "attorney_zip",
                "url",
                "aggregated",
            ]
            missing_columns = set(final_columns) - set(df.columns)
            if missing_columns:
                # add missing columns with NaN values
                for col in missing_columns:
                    df[col] = ""

            df["age_1"] = pd.to_numeric(df["age_1"], errors="coerce").astype("Int64")
            for col in df.columns:
                if "zip" in col.lower():
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

            df["date_of_death"] = pd.to_datetime(df["date_of_death"], errors="coerce")

            # Populate Aggregate column with column:value;column:value;column:value;
            def aggregate_row(row):
                return (
                    ";".join(
                        f"{col}:{row[col] if pd.notnull(row[col]) and row[col] != '' else ''}"
                        for col in df.columns
                        if col != "aggregated"
                    )
                    + ";"
                )

            df["aggregated"] = df.apply(aggregate_row, axis=1)

            df = df[final_columns]

            # Validate the DataFrame against the shared schema
            try:
                ProbateSchema.validate(df, lazy=True)
                logger.info("DataFrame validation successful!")
                # Construct PR Columns
                new_columns = []
                for col in df.columns:
                    new_col = col.title().replace("_", " ")
                    if "pr " in new_col.lower():
                        new_col = new_col.replace("Pr ", "PR ")
                    new_columns.append(new_col)
                df.columns = new_columns
            except pa.errors.SchemaErrors as e:
                logger.error("DataFrame validation failed! %s", e.failure_cases)
                logger.error(f"DataFrame validation failed for file '{filename}': {e}")

            df.to_excel(output_path, index=False)
            self.logger.info(f"Excel file generated successfully: {output_path}")
        else:
            self.logger.error(
                "Scraping failed. Please check your internet connection and try again."
            )
        self.logger.info("Scraping process completed")

    def scraping(self, date_from, date_to, party_type, record_limit):
        self.logger.info("Starting scraping operation")
        counter = 1
        url = "https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx"
        raw_html = get_html(url)
        if not raw_html:
            self.logger.error("Failed to make request for fetching parameters")
            return []
        soup = BeautifulSoup(raw_html, "html.parser")
        parameters = get_parameters(soup, counter)
        case_urls = set()

        new_parameters, case_urls = scrape_page(
            parameters, case_urls, date_from, date_to, party_type, counter
        )
        counter += 1

        while new_parameters:
            self.logger.debug(f"Processing page {counter}")
            new_parameters, case_urls = scrape_page(
                new_parameters, case_urls, date_from, date_to, party_type, counter
            )
            counter += 1

        if record_limit:
            case_urls = list(case_urls)[:record_limit]
        total = len(case_urls)
        self.logger.info(f"Total case URLs collected: {total}")
        master_list = []

        for idx, url in enumerate(case_urls, 1):
            self.logger.info(f"Processing {idx} of {total}: {url}")
            master_list.extend(scrape_single(url))
            time.sleep(0.5)
            # Log current progress percentage
            progress = int((idx / total) * 100)
            self.logger.debug(f"Progress: {progress}%")

        self.logger.info(f"Scraping completed - {len(master_list)} records collected")
        return master_list


if __name__ == "__main__":
    # Setup logging before creating the application
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting MDScraperApp")

    # implement the logic to run in headless mode or GUI mode
    parser = argparse.ArgumentParser(description="Wills Register Maryland Scraper")
    parser.add_argument(
        "--headless",
        type=bool,
        default=False,
        help="Set the headless mode.",
    )
    parser.add_argument(
        "--date-from",
        required=True,
        type=str,
        help="Set the from date.",
    )
    parser.add_argument(
        "--date-to",
        required=True,
        type=str,
        help="Set the to date.",
    )
    parser.add_argument(
        "--doc-type",
        type=str,
        default="pr",
        help="Set the document type.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Set the output directory.",
    )
    parser.add_argument(
        "--record-limit",
        type=int,
        default=0,
        help="Set the record limit.",
    )

    args = parser.parse_args()
    # validate headless
    if args.headless:
        app = MDScraperCli(
            date_from=args.date_from,
            date_to=args.date_to,
            doc_type=args.doc_type,
            output_dir=args.output_dir,
            record_limit=args.record_limit if args.record_limit > 0 else None,
        )
        app.start_process()
        logger.info("Headless scraping process completed")
    else:
        app = QApplication(sys.argv)
        window = MDScraperApp()
        window.show()
        logger.info("Application window displayed")
        sys.exit(app.exec_())
