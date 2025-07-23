import os
import sys
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time

from utils import get_parameters, get_html, scrape_page, scrape_single

from PyQt5.QtCore import QDate, Qt
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

    def create_date_widgets(self, layout):
        # Date range section
        date_layout = QHBoxLayout()

        # From date
        from_layout = QVBoxLayout()
        from_layout.addWidget(QLabel("From Date:"))
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        from_layout.addWidget(self.from_date)

        # To date
        to_layout = QVBoxLayout()
        to_layout.addWidget(QLabel("To Date:"))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
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
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            QApplication.instance().quit()

    def set_close_enabled(self, enabled):
        # Enable/disable window close button and Exit button
        self.exit_btn.setEnabled(enabled)
        self._close_enabled = enabled

    def closeEvent(self, event):
        if hasattr(self, "_close_enabled") and not self._close_enabled:
            event.ignore()
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
                event.accept()
            else:
                event.ignore()

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly,
        )
        if directory:
            self.dir_input.setText(directory)

    def validate_inputs(self):
        if not self.dir_input.text():
            QMessageBox.warning(
                self, "Missing Directory", "Please select an output directory"
            )
            return False

        if self.from_date.date() > self.to_date.date():
            QMessageBox.warning(
                self, "Invalid Date Range", "From date cannot be after To date"
            )
            return False

        return True

    def start_process(self):
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

        # Scrape the data
        master_list = self.scraping(self.date_from, self.date_to, self.party_type)
        if master_list:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Estates_Data_{self.date_from.replace('/', '-')}_{self.date_to.replace('/', '-')}_{self.party_type.replace(' ', '_')}_{timestamp}.xlsx"
            output_path = os.path.join(self.dir_input.text(), filename)

            df = pd.DataFrame(master_list)
            df.to_excel(output_path, index=False)
            info_text = f"Excel generated successfully at:\n{output_path}"
        else:
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

    def scraping(self, date_from, date_to, party_type):
        counter = 1
        url = "https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx"
        raw_html = get_html(url)
        if not raw_html:
            print("Failed to make request for fetching parameters.")
            return []
        soup = BeautifulSoup(raw_html, "html.parser")
        parameters = get_parameters(soup, counter)
        case_urls = set()

        new_parameters, case_urls = scrape_page(
            parameters, case_urls, date_from, date_to, party_type, counter
        )
        counter += 1

        while new_parameters:
            new_parameters, case_urls = scrape_page(
                new_parameters, case_urls, date_from, date_to, party_type, counter
            )
            counter += 1

        print(f"Total case URLs collected: {len(case_urls)}")
        master_list = []
        total = len(case_urls)

        for idx, url in enumerate(case_urls, 1):
            print(f"Processing {idx} of {total}: {url}")
            master_list.extend(scrap_single(url))
            time.sleep(0.5)
            # Print current progress percentage
            print(f"Progress: {int((idx / total) * 100)}%")

        return master_list

    def reset_form(self):
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MDScraperApp()
    window.show()
    sys.exit(app.exec_())
