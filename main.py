import os
import sys
import logging
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import pandera.pandas as pa

from data_schemas import ProbateSchema
from utils import get_parameters, get_html, scrape_page, scrape_single, setup_logging

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


class MDScraperApp(QMainWindow):
    def __init__(self):
        super().__init__()
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
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("MM/dd/yyyy")
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        from_layout.addWidget(self.from_date)

        # To date
        to_layout = QVBoxLayout()
        to_layout.addWidget(QLabel("To Date:"))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("MM/dd/yyyy")
        self.to_date.setDate(QDate.currentDate())
        to_layout.addWidget(self.to_date)

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
        self.dir_input = QLineEdit()
        self.dir_input.setReadOnly(True)
        dir_layout.addWidget(self.dir_input)

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
            self.dir_input.setText(directory)
            self.logger.info(f"Selected output directory: {directory}")
        else:
            self.logger.debug("No directory selected")

    def validate_inputs(self):
        if not self.dir_input.text():
            self.logger.warning("Validation failed: No output directory selected")
            QMessageBox.warning(
                self, "Missing Directory", "Please select an output directory"
            )
            return False

        if self.from_date.date() > self.to_date.date():
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
        self.date_from = self.from_date.date().toString("MM/dd/yyyy")
        self.date_to = self.to_date.date().toString("MM/dd/yyyy")
        self.party_type = self.doc_type.currentText()

        self.logger.info(
            f"Scraping parameters - Date range: {self.date_from} to {self.date_to}, Party type: {self.party_type}"
        )

        # Scrape the data
        master_list = self.scraping(self.date_from, self.date_to, self.party_type)
        if master_list:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Estates_Data_{self.date_from.replace('/', '-')}_{self.date_to.replace('/', '-')}_{self.party_type.replace(' ', '_')}_{timestamp}.xlsx"
            output_path = os.path.join(self.dir_input.text(), filename)

            df = pd.DataFrame(master_list)
            column_rename = {
                "case": "Court File Number",
                "county": "County",
                "date_of_death": "Date of Death",
                "decedent": "Decedent",
            }

            df.rename(columns=column_rename, inplace=True)
            df["Date of Death"] = pd.to_datetime(
                df["Date of Death"], errors="coerce"
            ).astype(str)

            final_columns = [
                "Fiduciary Number",
                "Court File Number",
                "case_number",
                "Estate Number",
                "county_jurisdiction",
                "date_of_filing",
                "date_of_will",
                "type",
                "status",
                "will",
                "Decedent",
                "Date of Death",
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
                "Relationship 1",
                "Age 1",
                "Address 1",
                "City 1",
                "State 1",
                "Zip 1",
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

            df = df[final_columns]
            df["Age 1"] = pd.to_numeric(df["Age 1"], errors="coerce").astype("Int64")
            for col in df.columns:
                if "zip" in col.lower():
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

            df["Date of Death"] = pd.to_datetime(df["Date of Death"], errors="coerce")

            df.columns = [col.lower().replace(" ", "_") for col in df.columns]

            df["court_file_number"] = df["court_file_number"].astype(str).str.zfill(6)
            # Validate the DataFrame against the shared schema
            try:
                ProbateSchema.validate(df, lazy=True)
                logger.info("DataFrame validation successful!")
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

    def scraping(self, date_from, date_to, party_type):
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

        # TODO
        case_urls = list(case_urls)[:5]
        self.logger.info(f"Total case URLs collected: {len(case_urls)}")
        master_list = []
        total = len(case_urls)

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
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date.setDate(QDate.currentDate())

        # Reset document type
        self.doc_type.setCurrentIndex(0)

        # Clear directory
        self.dir_input.clear()

        # Re-enable close and exit after reset
        self.set_close_enabled(True)
        self.start_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        self.logger.info("Form reset completed")


if __name__ == "__main__":
    # Setup logging before creating the application
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting MDScraperApp")

    app = QApplication(sys.argv)
    window = MDScraperApp()
    window.show()
    logger.info("Application window displayed")
    sys.exit(app.exec_())
